#pragma once

#include "CoreMinimal.h"
#include "Fonts/SlateFontInfo.h"
#include "Layout/Geometry.h"
#include "Rendering/DrawElements.h"

struct FSlateBrush;

/**
 * Tread UI style library (doc 157 section 3): paper / ink / red print look shared by the match HUD and the front end.
 *
 * Conventions
 *  - Every draw helper takes (Out, Geo, Layer, ...) and works in the local space of Geo; positions and sizes are
 *    already-scaled local pixels. Fixed design constants of the composite helpers (borders, cuts, shadows) are in
 *    1920x1080 design pixels and multiplied by the trailing Scale argument (local px per design px).
 *  - Slate draws the elements of one layer by TYPE (boxes, text, lines, custom polygons), not in call order. Anything
 *    that must overlap another thing therefore has to sit on a higher layer. Composite helpers document the layers
 *    they use as "Layer .. Layer+N"; put your own content above that.
 *  - Game thread only. Safe without a renderer (-nullrhi): geometry is still emitted, text is measured by estimate.
 *  - Missing UI assets never crash: fonts fall back to the engine default, textures draw nothing. One warning per asset.
 */
namespace TreadUI
{
	// ------------------------------------------------------------------ colour tokens (doc 157 section 3.1)
	// Authored in sRGB, stored linear (FLinearColor::FromSRGBColor), identical to the HTML prototype :root.
	extern const FLinearColor Paper;      // #E3D5B8
	extern const FLinearColor PaperL;     // #EFE6D3 light paper: panels, text on ink
	extern const FLinearColor PaperDD;    // #D8C8A6 disabled
	extern const FLinearColor PaperD;     // #C4B18D shadow paper
	extern const FLinearColor Ink;        // #16120F
	extern const FLinearColor Ink2;       // #2B241F
	extern const FLinearColor Red;        // #C2161C
	extern const FLinearColor RedD;       // #8E1015
	extern const FLinearColor RedL;       // #E3402F red text on ink
	extern const FLinearColor RedHi;      // #F2553D
	extern const FLinearColor Player;     // #3D8BFF player blue (health bars, drop hints)
	extern const FLinearColor PlayerInk;  // #1F4FA8 player blue on paper (text, label plates)
	extern const FLinearColor Enemy;      // #E3402F enemy red (health bars); on paper use Red
	extern const FLinearColor Ochre;      // #B8860B funds, emphasis
	extern const FLinearColor Olive;      // #4E7A2E success
	extern const FLinearColor Amber;      // #C8701E warning
	extern const FLinearColor Plum;       // #7A2E5A AI faction 3

	FLinearColor WithAlpha(const FLinearColor& Color, float Alpha);
	FLinearColor InkA(float Alpha);       // Ink with alpha (HTML --ink-70 / -55 / -30 / -12)
	FLinearColor PaperLA(float Alpha);    // PaperL with alpha (HTML --pl-70 / -50 / -25)
	/** Printed-ink tier colour. Tier 1..6 = I..VI; out of range is clamped. */
	FLinearColor TierColor(int32 Tier);
	/** Same by roman numeral ("I".."VI"); unknown text gives tier I. */
	FLinearColor TierColor(const FString& Roman);
	/** Name colour of AI faction 1/2/3 on paper (Red / Ochre / Plum); other values clamp. */
	FLinearColor AiFactionColor(int32 AiIndex);

	// ------------------------------------------------------------------ fonts (section 3.2)
	enum class EFontRole : uint8
	{
		SansBlack, SansBold, SansMedium, Serif, Cond, Mono, MonoBold, Stencil, Russo
	};

	/** HTML px to Slate pt (96 dpi): px * 0.75, then times the layout scale. */
	inline float Pt(float Px, float Scale = 1.0f) { return Px * 0.75f * Scale; }

