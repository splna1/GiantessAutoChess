---
description: "MMD 棋子在 PIE 里不显示的真因：Blender FBX 导出把骨架对象变成缩放 100 的根骨，重定向动画写成 1，整人缩到 1~2 cm；已在 Blender 导出侧修好。接新骨架/棋子不显示时读这条。"
---

# MMD 根骨缩放

2026-10-11 查明并修复：12 个 MMD 单位在棋盘上画不出来，**不是**创建顺序（`SetSkeletalMeshAsset` 在 `RegisterComponent` 前）也不是材质，而是动画把网格缩没了。

- 根因：旧导出（mmd_tools 导入缩放 0.08 + 导出器默认 `FBX_SCALE_NONE`）把米→厘米的 100 倍写进了每个物体变换，骨架对象 `<模型名>_arm` 被 UE 当成缩放 100 的根骨；重定向导出的 33×12 条 `A_GP_*` 把该根骨缩放写成 1（跟着英雄的根骨走），全身随之缩到百分之一。
- 实测对比（`Tools/m4/n2_fbx_scale_probe.py` + `Tools/m4/ue_n2_scale_probe.py`）：`FBX_SCALE_NONE` 得根骨缩放 100；`FBX_SCALE_ALL` **仍是 100**（UE 把文件头的单位缩放折回根节点）；只有"把几何直接做成厘米"得 1.0。
- 修法（已落地在 `Tools/m4/blender_mmd_to_fbx.py`）：mmd_tools 导入 `--scale 8.0` + 场景 `unit_settings.system='METRIC'`、`scale_length=0.01`，导出仍用 `FBX_SCALE_NONE`，即导出器完全不做缩放。重跑顺序：`n2_export_mmd_fbx.py` → `mmd_texture_alpha.py` → `ue_import_mmd.py --rebuild` → `ue_mmd_materials.py` → `n2_build_retarget.py`。
- 验证：`python Tools/ue_run.py Tools/m4/n2_anim_pose_probe.py`，参考姿势与动画姿势的根骨缩放都应为 1。

**Why:** 之前误判为创建顺序问题，差点去改 C++；真正要改的是 Blender 导出设置。

**How to apply:** 今后 100 个 VRM 若也走 Blender→FBX（M4），同样先在 UE 里量根骨缩放再往下做。

Related: [[tread-retarget-pose-align]], [[tread-viewport-capture-lies]], [[tread-ue-constraints]]
