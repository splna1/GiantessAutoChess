#include "TreadFrontEndWidget.h"

#include "Blueprint/WidgetTree.h"
#include "Brushes/SlateColorBrush.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/EditableText.h"
#include "Components/NativeWidgetHost.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "EngineUtils.h"
#include "Framework/Application/SlateApplication.h"
#include "Input/CursorReply.h"
#include "Input/Events.h"
#include "InputCoreTypes.h"
#include "Layout/Clipping.h"
#include "Misc/DateTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Rendering/DrawElements.h"
#include "Rendering/RenderingCommon.h"
#include "Rendering/SlateRenderer.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Styling/CoreStyle.h"
#include "Styling/SlateBrush.h"
#include "TreadM1MatchController.h"
#include "TreadUIStyle.h"
#include "Widgets/SLeafWidget.h"

namespace TUI = TreadUI;

// ============================================================================================================
// Front end (doc 157 section 4). Everything is laid out in the 1920x1080 design space of Tools/ui_proto/tread_ui.src.html
// and scaled uniformly (letterboxed). Coordinates in the Draw* functions are design pixels unless stated otherwise.
// ============================================================================================================

namespace
{
	constexpr float DW = 1920.0f;
	constexpr float DH = 1080.0f;

	// TIMING object of the prototype (milliseconds).
	constexpr float TmLoadTotal = 3700.0f;
	constexpr float TmReadyHold = 650.0f;
	constexpr float TmScan = 950.0f;
	constexpr float TmSlab = 1150.0f;
	constexpr float TmBlinds = 620.0f;
	constexpr float TmLoginScan = 700.0f;
	constexpr float TmLoginStamp = 720.0f;
	constexpr float TmLoginGreet = 900.0f;
	constexpr float TmLoginLeave = 2050.0f;
	constexpr float TmSortieDeploy = 2600.0f;

	float Sat(float V) { return FMath::Clamp(V, 0.0f, 1.0f); }
	FString Pad2(int32 V) { return FString::Printf(TEXT("%02d"), V); }
	FString Signed(int32 V)
	{
		if (V > 0) return FString::Printf(TEXT("+%d"), V);
		if (V < 0) return FString::Printf(TEXT("−%d"), -V);
		return FString(TEXT("±") TEXT("0"));
	}

	FVector2f RotAbout(const FVector2f& Pt, const FVector2f& Pivot, float Deg)
	{
		const float Rad = FMath::DegreesToRadians(Deg);
		const float C = FMath::Cos(Rad), S = FMath::Sin(Rad);
		const FVector2f D = Pt - Pivot;
		return Pivot + FVector2f(D.X * C - D.Y * S, D.X * S + D.Y * C);
	}

	/** CSS `steps(1)` blink (opacity 1 for the first half of the period, 0 for the second). */
	bool BlinkOn(double Now, double PeriodSec) { return FMath::Fmod(Now, PeriodSec) < PeriodSec * 0.5; }
	/** Blink that stays lit most of the time (REC dot), so a still capture rarely catches it dark. */
	bool BlinkMostlyOn(double Now, double PeriodSec) { return FMath::Fmod(Now, PeriodSec) < PeriodSec * 0.7; }

	/** Progress keys of the loading bar (HTML PKEYS) with the same smoothstep between keys. */
	float ProgAt(float TMs)
	{
		static const float Keys[10][2] = {
			{ 0, 0.0f }, { 380, 0.05f }, { 900, 0.2f }, { 1250, 0.33f }, { 1700, 0.36f },
			{ 2150, 0.57f }, { 2500, 0.7f }, { 2850, 0.72f }, { 3300, 0.9f }, { 3700, 1.0f } };
		if (TMs >= Keys[9][0]) return 1.0f;
		for (int32 Index = 1; Index < 10; ++Index)
		{
			if (TMs <= Keys[Index][0])
			{
				const float K = (TMs - Keys[Index - 1][0]) / (Keys[Index][0] - Keys[Index - 1][0]);
				return Keys[Index - 1][1] + (Keys[Index][1] - Keys[Index - 1][1]) * (K * K * (3.0f - 2.0f * K));
			}
		}
		return 1.0f;
	}

	/** Terminal log lines of the loading screen (HTML LOG). Bold is the red bold head of the line, if any. */
	struct FLogRow { int32 Ms; const TCHAR* Bold; const TCHAR* Text; const TCHAR* Status; };
	const FLogRow LogRows[] = {
		{ 0, TEXT(""), TEXT("ТРЕАД//BOOT 行军档案终端 v0.5.14"), TEXT("") },
		{ 170, TEXT(""), TEXT("挂载 档案库 /archive/tread"), TEXT("OK") },
		{ 390, TEXT(""), TEXT("校验 名册 112 / 112 · VRM 100 · MMD 12"), TEXT("OK") },
		{ 640, TEXT(""), TEXT("载入 盟约 23 · 特质 126"), TEXT("OK") },
		{ 860, TEXT(""), TEXT("载入 策略 40 · 禁用 4"), TEXT("OK") },
		{ 1060, TEXT(""), TEXT("编目 装备 56 · 法术 3"), TEXT("OK") },
		{ 1290, TEXT(""), TEXT("同步 十六国战役 16 / 16"), TEXT("OK") },
		{ 1530, TEXT(""), TEXT("编译 着色器 3267 / 3267"), TEXT("OK") },
		{ 1780, TEXT(""), TEXT("重定向 动作 33 段 × 112 名"), TEXT("OK") },
		{ 2020, TEXT(""), TEXT("预热 棋盘网格 8×8 · 巴黎"), TEXT("OK") },
		{ 2260, TEXT(""), TEXT("检定 确定性随机 SEED 20260926"), TEXT("OK") },
		{ 2480, TEXT("显存"), TEXT(" 6.1 / 8.0 GB · 余量偏低"), TEXT("WARN") },
		{ 2720, TEXT(""), TEXT("校准 观众镜头 · 演出时间轴"), TEXT("OK") },
		{ 2960, TEXT(""), TEXT("唤醒 巨人 · 心跳 72 bpm"), TEXT("OK") },
		{ 3200, TEXT(""), TEXT("装订 宣传画 Л.01 – Л.04"), TEXT("OK") },
		{ 3420, TEXT(""), TEXT("校对 套印 · 红 / 黑 两色"), TEXT("OK") },
		{ 3640, TEXT(""), TEXT("一切就绪。前进！ ВПЕРЁД!"), TEXT("★") },
	};
	constexpr int32 LogRowCount = UE_ARRAY_COUNT(LogRows);

	// Five pointed star outlines (outer radius 100 and 48 units): index 0 is the top point.
	const FVector2f StarBig[10] = {
		FVector2f(0.0f, -100.0f), FVector2f(23.5f, -32.4f), FVector2f(95.1f, -30.9f), FVector2f(38.0f, 12.3f), FVector2f(58.8f, 80.9f),
		FVector2f(0.0f, 40.0f), FVector2f(-58.8f, 80.9f), FVector2f(-38.0f, 12.3f), FVector2f(-95.1f, -30.9f), FVector2f(-23.5f, -32.4f) };
	const FVector2f StarSmall[10] = {
		FVector2f(0.0f, -48.0f), FVector2f(11.3f, -15.5f), FVector2f(45.6f, -14.8f), FVector2f(18.3f, 5.9f), FVector2f(28.2f, 38.8f),
		FVector2f(0.0f, 19.2f), FVector2f(-28.2f, 38.8f), FVector2f(-18.3f, 5.9f), FVector2f(-45.6f, -14.8f), FVector2f(-11.3f, -15.5f) };

	/** Accumulates rectangles (optionally vertically graded) and submits them as one custom-verts element. */
	struct FRectBatch
	{
		explicit FRectBatch(const FGeometry& InGeo) : Transform(InGeo.GetAccumulatedRenderTransform()) {}

		FSlateRenderTransform Transform;
		TArray<FSlateVertex> Verts;
		TArray<SlateIndex> Indices;

		SlateIndex AddVert(const FVector2f& Point, const FColor& Color)
		{
			Verts.Add(FSlateVertex::Make<ESlateVertexRounding::Disabled>(Transform, Point, FVector2f::ZeroVector, Color));
			return static_cast<SlateIndex>(Verts.Num() - 1);
		}

		void Rect(const FVector2f& Pos, const FVector2f& Size, const FLinearColor& Color)
		{
			GradRect(Pos, Size, Color, Color);
		}

		void GradRect(const FVector2f& Pos, const FVector2f& Size, const FLinearColor& Top, const FLinearColor& Bottom)
		{
			if (Size.X <= 0.0f || Size.Y <= 0.0f || (Top.A <= 0.0f && Bottom.A <= 0.0f)) return;
			const FColor CTop = Top.ToFColor(true), CBottom = Bottom.ToFColor(true);
			const SlateIndex A = AddVert(Pos, CTop);
			const SlateIndex B = AddVert(FVector2f(Pos.X + Size.X, Pos.Y), CTop);
			const SlateIndex C = AddVert(Pos + Size, CBottom);
			const SlateIndex D = AddVert(FVector2f(Pos.X, Pos.Y + Size.Y), CBottom);
			Indices.Add(A); Indices.Add(B); Indices.Add(C);
			Indices.Add(A); Indices.Add(C); Indices.Add(D);
		}

		void Flush(FSlateWindowElementList& Out, int32 Layer)
		{
			if (Indices.Num() < 3) return;
			if (FSlateApplication::IsInitialized())
			{
				if (FSlateRenderer* Renderer = FSlateApplication::Get().GetRenderer())
				{
					const FSlateBrush* White = FCoreStyle::Get().GetBrush(TEXT("WhiteBrush"));
					if (White)
					{
						const FSlateResourceHandle Handle = Renderer->GetResourceHandle(*White);
						FSlateDrawElement::MakeCustomVerts(Out, static_cast<uint32>(Layer), Handle, Verts, Indices, nullptr, 0, 0);
					}
				}
			}
			Verts.Reset();
			Indices.Reset();
		}
	};
}

// ------------------------------------------------------------------------------------------------------------
// Paint helpers (global names so the header can forward declare them).
// ------------------------------------------------------------------------------------------------------------

/** Design-space painter: design px -> local px through a transform stack (uniform scale + translation + group alpha). */
struct FFrontPaint
{
	FSlateWindowElementList& Out;
	const FGeometry& Geo;
	float K;          // local px per design px (current transform)
	FVector2f B;      // local position of design (0,0)
	float A = 1.0f;   // group alpha
	int32 Layer;      // highest layer handed out so far

	struct FState { float K; FVector2f B; float A; };
	TArray<FState, TInlineAllocator<8>> Stack;

	FFrontPaint(FSlateWindowElementList& InOut, const FGeometry& InGeo, int32 InLayer, float InK, const FVector2f& InB)
		: Out(InOut), Geo(InGeo), K(InK), B(InB), Layer(InLayer) {}

	/** A fresh layer above everything drawn so far (slate draws one layer by element type, not by call order). */
	int32 L() { return ++Layer; }
	/** Count consecutive fresh layers; returns the first. */
	int32 Reserve(int32 Count) { const int32 First = Layer + 1; Layer += Count; return First; }

	/** Scale about Pivot (design px), then translate by Offset (design px), then multiply the group alpha. */
	void Push(float Scale, const FVector2f& Pivot, const FVector2f& Offset, float AlphaMul)
	{
		Stack.Add(FState{ K, B, A });
		B += (Pivot * (1.0f - Scale) + Offset) * K;
		K *= Scale;
		A *= AlphaMul;
	}
	void Pop()
	{
		const FState S = Stack.Pop();
		K = S.K; B = S.B; A = S.A;
	}

	FVector2f Pt(float X, float Y) const { return B + FVector2f(X, Y) * K; }
	FVector2f Sz(float W, float H) const { return FVector2f(W, H) * K; }
	FLinearColor Col(const FLinearColor& C, float Mul = 1.0f) const { return FLinearColor(C.R, C.G, C.B, C.A * A * Mul); }

	void Box(int32 Lyr, float X, float Y, float W, float H, const FLinearColor& C)
	{
		TUI::Quad(Out, Geo, Lyr, Pt(X, Y), Sz(W, H), Col(C));
	}

	void Poly(int32 Lyr, std::initializer_list<FVector2f> Pts, const FLinearColor& C, bool bAntiAlias = true)
	{
		TArray<FVector2f> Local;
		Local.Reserve(static_cast<int32>(Pts.size()));
		for (const FVector2f& V : Pts) Local.Add(Pt(V.X, V.Y));
		TUI::Poly(Out, Geo, Lyr, Local, Col(C), bAntiAlias);
	}

	void PolyArr(int32 Lyr, const TArray<FVector2f>& DesignPts, const FLinearColor& C, bool bAntiAlias = true)
	{
		TArray<FVector2f> Local;
		Local.Reserve(DesignPts.Num());
		for (const FVector2f& V : DesignPts) Local.Add(Pt(V.X, V.Y));
		TUI::Poly(Out, Geo, Lyr, Local, Col(C), bAntiAlias);
	}

	/** Filled five pointed star (fan from the centre; the outline is stroked for smooth edges). */
	void Star(int32 Lyr, const FVector2f* Outline, const FVector2f& Center, float Scale, float RotDeg, const FLinearColor& C)
	{
		TArray<FVector2f> Fan;
		Fan.Add(Pt(Center.X, Center.Y));
		TArray<FVector2f> Ring;
		for (int32 Index = 0; Index <= 10; ++Index)
		{
			const FVector2f Rot = RotAbout(Outline[Index % 10] * Scale, FVector2f::ZeroVector, RotDeg);
			const FVector2f Local = Pt(Center.X + Rot.X, Center.Y + Rot.Y);
			Fan.Add(Local);
			Ring.Add(Local);
		}
		TUI::Poly(Out, Geo, Lyr, Fan, Col(C), false);
		TUI::Lines(Out, Geo, Lyr, Ring, Col(C), 1.0f);
	}

	void Circle(int32 Lyr, float Cx, float Cy, float Radius, const FLinearColor& C)
	{
		TArray<FVector2f> Pts;
		for (int32 Index = 0; Index < 20; ++Index)
		{
			const float Rad = Index * 2.0f * PI / 20.0f;
			Pts.Add(Pt(Cx + FMath::Cos(Rad) * Radius, Cy + FMath::Sin(Rad) * Radius));
		}
		TUI::Poly(Out, Geo, Lyr, Pts, Col(C), false);
	}

	void CutBox(int32 Lyr, float X, float Y, float W, float H, const FLinearColor& Fill, float Cut, TUI::ECorner Corner,
		float Border = 0.0f, const FLinearColor& BorderCol = TUI::Ink)
	{
		TUI::CutBox(Out, Geo, Lyr, Pt(X, Y), Sz(W, H), Col(Fill), Cut * K, Corner, Border * K, Col(BorderCol));
	}

	void Frame(int32 Lyr, float X, float Y, float W, float H, const FLinearColor& C, float Thickness)
	{
		TUI::Frame(Out, Geo, Lyr, Pt(X, Y), Sz(W, H), Col(C), Thickness * K);
	}

	void RotBox(int32 Lyr, float X, float Y, float W, float H, const FVector2f& PivotDesign, float Deg, const FLinearColor& C)
	{
		const FVector2f Pivot((PivotDesign.X - X) / W, (PivotDesign.Y - Y) / H);
		TUI::RotatedQuad(Out, Geo, Lyr, Pt(X, Y), Sz(W, H), Col(C), Deg, Pivot);
	}

	void Tex(int32 Lyr, TUI::ETex Which, float X, float Y, float W, float H, const FLinearColor& Tint, float RotDeg = 0.0f, float Scale = 1.0f)
	{
		TUI::Tex(Out, Geo, Lyr, Which, Pt(X, Y), Sz(W, H), Col(Tint), RotDeg, Scale);
	}

	/** Tiled texture; TilePx is the size of one tile in design px. */
	void Tiled(int32 Lyr, TUI::ETex Which, float X, float Y, float W, float H, const FLinearColor& Tint, float TilePx)
	{
		const FVector2f TexPx = TUI::TexSize(Which);
		if (TexPx.X <= 0.0f) return;
		TUI::Tiled(Out, Geo, Lyr, Which, Pt(X, Y), Sz(W, H), Col(Tint), TilePx * K / TexPx.X);
	}

	FSlateFontInfo FontFor(TUI::EFontRole Role, float Px, float Track = 0.0f) const
	{
		return TUI::Font(Role, TUI::Pt(Px, K), Track);
	}

	/** Text anchored at (X, Cy): Cy is the vertical centre of the CSS line box, PivX 0 = left, 0.5 = centred, 1 = right. */
	void Text(int32 Lyr, const FString& S, TUI::EFontRole Role, float Px, float X, float Cy, const FLinearColor& C,
		float Track = 0.0f, float PivX = 0.0f, float RotDeg = 0.0f)
	{
		if (S.IsEmpty()) return;
		TUI::Text(Out, Geo, Lyr, S, FontFor(Role, Px, Track), Pt(X, Cy), Col(C), RotDeg, FVector2f(PivX, 0.5f));
	}

	/** Width of S in the current design space. */
	float TextW(const FString& S, TUI::EFontRole Role, float Px, float Track = 0.0f) const
	{
		if (S.IsEmpty() || K <= 0.0f) return 0.0f;
		return TUI::TextSize(S, FontFor(Role, Px, Track)).X / K;
	}

	/** One CSS space between two inline segments: the space advance plus the letter spacing that follows it. */
	float SpaceW(TUI::EFontRole Role, float Px, float Track = 0.0f) const
	{
		return TextW(TEXT(" "), Role, Px, Track);
	}

	/**
	 * Thickness of a hairline rule in design px, never thinner than one screen pixel. Below 1:1 a 1 px rect covers no pixel
	 * centre on some rows and vanishes (every other log rule went missing at 0.55); the browser always keeps one device pixel.
	 */
	float Hair(float DesignPx = 1.0f) const
	{
		return FMath::Max(DesignPx, 1.0f / FMath::Max(K * TUI::GetPaintFontScale(), 0.01f));
	}

	void ClipRect(float X, float Y, float W, float H)
	{
		TUI::PushClipRect(Out, Geo, Pt(X, Y), Sz(FMath::Max(W, 0.0f), FMath::Max(H, 0.0f)));
	}
	void ClipQuad(const FVector2f& TL, const FVector2f& TR, const FVector2f& BL, const FVector2f& BR)
	{
		TUI::PushClipQuad(Out, Geo, Pt(TL.X, TL.Y), Pt(TR.X, TR.Y), Pt(BL.X, BL.Y), Pt(BR.X, BR.Y));
	}
	void PopClip() { TUI::PopClip(Out); }
};

/** Per-screen timing: when the screen was entered and how its entrance animations are staggered. */
struct FFrontEnv
{
	double Now = 0.0;
	double T0 = 0.0;
	float ScanMs = 0.0f;      // > 0 when the screen is revealed by the scan transition (delays follow the scan line)
	bool bFinal = false;      // test hooks: all entrance animations at their final state
	float ElapsedMs() const { return bFinal ? 1.0e7f : static_cast<float>((Now - T0) * 1000.0); }
};

enum class EFrontIn : uint8 { Fade, Up, Down, Left, Right, Scale, Wipe, WipeL, WipeV };

/** Entrance animation of one data-in element (HTML [data-in]): applies transform / alpha / clip until it goes out of scope. */
struct FFrontIn
{
	FFrontPaint& P;
	bool bXf = false;
	bool bClip = false;
	bool bShown = true;
	float Alpha = 1.0f;

	FFrontIn(FFrontPaint& InP, const FFrontEnv& Env, EFrontIn Type, float DelayMs, float DurMs, float X, float Y, float W, float H)
		: P(InP)
	{
		float Delay = DelayMs;
		if (Env.ScanMs > 0.0f) Delay = FMath::Clamp(Y, 0.0f, DH) / DH * Env.ScanMs * 0.8f + Delay * 0.35f;
		const float E = Env.ElapsedMs() - Delay;
		const float DurO = DurMs > 0.0f ? DurMs : 560.0f;
		const float DurT = DurMs > 0.0f ? DurMs : 720.0f;
		const float PO = TUI::Ease::CssOut(Sat(E / DurO));
		const float PT = TUI::Ease::CssOut(Sat(E / DurT));
		FVector2f Offset = FVector2f::ZeroVector;
		float Scale = 1.0f;
		Alpha = PO;
		FVector2f ClipPos(0.0f, 0.0f), ClipSize(0.0f, 0.0f);
		switch (Type)
		{
		case EFrontIn::Fade: break;
		case EFrontIn::Up: Offset.Y = 30.0f * (1.0f - PT); break;
		case EFrontIn::Down: Offset.Y = -30.0f * (1.0f - PT); break;
		case EFrontIn::Left: Offset.X = -56.0f * (1.0f - PT); break;
		case EFrontIn::Right: Offset.X = 56.0f * (1.0f - PT); break;
		case EFrontIn::Scale: Scale = 0.9f + 0.1f * PT; break;
		case EFrontIn::Wipe:
			Alpha = PT > 0.0005f ? 1.0f : 0.0f;
			bClip = true; ClipPos = FVector2f(X - 80.0f, Y - 80.0f); ClipSize = FVector2f(PT * (W + 80.0f) + 80.0f, H + 160.0f);
			break;
		case EFrontIn::WipeL:
			Alpha = PT > 0.0005f ? 1.0f : 0.0f;
			bClip = true; ClipPos = FVector2f(X + W - PT * (W + 80.0f), Y - 80.0f); ClipSize = FVector2f(PT * (W + 80.0f) + 80.0f, H + 160.0f);
			break;
		case EFrontIn::WipeV:
			Alpha = PT > 0.0005f ? 1.0f : 0.0f;
			bClip = true; ClipPos = FVector2f(X - 80.0f, Y - 80.0f); ClipSize = FVector2f(W + 160.0f, PT * (H + 80.0f) + 80.0f);
			break;
		}
		bShown = Alpha > 0.002f;
		if (!bShown) { bClip = false; return; }
		if (Type != EFrontIn::Wipe && Type != EFrontIn::WipeL && Type != EFrontIn::WipeV)
		{
			P.Push(Scale, FVector2f(X + W * 0.5f, Y + H * 0.5f), Offset, Alpha);
			bXf = true;
		}
		if (bClip) P.ClipRect(ClipPos.X, ClipPos.Y, ClipSize.X, ClipSize.Y);
	}

	~FFrontIn()
	{
		if (bClip) P.PopClip();
		if (bXf) P.Pop();
	}
};

/** Seconds since a stamp-type entrance started (negative before it). */
static float StampSec(const FFrontEnv& Env, float DelayMs)
{
	return (Env.ElapsedMs() - DelayMs) / 1000.0f;
}

// ------------------------------------------------------------------------------------------------------------
// Slate child that hosts the custom painting. It sits at z-order 0 of the root canvas so the two real text boxes
// (z-order 1) are drawn above it.
// ------------------------------------------------------------------------------------------------------------
class STreadFrontEndPaint : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(STreadFrontEndPaint) {}
		SLATE_ARGUMENT(TWeakObjectPtr<UTreadFrontEndWidget>, Owner)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs)
	{
		Owner = InArgs._Owner;
		SetVisibility(EVisibility::HitTestInvisible);
		// Everything animates every frame: never let Slate cache this widget's draw elements.
		ForceVolatile(true);
	}

	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
		FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override
	{
		if (const UTreadFrontEndWidget* Widget = Owner.Get())
		{
			return Widget->PaintFrontEnd(AllottedGeometry, OutDrawElements, LayerId);
		}
		return LayerId;
	}

	virtual FVector2D ComputeDesiredSize(float) const override { return FVector2D::ZeroVector; }

private:
	TWeakObjectPtr<UTreadFrontEndWidget> Owner;
};

namespace
{
	// Hit rectangles of the clickable things, in design px (they equal the drawn rectangles).
	struct FRectD { float X, Y, W, H; bool Contains(const FVector2f& P) const { return P.X >= X && P.Y >= Y && P.X < X + W && P.Y < Y + H; } };
	const FRectD RcLoginBtn = { 1180.0f, 762.0f, 620.0f, 108.0f };
	const FRectD RcField[2] = { { 1180.0f, 462.0f, 620.0f, 76.0f }, { 1180.0f, 600.0f, 620.0f, 76.0f } };
	const FRectD RcLogout = { 1676.0f, 96.0f, 150.0f, 74.0f };
	const FRectD RcGoBtn = { 1317.0f, 900.0f, 506.0f, 88.0f };
	// Free match ghost button: lives in the bottom strip, right of the (shortened, ends at x=680) signal wave and left of the tilted
	// "踏平十六国!" stamp text (design y 885..1000), not in the dossier panel. Hit area and drawing both use this rectangle.
	const FRectD RcFreeBtn = { 700.0f, 1000.0f, 260.0f, 50.0f };
	const FRectD RcBackBtn = { 640.0f, 862.0f, 210.0f, 84.0f };

