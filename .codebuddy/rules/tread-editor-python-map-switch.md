---
description: "UE 编辑器 Python 切地图（load_level）必须单独一次调用，同一帧里先持有世界引用再切图会让编辑器 fatal 崩溃。写编辑器脚本涉及切图时必读。"
---

# 编辑器 Python 切图崩溃

在 `E:\AI\Tread\Tread` 里用 `Tools/ue_run.py` 跑编辑器脚本时，**切地图（`load_level` / `load_map`）必须在独立的脚本调用里做**，而且那一次调用里不要先读取当前世界。

反例（已造成两次编辑器致命崩溃）：

```python
w = unreal.EditorLevelLibrary.get_editor_world()   # 持有世界引用
print(w.get_path_name())
unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level('/Game/Tread/Maps/M3_Paris_Match')
```

崩溃日志：

```
LogLoad: Error: Old Package /Game/Tread/Maps/<旧地图> not cleaned up by GC!
  referenced by GCObjectReferencer
Fatal error: EditorServer.cpp:1951 — World Memory Leaks: 1 leaks objects and packages.
```

原因：正在执行的 Python 栈帧里的局部变量仍引用旧世界，GC 清不掉旧包，切图时的泄漏检查直接 fatal。

**Why:** 这个坑不写下来必然重犯——两次都是隔了几十分钟又踩进去，每次都赔上编辑器重启（几分钟）和一次现场恢复。

**How to apply:** 切地图前先确认没有脏包；把切图写成一次只做 `load_level` 的调用，之后再新起一次调用去读世界/找 Actor。

Related: [[tread-m2-runtime-notes]]
