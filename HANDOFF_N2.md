# N2 交接：MMD 按角色模型与动作重定向

> 写于 2026-10-11 深夜，2026-10-12 凌晨定稿。
> **不是项目文档**：不带编号，不进 `document/`，不参与文档编号序列。
> 交接对象：下一个接手 Tread 的 agent。
> **2026-10-14：本文已被根目录 `HANDOFF_M4_Battle.md` 取代，只作历史记录。**
> **本文优先于** `document/145_*.md` 和 `document/148_*.md` —— 那两份写着"重定向未开始"，已经过期。

> **2026-10-12 更新：§5 第一步、第二步已完成，N2 正式收尾，见 `document/151_*.md`。**
> 补齐验证时又发现并修掉两个缺陷（本文 §2 写"已完成"时它们还在）：
> ① **腿完全不动**：MMD 腿蒙皮只挂在 `足D/ひざD/足首D`，GP 源动作也只动 D 骨，原腿链接的是普通腿骨 → 两侧改接 D 骨；
> ② **MMD 全体背对敌人**：进 UE 面朝 +Y、英雄 -Y → Blender 导出烘焙 yaw 180，UE 用 `ue_import_mmd.py --reimport` 原地重导。
> 现在 `n2_anim_pose_probe.py --clip all` 396/396 通过（臂/腿/朝向判据），`n2_retarget_review_pie.py` 出 PIE 同帧并排图。
> §2 的验收数字（差分 6.70%、`N2_Retarget_*.png`）已被 151 的新结果取代；§8 重跑步骤以 151 §6 为准。
> **2026-10-14 更新：§5 第三步（M4：100 个 VRM）已完成，见 `document/152_UE5_M4-A_100个VRM批量导入_重定向_显存修复_2026-10-14.md`；本文件以下内容为 N2 历史记录。**
>
> ~~下一步直接从 §5 第三步（M4：100 个 VRM）开始~~，接新骨架前先查根骨缩放、A/T-pose、朝向、哪组骨带蒙皮。

---

## 1. 当前目标

**表层（收尾）**：N2 的**资产已经做完并验证**，但**文档没跟上**。doc 145、doc 148、
`document/100_DOCUMENT_INDEX.md` §5、`document/11_ASSET_MIGRATION.md` §M4 待办这四处仍把
"33 段 GP 动作重定向到 MMD 骨骼"列为未完成，与实际相反。先把这种不一致消掉。

**实质（继续往下做）**：整个"112 角色"计划 = **100 个 VRM + 12 个 MMD**（见
`document/03_ROSTER_100.md`、`document/143_*.md`）。

| 部分 | 状态 |
|---|---|
| 12 个 MMD（char_101–112） | **本轮的成果，已完成**：模型、材质、33 段动作重定向、PIE 验收 |
| 100 个 VRM（其余名册） | **M4，完全没开始**。UE 里目前只有 1 个 VRM 真的在用（Clukay416），另有 1 个对照样本（阿芙） |

所以下一个 agent 的工作重心是 **M4：把 100 个 VRM 批量接进来**，本轮为它留下了一套可直接复用的
"导出 → 导入 → 材质 → 重定向 → 验证"流程和三条已踩过的坑（见 §4）。

---

## 2. 已经完成了什么

N2 拆成两半，两半都完成了：

### (a) 棋盘按角色显示各自的模型
`ATreadM3BoardPresenter` 按 `CharacterId` 解析网格与动作：`char_101..112` 用各自的 MMD 模型和
各自的 MMD 动作；其余角色（含 `char_100`，它是第 100 个 VRM，命名却和 MMD 连号）回退到 M1 英雄 Clukay416。
**C++ 本轮没有改动** —— 缺陷全在资产侧（见 §7）。

### (b) 33 段 GP 动作重定向到 12 套 MMD 骨骼
396 段（33 × 12）全部生成，并且**待机姿势与英雄对齐**。

### 验收证据（全部已存盘）