	/** Card slot (design px): rows are staggered by 60 px, x = 96 + (3 - row) * 60 + col * 252, y = 250 + row * 188. */
	FVector2f CardSlot(int32 Index)
	{
		const int32 Row = Index / 4, Col = Index % 4;
		return FVector2f(96.0f + (3 - Row) * 60.0f + Col * 252.0f, 250.0f + Row * 188.0f);
	}
	/** Hover target of a card: the union of its resting and its raised position, so the pointer never flickers on the edge. */
	FRectD CardHit(int32 Index)
	{
		const FVector2f S = CardSlot(Index);
		return FRectD{ S.X - 4.0f, S.Y - 7.0f, 240.0f, 175.0f };
	}
}

// ------------------------------------------------------------------------------------------------------------
// Lifecycle
// ------------------------------------------------------------------------------------------------------------
UTreadFrontEndWidget::UTreadFrontEndWidget(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	SetIsFocusable(false);
}

ATreadM1MatchController* UTreadFrontEndWidget::FindController() const
{
	if (!GetWorld()) return nullptr;
	for (TActorIterator<ATreadM1MatchController> It(GetWorld()); It; ++It) return *It;
	return nullptr;
}

UEditableText* UTreadFrontEndWidget::MakeInputText(const TCHAR* Name, bool bPassword, int32 ZOrder)
{
	UEditableText* Text = WidgetTree->ConstructWidget<UEditableText>(UEditableText::StaticClass(), FName(Name));
	Text->SetIsPassword(bPassword);
	Text->SetClearKeyboardFocusOnCommit(false);
	Text->SetVisibility(ESlateVisibility::Collapsed);
	if (UCanvasPanelSlot* CanvasSlot = RootCanvas->AddChildToCanvas(Text))
	{
		CanvasSlot->SetAnchors(FAnchors(0.0f, 0.0f));
		CanvasSlot->SetAlignment(FVector2D::ZeroVector);
		CanvasSlot->SetPosition(FVector2D::ZeroVector);
		CanvasSlot->SetSize(FVector2D(300.0, 40.0));
		CanvasSlot->SetZOrder(ZOrder);
	}
	return Text;
}

TSharedRef<SWidget> UTreadFrontEndWidget::RebuildWidget()
{
	if (WidgetTree)
	{
		RootCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("FrontEndCanvas"));
		WidgetTree->RootWidget = RootCanvas;
		RootCanvas->SetVisibility(ESlateVisibility::SelfHitTestInvisible);

		TSharedPtr<STreadFrontEndPaint> Paint;
		SAssignNew(Paint, STreadFrontEndPaint).Owner(this);
		PaintWidget = Paint;
		PaintHost = WidgetTree->ConstructWidget<UNativeWidgetHost>(UNativeWidgetHost::StaticClass(), TEXT("FrontEndPaintHost"));
		PaintHost->SetContent(Paint.ToSharedRef());
		PaintHost->SetVisibility(ESlateVisibility::HitTestInvisible);
		if (UCanvasPanelSlot* HostSlot = RootCanvas->AddChildToCanvas(PaintHost))
		{
			HostSlot->SetAnchors(FAnchors(0.0f, 0.0f, 1.0f, 1.0f));
			HostSlot->SetOffsets(FMargin(0.0f));
			HostSlot->SetZOrder(0);
		}

		CallsignText = MakeInputText(TEXT("FrontEndCallsign"), false, 1);
		PasswordText = MakeInputText(TEXT("FrontEndPassword"), true, 2);
		CallsignText->OnTextChanged.AddDynamic(this, &UTreadFrontEndWidget::HandleCallsignChanged);
		CallsignText->OnTextCommitted.AddDynamic(this, &UTreadFrontEndWidget::HandleInputCommitted);
		PasswordText->OnTextChanged.AddDynamic(this, &UTreadFrontEndWidget::HandlePasswordChanged);
		PasswordText->OnTextCommitted.AddDynamic(this, &UTreadFrontEndWidget::HandleInputCommitted);
		LastFontScale = -1.0f;
	}
	return Super::RebuildWidget();
}

void UTreadFrontEndWidget::ReleaseSlateResources(bool bReleaseChildren)
{
	PaintWidget.Reset();
	Super::ReleaseSlateResources(bReleaseChildren);
}

void UTreadFrontEndWidget::NativeConstruct()
{
	Super::NativeConstruct();
	// Load fonts and textures now instead of hitching on the first paint.
	TUI::Preload();
	Controller = FindController();
	BindController();
	bShownNow = false;
	SetVisibility(ESlateVisibility::Collapsed);
	SyncVisibility();
}

void UTreadFrontEndWidget::NativeDestruct()
{
	if (Controller.IsValid())
	{
		Controller->OnPhaseChanged.RemoveDynamic(this, &UTreadFrontEndWidget::HandlePhaseChanged);
		Controller->OnStateChanged.RemoveDynamic(this, &UTreadFrontEndWidget::HandleStateChanged);
	}
	Super::NativeDestruct();
}

void UTreadFrontEndWidget::HandlePhaseChanged(ETreadM1Phase PreviousPhase, ETreadM1Phase NewPhase)
{
	SyncVisibility();
}

void UTreadFrontEndWidget::HandleStateChanged()
{
	SyncVisibility();
}

void UTreadFrontEndWidget::HandleCallsignChanged(const FText& Text)
{
	FString Value = Text.ToString();
	if (Value.Len() > 16)
	{
		CallsignText->SetText(FText::FromString(Value.Left(16)));
		return;
	}
	CallsignValue = Value;
}

void UTreadFrontEndWidget::HandlePasswordChanged(const FText& Text)
{
	const FString Value = Text.ToString();
	if (Value.Len() > 24)
	{
		PasswordText->SetText(FText::FromString(Value.Left(24)));
		return;
	}
	PasswordLen = Value.Len();
}

void UTreadFrontEndWidget::HandleInputCommitted(const FText& Text, ETextCommit::Type CommitMethod)
{
	if (CommitMethod == ETextCommit::OnEnter) DoLogin();
}

// ------------------------------------------------------------------------------------------------------------
// Visibility: the front end covers the game only in the R0 briefing (and while its own exit transition runs).
// ------------------------------------------------------------------------------------------------------------
bool UTreadFrontEndWidget::WantsVisible() const
{
	if (bExitRunning) return true;
	if (!Controller.IsValid()) return true;
	const ETreadM1Phase Phase = Controller->GetPhase();
	return Phase == ETreadM1Phase::MainMenu || Phase == ETreadM1Phase::R0Briefing;
}

void UTreadFrontEndWidget::SyncVisibility()
{
	const bool bWant = WantsVisible();
	if (bWant && !bShownNow) ShowFrontEnd();
	else if (!bWant && bShownNow) HideFrontEnd();
}

void UTreadFrontEndWidget::ResetFlow()
{
	Trans = FFrontTrans();
	bChromeHold = false;
	for (FFrontScreenRt& Rt : Scr) Rt = FFrontScreenRt();
	Current = EFrontScreen::None;
	LoadGoAt = -1.0;
	SortieGoAt = -1.0;
	SortieStampT = -1.0;
	SwapStartT = -1.0;
	ForcedHover = 0;
	HoverCardMouse = 0;
	EffHover = 0;
	TipStage = 0;
	TipHideT = -1.0;
	TipShowT = -1.0;
	LoginPhase = EFrontLogin::Idle;
	bLaunchStarted = false;
}

void UTreadFrontEndWidget::ShowFrontEnd()
{
	bShownNow = true;
	bExitRunning = false;
	ResetFlow();
	SetVisibility(ESlateVisibility::Visible);
	LastTick = TUI::RealTime();
	RefreshStages();
	if (!bLoggedIn)
	{
		// First entry: loading -> (scan) login -> (slab) select.
		Current = EFrontScreen::Loading;
		EnterScreen(EFrontScreen::Loading, 0.0f, false);
	}
	else
	{
		// Back from a match: slab straight into the campaign map.
		StartTransition(EFrontTrans::Slab, EFrontScreen::Select, 1.0f, TEXT("十六国战役"), TEXT("КАМПАНИЯ · Л.03"), false);
	}
}

void UTreadFrontEndWidget::HideFrontEnd()
{
	const bool bHadFocus = (CallsignText && CallsignText->HasKeyboardFocus()) || (PasswordText && PasswordText->HasKeyboardFocus());
	bShownNow = false;
	bExitRunning = false;
	ResetFlow();
	if (CallsignText) CallsignText->SetVisibility(ESlateVisibility::Collapsed);
	if (PasswordText) PasswordText->SetVisibility(ESlateVisibility::Collapsed);
	SetVisibility(ESlateVisibility::Collapsed);
	if (bHadFocus && FSlateApplication::IsInitialized()) FSlateApplication::Get().SetAllUserFocusToGameViewport();
}

// ------------------------------------------------------------------------------------------------------------
// Screens
// ------------------------------------------------------------------------------------------------------------
void UTreadFrontEndWidget::SetChromeTargets(EFrontScreen S, bool bHeld)
{
	// HTML chromeFor(ct, cb, held): data-ct / data-cb of each screen decide the paper-or-ink text colours.
	bool bTopPaper = false, bBottomPaper = false;
	switch (S)
	{
	case EFrontScreen::Loading: bTopPaper = true; bBottomPaper = false; break;
	case EFrontScreen::Login: bTopPaper = false; bBottomPaper = true; break;
	case EFrontScreen::Select: bTopPaper = false; bBottomPaper = false; break;
	case EFrontScreen::Sortie: bTopPaper = true; bBottomPaper = true; break;
	default: break;
	}
	if (bHeld) { bTopPaper = true; bBottomPaper = true; }
	ChromeTopTarget = bTopPaper ? TUI::PaperL : TUI::Ink;
	ChromeBottomTarget = bBottomPaper ? TUI::PaperL : TUI::Ink;
	ChromeAccentTarget = bHeld ? TUI::PaperL : (bTopPaper ? TUI::RedHi : TUI::Red);
}

void UTreadFrontEndWidget::EnterScreen(EFrontScreen S, float ScanMs, bool bFinal)
{
	FFrontScreenRt& Rt = Scr[static_cast<int32>(S)];
	Rt.bOn = true;
	Rt.T0 = TUI::RealTime();
	Rt.ScanMs = ScanMs;
	Rt.bFinal = bFinal;
	SheetNo = static_cast<int32>(S);
	if (!bChromeHold) SetChromeTargets(S, false);
	switch (S)
	{
	case EFrontScreen::Loading: BeginLoading(); break;
	case EFrontScreen::Login: BeginLogin(); break;
	case EFrontScreen::Select: BeginSelect(); break;
	case EFrontScreen::Sortie: BeginSortie(); break;
	default: break;
	}
}

void UTreadFrontEndWidget::LeaveScreen(EFrontScreen S)
{
	if (S == EFrontScreen::None) return;
	Scr[static_cast<int32>(S)].bOn = false;
}

FFrontEnv UTreadFrontEndWidget::EnvFor(EFrontScreen S, double Now) const
{
	const FFrontScreenRt& Rt = Scr[static_cast<int32>(S)];
	FFrontEnv Env;
	Env.Now = Now;
	Env.T0 = Rt.T0;
	Env.ScanMs = Rt.ScanMs;
	Env.bFinal = Rt.bFinal;
	return Env;
}

FString UTreadFrontEndWidget::GetScreenName() const
{
	if (!bShownNow) return TEXT("hidden");
	EFrontScreen S = Current;
	if (S == EFrontScreen::None)
	{
		// Mid first transition / launch: report whichever screen is on.
		for (int32 Index = 4; Index >= 1; --Index)
		{
			if (Scr[Index].bOn) { S = static_cast<EFrontScreen>(Index); break; }
		}
	}
	switch (S)
	{
	case EFrontScreen::Loading: return TEXT("loading");
	case EFrontScreen::Login: return TEXT("login");
	case EFrontScreen::Select: return TEXT("select");
	case EFrontScreen::Sortie: return TEXT("sortie");
	default: return TEXT("none");
	}
}

void UTreadFrontEndWidget::BeginLoading()
{
	LoadT0 = TUI::RealTime() + 0.3;
	LoadStopMs = 1.0e9f;
	bLoadHold = false;
	bLoadFrozen = false;
	bLoadReady = false;
	LoadReadyT = -1.0;
	LoadGoAt = -1.0;
	LastJitter = 0.0;
	PmIo = TEXT("000.0");
	PmSync = TEXT("00.00");
	PmBlk = TEXT("0x0000");
	PmTemp = TEXT("00.0");
	PmHz = TEXT("47.20");
}

void UTreadFrontEndWidget::BeginLogin()
{
	LoginPhase = EFrontLogin::Idle;
	LoginT0 = -1.0;
	bLoginHold = false;
	FocusAt = TUI::RealTime() + 0.9;
	FocusBar[0] = FocusBar[1] = 0.0f;
	FocusLine[0] = FocusLine[1] = 0.0f;
	if (CallsignText) CallsignText->SetIsReadOnly(false);
	if (PasswordText) PasswordText->SetIsReadOnly(false);
}

void UTreadFrontEndWidget::BeginSelect()
{
	RefreshStages();
	SelIdx = 0;
	bDosShown = false;
	DosContent = 0;
	SwapStartT = -1.0;
	PendingSel = 0;
	DosNotice.Empty();
	SortieStampT = -1.0;
	SortieGoAt = -1.0;
	ForcedHover = 0;
	HoverCardMouse = 0;
	EffHover = 0;
	TipStage = 0;
	TipHideT = -1.0;
	TipShowT = -1.0;
	for (float& Value : CardHover) Value = 0.0f;
	for (float& Value : BtnHover) Value = 0.0f;
	PmSelHz = TEXT("47.2");
	NextSelHz = 0.0;
}

void UTreadFrontEndWidget::BeginSortie()
{
	bSortieHold = false;
	SortieDoneT = -1.0;
	bLaunchStarted = false;
	for (float& Value : BtnHover) Value = 0.0f;
}

// ------------------------------------------------------------------------------------------------------------
// Transitions (HTML TRANS.scan / slab / blinds)
// ------------------------------------------------------------------------------------------------------------
bool UTreadFrontEndWidget::StartTransition(EFrontTrans Kind, EFrontScreen To, float Dir, const FString& Cap, const FString& Ru, bool bLaunch)
{
	if (Trans.Kind != EFrontTrans::None) return false;
	Trans = FFrontTrans();
	Trans.Kind = Kind;
	Trans.From = Current;
	Trans.To = To;
	Trans.T0 = TUI::RealTime();
	Trans.Dir = Dir;
	Trans.Cap = Cap;
	Trans.Ru = Ru;
	Trans.bLaunch = bLaunch;
	HideTip();
	switch (Kind)
	{
	case EFrontTrans::Scan:
		EnterScreen(To, TmScan, false);
		break;
	case EFrontTrans::Slab:
		bChromeHold = true;
		SetChromeTargets(To, true);
		break;
	default:
		break;
	}
	return true;
}

void UTreadFrontEndWidget::UpdateTransition(double Now)
{
	if (Trans.Kind == EFrontTrans::None || Trans.Frozen >= 0.0f) return;
	const float ElapsedMs = static_cast<float>((Now - Trans.T0) * 1000.0);
	switch (Trans.Kind)
	{
	case EFrontTrans::Scan:
		if (ElapsedMs >= TmScan)
		{
			LeaveScreen(Trans.From);
			Current = Trans.To;
			Trans = FFrontTrans();
		}
		break;
	case EFrontTrans::Slab:
	{
		const float T = ElapsedMs / TmSlab;
		const float Lag = 110.0f / TmSlab;
		const float PK = Sat((T - Lag) / (1.0f - Lag));
		if (!Trans.bSwapped && PK >= 0.42f)
		{
			Trans.bSwapped = true;
			LeaveScreen(Trans.From);
			EnterScreen(Trans.To, 0.0f, false);
		}
		if (T >= 1.0f)
		{
			const EFrontScreen To = Trans.To;
			Current = To;
			bChromeHold = false;
			SetChromeTargets(To, false);
			Trans = FFrontTrans();
		}
		break;
	}
	case EFrontTrans::Blinds:
	{
		if (!Trans.bSwapped && ElapsedMs >= TmBlinds)
		{
			Trans.bSwapped = true;
			if (Trans.bLaunch) LaunchMatch();
			else
			{
				LeaveScreen(Trans.From);
				EnterScreen(Trans.To, 0.0f, false);
			}
		}
		if (ElapsedMs >= TmBlinds * 2.0f + 80.0f)
		{
			const bool bLaunched = Trans.bLaunch && Trans.bLaunchOk;
			const EFrontScreen To = Trans.To;
			Trans = FFrontTrans();
			if (bLaunched) FinishExit();
			else Current = To;
		}
		break;
	}
	default:
		break;
	}
}

/** Called when the blinds are fully closed on a sortie: hand the stage to the controller and enter the BP phase. */
void UTreadFrontEndWidget::LaunchMatch()
{
	const int32 N = SortieStage;
	ETreadM1RejectReason Reason = ETreadM1RejectReason::Unknown;
	bool bOk = false;
	if (Controller.IsValid())
	{
		const FTreadM1CommandResult Selected = Controller->SelectCampaignStage(N);
		if (Selected.bAccepted)
		{
			const FTreadM1CommandResult Begun = Controller->BeginPreMatchBP();
			bOk = Begun.bAccepted;
			Reason = Begun.ReasonCode;
		}
		else
		{
			Reason = Selected.ReasonCode;
		}
	}
	LeaveScreen(EFrontScreen::Sortie);
	if (bOk)
	{
		Trans.bLaunchOk = true;
		Trans.To = EFrontScreen::None;
		Current = EFrontScreen::None;
		return;
	}
	// Rejected: back to the map with the reason shown in the dossier.
	bExitRunning = false;
	bLaunchStarted = false;
	Trans.To = EFrontScreen::Select;
	EnterScreen(EFrontScreen::Select, 0.0f, false);
	FString Why;
	const FFrontStage* Stage = N > 0 && Stages.IsValidIndex(N - 1) ? &Stages[N - 1] : nullptr;
	if (Stage && !Stage->bUnlocked) Why = FString::Printf(TEXT("需先攻克第 %s 关"), *Pad2(N - 1));
	else if (!Controller.IsValid()) Why = TEXT("控制器不可用");
	else Why = UEnum::GetValueAsString(Reason);
	DosNotice = FString::Printf(TEXT("出征受阻 · %s"), *Why);
	DosNoticeT = TUI::RealTime();
	if (N > 0 && Stage)
	{
		SelIdx = N;
		SelChangeT = DosNoticeT;
		bDosShown = true;
		DosShowT = DosNoticeT - 1.0;
		DosContent = N;
		BlkInT = -1.0e9;
		RollT0 = -1.0e9;
	}
}

/** Blinds are open again on the game: the front end is done until the controller returns to the R0 briefing. */
void UTreadFrontEndWidget::FinishExit()
{
	bExitRunning = false;
	SyncVisibility();
	if (bShownNow)
	{
		// The controller is still (or again) in the briefing: show the map instead of an empty cover.
		EnterScreen(EFrontScreen::Select, 0.0f, true);
		Current = EFrontScreen::Select;
	}
}

// ------------------------------------------------------------------------------------------------------------
// Campaign data: the controller view plus the extras it does not expose (Campaign16.json / LeaderRounds.json).
// ------------------------------------------------------------------------------------------------------------
void UTreadFrontEndWidget::LoadStageExtras()
{
	if (bExtrasLoaded) return;
	bExtrasLoaded = true;
	const FString Dir = FPaths::Combine(FPaths::ProjectContentDir(), TEXT("Data/Generated"));
	auto LoadJson = [&Dir](const TCHAR* FileName) -> TSharedPtr<FJsonObject>
	{
		FString Text;
		if (!FFileHelper::LoadFileToString(Text, *FPaths::Combine(Dir, FileName))) return nullptr;
		TSharedPtr<FJsonObject> Root;
		const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Text);
		return FJsonSerializer::Deserialize(Reader, Root) ? Root : nullptr;
	};

	TMap<FString, TPair<FString, TPair<int32, int32>>> Leaders;   // opponentId -> (name, (lineup size, health))
	if (const TSharedPtr<FJsonObject> LeaderRoot = LoadJson(TEXT("LeaderRounds.json")))
	{
		const TArray<TSharedPtr<FJsonValue>>* Array = nullptr;
		if (LeaderRoot->TryGetArrayField(TEXT("leaders"), Array))
		{
			for (const TSharedPtr<FJsonValue>& Value : *Array)
			{
				const TSharedPtr<FJsonObject> Obj = Value.IsValid() ? Value->AsObject() : nullptr;
				if (!Obj.IsValid()) continue;
				FString Id, Name;
				Obj->TryGetStringField(TEXT("opponentId"), Id);
				Obj->TryGetStringField(TEXT("displayName"), Name);
				Name.ReplaceInline(TEXT("（占位）"), TEXT(""));
				int32 Health = 0;
				Obj->TryGetNumberField(TEXT("health"), Health);
				const TArray<TSharedPtr<FJsonValue>>* Lineup = nullptr;
				const int32 LineupCount = Obj->TryGetArrayField(TEXT("lineup"), Lineup) ? Lineup->Num() : 0;
				Leaders.Add(Id, TPair<FString, TPair<int32, int32>>(Name, TPair<int32, int32>(LineupCount, Health)));
			}
		}
	}

	if (const TSharedPtr<FJsonObject> CampaignRoot = LoadJson(TEXT("Campaign16.json")))
	{
		const TArray<TSharedPtr<FJsonValue>>* Array = nullptr;
		if (CampaignRoot->TryGetArrayField(TEXT("stages"), Array))
		{
			for (const TSharedPtr<FJsonValue>& Value : *Array)
			{
				const TSharedPtr<FJsonObject> Obj = Value.IsValid() ? Value->AsObject() : nullptr;
				if (!Obj.IsValid()) continue;
				FFrontStage S;
				Obj->TryGetNumberField(TEXT("index"), S.Index);
				Obj->TryGetStringField(TEXT("country"), S.Country);
				Obj->TryGetStringField(TEXT("landmark"), S.Landmark);
				Obj->TryGetStringField(TEXT("rule"), S.Rule);
				Obj->TryGetStringField(TEXT("effect"), S.Effect);
				Obj->TryGetNumberField(TEXT("aiLevel"), S.AiLevel);
				Obj->TryGetNumberField(TEXT("garrisonBonus"), S.GarrisonBonus);
				Obj->TryGetNumberField(TEXT("enemyHpBonus"), S.EnemyHpBonus);
				Obj->TryGetNumberField(TEXT("startGoldBonus"), S.StartGoldBonus);
				Obj->TryGetNumberField(TEXT("incomeBonus"), S.IncomeBonus);
				Obj->TryGetNumberField(TEXT("damageTakenPercent"), S.DamageTakenPercent);
				Obj->TryGetNumberField(TEXT("prepareSecondsDelta"), S.PrepareDelta);
				FString LeaderId;
				Obj->TryGetStringField(TEXT("leaderId"), LeaderId);
				if (const TPair<FString, TPair<int32, int32>>* Leader = Leaders.Find(LeaderId))
				{
					S.Leader = Leader->Key;
					S.LeaderSize = Leader->Value.Key;
					S.LeaderHp = Leader->Value.Value;
				}
				if (S.Index >= 1 && S.Index <= 16)
				{
					while (ExtraStages.Num() < S.Index) { FFrontStage Blank; Blank.Index = ExtraStages.Num() + 1; ExtraStages.Add(Blank); }
					ExtraStages[S.Index - 1] = S;
				}
			}
		}
	}
	for (FFrontStage& S : ExtraStages) FinishStageText(S);
}

void UTreadFrontEndWidget::FinishStageText(FFrontStage& S)
{
	int32 Slash = INDEX_NONE;
	S.ShortName = S.Country.FindChar(TEXT('/'), Slash) ? S.Country.Left(Slash).TrimEnd() : S.Country;
	int32 Colon = INDEX_NONE;
	S.City = S.Rule.FindChar(TEXT('：'), Colon) ? S.Rule.Left(Colon) : S.Rule;
}

