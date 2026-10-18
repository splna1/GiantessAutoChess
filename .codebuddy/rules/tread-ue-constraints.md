---
description: "《踏国》UE5 移植的硬约束：只读源目录、资产必须由 Tools/ 下脚本生成、禁止手 K 动画、中文回复与文档。开始任何新步骤前用这条自检（源自 Claude memory，2026-09-28）。"
---

# Tread UE 硬约束

- Never modify the old Unity project (`F:\AI\workbuddy\GiantessAutoChess`); it, the reference images, the model folder and the GP export (`0614/gp_extract`) are read-only. Copy to `Saved/Staging/` first.
- Every UE asset, level and material must come from a repeatable script under `E:/AI/Tread/Tread/Tools/` (or an editor operation); never hand-edit `.uasset`/`.umap`.
- Animation: no hand keying; all keys come from GP PSA data (Unity-derived `A_Clukay_*` clips are deprecated).
- Reply in Chinese; documents in Chinese under `document/`, numbered per `100_DOCUMENT_INDEX.md` (100+ = dated process records); code comments in English.

**Why:** the user stated these explicitly (2026-09-28); hand-keyed Unity clips were rejected as error-prone.

**How to apply:** check any new step against these before writing code; each phase ends with screenshots + a JSON report in `Saved/`. Schedule lives in doc 125.

Related: [[tread-doc-numbering]], [[tread-m2-runtime-notes]]