| 证据 | 文件 | 结果 |
|---|---|---|
| PIE 验收图 2560×1440 | `Saved/Screenshots/N2_Accept_Board.png` | 棋盘 24 个单位全部画出（12 MMD + 12 英雄） |
| 同帧对照（藏 MMD） | `Saved/Screenshots/N2_Accept_Board_NoMMD.png` | 12 个选择环空着 |
| 差分掩码 | `Saved/Screenshots/N2_Accept_DiffMask.png` | 12 个人形轮廓 |
| 左右并排裁剪 | `Saved/Screenshots/N2_Accept_Zoom_AB.png` | 可直接目检 |
| 单角色特写 | `Saved/Screenshots/N2_Accept_Single.png` | 贴图/材质/待机正常 |
| 差分计数 | `Saved/Reports/N2_Accept_Diff.json` | 247,161 像素 = 6.70% |
| 棋盘普查 | `Saved/Reports/N2_RenderTruth.json` → `acceptShot` | bodies 24 / mmd 12 / hero 12 / visible 24 |
| 姿势探针 | `Saved/Reports/N2_AnimPoseProbe.json` | 12 个角色根骨缩放 = 1；手臂角 20–26°（英雄 17–20°） |
| 重定向报告 | `Saved/Reports/N2_Retarget_Build.json` | ok=true；12 角色 × 33 段；每个 rig 7 条链 |
| 导入报告 | `Saved/Reports/N2_MMD_Import.json` | ok=true；12 个模型，身高 155–212 cm |
| 材质报告 | `Saved/Reports/N2_MMD_Materials.json` | 12 个模型全 ok；共 288 个材质槽 |
| FBX 导出报告 | `Saved/Reports/N2_MmdFbxExport.json` | ok=true；`units: cm` |
| 导出方式对照实验 | `Saved/Reports/N2_FbxScaleProbeUE.json` | 见 §7.2 的三种方式对比 |

### 资产落点

| 位置 | 内容 |
|---|---|
| `Saved/Staging/mmd_fbx/char_1xx/` | 12 个厘米制 FBX + 逐槽材质 JSON + 贴图副本 |
| `/Game/Tread/Characters/MMD/char_1xx/SK_MMD_char_1xx` | 12 个骨骼网格 |
| `.../Materials/MI_Toon_<序号>_<槽名>` | 288 个逐槽卡通材质实例（含镂空、双面） |
| `.../Retarget/IK_MMD_char_1xx` | 12 个 IK Rig（各 7 条链，链名可读回） |
| `.../Retarget/RTG_char_1xx` | 12 个 IK Retargeter（**已对齐 target retarget pose**） |
| `.../Anim/A_GP_*` | 396 段重定向动画 |
| `/Game/Tread/Characters/Clukay416/Retarget/IK_Clukay416` | 源 IK Rig（root `5_joint_HipMaster`） |

---

## 3. 权威来源

**总规则**：工程实际状态优先于文档；冲突必须写进过程记录（`document/100_DOCUMENT_INDEX.md` §1）。

| 想知道什么 | 以谁为准 |
|---|---|
| N2 做到哪了、怎么复现 | **本文档**。doc 145/148 过期，doc 144 的导入部分仍然有效 |
| 项目定位、口径、里程碑 | `document/00_PROJECT_MASTER.md` + `document/100_DOCUMENT_INDEX.md` |
| 数据真源（盟约/特质/经济/112 名册） | `document/卫戍合约联机版资料整理.xlsx`、`document/卫戍协议#1快查表.xlsx` |
| MMD 模型来源与授权 | `document/143_*.md`、`Content/Data/Source/Roster112_Models.json`、`Saved/Staging/mmd_lic/` |
| 资产迁移台账、（过期的）M4 待办 | `document/11_ASSET_MIGRATION.md` |
| 管线、脚本、渲染约定 | `document/10_UE5_TECH_PIPELINE.md` |
| 运行结果 | **一律以 `Saved/Reports/*.json` 为准**，不看文档里的转述 |
| 视觉证据 | `Saved/Screenshots/`，判"游戏里画出了什么"只认 `HighResShot` 那条路（§4） |
| 只读边界 | 旧 Unity 工程 `F:\AI\workbuddy\GiantessAutoChess` 及其 `docs/`、`vrm/`、`lihui/`、JSON —— **只读** |

**脚本是资产的唯一生成途径**：每个 UE 资产都必须能由 `Tools/` 下可重复运行的脚本重建，
`.uasset`/`.umap` 禁止手改（只能由脚本、MCP 或编辑器操作产生）。

---

## 4. 不能重新争论的决策

这些都已经有实测结论或明确规则，**不要再回头试**：

