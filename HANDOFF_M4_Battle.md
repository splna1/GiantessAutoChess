# 交接：M4 全量内容与战斗演出之后

> 写于 2026-10-14 夜。
> **这不是项目文档**：不带编号，不放进 `document/`，也不占用文档编号。
> 交接对象：下一个接手 Tread 的 agent。本文取代 `HANDOFF_N2.md`，那份只作历史记录。
> 工程：`E:\AI\Tread\Tread`，Unreal Engine 5.8.3（引擎在 `G:\epicgame\UE_5.8`），Windows 单机。不是 git 仓库。

---

## 1. 当前目标

《踏国 TREAD》是巨大少女题材的中文单机自走棋：4 人对局（玩家 + 3 个 AI），全自动战斗，12 回合，16 国战役。项目正在把它从 Unity 移植到 UE5。

到 2026-10-14，**M0–M4、N1、N2 和战斗演出（文档 12）都已实机验收**。下一阶段有两条线：

1. **收掉 M4 和战斗演出的剩余项**（见 §5.1），都是小而明确的工作。
2. **M5：性能调优、Windows 打包与发布门。** 施工计划 `document/_archive/UE5_移植施工计划.md` 的 §M5 是唯一的验收清单。

两条线都需要主人确认先做哪条。没有新指示时，先做 §5.1，再进 M5。

---

## 2. 已经完成了什么

| 阶段 | 内容 | 记录 |
|---|---|---|
| M0 | 巴黎写实城市棋盘、33 段 GP 动作 | 122、135 |
| M1 | 四人状态机、确定性随机、经济与商店、拖拽 UI、R1–R12 | 140 |
| M2 | 事件总线、盟约层数、数据驱动特质 | 141 |
| M3-A | `M3_Paris_Match` 地图、补充建模、3D 棋盘对局 | 142 |
| N1 | 按卫戍协议网页复刻的数值（112 名册、23 盟约、126 特质、40 策略、险境模拟经济） | 144、149 |
| N2 | 12 个 MMD 模型，按角色显示，33 段动作重定向 396/396 | 145、151 |
| M4-A | 99 个名册 VRM 导入、材质、33 段动作重定向（3267 段） | 152 |
| M4-B..E | 112 行名册、56 件装备 + 3 个法术、16 关战役、R12 数据领袖、世界统治结算、卡牌 Tooltip、名册审核面板 | 153 |
| M4 头像 | 商店和备战席头像改为 3D 模型胸部以上截图；PNG 立绘只用于单击后的详情层；6 个角色的贴图被误判为法线贴图，已修 | 154 |
| 战斗演出 | 先结算、再播 3D 演出；时间轴、移动、职业动作、血条飘字、观众镜头 | 155 |

**最近一次验证（2026-10-14，全部在主人的编辑器里实机跑）**

| 检查 | 命令 | 结果 |
|---|---|---|
| M4 自测（PIE，25 项）+ 5 张证据图 | `python Tools/m4/m4_selftest_pie.py` | 通过，`Saved/Reports/M4_SelfTest.json` |
| 头像检查（PIE）+ 4 张图 | `python Tools/m4/m4_avatar_check_pie.py` | 通过，`M4_AvatarCheck.json` |
| 战斗演出（PIE，10 项）+ 5 张图 | `python Tools/battle/battle_presentation_check_pie.py` | 通过，`Battle_Presentation_Check.json`；结算 14.8 秒、平均 56.8 fps |
| M1 原生回归 | 见 §4.4 | 通过，`M1_Match_SelfTest.json`（31/31） |
| M2 原生回归 | 见 §4.4 | 通过，`M2_Pact_SelfTest.json` |

以上全部编进了 `TreadEditor` 并在编辑器里跑过。2026-10-14 之后没有改过 C++。

---

## 3. 权威来源

### 3.1 文档（中文，`document/`）

