---
name: tread-ue5-verify
description: "在 Tread 工程里验收/验证 UE 渲染结果、PIE 表现、资产导入是否真的生效、性能是否达标、编辑器日志有没有报错时使用。触发词：验收、验证、截图、差分、PIE、FPS、性能、显存、日志报错、画面不对、没显示出来。"
---

# Tread 验收口径

## 第一原则：测量工具会骗人

**判"游戏里到底画出了什么"只用 `HighResShot` + 差分。**

`Tools/ue_shot.py` 走的 `CaptureViewport`（关卡视口捕获）**根本不渲染 PIE 里运行时创建的组件**：

- 同一机位：它画 1 个单位，`HighResShot` 画 24 个；
- 在 PIE 里把 presenter 隐藏，它**一个像素都不变**。

这条坑害过整整一轮排查。要验收 PIE 画面就走验收编排脚本，不要用 `ue_shot.py` 下结论。

其它已知会骗人的读数：

- **`was_recently_rendered()` 会与画面矛盾**（它说 24/24 在渲染而画面里只有 3 个）——不要单独信它。
- **差分前先 `slomo 0` 冻结对局**，否则烟尘粒子和回合推进污染差分。
- **`slomo` 是控制台变量，跨 PIE 会话存活**——收尾必须复位，否则下一次 PIE 里 presenter 永远不 tick、组件数恒为 0。
- 开启 Nanite 后 `get_num_triangles` 返回的是 **fallback** 网格三角数，不是资产真实三角面数。

## 证据落盘

| 想看什么 | 以谁为准 |
|---|---|
| 运行结果（数字、ok 标志） | **`Saved/Reports/*.json`**，不看文档里的转述 |
| 视觉证据 | `Saved/Screenshots/*.png` |
| 报错 | `Saved/Logs/Tread.log`；用 `sh Tools/ue_logcheck.sh <start_line>` 过滤材质/shader/python 问题 |
| 长任务实时进度 | `Saved/Logs/ue_run_last.log`（stdout 会缓冲；`ue_run.py` 退出码不可靠，看 `status=OK`/`status=FAIL`） |

## 验收编排

```bash
python Tools/m4/n2_accept_pie.py [--set vrm]        # 切图 → StartPIE → 铺盘 → 冻结拍图 ×2 → 停 → 还原地图
python Tools/m4/n2_retarget_review_pie.py --set vrm --chars ... [--shots SitCrush,Grab] [--front]
python Tools/ue_run.py Tools/m4/n2_anim_pose_probe.py --set vrm --clip all --only char_002,...
python Tools/m4/n2_render_truth.py
```

**棋盘验收的完整证据包**（缺一项就不算验收）：

- `M4_Accept_Board.png` / `N2_Accept_Board.png` —— 全单位画出
- `*_No*` 对照图 —— 藏掉被测对象后选择环空着
- `*_DiffMask.png` —— 差分掩码出人形轮廓
- `*_Zoom_AB.png` —— 左右并排，可直接目检
- `*_Diff.json` —— **差分像素计数**（例：247,161 像素 = 6.70%）
- `*RenderTruth.json` —— 普查（bodies / 目标数 / visible）

## 姿势探针

`n2_anim_pose_probe.py` 只读探针，报**根骨缩放、包围范围、手臂角 `armDeg`、NaN**。

- 根骨缩放应为 **1**；英雄 `armDeg` 17–20°，MMD 20–26°。
- **数值越界不等于缺陷**：背视角下坐姿伸腿会被透视压缩使包围盒变窄；弯腰时飘带袖子会撑大包围盒。
  **必须看图确认**再判定（char_057 SitCrush 0.61×、char_052 Grab 1.60× 都是误报）。
- 大盾、火焰发、裙摆会遮住腿导致目检看不清，但数值扫描可以通过——两者互为补充。

## 性能门

- 目标平台 Windows，**1080p 准备阶段稳定 ≥60 FPS，战斗 ≥45 FPS**。
- **平均值通过不等于达标**：M0 收尾平均 69.89 FPS 过了，但 1% low = 56.89 **低于 60**，是挂账项。
- 8 GB 显存预算靠异步加载、材质实例合批、LOD、VSM/Nanite 池与 Niagara 分开采样。
- 批量任务每批前 `nvidia-smi` 看显存，超过 **6300 MiB** 就停。

## 硬规则

- **下结论前自己看图。** 不要凭日志或坐标说"完成了"。
- 报告写结论时给出**证据文件路径 + 数值**，不要写"已验证通过"这种没有落点的句子。
- 验收不通过就如实报告，不要为了收工把门槛说成达标。
