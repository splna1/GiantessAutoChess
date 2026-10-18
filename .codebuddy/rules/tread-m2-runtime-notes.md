---
description: "《踏国》本地构建/自测的非显然坑：Git Bash 改写 /Game/... 路径、退出码不可信、编辑器开着时 UBT 链不上 DLL、C4458 硬错误、reload_packages 会崩编辑器。跑构建或自测脚本前读这条。"
---

# M2 运行时踩坑

- Git Bash rewrites `/Game/...` args (also when forwarded to a `.ps1` via powershell; on 2026-10-07 this popped a "map C:/Program not found" dialog on the owner's screen) into `C:/Program Files/Git/Game/...`; set `MSYS_NO_PATHCONV=1` or use the pwsh runners (`Tools/m1/run_match_selftest.ps1`, `Tools/m2/run_m2_selftest.ps1`).
- `UnrealEditor-Cmd -game` does not reliably return `RequestExitWithStatus` codes; gate on the JSON report's `ok`/namedChecks, not the process exit code.
- UBT cannot link `UnrealEditor-Tread.dll` while the owner's editor is open; do not close an editor the owner opened without asking (check dirty packages first). Editor-side checks go through Unreal MCP (StartPIE/StopPIE) + `Tools/ue_run.py`.
- C4458 (param shadows AActor member, e.g. `Owner`) is a hard error in this module.
- `EditorLoadingAndSavingUtils.reload_packages` on a dirty map disconnected/crashed the editor (2026-10-09); for review shots use a scratch map (`Tools/m4/ue_mmd_lineup.py` -> `Review_Lineup`), never spawn into game maps.
- Material instances made by `get_or_create_mi` in batch may stay dirty; save own packages explicitly (filter by path) at the end of a step.

**Why:** each of these cost a failed run during M2 (2026-10-07).

**How to apply:** use the pwsh runners for native tests; ask before closing the editor for a rebuild.

Related: [[tread-ue-constraints]], [[tread-editor-vram-batch]]

## standalone 运行：别用 `-Key=Value`（2026-10-18）

`Start-Process -ArgumentList` 把 `-SomeFlag=Value` 交给引擎时，`=` 会让参数被拆成两个 token，引擎的地图解析把
`Value` 当成地图名去加载 → 弹模态错误框、进程挂住、日志停在启动阶段（本次两次 150 s 超时就是这么来的，现象很像
"游戏起不来"）。判别方法：同一份 exe 换回不带 `=` 的 flag 立刻正常。

做法：开关一律用**独立 flag**（`-TreadDestructionCascade` 而不是 `-TreadDestructionTest=cascade`），值需要传就把
数值作为单独参数或写进 URL 参数。跑 standalone 自测时同时给报告文件设**超时 + 5 s 宽限后强杀**，因为
`QuitGame` 在 Live Coding 附着时不一定真的结束进程。
