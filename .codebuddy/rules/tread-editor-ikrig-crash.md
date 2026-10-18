---
description: "删掉被 IK Retargeter 引用的 IK Rig 会让编辑器崩溃（UnrealEditor-IKRig 空指针）；IK Rig / Retargeter 一律原地重配不要删除重建，编辑器已加载的资产 delete_asset 会静默失败。"
---

# IK Rig 删除崩溃

2026-10-11：`n2_build_retarget.py` 原来先 `delete_asset` 再 `create_asset` 重建 IK Rig，重建 char_101 的 rig 后、下一条 IK Rig 调用时编辑器**直接崩掉**：

```
Critical error: EXCEPTION_ACCESS_VIOLATION reading address 0x0000000000000000
[Callstack] UnrealEditor-IKRig.dll ... UnrealEditor-IKRigEditor.dll ... PythonScriptPlugin.dll
```

原因：IK Retargeter 的 op 里还存着指向刚被删掉的 rig 的对象，下一次 IK Rig 操作解引用它。崩溃没有生成 `Saved/Crashes` 转储，只有 `Saved/Logs/Tread.log` 末尾有堆栈。

- 修法（已落地）：`make_rig` 改成**原地重配**——`load_asset` 取回同一个对象，`set_skeletal_mesh`（路径不同才调）、`set_retarget_root`、逐个 `remove_retarget_chain` 再 `add_retarget_chain`，最后保存。`make_retargeter` 同理（`remove_all_ops` + 重设两个 rig + `add_default_ops` + `auto_map_chains` + `auto_align_all_bones`），不删除。
- 另一个坑：`EditorAssetLibrary.delete_directory()` / `delete_asset()` 对**编辑器进程已经加载**的资产会静默失败（返回 True 但文件还在，Windows 上文件被进程锁住），于是 `create_asset` 同名返回 None。`ue_import_mmd.py --rebuild` 因此在 2026-10-11 静默留下了 12 个 `Retarget/` 目录；现在它会在 mesh 没删掉时直接报错。

**Why:** 重建派生资产的"删了再来"写法在这套资产上会崩编辑器，而且崩之前一切看起来都正常。

**How to apply:** 生成 IK Rig / IK Retargeter 的脚本一律用"取回 + 重配"，不要删除；真要删除，先确认没有别的资产引用它。

Related: [[tread-retarget-pose-align]], [[tread-m2-runtime-notes]]
