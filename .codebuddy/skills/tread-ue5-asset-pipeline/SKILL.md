---
name: tread-ue5-asset-pipeline
description: "在 Tread 工程里做角色模型资产管线时使用：VRM/MMD 模型导入 UE、Blender 转 FBX、逐槽卡通材质、IK Rig / IK Retargeter 动作重定向、骨骼缩放与姿势对齐、批量导入时的编辑器显存问题。触发词：VRM、MMD、PMX、FBX、重定向、retarget、IK Rig、蒙皮、材质槽、char_0xx、char_1xx。"
---

# Tread 角色资产管线

角色名册 = **100 个 VRM + 12 个 MMD**。两条线共用同一套"导出 → 导入 → 材质 → 重定向 → 验证"流程。

| 部分 | 角色 | 源 |
|---|---|---|
| VRM | `char_002` … `char_100`（`char_001` 是英雄 Clukay416，跳过） | 旧 Unity 工程 `F:\AI\workbuddy\GiantessAutoChess\`（**只读**） |
| MMD | `char_101` … `char_112` | 同上 |

**权威记录**：VRM 看 `document/152_UE5_M4-A_100个VRM批量导入_重定向_显存修复_2026-10-14.md`；
MMD 看 `document/151_UE5_N2收尾_腿部D骨与朝向修复_全量验收_2026-10-12.md` + 根目录 `HANDOFF_N2.md`。
报告一律以 `Saved/Reports/*.json` 为准。

## 管线（全部可重跑、按报告断点续跑）

VRM 线：

```bash
python Tools/m4/vrm_inventory.py                                # 读只读源目录，写普查报告
python Tools/m4/m4_export_vrm_fbx.py --jobs 4                   # 复制到 Saved/Staging/vrm100，Blender 转厘米制 FBX（yaw 180）
python Tools/ue_run.py Tools/m4/ue_import_vrm.py --limit 5      # 分批导入
python Tools/ue_run.py Tools/m4/ue_vrm_materials.py --limit 5   # 分批配材质
python Tools/ue_run.py Tools/m4/m4_build_retarget.py --limit 5  # 分批 IK Rig / Retargeter / 33 段动作
python Tools/ue_run.py Tools/m4/editor_release.py reload        # 批次之间：切图重置撤销缓冲
python Tools/ue_run.py Tools/m4/editor_release.py gc            # 批次之间：卸载资产包 + 释放缩略图场景
```

MMD 线的对应脚本在 `Tools/m4/`：`n2_export_mmd_fbx.py` → `mmd_texture_alpha.py`（**必须在上一步之后跑**）→ `ue_import_mmd.py --rebuild` → `ue_mmd_materials.py` → `n2_build_retarget.py`。

**每批前用 `nvidia-smi` 看显存，超过 6300 MiB 就停。**

## 不可重议的规则（都是踩过坑换来的）

### 1. 厘米制导出，别用 `FBX_SCALE_ALL`

实测三种方式在 UE 里的根骨缩放：

| 方式 | 根骨缩放 |
|---|---|
| `FBX_SCALE_NONE` + 导入缩放 0.08 | 100 ❌ |
| `FBX_SCALE_ALL` + 导入缩放 0.08 | **仍是 100** ❌（UE 把文件头单位缩放折回根节点） |
| 导入缩放 8.0 + 场景 `scale_length=0.01`，导出**不做缩放** | **1.0** ✅ |

根骨缩放是 100 时，重定向导出的 `A_GP_*` 会把该缩放写成 1，**整个人缩到 1~2 cm** ——
组件"已渲染"标志为真但没有像素。已落地在 `Tools/m4/blender_mmd_to_fbx.py`（默认 `--scale 8.0 --unit-scale 0.01 --scale-mode none`）。

### 2. 重定向必须对齐 target retarget pose

MMD 是 **A-pose**、VRM 英雄是 **T-pose**，IK Retargeter 默认取各自骨架参考姿势 → **手臂反向约 100°**
（手首跑到肩上方 26 cm，英雄是肩下方 43 cm），而脊椎/腿/所有骨骼缩放**全都正常**。

修法在 `n2_build_retarget.py` / `m4_build_retarget.py` 的 `make_retargeter`：

```python
controller.auto_align_all_bones(unreal.RetargetSourceOrTarget.TARGET,
                                unreal.RetargetAutoAlignMethod.CHAIN_TO_CHAIN)
```

**验收必须按关节角度**（`armDeg` 之类），不能只看骨骼缩放和包围范围。

### 3. 腿拆成三条链

UE 5.8 的 FK Chains op（Interpolated 模式）对目标链每根骨取源链**同一比例位置**的旋转。
膝盖不在同一比例处、或腿里夹着扭转骨（AdvancedSkeleton 的 `HipPart1/2`、`KneePart1/2`）时，弯曲会被分走。
每条腿拆成 **Thigh / Shin / Foot** 三条链，在膝和踝切开。源端另建 `IK_Clukay416_LegSplit`；原 `IK_Clukay416` **不动**（12 个 MMD 的 Retargeter 还引用它）。

### 4. 其它沿用规则

- 重定向根取**脊柱与两腿链的最低公共祖先**，不是 VRM 的 hips（MMD 系 hips 是センター，太低，跪坐时膝盖悬空）。
- 腿部蒙皮挂在 MMD `D` 骨上的模型，腿链要接 **D 骨**（`足D` / `ひざD` / `足首D`）。
- **IK Rig / IK Retargeter 取回 + 原地重配，绝不删除重建** —— 删掉被引用的 IK Rig 会让编辑器崩溃且不留转储。
- 动画不许手 K，跨骨架只能重定向。

## 编辑器显存泄漏（批量导入必读）

**现象**：8 GB 显存上每处理 5 个角色约涨 1 GB，最终 GPU 崩溃（`CreateReservedResource failed`）。

**根因**：保存资产时会渲染缩略图。SkeletalMesh / Skeleton / IK Rig / IK Retargeter / 布料资产的缩略图渲染器
各为每个渲染过的资产缓存一个预览 FScene（`TObjectInstanceThumbnailScene<...,128>`），**每个约 90 MB**，
卸载资产释放不了，只有渲染器自己 `BeginDestroy` 才清。

**修法**：
- 编辑器控制台命令 **`Tread.FlushThumbnailScenes`**（`Source/Tread/TreadEditorThumbnails.cpp`，仅编辑器构建）——
  三个批处理脚本每处理完一个角色就调一次。
- `Tools/m4/editor_release.py`：`reload` 切图重置撤销缓冲、`gc` 卸载包 + 释放缩略图场景。
- 修完后 68 个角色连续重定向，显存稳定在 2.9–3.6 GB。

## 流程坑

- **`--rebuild` 会静默半途而废**：`EditorAssetLibrary.delete_directory/delete_asset` 对编辑器已加载的资产
  返回 `True` 但文件还在；接着 `create_asset` 同名返回 `None`。`ue_import_mmd.py` 现在在 mesh 没删掉时**直接报错**。
- **脏包会挡住地图切换**，第 3 / 第 7 步之前必须没有脏包；长任务跑完记得存盘。
- presenter 的组件在 `Tick()` 里建，而 Python 远程执行跑在游戏线程上 —— **"铺盘"和"数组件"必须分成两次调用**。
- **IK Retargeter 的链映射在 UE 5.8 Python 里读不出来**（`get_all_chain_settings()` 返回空数组）。
  能读的是 IK Rig 的链：`unreal.IKRigController.get_controller(rig).get_retarget_chains()`。
- 单个大 FBX 可以让游戏线程卡很久（char_080 有 112 个子网格，转换用了 23 分钟），编辑器显示"未响应"——
  **先查日志和 CPU，别误判成卡死**。

## 资产落点

```
/Game/Tread/Characters/VRM/char_0xx/   SK_VRM_char_0xx(+Skeleton/PhysicsAsset)、Materials/MI_Toon_*、Retarget/IK_VRM_char_0xx 与 RTG_char_0xx、Anim/A_GP_*
/Game/Tread/Characters/MMD/char_1xx/   同上，命名 SK_MMD_char_1xx / IK_MMD_char_1xx
```

`ATreadM3BoardPresenter::ResolveCharacterVisuals` 按角色 ID 解析：`char_002..100` 用 VRM、`char_101..112` 用 MMD，
`char_001` 和缺资产的角色回退到英雄。**这条 C++ 不用改。**
