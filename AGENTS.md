# Tread 项目记忆（DSH 版）

> 2026-10-17 从 Claude Code 迁移：来源 `C:\Users\spylnexus\.claude\projects\E--AI-Tread-Tread\memory\`（19 个文件 / 33,620 字节，SHA256 逐一校验一致）。
> 本文件由 DSH **自动加载**（工作区根 `AGENTS.md`，首次请求注入），只放**硬规则 + 索引**；细节用 read 打开 `memory/<名>.md` 看原文。
> 记忆状态截至 2026-10-17。与之冲突时以新证据和 `document/` 里的记录为准，并回来订正本文件。

---

## 1. 项目与本机事实

- **Tread**：巨物棋类 PvP（4 人 / 12 回合）的 **UE 5.8 重制**，从旧 Unity 工程移植。非商业同人作品。
- 工作区 `E:\AI\Tread\Tread`；引擎 `G:\epicgame\UE_5.8`；**无 git 仓库**；控制台编码是 GBK。
- 资产脚本全在 `Tools/`（编辑器 Python 入口是 `Tools/ue_run.py`）；文档在 `document/`（编号制）；截图、JSON 报告等产物在 `Saved/`。
- 名册 112 = 100 个 VRM 模型 + `mmd_12/` 里 12 个 MMD 模型。

## 2. 硬规则（每次动手前过一遍）

1. **只读源头**：旧 Unity 工程 `F:\AI\workbuddy\GiantessAutoChess`、参考图、模型目录、GP 导出 `0614/gp_extract` 一律不改；要改先复制到 `Saved/Staging/`。
2. **资产只能脚本生成**：所有 UE 资产 / 关卡 / 材质必须来自 `Tools/` 下可重复执行的脚本（或编辑器操作），**绝不手改** `.uasset` / `.umap`。
3. **动画不许手 K**：所有帧来自 GP PSA 数据；Unity 导出的 `A_Clukay_*` 已废弃。
4. **语言**：回复用中文；`document/` 文档用中文；代码注释用英文。
5. **文档编号**：新建记录前先 Glob `document/15*.md` 找空号（别的会话也在用号），再更新 `100_DOCUMENT_INDEX.md`。**当前下一个空号 188**（187 = 准备 5 分钟 + 删语音 + 击杀镜头，186 = 打包版单位模型消失，185 = 战役卡片 + Esc 菜单，184 = 完整 Win64 打包，183 = M0 TSR→TAA 性能，182 = 巨人座（另一会话），181 = 特勤处施工场（另一会话），180 = 剩余 P2 收尾，179 = 特勤处基地模块组（另一会话），178 = 装备 proc 第二波 14 件，175 = 装备 proc + AI 装备，176 = 三选一奖励，177 = 音频验收，174 = 阿戈尔吞噬，172 = 特勤处局外基地与对话驱动助手设计案（初版不接 LLM，待拍板），173 = 盟约机制判据（另一会话），164 = 华沙五地标建模，163 = 局部破坏与坍塌观感，156 = UI 原型，157 = UI 迁移施工说明，158 = 战斗演出观感修正，159 = 脚圈血条 + HUD 坐标修复，160 = 建筑破坏可行性 + 4060 实测，161 = 破坏玩法层，162 = 踩踏破坏 + 碎片物理 + 烟尘接线）。
6. **别动用户的编辑器**：不许自己关闭用户打开的编辑器；要重建（`UnrealEditor-Tread.dll` 被占用）先问，且先查脏包。重启编辑器这件事由用户手动做。
7. **每阶段要证据**：以截图 + `Saved/` 下的 JSON 报告收尾，验收看**关节角度 / 差分图**，不看包络。

## 3. 坑速查（每条都是花过时间换来的）

### 测量 / 截图（最容易骗人的部分）

- `Tools/ue_shot.py` 的 `CaptureViewport` **不画 PIE 里运行时创建的 Actor** —— 用它得出的"画面"结论全部作废。看游戏画面用 `HighResShot`；判"某组件画出来没有"用显示 / 隐藏两张**差分**（差分前先 `slomo 0`）。→ `tread-viewport-capture-lies.md`
- `HighResShot` **不含 UMG / HUD**；看 UI 只能用 `shot showui`，且**必须在不冻结时发** —— 冻结时发的请求会挂起到 PIE 结束，然后在 D3D12 回读转换里越界写崩编辑器。`shot showui` 截的是**整个编辑器窗口**（≈1361×774，游戏视口只占约 0.554 缩放），不是 1920×1080。要冻结 UI 用控件自己的测试钩子（如 `FreezeTransitionForTest`）。→ `tread-shot-showui-crash.md`
- **UE Python 的结构体赋值是别名不是拷贝**：`hidden = transform` 再改 `hidden.scale3d` 会把源变换一起改，曾让碎片替身全缩到 1%、「测出」一个假的帧率；改副本先 `.copy()`，改完必须同时验数字和画面。→ `tread-unreal-python-struct-aliasing.md`
- **只量骨骼不量蒙皮必然漏**：根骨缩放、retarget pose、D 骨三次都是"骨骼数据正常、画面不对"。验收要有 PIE 同帧源 / 目标并排图。

### 重定向 / 骨架

- 重定向器建完立刻 `auto_align_all_bones(TARGET, CHAIN_TO_CHAIN)` 对齐 target retarget pose，否则手臂反向约 100° 而所有缩放仍是 1。→ `tread-retarget-pose-align.md`
- MMD 腿蒙皮**只挂在 `足D / ひざD / 足首D`**（`足 / ひざ / 足首` 权重为 0），GP 源动作也只驱动 D 骨；**腿链两侧都要接 D 骨**。→ `tread-mmd-dbone-skin.md`
- 单条髋→踝 FK 链会丢膝弯（目标膝盖位置不同就短 35°）；腿拆 Thigh / Shin / Foot 三条链，源用 `IK_Clukay416_LegSplit`（`IK_Clukay416` 别动，12 个 MMD 重定向器在用）。swing 量大腿（髋→膝），不要量髋→踝。→ `tread-retarget-leg-split.md`
- Blender 导出必须把朝向 / 缩放**烘进几何**：MMD 面朝 +Y、英雄 -Y（导出加 `--yaw 180`）；缩放 100 的根骨会被重定向写成 1，整人缩到 1~2 cm。UE 侧重导用 `--reimport` 原地重导。→ `tread-mmd-facing.md`、`tread-mmd-root-scale.md`
- **不要"删了再建"** IK Rig / IK Retargeter：被引用的 IK Rig 一删，下次操作直接崩编辑器；一律"取回 + 原地重配"。编辑器已加载的资产 `delete_asset` 会**静默失败**（返回 True、文件还在）。→ `tread-editor-ikrig-crash.md`

### 编辑器稳定性

- **8 GB 显卡长批次会 GPU 崩溃**（`CreateReservedResource` 失败）：根因是各类缩略图场景每个约 90 MB 不清；已加控制台命令 `Tread.FlushThumbnailScenes`，批次脚本每角色调一次。对策：小批次（`--limit 4-5`）、可续跑、`nvidia-smi` 超 ~6300 MiB 就停、请用户重启编辑器。单个大 FBX 卡 20+ 分钟**不算死**。→ `tread-editor-vram-batch.md`
- 切地图（`load_level`）必须**单独一次脚本调用**，那次调用里不要先拿世界引用，否则 GC 清不掉旧包 → `World Memory Leaks` fatal。→ `tread-editor-python-map-switch.md`
- `EditorLoadingAndSavingUtils.reload_packages` 对脏地图会让编辑器断开 / 崩溃；审查截图用临时地图（`Tools/m4/ue_mmd_lineup.py` → `Review_Lineup`），不要往游戏地图里生成。

### 构建 / 运行

- Git Bash 会把 `/Game/...` 改写成 `C:/Program Files/Git/Game/...`（曾弹出对话框）：设 `MSYS_NO_PATHCONV=1`，或直接用 pwsh runner（`Tools/m1/run_match_selftest.ps1`、`Tools/m2/run_m2_selftest.ps1`）。
- `UnrealEditor-Cmd -game` 的**退出码不可信**：判 `Saved/` 里 JSON 报告的 `ok` / `namedChecks`。
- C4458（参数名遮蔽 AActor 成员，如 `Owner`）在本模块是**硬错误**。
- 字距：UE 5.8 的 `MakeText` **不画** `LetterSpacing`，`FontMeasure` 也不计入；必须 `MakeShapedText` + 用**同一整形序列**在绘制缩放（`Geo.GetAccumulatedLayoutTransform().GetScale()`）下测宽。→ `tread-slate-maketext-letterspacing.md`
- `ue_ui_style_check_pie.py` 在编辑器最小化时拒绝运行，先 `ShowWindow(SW_RESTORE)` 恢复窗口。

### 内容 / 美术

- 棋盘可读性优先：8×8 格子的**院子保持空**，楼放进环里（替换周边模块），每格是干净的"环"街区，落在 ±81 m 街道线上；**烟囱必须长在多层厂房上**，不许独立站在地面。→ `tread-board-readability.md`
- 颜色贴图导入强制 `TC_DEFAULT + sRGB + TEXTUREGROUP_WORLD`，否则偏蓝紫的基础色会被引擎判成法线贴图（BC5、B=0 → 变黄绿）。文件名 `_D` 后缀**不影响**自动判断。`Tools/m4/fix_color_textures.py --check` 可扫描。→ `tread-texture-normalmap-misdetect.md`
- 数值 / 契约以 Stronghold-Protocol 网页版为源（只取数据，**不抄它 GPL-3.0 的代码**）；来源数据是鹰角/hypergryph 版权、GF2 MMD 模型限"MMD-only"、异环模型禁血腥暴力 —— 待用户最终确认。→ `tread-stronghold-plan.md`

## 4. 当前进度（截至 2026-10-17）

- **M4 完成**：100 个 VRM 批量导入 / 重定向 / 显存修复（152）、名册道具战役与验收（153）、角色头像与立绘（154）、战斗演出（155），均已 PIE 验收。
- **UI 风格迁移已完工**：乌萨斯建构主义 + 莱茵动效，原型（156）→ 施工说明（157）；4 轮修复后 19 张 UI 截图、M4、战斗 PIE、原生 M1/M2 **全过**（157 §7）。规则：**玩家蓝（血条 / 脚圈）、敌人红**；前台必须排除在自测 / 截图流程外。
- **战斗演出观感已收口**（158，2026-10-17）：主人两条反馈（敌人原地不动 / 烟尘挡屏）均已消除；`rangedRangeCells` 1.8、删 467 个占位烟尘、验收夹具给 P1/P2/P3 都配混编棋盘（修配对漂移）、判据 10→15 项；15/15 通过（敌方位移 1.96–3.94 格、17.4 秒进 Settlement、57.6 fps）。
- **脚圈血条 + HUD 坐标修复**（159，2026-10-17）：头顶血条挤到左上角的根因是「视口像素当设计像素用」，已用 `ScreenToDesign()` 修掉；脚下圆圈改成血条（`M_Tread_UnitRing` 遮罩弧 + 暗底环，6 点钟方向对称张缺口，归零同帧倒地）；**阶层/★ 只在准备阶段显示、战斗时隐藏**。验收：PIE 15/15、逐档环状态看过、HUD 两张截图（准备期有铭牌 / 战斗期无铭牌、飘字贴单位）、帧率实测 57.5 fps。HUD 取证改用 `Tools/ue_hud_shot.py`（系统层截窗，不再用 `shot showui`）。
- **建筑破坏（160/161/162，2026-10-18）**：阶段 A/B + 玩法层 + **踩踏破坏**已实装——17 套碎片集 / 114 个带碰撞的碎片网格；`ATreadBuildingDestructionManager` 管生命值（三档表现）、承重级联（90 m 支撑图、按缺口吃伤害）、**踩踏覆盖率过半整体坍塌**、碎片刚体（每栋 ≤3 块、同屏 ≤24 体、1.8 s 后冻结成 HISM）与 Niagara 烟尘接线。实测：整片 254 栋全毁 65.4→61.2 fps、4 发命中经级联倒 30-44 栋、六步踩踏倒 32 栋（16 栋因过半）、刚体 24 全落地。**烟尘已接官方示例包**（`/Game/NiagaraExamples/NS_Dirt_Explosion`，配置驱动）+ 按镜头分工（`bDustOnAudienceOnly`：棋盘机位不生成、只有观众/击杀镜头生成）+ 观众镜头抬高到 34 m（比建筑稍高，pitch -2°）+ **击杀镜头近景化**（只跟我方**第一个拿到人头**的角色，击杀时把镜头挪到受害者旁 380 m/90 m 高、FOV 30°，2.6 s 后回位）；PIE 已验（`cameraSwitches 1`、`camera.m` 在受害者旁、`fov 30`、镜头用完回位），**踩踏已接进战斗**（每次命中在攻击者脚下 `ApplyTrample`，半径 45 m×成长、技能更重；PIE 一场打出 5 次坍塌）。**163 按主人反馈改成局部破坏**：脚半径 12 m×成长（3 星 30 m）、倒地时尸体砸塌脚下楼；坍塌改为「结构坐塌」（碎片保留原位、上半下折 45%、尺寸 0.62、冲量 260→90）、碎片集 3×3×2（210 块）、library 废墟不再压成黑石板。⚠️ 162 §4.6 那段是 Live Coding 打的，163 的改动已做过**正式编译**。
- **P0 收口（165，2026-10-18）**：① 三个 AI 会下了——`RunAIPreparation()` 每回合升级/买牌（优先凑三合一）/资金不足时刷新/按前排阶梯部署，自测下自动关闭，实测 `board 3→5, funds 1`，M1/M2 自测全过；② 装备从 0 条接线到 **10 条 onEquip**（资金类/盟约层/招募/升精锐/人口），applied 16 / partial 16 / deferred 24，余下 24 件要战斗 proc 钩子；③ **M5 打包跑通**：`Tools/m5/package_win64.ps1` → `Saved/StagedBuilds/Windows/Tread.exe`（1.36 GB，617 MB pak），冒烟启动通过；`-archive` 因本机无 ZenServer 失败（脚本改成只 stage）。Shipping 编译修了 `GetActorLabel` 编辑器专用 API。
- **P1 盟约核查（166，2026-10-18）**：`04` 里「叙拉古/卡西米尔/奥术/独行/绝技缺源用默认」是**过时记录**——`Pacts.json` 早由 `import_stronghold_data.py` 从 `bonds.json` 生成，23 盟约阈值与卫戍协议逐条一致，`countsBench`（远见/奇迹/投资人）、`countsEliteAll`（绝技）、`isHarmony`（调和）运行时都实现；**唯一真缺**是独行「第二个成员失效」（`maxCount = 1`），已补（数据字段 + `RecomputePacts` 上限 + 自测断言）。仍缺的盟约机制：拉特兰弹药、不屈复活、奇迹免费刷新、迅捷/远见/绝技的 SP、卡西米尔部署事件、炎/阿戈尔召唤。
- **技力系统（167，2026-10-18）**：战斗模拟新增技力——`SpMax 100`、每次攻击 +`100/SkillEvery`（默认 +34，**第一次放技能的时点与旧版一致**，M1/M2 自测数值不用改）、满则放技能并扣 100；迅捷按 0.2 概率额外 +12、绝技 2 档消耗 ×0.7、独行开局 +15，数值全部来自 `bonds.json` 的 `bb`，经 `import_stronghold_data.py` 的 `sp_block()` 写进 `Pacts.json`；新增自测判据 `spNumbersFromData`（PASS）。仍未做：随时间回技力、拉特兰弹药、远见联动、精锐额外回技力、HUD 技力条。
- **弹药与技力面板（168，2026-10-18）**：① 拉特兰弹匣（技能装填、每发叠 4% 攻击、上限 2×）；② 迅捷对精锐单位给 15 点技力（普通 12）；③ 每战斗秒回 2 技力（`rules.spRegenPerSecond`）；④ 远见每次刷新商店 +1 层（10 层结算 2 资金）；⑤ **HUD 小队面板**（`UTreadM1MatchWidget::DrawSquadPanel`）——头像 + 蓝色血条 + 绿色技力条 + 弹药数，画在结算遮罩之上；坑：四个战斗状态没重置会让 M1 的 `replay` 判据发散，已修。M1 267 项 / M2 39 项自测 PASS；证据 `Saved/Screenshots/HUD_Squad_168.png`。169 补了面板的 `技力 n` 数字读数，并把 `ResetBattleMeters()` 从 BattleEnd 的清理里拆出来（否则结算界面永远读到 0）；仍缺：技力满槽动效、拉特兰叠攻显示、远见整备区层数。
- **HUD 细节（170，2026-10-18）**：小队面板改用**角色名**（`GetCardDisplayName`）；盟约层数面板新增「拉特兰 叠攻 ×N · 远见 整备 N 人」（新 getter `GetUnitAmmoMultiplier` / `GetForesightBenchCount`）；**对阵/击杀播报/盟约/小队**四面板加不可见按钮做折叠（收起只剩标题 + `＋`），证据钩子 `SetPanelCollapsedForTest`；小队面板改到只在战斗/结算显示（准备期与商店撞位）。证据 `Saved/Screenshots/HUD_Battle_170.png`。
- **盟约机制（171，2026-10-18）**：`FTreadM2PactDef::Params` 承载 `bonds.json` 的整套 `bb` 数字后，五个机制落地——远见（刷新 +1 层、80 层远见卡 -1、150 层全部 -1）、不屈（击倒按 base_prob+0.004×层数 复活、3 人档全队 +5 技力）、奇迹（刷新后按 baseprob+0.003×层数 送一次免费刷新）、炎（≥6 人召唤最高星炎角色副本，≥9 人两只且 ×1.5 攻/×0.1 受伤，**准备阶段 `StripSummons` 自动下场**）、阿戈尔（≥5 人前 3 名各复活一次）。M1 267 / M2 39 自测 PASS。未做：阿戈尔吞噬、召唤物专属视觉、这五个机制的专门判据。
- **盟约机制判据（173，2026-10-18）**：M2 自测新增六条判据（`namedChecks` 39 → **45**）——参数来源、阿戈尔一次性复活、炎 6/9 召唤并清理、远见层数与 150 层折扣、不屈概率复活、奇迹免费刷新；为可测把奇迹掷骰抽成 `TryMiracleFreeRefresh()`。M1 267 / M2 45 全 PASS。坑：C4456（局部名遮蔽）在本模块是硬错误，新判据里的 `Agir` 已改名 `AgirParams`。
- **阿戈尔吞噬（174，2026-10-18）**：按主人口径「左=后排、右=前排」，阿戈尔 3 人档在战斗开始时咬**右边一格**的队友——**不是吃掉**（主人口径：吞是触发盟约队友原地复活的开关），队友掉三分之一血；咬到 0 时走一次盟约原地复活（40 血），**复活预算用尽则真的倒下**（0 血入场、不参战），阿戈尔吸收其攻击（0.2×费用）与咬掉血量的一半、并按其等阶叠盟约层；行动顺序按「更靠左、更靠上」先动。新增判据 `agirDevoursFrontCell` + `agirDevourFallsWhenReviveBudgetSpent`（M2 `namedChecks` 45 → **47**），M1 267 / M2 47 全 PASS。坑：夹具格子撞车、判据要取「所有阿戈尔里最大攻击」而不是数组里第一个、C2374 重定义 `bLayers`。未做：阻挡数字段、吞噬演出。
- **装备 proc 与 AI 装备（175，2026-10-18）**：`ItemCatalog.json` 新增 `proc` 数组（`Tools/m4/wire_item_procs.py` 显式表生成，27 件 / 31 条 / 20 种 op）；`TreadM2ItemProc.cpp` 新增 `FTreadM2ItemProc` / `FTreadM2UnitProcs` / `FTreadM2BattleSide`，`ResolveBattle` 改成按「战斗侧」跑交换（眩晕/吸血/复活/不死/嘲讽/灼烧/反伤/额外一击/沉默/叠层/弹药退还）；装备三档从 16 applied / 16 partial / 24 deferred 变成 **42 / 5 / 9**；`RunAIPreparation` 第 5 步把库存穿到最强上场单位；**第一回合 AI 行动补在 `ConfirmPreMatchBP`**（之前第 1 回合 AI 不买牌，实测已到 board 5/7/7）。M1 267 / M2 56（+6 判据）全 PASS。仍未接 14 件（自伤、再部署、邻接光环、RECRUIT 4 件、隐匿、护盾、法术穿透、技能窗口等）。
- **三选一奖励（176，2026-10-18）**：`Economy.rewardOffer` 接入运行时——准备期开头四人各抽 3 件免费装备（阶级上限 = 调度中心等级 + 1，clamp 6），`ChooseReward` 领取入库存、重复领取 `RewardUnavailable`、回合末作废；**第一回合入口在 `ConfirmPreMatchBP`**（之前第一回合根本没有奖励）；AI 固定领第一张。UI 在标题栏与棋盘之间画「战术补给 // 三选一 · 免费」纸带（`DrawRewardOffer` + 三个透明按钮），证据 `Saved/Screenshots/HUD_Reward_176.png`。判据 `rewardOfferThreeChoices` / `rewardChooseGrantsItem` / `aiClaimsReward`。
- **音频验收（177，2026-10-18）**：新增 `-TreadAudioSelfTest`（`RunAudioSelfTest` + `UTreadAudioDirector::PlayAssetPath`）与 `Tools/m3/run_audio_selftest.ps1`（**不带** `-nosound`/`-nullrhi`）。实测 **2/2 BGM、14/14 SFX、`char_001` 语音开播、脚步首次 true / 0.4 s 内第二次 false、准备→战斗切 BGM 正常**，`Saved/Reports/Audio_SelfTest.json` ok。仍未做：响度平衡、3D 空间化、逐条语音表。
- **装备 proc 第二波（178，2026-10-18）**：剩下 14 件全部接完——自损（1_05）、再部署（2_01）、邻接光环（3_01）、法抗穿透（3_03）、装备即招募（4_01/5_04，自动取 1 名）、隐匿（4_04）、护盾（4_11）、出售计 8（5_07）、战后升阶（5_08）、获得收益（6_03）、盟约信物（6_09）、技能窗口（6_10）、SP+攻击 ramp（6_11）。`ItemCatalog.json` 现在 **56/56 applied、40 件带 proc、35 种 op**；M2 63 项判据全过（+7），M1 267 全过。近似处：招募未做 3 选 1 UI、6_10 敌方攻速光环、6_11 首次伤害 8×、2_01 用推迟 2 次交换代替计秒。
- **剩余 P2 收尾（180，2026-10-18）**：脚圈改跟骨骼体位置（修胜利/攻击根运动错位）；`char_093 + Idle` 回退英雄动画，并用新钩子 `-TreadChar093View` 实拍 `Char093_180.png`（模型在棋盘上可见、Idle 未消失）；单位放大 ×1.2（`StarScale`）；观众镜头改为 78 m / pitch **−1.5°** / FOV 20（−7° 会只剩腿），PIE 实拍 `M1_Audience_View_180.png` / `Battle_Victory_180.png` 全员全身在框、右侧不再被楼挡；尘雾 ×1.5；碎片集重建为 **4×4×3（17 套 / 458 块）**、按楼层 15%→65% 下沉、`M_Decal_Scorch` 贴花（踩踏/坍塌各留，60 s，上限 64）；30 m 脚复测：踩踏直接坍塌 0、承重级联 16、贴花 34、全毁 39.7 fps；char_080 复核当前头像：脸部无遮挡、武器只在右缘，按当前资产判为已解决；**1% low 干净复测**：平均 **58.84**、1% low **39.08**（10-04 是 69.89 / 56.89），仍未达 60，登记为已知限制。M1 267 / M2 63 全 PASS。
- **M0 渲染性能：TSR → TAA（183，2026-10-18）**：`ATreadM0PerfActor` 补 p50/p95/p99、慢帧表（game/render/gpu/draw/prim）、平均 draw call 与三角形数；对照 9 组后确认 **TSR resolve 是唯一大头**（约 2.1 ms GPU / 12–13 fps），VSM 关、Lumen 关、雾关、ScreenPercentage 80 全部无收益或更差，阴影质量 2 只多 2 fps。`Config/DefaultEngine.ini` 设 `r.AntiAliasingMethod=2`，其余画质不动。实测 **58.84 → 81.99 fps、1% low 39.08 → 72.21**（p99 13.85 ms、20 ms 以上帧 0），同机位截图 `Battle_TAA_181.png`（文件名为 181，实际记录是 183）无可见退化；报告 `M0_Paris_Render_Baseline_TAA.json`。变体测量脚本 `Tools/m0/run_perf_variant.ps1`。
- **完整 Win64 打包（184，2026-10-18）**：修两个打包阻塞——① `bUseZenStore=False`（`Config/DefaultGame.ini` 的 `[/Script/UnrealEd.ProjectPackagingSettings]`），否则 stage 走 `UnrealPak -StartZenServerForStage` 在本机必然失败；② `+DirectoriesToAlwaysCook=(Path="/Game/Tread")`，否则前端/HUD 用 `LoadObject` 路径加载的 UI 贴图与字体不会被 cook，登录页黑屏。最终 Shipping + 全量 pak：staged **2.03 GB**、`Tread-Windows.ucas` **1589 MB**、zip **1748 MB**（`Saved/Archives/Tread_Win64_Shipping_2026-10-18.zip`）；冒烟启动到登录页且与编辑器 `-game` 一致，进「自由对局 · 巴黎」菜单正常。截图 `Packaged_Login_184.png` / `Packaged_Board_184.png`。`Tools/m5/package_win64.ps1` 未改，仍需在无 Zen 机器上用同样参数；报告字段 `stage=false` 不可信。
- **战役卡片 + Esc 菜单（185，2026-10-18）**：战役卡是代码画、数据读 `Content/Data/Generated/*.json`，打包不带非资产文件 → 卡片全空；`+DirectoriesToAlwaysStageAsNonUFS=(Path="Data")` 与 `(Path="Tread/Destruction")` 修复（注意别写 `Path="Tread"`，会把整个 Content/Tread 再拷一份、包从 2.05 GB 涨到 9.37 GB）。新增 `TreadEscapeMenu`（Slate 代码构建）：Esc 由输入预处理器在 Slate 之前截获，弹「系统菜单」并暂停，**退出游戏**调 `QuitGame`、**取消**关闭；`ATreadM1PlayerController` 管生命周期与 `RemoveViewportWidgetContent`。打包版实测 16 张国家卡、Esc 菜单、退出按钮 `exited=True`；staged 2.05 GB / zip 1757 MB。截图 `Packaged_Campaign_185.png` / `Packaged_EscMenu_185.png`。
- **打包版单位模型消失（186，2026-10-18）**：`FindTemplates` 用 `GetActorNameOrLabel()` 匹配 `Clukay416`，但 Shipping 里 label 不参与构建，返回 `SkeletalMeshActor_N` → `BodyMesh/FaceMesh/BaseScale` 全空，`char_001` 回退到 null 网格，单位可拖动、有脚圈但不可见（战斗动作其实在播）。改成按**网格资产名**识别（`SK_Clukay416` / `U_Char_1`），并在关卡无模板时用硬路径兜底 + 按包围盒反推 `BaseScale = 11500 / 高度`；顺带加模板/角色/spawn 三处诊断日志。打包版 `-TreadM2Capture=PREPARE/BATTLE -TreadM2Shot` 实拍：准备阶段 10 个单位有模型，战斗阶段有动作。zip 1757 MB 已覆盖。
- **准备 5 分钟 + 删语音 + 击杀镜头（187，2026-10-19）**：`BuildRules` 正常游戏 `PreparationDurationSec = 300`（三个自测仍 30 秒，避免 UITest 自动换阶段超时；战役 `PrepareSecondsDelta` 只加不减）；`char_053` 第一条购买语音/字幕（“企业号，制空权争夺开始。”）从 roster 数据删除（`build_roster_map.py` 的 `VOICE_LINE_BLOCKLIST` + `Tools/m4/strip_voice_lines.py` 同步生成数据），打包后只剩第二条；击杀镜头条件从 `!bAudienceView` 改为 `bAudienceView`，俯视机位不再被切走。Editor/Shipping 编译、M1/M2 自测均通过；zip 已覆盖 1757 MB。
- **交接入口**：根目录 `HANDOFF_M4_Battle.md`（M4/M5 主线）+ `HANDOFF_Battle_Visuals.md` / `HANDOFF_Battle_Visuals_2.md`（战斗演出观感线，已由 158 收口）。

## 5. 记忆索引（原文在 `memory/`，共 23 条）

| 主题 | 一句话 | 文件 |
| --- | --- | --- |
| UE 硬约束 | 只读源头 / 脚本生成资产 / 不手 K / 中文文档 | `memory/tread-ue-constraints.md` |
| 文档编号 | 下一空号 188（先 Glob，187 = 准备 5 分钟 + 删语音 + 击杀镜头）；00–19 只放需求与现状 | `memory/tread-doc-numbering.md` |
| M2 运行坑 | MSYS 路径改写、退出码不可信、DLL 锁、C4458 | `memory/tread-m2-runtime-notes.md` |
| 切图崩溃 | `load_level` 单独一次调用，同帧持世界引用会 fatal | `memory/tread-editor-python-map-switch.md` |
| 棋盘可读性 | 院子留空、环内放楼、烟囱上房 | `memory/tread-board-readability.md` |
| Stronghold 计划 | 数值契约来源；名册 112 = 100 + MMD | `memory/tread-stronghold-plan.md` |
| 截图骗人 | `CaptureViewport` 不画 PIE Actor，改用 HighResShot + 差分 | `memory/tread-viewport-capture-lies.md` |
| MMD 根骨缩放 | FBX 根骨缩放 100 被重定向写成 1，整人 1~2 cm | `memory/tread-mmd-root-scale.md` |
| 重定向姿势对齐 | 不对齐 target retarget pose → 手臂反 100° | `memory/tread-retarget-pose-align.md` |
| IK Rig 崩溃 | 删被引用的 IK Rig 崩编辑器；原地重配 | `memory/tread-editor-ikrig-crash.md` |
| MMD D 骨蒙皮 | 腿蒙皮只在 D 骨，腿链两侧都要接 | `memory/tread-mmd-dbone-skin.md` |
| MMD 朝向 | MMD +Y / 英雄 -Y，导出烘 yaw 180 | `memory/tread-mmd-facing.md` |
| 显存批次 | 8 GB 卡长批次炸 GPU；小批次 + `Tread.FlushThumbnailScenes` | `memory/tread-editor-vram-batch.md` |
| 腿链拆分 | 单链丢膝弯，拆 Thigh/Shin/Foot，源 `LegSplit` | `memory/tread-retarget-leg-split.md` |
| 法线贴图误判 | 蓝紫基础色被判法线 → 黄绿；强制 TC_DEFAULT+sRGB | `memory/tread-texture-normalmap-misdetect.md` |
| showui 崩溃 | 冻结时发 `shot showui` 崩编辑器；UI 截图规则 | `memory/tread-shot-showui-crash.md` |
| UI 风格迁移 | 已完成（157 §7）；玩家蓝 / 敌人红；前台跳过自测 | `memory/tread-ui-style-prototype.md` |
| Slate 字距 | `MakeText` 不画 LetterSpacing，必须 MakeShapedText | `memory/tread-slate-maketext-letterspacing.md` |
| HUD 世界锚定坐标 | 投影给视口像素、`Ref/RefVec` 给设计像素，混用会把 HUD 挤到左上角 | `memory/tread-hud-world-anchor-space.md` |
| RemoveAt 悬垂引用 | `RemoveAt` 后用调用方的 `const FString&` 成员 = use-after-free；先拷副本 | `memory/tread-tarray-removeat-aliasing.md` |
| 夹具配板坑 | 配板消耗 RandomStream 会换对手（三个 AI 都要配）；`RequestId` 幂等 | `memory/tread-battle-fixture-pitfalls.md` |
| 崩溃取证工具 | `crash_exc.py` 看寄存器；`disasm.py` 四参数，引擎 dll 在 G 盘 | `memory/tread-crash-dump-tools.md` |
| UE Python 结构体别名 | `unreal.Transform` 赋值是别名不是拷贝，改副本会连源一起改（曾把碎片缩到 1% 而测出假帧率） | `memory/tread-unreal-python-struct-aliasing.md` |

`memory/MEMORY.md` 是 Claude 时代的原索引，保留作对照（内容已被上表覆盖）。

## 6. 可用 MCP 与 skill（2026-10-17 从 Claude Code 迁入）

- **unreal-mcp**（`mcp__unreal-mcp__*`）：只有 `list_toolsets` / `describe_toolset` / `call_tool` 三个入口，**只在 UE 编辑器开着时可用**（`http://127.0.0.1:8000/mcp`）。本项目用得上的工具集：`EditorToolset.EditorAppToolset`（PIE 开关、控制台命令、视口相机、资产成像）、`EditorToolset.LogsToolset`（读 `Saved/Logs/Tread.log`）、`AutomationTestToolset`（跑自动化测试拿结果）、`SlateInspectorToolset`（程序化驱动编辑器 UI）、`UMGToolSet`、`editor_toolset.toolsets.*`（actor / asset / blueprint / material / skeletal_mesh / static_mesh / scene）。先 `list_toolsets`，再 `describe_toolset` 拿参数 schema，最后 `call_tool`。
- **blender**（`mcp__blender__*`）：驱动**用户当前开着的 Blender**，`execute_blender_code` 就是活的 bpy，`look` 出图，`get_scene_info` 量包围盒（正好对上「先量再改」的规矩）。端口**不用配**：MCP 侧 `DEFAULT_PORT=9876`、addon 侧 `blendermcp_port` 默认也是 9876，两边天然对齐（只有改过 addon 端口才需要给条目加 `BLENDER_PORT`）。addon 默认 `blendermcp_auto_start_server=True`，**Blender 一启动就自动监听，不用手点 Connect**。连不上先查三件事：Blender 没开 / addon 没启用 / 端口被改过；addon 版本旧了就 `uvx mcp-for-blender install-addon`。PyPI 包名 `mcp-for-blender` 与旧名 `blender-mcp`（2.0.0 兼容壳）等价，两个都能用。没连上时回老办法：`blender --background` 跑 `Tools/` 下的 bpy 脚本（doc 132/142 就是这么干的）。
- **skill `procedura`**：程序化建模（OpenSCAD 源码 + `.obj`，分部件建、每轮渲染后改）。对本项目适合建筑部件 / 小道具；注意它产物是 `.scad`/`.obj`，进 UE 仍必须走 `Tools/` 的脚本与 FBX 管线（§2 规则 2）。

## 7. 维护约定

- **加新记忆**：在 `memory/` 新建 `<主题>.md`（保留 `name` / `description` 头），在 §5 表格加一行；规则类内容同步进 §2。
- **改记忆**：只改 `memory/` 原文 + 本文件的摘要行，两处别写岔。
- 原文里 `[[名称]]` 形式的链接 = `memory/<名称>.md`，DSH 不自动跳转，按名字找。
- 每次收尾若发现记忆过时，当场订正并在回复里说明改了什么。