- `00_PROJECT_MASTER.md`：项目正典、拍板口径（§2）、里程碑状态（§4）。**与其他文档冲突时以它为准。**
- `100_DOCUMENT_INDEX.md`：文档索引和编号规则（§1）。下一个空号是 **156**，取号前先 Glob `document/15*.md`，因为别的会话也会占号。
- `_archive/UE5_移植施工计划.md`：里程碑验收清单。勾选要如实，没验证过的不勾。
- `12_BATTLE_PRESENTATION.md`：战斗演出需求和验收（§8）。
- 过程记录：153（M4-B..E）、154（头像）、155（战斗演出）各有“未完成 / 已知问题”一节，这就是剩余工作的清单。

### 3.2 数据（`Content/Data/Generated/`，都由 `Tools/` 下的脚本生成，不要手改）

| 文件 | 生成脚本 | 用途 |
|---|---|---|
| `CharacterRosterMap.json`（112 行） | `Tools/m4/build_roster_map.py` | 名册真源：原版名、UE 模型、模型/头像/立绘/语音资产；C++ 运行时读取 |
| `Traits.json`、`Pacts.json`、`Strategies40.json`、`Economy.json` | N1 导入脚本（doc 144） | 卡池、特质、盟约、策略、经济 |
| `ItemCatalog.json`、`StrategyItems.json` | `Tools/m4/build_item_catalog.py` | 道具和法术 |
| `Campaign16.json`、`LeaderRounds.json` | `Tools/m4/build_campaign_data.py` | 16 关战役、R12 领袖 |
| `BattlePresentation.json` | `Tools/battle/build_battle_presentation.py` | 职业动作、时间参数、移动、镜头 |
| `ModelFacing.json` | `Tools/battle/ue_model_facing.py`（编辑器端） | 112 个模型的正面朝向（全部 -90°） |

只读的外部来源：Stronghold-Protocol 快照 `Content/Data/Source/StrongholdProtocol/`（只取数据，不抄 GPL 代码），道具快照 `Content/Data/Source/ItemStrategy_Snapshot.json`。

### 3.3 代码（`Source/Tread/`）

- `TreadM1MatchController.*`：对局状态机。战斗保持逻辑在这里：`SetBattlePresenterActive`、`NotifyBattlePresentationFinished`、`FinishHeldBattle`。
- `TreadM2PactRuntime.cpp`、`TreadM2PactData.cpp`：盟约、特质和数据加载。
- `TreadM4Campaign.cpp`：战役和测试接口（`*ForTest`）。
- `TreadM3BoardPresenter.*` + `TreadM3BattlePresentation.cpp`：3D 棋盘和战斗演出。
- `TreadM1MatchWidget.*`：整个 HUD，全部用 Slate 直接绘制。`WBP_*` 模板运行时不用。
- `TreadAudioDirector.*`：音频。

### 3.4 报告和证据

`Saved/Reports/*.json` 和 `Saved/Screenshots/*.png`。验收只认这两处的文件。

---

## 4. 不能重新争论的决策

### 4.1 主人拍板的玩法口径（见 `00_PROJECT_MASTER.md` §2）

- 数值、盟约、干员、道具、策略都以 Stronghold-Protocol 网页复刻为准，但保留 Tread 自己的 4 人 PvP 12 回合结构。
- 名册 112 个角色，即 100 个 VRM 加 12 个 MMD（`mmd_12`）。
- 经济用 N1 险境模拟口径：收入 min(3+回合,12)，没有利息和连胜收入。
- **策略 40 条**（`Strategies40.json`）：BAN 4，可选 36。施工计划里写的 32/28 是旧口径。
- 缪尔赛思（char_070）用 Modernia 模型；她的复制能力不扣公共卡池。
- 身高只影响视觉，不进伤害公式。

### 4.2 头像与立绘（主人 2026-10-14 定）

- 商店和备战席的头像 = VRM/MMD 模型**胸部以上**截图（`/Game/Tread/UI/Avatars/T_Avatar_char_XXX`，256²）。
- `lihui` 100 张和 `mmd_12` 12 张 PNG **只作单击后的详情立绘**（`/Game/Tread/UI/Portraits/`）。不允许把它们裁成头像。
- 交互：
  - 单击头像打开立绘详情。
  - 长按 0.6 秒关闭。
  - 战斗阶段禁止购买和拖拽。