void UTreadFrontEndWidget::RefreshStages()
{
	LoadStageExtras();
	TArray<FFrontStage> Out = ExtraStages;
	bool bHaveView = false;
	if (Controller.IsValid())
	{
		const TArray<FTreadM4CampaignStageView> Views = Controller->GetCampaignStages();
		for (const FTreadM4CampaignStageView& V : Views)
		{
			if (V.Index < 1 || V.Index > 16) continue;
			bHaveView = true;
			while (Out.Num() < V.Index) { FFrontStage Blank; Blank.Index = Out.Num() + 1; Out.Add(Blank); }
			FFrontStage& S = Out[V.Index - 1];
			S.Index = V.Index;
			S.Country = V.Country;
			S.Landmark = V.Landmark;
			S.Rule = V.Rule;
			S.Effect = V.Effect;
			S.AiLevel = V.AiLevel;
			S.bUnlocked = V.bUnlocked;
			S.bConquered = V.bConquered;
			FinishStageText(S);
		}
	}
	if (!bHaveView && Out.Num() > 0) Out[0].bUnlocked = true;
	Stages = MoveTemp(Out);
}

EFrontStageState UTreadFrontEndWidget::StateOf(int32 StageNo) const
{
	if (!Stages.IsValidIndex(StageNo - 1)) return EFrontStageState::Locked;
	const FFrontStage& S = Stages[StageNo - 1];
	if (S.bConquered) return EFrontStageState::Cleared;
	return S.bUnlocked ? EFrontStageState::Front : EFrontStageState::Locked;
}

int32 UTreadFrontEndWidget::ClearedCount() const
{
	int32 Count = 0;
	for (const FFrontStage& S : Stages) Count += S.bConquered ? 1 : 0;
	return Count;
}

// ------------------------------------------------------------------------------------------------------------
// Per-frame update
// ------------------------------------------------------------------------------------------------------------
void UTreadFrontEndWidget::BindController()
{
	if (!Controller.IsValid()) return;
	Controller->OnPhaseChanged.RemoveDynamic(this, &UTreadFrontEndWidget::HandlePhaseChanged);
	Controller->OnStateChanged.RemoveDynamic(this, &UTreadFrontEndWidget::HandleStateChanged);
	Controller->OnPhaseChanged.AddDynamic(this, &UTreadFrontEndWidget::HandlePhaseChanged);
	Controller->OnStateChanged.AddDynamic(this, &UTreadFrontEndWidget::HandleStateChanged);
}

void UTreadFrontEndWidget::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
	Super::NativeTick(MyGeometry, InDeltaTime);
	const double Now = TUI::RealTime();
	if (!Controller.IsValid() && Now >= NextControllerSearch)
	{
		NextControllerSearch = Now + 0.5;
		Controller = FindController();
		BindController();
	}
	SyncVisibility();
	if (!bShownNow) return;

	const float Dt = FMath::Clamp(static_cast<float>(Now - LastTick), 0.0f, 0.1f);
	LastTick = Now;
	const FVector2f Size = MyGeometry.GetLocalSize();
	UpdateViewMetrics(Size);
	if (bMouseIn) MouseDesign = (MouseLocal - ViewOrigin) / ViewScale;

	UpdateTransition(Now);
	if (Scr[static_cast<int32>(EFrontScreen::Loading)].bOn) TickLoading(Now);
	if (Scr[static_cast<int32>(EFrontScreen::Login)].bOn) TickLogin(Now, Dt);
	if (Scr[static_cast<int32>(EFrontScreen::Select)].bOn) TickSelect(Now, Dt);
	if (Scr[static_cast<int32>(EFrontScreen::Sortie)].bOn) TickSortie(Now);
	TickChrome(Dt);
	UpdateHover(Now, Dt);
	UpdateInputWidgets(Now);
	if (PaintWidget.IsValid()) PaintWidget->Invalidate(EInvalidateWidgetReason::Paint);
}

void UTreadFrontEndWidget::UpdateViewMetrics(const FVector2f& Size)
{
	ViewSize = Size;
	ViewScale = FMath::Max(0.01f, FMath::Min(Size.X / DW, Size.Y / DH));
	ViewOrigin = FVector2f((Size.X - DW * ViewScale) * 0.5f, (Size.Y - DH * ViewScale) * 0.5f);
}

void UTreadFrontEndWidget::TickLoading(double Now)
{
	const float TtMs = FMath::Clamp(static_cast<float>((Now - LoadT0) * 1000.0), 0.0f, LoadStopMs);
	const float P = ProgAt(TtMs);
	if (P >= 1.0f && !bLoadReady)
	{
		bLoadReady = true;
		LoadReadyT = Now;
		if (!bLoadHold) LoadGoAt = Now + TmReadyHold / 1000.0;
	}
	if (Now - LastJitter > 0.09)
	{
		LastJitter = Now;
		PmIo = FString::Printf(TEXT("%05.1f"), P < 1.0f ? 360.0f + FMath::FRand() * 120.0f : 0.0f);
		PmSync = FString::Printf(TEXT("%05.2f"), FMath::Clamp(P * 100.0f - FMath::FRand() * 1.2f * (1.0f - P), 0.0f, 99.99f));
		PmBlk = FString::Printf(TEXT("0x%04X"), FMath::FloorToInt(P * 16383.0f + FMath::FRand() * 40.0f * (1.0f - P)));
		PmTemp = FString::Printf(TEXT("%.1f"), 58.0f + P * 4.0f + FMath::FRand() * 1.6f);
		PmHz = FString::Printf(TEXT("%.2f"), 47.2f + (FMath::FRand() - 0.5f) * 0.3f);
	}
	if (LoadGoAt > 0.0 && Now >= LoadGoAt && Trans.Kind == EFrontTrans::None && Current == EFrontScreen::Loading)
	{
		LoadGoAt = -1.0;
		StartTransition(EFrontTrans::Scan, EFrontScreen::Login, 1.0f, FString(), FString(), false);
	}
}

void UTreadFrontEndWidget::TickLogin(double Now, float Dt)
{
	const bool bLive = AreInputsLive();
	if (bLive && CallsignText && PasswordText)
	{
		// Mirror the real text boxes (OnTextChanged also truncates to the maximum length).
		CallsignValue = CallsignText->GetText().ToString();
		PasswordLen = PasswordText->GetText().ToString().Len();
		const bool bFocus[2] = { CallsignText->HasKeyboardFocus(), PasswordText->HasKeyboardFocus() };
		for (int32 Index = 0; Index < 2; ++Index)
		{
			FocusBar[Index] = FMath::Clamp(FocusBar[Index] + (bFocus[Index] ? Dt / 0.3f : -Dt / 0.3f), 0.0f, 1.0f);
			FocusLine[Index] = FMath::Clamp(FocusLine[Index] + (bFocus[Index] ? Dt / 0.42f : -Dt / 0.42f), 0.0f, 1.0f);
		}
		if (FocusAt > 0.0 && Now >= FocusAt && LoginPhase == EFrontLogin::Idle)
		{
			FocusAt = -1.0;
			CallsignText->SetKeyboardFocus();
		}
	}
	if (LoginPhase == EFrontLogin::Verifying && !bLoginHold && Trans.Kind == EFrontTrans::None && Current == EFrontScreen::Login
		&& (Now - LoginT0) * 1000.0 >= TmLoginLeave)
	{
		StartTransition(EFrontTrans::Slab, EFrontScreen::Select, 1.0f, TEXT("十六国战役"), TEXT("КАМПАНИЯ · Л.03"), false);
	}
}

void UTreadFrontEndWidget::TickSelect(double Now, float Dt)
{
	if (Now >= NextStageRefresh)
	{
		NextStageRefresh = Now + 0.5;
		RefreshStages();
	}
	if (SwapStartT >= 0.0 && Now - SwapStartT >= 0.12)
	{
		// The old dossier faded out: put the new content in and let the blocks stagger back.
		DosContent = PendingSel;
		BlkInT = Now;
		RollT0 = Now;
		SwapStartT = -1.0;
	}
	if (SortieGoAt > 0.0 && Now >= SortieGoAt && Trans.Kind == EFrontTrans::None && Current == EFrontScreen::Select)
	{
		SortieGoAt = -1.0;
		SortieStage = SortieGoStage;
		StartTransition(EFrontTrans::Blinds, EFrontScreen::Sortie, 1.0f, FString(), FString(), false);
	}
	if (Now >= NextSelHz)
	{
		NextSelHz = Now + 0.14;
		PmSelHz = FString::Printf(TEXT("%.1f"), 47.2f + (FMath::FRand() - 0.5f) * 0.4f);
	}
}

void UTreadFrontEndWidget::TickSortie(double Now)
{
	const FFrontScreenRt& Rt = Scr[static_cast<int32>(EFrontScreen::Sortie)];
	const double Raw = (Now - Rt.T0 - 0.7) * 1000.0 / TmSortieDeploy;
	if (Raw >= 1.0 && SortieDoneT < 0.0) SortieDoneT = Now;
	if (SortieDoneT >= 0.0 && !bSortieHold && !bLaunchStarted && Trans.Kind == EFrontTrans::None && Current == EFrontScreen::Sortie
		&& Now - SortieDoneT >= 0.45)
	{
		// Deployment is full: blinds close, then (at full cover) the controller gets the stage.
		bLaunchStarted = true;
		bExitRunning = true;
		StartTransition(EFrontTrans::Blinds, EFrontScreen::None, 1.0f, FString(), FString(), true);
	}
}

void UTreadFrontEndWidget::TickChrome(float Dt)
{
	auto Approach = [Dt](FLinearColor& Value, const FLinearColor& Target)
	{
		const float K = 1.0f - FMath::Exp(-Dt * 7.0f);   // ~500 ms transition
		Value = FLinearColor(FMath::Lerp(Value.R, Target.R, K), FMath::Lerp(Value.G, Target.G, K),
			FMath::Lerp(Value.B, Target.B, K), 1.0f);
	};
	if (!bChromeInit)
	{
		bChromeInit = true;
		ChromeTop = ChromeTopTarget;
		ChromeBottom = ChromeBottomTarget;
		ChromeAccent = ChromeAccentTarget;
		return;
	}
	Approach(ChromeTop, ChromeTopTarget);
	Approach(ChromeBottom, ChromeBottomTarget);
	Approach(ChromeAccent, ChromeAccentTarget);
}

// ------------------------------------------------------------------------------------------------------------
// Hover / hit testing: the rectangles are the ones the Draw* functions use.
// ------------------------------------------------------------------------------------------------------------
void UTreadFrontEndWidget::ComputeHover(const FVector2f& M, int32& OutBtn, int32& OutCard) const
{
	OutBtn = -1;
	OutCard = 0;
	if (Trans.Kind != EFrontTrans::None || bExitRunning) return;
	switch (Current)
	{
	case EFrontScreen::Login:
		if (LoginPhase == EFrontLogin::Idle && RcLoginBtn.Contains(M)) OutBtn = BtnLogin;
		break;
	case EFrontScreen::Select:
		if (RcLogout.Contains(M)) { OutBtn = BtnLogout; break; }
		if (bDosShown && SwapStartT < 0.0)
		{
			if (RcGoBtn.Contains(M)) { OutBtn = BtnGo; break; }
		}
		else if (!bDosShown && RcFreeBtn.Contains(M)) { OutBtn = BtnFree; break; }
		for (int32 Index = 0; Index < Stages.Num() && Index < 16; ++Index)
		{
			if (CardHit(Index).Contains(M)) { OutCard = Index + 1; break; }
		}
		break;
	case EFrontScreen::Sortie:
		if (!bLaunchStarted && RcBackBtn.Contains(M)) OutBtn = BtnBack;
		break;
	default:
		break;
	}
}

void UTreadFrontEndWidget::UpdateHover(double Now, float Dt)
{
	int32 Btn = -1, Card = 0;
	if (bMouseIn) ComputeHover(MouseDesign, Btn, Card);
	HoverBtn = Btn;
	HoverCardMouse = Card;
	static const float Dur[BtnCount] = { 0.38f, 0.38f, 0.3f, 0.3f, 0.3f };
	for (int32 Index = 0; Index < BtnCount; ++Index)
	{
		const bool bOn = Btn == Index;
		BtnHover[Index] = FMath::Clamp(BtnHover[Index] + (bOn ? Dt / Dur[Index] : -Dt / Dur[Index]), 0.0f, 1.0f);
	}

	const int32 NewHover = Current == EFrontScreen::Select && Trans.Kind == EFrontTrans::None
		? (ForcedHover > 0 ? ForcedHover : HoverCardMouse) : 0;
	if (NewHover != EffHover)
	{
		EffHover = NewHover;
		if (EffHover > 0) ShowTip(EffHover);
		else HideTip();
	}
	for (int32 Index = 0; Index < 16; ++Index)
	{
		const bool bUp = EffHover == Index + 1 || SelIdx == Index + 1;
		CardHover[Index] = FMath::Clamp(CardHover[Index] + (bUp ? Dt / 0.26f : -Dt / 0.26f), 0.0f, 1.0f);
	}
}

void UTreadFrontEndWidget::HideTip()
{
	if (TipStage > 0 && TipHideT < 0.0) TipHideT = TUI::RealTime();
}

/** Greedy character wrap (CJK has no spaces) of Value to MaxWidth design px in the tooltip body font. */
static TArray<FString> WrapToWidth(const FString& Value, float MaxWidth, float Scl)
{
	TArray<FString> Lines;
	const FSlateFontInfo Font = TUI::Font(TUI::EFontRole::SansMedium, TUI::Pt(15.0f, Scl));
	FString Line;
	for (int32 Index = 0; Index < Value.Len(); ++Index)
	{
		const FString Trial = Line + Value.Mid(Index, 1);
		if (!Line.IsEmpty() && TUI::TextSize(Trial, Font).X / Scl > MaxWidth)
		{
			Lines.Add(Line);
			Line = Value.Mid(Index, 1);
		}
		else
		{
			Line = Trial;
		}
	}
	Lines.Add(Line);
	return Lines;
}

/** HTML showTip(): pick the side of the card (right / left / down / up) that hides the least. */
void UTreadFrontEndWidget::ShowTip(int32 N)
{
	if (!Stages.IsValidIndex(N - 1) || Trans.Kind != EFrontTrans::None) return;
	const FFrontStage& S = Stages[N - 1];
	const double Now = TUI::RealTime();
	TipStage = N;
	TipShowT = Now;
	TipHideT = -1.0;

	const float BodyW = 330.0f - 28.0f - 50.0f;
	TipLand = WrapToWidth(S.Landmark, BodyW, ViewScale);
	TipRuleText = WrapToWidth(S.Rule, BodyW, ViewScale);
	TipEff = WrapToWidth(S.Effect, BodyW, ViewScale);
	auto RowH = [](const TArray<FString>& Lines) { return FMath::Max(22.0f, Lines.Num() * 21.0f); };
	const float W = 330.0f;
	const float H = 46.0f + 8.0f + RowH(TipLand) + 8.0f + RowH(TipRuleText) + 8.0f + RowH(TipEff) + 11.0f + 24.0f + 8.0f + 27.0f;
	TipH = H;

	struct FWeighted { float X, Y, W, H, K; };
	TArray<FWeighted> Rects;
	for (int32 Index = 0; Index < Stages.Num() && Index < 16; ++Index)
	{
		const int32 K = Index + 1;
		const FVector2f SlotPos = CardSlot(Index);
		const float Weight = K == N ? 0.0f : (K == SelIdx || StateOf(K) == EFrontStageState::Front) ? 6.0f : 1.0f;
		Rects.Add(FWeighted{ SlotPos.X, SlotPos.Y, 236.0f, 168.0f, Weight });
	}
	Rects.Add(FWeighted{ 1270.0f, 220.0f, 600.0f, 800.0f, 8.0f });   // dossier column

	auto Overlap = [](const FWeighted& A, const FWeighted& B)
	{
		return FMath::Max(0.0f, FMath::Min(A.X + A.W, B.X + B.W) - FMath::Max(A.X, B.X))
			* FMath::Max(0.0f, FMath::Min(A.Y + A.H, B.Y + B.H) - FMath::Max(A.Y, B.Y));
	};
	auto ClampHtml = [](float V, float Lo, float Hi) { return FMath::Max(Lo, FMath::Min(Hi, V)); };

	const FVector2f SlotPos = CardSlot(N - 1);
	struct FCandidate { int32 Side; float X, Y; };
	const FCandidate Cands[4] = {
		{ 0, SlotPos.X + 236.0f + 20.0f, ClampHtml(SlotPos.Y - 6.0f, 236.0f, 1000.0f - H) },
		{ 1, SlotPos.X - W - 20.0f, ClampHtml(SlotPos.Y - 6.0f, 236.0f, 1000.0f - H) },
		{ 2, ClampHtml(SlotPos.X - 42.0f, 90.0f, 1880.0f - W), SlotPos.Y + 168.0f + 18.0f },
		{ 3, ClampHtml(SlotPos.X - 42.0f, 90.0f, 1880.0f - W), SlotPos.Y - H - 18.0f } };
	float BestScore = 0.0f;
	int32 Best = -1;
	for (int32 Index = 0; Index < 4; ++Index)
	{
		const FCandidate& C = Cands[Index];
		const FWeighted Box{ C.X, C.Y, W + 12.0f, H + 12.0f, 0.0f };
		float Score = 0.0f;
		for (const FWeighted& R : Rects) Score += Overlap(Box, R) * R.K;
		if (C.X < 80.0f || C.X + W > 1890.0f || C.Y < 220.0f || C.Y + H > 1050.0f) Score += 1.0e9f;
		if (C.Side >= 2) Score *= 1.15f;
		if (Best < 0 || Score < BestScore) { Best = Index; BestScore = Score; }
	}
	TipSide = Cands[Best].Side;
	TipPos = FVector2f(Cands[Best].X, Cands[Best].Y);
}

// ------------------------------------------------------------------------------------------------------------
// Real text boxes: positioned over the drawn input boxes every tick, shown only while the login screen is idle.
// ------------------------------------------------------------------------------------------------------------
bool UTreadFrontEndWidget::AreInputsLive() const
{
	return bShownNow && Current == EFrontScreen::Login && Scr[static_cast<int32>(EFrontScreen::Login)].bOn
		&& Trans.Kind == EFrontTrans::None && !bExitRunning;
}

void UTreadFrontEndWidget::ApplyInputStyle()
{
	if (!CallsignText || !PasswordText) return;
	const FSlateFontInfo Font = TUI::Font(TUI::EFontRole::Mono, TUI::Pt(30.0f, ViewScale));
	FieldLineHeight = TUI::TextSize(TEXT("国Ag|"), Font).Y;

	// Password bullets: the Mono face's U+2022 is about twice the browser's (9 px dot on a 16 px pitch at 30 px) and the dots
	// touch, while a shrunken font gives a ~3 px dot. So the box keeps only the metrics: the font is shrunk until the bullet
	// advance is ~8.5 design px and tracking widens the pitch back to 16 (the caret follows that advance), and its glyphs are
	// transparent. DrawLogin paints the dots on the same pitch. The caret takes the widget foreground, not this colour.
	const float BulletAdv = TUI::TextSize(TEXT("•"), Font).X;
	const float PwFactor = BulletAdv > 1.0f ? FMath::Clamp(8.5f * ViewScale / BulletAdv, 0.2f, 1.0f) : 1.0f;
	const FSlateFontInfo PasswordFont = TUI::Font(TUI::EFontRole::Mono, TUI::Pt(30.0f * PwFactor, ViewScale), (16.0f - 8.5f) / (30.0f * PwFactor));
	PasswordLineHeight = TUI::TextSize(TEXT("国Ag|"), PasswordFont).Y;
	for (UEditableText* Text : { CallsignText.Get(), PasswordText.Get() })
	{
		FEditableTextStyle Style = Text->WidgetStyle;
		Style.SetFont(Text == PasswordText.Get() ? PasswordFont : Font);
		Style.SetColorAndOpacity(FSlateColor(Text == PasswordText.Get() ? TUI::WithAlpha(TUI::Ink, 0.0f) : TUI::Ink));
		Style.SetCaretImage(FSlateColorBrush(TUI::Red));
		Style.SetBackgroundImageSelected(FSlateColorBrush(TUI::WithAlpha(TUI::Red, 0.35f)));
		Text->SetWidgetStyle(Style);
	}
}

FVector2f UTreadFrontEndWidget::ShakeOffset(double Now) const
{
	if (LoginPhase != EFrontLogin::Verifying) return FVector2f::ZeroVector;
	const float T = static_cast<float>((Now - LoginT0 - 0.95) / 0.3);
	if (T < 0.0f || T > 1.0f) return FVector2f::ZeroVector;
	// CSS @keyframes shake (linear): 0 -> (5,-3) -> (-4,3) -> (3,-1) -> (-1,1) -> 0 at 20% steps.
	static const FVector2f Keys[6] = { FVector2f(0, 0), FVector2f(5, -3), FVector2f(-4, 3), FVector2f(3, -1), FVector2f(-1, 1), FVector2f(0, 0) };
	const float F = T * 5.0f;
	const int32 Index = FMath::Min(4, FMath::FloorToInt(F));
	return Keys[Index] + (Keys[Index + 1] - Keys[Index]) * (F - Index);
}

void UTreadFrontEndWidget::UpdateInputWidgets(double Now)
{
	if (!CallsignText || !PasswordText) return;
	const bool bLive = AreInputsLive();
	const ESlateVisibility Want = bLive ? ESlateVisibility::Visible : ESlateVisibility::Collapsed;
	if (CallsignText->GetVisibility() != Want) CallsignText->SetVisibility(Want);
	if (PasswordText->GetVisibility() != Want) PasswordText->SetVisibility(Want);
	if (!bLive) return;
	if (!FMath::IsNearlyEqual(LastFontScale, ViewScale, 0.0005f) || !FMath::IsNearlyEqual(LastPaintScale, TUI::GetPaintFontScale(), 0.0005f))
	{
		LastFontScale = ViewScale;
		LastPaintScale = TUI::GetPaintFontScale();
		ApplyInputStyle();
	}
	const FFrontEnv Env = EnvFor(EFrontScreen::Login, Now);
	const FVector2f Shake = ShakeOffset(Now);
	UEditableText* Texts[2] = { CallsignText.Get(), PasswordText.Get() };
	static const float Delays[2] = { 440.0f, 520.0f };
	for (int32 Index = 0; Index < 2; ++Index)
	{
		float Delay = Delays[Index];
		if (Env.ScanMs > 0.0f) Delay = FMath::Clamp(RcField[Index].Y - 40.0f, 0.0f, DH) / DH * Env.ScanMs * 0.8f + Delay * 0.35f;
		const float E = Env.ElapsedMs() - Delay;
		const float PO = TUI::Ease::CssOut(Sat(E / 560.0f));
		const float PT = TUI::Ease::CssOut(Sat(E / 720.0f));
		const float X = RcField[Index].X + 46.0f + Shake.X;
		const float BoxH = Index == 1 ? PasswordLineHeight : FieldLineHeight;   // local px
		const float Y = RcField[Index].Y + 4.0f + (68.0f - BoxH / ViewScale) * 0.5f + 30.0f * (1.0f - PT) + Shake.Y;
		if (UCanvasPanelSlot* CanvasSlot = Cast<UCanvasPanelSlot>(Texts[Index]->Slot))
		{
			CanvasSlot->SetPosition(FVector2D(ViewOrigin.X + X * ViewScale, ViewOrigin.Y + Y * ViewScale));
			CanvasSlot->SetSize(FVector2D((620.0f - 46.0f - 28.0f) * ViewScale, BoxH));
		}
		Texts[Index]->SetRenderOpacity(PO);
	}
}

// ------------------------------------------------------------------------------------------------------------
// Login
// ------------------------------------------------------------------------------------------------------------
void UTreadFrontEndWidget::DoLogin()
{
	if (LoginPhase != EFrontLogin::Idle || Current != EFrontScreen::Login || Trans.Kind != EFrontTrans::None
		|| !Scr[static_cast<int32>(EFrontScreen::Login)].bOn) return;
	FString Name = CallsignValue.TrimStartAndEnd();
	if (Name.IsEmpty()) Name = TEXT("无名");
	Commander = Name.Left(16);
	LoginPhase = EFrontLogin::Verifying;
	LoginT0 = TUI::RealTime();
	bLoggedIn = true;
	const bool bHadFocus = (CallsignText && CallsignText->HasKeyboardFocus()) || (PasswordText && PasswordText->HasKeyboardFocus());
	if (CallsignText) CallsignText->SetIsReadOnly(true);
	if (PasswordText) PasswordText->SetIsReadOnly(true);
	if (bHadFocus && FSlateApplication::IsInitialized()) FSlateApplication::Get().SetAllUserFocusToGameViewport();
}

// ------------------------------------------------------------------------------------------------------------
// Select
// ------------------------------------------------------------------------------------------------------------
void UTreadFrontEndWidget::SelectStage(int32 N)
{
	if (Trans.Kind != EFrontTrans::None || !Stages.IsValidIndex(N - 1)) return;
	const double Now = TUI::RealTime();
	DosNotice.Empty();
	if (!bDosShown)
	{
		// First selection: the dossier opens with the content already in place (clip reveal + scan line).
		DosContent = N;
		SelIdx = N;
		SelChangeT = Now;
		bDosShown = true;
		DosShowT = Now;
		BlkInT = -1.0e9;
		RollT0 = Now;
		SwapStartT = -1.0;
		return;
	}
	if (N == SelIdx) return;
	SelIdx = N;
	SelChangeT = Now;
	PendingSel = N;
	if (SwapStartT < 0.0) SwapStartT = Now;
}