1. **判"游戏里到底画出了什么"只用 `HighResShot` + 差分。**
   `Tools/ue_shot.py` 走的 `CaptureViewport`（关卡视口捕获）**根本不渲染 PIE 里运行时创建的组件** ——
   同一机位它画 1 个单位、`HighResShot` 画 24 个；在 PIE 里隐藏 presenter 它一个像素都不变。
   这条坑害了整整一轮排查。（记忆：`tread-viewport-capture-lies`）
2. **MMD 模型按厘米制导出。** 别再用 `FBX_SCALE_ALL` —— 实测 UE 仍把根骨缩成 100；
   只有"几何直接做成厘米 + 导出器完全不缩放"才得到根骨缩放 1。（记忆：`tread-mmd-root-scale`）
3. **跨骨架重定向必须对齐 target retarget pose**，并且要按**关节角度**验收，
   不能只看骨骼缩放和包围范围 —— 手臂反向约 100° 时那两项全都正常。
   （记忆：`tread-retarget-pose-align`）
4. **IK Rig / IK Retargeter 一律"取回 + 原地重配"，不要删除重建。**
   删掉被 retargeter 引用的 IK Rig 会让编辑器 `EXCEPTION_ACCESS_VIOLATION` 崩掉，且不留崩溃转储。
   （记忆：`tread-editor-ikrig-crash`）
5. **动画不许手 K。** 所有关键帧来自 GP PSA 数据；跨骨架只能重定向，不能重做。
6. **presenter 的 C++ 不用改。** 三个缺陷全在资产侧，presenter 的组件创建顺序（`SetSkeletalMeshAsset`
   在 `RegisterComponent` 之前）**不是**问题 —— 这条曾被误判过，别再回去试。
7. **不要主动关主人在用的编辑器。** 它崩了可以重新拉起（本轮拉过两次），但不要 taskkill。
8. **地图切换（`load_map`）必须单独一次调用**，同一帧持有世界引用再切图会让编辑器 fatal 崩溃。
9. **`slomo` 是控制台变量，跨 PIE 会话存活。** 拍照用的 `slomo 0` 必须在收尾时复位，
   否则下一次 PIE 里 presenter 永远不 tick、组件数恒为 0。
10. **回复与文档用中文，代码注释用英文。**

---

## 5. 下一步应该从哪里开始

### 第一步（小、立刻可做）：把文档对齐到实际

只改状态描述，不要重写内容：

- `document/145_UE5_N2_按角色显示模型与动作重定向_2026-10-09.md`
  状态行改成"已完成并在 PIE 验收"；§2 里的接口名 `LoadCharacterMesh` / `CharacterMeshCache` **已经不存在**，
  实际是 `ResolveCharacterVisuals()` / `TMap<FString, FTreadM3CharacterVisuals> CharacterVisualCache`。
- `document/148_*.md`：把两份状态对齐，或直接在这份文档顶部加一行指向 `HANDOFF_N2.md`。
- `document/100_DOCUMENT_INDEX.md` §5 的 N2 那一条。
- `document/11_ASSET_MIGRATION.md` §M4 待办：把"33 段 GP 动作重定向到 MMD 骨骼"从待办里划掉（已完成），
  并把 MMD 那行的材质/骨架描述补上 `IK_MMD_*` / `RTG_*` / 396 段 `Anim`。

新建过程记录前 **Glob `document/14*.md`** 占号（其他会话也会占号，下一个空号可能是 151）。

### 第二步：把验证补齐（本轮只验证了 Idle）

1. `Tools/m4/n2_anim_pose_probe.py` 目前只探 `A_GP_Idle`、且只按角色过滤（`--only char_1xx`）。
   **给它加一个 `--clip` 参数**，然后扫 33 × 12 段的 `armDeg` + 包围范围，把"396 段都健康"变成机器结论。
2. `Tools/m4/n2_retarget_review.py` 是项目原本设计的"源/目标同帧并排对比"验收工具
   （`prepare → stage → StartPIE → frame → shoot → StopPIE → cleanup`）。
   **修复后没重跑过**，`Saved/Screenshots/N2_Retarget_*.png` 是修复前的，不要当证据。

### 第三步：M4 —— 100 个 VRM 批量导入

