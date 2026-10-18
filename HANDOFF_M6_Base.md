# 交接：特勤处 M6 基地线（六件设施 + 施工场 + 履带吊 + 巨人座）

> 写于 2026-10-18 夜。
> **这不是项目文档**：不带编号，不放进 `document/`，也不占用文档编号。
> 交接对象：下一个接手 M6 基地线的 agent。
> 工程：`E:\AI\Tread\Tread`；Blender 5.2.0 LTS，经 `dsh-blender-plugin` 的 `blender_rt_*` 直连通道跑 headless。不是 git 仓库。

---

## 0. 三十秒版本

一条链路：`build_*.py`（逐件）→ `assemble.py`（总装）→ `render_batch.py`（出图）→ `audit_export.py`（审计 + FBX/GLB）。
**尺寸只有一个真源**：`Tools/m6/base/m6spec.py`。`build_*.py` 里不许发明尺寸，只能引用 `MODS[...]`。
当前产出：10 个 `.blend`、10 组 FBX/GLB、35 张渲染图（其中 `shot_C2t_*` 两张是早期试验图，可删）、1 份审计回执、3 篇文档（179 / 181 / 182）。

---

## 1. 当前目标

M6 = 172 号设计案里的**特勤处局外基地**（`M6_Bureau`）。主人先后要了三批东西：

1. **六件设施模块**（指挥中心 / 机库 / 兵营 / 雷达近防塔 / 门禁围墙 / 无人机坪）+ 220×170 m 总装 —— 文档 **179**。
2. **可扩展基地 + 施工中的工地（建材按 100 m 女巨人可搬运）+ 高精度履带式集装箱吊车** —— 文档 **181**。
3. **给 100 m 女巨人坐的建筑，高矮两段（矮=座面，高=靠背）** —— 文档 **182**。

三批都已完成建模、渲染、审计、导出与文档。**下一步没有拍板**，见 §5。

---

## 2. 已经完成了什么

| 批次 | 件 | 对象 | 三角面 | 关键尺寸 | 文档 |
| --- | --- | ---: | ---: | --- | --- |
| 179 | **C2** 指挥中心 | 15 | 15 596 | 基座 40×32，桅顶 41.5 m | 179 |
| 179 | **HGR** 机库 | 10 | 9 276 | 48×34，檐 14.6 / 脊 18.8，门洞 28×11.2 | 179 |
| 179 | **BRK** 兵营 | 10 | 9 034 | 40×12，四层，檐 13.7 | 179 |
| 179 | **RDR** 雷达近防塔 | 10 | 8 516 | 塔 38 m，总高 49.5 m，AESA 6.6×5.0 | 179 |
| 179 | **GTE** 门禁围墙 | 10 | 3 860 | 门卫房 12×8，哨塔 9.2 m，围界 ≈116 m | 179 |
| 179 | **UAV** 无人机坪 | 9 | 6 876 | 坪 30×26，发射棚 15×7.5 | 179 |
| 181 | **CON** 施工场 | 14 | 26 306 | 64×52 场地，基坑 34×24×4.2，框架 24×18 两级 | 181 |
| 181 | **CCR** 履带吊 | 11 | 11 414 | 履带 10.6×1.9（轨距 4.8），臂 44 m @58°，吊具 12.6 m | 181 |
| 182 | **SIT** 巨人座 | 16 | 13 370 | 座体 64×46×26，靠背 64×18×78，总高 90.5 | 182 |
| — | **SITE** 总装 | 118 | 127 658 | 220×170 m，9 个落位 + 4 块扩建地块 + 南门外 120×92 m 广场 | 179/181 |

