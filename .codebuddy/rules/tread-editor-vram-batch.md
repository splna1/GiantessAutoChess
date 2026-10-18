---
description: "8 GB 显卡跑长批次（批量导入/重定向骨骼网格）会 GPU 崩溃 CreateReservedResource failed；根因是缩略图渲染器每个约 90 MB VRAM。批量跑编辑器脚本前必读。"
---

# 编辑器长批次显存崩溃

On the owner's RTX 4060 Laptop (8 GB, D3D12 budget ~7.1 GB) the editor crashed twice on 2026-10-12 during M4 VRM batches with `LogD3D12RHI: Error: GPU crash detected ... Adapter->CreateReservedResource(...) failed`, breadcrumbs in GPUSkinCache skinning of the newest SK_VRM mesh (char_054 during import, char_016 during retarget). Each SavePackage renders a thumbnail (3454 in one session), and the project has `r.RayTracing=True`, Lumen, VSM and the skin cache on, so GPU memory builds up across a session; `obj gc` between characters does not stop it.

**Root cause (found 2026-10-12):** the thumbnail renderers for SkeletalMesh, Skeleton, IK Rig, IK Retargeter and cloth assets each cache one preview FScene per rendered asset (`TObjectInstanceThumbnailScene<...,128>`), ~90 MB VRAM each; `rhi.DumpResourceMemory all` showed 32 alive (~2.9 GB). Unloading assets or ray tracing off does not free them. Fix: editor console command `Tread.FlushThumbnailScenes` (`Source/Tread/TreadEditorThumbnails.cpp`) swaps those renderers and GCs; `Tools/m4` batch scripts call it per character. Undo buffer also pins touched objects: reload the map (`Tools/m4/editor_release.py` reload) to reset it. Ray tracing turned off in `DefaultEngine.ini`.

A single FBX import can also stall the game thread for a long time without crashing: char_080 (112 submeshes) took 23 min in FBXSDK translation, and the editor showed "Not Responding". That stall is not a hang — check the log and CPU before concluding it hung.

**Why:** each crash loses the editor session and the owner has to restart it by hand.

**How to apply:** run editor batches as many small remote calls (`--limit 4-5`), keep every tool resumable from its report, watch nvidia-smi between calls (stop above ~6300 MiB), and if VRAM still climbs ask the owner to restart the editor before continuing. Never close the editor yourself.

Related: [[tread-m2-runtime-notes]], [[tread-shot-showui-crash]]
