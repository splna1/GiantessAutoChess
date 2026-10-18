# 交接：战斗演出观感修正（第二段：崩溃修复后重跑与配对漂移）

> 写于 2026-10-17 深夜，崩溃已修、验收已重跑、新证据图已出但**尚未看图**时被中断。
> **这不是项目文档**：不带编号，不放进 `document/`，不占用文档编号。
> 工程：`E:\AI\Tread\Tread`，UE 5.8.3，Windows 单机，非 git 仓库。
> **与 `HANDOFF_Battle_Visuals.md`（第一段）、`HANDOFF_M4_Battle.md`（M4/M5 主线）一起读**；本份只追加 2026-10-17 深夜之后的状态。
> **状态更新（2026-10-17 深夜，本交接已收口）**：§5.1 配对漂移已修（**P1/P2/P3 三个 AI 都配混编棋盘**，并在 `deploy` 后记录实际配对）、§5.2 重跑 **15/15 通过**（对手 P2 混编 6 人、敌方位移 1.96–3.94 格、17.4 秒进 Settlement、57.6 fps、编辑器前台）、五张证据图已看过（**烟尘消失、红蓝双方接敌**）、§5.3 规则条目已入库、过程记录写在 `document/158`。另修掉一个交接没提的证据缺陷：`M1_Audience_Camera.json` 一直记的是俯视相机。**后续以 `HANDOFF_M4_Battle.md`（M4/M5 主线）和 doc 158 §7（战斗演出剩余 7 项）为准。**

---

## 1. 当前目标

主人 2026-10-17 下午提出两点观感问题（敌人原地不动、棋盘被烟尘挡住），当晚拍板四项施工：删占位烟尘、`rangedRangeCells` 3.2→1.8、验收夹具给敌方也配近战+远程混编棋盘、重跑验收出新证据。

**当前状态（2026-10-17 深夜，已被接手会话收口）**：前三项落地；崩溃确诊修复并编译通过；22:35 重跑 10/10 通过但发现配对漂移（P0 的对手从 P1 漂到 P3，镜头上是灰盒）；**接手后**给 P1/P2/P3 都配了混编棋盘并记录实际配对，重跑 **15/15 通过**（对手 P2 混编，敌方位移 1.96–3.94 格），五张证据图已看（烟尘消失、双方接敌），过程记录写在 `document/158`。

一句话结论：**这条线已完成；剩余的战斗演出项（音频、侦察守卫、胜利光圈、观众镜头右侧遮挡等 7 项）在 doc 158 §7，按 `HANDOFF_M4_Battle.md` 主线排期。**

---

## 2. 已经完成了什么

| 项 | 状态 | 证据 / 位置 |
|---|---|---|
| 删占位烟尘 | 完成，地图已保存 | `Tools/battle/remove_board_smoke.py` 删 467 个 LocalFogVolume；`Saved/Reports/Battle_Smoke_Removal.json` |
| 方案 A：`rangedRangeCells` 3.2→1.8 | 完成，已重新生成数据 | `Tools/battle/build_battle_presentation.py` → `Content/Data/Generated/BattlePresentation.json`（C++ 磁盘直读，无需重导/编译） |
| 方案 C：敌方配混编棋盘 | 完成（代码层），当时**没进画面**；接手后改为三个 AI 都配，**已进画面** | `Tools/battle/battle_presentation_check.py` `phase_start` / `phase_deploy`；见 §5.1 配对漂移 |
| **崩溃根因确诊** | 完成 | 见 §4.1；转储 `Saved/Crashes/UECC-Windows-933A924342C2A64BB2CADE87604D893C_0000` |
| **崩溃修复 + 编译** | 完成，`Result: Succeeded` | `Source/Tread/TreadM1MatchController.cpp`；备份 `Saved/Backup/crash_fix_20261017/` |
| 脚本幂等坑修复 | 完成 | 敌方重摆 6 次移动改为独立 `RequestId` |
| **重跑验收（方案 A+C 后）** | **第一次 10/10 通过（22:35）；配对漂移修复后 15/15 通过（23:14）** | `Saved/Reports/Battle_Presentation_Check.json`：`ok=true`，`checks` 全 true，`settleWallSec=17.4`（≤45），`avgFps=57.6`（≥45），`fpsMeasured=true`；5 张证据图已出 |
| 看图验收 | **已完成（接手会话）** | `Saved/Screenshots/Battle_Run/Attack/Defeat/Victory.png`、`M1_Audience_View.png`（2026-10-17 23:14 新图）：烟尘已消失、红蓝双方接敌可读；观众镜头右侧仍被楼挡（既有开放项） |
| 写 158 号过程记录 | **已完成（接手会话）** | `document/158_UE5_战斗演出观感修正与验收重跑_2026-10-17.md`，索引已登记 |