	/**
	 * Font of a role at SizePt (already includes the layout scale, see Pt()). TrackingEm is the CSS letter-spacing in em
	 * (converted to Slate LetterSpacing units: Slate computes whole pixels (int16)(LetterSpacing * PaintScale * Size / 1000)
	 * with Size in points, while the CSS em is Size * 96/72 px; the result is the nearest whole pixel at GetPaintFontScale()).
	 * Built from /Game/Tread/UI/Fonts/FF_* composite fonts (Sans Bold as fallback typeface for CJK); falls back to the
	 * engine default font when an asset is missing.
	 */
	FSlateFontInfo Font(EFontRole Role, float SizePt, float TrackingEm = 0.0f);

	/** Largest size in [MinPt, MaxPt] that makes Value fit MaxWidth (local px); the font at MinPt if it never fits. */
	FSlateFontInfo FitFont(const FString& Value, EFontRole Role, float MaxPt, float MinPt, float MaxWidth, float TrackingEm = 0.0f);

	/**
	 * Scale Slate really rasterises text at: the widget's accumulated layout scale (viewport DPI scale times widget transform).
	 * Set it at the start of every OnPaint / NativePaint (GetAccumulatedLayoutTransform().GetScale()). Slate shapes glyphs at that
	 * scale with whole-pixel advances and letter spacing, so Font() (letter spacing) and TextSize() (width) must use it too;
	 * measuring at scale 1 comes out several percent narrower than what is drawn. Defaults to 1.
	 */
	void SetPaintFontScale(float Scale);
	float GetPaintFontScale();

	/**
	 * Measured size of Value in local px (estimated when no renderer exists). The width comes from the shaped glyph sequence at the
	 * paint font scale (see SetPaintFontScale), so it includes letter spacing, plus the trailing spacing like a CSS inline box.
	 * It is exactly the width Text() draws, so chained segments (X += TextSize(A).X) line up like consecutive CSS inline boxes;
	 * a single space between two segments is TextSize(" ").X (space advance plus tracking).
	 */
	FVector2f TextSize(const FString& Value, const FSlateFontInfo& FontInfo);

	/** Value shortened with an ellipsis until it fits MaxWidth (CSS text-overflow: ellipsis). */
	FString Ellipsize(const FString& Value, const FSlateFontInfo& FontInfo, float MaxWidth);

	// ------------------------------------------------------------------ texture brushes (section 3.3)
	enum class ETex : uint8
	{
		Paper, Grain, Vignette, Logo, Disc, DiscShade,
		StampApproved, StampCleared, StampReady, StampSortie,
		InkSplat, Giantess, GiantessInDisc, Hatch, Halftone, Scanlines,
		Count
	};

	/** Resident brush of /Game/Tread/UI/Style/T_UI_*. Never null: a missing texture yields a no-draw brush. */
	const FSlateBrush* Brush(ETex Which);
	/** True when the texture is loaded. */
	bool HasTex(ETex Which);
	/** Pixel size of the texture (0,0 when missing). */
	FVector2f TexSize(ETex Which);
	/** Loads every font and texture now (call from widget construction to avoid a hitch on the first paint). */
	void Preload();
	/** Real-time clock in seconds, unaffected by slomo / pause; use it for all UI animation. */
	double RealTime();
	/** FVector2D (e.g. the HUD's RefVec) to FVector2f. */
	inline FVector2f V2(const FVector2D& Value) { return FVector2f(static_cast<float>(Value.X), static_cast<float>(Value.Y)); }

	// ------------------------------------------------------------------ easing (copied from the HTML Ease object)
	namespace Ease
	{
		float OutExpo(float T);
		float OutCubic(float T);
		float InCubic(float T);
		float InOutCubic(float T);
		float InOutQuart(float T);
		/** CSS cubic-bezier(X1, Y1, X2, Y2) evaluated at progress T (0..1). */
		float CubicBezier(float X1, float Y1, float X2, float Y2, float T);
		float CssOut(float T);      // --e-out cubic-bezier(.16,1,.3,1)
		float CssInOut(float T);    // --e-io  cubic-bezier(.65,0,.35,1)
		float CssIn(float T);       // --e-in  cubic-bezier(.7,0,.84,0)
	}

