# 交接：战斗演出观感修正与 StockBoardForFixture(P1) 崩溃

> 写于 2026-10-17 夜，编辑器刚崩溃之后。
> **这不是项目文档**：不带编号，不放进 `document/`，也不占用文档编号。
> 交接对象：下一个接手 Tread 的 agent。**本份只管 2026-10-17 这条“战斗演出观感修正”线；M4/M5 主线仍以 `HANDOFF_M4_Battle.md` 为准，两份一起读。**
> **后续已写入 `HANDOFF_Battle_Visuals_2.md`（崩溃修复 + 重跑结果 + 配对漂移），接手请先读那份再看本份。**
> 工程：`E:\AI\Tread\Tread`，Unreal Engine 5.8.3，Windows 单机。不是 git 仓库。

---

## 1. 当前目标

主人在 2026-10-17 下午观察战斗演出后提出两点：**敌人原地不动、棋盘被烟尘挡住**。当晚确认现状后按主人拍板的方案施工：

1. **清烟尘**：删掉 `M3_Paris_Match` 上遮挡角色的占位烟尘（LocalFogVolume 堆叠球，主人原话“看起来只是几个大圆圈”），火焰/焦痕保留，后续换真实烟尘。
2. **方案 A**：`rangedRangeCells` 3.2 → 1.8，远程单位（含敌方）也有可见接敌移动。
3. **方案 C**：验收夹具给敌方（P1）也配近战+远程混编棋盘，证据图要能读出双方都在接敌。
4. 重跑 `battle_presentation_check_pie.py` 出新证据并验收。

**当前状态：1–3 的文件/地图改动已全部完成，第 4 步（重跑验收）被编辑器崩溃打断，未出新证据。**

### 1.1 现状核实的结论（本次确认，后面不用再争）

- 10-17 17:34 的报告（`Saved/Reports/Battle_Presentation_Check.json`）里：我方近战位移 2.65/2.85/3.33 格，我方远程 0.33/0.45/1.43 格，**敌方 3 个单位（全远程）只有 0.32/0.39/0.59 格**——俯视 50 像素尺度下等于完全没动。主人描述属实。
- 根因不是转向代码偏袒某方（`SteerUnit` 对所有单位对称，`TreadM3BattlePresentation.cpp:664`），而是：验收夹具敌方全是远程、固定摆最后排（graybox 摆 Y=0 行），`rangedRangeCells=3.2`（半场才 4 格）让远程一开场就几乎在射程内站桩。数值可互验：我方近战 2.85 + 敌方 0.32 ≈ 4.0（初始间距）− 0.8（近战射程）。
- Space-Bunny 子代理看图辅助确认：烟尘遮挡敌后排行、红圈在图上读不出，五张证据图里读不到任何敌方位移。烟尘遮挡也是本次实锤的。

---

## 2. 已经完成了什么

| 项 | 状态 | 证据/位置 |
|---|---|---|
| 现状核实（敌方位移 + 烟尘遮挡） | 完成 | §1.1；`Battle_Presentation_Check.json`（17:34 旧报告） |
| 方案 A 参数 | 完成 | `Tools/battle/build_battle_presentation.py` `rangedRangeCells` 3.2→1.8；`Content/Data/Generated/BattlePresentation.json` 已重新生成（C++ 用 `FFileHelper::LoadFileToString` 磁盘直读，**无需重导入、无需编译**） |
| 方案 C 夹具 | 完成（代码层） | `Tools/battle/battle_presentation_check.py`：新增 `ENEMY="P1"`、`player()` 助手；`board_ids()` 增加 `exclude`/`want` 参数；`phase_start` 先给 P1 配 3 近战（第 2 行）+2 远程+1 医疗（第 0 行），格子取 (4..6, 0/2) 避开 P2/P3 graybox 的 0–2 列 |
| 清烟尘 | **完成并已保存进地图** | `Tools/battle/remove_board_smoke.py`（新脚本）已跑通：`M3_Paris_Match` 删除 **467 个 LocalFogVolume**（棋盘雾霾 FX_Haze×2、棋盘烟柱 6 组、北面 8 组、工业带 69 柱、远景 2 组、外环 8 组），地图已 save。报告 `Saved/Reports/Battle_Smoke_Removal.json`。火焰卡片、余烬、火光、焦痕全部保留 |
| HANDOFF_M4_Battle.md 全目标核对 | 完成 | §5.3 |
| 崩溃修复（根因确诊 + 编译通过） | 完成 | §5.1；备份 `Saved/Backup/crash_fix_20261017/` |
| 重跑验收 | **未完成，等主人重开编辑器** | §5.2 |

改前备份：`Saved/Backup/doc_20261017/`（4 个文件的改动前版本）。

