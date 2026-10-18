---
description: "一条髋到脚的 FK 链在目标膝盖位置不同或腿里有 twist 骨时会丢膝弯；腿必须拆成 Thigh/Shin/Foot 三段链，源用 IK_Clukay416_LegSplit，swing 判据量髋→膝。"
---

# 重定向腿链拆分

UE 5.8 FK Chains op (Interpolated) gives each target bone the source rotation at its fractional position along the chain. On 2026-10-13 the M4 VRM pose sweep found knees bending ~35 deg short on char_053 (knee at 37 % of the leg vs hero 49 %) and char_046 (AdvancedSkeleton HipPart1/2, KneePart1/2 inside the leg). Fix in `Tools/m4/m4_build_retarget.py`: legs split into Thigh/Shin/Foot chains, source = `IK_Clukay416_LegSplit` (a copy; `IK_Clukay416` stays untouched because the 12 MMD retargeters use it). Also the sweep's leg "swing" now measures hip->knee, not hip->ankle (the latter depends on thigh/shin ratio and gave false 30 deg fails).

**Why:** both bugs were invisible in the cheap numeric pass until the ratio/twist cases showed up.

**How to apply:** for new rigs, check the leg bone path length and thigh/shin ratio; keep single-bone leg chains.

Related: [[tread-retarget-pose-align]], [[tread-mmd-dbone-skin]]