	/** 0..1 OutExpo reveal of an element that starts at DelaySec and takes DurSec. */
	float Reveal(float ElapsedSec, float DelaySec, float DurSec);

	// ------------------------------------------------------------------ primitives (section 3.4)
	/** Flat rectangle (a WhiteBrush box). */
	void Quad(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer,
		const FVector2f& Pos, const FVector2f& Size, const FLinearColor& Color);

	/** Convex polygon (fan triangulated custom verts). Diagonal edges get a 1 px antialias fringe when opaque. */
	void Poly(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer,
		const TArray<FVector2f>& Points, const FLinearColor& Color, bool bAntiAlias = true);

	/** Rectangle rotated by RotationDeg (clockwise) around Pivot (normalised inside the rectangle). */
	void RotatedQuad(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer,
		const FVector2f& Pos, const FVector2f& Size, const FLinearColor& Color,
		float RotationDeg, const FVector2f& Pivot = FVector2f(0.5f, 0.5f));

	/** Hollow rectangle: four strips of Thickness px, drawn inside Pos/Size. */
	void Frame(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer,
		const FVector2f& Pos, const FVector2f& Size, const FLinearColor& Color, float Thickness);

	enum class ECorner : uint8
	{
		None = 0, TL = 1 << 0, TR = 1 << 1, BL = 1 << 2, BR = 1 << 3
	};
	ENUM_CLASS_FLAGS(ECorner);

	/**
	 * Rectangle with 45 degree cut corners (every flagged corner loses Cut px along each edge).
	 * With Border > 0 the border is drawn as a ring and the inner cut becomes Cut - 0.586 * Border.
	 */
	void CutBox(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer,
		const FVector2f& Pos, const FVector2f& Size, const FLinearColor& Fill, float Cut, ECorner Corner,
		float Border = 0.0f, const FLinearColor& BorderColor = Ink);

	/** CutBox preceded by a solid copy of itself offset by ShadowOffset (the prototype's 8 px hard ink shadow). */
	void HardShadowBox(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer,
		const FVector2f& Pos, const FVector2f& Size, const FLinearColor& Fill, float Cut, ECorner Corner,
		const FVector2f& ShadowOffset, float Border = 0.0f, const FLinearColor& BorderColor = Ink,
		const FLinearColor& ShadowColor = Ink);

	/** Texture multiplied by Tint, stretched to Size, rotated (clockwise degrees) and scaled around its centre. */
	void Tex(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, ETex Which,
		const FVector2f& Pos, const FVector2f& Size, const FLinearColor& Tint,
		float RotationDeg = 0.0f, float Scale = 1.0f);

	/** Tiled texture; one tile is the texture's pixel size times TileScale (local px). */
	void Tiled(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, ETex Which,
		const FVector2f& Pos, const FVector2f& Size, const FLinearColor& Tint, float TileScale = 1.0f);

	/**
	 * Text with its Pivot (0..1 inside the measured text box) placed at Pos, rotated clockwise by RotationDeg around it.
	 * Pivot (0,0) = Pos is the top-left corner, (0.5,0.5) = centred, (1,0) = right aligned.
	 * Single lines are drawn as shaped glyph sequences at the scale TextSize() measures them at, so the letter spacing of Font()
	 * really renders and the drawn width equals the measured one (the legacy FSlateDrawElement::MakeText path ignores LetterSpacing).
	 * Multi-line text (containing '\n') still goes through MakeText and renders without letter spacing.
	 */
	void Text(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FString& Value,
		const FSlateFontInfo& FontInfo, const FVector2f& Pos, const FLinearColor& Color,
		float RotationDeg = 0.0f, const FVector2f& Pivot = FVector2f::ZeroVector);

	/** Text with a hard drop shadow (offset in local px), for PaperL text over the 3D scene. Uses one layer. */
	void TextShadow(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FString& Value,
		const FSlateFontInfo& FontInfo, const FVector2f& Pos, const FLinearColor& Color,
		const FVector2f& ShadowOffset, const FLinearColor& ShadowColor,
		float RotationDeg = 0.0f, const FVector2f& Pivot = FVector2f::ZeroVector);

