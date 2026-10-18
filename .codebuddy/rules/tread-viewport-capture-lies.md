---
description: "Tools/ue_shot.py 的 CaptureViewport 不渲染 PIE 里运行时创建的 Actor，截图会骗人；判游戏画面一律用 HighResShot + 显示/隐藏差分，差分前 slomo 0 冻结。任何 PIE 画面验收前必读。"
---

# 视口截图会骗人

`Tools/ue_shot.py`（走 MCP `EditorToolset.EditorAppToolset.CaptureViewport`，即"关卡视口捕获"）**不会渲染 PIE 世界里运行时创建的 Actor**。它画出来的是关卡静态几何加上关卡里已有的 Actor，presenter 在 PIE 里 NewObject 出来的组件它一个都不画。

2026-10-11 实测证据（`M3_Paris_Match`，PIE 中）：

- 同一个机位，游戏视口 `HighResShot` 画出 24 个棋子组件 + 满盘选择环；`CaptureViewport` 只画出 1 个人和 1 个环。
- 在 PIE 里把 presenter 隐藏（`set_actor_hidden_in_game(True)`）→ `CaptureViewport` 那张图**一个像素都没变**；同一时刻 `HighResShot` 的棋盘**整个空了**。
- 因此那条路径测不出 presenter 的任何状态：以前用它做的"藏 MMD 组件不影响画面""换网格不影响画面""stop() 不影响画面"等结论全部作废。

**Why:** 这条坑害了整整一轮 N2 排查——截图一直显示"只渲染 1 个单位"，于是去怀疑世界错位、视锥剔除、渲染状态、动画，真正的原因只是测量工具画的是另一个世界。

**How to apply:** 任何"PIE 里到底画出了什么"的判据，用游戏视口自己的输出：
- `unreal.SystemLibrary.execute_console_command(world, "HighResShot 1")` → 落到 `Saved/Screenshots/WindowsEditor/HighresScreenshot*.png`（真实游戏画面，且会被 `set_actor_hidden_in_game` 影响）。
- 判"某个组件画出来没有"用**差分**：同机位拍"显示 / 隐藏"两张相减，比看 `was_recently_rendered()` 可靠得多（该标志会给出与画面矛盾的读数）。差分前先 `slomo 0` 冻结对局，否则烟尘粒子和回合推进会污染差分。
- 独立游戏窗口截图（`capture_m2.ps1` 那条路）同样有效，M1/M2/M3 一直用它。

Related: [[tread-ue-constraints]], [[tread-m2-runtime-notes]], [[tread-shot-showui-crash]]
