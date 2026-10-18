---
description: "编辑器崩溃取证的两个脚本：Saved/Diag/crash_exc.py <minidump> 看异常地址/寄存器/栈上模块；Saved/Diag/disasm.py <dll> <rva> <before> <after> 必须四个参数，UnrealEditor-Core.dll 在引擎 Binaries 下。排查 Saved/Crashes/ 转储时用。"
---

# 崩溃取证：`crash_exc.py` 与 `disasm.py`

转储在 `Saved/Crashes/UECC-Windows-*`（每次崩溃一个目录，`CrashContext.runtime-xml` 里有带行号的栈）。

## `Saved/Diag/crash_exc.py <minidump>`

输出异常码、出错地址、寄存器快照和栈上的模块归属。2026-10-17 那次就是靠寄存器互证确认
`FString` 的 `Data` 被写成了 0（`rdx=0`，而 `rax=0x50='P'` 是元素串首字符）。

## `Saved/Diag/disasm.py <dll> <rva> <before> <after>`

**四个参数缺一不可**（少一个直接 IndexError）。`<before>` / `<after>` 是相对该 rva 前后反汇编多少字节，
常用 `120 40`。

- `UnrealEditor-Core.dll` 在 `G:\epicgame\UE_5.8\Engine\Binaries\Win64\`——工程 `Binaries\Win64\` 下
  **没有**引擎 dll，找不到时别在工程目录里翻。
- rva 用 `crash_exc.py` 报的"模块 + 偏移"，不要拿绝对地址硬算。

**How to apply:** 先 `crash_exc.py` 拿到模块/偏移/寄存器，再 `disasm.py` 反汇编那个 rva 看具体指令，
最后回引擎源码（`G:\epicgame\UE_5.8\Engine\Source\...`）对照行号。三样互证之后再改代码——2026-10-17
那次一开始怀疑"Player 指针跨广播失效"，方向完全是错的。

Related: [[tread-tarray-removeat-aliasing]], [[tread-m2-runtime-notes]], [[tread-battle-fixture-pitfalls]]