- **可扩展机制**：`SITE["expansion"]` 是唯一清单（P-01 施工场已用、P-02 车辆场二期、P-03 仓储、P-04 能源站、S-01 巨人座广场）；`assemble.py` 自动画碎石垫层、白色边界、四角橙顶角桩、预留标牌。**加模块 = 3 行注册**（`MBLENDS` / `SITE["place"]` / `assemble` 的 tag 元组）。
- **渲染**：每件 hero / front / aerial；吊车另加 side / low 特写；C2 另有 detail / entry；总装 aerial + hero——共 35 张（`shot_C2t_*` 两张为早期试验，可删）。全部在 `Saved/M6Base/renders/`。
- **审计**：`Saved/M6Base/reports/audit_export.json` 覆盖 10 件。**CON / CCR / SIT / GTE 每个对象都是闭合流形**（边界边 0、非流形 0、退化 0、游离 0）；C2/HGR/BRK/RDR/UAV 的少量边界边来自开放薄壳件（抛物面天线、管件端头），从 179 起就登记为已知限制。
- **导出**：`model/m6/base/export/{C2,HGR,BRK,RDR,GTE,UAV,CON,CCR,SIT,SITE}.{fbx,glb}`。

---

## 3. 权威来源（冲突时按这个顺序）

| 优先级 | 路径 | 作用 |
| ---: | --- | --- |
| 1 | `Tools/m6/base/m6spec.py` | **唯一真源**：模块尺寸、材质表、发光表、`SITE` 尺寸/落位/扩建地块 |
| 2 | `Tools/m6/base/lib_kit.py` | 几何原语（面板/百叶/桁架/履带/吊具/工字钢…）、材质管线、天空、地面散布、`finish()` |
| 3 | `Tools/m6/base/build_*.py` | 每件的具体构造；**改形状只改这里** |
| 4 | `Tools/m6/base/assemble.py` | 落位、场地、道路、围界、扩建地块、外场广场 |
| 5 | `Saved/M6Base/reports/audit_export.json` | 审计数字的**唯一回执**；不要手抄到别处 |
| 6 | `Saved/M6Base/renders/` | 验收图（`shot_<TAG>_<view>.png`） |
| 7 | `document/179_…md`、`181_…md`、`182_…md` | 设计与施工记录（中文）；`document/100_DOCUMENT_INDEX.md` 已登记 |
| — | `Tools/warsaw/lib_geom.py` | **只读复用**（`MB` 基类与 `emit`），不要改 |

**明确不是权威**：`Saved/M6Base/preview/`（迭代中间图）、`Saved/M6Base/diag/`（打光试验）、`shot_C2t_*` 之类的试验图、`model/m6/base/*.blend1` 备份。旧结论以本文与三篇文档为准。

---

## 4. 不能重新争论的决策

1. **工具链**：建模走 `blender_rt_*`（`dsh-blender-plugin`）；`dsh-ops` 只负责 shell/file。不要把 `dsh-ops` 当建模插件（这是最初的一个误解，已澄清）。
2. **坐标与单位**：米、Z 向上、+X 东、+Y 北；模块**正面朝局部 -Y**、原点在地面。总装落位只读 `SITE["place"]` 的 `pos/rz`。
3. **资产只脚本生成**（项目硬规则 2）：不改 `.uasset/.umap`，也不手改 `.blend` 里的几何；要改就改 `build_*.py` 重跑。
4. **参考只取设计语言**：模块化未来军事基地资产目录、无人机威胁下的模块化掩体、预制地堡、北约东翼筑垒——**没有导入任何外部模型/贴图/代码**。
5. **材质口径**：不用 Warsaw 的 Voronoi 混凝土（建筑尺度像碎冰）；一律"一条噪声驱动颜色斑驳 + 粗糙度 + 凹凸"；重钢用 `steel_plate` / `steel_matte` / `track_steel` 三档，带 90 周期/米细噪声做磨砂。
6. **命名**：对象 `GEO-<MOD>-<part>`；材质 `M6_<key>`；总装文件 `M6_Base_Site.blend`。
7. **场地冻结**：SITE 220×170 m、围界 3.3 m、9 个落位坐标、4 块扩建地块都已定；新增模块必须走 `expansion` + 3 行注册，**不要硬编码新坐标**。
8. **巨人座口径**：26 m 座高 / 78 m 靠背（按 1.70 m 的人 58.8 倍换算）；**只做两段，不加扶手**（主人明确"由高矮两部分组成"）。
9. **渲染口径**：解析法 NDC 取景（把 8 角点投影解距离），不要退回"AABB 半径 × 系数"；世界用屏幕空间竖向渐变 + 30° 西南低阳 + 反侧柔光；AgX、曝光 +0.35；Cycles 40 samples / 1280×960。
10. **审计读法**：装配体一个对象装多块咬合构件 → `normals_unknown` → `state=degraded`，这不是缺陷；开放薄壳的边界边也不是缺陷。**不要为了把 `state` 刷成 pass 去拆对象**（179 §6 已经写过）。
11. **文档号**：179 / 181 / 182 已占用；**下一个空号 183**，新建前先 `Glob document/18*.md` 复核（别的会话也在用号）。
12. **批量渲染**：一个 Blender 进程连续开 6 个文件后崩过一次（exit 3221225786）；**≤4 个文件/进程**。