### 2.1 重跑报告里的关键数字（本次新出，需正确解读）

- 我方（P0）近战 `travelledCells`：1.63 / 0.61 / 0.61；远程：0.21 / 0.09 / 1.45。
- 敌方（本次是 **P3 灰盒**，`ranged=false`，全部战死）：0.55 / 0.97 / 0.55。
- **对比 10-17 17:34 旧报告**：我方近战 2.65 / 2.85 / 3.33、敌方远程 0.32 / 0.39 / 0.59。
- **别误读成回归**：方案 A 生效后双方同时前压，接触更早、战斗更短（`victoryAt=6.28s`），所以**我方**位移也整体变小了。判据"敌方近战 ≥1.0、敌方远程 ≥0.5"是按旧场景（敌人站桩、我方长途奔袭）写死的，**需要重新校准**；真正该看的是"敌方单位是否都有可见接敌移动 + 画面是否读得出"。

---

## 3. 权威来源

- **代码修复点**：`Source/Tread/TreadM1MatchController.cpp`
  - `MoveUnitToBoard`：2138 行 `RemoveAt` 后，2143 行改用 2137 行已拷贝的 `Unit.UnitInstanceId`。
  - `MoveUnitToBench`：2185 行 `RemoveAt` 后，2193/2197 行同样改用 `Unit.UnitInstanceId`。
  - 已审计安全无需改：`SellUnit`（用 `SoldUnit` 副本）、`DestroyTransformClone`（用 `DestroyedClone` 副本）。
- **配对逻辑**：`TreadM1MatchController.cpp:1686-1709` `BuildPairings()` 用 `RandomStream` 洗牌；`TreadM2PactRuntime.cpp:1059-1060` `GrantUnitToPlayer` 的 tier 洗牌**消耗同一随机流** → 给谁配板就会改变谁跟 P0 打。
- **脚本**：`Tools/battle/battle_presentation_check.py`（各 phase，`phase_start` 在 161-191 行；`board_ids` 在 101 行，用 `seen`/`skip` 保证角色互不重复）、`Tools/battle/battle_presentation_check_pie.py`（驱动，约 4 分钟）、`Tools/battle/build_battle_presentation.py`。
- **数据**：`Content/Data/Generated/BattlePresentation.json`（脚本生成，不手改）、`Content/Data/Generated/CharacterRosterMap.json`（`board_ids` 用它筛 attackKind/profession）。
- **报告 / 证据**：`Saved/Reports/Battle_Presentation_Check.json`（新）、`Battle_Presentation_state.json`、`Saved/Screenshots/Battle_*.png`、`M1_Audience_View.png`。
- **崩溃取证**：`Saved/Crashes/UECC-Windows-933A924342C2A64BB2CADE87604D893C_0000`（`CrashContext.runtime-xml` 有带行号的栈）；`Saved/Diag/crash_exc.py <minidump>`（寄存器）、`Saved/Diag/disasm.py <dll> <rva> <before> <after>`（**四个参数缺一不可**，否则 IndexError）。
- **引擎源码**（定位机理时用）：`G:\epicgame\UE_5.8\Engine\Source\Runtime\Core\Public\Containers\Array.h:1554-1565`（`Find`）、`...\UnrealString.h.inl:1271-1294`（`FString::Equals`，`Num>1` 时直接 `Strcmp(GetData(), ...)`，不判空）。
- **备份**：`Saved/Backup/crash_fix_20261017/`（改动前版本）、`Saved/Backup/doc_20261017/`（第一段改动前版本）。

