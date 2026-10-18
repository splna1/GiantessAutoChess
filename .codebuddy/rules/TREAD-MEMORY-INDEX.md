---
description: "《踏国》Tread UE5 项目长期记忆总索引（源：Claude 项目记忆，最近同步 2026-10-17）。在本项目里开工、写文档、跑 UE 编辑器/脚本、做资产导入与重定向、改 UI 之前先看这条，按需加载下列条目。"
alwaysApply: true
---

# Tread 项目记忆索引

来源：`C:\Users\spylnexus\.claude\projects\E--AI-Tread-Tread\memory\`（Claude 项目记忆，2026-10-14 首次迁入、2026-10-17 增量同步至 CodeBuddy `.codebuddy/rules/`）。
正文条目在同目录下，文件名即条目名，按需用 read_rules 读取。当前共 23 条。

## 硬约束与项目口径

- `tread-ue-constraints.md` — 只读源（Unity 旧工程/参考图/GP 导出）、资产必须由 Tools/ 下脚本生成、禁止手 K 动画、中文回复与中文文档、代码注释英文
- `tread-doc-numbering.md` — document/ 编号规则：00–19 只放需求与现状，100+ 是过程记录；下一个空号 158（先 Glob 再取号，156 = UI 原型+移植计划、157 = UI 移植说明）；当前进度与交接文件位置
- `tread-stronghold-plan.md` — 数值/盟约以 Stronghold-Protocol 数据为真源（只取数据不抄 GPL 代码）；112 卡 = 100 原卡 + 12 MMD
- `tread-board-readability.md` — 棋盘 8x8 庭院留空保持格子可读性；烟囱只能长在多层厂房顶上

## 构建 / 运行踩坑

- `tread-m2-runtime-notes.md` — Git Bash 会改写 `/Game/...` 路径、进程退出码不可信、编辑器开着时 UBT 链不上 DLL、C4458 是硬错误、standalone 别用 -Key=Value（会被当成地图名挂住）、reload_packages 会崩编辑器
- `tread-editor-python-map-switch.md` — 编辑器 Python 里 `load_level` 必须单独一次调用，同帧持有世界引用再切图必崩
- `tread-editor-vram-batch.md` — 8 GB 显卡长批次 GPU 崩溃（缩略图 FScene 每个约 90 MB）；小批次 + `Tread.FlushThumbnailScenes` + 定期重启编辑器；单个大 FBX 可卡数十分钟不算死
- `tread-shot-showui-crash.md` — 冻结（slomo）时发 `shot showui` 会挂起并在 PIE 后越界写崩编辑器；但 HighResShot 不画 Slate/UMG，看 UI 只能不冻结时发 `shot showui`，它截整个编辑器窗口、视口缩放约 0.554

## 验证 / 测量会骗人

- `tread-viewport-capture-lies.md` — `CaptureViewport` 不画 PIE 运行时 Actor；判游戏画面一律 `HighResShot` + 差分，差分前 `slomo 0` 冻结
- `tread-texture-normalmap-misdetect.md` — 蓝紫色基础色贴图被 UE 自动判成法线贴图；颜色贴图导入强制 TC_DEFAULT + sRGB

## MMD / 重定向

- `tread-mmd-root-scale.md` — MMD 棋子不显示的真因：FBX 根骨缩放 100 被重定向写成 1，整人缩成 1~2 cm；已改 Blender 导出设置
- `tread-mmd-facing.md` — MMD 进 UE 面朝 +Y、英雄 -Y；导出烘焙 yaw 180，UE 侧 `--reimport` 原地重导
- `tread-mmd-dbone-skin.md` — MMD 腿蒙皮只在 足D 系，GP 源动作也只动 D 骨；腿链两侧都接 D 骨，验收看 PIE 并排图
- `tread-retarget-pose-align.md` — 跨骨架重定向必须对齐 target retarget pose，否则手臂反向约 100° 而缩放全正常
- `tread-retarget-leg-split.md` — 单条腿链按比例插值会丢膝弯；腿拆 Thigh/Shin/Foot，源用 IK_Clukay416_LegSplit；swing 量大腿
- `tread-editor-ikrig-crash.md` — 删掉被 IK Retargeter 引用的 IK Rig 会崩编辑器；派生资产一律原地重配

## 崩溃 / 命令坑（2026-10-17 战斗演出那轮）

- `tread-tarray-removeat-aliasing.md` — `RemoveAt` 后继续用调用方按 `const FString&` 传进来的数组成员 = use-after-free（StockBoardForFixture→MoveUnitToBoard 实崩）；先拷副本
- `tread-battle-fixture-pitfalls.md` — 给 AI 配板会消耗 RandomStream 改变 P0 的对手（要给三个 AI 都配）；命令 `RequestId` 幂等，循环调命令必须每次换 id
- `tread-crash-dump-tools.md` — `Saved/Diag/crash_exc.py <minidump>` 看寄存器；`disasm.py <dll> <rva> <before> <after>` 四参数，`UnrealEditor-Core.dll` 在引擎 Binaries 下

## UI 移植 / Slate

- `tread-ui-style-prototype.md` — UI 换装（Ursus 构成主义 + Rhine 动效）原型 2026-10-15 通过、UE 移植 2026-10-17 完成验收（doc 157 §7）；玩家蓝（血条/脚圈）、敌人红；前台必须跳过自测参数
- `tread-hud-world-anchor-space.md` — `ProjectWorldToScreen` 给视口像素、`Ref/RefVec` 给设计像素，混用会把世界锚定的 HUD 全挤到左上角；先过 `ScreenToDesign()`
- `tread-slate-maketext-letterspacing.md` — UE 5.8 `MakeText` 不画 LetterSpacing、`FontMeasure` 也不算；字距只能 `MakeShapedText` 画 + 同一整形序列测宽

## 测量 / UE Python（2026-10-18 建筑破坏那轮）

- `tread-unreal-python-struct-aliasing.md` — `unreal.Transform` 赋值是别名不是拷贝，改副本会连源一起改，曾把碎片缩到 1% 而测出假帧率（已撤回）；缩放字段是 `scale3d`，`Transform()` 第二参数要 `Rotator`
