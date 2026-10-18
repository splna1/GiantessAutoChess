---
description: "《踏国》数值口径：数值/盟约/干员/道具/策略以 Stronghold-Protocol 网页复刻数据为真源（只取数据不抄 GPL 代码），112 卡 = 100 模型 + 12 MMD（2026-10-08 主人拍板）。涉及数值、盟约、卡池时读这条。"
---

# Stronghold 数值口径

2026-10-08 owner directive: numbers, pacts etc. follow https://github.com/sganggs/Stronghold-Protocol (snapshot commit 3eced7bd, staged read-only at `Saved/Staging/ref/`). Its `data/chess.json` has 112 recruitable chars, `bonds.json` 23 pacts (fills M2's 5 missing), `config.economy`. Roster 112 = existing 100 models + 12 MMD PMX models in `E:\AI\Tread\Tread\mmd_12` (12th = 异环 浔, added 10-08). Owner decided 10-08: take only numbers/pacts/operators/items/strategies, keep Tread's 4-player PvP 12-round structure; project is a non-commercial fan work. Implemented 10-09 (doc 144, `Tools/m4/`). Plan in doc 143 + `UE5_移植施工计划` "新增计划" (N1 data, N2 roster).

**Why:** owner wants the web remake's balance as source of truth instead of the two xlsx sheets.

**How to apply:** take data only, never copy its GPL-3.0 code; flag that its data is Hypergryph-owned non-commercial, GF2 MMD models are "MMD-only", 异环 models forbid gore/violence — pending owner confirmation (doc 143 §4).

Related: [[tread-doc-numbering]], [[tread-ue-constraints]]