### 4.3 战斗演出的架构

- **先结算，再演出**：控制器在战斗第一帧就结算出结果，Battle 阶段一直保持，直到演出器通知演出结束，或到 45 秒上限。演出永远不决定胜负。
- 时间轴是战斗事件的纯函数：同一个 seed，时间轴逐字一致。
- 演出期间 HUD 显示战前生命，击杀播报等结算后再出，不提前剧透结果。

### 4.4 工作规则（主人明确要求，违反过会出事）

- **绝不关闭或结束编辑器进程。** 需要关闭或重开时请主人操作。编辑器开着时：
  - 只能编 Game 目标：`"G:/epicgame/UE_5.8/Engine/Build/BatchFiles/Build.bat" Tread Win64 Development -Project=E:/AI/Tread/Tread/Tread.uproject -WaitMutex`
  - `TreadEditor` 目标要等主人关掉编辑器才能编，命令同上，把 `Tread` 换成 `TreadEditor`。
- Unity 原工程 `F:\AI\workbuddy\GiantessAutoChess` **只读**，不能在它上面运行 Unity。`mmd_12`、lihui、GP 导出也只读。
- 所有 `.uasset` 只能由 `Tools/` 下的脚本、编辑器 Python 或 MCP 生成和修改，不手改。
- 不手 K 动画；所有动作来自 GP 数据重定向。
- **不删 IK Rig 或 IK Retargeter**，删了会让编辑器崩溃，要原地重配。
- 回复和文档用中文，代码注释用英文。
- 改文件前先备份到 `Saved/Backup/doc_YYYYMMDD/...`。
- 画面效果只看 HighResShot 或游戏内截图，不信编辑器视口捕获。
- 看图交给 Sonnet 子代理（`model: "sonnet"`），主人的要求。

### 4.5 已经踩过的坑（详情在 memory）

- **游戏被冻结时（`slomo 0.0001`）不要发 `shot showui`。** 请求会挂起，PIE 结束后越界写，编辑器崩溃。2026-10-14 崩过两次。冻结时只用 `HighResShot`。
- **切地图（`load_level`）必须单独一次远程调用**，切之前先查有没有未保存的包。
- 远程 Python：只输出 ASCII，不用 `time.sleep`；Git Bash 里传 `/Game/...` 路径要加 `MSYS_NO_PATHCONV=1`，否则会被改写成 `C:/Program Files/Git/Game/...`。
- **显存守护**：8 GB 显卡跑长批次会让 GPU 崩溃。`nvidia-smi` 超过 6300 MiB 就停批次，批次之间执行 `Tread.FlushThumbnailScenes` 和 `Tools/m4/editor_release.py`。
- **颜色贴图导入必须强制 `TC_DEFAULT` + sRGB**，否则 UE 会把偏蓝紫的贴图自动判成法线贴图。检查命令：`Tools/m4/fix_color_textures.py --check`。
- 编辑器在后台时只有约 3 fps。战斗检查期间会临时关掉“后台时降低 CPU 占用”，结束后恢复；编辑器最小化或锁屏时，帧率记“未测”。
- PIE 运行时 `EditorAssetLibrary.does_asset_exist` 恒为 False，要直接加载资产判断。UE 5.8 把 `WidgetBlueprintLibrary` 改名为 `WidgetLibrary`。

**原生回归命令**（不用开编辑器窗口，可以和编辑器并行运行）：
```
MSYS_NO_PATHCONV=1 "G:/epicgame/UE_5.8/Engine/Binaries/Win64/UnrealEditor-Cmd.exe" "E:/AI/Tread/Tread/Tread.uproject" /Game/Tread/Maps/M1_Match_Graybox -game -TreadM1SelfTest -TreadSeed=20260926 -nullrhi -unattended -nosplash -nosound -NoLiveCoding
```
M2 用同一条命令，把 `-TreadM1SelfTest` 换成 `-TreadM2SelfTest`。判定看报告里的 `ok`，进程退出码不可靠。