void UTreadFrontEndWidget::DoSortie()
{
	const int32 N = SelIdx;
	if (N <= 0 || StateOf(N) == EFrontStageState::Locked || Trans.Kind != EFrontTrans::None || SortieGoAt > 0.0) return;
	const double Now = TUI::RealTime();
	SortieStampT = Now;
	SortieGoAt = Now + 0.56;
	SortieGoStage = N;
	HideTip();
}

void UTreadFrontEndWidget::DoFreeMatch()
{
	if (Trans.Kind != EFrontTrans::None || bDosShown) return;
	SortieStage = 0;
	StartTransition(EFrontTrans::Blinds, EFrontScreen::Sortie, 1.0f, FString(), FString(), false);
}

// ------------------------------------------------------------------------------------------------------------
// Mouse
// ------------------------------------------------------------------------------------------------------------
void UTreadFrontEndWidget::UpdateMouse(const FGeometry& Geometry, const FPointerEvent& MouseEvent)
{
	const FVector2f Size = Geometry.GetLocalSize();
	UpdateViewMetrics(Size);
	const FVector2f Local = Geometry.AbsoluteToLocal(MouseEvent.GetScreenSpacePosition());
	MouseLocal = Local;
	bMouseIn = true;
	MouseDesign = (MouseLocal - ViewOrigin) / ViewScale;
}

FReply UTreadFrontEndWidget::NativeOnMouseMove(const FGeometry& InGeometry, const FPointerEvent& InMouseEvent)
{
	if (!bShownNow) return Super::NativeOnMouseMove(InGeometry, InMouseEvent);
	UpdateMouse(InGeometry, InMouseEvent);
	return FReply::Handled();
}

FReply UTreadFrontEndWidget::NativeOnMouseButtonDown(const FGeometry& InGeometry, const FPointerEvent& InMouseEvent)
{
	if (!bShownNow) return Super::NativeOnMouseButtonDown(InGeometry, InMouseEvent);
	UpdateMouse(InGeometry, InMouseEvent);
	if (InMouseEvent.GetEffectingButton() == EKeys::LeftMouseButton) HandleClick();
	// Always swallow the click: nothing underneath (the legacy campaign map, the board) may see it.
	return FReply::Handled();
}

FReply UTreadFrontEndWidget::NativeOnMouseButtonUp(const FGeometry& InGeometry, const FPointerEvent& InMouseEvent)
{
	if (!bShownNow) return Super::NativeOnMouseButtonUp(InGeometry, InMouseEvent);
	return FReply::Handled();
}

FReply UTreadFrontEndWidget::NativeOnMouseWheel(const FGeometry& InGeometry, const FPointerEvent& InMouseEvent)
{
	if (!bShownNow) return Super::NativeOnMouseWheel(InGeometry, InMouseEvent);
	return FReply::Handled();
}

void UTreadFrontEndWidget::NativeOnMouseLeave(const FPointerEvent& InMouseEvent)
{
	Super::NativeOnMouseLeave(InMouseEvent);
	bMouseIn = false;
}

FCursorReply UTreadFrontEndWidget::NativeOnCursorQuery(const FGeometry& InGeometry, const FPointerEvent& InCursorEvent)
{
	if (!bShownNow) return Super::NativeOnCursorQuery(InGeometry, InCursorEvent);
	UpdateMouse(InGeometry, InCursorEvent);
	int32 Btn = -1, Card = 0;
	ComputeHover(MouseDesign, Btn, Card);
	return FCursorReply::Cursor(Btn >= 0 || Card > 0 ? EMouseCursor::Hand : EMouseCursor::Default);
}

void UTreadFrontEndWidget::HandleClick()
{
	if (Trans.Kind != EFrontTrans::None || bExitRunning) return;
	const FVector2f M = MouseDesign;
	int32 Btn = -1, Card = 0;
	ComputeHover(M, Btn, Card);
	switch (Current)
	{
	case EFrontScreen::Login:
		if (LoginPhase != EFrontLogin::Idle) break;
		if (Btn == BtnLogin) DoLogin();
		else if (RcField[0].Contains(M) && CallsignText) CallsignText->SetKeyboardFocus();
		else if (RcField[1].Contains(M) && PasswordText) PasswordText->SetKeyboardFocus();
		break;
	case EFrontScreen::Select:
		if (Btn == BtnLogout)
		{
			StartTransition(EFrontTrans::Slab, EFrontScreen::Login, -1.0f, TEXT("身份核验"), TEXT("ВЫХОД · Л.02"), false);
		}
		else if (Btn == BtnGo) DoSortie();
		else if (Btn == BtnFree) DoFreeMatch();
		else if (Card > 0) SelectStage(Card);
		break;
	case EFrontScreen::Sortie:
		if (Btn == BtnBack)
		{
			StartTransition(EFrontTrans::Slab, EFrontScreen::Select, -1.0f, TEXT("十六国战役"), TEXT("НАЗАД · Л.03"), false);
		}
		break;
	default:
		break;
	}
}

// ------------------------------------------------------------------------------------------------------------
// Test hooks (doc 157 section 4.3)
// ------------------------------------------------------------------------------------------------------------
void UTreadFrontEndWidget::JumpToScreenForTest(const FString& Screen)
{
	SyncVisibility();
	if (!bShownNow) return;
	bTickerPinned = true;
	const FString Name = Screen.ToLower();
	const double Now = TUI::RealTime();
	ResetFlow();
	if (Commander.IsEmpty()) Commander = TEXT("伊万诺娃");
	if (Name == TEXT("loading"))
	{
		Current = EFrontScreen::Loading;
		EnterScreen(EFrontScreen::Loading, 0.0f, true);
		LoadT0 = Now;
		bLoadHold = true;
	}
	else if (Name == TEXT("login"))
	{
		Current = EFrontScreen::Login;
		EnterScreen(EFrontScreen::Login, 0.0f, true);
	}
	else if (Name == TEXT("select"))
	{
		bLoggedIn = true;
		Current = EFrontScreen::Select;
		EnterScreen(EFrontScreen::Select, 0.0f, true);
	}
	else if (Name == TEXT("sortie"))
	{
		bLoggedIn = true;
		if (SortieStage <= 0 && SelIdx > 0) SortieStage = SelIdx;
		if (SortieStage <= 0)
		{
			SortieStage = 1;
			for (const FFrontStage& S : Stages)
			{
				if (S.bUnlocked && !S.bConquered) { SortieStage = S.Index; break; }
			}
		}
		Current = EFrontScreen::Sortie;
		EnterScreen(EFrontScreen::Sortie, 0.0f, true);
		Scr[static_cast<int32>(EFrontScreen::Sortie)].T0 = Now - 10.0;
		bSortieHold = true;
		SortieDoneT = Now - 10.0;
	}
	bChromeInit = false;
	SetChromeTargets(Current, false);
}

void UTreadFrontEndWidget::SetLoadingProgressForTest(float Fraction)
{
	if (!bShownNow) return;
	if (!Scr[static_cast<int32>(EFrontScreen::Loading)].bOn) JumpToScreenForTest(TEXT("loading"));
	const double Now = TUI::RealTime();
	const float F = Sat(Fraction);
	float Stop = 0.0f;
	while (Stop < TmLoadTotal && ProgAt(Stop) < F) Stop += 10.0f;
	bLoadHold = true;
	bLoadFrozen = true;
	LoadGoAt = -1.0;
	LoadStopMs = Stop;
	LoadT0 = Now - Stop / 1000.0 - 1.0;
	bLoadReady = F >= 1.0f;
	LoadReadyT = bLoadReady ? Now - 2.0 : -1.0;
	Scr[static_cast<int32>(EFrontScreen::Loading)].bFinal = true;
}

void UTreadFrontEndWidget::SubmitLoginForTest(const FString& Name)
{
	if (!bShownNow) return;
	if (Current != EFrontScreen::Login) JumpToScreenForTest(TEXT("login"));
	const FString Value = Name.Left(16);
	CallsignValue = Value;
	if (CallsignText) CallsignText->SetText(FText::FromString(Value));
	if (PasswordText && PasswordLen == 0)
	{
		PasswordText->SetText(FText::FromString(TEXT("xxxxxxxx")));
		PasswordLen = 8;
	}
	bLoginHold = true;
	DoLogin();
}

void UTreadFrontEndWidget::HoverStageForTest(int32 Index)
{
	if (!bShownNow) return;
	if (Current != EFrontScreen::Select) JumpToScreenForTest(TEXT("select"));
	ForcedHover = Index >= 1 && Index <= 16 ? Index : 0;
}

void UTreadFrontEndWidget::SelectStageForTest(int32 Index)
{
	if (!bShownNow) return;
	if (Current != EFrontScreen::Select) JumpToScreenForTest(TEXT("select"));
	SelectStage(Index);
	if (bDosShown)
	{
		// Settle every dossier animation so a screenshot taken right after shows the final state.
		const double Now = TUI::RealTime();
		DosContent = SelIdx;
		SwapStartT = -1.0;
		DosShowT = Now - 10.0;
		BlkInT = -1.0e9;
		RollT0 = -1.0e9;
		SelChangeT = Now - 10.0;
	}
}

float UTreadFrontEndWidget::TransElapsedMs(double Now) const
{
	if (Trans.Frozen >= 0.0f)
	{
		switch (Trans.Kind)
		{
		case EFrontTrans::Scan: return Trans.Frozen * TmScan;
		case EFrontTrans::Slab: return Trans.Frozen * TmSlab;
		case EFrontTrans::Blinds: return Trans.Frozen * (TmBlinds * 2.0f + 80.0f);
		default: return 0.0f;
		}
	}
	return static_cast<float>((Now - Trans.T0) * 1000.0);
}

void UTreadFrontEndWidget::FreezeTransitionForTest(const FString& Kind, float Progress)
{
	if (!bShownNow) return;
	const FString K = Kind.ToLower();
	if (K == TEXT("none") || K.IsEmpty())
	{
		if (Trans.Frozen >= 0.0f)
		{
			Trans = FFrontTrans();
			bChromeHold = false;
			Current = EFrontScreen::None;
			for (int32 Index = 4; Index >= 1; --Index)
			{
				if (Scr[Index].bOn) { Current = static_cast<EFrontScreen>(Index); break; }
			}
			SetChromeTargets(Current, false);
		}
		return;
	}
	bTickerPinned = true;
	const float P = Sat(Progress);
	const double Now = TUI::RealTime();
	if (K == TEXT("scan"))
	{
		SetLoadingProgressForTest(1.0f);
		Trans = FFrontTrans();
		Trans.Kind = EFrontTrans::Scan;
		Trans.From = EFrontScreen::Loading;
		Trans.To = EFrontScreen::Login;
		Trans.Frozen = P;
		EnterScreen(EFrontScreen::Login, TmScan, true);
	}
	else if (K == TEXT("slab"))
	{
		EFrontScreen From = Current;
		EFrontScreen To = EFrontScreen::Select;
		float Dir = 1.0f;
		FString Cap = TEXT("十六国战役"), Ru = TEXT("КАМПАНИЯ · Л.03");
		if (From == EFrontScreen::Select) { To = EFrontScreen::Login; Dir = -1.0f; Cap = TEXT("身份核验"); Ru = TEXT("ВЫХОД · Л.02"); }
		else if (From == EFrontScreen::Sortie) { To = EFrontScreen::Select; Dir = -1.0f; Ru = TEXT("НАЗАД · Л.03"); }
		else From = EFrontScreen::Login;
		JumpToScreenForTest(From == EFrontScreen::Login ? TEXT("login") : From == EFrontScreen::Select ? TEXT("select") : TEXT("sortie"));
		Trans = FFrontTrans();
		Trans.Kind = EFrontTrans::Slab;
		Trans.From = From;
		Trans.To = To;
		Trans.Dir = Dir;
		Trans.Cap = Cap;
		Trans.Ru = Ru;
		Trans.Frozen = P;
		bChromeHold = true;
		SetChromeTargets(To, true);
		const float Lag = 110.0f / TmSlab;
		if (Sat((P - Lag) / (1.0f - Lag)) >= 0.42f)
		{
			Trans.bSwapped = true;
			LeaveScreen(From);
			EnterScreen(To, 0.0f, true);
		}
	}
	else if (K == TEXT("blinds"))
	{
		JumpToScreenForTest(TEXT("select"));
		SortieStage = 1;
		for (const FFrontStage& S : Stages)
		{
			if (S.bUnlocked && !S.bConquered) { SortieStage = S.Index; break; }
		}
		Trans = FFrontTrans();
		Trans.Kind = EFrontTrans::Blinds;
		Trans.From = EFrontScreen::Select;
		Trans.To = EFrontScreen::Sortie;
		Trans.Frozen = P;
		if (P * (TmBlinds * 2.0f + 80.0f) >= TmBlinds)
		{
			Trans.bSwapped = true;
			LeaveScreen(EFrontScreen::Select);
			EnterScreen(EFrontScreen::Sortie, 0.0f, true);
			bSortieHold = true;
		}
	}
	(void)Now;
}

// ============================================================================================================
// Painting
// ============================================================================================================

/** RAII wrapper around FFrontPaint::Push for blocks that fade / slide on their own (dossier blocks, groups). */
struct FFrontPushScope
{
	FFrontPaint& P;
	FFrontPushScope(FFrontPaint& InP, float Scale, const FVector2f& Pivot, const FVector2f& Offset, float AlphaMul) : P(InP)
	{
		P.Push(Scale, Pivot, Offset, AlphaMul);
	}
	~FFrontPushScope() { P.Pop(); }
};

namespace
{
	FLinearColor Fade(const FLinearColor& C, float Mul) { return FLinearColor(C.R, C.G, C.B, C.A * Mul); }
	const FLinearColor White(1.0f, 1.0f, 1.0f, 1.0f);
}

int32 UTreadFrontEndWidget::PaintFrontEnd(const FGeometry& Geo, FSlateWindowElementList& Out, int32 LayerId) const
{
	if (!bShownNow) return LayerId;
	const FVector2f Size = Geo.GetLocalSize();
	if (Size.X < 8.0f || Size.Y < 8.0f) return LayerId;
	// Text is rasterised at the accumulated layout scale (viewport DPI scale): fonts and measurements must use it.
	TUI::SetPaintFontScale(Geo.GetAccumulatedLayoutTransform().GetScale());
	const float S = FMath::Max(0.01f, FMath::Min(Size.X / DW, Size.Y / DH));
	const FVector2f Orig((Size.X - DW * S) * 0.5f, (Size.Y - DH * S) * 0.5f);
	FFrontPaint P(Out, Geo, LayerId, S, Orig);
	const double Now = TUI::RealTime();

	bool bAny = false;
	for (int32 Index = 1; Index <= 4; ++Index) bAny |= Scr[Index].bOn;
	if (bAny)
	{
		// Letterbox bars (HTML body background).
		TUI::Quad(Out, Geo, P.L(), FVector2f::ZeroVector, Size, FLinearColor::FromSRGBColor(FColor(0x0B, 0x09, 0x08, 0xFF)));
	}
	P.ClipRect(0.0f, 0.0f, DW, DH);

	// Screens in DOM order; the one revealed by the scan transition goes last, clipped above the scan line.
	const EFrontScreen ScanTo = Trans.Kind == EFrontTrans::Scan ? Trans.To : EFrontScreen::None;
	for (int32 Index = 1; Index <= 4; ++Index)
	{
		const EFrontScreen Which = static_cast<EFrontScreen>(Index);
		if (!Scr[Index].bOn || Which == ScanTo) continue;
		DrawScreen(P, Which, Now);
	}
	if (ScanTo != EFrontScreen::None && Scr[static_cast<int32>(ScanTo)].bOn)
	{
		const float ClipH = FMath::Clamp(ScanBarY(Now) + 92.0f, 0.0f, DH);
		P.ClipRect(0.0f, 0.0f, DW, ClipH);
		DrawScreen(P, ScanTo, Now);
		P.PopClip();
	}

	DrawTransitionFx(P, Now);
	if (bAny)
	{
		DrawChrome(P, Now);
		// Paper grain over everything (including the transition layers), then the vignette.
		P.Tiled(P.L(), TUI::ETex::Grain, 0.0f, 0.0f, DW, DH, White, 1024.0f);
		P.Tex(P.L(), TUI::ETex::Vignette, 0.0f, 0.0f, DW, DH, White);
	}
	P.PopClip();
	return P.Layer + 1;
}

void UTreadFrontEndWidget::DrawScreen(FFrontPaint& P, EFrontScreen Which, double Now) const
{
	const FFrontEnv Env = EnvFor(Which, Now);
	switch (Which)
	{
	case EFrontScreen::Loading: DrawLoading(P, Env); break;
	case EFrontScreen::Login: DrawLogin(P, Env); break;
	case EFrontScreen::Select: DrawSelect(P, Env); break;
	case EFrontScreen::Sortie: DrawSortie(P, Env); break;
	default: break;
	}
}

