---
description: "冻结（slomo 0.0001）时发控制台命令 shot showui 会挂起，并在 PIE 结束后于 D3D12RHI 像素回读里越界写崩编辑器；冻结状态下只用 HighResShot。要截编辑器窗口 UI 时读这条。"
---

# shot showui 崩溃

2026-10-14 编辑器两次在空闲时崩溃（12:10、12:36 UTC），签名相同：EXCEPTION_ACCESS_VIOLATION writing user32.dll+0x14b4c，崩溃点 UnrealEditor-D3D12RHI.dll+0x10d25c，是 R10G10B10A2→8bit 的像素转换循环（屏幕回读），调用方是 SlateRHIRenderer。两次之前都有战斗检查里发出却始终没出文件的 "shot showui"（当时游戏被 slomo 0.0001 冻结）。推断：挂起的 UI 截图请求在 PIE 结束后对编辑器窗口回读，尺寸不符导致越界写。推断依据是反汇编+时间线，无符号，未 100% 证实。

**Why:** 没有 Windows 事件（无 TDR/休眠），模块无第三方 overlay；寄存器 rax=0xff151515 是 Slate 背景色像素。

**How to apply:** 冻结游戏时只用 HighResShot，不要发 "shot showui"；"shot showui" 只在正常速度、编辑器前台时用（M4 自测那样）。若 "shot showui" 20 秒没出文件，别重复发，结束后提醒用户可能需要重启编辑器。崩溃排查工具：`Saved/Diag/crash_exc.py`（读 minidump 异常与栈）、`Saved/Diag/disasm.py`（capstone 反汇编）。

补充（2026-10-16）：HighResShot 只读视口渲染目标，**不含 Slate/UMG**（`Battle_Run.png` 没有 HUD 和血条）。凡是要看 UI（前台、HUD、血条）的证据只能用 "shot showui"，且必须在不冻结时发；尺寸是编辑器视口大小（如 1361x774），不是 1920x1080。UI 冻结用控件自己的测试钩子（如前台 `FreezeTransitionForTest`），不要用 slomo。

更正（2026-10-17）：1361x774 是**整个编辑器窗口**（含菜单、大纲面板），游戏视口只占约 x7..1080、y137..735，对 1920x1080 设计空间的缩放约 0.554，不是 0.709。交给审查员时要说明裁剪范围和缩放；小字号细节（字距、Mono 0、Stencil 4）在这个缩放下不可靠，整像素字距取整会让 Mono 标签显宽约 15%。

**第二次崩（2026-10-17 23:36，第三种触发条件）**：窗口被**最小化**时发的 `shot showui` 一样会崩，哪怕游戏没有冻结。经过：先 `ShowWindow(SW_RESTORE)` 再发命令，转储 `Saved/Crashes/UECC-Windows-D5E014E84C5DE8495732F0A6C13E9FA9_0000`，崩在 `UnrealEditor-SlateCore.dll+0x18fd24` 读 `0xffffffffffffffff`，寄存器满是 `0xff151515`（堆毒化），栈 SlateCore→RenderCore→RHI→SlateCore —— 就是 Slate 整窗截图的回读路径。
**结论：`shot showui` 只在"编辑器前台、窗口正常、游戏不冻结"三者同时成立时才算相对安全；最小化或刚恢复的窗口一律不要发。**

**替代做法（HUD 证据，2026-10-17 起）**：用 `pwsh Tools/ue_hud_shot.ps1 -Out Saved/Screenshots/HUD_xxx.png` —— 纯系统层 `CopyFromScreen` 抓编辑器窗口，完全不进 UE 的截图请求，不会崩。要求编辑器窗口可见、未最小化（脚本会先置前）。

Related: [[tread-editor-vram-batch]], [[tread-viewport-capture-lies]], [[tread-ui-style-prototype]]