源在哪（**只读**）：旧 Unity 工程 `F:\AI\workbuddy\GiantessAutoChess\`
—— `vrm/`（顶层 15 项，含 `AetherGazer`/`Arknights`/`GilesFrontline` 等子目录）、
`tmp/dedup_backup/`（去重后的那批）、`output/model_fix/`。全工程共 **267 个 `.vrm`**。

缺的东西：**UE 侧还没有"名册角色 → VRM 文件"的映射表**
（`Content/Data/Source/Roster112_Models.json` 现在只有 12 条 MMD 记录）。这大概要参照旧工程的数据或
`document/03_ROSTER_100.md` 先建一张表，再照 MMD 那条路做：
`复制到 Saved/Staging → 导入 → 材质 → 重定向 → 探针验证 → PIE 差分`。

**先做一件事再动手**：随便挑一个 VRM 导入后，在 UE 里量它的**根骨缩放**和**绑定姿势是 A-pose 还是 T-pose**。
VRM（尤其 VRM 1.0）多半是 A-pose 或 T-pose，跟 MMD 的 A-pose 未必一致 —— 这决定要不要复用本轮的
`auto_align_all_bones` 那一步。

开始前建议先读 doc 143 §4（有三项等主人决定）和 `document/11_ASSET_MIGRATION.md` 的授权表
（爱给网条目需逐条复核，CC-BY 需保留署名）。

---

## 6. 该调用哪些 skills

**先说结论：本项目的工作主要靠 `Tools/` 下的脚本 + `Tools/ue_run.py`（Python 远程执行），
大多数时候不需要 skill。** 项目里没有 `.claude/` 目录，没有自定义 skill 或 subagent。

| 什么时候 | 用哪个 |
|---|---|
| 需要**直接操作 UE 编辑器**（摆 Actor、读属性、改资产、Live Coding 重编 C++）而不是跑脚本时 | `anthropic-skills:unreal-mcp` |
| 改了 C++ 之后自查 | `code-review` |
| 要动数据真源那两个 `.xlsx`（盟约/特质/经济/名册） | `anthropic-skills:xlsx` |
| 记忆文件多了、需要合并去重 | `anthropic-skills:consolidate-memory` |
| 想把某个模型程序化生成/参数化（例如"授权不合格的条目替换为程序化模型"，doc 11 明确提到这条路） | `procedura` |

其余（`pdf`/`docx`/`pptx`/`dataviz`/`frontend-design` 等）与本项目无关。

**日常真正会用到的接口**（不是 skill）：

```bash
python Tools/ue_run.py <script.py> [args]     # 在跑着的编辑器里执行 Python（最常用）
python Tools/ue_run.py -c "<python>"          # 一行式查询
python Tools/ue_mcp.py toolsets               # 看 MCP 有哪些工具集
python Tools/ue_mcp.py call <toolset> <tool> '<json>'
```

---

## 7. 附录 A：本轮修了什么

进来时棋盘上 12 个 MMD 单位**一个都看不见**（只有选择环）。查下来是**三个独立缺陷**叠在一起，
外加**两个流程坑**。

### 7.1 测量工具在骗人（不是代码缺陷）

见 §4 第 1 条。附带结论：`was_recently_rendered()` 会给出与画面矛盾的读数（它说 24/24 在渲染而画面里只有 3 个），
不要单独信它；差分前先 `slomo 0` 冻结对局，否则烟尘粒子和回合推进污染差分。

### 7.2 FBX 根骨缩放 100 → 重定向动画把整个人缩成 1~2 cm

根因：旧导出（mmd_tools 缩放 0.08 + 导出器默认 `FBX_SCALE_NONE`）把米→厘米的 100 倍写进了每个物体变换，
骨架对象 `<模型名>_arm` 被 UE 当成**缩放 100 的根骨**；重定向导出的 `A_GP_*` 把该根骨缩放写成 1，
全身随之缩到百分之一 —— 组件"已渲染"标志为真但没有像素。

实测三种导出方式：

| 方式 | UE 里的根骨缩放 |
|---|---|
| `FBX_SCALE_NONE` + 导入缩放 0.08（原来） | 100 |
| `FBX_SCALE_ALL` + 导入缩放 0.08 | **仍是 100**（UE 把文件头单位缩放折回根节点） |
| 导入缩放 8.0 + 场景 `scale_length=0.01`，导出不做缩放 | **1.0** ✅ |

修法已落地在 `Tools/m4/blender_mmd_to_fbx.py`（默认 `--scale 8.0 --unit-scale 0.01 --scale-mode none`）。

### 7.3 重定向姿势没对齐 → 手臂反向转约 100 度

根骨缩放修好后人能看见了，但**两只手臂举到肩上方**：手首在肩**上方** 26 cm，英雄待机是肩**下方** 43 cm。
脊椎、腿、所有骨骼缩放都正常，左右对称。

根因：MMD 模型绑定是 **A-pose**，VRM 英雄是 **T-pose**，而 IK Retargeter 的 target retarget pose
默认取各自骨架的参考姿势。
修法已落地在 `Tools/m4/n2_build_retarget.py` 的 `make_retargeter`：

```python
controller.auto_align_all_bones(unreal.RetargetSourceOrTarget.TARGET,
                                unreal.RetargetAutoAlignMethod.CHAIN_TO_CHAIN)