// ------------------------------------------------------------------------------------------------------------
// Loading (Л.01)
// ------------------------------------------------------------------------------------------------------------
void UTreadFrontEndWidget::DrawLoading(FFrontPaint& P, const FFrontEnv& Env) const
{
	const double Now = Env.Now;
	const float K = P.K;
	const float TtMs = FMath::Clamp(static_cast<float>((Now - LoadT0) * 1000.0), 0.0f, LoadStopMs);
	const float Prog = ProgAt(TtMs);
	const bool bFrozen = bLoadFrozen;

	P.Tex(P.L(), TUI::ETex::Paper, 0.0f, 0.0f, DW, DH, White);
	{
		const int32 L = P.L();
		P.Poly(L, { {1060.0f, 0.0f}, {1920.0f, 0.0f}, {1920.0f, 760.0f} }, TUI::Ink);
		P.Poly(L, { {996.0f, 0.0f}, {1010.0f, 0.0f}, {1920.0f, 804.2f}, {1920.0f, 816.5f} }, TUI::Red);
	}
	{
		FFrontIn A(P, Env, EFrontIn::Scale, 0.0f, 0.0f, 260.0f, 150.0f, 600.0f, 600.0f);
		if (A.bShown)
		{
			P.Tex(P.L(), TUI::ETex::Disc, 260.0f, 150.0f, 600.0f, 600.0f, TUI::Red);
			P.Tex(P.L(), TUI::ETex::DiscShade, 260.0f, 150.0f, 600.0f, 600.0f, Fade(TUI::RedD, 0.8f));
		}
	}
	TUI::SignalRings(P.Out, P.Geo, P.L(), P.Pt(560.0f, 450.0f), 306.0f * K, TUI::Ink, TUI::Red, Now, 5.0f, 0.6f, 150.0f * K, K, false, false);
	{
		FFrontIn A(P, Env, EFrontIn::Wipe, 120.0f, 900.0f, 150.0f, 182.0f, 860.0f, 449.0f);
		if (A.bShown) P.Tex(P.L(), TUI::ETex::Logo, 162.0f, 191.0f, 860.0f, 449.0f, TUI::Red);
	}
	{
		FFrontIn A(P, Env, EFrontIn::Wipe, 300.0f, 900.0f, 150.0f, 182.0f, 860.0f, 449.0f);
		if (A.bShown) P.Tex(P.L(), TUI::ETex::Logo, 150.0f, 182.0f, 860.0f, 449.0f, TUI::Ink);
	}
	{
		// Vertical ТРЕАД, rotated -90 degrees about the centre of its 600x150 box.
		FFrontIn A(P, Env, EFrontIn::Up, 420.0f, 0.0f, 0.0f, 160.0f, 130.0f, 600.0f);
		if (A.bShown) P.Text(P.L(), TEXT("ТРЕАД"), TUI::EFontRole::Russo, 150.0f, 48.0f, 460.0f, TUI::Red, 0.0f, 0.5f, -90.0f);
	}
	{
		// Slogan bar: ink strip rotated -2.5 degrees about its bottom-left corner, hard red shadow (12,10).
		FFrontIn A(P, Env, EFrontIn::Wipe, 620.0f, 0.0f, 120.0f, 680.0f, 720.0f, 92.0f);
		if (A.bShown)
		{
			const FVector2f Pivot(120.0f, 772.0f);
			const float Ang = -2.5f;
			P.RotBox(P.L(), 132.0f, 690.0f, 720.0f, 92.0f, Pivot, Ang, TUI::Red);
			P.RotBox(P.L(), 120.0f, 680.0f, 720.0f, 92.0f, Pivot, Ang, TUI::Ink);
			const int32 LT = P.L();
			const FString Slogan = TEXT("一步一国，踏平旧世界。");
			const float Ws = P.TextW(Slogan, TUI::EFontRole::Serif, 56.0f, 0.02f);
			const FVector2f A1 = RotAbout(FVector2f(154.0f, 726.0f), Pivot, Ang);
			P.Text(LT, Slogan, TUI::EFontRole::Serif, 56.0f, A1.X, A1.Y, TUI::PaperL, 0.02f, 0.0f, Ang);
			const FVector2f A2 = RotAbout(FVector2f(154.0f + Ws + 18.0f, 726.0f), Pivot, Ang);
			P.Text(LT, TEXT("★"), TUI::EFontRole::SansBlack, 40.0f, A2.X, A2.Y, TUI::RedHi, 0.0f, 0.0f, Ang);
		}
	}
	{
		FFrontIn A(P, Env, EFrontIn::Left, 740.0f, 0.0f, 150.0f, 788.0f, 700.0f, 26.0f);
		if (A.bShown) P.Text(P.L(), TEXT("ШАГ ЗА ШАГОМ — СТРАНА ЗА СТРАНОЙ"), TUI::EFontRole::Russo, 22.0f, 150.0f, 801.0f, TUI::Red, 0.24f);
	}
	{
		// Tag line: texts separated by red stars, the last tag is a red pill.
		FFrontIn A(P, Env, EFrontIn::Up, 840.0f, 0.0f, 150.0f, 824.0f, 700.0f, 40.0f);
		if (A.bShown)
		{
			const int32 LB = P.L();
			const int32 LT = P.L();
			float X = 150.0f;
			const float CenterY = 844.0f;
			auto Item = [&](const TCHAR* Value)
			{
				P.Text(LT, Value, TUI::EFontRole::SansBlack, 23.0f, X, CenterY, TUI::Ink, 0.1f);
				X += P.TextW(Value, TUI::EFontRole::SansBlack, 23.0f, 0.1f) + 14.0f;
			};
			auto StarItem = [&]()
			{
				P.Text(LT, TEXT("★"), TUI::EFontRole::SansBlack, 20.0f, X, CenterY, TUI::Red);
				X += P.TextW(TEXT("★"), TUI::EFontRole::SansBlack, 20.0f) + 14.0f;
			};
			Item(TEXT("十六国战役")); StarItem(); Item(TEXT("十二回合")); StarItem(); Item(TEXT("四人对局")); StarItem();
			const FString Pill = TEXT("巨大少女自走棋");
			const float Wp = P.TextW(Pill, TUI::EFontRole::SansBlack, 23.0f, 0.1f);
			P.Box(LB, X, 824.0f, Wp + 24.0f, 40.0f, TUI::Red);
			P.Text(LT, Pill, TUI::EFontRole::SansBlack, 23.0f, X + 12.0f, CenterY, TUI::PaperL, 0.1f);
		}
	}

	// ---- terminal log panel
	{
		FFrontIn A(P, Env, EFrontIn::WipeV, 260.0f, 820.0f, 1220.0f, 112.0f, 620.0f, 600.0f);
		if (A.bShown)
		{
			const float PX = 1220.0f, PY = 112.0f, PW = 620.0f;
			P.CutBox(P.L(), PX, PY, PW, 600.0f, TUI::PaperL, 30.0f, TUI::ECorner::TL, 3.0f, TUI::Ink);
			P.CutBox(P.L(), PX + 3.0f, PY + 3.0f, PW - 6.0f, 54.0f, TUI::Ink, 28.2f, TUI::ECorner::TL);
			const int32 LH = P.L();
			const float HeadCy = PY + 3.0f + 27.0f;
			const float Hx = PX + 3.0f + 40.0f;
			P.Text(LH, TEXT("终端日志"), TUI::EFontRole::SansBlack, 24.0f, Hx, HeadCy, TUI::PaperL, 0.1f);
			const float W1 = P.TextW(TEXT("终端日志"), TUI::EFontRole::SansBlack, 24.0f, 0.1f);
			P.Text(LH, TEXT("ЖУРНАЛ"), TUI::EFontRole::Russo, 17.0f, Hx + W1 + 14.0f, HeadCy + 1.0f, TUI::RedL, 0.14f);
			const int32 TimeMin = FMath::FloorToInt(TtMs / 60000.0f);
			const FString TimeText = FString::Printf(TEXT("%02d:%02d.%02d"), TimeMin, FMath::FloorToInt(TtMs / 1000.0f) % 60, FMath::FloorToInt(TtMs / 10.0f) % 100);
			const float Rx = PX + PW - 3.0f - 22.0f;
			const float Wt = P.TextW(TimeText, TUI::EFontRole::Mono, 14.0f, 0.08f);
			const float Wr = P.TextW(TEXT("REC · T+"), TUI::EFontRole::Mono, 14.0f, 0.08f);
			P.Text(LH, TimeText, TUI::EFontRole::Mono, 14.0f, Rx - Wt, HeadCy, TUI::PaperL, 0.08f);
			P.Text(LH, TEXT("REC · T+"), TUI::EFontRole::Mono, 14.0f, Rx - Wt - 8.0f - Wr, HeadCy, TUI::PaperL, 0.08f);
			// REC dot (CSS .rec 11px, blink steps(1)): kept on while the test hooks pin the ticker so captures always show it.
			// Own layer above the header text so it can never be batched under it.
			if (bTickerPinned || BlinkMostlyOn(Now, 1.0)) P.Circle(P.L(), Rx - Wt - 8.0f - Wr - 8.0f - 5.5f, HeadCy, 5.5f, TUI::RedL);

			// Log body: bottom anchored rows that scroll up by one row whenever a line is added.
			const float BodyX = PX + 3.0f, BodyW = PW - 6.0f, BodyTop = PY + 3.0f + 62.0f, BodyH = 462.0f;
			const float BodyBottom = BodyTop + BodyH;
			int32 Shown = 0;
			while (Shown < LogRowCount && LogRows[Shown].Ms <= TtMs) ++Shown;
			P.ClipRect(BodyX, BodyTop, BodyW, BodyH);
			{
				const int32 LRect = P.L();
				const int32 LText = P.L();
				FRectBatch Batch(P.Geo);
				for (float Y = BodyTop + 32.0f; Y < BodyBottom; Y += 27.0f)
					Batch.Rect(P.Pt(BodyX, Y), P.Sz(BodyW, P.Hair()), P.Col(TUI::InkA(0.2f)));
				Batch.Rect(P.Pt(BodyX + 104.0f, BodyTop), P.Sz(2.0f, BodyH), P.Col(TUI::WithAlpha(TUI::Red, 0.35f)));

				const float LastElapsed = Shown > 0 ? (bFrozen ? 1.0e6f : TtMs - LogRows[Shown - 1].Ms) : 1.0e6f;
				const float Scroll = 27.0f * (1.0f - TUI::Ease::CssOut(Sat(LastElapsed / 260.0f)));
				for (int32 Row = 0; Row < Shown; ++Row)
				{
					const FLogRow& R = LogRows[Row];
					const float E = bFrozen ? 1.0e6f : TtMs - R.Ms;
					const float RowBottom = BodyBottom - 10.0f - 27.0f * (Shown - 1 - Row) + Scroll;
					if (RowBottom < BodyTop || RowBottom - 27.0f > BodyBottom) continue;
					const float Cy = RowBottom - 13.5f;
					const float RA = TUI::Ease::CssOut(Sat(E / 260.0f));
					const float X0 = BodyX + 22.0f - 14.0f * (1.0f - RA);
					const bool bFinal = FCString::Strcmp(R.Status, TEXT("★")) == 0;
					const bool bWarn = FCString::Strcmp(R.Status, TEXT("WARN")) == 0;
					const FString TimeTag = FString::Printf(TEXT("[%02d.%03d]"), R.Ms / 1000, R.Ms % 1000);
					P.Text(LText, TimeTag, TUI::EFontRole::Mono, 14.0f, X0, Cy, Fade(TUI::InkA(0.7f), RA));
					float X = X0 + 96.0f;
					const FString Head = R.Bold;
					const FString Body = R.Text;
					if (bFinal)
					{
						P.Text(LText, Body, TUI::EFontRole::MonoBold, 16.0f, X, Cy, Fade(TUI::Red, RA));
						X += P.TextW(Body, TUI::EFontRole::MonoBold, 16.0f);
					}
					else
					{
						if (!Head.IsEmpty())
						{
							P.Text(LText, Head, TUI::EFontRole::MonoBold, 16.0f, X, Cy, Fade(TUI::Red, RA));
							X += P.TextW(Head, TUI::EFontRole::MonoBold, 16.0f);
						}
						P.Text(LText, Body, TUI::EFontRole::Mono, 16.0f, X, Cy, Fade(TUI::Ink, RA));
						X += P.TextW(Body, TUI::EFontRole::Mono, 16.0f);
					}
					const FString Status = R.Status;
					if (!Status.IsEmpty())
					{
						const float SA = TUI::Ease::CssOut(Sat((E - 260.0f) / 160.0f));
						const float Sx = -14.0f * (1.0f - SA);
						const float Ws = P.TextW(Status, TUI::EFontRole::MonoBold, 16.0f);
						const float BoxW = bWarn ? Ws + 14.0f : Ws;
						const float StatusLeft = PX + PW - 3.0f - 22.0f - BoxW + Sx;
						if (bWarn)
						{
							Batch.Rect(P.Pt(StatusLeft, Cy - 11.0f), P.Sz(BoxW, 22.0f), P.Col(TUI::Red, SA));
							P.Text(LText, Status, TUI::EFontRole::MonoBold, 16.0f, StatusLeft + 7.0f, Cy, Fade(TUI::PaperL, SA));
						}
						else
						{
							P.Text(LText, Status, TUI::EFontRole::MonoBold, 16.0f, StatusLeft, Cy, Fade(TUI::Ink, SA));
						}
						// Dotted leader grows from the left (scaleX 0 -> 1).
						const float LeadFrom = X + 10.0f;
						const float LeadTo = StatusLeft - 10.0f;
						const float Grow = TUI::Ease::CssOut(Sat((E - 90.0f) / 240.0f));
						const float LeadEnd = LeadFrom + (LeadTo - LeadFrom) * Grow;
						for (float Dx = LeadFrom; Dx + 2.0f <= LeadEnd; Dx += 4.0f)
							Batch.Rect(P.Pt(Dx, Cy - 1.0f), P.Sz(2.0f, 2.0f), P.Col(TUI::InkA(0.3f), RA));
					}
				}
				Batch.Flush(P.Out, LRect);
			}
			P.PopClip();

			// Footer: carrier wave and read-out.
			P.Box(P.L(), BodyX, PY + 3.0f + 524.0f, BodyW, 2.0f, TUI::Ink);
			TUI::Wave(P.Out, P.Geo, P.L(), P.Pt(PX + 3.0f, PY + 3.0f + 524.0f + 18.0f), P.Sz(614.0f, 52.0f), P.Col(TUI::Ink), P.Col(TUI::Red), Now, 13.0f * K, K);
			{
				const int32 LF = P.L();
				float X = PX + 3.0f + 22.0f;
				const float Cy = PY + 3.0f + 524.0f + 2.0f + 8.0f + 7.5f;
				const FString A1 = TEXT("载波 · CARRIER ");
				P.Text(LF, A1, TUI::EFontRole::Mono, 15.0f, X, Cy, TUI::InkA(0.7f), 0.1f);
				X += P.TextW(A1, TUI::EFontRole::Mono, 15.0f, 0.1f);
				P.Text(LF, PmHz, TUI::EFontRole::MonoBold, 15.0f, X, Cy, TUI::Red, 0.1f);
				X += P.TextW(PmHz, TUI::EFontRole::MonoBold, 15.0f, 0.1f);
				P.Text(LF, TEXT(" kHz"), TUI::EFontRole::Mono, 15.0f, X, Cy, TUI::InkA(0.7f), 0.1f);
			}
		}
	}
	if (bLoadReady && LoadReadyT >= 0.0)
	{
		const float Sec = static_cast<float>(Now - LoadReadyT);
		TUI::Stamp(P.Out, P.Geo, P.L(), TUI::ETex::StampReady, P.Pt(878.0f + 159.0f, 652.0f + 53.0f), P.Sz(318.0f, 106.0f), P.Col(TUI::Red), -10.0f, Sec);
	}

	// ---- parameter read-outs
	{
		FFrontIn A(P, Env, EFrontIn::Up, 520.0f, 0.0f, 1220.0f, 734.0f, 620.0f, 80.0f);
		if (A.bShown)
		{
			const int32 LR = P.L();
			const int32 LT = P.L();
			P.Box(LR, 1220.0f, 734.0f, 620.0f, 3.0f, TUI::Ink);
			static const TCHAR* const Labels[4] = { TEXT("吞吐 I/O · MB/s"), TEXT("同步 SYNC · %"), TEXT("档案块 BLK"), TEXT("温度 TEMP · °C") };
			const FString* Values[4] = { &PmIo, &PmSync, &PmBlk, &PmTemp };
			for (int32 Index = 0; Index < 4; ++Index)
			{
				const float X = 1220.0f + Index * 155.0f;
				if (Index > 0) P.Box(LR, X, 737.0f, P.Hair(), 77.0f, TUI::InkA(0.3f));
				P.Text(LT, Labels[Index], TUI::EFontRole::Mono, 15.0f, X + 14.0f, 754.5f, TUI::Ink, 0.02f);
				P.Text(LT, *Values[Index], TUI::EFontRole::Stencil, 46.0f, X + 14.0f, 791.0f, TUI::Ink, 0.02f);
			}
		}
	}
	{
		FFrontIn A(P, Env, EFrontIn::Up, 560.0f, 0.0f, 112.0f, 894.0f, 400.0f, 130.0f);
		if (A.bShown)
		{
			const FString Pct = FString::Printf(TEXT("%03d"), FMath::FloorToInt(Prog * 100.0f + 0.0001f));
			const int32 L = P.L();
			P.Text(L, Pct, TUI::EFontRole::Stencil, 166.0f, 112.0f, 958.7f, TUI::Red, -0.01f);
			const float W = P.TextW(Pct, TUI::EFontRole::Stencil, 166.0f, -0.01f);
			P.Text(L, TEXT("%"), TUI::EFontRole::Stencil, 70.0f, 112.0f + W + 8.0f, 931.0f, TUI::Ink);
		}
	}
	{
		FFrontIn A(P, Env, EFrontIn::Wipe, 640.0f, 900.0f, 520.0f, 898.0f, 1320.0f, 120.0f);
		if (A.bShown)
		{
			const int32 L = P.L();
			P.Text(L, TEXT("载入进度"), TUI::EFontRole::SansBlack, 24.0f, 520.0f, 912.0f, TUI::Ink, 0.12f);
			const float W1 = P.TextW(TEXT("载入进度"), TUI::EFontRole::SansBlack, 24.0f, 0.12f);
			P.Text(L, TEXT("ЗАГРУЗКА"), TUI::EFontRole::Russo, 16.0f, 520.0f + W1 + 14.0f, 914.0f, TUI::Red, 0.16f);
			FString Task = TEXT("初始化终端");
			int32 Shown = 0;
			while (Shown < LogRowCount && LogRows[Shown].Ms <= TtMs) ++Shown;
			if (Shown > 0) Task = FString(LogRows[Shown - 1].Bold) + LogRows[Shown - 1].Text;
			P.Text(L, Task, TUI::EFontRole::Mono, 16.0f, 1840.0f, 913.0f, TUI::InkA(0.7f), 0.0f, 1.0f);
			TUI::SegBar(P.Out, P.Geo, P.L(), P.Pt(520.0f, 936.0f), P.Sz(1320.0f, 42.0f), 50, Prog, P.Col(TUI::Red), P.Col(TUI::InkA(0.12f)),
				2.0f * K, 4.0f * K, P.Col(TUI::InkA(0.3f)), Now, P.Col(TUI::Ink));
			const int32 LT = P.L();
			P.Box(LT, 520.0f, 984.0f, 1320.0f, 2.0f, TUI::Ink);
			for (int32 Index = 0; Index <= 10; ++Index)
			{
				const float X = 520.0f + Index * 132.0f;
				P.Box(LT, X - 1.0f, 986.0f, 2.0f, 8.0f, TUI::Ink);
				P.Text(LT, Index == 10 ? TEXT("100") : *Pad2(Index * 10), TUI::EFontRole::MonoBold, 15.0f, X, 1005.5f, TUI::Ink, 0.0f, 0.5f);
			}
		}
	}
}

// ------------------------------------------------------------------------------------------------------------
// Login (Л.02)
// ------------------------------------------------------------------------------------------------------------
void UTreadFrontEndWidget::DrawLogin(FFrontPaint& P, const FFrontEnv& Env) const
{
	const double Now = Env.Now;
	const float K = P.K;
	const bool bVerifying = LoginPhase == EFrontLogin::Verifying;
	const float LoginMs = bVerifying ? static_cast<float>((Now - LoginT0) * 1000.0) : -1.0f;

	P.Tex(P.L(), TUI::ETex::Paper, 0.0f, 0.0f, DW, DH, White);
	{
		const int32 L = P.L();
		P.Poly(L, { {1920.0f, 820.0f}, {1920.0f, 1080.0f}, {1260.0f, 1080.0f} }, TUI::Ink);
		P.Star(P.L(), StarBig, FVector2f(1806.0f, 948.0f), 0.62f, -14.0f, TUI::Red);
	}
	{
		const int32 L = P.L();
		P.Poly(L, { {0.0f, 0.0f}, {1080.0f, 0.0f}, {880.0f, 1080.0f}, {0.0f, 1080.0f} }, TUI::Ink);
		P.Poly(L, { {1104.0f, 0.0f}, {1116.0f, 0.0f}, {916.0f, 1080.0f}, {904.0f, 1080.0f} }, TUI::Red);
	}

	// Ticker: red strip with a looping line of text, clipped to its slanted shape.
	{
		P.Poly(P.L(), { {1104.0f, 114.0f}, {1920.0f, 114.0f}, {1920.0f, 154.0f}, {1096.6f, 154.0f} }, TUI::Red);
		P.ClipQuad(FVector2f(1104.0f, 114.0f), FVector2f(1920.0f, 114.0f), FVector2f(1096.6f, 154.0f), FVector2f(1920.0f, 154.0f));
		struct FPiece { const TCHAR* Text; bool bRu; };
		static const FPiece Spans[][2] = {
			{ { TEXT("身份核验 "), false }, { TEXT("ИДЕНТИФИКАЦИЯ"), true } }, { { TEXT("★ 原型终端 · 无后端"), false }, { nullptr, false } },
			{ { TEXT("任意代号与口令均可通过 ★"), false }, { nullptr, false } }, { { TEXT("ШАГ ЗА ШАГОМ"), true }, { nullptr, false } },
			{ { TEXT("一步一国 ★"), false }, { nullptr, false } }, { { TEXT("十六国 · 十二回合 · 四人对局"), false }, { nullptr, false } } };
		auto SpanWidth = [&P](const FPiece (&Span)[2])
		{
			float W = 34.0f;
			for (const FPiece& Piece : Span)
			{
				if (!Piece.Text) continue;
				W += Piece.bRu ? P.TextW(Piece.Text, TUI::EFontRole::Russo, 15.0f, 0.2f) : P.TextW(Piece.Text, TUI::EFontRole::SansBold, 17.0f, 0.16f);
			}
			return W;
		};
		float Total = 0.0f;
		for (const FPiece (&Span)[2] : Spans) Total += SpanWidth(Span);
		const float Shift = -(Total + 19.0f) * (bTickerPinned ? 0.0f : static_cast<float>(FMath::Fmod(Now - Env.T0, 46.0) / 46.0));
		const int32 L = P.L();
		float X = 1096.0f + 38.0f + Shift;
		for (int32 Repeat = 0; Repeat < 2; ++Repeat)
		{
			for (const FPiece (&Span)[2] : Spans)
			{
				const float SpanW = SpanWidth(Span);
				if (X + SpanW > 1090.0f && X < 1925.0f)
				{
					float Px = X;
					for (const FPiece& Piece : Span)
					{
						if (!Piece.Text) continue;
						if (Piece.bRu)
						{
							P.Text(L, Piece.Text, TUI::EFontRole::Russo, 15.0f, Px, 135.0f, TUI::Ink, 0.2f);
							Px += P.TextW(Piece.Text, TUI::EFontRole::Russo, 15.0f, 0.2f);
						}
						else
						{
							P.Text(L, Piece.Text, TUI::EFontRole::SansBold, 17.0f, Px, 134.0f, TUI::PaperL, 0.16f);
							Px += P.TextW(Piece.Text, TUI::EFontRole::SansBold, 17.0f, 0.16f);
						}
					}
				}
				X += SpanW;
			}
		}
		P.PopClip();
	}
	{
		FFrontIn A(P, Env, EFrontIn::Scale, 80.0f, 0.0f, 335.0f, 280.0f, 560.0f, 560.0f);
		if (A.bShown)
		{
			P.Tex(P.L(), TUI::ETex::Disc, 335.0f, 280.0f, 560.0f, 560.0f, TUI::PaperL);
			P.Tex(P.L(), TUI::ETex::DiscShade, 335.0f, 280.0f, 560.0f, 560.0f, Fade(TUI::PaperD, 0.9f));
		}
	}
	TUI::SignalRings(P.Out, P.Geo, P.L(), P.Pt(615.0f, 560.0f), 290.0f * K, TUI::PaperL, TUI::RedL, Now, -4.0f, 0.5f, 120.0f * K, K, false, false);
	{
		// The giantess is red and clipped to the black slanted block.
		P.ClipQuad(FVector2f(0.0f, 0.0f), FVector2f(1080.0f, 0.0f), FVector2f(0.0f, 1080.0f), FVector2f(880.0f, 1080.0f));
		FFrontIn A(P, Env, EFrontIn::Up, 160.0f, 900.0f, 300.0f, 300.0f, 625.0f, 780.0f);
		if (A.bShown) P.Tex(P.L(), TUI::ETex::Giantess, 300.0f, 300.0f, 625.0f, 780.0f, TUI::Red);
		P.PopClip();
	}
	TUI::Particles(P.Out, P.Geo, P.L(), P.Pt(0.0f, 0.0f), P.Sz(1000.0f, 1080.0f), 46, TUI::PaperL, 0.5f * P.A, Now, K);
	{
		FFrontIn A(P, Env, EFrontIn::Wipe, 100.0f, 0.0f, 84.0f, 62.0f, 470.0f, 245.0f);
		if (A.bShown) P.Tex(P.L(), TUI::ETex::Logo, 94.0f, 70.0f, 470.0f, 245.0f, TUI::Red);
	}
	{
		FFrontIn A(P, Env, EFrontIn::Wipe, 240.0f, 0.0f, 84.0f, 62.0f, 470.0f, 245.0f);
		if (A.bShown) P.Tex(P.L(), TUI::ETex::Logo, 84.0f, 62.0f, 470.0f, 245.0f, TUI::PaperL);
	}
	{
		FFrontIn A(P, Env, EFrontIn::Left, 360.0f, 0.0f, 92.0f, 322.0f, 300.0f, 40.0f);
		if (A.bShown) P.Text(P.L(), TEXT("ТРЕАД"), TUI::EFontRole::Russo, 40.0f, 92.0f, 342.0f, TUI::Red, 0.32f);
	}
	{
		FFrontIn A(P, Env, EFrontIn::Left, 420.0f, 0.0f, 94.0f, 378.0f, 500.0f, 20.0f);
		if (A.bShown) P.Text(P.L(), TEXT("Л.02 · 两色套印 · 印数 0417"), TUI::EFontRole::Mono, 15.0f, 94.0f, 388.0f, TUI::PaperLA(0.7f), 0.2f);
	}
	{
		// Vertical slogan: four stacked Serif glyphs.
		FFrontIn A(P, Env, EFrontIn::Down, 300.0f, 0.0f, 846.0f, 82.0f, 100.0f, 400.0f);
		if (A.bShown)
		{
			const int32 L = P.L();
			static const TCHAR* const Glyphs[4] = { TEXT("一"), TEXT("步"), TEXT("一"), TEXT("国") };
			for (int32 Index = 0; Index < 4; ++Index)
				P.Text(L, Glyphs[Index], TUI::EFontRole::Serif, 100.0f, 896.0f, 132.0f + Index * 100.0f, TUI::Red, 0.0f, 0.5f);
		}
	}
	{
		FFrontIn A(P, Env, EFrontIn::Fade, 520.0f, 0.0f, 958.0f, 330.0f, 1.0f, 1.0f);
		if (A.bShown) P.Text(P.L(), TEXT("ВПЕРЁД!"), TUI::EFontRole::Russo, 24.0f, 958.0f, 330.0f, TUI::PaperLA(0.7f), 0.24f, 0.5f, 90.0f);
	}
	{
		FFrontIn A(P, Env, EFrontIn::Fade, 600.0f, 0.0f, 1027.0f, 612.0f, 1.0f, 1.0f);
		if (A.bShown)
			P.Text(P.L(), TEXT("巨人们，前进！ ★ ВЕЛИКАНЫ, ВПЕРЁД! ★ 一步一国 ★ ШАГ ЗА ШАГОМ ★"), TUI::EFontRole::SansBold, 17.0f, 1027.0f, 612.0f,
				TUI::Ink, 0.3f, 0.5f, -79.5f);
	}

	// ---- form (shakes as a whole after the stamp)
	{
		const FVector2f Shake = ShakeOffset(Now);
		FFrontPushScope Shaking(P, 1.0f, FVector2f::ZeroVector, Shake, 1.0f);
		const float FX = 1180.0f, FY = 196.0f;
		{
			FFrontIn A(P, Env, EFrontIn::Fade, 200.0f, 0.0f, FX, FY, 620.0f, 16.0f);
			if (A.bShown)
			{
				const int32 L = P.L();
				float X = FX;
				P.Text(L, TEXT("Л.02"), TUI::EFontRole::MonoBold, 15.0f, X, FY + 7.5f, TUI::Red, 0.14f);
				X += P.TextW(TEXT("Л.02"), TUI::EFontRole::MonoBold, 15.0f, 0.14f) + 14.0f;
				const FString Sec = TEXT("СЕКЦИЯ · 身份核验");
				P.Text(L, Sec, TUI::EFontRole::Mono, 15.0f, X, FY + 7.5f, TUI::InkA(0.55f), 0.14f);
				X += P.TextW(Sec, TUI::EFontRole::Mono, 15.0f, 0.14f) + 14.0f;
				P.Box(L, X, FY + 6.5f, FX + 620.0f - X, 2.0f, TUI::InkA(0.3f));
			}
		}
		{
			FFrontIn A(P, Env, EFrontIn::Wipe, 260.0f, 0.0f, FX, FY + 28.0f, 620.0f, 96.0f);
			if (A.bShown)
			{
				const int32 L = P.L();
				const float Wb = P.TextW(TEXT("身份核验"), TUI::EFontRole::SansBlack, 96.0f, -0.01f);
				P.Text(L, TEXT("身份核验"), TUI::EFontRole::SansBlack, 96.0f, FX, FY + 28.0f + 48.0f, TUI::Ink, -0.01f);
				const float Dx = FX + Wb + 20.0f;
				P.Text(L, TEXT("ИДЕНТИФИКАЦИЯ"), TUI::EFontRole::Russo, 19.0f, Dx, 253.0f, TUI::Red, 0.1f);
				P.Text(L, TEXT("ОПЕРАТОРА"), TUI::EFontRole::Russo, 19.0f, Dx, 277.7f, TUI::Ink, 0.1f);
				P.Text(L, TEXT("ACCESS · LEVEL Б"), TUI::EFontRole::Mono, 14.0f, Dx, 303.0f, TUI::InkA(0.55f), 0.14f);
			}
		}
		{
			FFrontIn A(P, Env, EFrontIn::Up, 340.0f, 0.0f, FX, FY + 146.0f, 620.0f, 30.0f);
			if (A.bShown) P.Text(P.L(), TEXT("核验行军档案终端的操作员身份。原型阶段：任意代号与口令均可通过。"), TUI::EFontRole::SansMedium, 19.0f, FX, 356.0f, TUI::InkA(0.7f));
		}
		{
			FFrontIn A(P, Env, EFrontIn::Wipe, 380.0f, 0.0f, FX, FY + 190.0f, 620.0f, 16.0f);
			if (A.bShown) TUI::Ruler(P.Out, P.Geo, P.L(), P.Pt(FX, FY + 190.0f), 620.0f * K, P.Col(TUI::Ink), K);
		}

		// Input fields: drawn frame, labels, counter; the text itself comes from the real text box while it is live.
		const bool bLive = AreInputsLive();
		const bool bLocked = bVerifying;
		for (int32 Index = 0; Index < 2; ++Index)
		{
			const float Top = FY + (Index == 0 ? 226.0f : 364.0f);
			const float Delay = Index == 0 ? 440.0f : 520.0f;
			FFrontIn A(P, Env, EFrontIn::Up, Delay, 0.0f, FX, Top, 620.0f, 126.0f);
			if (!A.bShown) continue;
			const int32 LS = P.L(), LB = P.L(), LF = P.L(), LR = P.L(), LU = P.L(), LT = P.L();
			const FString CnLabel = Index == 0 ? TEXT("代号") : TEXT("口令");
			const FString RuLabel = Index == 0 ? TEXT("ПОЗЫВНОЙ") : TEXT("ПАРОЛЬ");
			const FString EnLabel = Index == 0 ? TEXT("F-01 · CALLSIGN") : TEXT("F-02 · PASSWORD");
			P.Text(LT, CnLabel, TUI::EFontRole::SansBlack, 28.0f, FX, Top + 16.0f, TUI::Ink);
			const float Wc = P.TextW(CnLabel, TUI::EFontRole::SansBlack, 28.0f);
			P.Text(LT, RuLabel, TUI::EFontRole::Cond, 16.0f, FX + Wc + 12.0f, Top + 20.0f, TUI::InkA(0.55f), 0.24f);
			if (!bLocked) P.Text(LT, EnLabel, TUI::EFontRole::Mono, 14.0f, FX + 620.0f, Top + 20.5f, TUI::InkA(0.55f), 0.08f, 1.0f);

			const float By = Top + 40.0f;
			P.Box(LS, FX + 8.0f, By + 8.0f, 620.0f, 76.0f, TUI::Ink);
			P.Box(LB, FX, By, 620.0f, 76.0f, TUI::Ink);
			P.Box(LF, FX + 4.0f, By + 4.0f, 612.0f, 68.0f, bLocked ? TUI::PaperDD : TUI::PaperL);
			const float BarW = 12.0f + (bLocked ? 0.0f : 10.0f * TUI::Ease::CssOut(FocusBar[Index]));
			P.Box(LR, FX + 4.0f, By + 4.0f, BarW, 68.0f, bLocked ? TUI::Ink : TUI::Red);
			if (!bLocked && FocusLine[Index] > 0.001f)
				P.Box(LU, FX + 1.0f, By + 77.0f, 618.0f * TUI::Ease::CssOut(FocusLine[Index]), 4.0f, TUI::Red);

			const int32 Len = Index == 0 ? CallsignValue.Len() : PasswordLen;
			if (!bLocked)
				P.Text(LT, FString::Printf(TEXT("%s/%d"), *Pad2(Len), Index == 0 ? 16 : 24), TUI::EFontRole::Mono, 13.0f, FX + 612.0f - 14.0f + 4.0f, By + 76.0f - 4.0f - 6.0f - 6.5f, TUI::InkA(0.55f), 0.06f, 1.0f);
			if (Len == 0 && !bLocked)
				P.Text(LT, Index == 0 ? TEXT("输入任意代号") : TEXT("输入任意口令"), TUI::EFontRole::Mono, 30.0f, FX + 46.0f, By + 38.0f, TUI::InkA(0.55f));
			else if (Index == 1 && Len > 0)
			{
				// Password bullets as in the browser (9 px dots on a 16 px pitch), painted whether or not the real box is live: the box
				// only supplies the caret and its glyphs are transparent (ApplyInputStyle).
				for (int32 Dot = 0; Dot < Len; ++Dot) P.Circle(LT, FX + 46.0f + 7.5f + 16.0f * Dot, By + 41.0f, 4.5f, TUI::Ink);
			}
			else if (!bLive && Len > 0)
			{
				// The real text box is hidden (transition running): paint its text so the name does not blink out.
				P.Text(LT, CallsignValue, TUI::EFontRole::Mono, 30.0f, FX + 46.0f, By + 38.0f, TUI::Ink);
			}
		}

		// Status lines / greeting.
		{
			FFrontIn A(P, Env, EFrontIn::Fade, 600.0f, 0.0f, FX, 694.0f, 620.0f, 56.0f);
			if (A.bShown)
			{
				const int32 L = P.L();
				if (LoginMs >= TmLoginGreet)
				{
					const float E = LoginMs - TmLoginGreet;
					const float Pg = TUI::Ease::CssOut(Sat(E / 620.0f));
					const FString G1 = TEXT("欢迎归队，"), G3 = TEXT(" 同志");
					const float W1 = P.TextW(G1, TUI::EFontRole::SansBlack, 36.0f);
					const float W2 = P.TextW(Commander, TUI::EFontRole::SansBlack, 36.0f);
					const float W3 = P.TextW(G3, TUI::EFontRole::SansBlack, 36.0f);
					P.ClipRect(FX - 20.0f, 694.0f - 20.0f, Pg * (W1 + W2 + W3 + 20.0f) + 20.0f, 76.0f);
					P.Text(L, G1, TUI::EFontRole::SansBlack, 36.0f, FX, 712.0f, TUI::Ink);
					P.Text(L, Commander, TUI::EFontRole::SansBlack, 36.0f, FX + W1, 712.0f, TUI::Red);
					P.Text(L, G3, TUI::EFontRole::SansBlack, 36.0f, FX + W1 + W2, 712.0f, TUI::Ink);
					P.PopClip();
				}
				else if (!bVerifying)
				{
					P.Text(L, TEXT("> 终端待命。请输入代号与口令。"), TUI::EFontRole::Mono, 15.0f, FX, 707.0f, TUI::InkA(0.7f));
					P.Text(L, TEXT("> 回车键亦可提交。"), TUI::EFontRole::Mono, 15.0f, FX, 733.0f, TUI::InkA(0.7f));
				}
				else
				{
					float X = FX;
					auto Piece = [&](const FString& S, TUI::EFontRole Role, const FLinearColor& C, float Cy)
					{
						P.Text(L, S, Role, 15.0f, X, Cy, C);
						X += P.TextW(S, Role, 15.0f);
					};
					Piece(TEXT("> 比对档案 · 代号 "), TUI::EFontRole::Mono, TUI::InkA(0.7f), 707.0f);
					Piece(Commander, TUI::EFontRole::MonoBold, TUI::Red, 707.0f);
					Piece(TEXT(" ··········· "), TUI::EFontRole::Mono, TUI::InkA(0.7f), 707.0f);
					Piece(TEXT("OK"), TUI::EFontRole::MonoBold, TUI::Ink, 707.0f);
					if (LoginMs >= TmLoginScan * 0.45f)
					{
						X = FX;
						Piece(TEXT("> 签发通行证 No.0417 ················ "), TUI::EFontRole::Mono, TUI::InkA(0.7f), 733.0f);
						Piece(TEXT("OK"), TUI::EFontRole::MonoBold, TUI::Ink, 733.0f);
					}
				}
			}
		}

		// Login button (primary): busy scan, then "准许 ★".
		{
			FFrontIn A(P, Env, EFrontIn::Up, 660.0f, 0.0f, FX, 762.0f, 620.0f, 108.0f);
			if (A.bShown && A.Alpha >= 0.5f)
			{
				FString Label = TEXT("登入"), Ru = TEXT("ВОЙТИ"), Arrow = TEXT("→");
				float ScanT = -1.0f;
				if (bVerifying)
				{
					if (LoginMs < TmLoginStamp) { Label = TEXT("核验中"); Ru = TEXT("ПРОВЕРКА"); ScanT = Sat(LoginMs / TmLoginScan); }
					else { Label = TEXT("准许"); Ru = TEXT("ДОПУЩЕН"); Arrow = TEXT("★"); }
				}
				TUI::FButtonLook Look;
				Look.Scale = K;
				Look.CutPx = 34.0f;
				Look.LabelPx = 50.0f;
				Look.TrackingEm = 0.3f;
				Look.Arrow = Arrow;
				Look.ScanT = ScanT;
				TUI::PrimaryButton(P.Out, P.Geo, P.Reserve(3), P.Pt(FX, 762.0f), P.Sz(620.0f, 108.0f), Label, Ru,
					bVerifying ? 0.0f : BtnHover[BtnLogin], true, Look);
			}
		}
		{
			FFrontIn A(P, Env, EFrontIn::Fade, 760.0f, 0.0f, FX, 890.0f, 620.0f, 16.0f);
			if (A.bShown)
			{
				// No face in the Mono stack has U+21B5 (it drew a tofu box), so the return arrow is stroked into one mono cell
				// between the two text runs, like the browser's small fallback glyph.
				const int32 L = P.L();
				const FLinearColor Tone = TUI::InkA(0.7f);
				const float Cy = 897.0f;
				P.Text(L, TEXT("ENTER"), TUI::EFontRole::Mono, 14.0f, FX, Cy, Tone, 0.1f);
				const float Space = P.SpaceW(TUI::EFontRole::Mono, 14.0f, 0.1f);
				const float CellX = FX + P.TextW(TEXT("ENTER"), TUI::EFontRole::Mono, 14.0f, 0.1f) + Space;
				const float CellW = P.TextW(TEXT("M"), TUI::EFontRole::Mono, 14.0f, 0.1f);
				const float Ax0 = CellX + CellW * 0.12f, Ax1 = CellX + CellW * 0.78f, Ay0 = Cy - 4.0f, Ay1 = Cy + 2.0f;
				const float Stroke = FMath::Max(1.0f, 1.3f * K);
				TUI::Lines(P.Out, P.Geo, L, { P.Pt(Ax1, Ay0), P.Pt(Ax1, Ay1), P.Pt(Ax0, Ay1) }, P.Col(Tone), Stroke);
				TUI::Lines(P.Out, P.Geo, L, { P.Pt(Ax0 + 3.0f, Ay1 - 3.0f), P.Pt(Ax0, Ay1), P.Pt(Ax0 + 3.0f, Ay1 + 3.0f) }, P.Col(Tone), Stroke);
				P.Text(L, TEXT("亦可登入 · 本原型不连接任何服务器"), TUI::EFontRole::Mono, 14.0f, CellX + CellW + Space, Cy, Tone, 0.1f);
			}
		}
	}

	// ---- approval stamp and ink splat (outside the shaking form, above it)
	if (bVerifying)
	{
		if (LoginMs >= 950.0f)
		{
			const float E = LoginMs - 950.0f;
			const float Ps = TUI::Ease::CssOut(Sat(E / 260.0f));
			P.Tex(P.L(), TUI::ETex::InkSplat, 1522.0f, 390.0f, 316.0f, 316.0f, Fade(TUI::RedD, 0.95f * Sat(E / 80.0f)), 0.0f, 0.5f + 0.5f * Ps);
		}
		if (LoginMs >= TmLoginStamp)
		{
			TUI::Stamp(P.Out, P.Geo, P.L(), TUI::ETex::StampApproved, P.Pt(1540.0f + 140.0f, 408.0f + 140.0f), P.Sz(280.0f, 280.0f), P.Col(TUI::Red),
				-14.0f, (LoginMs - TmLoginStamp) / 1000.0f);
		}
	}
}

