---
description: "UE 5.8 Slate 的 MakeText 不画 FSlateFontInfo::LetterSpacing，FontMeasure 也不算它；字距只能用 MakeShapedText 画并用同一整形序列测宽。做自定义绘制文本/字距时读这条。"
---

# Slate 字距（LetterSpacing）

In UE 5.8, `FSlateDrawElement::MakeText` renders through `ElementBatcher::AddTextElement`. That path lays out glyphs from `FCharacterList` and **ignores `LetterSpacing`**. Letter spacing is only applied by `SlateTextShaper`, i.e. by `MakeShapedText` / STextBlock. The legacy `FontMeasureService::Measure` also ignores it and measures at scale 1.

Slate's spacing value works out as px = `(int16)(LetterSpacing * FontScale * Size / 1000)`. `Size` is in points rendered at 96 DPI, so one CSS em = Size × 96/72 px.

**Why:** in the 2026-10-17 UI port, tracking never showed up across two fix rounds. After measurement was switched to shaped text, chained text segments then showed big gaps, because the measured width included spacing that the renderer never drew.

**How to apply:** measure and draw tracked text with the same shaped glyph sequence, at the paint scale (`Geo.GetAccumulatedLayoutTransform().GetScale()`), and draw it with `MakeShapedText`. Never mix MakeText with shaped measurement.

Related: [[tread-ui-style-prototype]]