---

## 4. 不能重新争论的决策

- `HANDOFF_M4_Battle.md` §4 全部继续有效：**不手改 uasset/umap**、不手 K 动画、不删被引用的 IK Rig、中文回复 / 英文注释、**绝不自己启动或关闭编辑器**、改文件先备份、画面只信 `HighResShot`（`CaptureViewport` 不画 PIE Actor）、编辑器开着时不要编 `TreadEditor`。
- 本次拍板（第一段 §4）：占位烟尘**全部删除**、火焰/焦痕保留；`rangedRangeCells = 1.8`；只批 **A + C**，方案 B（双方前压到中线）未批，**不要顺手做**。
- 主人明确要求：给主人的提示词类交付物只写需求清单。
- 看图子代理：第一段主人指定 **Space-Bunny** 模型（仅限那次对话），下一会话是否沿用**先问主人**。

### 4.1 崩溃根因（已结案，不要再怀疑别的方向）

`MoveUnitToBoard` 自身的 use-after-free：

1. `StockBoardForFixture`（`TreadM2PactRuntime.cpp:1769`）把 `Player->BenchUnits.Last().UnitInstanceId` **按 const 引用**传入（不拷贝）；
2. `MoveUnitToBoard` 2138 行 `BenchUnits.RemoveAt(Index)` 销毁该元素 —— UE 5.8 的 `RemoveAt` 默认允许缩容，夹具每次恰好 1→0，整个元素缓冲区被释放回堆，分配器把 freelist 链接写进释放块首部，把悬垂 `FString` 的 `Data` 覆盖成 0 而 `Num=13` 还在；
3. 2143 行 `Find` → `FString::Equals` 两边 `Num>1` → `Strcmp(有效串, nullptr)` → 读 0x0。

寄存器互证：`rdx=0`（入参字符指针）、`rax=0x50='P'`（元素串 `"P1_unit_..."` 首字符）。P0 多年不崩纯属侥幸（P0 台位容量大，`RemoveAt` 不触发缩容释放）。**不是**第一段怀疑的"Player 指针跨广播失效"——广播链（FrontEndWidget / MatchWidget / DragController）只有同步可见性，没人重建 `Players`。

---

## 5. 下一步从哪里开始

> **§5.1–§5.3 已全部执行完毕（2026-10-17 深夜，接手会话）**，结果与数字见 `document/158`。下面保留原文作复盘，接手新任务时从 §5.4 与 `HANDOFF_M4_Battle.md` §5 继续。

### 5.1 先解决配对漂移（阻塞方案 C 成立）

- 现象：给 P1 配板后，6 次 `GrantUnitToPlayer` 各消耗 `RandomStream` 若干随机数，`BuildPairings` 洗牌结果变了 —— 从 17:34 的 P0↔P1 变成 P0↔**P3**。证据镜头只拍 P0 的战场，所以看到的是 P3 的灰盒 3 个单位（全近战），方案 C 的"敌方混编（近战+远程）接敌"没有出现在画面里。
- **建议做法（最简单、稳）**：`phase_start` 里对 **P1 / P2 / P3 三个 AI 玩家都配混编棋盘**（`want` 用 `("melee","melee","ranged","melee","heal","ranged")`，`exclude` 累加前面已选角色避免角色重复、池子被一方抽干），各自卖掉灰盒后按 `enemy_cells` 重摆（**每次移动必须独立 `RequestId`**）。这样无论洗牌把谁配给 P0，镜头里的敌人都是混编。
- 不要试图"预测配对再单独配那个人"：洗牌在 deploy 时才跑，复算脆弱。
- 状态记录：`state["runs"][tag]` 里现在只有一个 `boardEnemy`；改成按玩家记（如 `boardEnemies: {"P1": [...], "P2": [...], "P3": [...]}`），并保持 `stocked` 布尔语义（下游只用它判成功）。