// ------------------------------------------------------------------------------------------------------------
// Select (Л.03)
// ------------------------------------------------------------------------------------------------------------
void UTreadFrontEndWidget::DrawSelect(FFrontPaint& P, const FFrontEnv& Env) const
{
	const double Now = Env.Now;
	const float K = P.K;

	P.Tex(P.L(), TUI::ETex::Paper, 0.0f, 0.0f, DW, DH, White);
	{
		const int32 L = P.L();
		P.Poly(L, { {0.0f, 764.0f}, {1290.0f, 401.2f}, {1290.0f, 415.2f}, {0.0f, 778.0f} }, TUI::Ink);
		P.Poly(L, { {0.0f, 800.0f}, {1920.0f, 260.0f}, {1920.0f, 520.0f}, {0.0f, 1060.0f} }, TUI::Red);
	}
	{
		// Halftone dots on the lower part of the red band.
		P.ClipQuad(FVector2f(0.0f, 940.0f), FVector2f(1920.0f, 400.0f), FVector2f(0.0f, 1060.0f), FVector2f(1920.0f, 520.0f));
		P.Tiled(P.L(), TUI::ETex::Halftone, 0.0f, 0.0f, DW, DH, Fade(TUI::RedD, 0.7f), 24.0f);
		P.PopClip();
	}
	TUI::Particles(P.Out, P.Geo, P.L(), P.Pt(0.0f, 0.0f), P.Sz(DW, DH), 34, TUI::Ink, 0.35f * P.A, Now, K);

	{
		FFrontIn A(P, Env, EFrontIn::Scale, 60.0f, 0.0f, 96.0f, 70.0f, 112.0f, 112.0f);
		if (A.bShown)
		{
			P.Box(P.L(), 96.0f, 70.0f, 112.0f, 112.0f, TUI::Red);
			P.Star(P.L(), StarSmall, FVector2f(152.0f, 126.0f), 0.76f, 0.0f, TUI::PaperL);
		}
	}
	{
		const float W = P.TextW(TEXT("十六国战役"), TUI::EFontRole::SansBlack, 104.0f);
		FFrontIn A(P, Env, EFrontIn::Wipe, 120.0f, 0.0f, 228.0f, 62.0f, W, 104.0f);
		if (A.bShown) P.Text(P.L(), TEXT("十六国战役"), TUI::EFontRole::SansBlack, 104.0f, 228.0f, 114.0f, TUI::Ink);
	}
	{
		FFrontIn A(P, Env, EFrontIn::Up, 240.0f, 0.0f, 232.0f, 178.0f, 600.0f, 24.0f);
		if (A.bShown)
		{
			const int32 L = P.L();
			// HTML: "КАМПАНИЯ · 16 СТРАН — <b>选择作战目标</b>", one space (advance + tracking) between the two inline segments.
			const FString S1 = TEXT("КАМПАНИЯ · 16 СТРАН —");
			const float Space = P.SpaceW(TUI::EFontRole::Cond, 20.0f, 0.24f);
			P.Text(L, S1, TUI::EFontRole::Cond, 20.0f, 232.0f, 193.0f, TUI::InkA(0.7f), 0.24f);
			P.Text(L, TEXT("选择作战目标"), TUI::EFontRole::Cond, 20.0f, 232.0f + P.TextW(S1, TUI::EFontRole::Cond, 20.0f, 0.24f) + Space, 193.0f, TUI::Red, 0.24f);
		}
	}
	{
		// Cleared counter + 16 cell progress bar (real campaign data).
		FFrontIn A(P, Env, EFrontIn::Up, 200.0f, 0.0f, 880.0f, 80.0f, 340.0f, 100.0f);
		if (A.bShown)
		{
			const int32 L = P.L();
			P.Text(L, TEXT("已攻克"), TUI::EFontRole::Mono, 14.0f, 880.0f, 118.3f, TUI::InkA(0.7f), 0.12f);
			P.Text(L, TEXT("ВЗЯТО"), TUI::EFontRole::Mono, 14.0f, 880.0f, 136.5f, TUI::InkA(0.7f), 0.12f);
			const FString Count = Pad2(ClearedCount());
			P.Text(L, Count, TUI::EFontRole::Stencil, 92.0f, 1000.0f, 116.8f, TUI::Red);
			const float Wn = P.TextW(Count, TUI::EFontRole::Stencil, 92.0f);
			P.Text(L, TEXT("/16"), TUI::EFontRole::Stencil, 40.0f, 1000.0f + Wn + 10.0f, 129.6f, TUI::Ink);
			const int32 LC = P.L();
			// CSS .pr-bar i.f blinks (steps(1)); keep the red front cell lit while the test hooks pin the screen, so captures show it.
			const bool bFrontLit = bTickerPinned || BlinkOn(Now, 1.2);
			for (int32 Cell = 1; Cell <= 16; ++Cell)
			{
				const float X = 880.0f + (Cell - 1) * 22.0f;
				const EFrontStageState St = StateOf(Cell);
				if (St == EFrontStageState::Cleared) P.Box(LC, X, 167.6f, 18.0f, 16.0f, TUI::Ink);
				else if (St == EFrontStageState::Front) { if (bFrontLit) P.Box(LC, X, 167.6f, 18.0f, 16.0f, TUI::Red); }
				else P.Frame(LC, X, 167.6f, 18.0f, 16.0f, TUI::InkA(0.55f), 2.0f);
			}
		}
	}
	{
		// Commander block with the logout button.
		FFrontIn A(P, Env, EFrontIn::WipeL, 180.0f, 0.0f, 1290.0f, 66.0f, 560.0f, 134.0f);
		if (A.bShown)
		{
			P.CutBox(P.L(), 1290.0f, 66.0f, 560.0f, 134.0f, TUI::Ink, 30.0f, TUI::ECorner::BL);
			const int32 LT = P.L();
			P.Text(LT, TEXT("统帅 · КОМАНДИР"), TUI::EFontRole::Mono, 14.0f, 1320.0f, 93.0f, TUI::RedL, 0.16f);
			const FSlateFontInfo NameFont = P.FontFor(TUI::EFontRole::SansBlack, 42.0f);
			const FString Name = TUI::Ellipsize(Commander.IsEmpty() ? FString(TEXT("同志")) : Commander, NameFont, 320.0f * K);
			P.Text(LT, Name, TUI::EFontRole::SansBlack, 42.0f, 1318.0f, 132.2f, TUI::PaperL);
			P.Text(LT, TEXT("通行证 No.0417 · 已核准 ★"), TUI::EFontRole::Mono, 14.0f, 1320.0f, 175.0f, TUI::PaperLA(0.7f), 0.1f);
			TUI::FButtonLook Look;
			Look.Scale = K;
			Look.CutPx = 0.0f;
			Look.LabelPx = 24.0f;
			Look.TrackingEm = 0.2f;
			TUI::GhostButton(P.Out, P.Geo, P.Reserve(3), P.Pt(RcLogout.X, RcLogout.Y), P.Sz(RcLogout.W, RcLogout.H), TEXT("注销"), TEXT("← ВЫХОД"),
				BtnHover[BtnLogout], true, P.Col(TUI::PaperL), Look);
		}
	}
	{
		FFrontIn A(P, Env, EFrontIn::Scale, 420.0f, 0.0f, 104.0f, 262.0f, 150.0f, 150.0f);
		if (A.bShown) P.Star(P.L(), StarSmall, FVector2f(179.0f, 337.0f), 1.5f, -12.0f, TUI::Red);
	}
	{
		// "踏平十六国！" tilted with the red band (-15.7 degrees about the centre of its 240 px box).
		FFrontIn A(P, Env, EFrontIn::Fade, 900.0f, 0.0f, 1144.0f, 826.0f, 140.0f, 160.0f);
		if (A.bShown)
		{
			const FVector2f Pivot(1244.0f, 922.2f);
			const int32 L = P.L();
			const float Ang = -15.7f;
			const FVector2f P1 = RotAbout(FVector2f(1124.0f, 887.0f), Pivot, Ang);
			const FVector2f P2 = RotAbout(FVector2f(1124.0f, 929.0f), Pivot, Ang);
			const FVector2f P3 = RotAbout(FVector2f(1124.0f, 968.0f), Pivot, Ang);
			P.Text(L, TEXT("踏平"), TUI::EFontRole::Serif, 40.0f, P1.X, P1.Y, TUI::Red, 0.0f, 0.0f, Ang);
			P.Text(L, TEXT("十六国！"), TUI::EFontRole::Serif, 40.0f, P2.X, P2.Y, TUI::Red, 0.0f, 0.0f, Ang);
			P.Text(L, TEXT("ВПЕРЁД!"), TUI::EFontRole::Russo, 17.0f, P3.X, P3.Y, TUI::Ink, 0.2f, 0.0f, Ang);
		}
	}

	DrawCards(P, Env);
	DrawDossier(P, Env);
	{
		FFrontIn A(P, Env, EFrontIn::Wipe, 700.0f, 0.0f, 96.0f, 1004.0f, 1150.0f, 40.0f);
		if (A.bShown)
		{
			const int32 L = P.L();
			float X = 96.0f;
			// HTML: "前线信号 · СИГНАЛ <b>..</b> kHz": segments are separated by one space (advance + tracking).
			const float Space = P.SpaceW(TUI::EFontRole::Mono, 14.0f, 0.1f);
			auto Seg = [&](const FString& Str, TUI::EFontRole Role, const FLinearColor& C)
			{
				P.Text(L, Str, Role, 14.0f, X, 1025.0f, C, 0.1f);
				X += P.TextW(Str, Role, 14.0f, 0.1f) + Space;
			};
			Seg(TEXT("前线信号"), TUI::EFontRole::Mono, TUI::InkA(0.7f));
			Seg(TEXT("·"), TUI::EFontRole::Mono, TUI::InkA(0.7f));
			Seg(TEXT("СИГНАЛ"), TUI::EFontRole::Mono, TUI::InkA(0.7f));
			Seg(PmSelHz, TUI::EFontRole::MonoBold, TUI::Red);
			Seg(TEXT("kHz"), TUI::EFontRole::Mono, TUI::InkA(0.7f));
			// The wave is the prototype's 900 px canvas (x 346..1246), drawn once and shown through two windows so the free match
			// button (x 700..960) sits in a 20 px gap on each side while the trace stays continuous. It also keeps 10 px clear
			// of the read-out, which can run past 346 when the whole-pixel letter spacing rounds up.
			const float WaveX0 = FMath::Max(346.0f, X - Space + 10.0f);
			// The button only exists while the dossier is empty (it fades out with the empty state in 0.3 s, see DrawDossier).
			const bool bFreeBtnShown = !bDosShown || Now - DosShowT < 0.3;
			const float GapL = bFreeBtnShown ? RcFreeBtn.X - 20.0f : 1246.0f;
			const float GapR = bFreeBtnShown ? RcFreeBtn.X + RcFreeBtn.W + 20.0f : 1246.0f;
			const int32 LW = P.L();
			for (const FVector2f& Window : { FVector2f(WaveX0, GapL), FVector2f(GapR, 1246.0f) })
			{
				if (Window.Y <= Window.X) continue;
				P.ClipRect(Window.X, 1004.0f, Window.Y - Window.X, 40.0f);
				TUI::Wave(P.Out, P.Geo, LW, P.Pt(346.0f, 1004.0f), P.Sz(900.0f, 40.0f), P.Col(TUI::Ink), P.Col(TUI::Red), Now, 10.0f * K, K);
				P.PopClip();
			}
		}
	}
	DrawTip(P, Env);
}