	/** Antialiased polyline. */
	void Lines(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer,
		const TArray<FVector2f>& Points, const FLinearColor& Color, float Thickness);
	/** Antialiased single segment. */
	void Line(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer,
		const FVector2f& A, const FVector2f& B, const FLinearColor& Color, float Thickness);
	/** Circle outline. */
	void Ring(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Center, float Radius,
		const FLinearColor& Color, float Thickness, int32 Segments = 120);
	/** Arc from StartDeg to EndDeg (canvas convention: 0 = +X, clockwise on screen). Segments counts a full circle. */
	void Arc(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Center, float Radius,
		float StartDeg, float EndDeg, const FLinearColor& Color, float Thickness, int32 Segments = 120);
	/** Count radial ticks from InnerR to OuterR spread over SweepDeg starting at PhaseDeg (full circle = no duplicate). */
	void Ticks(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Center,
		float InnerR, float OuterR, int32 Count, float PhaseDeg, const FLinearColor& Color, float Thickness,
		float SweepDeg = 360.0f);

	/**
	 * HTML DRAW.rings: hairline, rotating 120-tick ring, counter-rotating arcs, orbit marker, cardinal ticks, two
	 * expanding pulses, optional centre star and bearing label. Center/R/Spread are local px; the fixed offsets and line
	 * widths of the formula are design px times Scale. Speed in deg/s (negative reverses), Alpha is cfg.alpha.
	 */
	void SignalRings(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Center, float R,
		const FLinearColor& LineColor, const FLinearColor& Accent, double TimeSec, float Speed, float Alpha, float Spread,
		float Scale = 1.0f, bool bStar = false, bool bLabel = false);

	/** HTML DRAW.wave: baseline with ticks, two lagged waveform strokes and a sweeping accent blip. Amp in local px. */
	void Wave(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos, const FVector2f& Size,
		const FLinearColor& LineColor, const FLinearColor& Accent, double TimeSec, float Amp, float Scale = 1.0f);

	/**
	 * HTML DRAW.particles: Count drifting squares / crosses in Region (same seeded layout, stateless closed-form motion
	 * so it needs no per-frame state). Alpha is cfg.alpha.
	 */
	void Particles(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& RegionPos,
		const FVector2f& RegionSize, int32 Count, const FLinearColor& Color, float Alpha, double TimeSec, float Scale = 1.0f);

	/**
	 * Segmented progress bar (.pb): Count cells with Gap px between them; cells below Fraction are OnColor, the rest are
	 * OffColor with an OffBorderColor border. With TimeSec >= 0 the first unlit cell blinks in LeadColor (160 ms period).
	 */
	void SegBar(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos, const FVector2f& Size,
		int32 Count, float Fraction, const FLinearColor& OnColor, const FLinearColor& OffColor, float Border,
		float Gap = 4.0f, const FLinearColor& OffBorderColor = InkA(0.3f),
		double TimeSec = -1.0, const FLinearColor& LeadColor = Ink);

	/** Ruler (.ruler): 2 px base line, short tick every 20 design px, long tick every 100. Occupies 16 * Scale px of height. */
	void Ruler(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos, float Width,
		const FLinearColor& Color, float Scale = 1.0f);

	/** Row of level pips (.cai / .pips): filled pips are solid OnColor, the rest are OffColor outlines. */
	void Pips(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos, int32 Count,
		int32 Filled, const FLinearColor& OnColor, const FLinearColor& OffColor, const FVector2f& PipSize,
		float Border = 2.0f, float Gap = 3.0f);