### 5.2 再重跑 + 验收

1. `python Tools/ue_run.py -c "print(1)"` 确认在线（不在线请主人开编辑器，**不要自己启动**）。
2. `python Tools/battle/battle_presentation_check_pie.py`（约 4 分钟；编辑器保持前台，不要最小化）。
3. 判据：`checks` 10/10、`settleWallSec ≤ 45`、`avgFps ≥ 45`；**重点看 `units` 里 `enemy=true` 的单位**：既有 `ranged=false` 也有 `ranged=true`，且 `travelledCells` 明显高于旧值（旧敌方全部 < 0.6）。按 §2.1 的说明**重新校准位移阈值**，别拿旧阈值判回归。
4. **看图**（必做）：`Battle_Run.png`、`Battle_Attack.png`、`Battle_Defeat.png`、`Battle_Victory.png`、`M1_Audience_View.png` —— 确认①烟尘（大圆圈）已消失、②红蓝双方都有接敌位移。看图前先确认这是本轮新出的文件（mtime）。
5. 通过后写 `document/` 新过程记录：**先 Glob `document/15*.md` 取空号（当前 158）**，再更新 `100_DOCUMENT_INDEX.md`。

### 5.3 收尾要补的规则条目（`.codebuddy/rules/`）

1. **UE 5.8 `TArray::RemoveAt` + `const FString&` 入参的 use-after-free**：调用方传数组成员（`Arr.Last().Id`）给命令函数、函数内 `RemoveAt` 后再用该引用必崩；一律先拷副本。同款隐患已修 `MoveUnitToBoard` / `MoveUnitToBench`。
2. **夹具配板会消耗 `RandomStream` → 改变配对**：`GrantUnitToPlayer` 的 tier 洗牌与 `BuildPairings` 共用随机流，给某个 AI 配板会让 P0 的对手换人；要"敌方也有戏"就得给**所有** AI 配。
3. 命令 `RequestId` 幂等：同一 id 的第二次调用被 `TryGetProcessedRequest` 直接返回缓存结果（脚本里循环调命令必须每次换 id）。
4. `Saved/Diag/disasm.py` 需要 4 个参数；`UnrealEditor-Core.dll` 在 `G:\epicgame\UE_5.8\Engine\Binaries\Win64\`，工程 `Binaries\Win64\` 下没有。

### 5.4 主线未变

`HANDOFF_M4_Battle.md` §5.1 七项收尾仍全部未完成（战斗音频验收、侦察被拒、胜利动作与光圈错位、观众镜头右侧被楼挡、41 件装备 deferred、char_093/char_080 头像、策略回归脚本）；§5.2 M5 未开始；§5.3 主人人工目检仍开着。本次**不要**顺手去碰这些。

---

## 6. 该调用哪些 skills / 工具

| 场景 | 用什么 |
|---|---|
| 编辑器远程 Python、跑 PIE 检查 | `python Tools/ue_run.py <script>`，`status=OK` 判成功 |
| UE 工程通用约束与构建 | skill **tread-ue5-toolchain**、**tread-ue5-verify** |
| 启停 PIE / MCP | `Tools/ue_mcp.py`（`EditorToolset.EditorAppToolset`），或 skill **unreal-mcp-routing** |
| 崩溃排查 | `Saved/Diag/crash_exc.py` + `Saved/Diag/disasm.py`；转储 `Saved/Crashes/` |
| 大范围搜代码 / 文档 | code-explorer 子代理 |
| 看图验收 | 先问主人是否继续用子代理；不指定就自己 `read_file` 看图 |
| 规则 / 记忆 | 先读 `.codebuddy/rules/` 索引，按需 `read_rules` 加载条目 |

**Workflow 多代理编排**只有主人明确要求时才用。