void UTreadFrontEndWidget::DrawCards(FFrontPaint& P, const FFrontEnv& Env) const
{
	const double Now = Env.Now;
	const float K = P.K;
	// Shared layers (no two cards overlap): shadow, face, decoration, text, chip plate, chip text, pips, stamp, brackets, pulse.
	const int32 L0 = P.Reserve(12);
	enum { LShadow = 0, LFace, LDeco, LText, LChip, LChipText, LPips, LStamp, LHalo, LBracket, LPulse };
	for (int32 Index = 0; Index < Stages.Num() && Index < 16; ++Index)
	{
		const int32 N = Index + 1;
		const FFrontStage& S = Stages[Index];
		const EFrontStageState St = StateOf(N);
		const FVector2f SlotPos = CardSlot(Index);
		const float Delay = 360.0f + (Index / 4) * 70.0f + (Index % 4) * 45.0f;
		FFrontIn A(P, Env, EFrontIn::Up, Delay, 0.0f, SlotPos.X, SlotPos.Y, 236.0f, 168.0f);
		if (!A.bShown) continue;

		const bool bSel = SelIdx == N;
		const float Hv = TUI::Ease::CssOut(CardHover[Index]);
		const float Fx = SlotPos.X - 4.0f * Hv, Fy = SlotPos.Y - 7.0f * Hv;       // face
		const float Sx = SlotPos.X + 4.0f * Hv, Sy = SlotPos.Y + 3.0f * Hv;       // hard shadow
		const FLinearColor Bg = St == EFrontStageState::Front ? TUI::Red : St == EFrontStageState::Locked ? TUI::Paper : TUI::PaperL;
		const FLinearColor Bd = St == EFrontStageState::Front ? TUI::PaperL : St == EFrontStageState::Locked ? TUI::InkA(0.55f) : TUI::Ink;
		const FLinearColor Fg = St == EFrontStageState::Front ? TUI::PaperL : St == EFrontStageState::Locked ? TUI::InkA(0.3f) : TUI::Ink;
		const FLinearColor Fg2 = St == EFrontStageState::Front ? TUI::PaperLA(0.7f) : TUI::InkA(0.7f);
		const FLinearColor ShadowCol = bSel && St != EFrontStageState::Front ? TUI::Red : TUI::Ink;

		P.CutBox(L0 + LShadow, Sx, Sy, 236.0f, 168.0f, ShadowCol, 26.0f, TUI::ECorner::TR);
		P.CutBox(L0 + LFace, Fx, Fy, 236.0f, 168.0f, Bg, 26.0f, TUI::ECorner::TR, 3.0f, Bd);
		if (St == EFrontStageState::Front)
		{
			P.Frame(L0 + LDeco, Fx + 6.0f, Fy + 6.0f, 224.0f, 156.0f, TUI::Ink, 2.0f);
		}
		else if (St == EFrontStageState::Locked)
		{
			// Hatching over the whole face except the cut corner.
			P.Tiled(L0 + LDeco, TUI::ETex::Hatch, Fx + 3.0f, Fy + 3.0f + 24.0f, 230.0f, 162.0f - 24.0f, TUI::InkA(0.1f), 24.0f);
			P.Tiled(L0 + LDeco, TUI::ETex::Hatch, Fx + 3.0f, Fy + 3.0f, 230.0f - 24.0f, 24.0f, TUI::InkA(0.1f), 24.0f);
		}
		P.Text(L0 + LText, Pad2(N), TUI::EFontRole::Stencil, 82.0f, Fx + 15.0f, Fy + 46.8f, Fg, 0.01f);
		P.Text(L0 + LText, S.ShortName, TUI::EFontRole::SansBlack, 31.0f, Fx + 16.0f, Fy + 109.5f,
			St == EFrontStageState::Locked ? TUI::InkA(0.7f) : Fg);
		{
			const FSlateFontInfo LandFont = P.FontFor(TUI::EFontRole::SansMedium, 15.0f);
			const FString Land = TUI::Ellipsize(S.Landmark, LandFont, 204.0f * K);
			P.Text(L0 + LText, Land, TUI::EFontRole::SansMedium, 15.0f, Fx + 17.0f, Fy + 143.5f, Fg2);
		}
		{
			const FLinearColor On = St == EFrontStageState::Locked ? TUI::InkA(0.55f) : Fg;
			TUI::Pips(P.Out, P.Geo, L0 + LPips, P.Pt(Fx + 181.0f, Fy + 102.0f), 4, S.AiLevel, P.Col(On), P.Col(Fg2), P.Sz(8.0f, 20.0f), 2.0f * K, 3.0f * K);
		}
		if (St == EFrontStageState::Cleared)
		{
			const float Sxo = 120.0f + (N * 37 % 9) - 4.0f, Syo = 6.0f + (N * 23 % 7) - 3.0f, Sro = -16.0f + (N * 41 % 11);
			P.Tex(L0 + LStamp, TUI::ETex::StampCleared, Fx + Sxo, Fy + Syo, 92.0f, 92.0f, TUI::Red, Sro);
		}
		else
		{
			const FString Chip = St == EFrontStageState::Front ? FString(TEXT("前线")) : (N == 16 ? FString(TEXT("封锁 · 终局")) : FString(TEXT("封锁")));
			const float Tw = P.TextW(Chip, TUI::EFontRole::SansBold, 15.0f, 0.1f);
			const float Extra = St == EFrontStageState::Front ? 14.0f : 0.0f;
			const float Cw = Tw + 16.0f + Extra, Cx = Fx + 206.0f - Cw, Cy = Fy + 15.0f;
			FLinearColor ChipText = TUI::PaperL;
			if (St == EFrontStageState::Front)
			{
				P.Box(L0 + LChip, Cx, Cy, Cw, 26.0f, TUI::PaperL);
				ChipText = TUI::Red;
				if (bTickerPinned || BlinkOn(Now, 1.0)) P.Circle(L0 + LChipText, Cx + 8.0f + Tw + 6.0f + 4.0f, Cy + 13.5f, 4.0f, TUI::Red);
			}
			else if (N == 16)
			{
				P.Box(L0 + LChip, Cx, Cy, Cw, 26.0f, TUI::Red);
			}
			else
			{
				P.Frame(L0 + LChip, Cx, Cy, Cw, 26.0f, TUI::InkA(0.55f), 2.0f);
				ChipText = TUI::InkA(0.7f);
			}
			P.Text(L0 + LChipText, Chip, TUI::EFontRole::SansBold, 15.0f, Cx + 8.0f, Cy + 12.5f, ChipText, 0.1f);
		}
		if (St == EFrontStageState::Front && !Env.bFinal)
		{
			// Pulse ring: expands 12 / 18 percent and fades (1.8 s, ease-out).
			const float E = TUI::Ease::CssOut(static_cast<float>(FMath::Fmod(Now, 1.8) / 1.8));
			const float W = 244.0f * (1.0f + 0.12f * E), H = 176.0f * (1.0f + 0.18f * E);
			P.Frame(L0 + LPulse, Fx + 118.0f - W * 0.5f, Fy + 84.0f - H * 0.5f, W, H, Fade(TUI::Red, 0.85f * (1.0f - E)), 3.0f);
		}
		if (bSel)
		{
			// Corner brackets slide in from outside (paper halo underneath, ink on top).
			const float Age = static_cast<float>(Now - SelChangeT);
			const float Slide = 1.0f - TUI::Ease::CssOut(Sat(Age / 0.34f));
			const float Op = Sat(Age / 0.2f);
			for (int32 Pass = 0; Pass < 2; ++Pass)
			{
				const bool bHalo = Pass == 0;
				const float Size = bHalo ? 32.0f : 26.0f, Thick = bHalo ? 12.0f : 6.0f, Out = bHalo ? 11.0f : 8.0f;
				const FLinearColor C = Fade(bHalo ? TUI::PaperL : TUI::Ink, Op);
				const int32 Lyr = L0 + (bHalo ? LHalo : LBracket);
				for (int32 Corner = 0; Corner < 4; ++Corner)
				{
					const bool bRight = (Corner & 1) != 0, bBottom = (Corner & 2) != 0;
					const float Ox = Fx + (bRight ? 236.0f + Out : -Out) + (bRight ? 14.0f : -14.0f) * Slide;
					const float Oy = Fy + (bBottom ? 168.0f + Out : -Out) + (bBottom ? 14.0f : -14.0f) * Slide;
					P.Box(Lyr, bRight ? Ox - Size : Ox, bBottom ? Oy - Thick : Oy, Size, Thick, C);
					P.Box(Lyr, bRight ? Ox - Thick : Ox, bBottom ? Oy - Size : Oy, Thick, Size, C);
				}
			}
		}
	}
}

void UTreadFrontEndWidget::DrawDossier(FFrontPaint& P, const FFrontEnv& Env) const
{
	const double Now = Env.Now;
	const float K = P.K;
	const float DX = 1290.0f, DY = 236.0f;
	FFrontIn A(P, Env, EFrontIn::Right, 300.0f, 0.0f, DX, DY, 560.0f, 764.0f);
	if (!A.bShown) return;
	const float ShowAge = bDosShown ? static_cast<float>(Now - DosShowT) : 0.0f;
	const float EmptyAlpha = bDosShown ? 1.0f - Sat(ShowAge / 0.3f) : 1.0f;

	// ---- empty state: signal rings, "ЦЕЛЬ" watermark, hint and the free match button
	if (EmptyAlpha > 0.003f)
	{
		FFrontPushScope Group(P, 1.0f, FVector2f::ZeroVector, FVector2f::ZeroVector, EmptyAlpha);
		P.ClipRect(DX, DY, 560.0f, 764.0f);
		P.CutBox(P.L(), DX, DY, 560.0f, 764.0f, TUI::PaperL, 0.0f, TUI::ECorner::None, 3.0f, TUI::Ink);
		P.ClipRect(DX + 33.0f, DY + 53.0f, 494.0f, 400.0f);
		TUI::SignalRings(P.Out, P.Geo, P.L(), P.Pt(DX + 280.0f, DY + 253.0f), 120.0f * K, P.Col(TUI::Ink), P.Col(TUI::Red), Now, 8.0f, 0.55f * P.A, 90.0f * K, K, true, false);
		P.PopClip();
		// CSS .de-big: left -14, bottom -34 (relative to the 3px bordered panel), 190px/1 line box, clipped by the panel.
		// Line box bottom = inner bottom (DY + 761) + 34, so its centre sits 95px above that.
		P.ClipRect(DX + 3.0f, DY + 3.0f, 554.0f, 758.0f);
		P.Text(P.L(), TEXT("ЦЕЛЬ"), TUI::EFontRole::Russo, 190.0f, DX + 3.0f - 14.0f, DY + 761.0f + 34.0f - 95.0f, TUI::PaperDD, -0.02f);
		P.PopClip();
		const int32 L = P.L();
		const float Cx = DX + 280.0f;
		P.Text(L, TEXT("选择作战目标"), TUI::EFontRole::SansBlack, 46.0f, Cx, 732.0f, TUI::Ink, 0.08f, 0.5f);
		P.Text(L, TEXT("ВЫБЕРИТЕ ЦЕЛЬ"), TUI::EFontRole::Russo, 22.0f, Cx, 780.0f, TUI::Red, 0.2f, 0.5f);
		P.Text(L, TEXT("悬停查看简报 · 单击打开作战档案"), TUI::EFontRole::Mono, 15.0f, Cx, 820.5f, TUI::InkA(0.55f), 0.1f, 0.5f);
		if (!DosNotice.IsEmpty())
		{
			const float NoticeX = 1360.0f, NoticeW = 420.0f;
			P.Box(P.L(), NoticeX, 856.0f, NoticeW, 28.0f, TUI::Red);
			const FSlateFontInfo F = P.FontFor(TUI::EFontRole::Mono, 15.0f);
			P.Text(P.L(), TUI::Ellipsize(DosNotice, F, (NoticeW - 24.0f) * K), TUI::EFontRole::Mono, 15.0f, NoticeX + 12.0f, 870.0f, TUI::PaperL);
		}
		P.PopClip();

		// Free match button sits outside the panel (bottom strip), so it is drawn after the panel clip is released.
		TUI::FButtonLook Look;
		Look.Scale = K;
		Look.CutPx = 0.0f;
		Look.LabelPx = 18.0f;
		Look.TrackingEm = 0.12f;
		TUI::GhostButton(P.Out, P.Geo, P.Reserve(3), P.Pt(RcFreeBtn.X, RcFreeBtn.Y), P.Sz(RcFreeBtn.W, RcFreeBtn.H), TEXT("自由对局 · 不计进度"),
			TEXT("СВОБОДНЫЙ БОЙ"), BtnHover[BtnFree], true, P.Col(TUI::Ink), Look);
	}

	if (!bDosShown || !Stages.IsValidIndex(DosContent - 1)) return;

	// ---- dossier body: revealed top to bottom, content blocks stagger in
	const FFrontStage& S = Stages[DosContent - 1];
	const int32 N = DosContent;
	const EFrontStageState St = StateOf(N);
	const float Reveal = TUI::Ease::CssOut(Sat(ShowAge / 0.64f));
	P.ClipRect(DX - 40.0f, DY - 40.0f, 560.0f + 80.0f, Reveal * (764.0f + 40.0f) + 40.0f);
	P.CutBox(P.L(), DX, DY, 560.0f, 764.0f, TUI::PaperL, 30.0f, TUI::ECorner::TL, 3.0f, TUI::Ink);
	{
		P.CutBox(P.L(), DX + 3.0f, DY + 3.0f, 554.0f, 52.0f, TUI::Ink, 28.2f, TUI::ECorner::TL);
		const int32 L = P.L();
		const float Cy = DY + 3.0f + 26.0f;
		P.Text(L, TEXT("作战档案"), TUI::EFontRole::SansBlack, 22.0f, DX + 3.0f + 40.0f, Cy, TUI::PaperL, 0.12f);
		const float W1 = P.TextW(TEXT("作战档案"), TUI::EFontRole::SansBlack, 22.0f, 0.12f);
		P.Text(L, TEXT("ДОСЬЕ"), TUI::EFontRole::Russo, 15.0f, DX + 3.0f + 40.0f + W1 + 12.0f, Cy + 1.0f, TUI::RedL, 0.18f);
		P.Text(L, FString::Printf(TEXT("No.%s/16 · %s方面"), *Pad2(N), *S.City), TUI::EFontRole::Mono, 14.0f, DX + 3.0f + 554.0f - 20.0f, Cy,
			TUI::PaperLA(0.7f), 0.06f, 1.0f);
	}

	auto BlockXf = [&](float DelayMs, float& OutAlpha, float& OutY)
	{
		if (SwapStartT >= 0.0)
		{
			const float Out = TUI::Ease::CssOut(Sat(static_cast<float>(Now - SwapStartT) / 0.11f));
			OutAlpha = 1.0f - Out;
			OutY = -10.0f * Out;
		}
		else
		{
			const float Ei = static_cast<float>((Now - BlkInT) - DelayMs / 1000.0);
			OutAlpha = TUI::Ease::CssOut(Sat(Ei / 0.34f));
			OutY = -10.0f * (1.0f - TUI::Ease::CssOut(Sat(Ei / 0.46f)));
		}
	};
	auto Block = [&](float DelayMs, auto&& Draw)
	{
		float Ba = 1.0f, By = 0.0f;
		BlockXf(DelayMs, Ba, By);
		if (Ba <= 0.003f) return;
		FFrontPushScope Group(P, 1.0f, FVector2f::ZeroVector, FVector2f(0.0f, By), Ba);
		Draw(Ba);
	};

	const float IX = DX + 3.0f, IY = DY + 3.0f;     // inner origin (.dos-in)
	const FLinearColor NoColor = St == EFrontStageState::Cleared ? TUI::Ink : St == EFrontStageState::Locked ? TUI::InkA(0.3f) : TUI::Red;
	Block(0.0f, [&](float)
	{
		FString NoText = Pad2(N);
		const float RollAge = static_cast<float>(Now - RollT0);
		if (RollAge >= 0.0f && RollAge < 0.238f)
			NoText = Pad2((FMath::FloorToInt(RollAge / 0.034f) * 7 + N * 5 + 3) % 16 + 1);
		P.Text(P.L(), NoText, TUI::EFontRole::Stencil, 186.0f, IX + 24.0f, IY + 68.0f + 74.4f, NoColor, -0.01f);
	});
	Block(40.0f, [&](float)
	{
		const int32 L = P.L();
		const float TagX = IX + 554.0f - 24.0f - 230.0f;
		P.Text(L, FString::Printf(TEXT("威胁等级 · AI LV.%d"), S.AiLevel), TUI::EFontRole::Mono, 14.0f, TagX, IY + 72.0f + 7.0f, TUI::InkA(0.55f), 0.12f);
		TUI::Pips(P.Out, P.Geo, L, P.Pt(TagX, IY + 72.0f + 22.0f), 4, S.AiLevel, P.Col(TUI::Red), P.Col(TUI::Ink), P.Sz(53.75f, 30.0f), 3.0f * K, 5.0f * K);
		const float StY = IY + 72.0f + 22.0f + 30.0f + 20.0f;
		if (St == EFrontStageState::Cleared)
		{
			P.Tex(P.L(), TUI::ETex::StampCleared, TagX + 230.0f - 46.0f - 112.0f, StY - 6.0f, 112.0f, 112.0f, TUI::Red, -12.0f);
		}
		else
		{
			const FString Chip = St == EFrontStageState::Front ? FString(TEXT("前线")) : FString(TEXT("封锁"));
			const float Cw = P.TextW(Chip, TUI::EFontRole::SansBlack, 30.0f, 0.2f) + 32.0f;
			P.Box(P.L(), TagX + 230.0f - Cw, StY + 4.0f, Cw, 54.0f, St == EFrontStageState::Front ? TUI::Red : TUI::Ink);
			P.Text(P.L(), Chip, TUI::EFontRole::SansBlack, 30.0f, TagX + 230.0f - Cw + 16.0f, StY + 4.0f + 27.0f, TUI::PaperL, 0.2f);
		}
	});
	Block(80.0f, [&](float)
	{
		// The prototype's fit loop (62px down to 36px "while scrollWidth > 490") always ends at 36px: the block is 506px wide and
		// scrollWidth never drops below that. 36px is what was signed off, so it is the size here; only a name too long for the
		// 490px measure shrinks further.
		const FSlateFontInfo F = TUI::FitFont(S.Country, TUI::EFontRole::SansBlack, TUI::Pt(36.0f, K), TUI::Pt(26.0f, K), 490.0f * K);
		const float Px = F.Size / (0.75f * K);
		TUI::Text(P.Out, P.Geo, P.L(), S.Country, F, P.Pt(IX + 24.0f, IY + 228.0f + Px * 0.53f), P.Col(TUI::Ink), 0.0f, FVector2f(0.0f, 0.5f));
	});
	Block(110.0f, [&](float)
	{
		P.Box(P.L(), IX + 24.0f, IY + 302.0f, 9.0f, 34.0f, TUI::Red);
		P.Text(P.L(), S.Landmark, TUI::EFontRole::Serif, 30.0f, IX + 24.0f + 9.0f + 12.0f, IY + 302.0f + 17.0f, TUI::Ink);
	});
	Block(140.0f, [&](float)
	{
		const FSlateFontInfo F = P.FontFor(TUI::EFontRole::SansBold, 21.0f);
		P.Text(P.L(), TUI::Ellipsize(S.Rule, F, 506.0f * K), TUI::EFontRole::SansBold, 21.0f, IX + 24.0f, IY + 350.0f + 13.65f, TUI::InkA(0.7f));
	});
	Block(160.0f, [&](float)
	{
		TUI::Ruler(P.Out, P.Geo, P.L(), P.Pt(IX + 24.0f, IY + 388.0f), 506.0f * K, P.Col(TUI::Ink), K);
	});
	Block(190.0f, [&](float)
	{
		struct FStat { FString Label; FString Value; bool bAdv; };
		const FStat Stats[6] = {
			{ TEXT("首两回合守军"), Signed(S.GarrisonBonus), S.GarrisonBonus > 0 },
			{ TEXT("敌方地标耐久"), Signed(S.EnemyHpBonus), S.EnemyHpBonus > 0 },
			{ TEXT("初始资金"), Signed(S.StartGoldBonus), S.StartGoldBonus < 0 },
			{ TEXT("战败伤害"), FString::Printf(TEXT("%d%%"), S.DamageTakenPercent), S.DamageTakenPercent > 100 },
			{ TEXT("备战时间"), FString::Printf(TEXT("%ds"), 30 + S.PrepareDelta), S.PrepareDelta < 0 },
			{ TEXT("每回合收入"), Signed(S.IncomeBonus), false } };
		const int32 LR = P.L();
		const int32 LT = P.L();
		for (int32 Cell = 0; Cell < 6; ++Cell)
		{
			const float X = IX + 24.0f + (Cell % 3) * (506.0f / 3.0f);
			const float Y = IY + 418.0f + (Cell / 3) * 66.0f;
			P.Box(LR, X, Y, 3.0f, 58.0f, TUI::Ink);
			P.Text(LT, Stats[Cell].Label, TUI::EFontRole::Mono, 15.0f, X + 15.0f, Y + 8.5f, TUI::InkA(0.7f));
			P.Text(LT, Stats[Cell].Value, TUI::EFontRole::Stencil, 36.0f, X + 15.0f, Y + 41.0f, Stats[Cell].bAdv ? TUI::Red : TUI::Ink);
		}
	});
	Block(230.0f, [&](float)
	{
		const float Y = IY + 582.0f;
		P.Box(P.L(), IX + 24.0f, Y, 506.0f, 65.7f, TUI::Ink);
		P.Box(P.L(), IX + 24.0f, Y, 9.0f, 65.7f, TUI::Red);
		const int32 L = P.L();
		P.Text(L, TEXT("特殊规则 · ОСОБОЕ"), TUI::EFontRole::Mono, 14.0f, IX + 24.0f + 9.0f + 18.0f, Y + 17.0f, TUI::RedL, 0.14f);
		const FSlateFontInfo F = P.FontFor(TUI::EFontRole::SansBold, 19.0f);
		P.Text(L, TUI::Ellipsize(S.Effect, F, 465.0f * K), TUI::EFontRole::SansBold, 19.0f, IX + 24.0f + 9.0f + 18.0f, Y + 10.0f + 14.0f + 6.0f + 12.35f, TUI::PaperL);
	});
	Block(260.0f, [&](float)
	{
		const float Y = IY + 555.0f;
		if (!DosNotice.IsEmpty())
		{
			const float Na = Sat(static_cast<float>(Now - DosNoticeT) / 0.3f);
			P.Box(P.L(), IX + 24.0f, Y - 7.0f, 506.0f, 28.0f, Fade(TUI::Red, Na));
			const FSlateFontInfo F = P.FontFor(TUI::EFontRole::Mono, 15.0f);
			P.Text(P.L(), TUI::Ellipsize(DosNotice, F, 482.0f * K), TUI::EFontRole::Mono, 15.0f, IX + 24.0f + 12.0f, Y + 7.5f, Fade(TUI::PaperL, Na));
		}
		else if (!S.Leader.IsEmpty())
		{
			const int32 L = P.L();
			const FString Tail = FString::Printf(TEXT(" · %s · %d 人 · 耐久 %d"), *S.Leader, S.LeaderSize, S.LeaderHp);
			P.Text(L, TEXT("R12 领袖"), TUI::EFontRole::MonoBold, 15.0f, IX + 24.0f, Y + 7.5f, TUI::Red);
			const float Wh = P.TextW(TEXT("R12 领袖"), TUI::EFontRole::MonoBold, 15.0f);
			const FSlateFontInfo F = P.FontFor(TUI::EFontRole::Mono, 15.0f);
			P.Text(L, TUI::Ellipsize(Tail, F, (506.0f - Wh) * K), TUI::EFontRole::Mono, 15.0f, IX + 24.0f + Wh, Y + 7.5f, TUI::InkA(0.7f));
		}
	});
	Block(290.0f, [&](float Ba)
	{
		if (Ba < 0.5f) return;
		TUI::FButtonLook Look;
		Look.Scale = K;
		Look.CutPx = 34.0f;
		Look.LabelPx = 40.0f;
		// #dos .btn .b-tx {left: 30px; gap: 16px}, span 22px: the dossier button is 88 high, so the 108 px defaults put the label 7.5 px right.
		Look.LabelLeftPx = 30.0f;
		Look.GapPx = 16.0f;
		Look.RuPx = 22.0f;
		Look.TrackingEm = St == EFrontStageState::Cleared ? 0.1f : 0.3f;
		Look.Arrow = St == EFrontStageState::Locked ? FString() : FString(TEXT("→"));
		const FVector2f Pos = P.Pt(RcGoBtn.X, RcGoBtn.Y), Size = P.Sz(RcGoBtn.W, RcGoBtn.H);
		const float Hover = BtnHover[BtnGo];
		if (St == EFrontStageState::Front) TUI::PrimaryButton(P.Out, P.Geo, P.Reserve(3), Pos, Size, TEXT("进入"), TEXT("ВПЕРЁД"), Hover, true, Look);
		else if (St == EFrontStageState::Cleared) TUI::SecondaryButton(P.Out, P.Geo, P.Reserve(3), Pos, Size, TEXT("再次进入"), TEXT("ПОВТОР"), Hover, true, Look);
		else
		{
			// .btn.off b {30px, .14em}; the span keeps 22px .14em in the Russo stack, whose CJK glyphs come from TSans (regular weight).
			Look.LabelPx = 30.0f;
			Look.TrackingEm = 0.14f;
			Look.RuRole = TUI::EFontRole::SansMedium;
			Look.RuTrackingEm = 0.14f;
			TUI::PrimaryButton(P.Out, P.Geo, P.Reserve(3), Pos, Size, TEXT("封锁中"), FString::Printf(TEXT("需先攻克第 %s 关"), *Pad2(N - 1)), 0.0f, false, Look);
		}
	});
	P.PopClip();

	// Red scan line sweeping down while the dossier opens.
	if (ShowAge < 0.64f)
	{
		const float Tn = Sat(ShowAge / 0.64f);
		const float Ly = DY + 764.0f * TUI::Ease::CssOut(Tn);
		const float La = Tn < 0.8f ? 1.0f : 1.0f - TUI::Ease::CssOut((Tn - 0.8f) / 0.2f);
		P.Box(P.L(), DX, Ly, 560.0f, 5.0f, Fade(TUI::Red, La));
	}
	// "出征" stamp slammed onto the dossier when the sortie button is pressed.
	if (SortieStampT >= 0.0)
	{
		TUI::Stamp(P.Out, P.Geo, P.L(), TUI::ETex::StampSortie, P.Pt(DX + 70.0f + 210.0f, DY + 250.0f + 70.0f), P.Sz(420.0f, 140.0f), P.Col(TUI::Red), -9.0f,
			static_cast<float>(Now - SortieStampT));
	}
}