	/** Duration of the stamp impact animation. */
	constexpr float StampDurationSec = 0.52f;
	/**
	 * Stamp impact: scale 2.2 -> 0.95 (45%) -> 1.025 (68%) -> 1 over StampDurationSec with the CSS easings, opacity
	 * 0 -> 1 over the first 45%. Draws nothing for negative ElapsedSec; holds the final state afterwards.
	 */
	void Stamp(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, ETex Which, const FVector2f& Center,
		const FVector2f& Size, const FLinearColor& Tint, float RotationDeg, float ElapsedSec);

	// ------------------------------------------------------------------ clipping
	/** Clip everything drawn until the matching PopClip to a local rectangle (intersects the current clip). */
	void PushClipRect(FSlateWindowElementList& Out, const FGeometry& Geo, const FVector2f& Pos, const FVector2f& Size);
	/** Clip to an arbitrary convex quad given in local space (stencil clipping when not axis aligned). */
	void PushClipQuad(FSlateWindowElementList& Out, const FGeometry& Geo, const FVector2f& TL, const FVector2f& TR,
		const FVector2f& BL, const FVector2f& BR);
	void PopClip(FSlateWindowElementList& Out);

	// ------------------------------------------------------------------ shared components (section 3.5)
	/** Paper panel: PaperL fill, 3 px ink border, 18 px top-left cut, optional 8 px ink shadow and grain. Layers Layer..Layer+1. */
	void PaperPanel(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos,
		const FVector2f& Size, bool bShadow, float Scale = 1.0f, bool bGrain = false);

	/** Ink panel: Ink at 94% opacity, 18 px top-left cut, no border. Layer only. */
	void InkPanel(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos,
		const FVector2f& Size, float Scale = 1.0f);

	/** Panel title bar: 46 px ink strip, title in Sans Black (PaperL) followed by RuTag in small Russo (RedL). Layers Layer..Layer+1. */
	void PanelHeader(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos, float Width,
		const FString& Title, const FString& RuTag, float Scale = 1.0f, bool bCutTopLeft = true);

	/** Optional look settings shared by the three button styles. */
	struct FButtonLook
	{
		float Scale = 1.0f;         // local px per design px
		float CutPx = -1.0f;        // bottom-right cut in design px; < 0 = style default (22 filled, 0 ghost)
		bool bCenter = false;       // centre the label (HUD) instead of left aligning it (front end)
		float LabelPx = 0.0f;       // label size in design px; 0 = derived from the button height
		float TrackingEm = 0.2f;    // label letter spacing
		float LabelLeftPx = -1.0f;  // left inset of a left-aligned label in design px; < 0 = 0.426 x height (CSS .btn .b-tx left 46 of 108)
		float GapPx = -1.0f;        // gap between label and Russian tag in design px; < 0 = 0.2 x height
		float RuPx = 0.0f;          // Russian tag size in design px; 0 = derived from LabelPx
		EFontRole RuRole = EFontRole::Russo; // tag face (a CJK tag reads as TSans in the prototype, the Russo fallback)
		float RuTrackingEm = -1.0f; // tag letter spacing; < 0 = style default
		FString Arrow;              // optional glyph on the right edge that slides 14 px on hover
		float ScanT = -1.0f;        // >= 0 draws the busy scan bars at that progress (0..1)
	};

	/** Red button, ink wipe from the left on hover. Disabled = PaperDD + hatch + Ink text (CSS .btn.off). Layers Layer..Layer+2. */
	void PrimaryButton(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos,
		const FVector2f& Size, const FString& Label, const FString& RuLabel, float HoverT, bool bEnabled,
		const FButtonLook& Look = FButtonLook());

	/** Ink button, red wipe on hover. Layers Layer..Layer+2. */
	void SecondaryButton(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos,
		const FVector2f& Size, const FString& Label, const FString& RuLabel, float HoverT, bool bEnabled,
		const FButtonLook& Look = FButtonLook());

	/** Ghost button: 2 px Tone border and label, red wipe on hover. Layers Layer..Layer+2. */
	void GhostButton(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos,
		const FVector2f& Size, const FString& Label, const FString& RuLabel, float HoverT, bool bEnabled,
		const FLinearColor& Tone, const FButtonLook& Look = FButtonLook());
}
