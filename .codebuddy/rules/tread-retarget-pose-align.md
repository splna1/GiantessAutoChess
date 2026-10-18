---
description: "IK Retargeter 必须先把目标骨架的 retarget pose 对齐到源（MMD 是 A-pose、VRM 英雄是 T-pose），否则手臂反向转约 100 度而所有骨骼缩放仍是 1；验收要看 armDeg 关节角。"
---

# 重定向姿势对齐

2026-10-11：MMD 单位的待机动作把**两只手臂转到肩上方约 100 度**（手首在肩上方 26 cm，而英雄是肩下方 43 cm），脊椎、腿、所有骨骼缩放都正常 —— 看起来像"只错了一个部位"，实际是重定向姿势没对齐。

- 根因：`IK_Retargeter` 的 **target retarget pose** 默认取该骨架的参考姿势。VRM 英雄绑定是 **T-pose**（肩→腕几乎水平，87°），mmd_tools 导入的 MMD 模型绑定是 **A-pose**（59°）。两侧参考姿势不同，FK Chains op 就按错位的坐标系转，误差远大于两个绑定的差值本身。
- 修法（已落地在 `Tools/m4/n2_build_retarget.py` 的 `make_retargeter`）：`add_default_ops()` + `auto_map_chains(EXACT, True)` 之后调用 `controller.auto_align_all_bones(unreal.RetargetSourceOrTarget.TARGET, unreal.RetargetAutoAlignMethod.CHAIN_TO_CHAIN)`，再保存。修后 12 个角色的待机手臂角 20–26°，英雄 17–20°。
- **机器判据**：`Tools/m4/n2_anim_pose_probe.py` 现在会打印每条手臂"肩→腕向量偏离正下方"的角度（`armDeg`）。缩放和包围范围都看不出这个缺陷，只有这个角度能。
- 重定向器的链映射在 UE 5.8 的 Python 里**读不出来**（`get_all_chain_settings()` 返回空数组、`get_retarget_chain_settings()` 对任何名字都返回空结构、`auto_map_chains()` 无返回值）；能读的是 **IK Rig** 的链：`unreal.IKRigController.get_controller(rig).get_retarget_chains()`。

**Why:** 只差这个对齐，重定向出来的动作就是"手臂举着"的废动作；只看缩放/范围会误判为通过。

**How to apply:** 任何跨骨架重定向（M4 的 100 个 VRM 同理）建完 retargeter 就立刻对齐 target retarget pose，然后用 `armDeg` 等**关节角度**验收，不要只看包络。

Related: [[tread-mmd-root-scale]], [[tread-editor-ikrig-crash]], [[tread-retarget-leg-split]]
