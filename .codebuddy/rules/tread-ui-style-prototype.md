---
description: "Tread UI 换装（Ursus 构成主义 + Rhine 动效）：HTML 原型 2026-10-15 通过，UE 移植 2026-10-17 完成验收（doc 157 §7）；玩家蓝（血条/脚圈）、敌人红，前台必须跳过自测参数。改 HUD/前台时读这条。"
---

# Tread UI 换装

2026-10-15: owner approved the HTML prototype (`Saved/UIPrototype/Tread_UI_Prototype.html`, built from `Tools/ui_proto/`; doc 156) and asked to port it to UE5. Owner's rulings:

- Agent decides which UI is replaced (chosen: R0 campaign map → new front-end widget loading/login/select/sortie; whole match HUD restyled, layout + hit areas unchanged). Plan/spec = doc 157.
- Port work is executed by Sonnet sub-agents (Agent tool, model sonnet); main session orchestrates and verifies.
- **Player = blue (unit health bar, foot ring), enemy = red.** Player health bar used to be green — now blue.
- Owner's giantess silhouette (`Saved/UIPrototype/source/giantess_silhouette_src.png`) is the hero art: red on the login slab, ink inside the sortie disc.

**Why:** owner wants one unified poster style replacing the plain blue HUD, with faction colours kept readable.

**How to apply:** follow doc 157 §0 rules; front-end must stay out of self-test/capture runs (command-line skip list in doc 157 §4.1). PIE acceptance needs a TreadEditor build, which needs the owner to close the editor. Screenshot reviews go to Sonnet.

**Status 2026-10-17:** port finished. After 4 fix rounds (the last finished by the main session when Sonnet hit its usage limit), all 19 UI shots, M4 and battle PIE, and native M1/M2 pass. Open question for the owner: scoreboard AI names use per-player identity colours (yellow, purple), not red. `ue_ui_style_check_pie.py` refuses to run while the editor is minimised; restore the window first (Win32 ShowWindow SW_RESTORE works).

Related: [[tread-slate-maketext-letterspacing]], [[tread-shot-showui-crash]], [[tread-ue-constraints]]