void UTreadFrontEndWidget::DrawTip(FFrontPaint& P, const FFrontEnv& Env) const
{
	if (TipStage <= 0 || !Stages.IsValidIndex(TipStage - 1)) return;
	const double Now = Env.Now;
	float Alpha;
	if (TipHideT < 0.0) Alpha = Sat(static_cast<float>(Now - TipShowT) / 0.16f);
	else Alpha = 1.0f - Sat(static_cast<float>(Now - TipHideT) / 0.16f);
	if (Alpha <= 0.003f) return;
	const FFrontStage& S = Stages[TipStage - 1];
	const int32 N = TipStage;
	const float Reveal = TUI::Ease::CssOut(Sat(static_cast<float>(Now - TipShowT) / 0.3f));
	const float X = TipPos.X, Y = TipPos.Y, W = 330.0f, H = TipH;

	FFrontPushScope Group(P, 1.0f, FVector2f::ZeroVector, FVector2f::ZeroVector, Alpha);
	if (TipSide == 1) P.ClipRect(X + W - Reveal * (W + 30.0f), Y - 30.0f, Reveal * (W + 30.0f) + 30.0f, H + 60.0f);
	else P.ClipRect(X - 30.0f, Y - 30.0f, Reveal * (W + 30.0f) + 30.0f, H + 60.0f);

	P.Box(P.L(), X - 3.0f + 9.0f, Y - 3.0f + 9.0f, W + 6.0f, H + 6.0f, TUI::Ink);     // hard shadow
	P.Box(P.L(), X - 3.0f, Y - 3.0f, W + 6.0f, H + 6.0f, TUI::PaperL);               // paper ring
	P.Box(P.L(), X, Y, W, H, TUI::Ink);
	const int32 LNotch = P.L();
	if (TipSide == 0) P.Poly(LNotch, { {X, Y + 30.0f}, {X, Y + 54.0f}, {X - 12.0f, Y + 42.0f} }, TUI::Ink, false);
	else if (TipSide == 1) P.Poly(LNotch, { {X + W, Y + 30.0f}, {X + W, Y + 54.0f}, {X + W + 12.0f, Y + 42.0f} }, TUI::Ink, false);

	P.Box(P.L(), X, Y, W, 46.0f, TUI::Red);
	const int32 L = P.L();
	const FString No = Pad2(N);
	P.Text(L, No, TUI::EFontRole::Stencil, 34.0f, X + 16.0f, Y + 23.0f, TUI::PaperL);
	const float Wn = P.TextW(No, TUI::EFontRole::Stencil, 34.0f);
	{
		const FSlateFontInfo F = P.FontFor(TUI::EFontRole::SansBlack, 21.0f);
		const float Avail = W - 32.0f - Wn - 12.0f;
		P.Text(L, TUI::Ellipsize(S.Country, F, Avail * P.K), TUI::EFontRole::SansBlack, 21.0f, X + 16.0f + Wn + 12.0f, Y + 23.0f, TUI::PaperL);
	}
	float RowY = Y + 46.0f;
	auto Row = [&](const TCHAR* Label, const TArray<FString>& Lines)
	{
		RowY += 8.0f;
		P.Text(L, Label, TUI::EFontRole::MonoBold, 14.0f, X + 14.0f, RowY + 11.0f, TUI::RedHi);
		for (int32 Line = 0; Line < Lines.Num(); ++Line)
			P.Text(L, Lines[Line], TUI::EFontRole::SansMedium, 15.0f, X + 14.0f + 50.0f, RowY + 10.5f + Line * 21.0f, TUI::PaperL);
		RowY += FMath::Max(22.0f, Lines.Num() * 21.0f);
	};
	Row(TEXT("地标"), TipLand);
	Row(TEXT("战场"), TipRuleText);
	Row(TEXT("规则"), TipEff);
	const float FootY = RowY + 11.0f;
	P.Box(L, X + 14.0f, FootY, W - 28.0f, P.Hair(), TUI::PaperLA(0.25f));
	P.Text(L, FString::Printf(TEXT("AI LV.%d · 耐久 +%d · 战败伤害 %d%%"), S.AiLevel, S.EnemyHpBonus, S.DamageTakenPercent), TUI::EFontRole::Mono, 14.0f,
		X + 14.0f, FootY + 17.0f, TUI::PaperL, 0.02f);
	const EFrontStageState St = StateOf(N);
	const FString Status = St == EFrontStageState::Cleared ? FString(TEXT("状态 · 已攻克 · 可再次进入"))
		: St == EFrontStageState::Front ? FString(TEXT("状态 · 前线 · 可进攻"))
		: FString::Printf(TEXT("状态 · 封锁 · 需先攻克第 %s 关"), *Pad2(N - 1));
	P.Text(L, Status, TUI::EFontRole::SansBold, 14.0f, X + 14.0f, FootY + 24.0f + 8.0f + 7.0f, TUI::RedHi, 0.06f);
	P.PopClip();
}

// ------------------------------------------------------------------------------------------------------------
// Sortie (Л.04)
// ------------------------------------------------------------------------------------------------------------
void UTreadFrontEndWidget::DrawSortie(FFrontPaint& P, const FFrontEnv& Env) const
{
	const double Now = Env.Now;
	const float K = P.K;
	const int32 N = SortieStage;
	const FFrontStage* Stage = N > 0 && Stages.IsValidIndex(N - 1) ? &Stages[N - 1] : nullptr;

	P.Box(P.L(), 0.0f, 0.0f, DW, DH, TUI::Ink);
	P.Poly(P.L(), { {0.0f, 1256.0f}, {1920.0f, 716.0f}, {1920.0f, 826.0f}, {0.0f, 1366.0f} }, TUI::RedD);
	{
		FFrontIn A(P, Env, EFrontIn::Scale, 0.0f, 0.0f, 980.0f, 120.0f, 860.0f, 860.0f);
		if (A.bShown)
		{
			P.Tex(P.L(), TUI::ETex::Disc, 980.0f, 120.0f, 860.0f, 860.0f, TUI::Red);
			P.Tex(P.L(), TUI::ETex::DiscShade, 980.0f, 120.0f, 860.0f, 860.0f, Fade(TUI::RedD, 0.85f));
		}
	}
	{
		FFrontIn A(P, Env, EFrontIn::Up, 120.0f, 900.0f, 980.0f, 120.0f, 860.0f, 860.0f);
		if (A.bShown) P.Tex(P.L(), TUI::ETex::GiantessInDisc, 980.0f, 120.0f, 860.0f, 860.0f, TUI::Ink);
	}
	TUI::SignalRings(P.Out, P.Geo, P.L(), P.Pt(1410.0f, 550.0f), 440.0f * K, TUI::PaperL, TUI::RedL, Now, 3.0f, 0.45f, 160.0f * K, K, false, false);
	TUI::Particles(P.Out, P.Geo, P.L(), P.Pt(0.0f, 0.0f), P.Sz(DW, DH), 40, TUI::PaperL, 0.4f * P.A, Now, K);
	{
		FFrontIn A(P, Env, EFrontIn::Left, 100.0f, 0.0f, 122.0f, 148.0f, 500.0f, 24.0f);
		if (A.bShown) P.Text(P.L(), TEXT("Л.04 · ПРИКАЗ · 作战命令"), TUI::EFontRole::MonoBold, 18.0f, 122.0f, 161.0f, TUI::RedHi, 0.2f);
	}
	{
		FFrontIn A(P, Env, EFrontIn::Up, 160.0f, 0.0f, 110.0f, 200.0f, 400.0f, 176.0f);
		if (A.bShown) P.Text(P.L(), Pad2(N), TUI::EFontRole::Stencil, 220.0f, 110.0f, 288.0f, TUI::Red);
	}
	const FString Name = Stage ? Stage->Country : FString(TEXT("自由对局"));
	{
		float Px = 124.0f;
		while (Px > 70.0f && P.TextW(Name, TUI::EFontRole::SansBlack, Px) > 820.0f) Px -= 4.0f;
		FFrontIn A(P, Env, EFrontIn::Wipe, 260.0f, 0.0f, 118.0f, 400.0f, 860.0f, Px * 1.05f);
		if (A.bShown) P.Text(P.L(), Name, TUI::EFontRole::SansBlack, Px, 118.0f, 400.0f + Px * 1.05f * 0.5f, TUI::PaperL);
	}
	{
		FFrontIn A(P, Env, EFrontIn::Up, 360.0f, 0.0f, 124.0f, 560.0f, 800.0f, 56.0f);
		if (A.bShown)
		{
			const FString Land = Stage ? FString::Printf(TEXT("%s · %s"), *Stage->Landmark, *Stage->City) : FString(TEXT("不计战役进度 · 巴黎"));
			P.Text(P.L(), Land, TUI::EFontRole::Serif, 42.0f, 124.0f, 588.0f, TUI::PaperLA(0.7f));
		}
	}
	{
		FFrontIn A(P, Env, EFrontIn::Up, 440.0f, 0.0f, 124.0f, 650.0f, 480.0f, 80.0f);
		if (A.bShown)
		{
			const int32 LR = P.L();
			const int32 LT = P.L();
			const int32 Ai = Stage ? Stage->AiLevel : 1;
			const int32 Funds = Stage ? Stage->StartGoldBonus : 0;
			const int32 Prep = 30 + (Stage ? Stage->PrepareDelta : 0);
			for (int32 Cell = 0; Cell < 3; ++Cell) P.Box(LR, 124.0f + Cell * 160.0f, 650.0f, 3.0f, 79.0f, TUI::RedHi);
			P.Text(LT, TEXT("威胁等级 AI"), TUI::EFontRole::Mono, 15.0f, 141.0f, 659.5f, TUI::PaperLA(0.7f));
			TUI::Pips(P.Out, P.Geo, LR, P.Pt(141.0f, 677.0f), 4, Ai, P.Col(TUI::RedHi), P.Col(TUI::PaperLA(0.5f)), P.Sz(20.0f, 42.0f), 3.0f * K, 6.0f * K);
			P.Text(LT, TEXT("初始资金"), TUI::EFontRole::Mono, 15.0f, 301.0f, 659.5f, TUI::PaperLA(0.7f));
			P.Text(LT, Signed(Funds), TUI::EFontRole::Stencil, 54.0f, 301.0f, 702.0f, Funds < 0 ? TUI::RedHi : TUI::PaperL);
			P.Text(LT, TEXT("备战时间"), TUI::EFontRole::Mono, 15.0f, 461.0f, 659.5f, TUI::PaperLA(0.7f));
			P.Text(LT, FString::Printf(TEXT("%ds"), Prep), TUI::EFontRole::Stencil, 54.0f, 461.0f, 702.0f, Prep < 30 ? TUI::RedHi : TUI::PaperL);
		}
	}
	{
		const float Sec = StampSec(Env, 560.0f);
		TUI::Stamp(P.Out, P.Geo, P.L(), TUI::ETex::StampSortie, P.Pt(640.0f + 150.0f, 652.0f + 50.0f), P.Sz(300.0f, 100.0f), P.Col(TUI::PaperL), -8.0f, Sec);
	}
	{
		// Deployment progress: 2.6 s after a 0.7 s lead-in, 32 cells and a percentage.
		FFrontIn A(P, Env, EFrontIn::Up, 600.0f, 0.0f, 124.0f, 836.0f, 480.0f, 120.0f);
		if (A.bShown)
		{
			const float Raw = Env.bFinal ? 1.0f : Sat(static_cast<float>((Now - Env.T0 - 0.7) * 1000.0 / TmSortieDeploy));
			const float Pr = TUI::Ease::InOutCubic(Raw);
			const int32 L = P.L();
			P.Text(L, TEXT("部署棋盘 8×8 · 第 1 回合备战"), TUI::EFontRole::Mono, 16.0f, 124.0f, 873.0f, TUI::PaperLA(0.7f), 0.06f);
			P.Text(L, FString::Printf(TEXT("%03d%%"), FMath::FloorToInt(Pr * 100.0f + 0.0001f)), TUI::EFontRole::Stencil, 44.0f, 604.0f, 862.0f, TUI::RedL, 0.0f, 1.0f);
			TUI::SegBar(P.Out, P.Geo, P.L(), P.Pt(124.0f, 897.0f), P.Sz(480.0f, 24.0f), 32, Pr, P.Col(TUI::RedL), FLinearColor(0.0f, 0.0f, 0.0f, 0.0f),
				2.0f * K, 4.0f * K, P.Col(TUI::PaperLA(0.25f)), -1.0, P.Col(TUI::Ink));
			if (SortieDoneT >= 0.0)
			{
				const float Ea = Sat(static_cast<float>(Now - SortieDoneT) / 0.4f);
				P.Text(P.L(), TEXT("部署完成 · 正在切入对局"), TUI::EFontRole::Mono, 15.0f, 124.0f, 944.5f, Fade(TUI::PaperL, Ea));
			}
		}
	}
	{
		// Back button: paper plate with ink text, red wipe on hover (not the library ghost style, it is filled).
		FFrontIn A(P, Env, EFrontIn::Fade, 800.0f, 0.0f, RcBackBtn.X, RcBackBtn.Y, RcBackBtn.W, RcBackBtn.H);
		if (A.bShown)
		{
			const float X0 = RcBackBtn.X, Y0 = RcBackBtn.Y, W0 = RcBackBtn.W, H0 = RcBackBtn.H, C = 22.0f;
			const float Hv = BtnHover[BtnBack];
			P.CutBox(P.L(), X0, Y0, W0, H0, TUI::PaperL, C, TUI::ECorner::BR);
			const float Wx = X0 + W0 * TUI::Ease::CssOut(Hv);
			if (Hv > 0.001f)
			{
				const int32 LW = P.L();
				if (Wx <= X0 + W0 - C) P.Poly(LW, { {X0, Y0}, {Wx, Y0}, {Wx, Y0 + H0}, {X0, Y0 + H0} }, TUI::Red);
				else P.Poly(LW, { {X0, Y0}, {Wx, Y0}, {Wx, Y0 + H0 - (Wx - (X0 + W0 - C))}, {X0 + W0 - C, Y0 + H0}, {X0, Y0 + H0} }, TUI::Red);
			}
			const int32 LT = P.L();
			const FLinearColor Tone = Hv > 0.5f ? TUI::PaperL : TUI::Ink;
			P.Text(LT, TEXT("返回选关"), TUI::EFontRole::SansBlack, 24.0f, X0 + W0 * 0.5f, Y0 + 51.5f - 22.5f + 12.0f, Tone, 0.2f, 0.5f);
			P.Text(LT, TEXT("← НАЗАД"), TUI::EFontRole::Russo, 14.0f, X0 + W0 * 0.5f, Y0 + 51.5f - 22.5f + 24.0f + 7.0f + 7.0f, Fade(Tone, 0.85f), 0.16f, 0.5f);
		}
	}
}

// ------------------------------------------------------------------------------------------------------------
// Transition effects (above the screens, below the chrome)
// ------------------------------------------------------------------------------------------------------------
float UTreadFrontEndWidget::ScanBarY(double Now) const
{
	const float T = Sat(TransElapsedMs(Now) / TmScan);
	return -96.0f + TUI::Ease::InOutCubic(T) * (DH + 110.0f);
}

void UTreadFrontEndWidget::DrawTransitionFx(FFrontPaint& P, double Now) const
{
	const float K = P.K;
	switch (Trans.Kind)
	{
	case EFrontTrans::Scan:
	{
		const float Y = ScanBarY(Now);
		const int32 L1 = P.L(), L2 = P.L(), L3 = P.L(), L4 = P.L(), L5 = P.L();
		{
			FRectBatch Batch(P.Geo);
			Batch.GradRect(P.Pt(0.0f, Y), P.Sz(DW, 90.0f), P.Col(TUI::InkA(0.0f)), P.Col(TUI::InkA(0.55f)));
			Batch.Flush(P.Out, L1);
		}
		P.Tiled(L2, TUI::ETex::Scanlines, 0.0f, Y, DW, 90.0f, Fade(TUI::Ink, 0.5f), 4.0f);
		P.Box(L3, 0.0f, Y + 90.0f, DW, 5.0f, TUI::Red);
		P.Box(L3, 0.0f, Y + 95.0f, DW, 1.0f, TUI::PaperL);
		const int32 TargetSheet = static_cast<int32>(Trans.To);
		const FString Label = FString::Printf(TEXT("SCAN ▸ Л.%s · %04d/1080"), *Pad2(TargetSheet), FMath::Clamp(FMath::RoundToInt(Y + 92.0f), 0, 1080));
		const float W = P.TextW(Label, TUI::EFontRole::MonoBold, 13.0f, 0.16f);
		P.Box(L4, 1850.0f - W - 16.0f, Y + 66.0f, W + 16.0f, 21.0f, TUI::Red);
		P.Text(L5, Label, TUI::EFontRole::MonoBold, 13.0f, 1850.0f - W - 8.0f, Y + 76.5f, TUI::PaperL, 0.16f);
		break;
	}
	case EFrontTrans::Slab:
	{
		const float Dir = Trans.Dir;
		const float Tn = Sat(TransElapsedMs(Now) / TmSlab);
		const float Lag = 110.0f / TmSlab;
		const float PR = Sat(Tn / (1.0f - Lag)), PK = Sat((Tn - Lag) / (1.0f - Lag));
		const float Start = Dir > 0.0f ? -2560.0f : 2080.0f, Cover = -240.0f, End = Dir > 0.0f ? 2080.0f : -2560.0f;
		const float Skew = FMath::Tan(FMath::DegreesToRadians(-14.0f * Dir));
		auto Hold = [](float Pp) { return Pp < 0.42f ? Pp / 0.42f * 0.5f : Pp < 0.58f ? 0.5f : 0.5f + (Pp - 0.58f) / 0.42f * 0.5f; };
		auto PlaceX = [&](float Pp)
		{
			return Pp < 0.5f ? Start + (Cover - Start) * TUI::Ease::OutCubic(Pp / 0.5f) : Cover + (End - Cover) * TUI::Ease::InCubic((Pp - 0.5f) / 0.5f);
		};
		auto SlabPoly = [&](int32 Lyr, float Tx, const FLinearColor& C)
		{
			P.Poly(Lyr, { {Tx + Skew * -540.0f, 0.0f}, {Tx + 2400.0f + Skew * -540.0f, 0.0f}, {Tx + 2400.0f + Skew * 540.0f, DH}, {Tx + Skew * 540.0f, DH} }, C);
		};
		const float RedX = PlaceX(Hold(PR)), InkX = PlaceX(Hold(PK));
		SlabPoly(P.L(), RedX, TUI::Red);
		SlabPoly(P.L(), InkX, TUI::Ink);
		const float CapA = Sat((PK - 0.25f) * 6.0f) * Sat((0.75f - PK) * 6.0f);
		if (CapA > 0.003f)
		{
			FFrontPushScope Group(P, 1.0f, FVector2f::ZeroVector, FVector2f::ZeroVector, CapA);
			const float Cx = InkX + 1200.0f;
			const float Wb = P.TextW(Trans.Cap, TUI::EFontRole::SansBlack, 196.0f, 0.04f);
			const float Wr = P.TextW(Trans.Ru, TUI::EFontRole::Russo, 36.0f, 0.32f);
			const float Wm = FMath::Max(Wb, Wr);
			const int32 L = P.L();
			P.Text(L, Trans.Cap, TUI::EFontRole::SansBlack, 196.0f, Cx, 491.0f, TUI::PaperL, 0.04f, 0.5f);
			P.Box(L, Cx - Wm * 0.5f, 615.0f, Wm, 14.0f, TUI::Red);
			P.Text(L, Trans.Ru, TUI::EFontRole::Russo, 36.0f, Cx, 669.0f, TUI::RedHi, 0.32f, 0.5f);
		}
		break;
	}
	case EFrontTrans::Blinds:
	{
		const float E = TransElapsedMs(Now);
		const float T = TmBlinds, Per = 300.0f, Stag = (T - Per) / 11.0f;
		const int32 LInk = P.L(), LEdge = P.L();
		FRectBatch Ink(P.Geo), Edge(P.Geo);
		const bool bClosing = E <= T + 80.0f;
		for (int32 Index = 0; Index < 12; ++Index)
		{
			const float Y0 = Index * 90.0f;
			if (bClosing)
			{
				const float Kk = TUI::Ease::InCubic(Sat((FMath::Min(E, T) - Index * Stag) / Per));
				const float Hh = FMath::RoundToFloat(Kk * 90.0f);
				if (Hh <= 0.0f) continue;
				Ink.Rect(P.Pt(0.0f, Y0), P.Sz(DW, Hh), P.Col(TUI::Ink));
				if (Hh >= 6.0f && Kk < 1.0f) Edge.Rect(P.Pt(0.0f, Y0 + Hh - 5.0f), P.Sz(DW, 5.0f), P.Col(TUI::Red));
			}
			else
			{
				const float E2 = E - (T + 80.0f);
				const float Kk = 1.0f - TUI::Ease::OutCubic(Sat((E2 - Index * Stag) / Per));
				const float Hh = FMath::RoundToFloat(Kk * 90.0f);
				if (Hh <= 0.0f) continue;
				const float Top = Y0 + 90.0f - Hh;
				Ink.Rect(P.Pt(0.0f, Top), P.Sz(DW, Hh), P.Col(TUI::Ink));
				Edge.Rect(P.Pt(0.0f, Top), P.Sz(DW, FMath::Min(5.0f, Hh)), P.Col(TUI::Red));
			}
		}
		Ink.Flush(P.Out, LInk);
		Edge.Flush(P.Out, LEdge);
		break;
	}
	default:
		break;
	}
	(void)K;
}

// ------------------------------------------------------------------------------------------------------------
// Persistent print furniture
// ------------------------------------------------------------------------------------------------------------
void UTreadFrontEndWidget::DrawChrome(FFrontPaint& P, double Now) const
{
	const int32 L = P.L();
	const FLinearColor Mark = TUI::Red;
	// Crop marks (3 px red corners, 34 px arms, 20 px from the edge).
	P.Box(L, 20.0f, 20.0f, 34.0f, 3.0f, Mark);       P.Box(L, 20.0f, 20.0f, 3.0f, 34.0f, Mark);
	P.Box(L, 1866.0f, 20.0f, 34.0f, 3.0f, Mark);     P.Box(L, 1897.0f, 20.0f, 3.0f, 34.0f, Mark);
	P.Box(L, 20.0f, 1057.0f, 34.0f, 3.0f, Mark);     P.Box(L, 20.0f, 1026.0f, 3.0f, 34.0f, Mark);
	P.Box(L, 1866.0f, 1057.0f, 34.0f, 3.0f, Mark);   P.Box(L, 1897.0f, 1026.0f, 3.0f, 34.0f, Mark);
	// Registration mark at the top centre.
	TUI::Ring(P.Out, P.Geo, L, P.Pt(960.0f, 22.0f), 8.0f * P.K, P.Col(Mark), 2.0f * P.K, 32);
	P.Box(L, 945.0f, 21.0f, 30.0f, 2.0f, Mark);
	P.Box(L, 959.0f, 7.0f, 2.0f, 30.0f, Mark);

	const FString Sheet = FString::Printf(TEXT("Л.%s"), *Pad2(SheetNo));
	const float Ws = P.TextW(Sheet, TUI::EFontRole::MonoBold, 14.0f, 0.14f);
	const FString Prefix = TEXT("ТРЕАД · 踏国行军档案终端 · ");
	const float Wp = P.TextW(Prefix, TUI::EFontRole::Mono, 14.0f, 0.14f);
	P.Text(L, Prefix, TUI::EFontRole::Mono, 14.0f, 1852.0f - Ws - Wp, 34.0f, ChromeTop, 0.14f);
	P.Text(L, Sheet, TUI::EFontRole::MonoBold, 14.0f, 1852.0f - Ws, 34.0f, ChromeAccent, 0.14f);

	const FDateTime Time = FDateTime::Now();
	const int64 Seed = Controller.IsValid() ? Controller->MatchState.Seed : 20260926;
	const FString Foot = FString::Printf(TEXT("%04d·%02d·%02d %02d:%02d:%02d · SEED %lld · v0.5.14"), Time.GetYear(), Time.GetMonth(), Time.GetDay(),
		Time.GetHour(), Time.GetMinute(), Time.GetSecond(), Seed);
	P.Text(L, Foot, TUI::EFontRole::Mono, 14.0f, 1852.0f, 1046.0f, ChromeBottom, 0.14f, 1.0f);

	static const FLinearColor* const Bars[5] = { &TUI::Red, &TUI::Ink, &TUI::PaperD, &TUI::RedD, &TUI::PaperL };
	for (int32 Index = 0; Index < 5; ++Index) P.Box(L, 68.0f + Index * 18.0f, 1040.0f, 15.0f, 15.0f, *Bars[Index]);
	(void)Now;
}