---

## 5. 下一步从哪里开始

**默认先做 A**：172 的 P0 要的是"场景能看"，不是"更多模型"。

### A. 进 UE（推荐，未拍板）
1. 建 `M6_Bureau` 关卡；若只是审查，用临时地图（别往游戏地图里生成，参考 `memory/tread-editor-python-map-switch.md` 的切图纪律）。
2. 逐件导入 `model/m6/base/export/*.fbx`（`FBX_SCALE_ALL`，米制）；一次 ≤4 件，注意 8 GB 卡显存（doc 140 的批次纪律）。
3. 材质：按 `M6_*` 建 Material Instance，沿用 `MI_Paint_*` 命名；发光件（`em_white/amber/cyan/red`）走 Unlit。
4. 碰撞：盒群（每件 6–20 盒），**不要**用渲染网格当碰撞。
5. 落位：直接读 `m6spec.SITE["place"]`；与 172 的地块桩标（`Bureau.json`）对齐。
6. 验收：`HighResShot` 多角度 + `Saved/Reports/M6_Import.json`（对象数 / 三角面 / 缺材质 / 帧率）。

### B. 继续加模块
复制 `build_con.py` → 在 `MODS` 加尺寸块 → 在 `MBLENDS`、`SITE["place"]`、`assemble.py` 的 tag 元组各加一行 → 跑 `build_*.py` + `assemble.py`。P-02 / P-03 / P-04 就是给这个准备的。

### C. 巨人座与看板娘的"坐下"验证
用一个 100 m 胶囊或现有巨人模型做坐姿对照，确认座面 26 m 与膝弯、靠背 78 m 与头高的关系；再决定是否把座面/靠背高度微调（改 `MODS["SIT"]` 一处即可重出）。

### D. 提升精度（可选）
板缝胶条凹槽、幕墙竖挺、屋顶检修走道、地脚螺栓；吊车的臂角/回转/吊具高目前是 spec 参数（可重出但没关键帧），要做"抬臂/回转"动画先把这三个量参数化。

---

## 6. 该调用哪些 skills

| Skill | 什么时候 | 说明 |
| --- | --- | --- |
| **`blender-modeling`** | **任何 bpy 操作前，必调** | 决策树（分面/光滑/有机/阵列/布尔）、流水线、24 个配方、六条坑；本组脚本就是照它的"冻结规格 → blockout → 细修 → 清理 → 交接"走的 |
| `procedura` | 需要 OpenSCAD 参数化零件（吊具、桁架节点、可复用连接件）时 | 产物仍必须经 `Tools/` 脚本 + FBX 管线进 UE，不能直接进工程 |
| `github` | 只有要查/提交仓库时 | 本工程**不是 git 仓库**，通常用不上 |
| `diagnose-windows-sandbox-acl` | 只有出现 sandbox 文件拒绝、且疑似 ACL 问题时 | 正常读写不该触发 |
| （不调）`unreal-mcp` / `ai-game-developer` | 除非 UE 编辑器开着且确实要做编辑器内操作 | 没开时连接会超时 |

---

## 7. 常用命令

