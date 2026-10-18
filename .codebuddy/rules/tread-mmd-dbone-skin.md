---
description: "MMD 腿部蒙皮只挂在 足D/ひざD/足首D 上，GP 源动作也只驱动 D 骨；重定向腿链两侧都必须走 D 骨，只量骨骼的探针看不出问题，验收要有 PIE 同帧并排图。"
---

# MMD D 骨蒙皮

12 个 MMD 模型（char_101–112）的腿部顶点**全部**权重在 `足D/ひざD/足首D`，`足/ひざ/足首` 权重为 0（MMD 里 D 骨靠"付与"跟随，UE 不执行付与）。英雄源骨架 Clukay416 的 GP 动作也一样：Walk 中 `21__joint_LeftFoot` 前后只动 ±4 cm，`245_joint_LeftFootD` 迈步 ±40 cm。

2026-10-12 前的重定向腿链是 `19__joint_LeftHip→21` 对 `足_L→足首_L`：骨头在动、蒙皮的腿笔直不动，Walk/Kneel/Stomp 全错；而只测手臂角、根骨缩放、包围范围的探针报 396/396 通过。加了 D 骨的髋→踝摆角 + 膝弯角判据后 303/396 不合格。

**Why:** "骨骼数据正常但画面不对"已是第三次（根骨缩放、retarget pose、D 骨）；只量骨骼不量蒙皮必然漏。

**How to apply:** M4 接 VRM/任何新骨架时，先用 Blender 读 FBX 顶点组统计每根腿/臂骨的蒙皮顶点数，链只接**有蒙皮**的骨；源骨架同样要查动作实际驱动哪组骨。验收必须有 PIE `HighResShot` 的源/目标同帧并排图（`Tools/m4/n2_retarget_review_pie.py`）。

Related: [[tread-retarget-pose-align]], [[tread-viewport-capture-lies]], [[tread-mmd-root-scale]]