---

## 3. 权威来源

- **崩溃转储**：`Saved/Crashes/UECC-Windows-933A924342C2A64BB2CADE87604D893C_0000`（2026-10-17 21:52）。诊断脚本：`Saved/Diag/crash_exc.py <minidump>`、`Saved/Diag/disasm.py`。
- **战斗演出**：需求 `document/12_BATTLE_PRESENTATION.md`；实现记录 `document/155`（§5 已知问题：远程原地不动“设计如此”——本次主人拍板改掉这个观感）；代码 `Source/Tread/TreadM3BattlePresentation.cpp`、`TreadM3BoardPresenter.*`。
- **崩溃相关代码**：`Source/Tread/TreadM1MatchController.cpp:2095–2156`（`MoveUnitToBoard`，崩在 2143 行 `BenchUnitInstanceIds.Find`）；`Source/Tread/TreadM2PactRuntime.cpp:1747–1775`（`StockBoardForFixture`，1769 行调用点）；`TreadM2PactRuntime.cpp:1078–1082`（`GrantUnitToPlayer` 里对**同一个** `BenchUnitInstanceIds` 的 Find 是先成功过的）。
- **数据**：`Content/Data/Generated/BattlePresentation.json`（由 `Tools/battle/build_battle_presentation.py` 生成，不手改）。
- **验收报告/证据图**：`Saved/Reports/Battle_Presentation_Check.json`、`Saved/Screenshots/Battle_*.png`、`M1_Audience_View.png`。**注意：这些仍是 10-17 17:34 的旧行为证据**（敌方不动、烟尘在）；新证据待重跑。
- **残留状态文件**：`Saved/Reports/Battle_Presentation_state.json` 已被崩溃那次的 `load` 阶段重写为 `runs: {}`、`previousMap: M3_Paris_Match`、`throttleCpu: true`——没有可复用的运行数据。
- 主线交接：`HANDOFF_M4_Battle.md`（M4 剩余 7 项 + M5 清单）。

---

## 4. 不能重新争论的决策

- `HANDOFF_M4_Battle.md` §4 的全部规则继续有效（不手改 uasset、不手 K 动画、不删 IK Rig、中文回复/英文注释、**绝不自己启动或关闭编辑器**、改文件先备份、画面只信 HighResShot 等）。
- 本次新增拍板：
  - 占位烟尘**全部删除**（不限于挡角色的那几个），后续换真实烟尘；火焰/焦痕保留。
  - `rangedRangeCells = 1.8`（3.2 的旧值已被主人否掉，理由：半边站桩）。
  - 方案只批了 **A + C**；“双方前压到中线”的观感增强（方案 B）未批，不要顺手做。
- 看图子代理：本次主人指定 **Space-Bunny** 模型（仅限本对话）。下个会话是否沿用问主人；登记方式见 §6。

---

## 5. 下一步从哪里开始

### 5.1 崩溃（最优先，阻塞重跑）

栈（主人粘贴）：

```
EXCEPTION_ACCESS_VIOLATION reading 0x0
TArray<FString>::Find()  [Array.h:1559]
ATreadM1MatchController::MoveUnitToBoard()      [TreadM1MatchController.cpp:2143]
ATreadM1MatchController::StockBoardForFixture() [TreadM2PactRuntime.cpp:1769]
execStockBoardForFixture -> Python
```

- 触发：`battle_presentation_check.py` 的 `phase_start` 里新加的 `c.stock_board_for_fixture("P1", enemy_ids)`——**这是这套 API 第一次对非 P0 玩家调用**（P0 路径 10-14 起多次跑过没问题）。
- **根因已确诊（2026-10-17 深夜，崩溃转储 + 反汇编 + UE 5.8 源码三方互证）**：不是当初怀疑的 Player 指针跨广播失效，而是 `MoveUnitToBoard` 自身的 use-after-free。`StockBoardForFixture` 1769 行把 `Player->BenchUnits.Last().UnitInstanceId` 按 const 引用传进 `MoveUnitToBoard`（**不拷贝**）；`MoveUnitToBoard` 2138 行 `BenchUnits.RemoveAt(Index)` 销毁该元素（UE 5.8 `RemoveAt` 默认允许缩容，P1 夹具每次恰好 1→0，整个元素缓冲区被释放回堆，分配器 freelist 链接写进释放块首部，把悬垂 FString 的 `Data` 字段覆盖成 0 而 `Num=13` 还在），2143 行 `Find` 走到 `FString::Equals` 的 `Strcmp(有效串, nullptr)` → 读 0x0。寄存器互证：rdx=0（Item 的字符指针）、rax=0x50='P'（元素串 "P1_unit_..." 首字符）。P0 一直不崩只是侥幸：P0 台位容量大，RemoveAt 不触发缩容释放。
- **修复（已编译通过，Result: Succeeded）**：`TreadM1MatchController.cpp` 2143 行改用 RemoveAt 前已拷贝的 `Unit.UnitInstanceId`；`MoveUnitToBench` 2193/2197 行同款隐患一并修。`SellUnit`/`DestroyTransformClone` 审计过，用的都是副本，无需改。改前备份 `Saved/Backup/crash_fix_20261017/`。
- 顺手修了脚本幂等坑：`battle_presentation_check.py` 敌方重摆 6 次移动原来共用同一 `RequestId`（`tag+"-p1"`），第 2–6 次会被 `TryGetProcessedRequest` 幂等缓存吞掉；已改成每次独立 id（`%s-p1-%d`）。
- **下一步：请主人重新打开编辑器**，然后按 §5.2 重跑验收。
- 兜底（已不需要，保留备查）：把 `phase_start` 回退到只给 P0 配板（备份在 `Saved/Backup/doc_20261017/battle_presentation_check.py`），先只带方案 A 重跑验收。

