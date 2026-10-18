---
description: "MMD 模型导进 UE 面朝 +Y，英雄 Clukay416 面朝 -Y；已在 Blender 导出时烘焙 yaw 180（不能留在节点上），UE 侧用 --reimport 原地重导。接新模型时先量朝向。"
---

# MMD 朝向

mmd_tools 导入的模型面朝 Blender -Y，经 FBX（axis_forward -Z）进 UE 后面朝 +Y；M1 英雄 Clukay416 面朝 -Y（参考姿势足首→脚尖向量判定）。presenter 对所有单位用同一个 yaw，于是 MMD 在棋盘上背对敌人。2026-10-12 在 `Tools/m4/blender_mmd_to_fbx.py` 加 `--yaw 180`（默认），旋转烘进几何和骨骼 rest pose；UE 侧用 `ue_import_mmd.py --reimport` 原地重导（不删 `Retarget/`，避免 IK Rig 崩溃），之后必须重跑材质和重定向。

**Why:** 骨骼之间的角度看不出整体转 180°，只量关节的探针全绿。

**How to apply:** M4 接 VRM 时先量新模型和英雄的朝向（髋部左右轴或脚尖向量）；转向只能烘进几何，不能留在节点上（同根骨缩放的理由）。`n2_anim_pose_probe.py --clip all` 现在带 facing 判据。

Related: [[tread-mmd-root-scale]], [[tread-editor-ikrig-crash]]