```

修后 12 个角色手臂角 20–26°，英雄 17–20°。

### 7.4 流程坑：`--rebuild` 静默半途而废

`EditorAssetLibrary.delete_directory()` / `delete_asset()` 对**编辑器进程已加载**的资产会静默失败
（返回 True 但文件还在）。于是 `ue_import_mmd.py --rebuild` 留下了 12 个 `Retarget/` 目录没删掉，
接着 `create_asset` 同名返回 `None`，重定向脚本报 "could not create IK Rig"。
现在 `ue_import_mmd.py` 在 mesh 没删掉时**直接报错**。

### 7.5 流程坑：删 IK Rig 会崩编辑器

见 §4 第 4 条。崩溃堆栈在 `Saved/Logs/Tread.log` 末尾：

```
Critical error: EXCEPTION_ACCESS_VIOLATION reading address 0x0000000000000000
[Callstack] UnrealEditor-IKRig.dll ... UnrealEditor-IKRigEditor.dll ... PythonScriptPlugin.dll
```

### 7.6 编辑器的第二次死亡（原因未知）

2026-10-11 23:49，在"切图到 `M3_Paris_Match` 成功约 5 分钟后"的一次 `list_assets` 调用中连接被重置、
进程消失。`Tread.log` 末尾**没有**崩溃堆栈，也没有 `Saved/Crashes` 转储，机器**没有**重启
（开机时间 23:12）。不确定是调用导致的还是环境问题 —— 遇到类似情况先看 `Tread.log` 末尾。

---

## 8. 附录 B：从头重跑

环境：引擎在 `G:\epicgame\UE_5.8`（**不在 C 盘**）；Blender 在
`C:/Program Files/Blender Foundation/Blender 5.2/blender.exe`；控制台是 GBK，脚本输出只用 ASCII。

```bash
# 1) Blender：PMX -> 厘米制 FBX（12 个模型，约 10 分钟）
python Tools/m4/n2_export_mmd_fbx.py --force

# 2) 主机侧：标注哪些槽需要镂空（改的是上一步刚写的 sidecar JSON，必须在导出之后跑）
python Tools/m4/mmd_texture_alpha.py

# 3) UE 导入（--rebuild 会删掉每个角色目录重导，约 19 分钟）
python Tools/ue_run.py Tools/m4/ue_import_mmd.py --rebuild

# 4) UE 材质实例（约 6 分钟）
python Tools/ue_run.py Tools/m4/ue_mmd_materials.py

# 5) UE 重定向：33 段 × 12 套骨架（约 40 分钟，含对齐 target retarget pose）
python Tools/ue_run.py Tools/m4/n2_build_retarget.py

# 6) 验证：根骨缩放应为 1，armDeg 应落在 20 上下（秒级）
python Tools/ue_run.py Tools/m4/n2_anim_pose_probe.py