### 5.2 崩溃后的验收步骤

1. `python Tools/ue_run.py -c "print(1)"` 确认在线（不在线请主人开编辑器，不要自己启动）。
2. 编完 C++ 后无需重导数据（BattlePresentation.json 磁盘直读）。
3. `python Tools/battle/battle_presentation_check_pie.py`（约 4 分钟；编辑器保持前台）。
4. 验收定量判据（新报告 `units` 数组）：敌方近战 `travelledCells` ≥ 1.0、敌方远程 ≥ 0.5（旧值全部 < 0.6）；`checks` 10 项全过；`settleWallSec` ≤ 45；帧率 ≥45 fps（编辑器最小化则记“未测”）。
5. 看图验收新证据图（`Battle_Run/Attack/Defeat/Victory.png`、`M1_Audience_View.png`）：确认烟尘已消失、红蓝双方都有位移。
6. 通过后把结果写进 `document/` 新过程记录（取号前先 Glob `document/15*.md`，当前空号 158）并更新本交接或并入主线交接。

### 5.3 HANDOFF_M4_Battle.md 目标核对结果（2026-10-17 核过，直接采信）

- §5.1 七项收尾**全部未完成**：①战斗音频验收（17:34 报告 voices/footsteps 仍 0，检查脚本还在 `Tread.Audio 0`）；②战斗中“侦察”被拒（`phase_guards` 没有侦察命令）；③胜利动作与光圈错位未查；④观众镜头右侧单位被楼挡未核实；⑤41 件装备条件/触发效果（`M4_ItemCatalog_Source_And_Validation.json` 的 `deferred` 仍 41 条）；⑥char_093 待机消失 / char_080 武器挡脸（头像资产 mtime 停在 10-14）；⑦策略“AI 确认前可改选”无回归脚本。
- §5.2 M5：**未开始**。§5.3 主人人工目检：仍开着。
- 另：10-15~10-17 额外完成了 UI 换装（doc 156/157 验收通过）；10-17 复跑 M1/M2/M4 自测与战斗演出检查全部仍绿（UI 改动后回归）。

---

## 6. 该调用哪些 skills 和工具

| 场景 | 用什么 |
|---|---|
| 编辑器远程 Python / 跑 PIE 检查 | `python Tools/ue_run.py <script>`，`status=OK` 判成功 |
| 启停 PIE / MCP | `Tools/ue_mcp.py`（`EditorToolset.EditorAppToolset`），或 skill **unreal-mcp-routing** |
| 崩溃排查 | `Saved/Diag/crash_exc.py <minidump>`（寄存器/栈上模块）+ `Saved/Diag/disasm.py <dll> <rva>`；转储在 `Saved/Crashes/` |
| 大范围搜代码/文档 | code-explorer 子代理 |
| 看图验收 | 本次指定 Space-Bunny 模型子代理：登记 `E:\AI\Tread\Tread\.codebuddy\agents\space-bunny.md`，frontmatter 里 `model: Space-Bunny`（**大小写敏感，小写会报 Bad Request 11130**），只给 `read_file` 工具；用完删除文件（主人限定本次对话）。以后会话先问主人 |
| Tread UE 工程通用约束 | skills **tread-ue5-toolchain**、**tread-ue5-verify**；规则目录 `.codebuddy/rules/`（先读索引） |
| 记忆/规则条目 | 本次两个新坑值得入规则目录：①`StockBoardForFixture` 对非 P0 调用会崩（修复后更新条目）；②Space-Bunny 子代理登记方式（含大小写坑） |

**Workflow 多代理编排**只有主人明确要求时才用。