---

## 5. 下一步从哪里开始

开工前先确认编辑器是开着的：`python Tools/ue_run.py -c "print(1)"` 应输出 `status=OK`。如果连不上，请主人打开编辑器，不要自己启动。

### 5.1 收尾项（按建议顺序）

> 2026-10-17 补记：主人在 10-17 提的"敌人原地不动 / 烟尘挡屏"那条观感线已单独收口（删 467 个占位烟尘、`rangedRangeCells` 1.8、验收夹具三个 AI 都配混编棋盘、判据 15 项），记录在 `document/158`，**不属于下面这 7 项**。下面 7 项仍然全部未完成。

1. **战斗音频验收**（12 §8 第 5 条）：检查脚本 `Tools/battle/battle_presentation_check.py` 在 `start` 里把音频关了（`Tread.Audio 0`）。加一个打开音频的运行，确认报告里 `voices`、`footsteps` 计数不为 0，且不串场。
2. **战斗中“侦察”被拒**（12 §8 第 3 条）：在 `phase_guards` 里加侦察命令。
3. **胜利时单位和脚下光圈错位**：怀疑 Victory 片段带根位移，查 `A_GP_Victory` 的根骨轨迹和 `TreadM3BattlePresentation.cpp` 里的 `Place`。
4. **观众镜头下右侧单位下半身被楼挡住**：用 HighResShot 拉近核实是否陷进屋顶。
5. **41 件装备的条件/触发效果**：概率、复活时间等，列表在 `Saved/Reports/M4_ItemCatalog_Source_And_Validation.json` 的 `deferred`。
6. **char_093 的待机动作会让模型消失**（头像拍成了 T-pose），先按 memory `tread-mmd-root-scale` 查根骨缩放。**char_080** 的头像前景有武器挡脸。
7. 策略“AI 确认前玩家可改选”单独回归。

### 5.2 M5

按施工计划 §M5 做：4 个采样点的性能报告、Windows 打包、打包版从主菜单到第 1 关 12 回合再到结算和存档完整跑通、打包版音频，最后请主人用打包版确认画面与手感。可以从 `Tools/run_m0_perf.ps1` 的测法起步。

### 5.3 主人的人工确认（自动报告代替不了）

M0、M1、M2、M3 的画面与手感目检，施工计划里都还开着。

---

## 6. 该调用哪些 skills 和工具

| 场景 | 用什么 |
|---|---|
| 在编辑器里执行 Python、建资产、跑 PIE 检查 | `python Tools/ue_run.py <script> args`，以 `status=OK` 判成功；实时日志在 `Saved/Logs/ue_run_last.log` |
| 启停 PIE、调 Unreal 的 MCP 工具 | `Tools/ue_mcp.py`（`StartPIE`/`StopPIE` 在 `EditorToolset.EditorAppToolset`），或 skill **`anthropic-skills:unreal-mcp`** |
| 看截图、评审画面 | Agent 工具，`model: "sonnet"`。只做看图，不让它开编辑器或改文件 |
| 大范围搜代码和文档 | Agent `Explore` |
| 改完 C++ 自查 | skill **`code-review`**，也可以用 **`simplify`** |
| 记忆整理 | skill **`anthropic-skills:consolidate-memory`**（memory 目录：`C:\Users\spylnexus\.claude\projects\E--AI-Tread-Tread\memory\`） |
| 画性能图表（M5 报告） | skill **`dataviz`** |
| 编辑器崩溃排查 | 两个脚本：`Saved/Diag/crash_exc.py <minidump>`（异常地址、寄存器、栈上模块）和 `Saved/Diag/disasm.py <dll> <rva> 120 40`（capstone 反汇编）；崩溃转储在 `Saved/Crashes/` |

**Workflow 多代理编排**只有主人明确要求时才用。