# 7) PIE 验收：切图 -> StartPIE -> 铺盘 -> 冻结拍图（含藏 MMD 的对照）-> StopPIE -> 还原地图
python Tools/m4/n2_accept_pie.py
```

**每一步的前置条件**：

- 第 3、7 步都要求**没有脏包**（脏包会挡住地图切换）。长任务跑完记得把新建的包存盘。
- presenter 的组件是在 `Tick()` 里建的，而 Python 远程执行跑在游戏线程上，
  所以"铺盘"和"数组件"**必须分成两次调用**。
- `IK Retargeter` 的链映射在 UE 5.8 的 Python 里**读不出来**
  （`get_all_chain_settings()` 返回空数组、`get_retarget_chain_settings()` 对任何名字都返回空结构、
  `auto_map_chains()` 无返回值）。能读的是 **IK Rig** 的链：
  `unreal.IKRigController.get_controller(rig).get_retarget_chains()`。
  `n2_build_retarget.py` 现在把 rig 链记进报告，并把它算进 `ok`。

---

## 9. 附录 C：环境地雷

1. 引擎在 `G:\epicgame\UE_5.8`；`C:\Program Files\Epic Games\UE_5.8` **不存在**，注册表也查不到。
   `Tools/m1`、`Tools/m2` 的 runner 从注册表读引擎路径会失败，必须显式给
   `$env:UE_ENGINE_ROOT="G:\epicgame\UE_5.8"`。
2. 编辑器重启后会回到默认启动图 `M0_Paris_Board`，需要手动切回 `M3_Paris_Match`。
3. **本工程不是 git 仓库**，改源码前先手备份。
4. **控制台是 GBK**：非 GBK 字符（`✓` 之类）会 `UnicodeEncodeError` 直接崩，用 `[OK]` / `ERROR:`。
5. Git Bash 会把 `/Game/...` 参数改写成 `C:/Program Files/Git/Game/...`，用 `MSYS_NO_PATHCONV=1`。
6. **Python 远程执行里不能 `time.sleep`**（会卡游戏线程），等待一律放在主机侧轮询。
7. `unreal.Rotator` 的位置参数顺序是 `(roll, pitch, yaw)`，**永远按名字传**。
8. 长任务日志会缓冲，实时进度看 `Saved/Logs/ue_run_last.log`，不要等 stdout；`ue_run.py` 的退出码不可靠，
   看输出里的 `status=OK` / `status=FAIL`。
9. `Content/Tread/Characters/MMD/` 下现在有 **1126 个 `.uasset`**；对该目录做递归 `list_assets` 偏重，
   上一次连接被重置就发生在它之后（§7.6）。

---

## 10. 附录 D：文件清单

### 本轮新增（都在 `Tools/m4/`）

| 脚本 | 作用 |
|---|---|
| `n2_export_mmd_fbx.py` | 纯主机侧：对 `staged.json` 的 12 个模型逐个调 Blender 导出（本轮补的批量入口） |
| `n2_fbx_scale_probe.py` + `ue_n2_scale_probe.py` | 三种导出方式对照实验（§7.2 的表就是它们出的）；前者写 `N2_FbxScaleProbe.json`，后者写 `N2_FbxScaleProbeUE.json` |
| `n2_anim_pose_probe.py` | 只读探针：根骨缩放、包围范围、**手臂角 `armDeg`**、NaN |
| `n2_accept_pie.py` | PIE 验收编排：切图 → PIE → 铺盘 → 冻结拍图 ×2 → 停 → 还原 |
| `n2_render_truth.py` | 上面的编辑器侧部分（本轮新增 `census` / `shoot` / `shoot_hidden` / `unfreeze` 阶段） |

### 本轮改动

- `blender_mmd_to_fbx.py`：厘米制导出；sidecar 字段改名 `height_cm` / `bounds_cm` / 新增 `units`
- `ue_import_mmd.py`：`--rebuild` 会检查删除是否真的成功
- `n2_build_retarget.py`：原地重配（不删资产）+ 对齐 retarget pose + 记 rig 链 + 结尾存盘
- `ue_n2_scale_probe.py`：报告路径从 `N2_FbxScaleProbe.json` 改成独立的 `N2_FbxScaleProbeUE.json`
  （原来两个脚本共用一个文件名，UE 侧那次把 Blender 侧的记录覆盖了）

### 旧的相关脚本（本轮没动）

`stage_mmd_models.py`、`ue_mmd_materials.py`、`mmd_texture_alpha.py`、`ue_mmd_lineup.py`、
`n2_retarget_review.py`、`n2_pie_board_check.py`、`n2_render_probe.py`、`inspect_mmd_bones.py`

### 文档

`document/144`（N1/N2 数据与导入，导入部分仍有效）、`document/145`（接口名已过时）、
`document/148`（**已被本文替代**）、`document/143`（112 角色计划）、
`document/11_ASSET_MIGRATION.md`（M4 待办，需订正）、`document/100_DOCUMENT_INDEX.md`