```bash
# 逐件（约 1.5–3.3 s/件）
blender -b --factory-startup --python Tools/m6/base/build_c2.py
blender -b --factory-startup --python Tools/m6/base/build_hgr.py
blender -b --factory-startup --python Tools/m6/base/build_brk.py
blender -b --factory-startup --python Tools/m6/base/build_rdr.py
blender -b --factory-startup --python Tools/m6/base/build_gte.py
blender -b --factory-startup --python Tools/m6/base/build_uav.py
blender -b --factory-startup --python Tools/m6/base/build_con.py
blender -b --factory-startup --python Tools/m6/base/build_ccr.py
blender -b --factory-startup --python Tools/m6/base/build_sit.py

# 总装（追加 9 件 + 场地 + 扩建地块 + 外场广场）
blender -b --factory-startup --python Tools/m6/base/assemble.py

# 出图（≤4 个文件/进程；-mods 逗号分隔，-views hero,front,aerial,side,low）
blender -b --factory-startup --python Tools/m6/base/render_batch.py -- \
        --res 1280x960 --samples 40 --views hero,aerial --mods SIT,SITE

# 审计 + FBX/GLB（需要预载 audit）
blender -b --factory-startup --python Tools/m6/base/audit_export.py
```

Dsh 通道下对应 `blender_rt_headless(script_file=..., preload="audit")`；长渲染用 `as_job=true`。

---

## 8. 本地踩过的坑（按出现顺序）

1. **`spec.py` 同名冲突**：`Tools/warsaw/spec.py` 与本项目同名，`import spec` 会拿到 Warsaw 的 → 本项目改名为 `m6spec.py`。
2. **材质缓存跨文件失效**：`bpy.ops.wm.open_mainfile` 会让缓存的 `bpy.data` 引用失效（`ReferenceError: StructRNA ... removed`）→ 打开文件后调 `K.reset_cache()`。
3. **`MB.push/pop` 是每个 MB 独立的**：在 `A.push(M)` 里用 `B.box(...)`，B 不会吃到变换（吊车臂走道、巨人座玻璃廊、车辆玻璃/轮胎都踩过）→ 给每个要画的 MB 都 push。
4. **引擎枚举只报 `BLENDER_EEVEE`**，但 `scene.render.engine = "CYCLES"` 是能直接赋值的 → 不要用枚举过滤再赋值。
5. **Nishita 天空会过曝**（实测画面全白）→ 改成平世界 + 屏幕空间竖向渐变（底部沙尘暖色 → 顶部冷蓝）。
6. **取景不能按 AABB 半径估**：60 m 的东西拍成画面 40% → 用 8 角点投影解最小距离（`render_shots.fit`）。
7. **批量渲染崩进程**：连续开 6 个 `.blend` 后 exit 3221225786；拆成 ≤4 个/进程后稳定。
8. **`GEO-SIT-seat` 的原点在座体中心**（y −23…23），靠背在 23…41；改座深时 plinth 的 `PLY1` 要跟着走（否则靠背悬在台外）。

---

## 9. 关键文件清单

```
Tools/m6/base/
  m6spec.py            # 冻结规格（尺寸/材质/落位/扩建）
  lib_kit.py           # 细节库 + 材质 + 天空 + 地面散布
  build_c2.py … build_sit.py   # 9 件
  assemble.py          # 总装 + 场地 + 扩建地块 + 广场
  render_batch.py      # 批量出图（解析取景）
  render_shots.py      # 单件出图/取景函数（被 batch 复用）
  audit_export.py      # 审计 + FBX/GLB
model/m6/base/
  M6_*.blend           # 10 个场景
  export/*.fbx|.glb    # 10 组交换格式
Saved/M6Base/
  renders/             # 验收图
  reports/audit_export.json
  preview/ diag/       # 中间产物，非权威
document/
  179_… 181_… 182_…    # 三篇记录
  100_DOCUMENT_INDEX.md
```

---

## 10. 交接时最重要的三句话

1. **尺寸只认 `m6spec.py`**，其余都是它的消费者；发现别处写死数字就是 bug。
2. **审计的 `degraded` 不是失败**——装配体多壳导致的 `normals_unknown` 是设计使然，真正要看的是退化面/游离点/边界边。
3. **先问主人走 A 还是 B**（进 UE vs 继续加模型）；默认 A。
