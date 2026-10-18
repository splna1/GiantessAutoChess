---
description: "UE 导入贴图时会把大片蓝/紫的基础色贴图自动判成法线贴图（BC5、B=0），蓝变黄绿、紫变黄；颜色贴图导入必须强制 TC_DEFAULT + sRGB。遇到颜色异常先查这里。"
---

# 贴图被误判成法线贴图

2026-10-14：头像 026/031/044/061（另有 025、052 的小配件）蓝紫色变黄绿/黄。根因是引擎 NormalMapIdentification 在导入时按像素把偏蓝的大块贴图判为法线贴图（TC_NORMALMAP、srgb=False、BC5 只存 RG，B 读成 0），文件名 `_D` 后缀不影响判断。

**Why:** `ue_vrm_materials.py` 的 `import_texture()` 当时没指定贴图类型，全靠引擎自动判断。

**How to apply:** 颜色贴图导入一律强制 TC_DEFAULT + srgb=True + TEXTUREGROUP_WORLD（已修进 `ue_vrm_materials.py`，并有 BaseTex 验收）。`Tools/m4/fix_color_textures.py --check` 可扫描。改贴图设置后同一编辑器会话里重拍可能仍用旧渲染状态：要先重载地图、gc、卸载相关贴图和材质实例包再拍。颜色异常先查贴图压缩设置，别先怀疑截图管线。

Related: [[tread-viewport-capture-lies]]
