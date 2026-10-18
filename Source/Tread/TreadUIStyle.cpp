#include "TreadUIStyle.h"

#include "Brushes/SlateNoResource.h"
#include "Engine/FontFace.h"
#include "Engine/Texture2D.h"
#include "Fonts/CompositeFont.h"
#include "Fonts/FontCache.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "Layout/Clipping.h"
#include "Misc/CoreDelegates.h"
#include "Rendering/RenderingCommon.h"
#include "Rendering/SlateRenderer.h"
#include "Styling/CoreStyle.h"
#include "Styling/SlateBrush.h"
#include "UObject/GCObject.h"

DEFINE_LOG_CATEGORY_STATIC(LogTreadUIStyle, Log, All);

namespace TreadUI
{
	namespace
	{
		constexpr double kPi = 3.14159265358979323846;

		/** See SetPaintFontScale(). */
		float GPaintFontScale = 1.0f;

		FLinearColor Srgb(uint8 R, uint8 G, uint8 B)
		{
			return FLinearColor::FromSRGBColor(FColor(R, G, B, 255));
		}

		float Saturate(float Value) { return FMath::Clamp(Value, 0.0f, 1.0f); }

		const TCHAR* const Ellipsis = TEXT("…");

		/** Positive modulo for doubles. */
		double PosMod(double Value, double Period)
		{
			const double Result = FMath::Fmod(Value, Period);
			return Result < 0.0 ? Result + Period : Result;
		}

		FVector2f PolarPoint(const FVector2f& Center, double Radius, double Radians)
		{
			return FVector2f(Center.X + static_cast<float>(Radius * FMath::Cos(Radians)),
				Center.Y + static_cast<float>(Radius * FMath::Sin(Radians)));
		}
	}

	// ------------------------------------------------------------------ colour tokens
	const FLinearColor Paper = Srgb(0xE3, 0xD5, 0xB8);
	const FLinearColor PaperL = Srgb(0xEF, 0xE6, 0xD3);
	const FLinearColor PaperDD = Srgb(0xD8, 0xC8, 0xA6);
	const FLinearColor PaperD = Srgb(0xC4, 0xB1, 0x8D);
	const FLinearColor Ink = Srgb(0x16, 0x12, 0x0F);
	const FLinearColor Ink2 = Srgb(0x2B, 0x24, 0x1F);
	const FLinearColor Red = Srgb(0xC2, 0x16, 0x1C);
	const FLinearColor RedD = Srgb(0x8E, 0x10, 0x15);
	const FLinearColor RedL = Srgb(0xE3, 0x40, 0x2F);
	const FLinearColor RedHi = Srgb(0xF2, 0x55, 0x3D);
	const FLinearColor Player = Srgb(0x3D, 0x8B, 0xFF);
	const FLinearColor PlayerInk = Srgb(0x1F, 0x4F, 0xA8);
	const FLinearColor Enemy = Srgb(0xE3, 0x40, 0x2F);
	const FLinearColor Ochre = Srgb(0xB8, 0x86, 0x0B);
	const FLinearColor Olive = Srgb(0x4E, 0x7A, 0x2E);
	const FLinearColor Amber = Srgb(0xC8, 0x70, 0x1E);
	const FLinearColor Plum = Srgb(0x7A, 0x2E, 0x5A);

	FLinearColor WithAlpha(const FLinearColor& Color, float Alpha)
	{
		return FLinearColor(Color.R, Color.G, Color.B, Saturate(Alpha));
	}

	FLinearColor InkA(float Alpha) { return WithAlpha(Ink, Alpha); }
	FLinearColor PaperLA(float Alpha) { return WithAlpha(PaperL, Alpha); }

	FLinearColor TierColor(int32 Tier)
	{
		static const FLinearColor TierColors[6] = {
			Srgb(0x6E, 0x66, 0x5C), Srgb(0x4E, 0x7A, 0x2E), Srgb(0x2F, 0x5D, 0xA8),
			Srgb(0x6A, 0x3C, 0x8C), Srgb(0xB8, 0x86, 0x0B), Srgb(0xC2, 0x16, 0x1C) };
		return TierColors[FMath::Clamp(Tier, 1, 6) - 1];
	}

	FLinearColor TierColor(const FString& Roman)
	{
		static const TCHAR* const Numerals[6] = { TEXT("I"), TEXT("II"), TEXT("III"), TEXT("IV"), TEXT("V"), TEXT("VI") };
		for (int32 Index = 0; Index < 6; ++Index)
		{
			if (Roman == Numerals[Index]) return TierColor(Index + 1);
		}
		return TierColor(1);
	}

	FLinearColor AiFactionColor(int32 AiIndex)
	{
		switch (FMath::Clamp(AiIndex, 1, 3))
		{
		case 2: return Ochre;
		case 3: return Plum;
		default: return Red;
		}
	}

	// ------------------------------------------------------------------ easing
	namespace Ease
	{
		float OutExpo(float T) { return T >= 1.0f ? 1.0f : 1.0f - FMath::Pow(2.0f, -10.0f * T); }
		float OutCubic(float T) { return 1.0f - FMath::Pow(1.0f - T, 3.0f); }
		float InCubic(float T) { return T * T * T; }
		float InOutCubic(float T) { return T < 0.5f ? 4.0f * T * T * T : 1.0f - FMath::Pow(-2.0f * T + 2.0f, 3.0f) / 2.0f; }
		float InOutQuart(float T) { return T < 0.5f ? 8.0f * T * T * T * T : 1.0f - FMath::Pow(-2.0f * T + 2.0f, 4.0f) / 2.0f; }

		float CubicBezier(float X1, float Y1, float X2, float Y2, float T)
		{
			if (T <= 0.0f) return 0.0f;
			if (T >= 1.0f) return 1.0f;
			auto Bezier = [](float P1, float P2, float S)
			{
				const float Inv = 1.0f - S;
				return 3.0f * Inv * Inv * S * P1 + 3.0f * Inv * S * S * P2 + S * S * S;
			};
			// Bisection on x(s) = T; x is monotonic for the CSS control point range.
			float Lo = 0.0f, Hi = 1.0f, S = T;
			for (int32 Iteration = 0; Iteration < 24; ++Iteration)
			{
				if (Bezier(X1, X2, S) < T) Lo = S; else Hi = S;
				S = 0.5f * (Lo + Hi);
			}
			return Bezier(Y1, Y2, S);
		}

		float CssOut(float T) { return CubicBezier(0.16f, 1.0f, 0.3f, 1.0f, T); }
		float CssInOut(float T) { return CubicBezier(0.65f, 0.0f, 0.35f, 1.0f, T); }
		float CssIn(float T) { return CubicBezier(0.7f, 0.0f, 0.84f, 0.0f, T); }
	}

	float Reveal(float ElapsedSec, float DelaySec, float DurSec)
	{
		if (DurSec <= 0.0f) return ElapsedSec >= DelaySec ? 1.0f : 0.0f;
		return Ease::OutExpo(Saturate((ElapsedSec - DelaySec) / DurSec));
	}

	double RealTime() { return FPlatformTime::Seconds(); }

	// ------------------------------------------------------------------ assets (fonts + textures)
	namespace
	{
		enum EFace : int32
		{
			FaceSansBlack, FaceSansBold, FaceSansMedium, FaceSerifBlack, FaceCondSemiBold,
			FaceMonoMedium, FaceMonoExtraBold, FaceStencilBlack, FaceRussoRegular, FaceCount
		};

		enum EGroup : int32 { GroupSans, GroupSerif, GroupCond, GroupMono, GroupStencil, GroupRusso, GroupCount };

		const TCHAR* const FaceNames[FaceCount] = {
			TEXT("FF_TreadSans_Black"), TEXT("FF_TreadSans_Bold"), TEXT("FF_TreadSans_Medium"), TEXT("FF_TreadSerif_Black"),
			TEXT("FF_TreadCond_SemiBold"), TEXT("FF_TreadMono_Medium"), TEXT("FF_TreadMono_ExtraBold"),
			TEXT("FF_TreadStencil_Black"), TEXT("FF_TreadRusso_Regular") };

		struct FRoleDef
		{
			EGroup Group;
			const TCHAR* Entry;   // typeface name inside the group's default typeface
			EFace Face;
			const TCHAR* Weight;  // engine default font weight used when the asset is missing
		};

		// Index = EFontRole.
		const FRoleDef RoleDefs[9] = {
			{ GroupSans, TEXT("Black"), FaceSansBlack, TEXT("Bold") },
			{ GroupSans, TEXT("Bold"), FaceSansBold, TEXT("Bold") },
			{ GroupSans, TEXT("Medium"), FaceSansMedium, TEXT("Regular") },
			{ GroupSerif, TEXT("Black"), FaceSerifBlack, TEXT("Bold") },
			{ GroupCond, TEXT("SemiBold"), FaceCondSemiBold, TEXT("Bold") },
			{ GroupMono, TEXT("Medium"), FaceMonoMedium, TEXT("Regular") },
			{ GroupMono, TEXT("ExtraBold"), FaceMonoExtraBold, TEXT("Bold") },
			{ GroupStencil, TEXT("Black"), FaceStencilBlack, TEXT("Bold") },
			{ GroupRusso, TEXT("Regular"), FaceRussoRegular, TEXT("Regular") } };

		const TCHAR* const TexNames[static_cast<int32>(ETex::Count)] = {
			TEXT("T_UI_Paper"), TEXT("T_UI_Grain"), TEXT("T_UI_Vignette"), TEXT("T_UI_Logo"), TEXT("T_UI_Disc"),
			TEXT("T_UI_DiscShade"), TEXT("T_UI_Stamp_Approved"), TEXT("T_UI_Stamp_Cleared"), TEXT("T_UI_Stamp_Ready"),
			TEXT("T_UI_Stamp_Sortie"), TEXT("T_UI_InkSplat"), TEXT("T_UI_Giantess"), TEXT("T_UI_GiantessInDisc"),
			TEXT("T_UI_Hatch"), TEXT("T_UI_Halftone"), TEXT("T_UI_Scanlines") };

		bool IsTiledTex(ETex Which)
		{
			return Which == ETex::Grain || Which == ETex::Hatch || Which == ETex::Halftone || Which == ETex::Scanlines;
		}

		constexpr int32 TexCount = static_cast<int32>(ETex::Count);
		constexpr double RetrySeconds = 3.0;

		/** Keeps the loaded font faces, textures and their brushes / composite fonts alive and resident. */
		class FAssets final : public FGCObject
		{
		public:
			TObjectPtr<UFontFace> Faces[FaceCount];
			TObjectPtr<UTexture2D> Textures[TexCount];
			TSharedPtr<FSlateBrush> Brushes[TexCount];
			TSharedPtr<const FCompositeFont> Composites[GroupCount];

			double NextTryFace[FaceCount] = {};
			double NextTryTex[TexCount] = {};
			bool bWarnedFace[FaceCount] = {};
			bool bWarnedTex[TexCount] = {};
			int32 BuiltFaceMask = -1;
			bool bFontsComplete = false;

			virtual void AddReferencedObjects(FReferenceCollector& Collector) override
			{
				for (TObjectPtr<UFontFace>& Face : Faces) Collector.AddReferencedObject(Face);
				for (TObjectPtr<UTexture2D>& Texture : Textures) Collector.AddReferencedObject(Texture);
			}

			virtual FString GetReferencerName() const override { return TEXT("TreadUI::FAssets"); }

			/** Tries to load faces that are still missing (throttled) and rebuilds the composite fonts when the set changed. */
			void RefreshFonts()
			{
				if (bFontsComplete) return;
				int32 Mask = 0;
				const double Now = FPlatformTime::Seconds();
				for (int32 Index = 0; Index < FaceCount; ++Index)
				{
					if (!Faces[Index] && Now >= NextTryFace[Index])
					{
						const FString Path = FString::Printf(TEXT("/Game/Tread/UI/Fonts/%s.%s"), FaceNames[Index], FaceNames[Index]);
						Faces[Index] = LoadObject<UFontFace>(nullptr, *Path, nullptr, LOAD_Quiet | LOAD_NoWarn);
						if (!Faces[Index])
						{
							NextTryFace[Index] = Now + RetrySeconds;
							if (!bWarnedFace[Index])
							{
								bWarnedFace[Index] = true;
								UE_LOG(LogTreadUIStyle, Warning, TEXT("UI font %s is missing; the engine default font is used instead."), *Path);
							}
						}
					}
					if (Faces[Index]) Mask |= (1 << Index);
				}
				bFontsComplete = Mask == (1 << FaceCount) - 1;
				if (Mask != BuiltFaceMask)
				{
					BuiltFaceMask = Mask;
					for (int32 Group = 0; Group < GroupCount; ++Group) Composites[Group] = BuildComposite(static_cast<EGroup>(Group));
				}
			}

			const FCompositeFont* GetComposite(EGroup Group) const { return Composites[Group].Get(); }

			/** Brush of a texture, loading it on first use. Null while the asset is missing. */
			const FSlateBrush* GetBrush(ETex Which)
			{
				const int32 Index = static_cast<int32>(Which);
				if (Brushes[Index].IsValid()) return Brushes[Index].Get();
				const double Now = FPlatformTime::Seconds();
				if (Now < NextTryTex[Index]) return nullptr;

				const FString Path = FString::Printf(TEXT("/Game/Tread/UI/Style/%s.%s"), TexNames[Index], TexNames[Index]);
				UTexture2D* Loaded = LoadObject<UTexture2D>(nullptr, *Path, nullptr, LOAD_Quiet | LOAD_NoWarn);
				if (!Loaded)
				{
					NextTryTex[Index] = Now + RetrySeconds;
					if (!bWarnedTex[Index])
					{
						bWarnedTex[Index] = true;
						UE_LOG(LogTreadUIStyle, Warning, TEXT("UI texture %s is missing; draws of it are skipped."), *Path);
					}
					return nullptr;
				}

				Textures[Index] = Loaded;
				TSharedPtr<FSlateBrush> NewBrush = MakeShared<FSlateBrush>();
				NewBrush->DrawAs = ESlateBrushDrawType::Image;
				NewBrush->Tiling = IsTiledTex(Which) ? ESlateBrushTileType::Both : ESlateBrushTileType::NoTile;
				NewBrush->SetResourceObject(Loaded);
				NewBrush->SetImageSize(FVector2f(static_cast<float>(Loaded->GetSizeX()), static_cast<float>(Loaded->GetSizeY())));
				Brushes[Index] = NewBrush;
				return NewBrush.Get();
			}

		private:
			TSharedPtr<const FCompositeFont> BuildComposite(EGroup Group) const
			{
				TSharedRef<FStandaloneCompositeFont> Composite = MakeShared<FStandaloneCompositeFont>();
				for (const FRoleDef& Def : RoleDefs)
				{
					if (Def.Group != Group || !Faces[Def.Face]) continue;
					FTypefaceEntry& Entry = Composite->DefaultTypeface.Fonts.AddDefaulted_GetRef();
					Entry.Name = FName(Def.Entry);
					Entry.Font = FFontData(Faces[Def.Face].Get());
				}
				if (Composite->DefaultTypeface.Fonts.IsEmpty()) return nullptr;
				// Sans Bold carries the CJK glyphs for every role.
				if (Faces[FaceSansBold])
				{
					FTypefaceEntry& Fallback = Composite->FallbackTypeface.Typeface.Fonts.AddDefaulted_GetRef();
					Fallback.Name = FName(TEXT("Fallback"));
					Fallback.Font = FFontData(Faces[FaceSansBold].Get());
				}
				return Composite;
			}
		};

		FAssets* GAssets = nullptr;
		bool GAssetsClosed = false;

		FAssets* GetAssets()
		{
			if (GAssetsClosed) return nullptr;
			if (!GAssets)
			{
				GAssets = new FAssets();
				// Drop the GC hooks before the UObject system goes away.
				FCoreDelegates::OnEnginePreExit.AddLambda([]()
				{
					GAssetsClosed = true;
					delete GAssets;
					GAssets = nullptr;
				});
			}
			return GAssets;
		}
	}

	// ------------------------------------------------------------------ fonts
	FSlateFontInfo Font(EFontRole Role, float SizePt, float TrackingEm)
	{
		const float Size = FMath::Max(1.0f, SizePt);
		const FRoleDef& Def = RoleDefs[static_cast<int32>(Role)];
		FSlateFontInfo Info;
		bool bResolved = false;
		if (FAssets* Assets = GetAssets())
		{
			Assets->RefreshFonts();
			if (Assets->GetComposite(Def.Group) && Assets->Faces[Def.Face])
			{
				Info = FSlateFontInfo(Assets->Composites[Def.Group], Size, FName(Def.Entry));
				bResolved = true;
			}
		}
		if (!bResolved) Info = FCoreStyle::GetDefaultFontStyle(FName(Def.Weight), FMath::RoundToInt(Size));
		// Slate letter spacing is whole pixels: spacing_px = (int16)(LetterSpacing * PaintScale * Size / 1000) with Size in points,
		// while the CSS em is Size * 96/72 px (times the paint scale on screen). Aim at the nearest whole pixel and land a quarter
		// pixel beyond it so the truncation can never drop to the pixel below.
		if (TrackingEm == 0.0f)
		{
			Info.LetterSpacing = 0;
		}
		else
		{
			const float Scale = FMath::Max(GPaintFontScale, 0.01f);
			const float WantPx = FMath::RoundToFloat(TrackingEm * Size * (96.0f / 72.0f) * Scale);
			Info.LetterSpacing = WantPx == 0.0f ? 0 : FMath::RoundToInt((WantPx + FMath::Sign(WantPx) * 0.25f) * 1000.0f / (Scale * Size));
		}
		return Info;
	}

	void SetPaintFontScale(float Scale) { GPaintFontScale = Scale > 0.01f ? Scale : 1.0f; }
	float GetPaintFontScale() { return GPaintFontScale; }

	namespace
	{
		/** One text line measured and shaped at the scale Slate rasterises it at. */
		struct FTextLine
		{
			/** Local px: shaped width incl. letter spacing and CSS trailing spacing, legacy line height. */
			FVector2f Size = FVector2f::ZeroVector;
			/** The glyph sequence the renderer draws. Null without a renderer, for multi-line text, or when shaping produced nothing. */
			FShapedGlyphSequencePtr Shaped;
		};

		FTextLine MeasureLine(const FString& Value, const FSlateFontInfo& FontInfo, float PaintScale)
		{
			FTextLine Result;
			if (FSlateApplication::IsInitialized())
			{
				if (FSlateRenderer* Renderer = FSlateApplication::Get().GetRenderer())
				{
					// The legacy font measure ignores LetterSpacing and works at scale 1; keep it for the height and for multi-line text,
					// but take the width of single lines from the glyph sequence the renderer really draws.
					Result.Size = FVector2f(Renderer->GetFontMeasureService()->Measure(Value, FontInfo));
					if (!Value.IsEmpty() && !Value.Contains(TEXT("\n")))
					{
						const float Scale = FMath::Max(PaintScale, 0.01f);
						const FShapedGlyphSequenceRef Shaped = Renderer->GetFontCache()->ShapeBidirectionalText(
							Value, FontInfo, Scale, TextBiDi::ETextDirection::LeftToRight, GetDefaultTextShapingMethod());
						const float Width = static_cast<float>(Shaped->GetMeasuredWidth());
						if (Width > 0.0f)
						{
							// Slate puts the spacing between glyphs only; CSS also adds it after the last one.
							const float Trailing = FontInfo.LetterSpacing != 0
								? static_cast<float>(static_cast<int16>(FontInfo.LetterSpacing * Scale * FontInfo.Size / 1000.0f)) : 0.0f;
							Result.Size.X = (Width + Trailing) / Scale;
						}
						if (Shaped->GetGlyphsToRender().Num() > 0 && Shaped->GetMaxTextHeight() > 0) Result.Shaped = Shaped;
					}
					return Result;
				}
			}
			// No renderer (-nullrhi): rough estimate, only used for layout of invisible output.
			const float Px = FontInfo.Size * (96.0f / 72.0f);
			float EstimatedWidth = 0.0f;
			for (const TCHAR Character : Value) EstimatedWidth += Character < 0x250 ? Px * 0.55f : Px;
			Result.Size = FVector2f(EstimatedWidth, Px * 1.25f);
			return Result;
		}
	}

	FVector2f TextSize(const FString& Value, const FSlateFontInfo& FontInfo)
	{
		return MeasureLine(Value, FontInfo, GPaintFontScale).Size;
	}

	FString Ellipsize(const FString& Value, const FSlateFontInfo& FontInfo, float MaxWidth)
	{
		if (Value.IsEmpty() || TextSize(Value, FontInfo).X <= MaxWidth) return Value;
		int32 Lo = 0, Hi = Value.Len();   // longest prefix length that fits together with the ellipsis
		while (Lo < Hi)
		{
			const int32 Mid = (Lo + Hi + 1) / 2;
			if (TextSize(Value.Left(Mid) + Ellipsis, FontInfo).X <= MaxWidth) Lo = Mid; else Hi = Mid - 1;
		}
		return Lo > 0 ? Value.Left(Lo) + Ellipsis : FString(Ellipsis);
	}

	FSlateFontInfo FitFont(const FString& Value, EFontRole Role, float MaxPt, float MinPt, float MaxWidth, float TrackingEm)
	{
		float Size = FMath::Max(MaxPt, MinPt);
		FSlateFontInfo Info = Font(Role, Size, TrackingEm);
		float Width = TextSize(Value, Info).X;
		if (Width <= MaxWidth || Width <= 0.0f) return Info;
		Size = FMath::Clamp(Size * MaxWidth / Width, MinPt, MaxPt);
		Info = Font(Role, Size, TrackingEm);
		for (int32 Iteration = 0; Iteration < 12 && Size > MinPt && TextSize(Value, Info).X > MaxWidth; ++Iteration)
		{
			Size = FMath::Max(MinPt, Size - 0.5f);
			Info = Font(Role, Size, TrackingEm);
		}
		return Info;
	}

	// ------------------------------------------------------------------ texture brushes
	const FSlateBrush* Brush(ETex Which)
	{
		if (FAssets* Assets = GetAssets())
		{
			if (const FSlateBrush* Found = Assets->GetBrush(Which)) return Found;
		}
		static const FSlateNoResource NoBrush;
		return &NoBrush;
	}

	bool HasTex(ETex Which)
	{
		return Brush(Which)->GetDrawType() != ESlateBrushDrawType::NoDrawType;
	}

	FVector2f TexSize(ETex Which)
	{
		const FSlateBrush* Found = Brush(Which);
		return Found->GetDrawType() == ESlateBrushDrawType::NoDrawType ? FVector2f::ZeroVector : FVector2f(Found->ImageSize);
	}

	void Preload()
	{
		if (FAssets* Assets = GetAssets())
		{
			Assets->RefreshFonts();
			for (int32 Index = 0; Index < TexCount; ++Index) Assets->GetBrush(static_cast<ETex>(Index));
		}
	}

	// ------------------------------------------------------------------ drawing internals
	namespace
	{
		const FSlateBrush* WhiteBrush() { return FCoreStyle::Get().GetBrush(TEXT("WhiteBrush")); }

		bool GetWhiteHandle(FSlateResourceHandle& OutHandle)
		{
			if (!FSlateApplication::IsInitialized()) return false;
			FSlateRenderer* Renderer = FSlateApplication::Get().GetRenderer();
			const FSlateBrush* White = WhiteBrush();
			if (!Renderer || !White) return false;
			OutHandle = Renderer->GetResourceHandle(*White);
			return true;
		}

		FColor VertexColor(const FLinearColor& Color) { return Color.ToFColor(true); }

		/** Accumulates coloured triangles in local space and submits them as ONE custom-verts element. */
		struct FTriBatch
		{
			explicit FTriBatch(const FGeometry& InGeo) : Transform(InGeo.GetAccumulatedRenderTransform()) {}

			FSlateRenderTransform Transform;
			TArray<FSlateVertex> Verts;
			TArray<SlateIndex> Indices;

			SlateIndex AddVert(const FVector2f& Point, const FColor& Color)
			{
				Verts.Add(FSlateVertex::Make<ESlateVertexRounding::Disabled>(Transform, Point, FVector2f::ZeroVector, Color));
				return static_cast<SlateIndex>(Verts.Num() - 1);
			}

			void Fan(const TArray<FVector2f>& Points, const FLinearColor& Color)
			{
				if (Points.Num() < 3 || Color.A <= 0.0f) return;
				const FColor Packed = VertexColor(Color);
				const SlateIndex First = AddVert(Points[0], Packed);
				SlateIndex Previous = AddVert(Points[1], Packed);
				for (int32 Index = 2; Index < Points.Num(); ++Index)
				{
					const SlateIndex Current = AddVert(Points[Index], Packed);
					Indices.Add(First); Indices.Add(Previous); Indices.Add(Current);
					Previous = Current;
				}
			}

			void Quad4(const FVector2f& A, const FVector2f& B, const FVector2f& C, const FVector2f& D, const FLinearColor& Color)
			{
				if (Color.A <= 0.0f) return;
				const FColor Packed = VertexColor(Color);
				const SlateIndex IA = AddVert(A, Packed), IB = AddVert(B, Packed), IC = AddVert(C, Packed), ID = AddVert(D, Packed);
				Indices.Add(IA); Indices.Add(IB); Indices.Add(IC);
				Indices.Add(IA); Indices.Add(IC); Indices.Add(ID);
			}

			void Rect(const FVector2f& Pos, const FVector2f& Size, const FLinearColor& Color)
			{
				if (Size.X <= 0.0f || Size.Y <= 0.0f) return;
				Quad4(Pos, FVector2f(Pos.X + Size.X, Pos.Y), Pos + Size, FVector2f(Pos.X, Pos.Y + Size.Y), Color);
			}

			/** Hollow rectangle as four non-overlapping strips. */
			void FrameRect(const FVector2f& Pos, const FVector2f& Size, float Thickness, const FLinearColor& Color)
			{
				const float T = FMath::Clamp(Thickness, 0.0f, FMath::Min(Size.X, Size.Y) * 0.5f);
				if (T <= 0.0f) return;
				Rect(Pos, FVector2f(Size.X, T), Color);
				Rect(FVector2f(Pos.X, Pos.Y + Size.Y - T), FVector2f(Size.X, T), Color);
				Rect(FVector2f(Pos.X, Pos.Y + T), FVector2f(T, Size.Y - 2.0f * T), Color);
				Rect(FVector2f(Pos.X + Size.X - T, Pos.Y + T), FVector2f(T, Size.Y - 2.0f * T), Color);
			}

			void Flush(FSlateWindowElementList& Out, int32 Layer)
			{
				if (Indices.Num() < 3) return;
				FSlateResourceHandle Handle;
				if (GetWhiteHandle(Handle))
				{
					FSlateDrawElement::MakeCustomVerts(Out, static_cast<uint32>(Layer), Handle, Verts, Indices, nullptr, 0, 0);
				}
				Verts.Reset();
				Indices.Reset();
			}
		};

		/** Antialiased fringe on the diagonal edges of an opaque polygon (straight edges stay pixel exact). */
		void StrokeDiagonals(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const TArray<FVector2f>& Points,
			const FLinearColor& Color)
		{
			const int32 Count = Points.Num();
			for (int32 Index = 0; Index < Count; ++Index)
			{
				const FVector2f& A = Points[Index];
				const FVector2f& B = Points[(Index + 1) % Count];
				if (FMath::Abs(A.X - B.X) > 0.01f && FMath::Abs(A.Y - B.Y) > 0.01f) Line(Out, Geo, Layer, A, B, Color, 1.0f);
			}
		}

		/** Outline points of a box with cut corners, clockwise from the top-left. Flagged corners always emit two points. */
		void BuildCutPoints(const FVector2f& Pos, const FVector2f& Size, float Cut, ECorner Corner, TArray<FVector2f>& OutPoints)
		{
			OutPoints.Reset();
			const float C = FMath::Clamp(Cut, 0.0f, FMath::Min(Size.X, Size.Y));
			const float X0 = Pos.X, Y0 = Pos.Y, X1 = Pos.X + Size.X, Y1 = Pos.Y + Size.Y;
			if (EnumHasAnyFlags(Corner, ECorner::TL)) { OutPoints.Add(FVector2f(X0, Y0 + C)); OutPoints.Add(FVector2f(X0 + C, Y0)); }
			else OutPoints.Add(FVector2f(X0, Y0));
			if (EnumHasAnyFlags(Corner, ECorner::TR)) { OutPoints.Add(FVector2f(X1 - C, Y0)); OutPoints.Add(FVector2f(X1, Y0 + C)); }
			else OutPoints.Add(FVector2f(X1, Y0));
			if (EnumHasAnyFlags(Corner, ECorner::BR)) { OutPoints.Add(FVector2f(X1, Y1 - C)); OutPoints.Add(FVector2f(X1 - C, Y1)); }
			else OutPoints.Add(FVector2f(X1, Y1));
			if (EnumHasAnyFlags(Corner, ECorner::BL)) { OutPoints.Add(FVector2f(X0 + C, Y1)); OutPoints.Add(FVector2f(X0, Y1 - C)); }
			else OutPoints.Add(FVector2f(X0, Y1));
		}

		/** Sutherland-Hodgman clip of a convex polygon against x <= MaxX. */
		void ClipPolyMaxX(const TArray<FVector2f>& Input, float MaxX, TArray<FVector2f>& OutPoints)
		{
			OutPoints.Reset();
			const int32 Count = Input.Num();
			for (int32 Index = 0; Index < Count; ++Index)
			{
				const FVector2f& A = Input[Index];
				const FVector2f& B = Input[(Index + 1) % Count];
				const bool bAIn = A.X <= MaxX, bBIn = B.X <= MaxX;
				if (bAIn) OutPoints.Add(A);
				if (bAIn != bBIn)
				{
					const float T = (MaxX - A.X) / (B.X - A.X);
					OutPoints.Add(A + (B - A) * T);
				}
			}
		}

		/** Tiled texture over a box with one cut corner (TL or BR), skipping the cut square so nothing leaks outside the shape. */
		void TiledCutOut(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, ETex Which, const FVector2f& Pos,
			const FVector2f& Size, const FLinearColor& Tint, float TileScale, float Cut, ECorner Corner)
		{
			const float C = FMath::Clamp(Cut, 0.0f, FMath::Min(Size.X, Size.Y));
			if (C <= 0.0f || Corner == ECorner::None)
			{
				Tiled(Out, Geo, Layer, Which, Pos, Size, Tint, TileScale);
			}
			else if (Corner == ECorner::TL)
			{
				Tiled(Out, Geo, Layer, Which, FVector2f(Pos.X + C, Pos.Y), FVector2f(Size.X - C, C), Tint, TileScale);
				Tiled(Out, Geo, Layer, Which, FVector2f(Pos.X, Pos.Y + C), FVector2f(Size.X, Size.Y - C), Tint, TileScale);
			}
			else
			{
				Tiled(Out, Geo, Layer, Which, Pos, FVector2f(Size.X, Size.Y - C), Tint, TileScale);
				Tiled(Out, Geo, Layer, Which, FVector2f(Pos.X, Pos.Y + Size.Y - C), FVector2f(Size.X - C, C), Tint, TileScale);
			}
		}
	}

	// ------------------------------------------------------------------ primitives
	void Quad(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos, const FVector2f& Size,
		const FLinearColor& Color)
	{
		if (Color.A <= 0.0f || Size.X <= 0.0f || Size.Y <= 0.0f) return;
		FSlateDrawElement::MakeBox(Out, static_cast<uint32>(Layer), Geo.ToPaintGeometry(Size, FSlateLayoutTransform(Pos)),
			WhiteBrush(), ESlateDrawEffect::None, Color);
	}

	void Poly(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const TArray<FVector2f>& Points,
		const FLinearColor& Color, bool bAntiAlias)
	{
		if (Points.Num() < 3 || Color.A <= 0.0f) return;
		FTriBatch Batch(Geo);
		Batch.Fan(Points, Color);
		Batch.Flush(Out, Layer);
		if (bAntiAlias && Color.A >= 0.99f) StrokeDiagonals(Out, Geo, Layer, Points, Color);
	}

	void RotatedQuad(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos, const FVector2f& Size,
		const FLinearColor& Color, float RotationDeg, const FVector2f& Pivot)
	{
		const FVector2f Anchor = Pos + FVector2f(Size.X * Pivot.X, Size.Y * Pivot.Y);
		const float Radians = FMath::DegreesToRadians(RotationDeg);
		const float Cos = FMath::Cos(Radians), Sin = FMath::Sin(Radians);
		TArray<FVector2f> Corners = { Pos, FVector2f(Pos.X + Size.X, Pos.Y), Pos + Size, FVector2f(Pos.X, Pos.Y + Size.Y) };
		for (FVector2f& Corner : Corners)
		{
			const FVector2f Offset = Corner - Anchor;
			Corner = Anchor + FVector2f(Offset.X * Cos - Offset.Y * Sin, Offset.X * Sin + Offset.Y * Cos);
		}
		Poly(Out, Geo, Layer, Corners, Color, true);
	}

	void Frame(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos, const FVector2f& Size,
		const FLinearColor& Color, float Thickness)
	{
		FTriBatch Batch(Geo);
		Batch.FrameRect(Pos, Size, Thickness, Color);
		Batch.Flush(Out, Layer);
	}

	void CutBox(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos, const FVector2f& Size,
		const FLinearColor& Fill, float Cut, ECorner Corner, float Border, const FLinearColor& BorderColor)
	{
		if (Size.X <= 0.0f || Size.Y <= 0.0f) return;
		const float BorderWidth = FMath::Clamp(Border, 0.0f, FMath::Min(Size.X, Size.Y) * 0.5f);
		TArray<FVector2f> Outer;
		BuildCutPoints(Pos, Size, Cut, Corner, Outer);

		FTriBatch Batch(Geo);
		FLinearColor EdgeColor = Fill;
		if (BorderWidth > 0.0f)
		{
			// Ring between the outer outline and the inset outline (same vertex count), then the fill inside.
			TArray<FVector2f> Inner;
			BuildCutPoints(Pos + FVector2f(BorderWidth, BorderWidth), Size - FVector2f(2.0f * BorderWidth, 2.0f * BorderWidth),
				FMath::Max(0.0f, Cut - 0.586f * BorderWidth), Corner, Inner);
			const int32 Count = Outer.Num();
			for (int32 Index = 0; Index < Count; ++Index)
			{
				const int32 Next = (Index + 1) % Count;
				Batch.Quad4(Outer[Index], Outer[Next], Inner[Next], Inner[Index], BorderColor);
			}
			Batch.Fan(Inner, Fill);
			EdgeColor = BorderColor;
		}
		else
		{
			Batch.Fan(Outer, Fill);
		}
		Batch.Flush(Out, Layer);
		if (EdgeColor.A >= 0.99f && Cut > 0.0f && Corner != ECorner::None) StrokeDiagonals(Out, Geo, Layer, Outer, EdgeColor);
	}

	void HardShadowBox(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos,
		const FVector2f& Size, const FLinearColor& Fill, float Cut, ECorner Corner, const FVector2f& ShadowOffset,
		float Border, const FLinearColor& BorderColor, const FLinearColor& ShadowColor)
	{
		CutBox(Out, Geo, Layer, Pos + ShadowOffset, Size, ShadowColor, Cut, Corner);
		CutBox(Out, Geo, Layer, Pos, Size, Fill, Cut, Corner, Border, BorderColor);
	}

	void Tex(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, ETex Which, const FVector2f& Pos,
		const FVector2f& Size, const FLinearColor& Tint, float RotationDeg, float Scale)
	{
		const FSlateBrush* Texture = Brush(Which);
		if (Texture->GetDrawType() == ESlateBrushDrawType::NoDrawType || Tint.A <= 0.0f || Size.X <= 0.0f || Size.Y <= 0.0f) return;
		if (FMath::IsNearlyZero(RotationDeg) && FMath::IsNearlyEqual(Scale, 1.0f))
		{
			FSlateDrawElement::MakeBox(Out, static_cast<uint32>(Layer), Geo.ToPaintGeometry(Size, FSlateLayoutTransform(Pos)),
				Texture, ESlateDrawEffect::None, Tint);
			return;
		}
		const FSlateRenderTransform Transform(Concatenate(FScale2D(FMath::Max(Scale, 0.001f)), FQuat2D(FMath::DegreesToRadians(RotationDeg))));
		FSlateDrawElement::MakeBox(Out, static_cast<uint32>(Layer),
			Geo.ToPaintGeometry(Size, FSlateLayoutTransform(Pos), Transform, FVector2f(0.5f, 0.5f)),
			Texture, ESlateDrawEffect::None, Tint);
	}

	void Tiled(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, ETex Which, const FVector2f& Pos,
		const FVector2f& Size, const FLinearColor& Tint, float TileScale)
	{
		const FSlateBrush* Texture = Brush(Which);
		if (Texture->GetDrawType() == ESlateBrushDrawType::NoDrawType || Tint.A <= 0.0f || Size.X <= 0.0f || Size.Y <= 0.0f) return;
		const float K = FMath::Max(TileScale, 0.001f);
		if (FMath::IsNearlyEqual(K, 1.0f))
		{
			FSlateDrawElement::MakeBox(Out, static_cast<uint32>(Layer), Geo.ToPaintGeometry(Size, FSlateLayoutTransform(Pos)),
				Texture, ESlateDrawEffect::None, Tint);
			return;
		}
		// Large tiles (e.g. the 1024 px grain): lay the tiles out explicitly as unscaled boxes. The render-transform path
		// below sampled the grain magnified (soft white blobs instead of fine specks) at layout scales other than 1.
		const FVector2f TexPx(Texture->ImageSize);
		const float TileW = TexPx.X * K, TileH = TexPx.Y * K;
		if (TexPx.X > 0.0f && TexPx.Y > 0.0f && TileW >= 64.0f && TileH >= 64.0f
			&& FMath::CeilToInt(Size.X / TileW) * FMath::CeilToInt(Size.Y / TileH) <= 144)
		{
			FSlateBrush Single = *Texture;
			Single.Tiling = ESlateBrushTileType::NoTile;
			for (float Y = 0.0f; Y < Size.Y - 0.01f; Y += TileH)
			{
				const float H = FMath::Min(TileH, Size.Y - Y);
				for (float X = 0.0f; X < Size.X - 0.01f; X += TileW)
				{
					const float W = FMath::Min(TileW, Size.X - X);
					Single.SetUVRegion(FBox2f(FVector2f(0.0f, 0.0f), FVector2f(W / TileW, H / TileH)));
					FSlateDrawElement::MakeBox(Out, static_cast<uint32>(Layer),
						Geo.ToPaintGeometry(FVector2f(W, H), FSlateLayoutTransform(Pos + FVector2f(X, Y))),
						&Single, ESlateDrawEffect::None, Tint);
				}
			}
			return;
		}
		// The batcher tiles by LocalSize / textureSize, so lay out a 1/K sized box and scale it back up by K.
		const FSlateRenderTransform Transform{FScale2D(K)};
		FSlateDrawElement::MakeBox(Out, static_cast<uint32>(Layer),
			Geo.ToPaintGeometry(Size / K, FSlateLayoutTransform(Pos), Transform, FVector2f::ZeroVector),
			Texture, ESlateDrawEffect::None, Tint);
	}

	namespace
	{
		/**
		 * Draws one measured line with its Pivot (0..1 inside Measured.Size) at Pos, rotated clockwise by RotationDeg around it.
		 * Single lines go out as shaped glyph sequences (FSlateDrawElement::MakeShapedText): the legacy MakeText path lays glyphs
		 * out per character and ignores FSlateFontInfo::LetterSpacing, so tracked text would render tight while TextSize()
		 * measures it wide. Both paths put the baseline at the same place, so the line box top does not move. Multi-line text and
		 * the no-renderer case keep MakeText.
		 */
		void EmitLine(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FString& Value, const FSlateFontInfo& FontInfo,
			const FTextLine& Measured, const FVector2f& Pos, const FLinearColor& Color, float RotationDeg, const FVector2f& Pivot)
		{
			const FVector2f TopLeft = Pos - FVector2f(Measured.Size.X * Pivot.X, Measured.Size.Y * Pivot.Y);
			const FPaintGeometry Paint = FMath::IsNearlyZero(RotationDeg)
				? Geo.ToPaintGeometry(Measured.Size, FSlateLayoutTransform(TopLeft))
				: Geo.ToPaintGeometry(Measured.Size, FSlateLayoutTransform(TopLeft), FSlateRenderTransform{FQuat2D(FMath::DegreesToRadians(RotationDeg))}, Pivot);
			if (Measured.Shaped.IsValid())
			{
				FSlateDrawElement::MakeShapedText(Out, static_cast<uint32>(Layer), Paint, Measured.Shaped.ToSharedRef(), ESlateDrawEffect::None,
					Color, FLinearColor::Transparent);
				return;
			}
			FSlateDrawElement::MakeText(Out, static_cast<uint32>(Layer), Paint, Value, FontInfo, ESlateDrawEffect::None, Color);
		}

		/** Scale Slate will rasterise text drawn under Geo at (the accumulated layout scale); shaping must use exactly this. */
		float DrawScaleOf(const FGeometry& Geo) { return FMath::Max(Geo.GetAccumulatedLayoutTransform().GetScale(), 0.01f); }
	}

	void Text(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FString& Value,
		const FSlateFontInfo& FontInfo, const FVector2f& Pos, const FLinearColor& Color, float RotationDeg, const FVector2f& Pivot)
	{
		if (Value.IsEmpty() || Color.A <= 0.0f) return;
		EmitLine(Out, Geo, Layer, Value, FontInfo, MeasureLine(Value, FontInfo, DrawScaleOf(Geo)), Pos, Color, RotationDeg, Pivot);
	}

	void TextShadow(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FString& Value,
		const FSlateFontInfo& FontInfo, const FVector2f& Pos, const FLinearColor& Color, const FVector2f& ShadowOffset,
		const FLinearColor& ShadowColor, float RotationDeg, const FVector2f& Pivot)
	{
		if (Value.IsEmpty() || (Color.A <= 0.0f && ShadowColor.A <= 0.0f)) return;
		// Measure and shape once; the shadow and the face share the glyph sequence.
		const FTextLine Measured = MeasureLine(Value, FontInfo, DrawScaleOf(Geo));
		if (ShadowColor.A > 0.0f) EmitLine(Out, Geo, Layer, Value, FontInfo, Measured, Pos + ShadowOffset, ShadowColor, RotationDeg, Pivot);
		if (Color.A > 0.0f) EmitLine(Out, Geo, Layer, Value, FontInfo, Measured, Pos, Color, RotationDeg, Pivot);
	}

	void Lines(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const TArray<FVector2f>& Points,
		const FLinearColor& Color, float Thickness)
	{
		if (Points.Num() < 2 || Color.A <= 0.0f) return;
		FSlateDrawElement::MakeLines(Out, static_cast<uint32>(Layer), Geo.ToPaintGeometry(), Points, ESlateDrawEffect::None,
			Color, true, Thickness);
	}

	void Line(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& A, const FVector2f& B,
		const FLinearColor& Color, float Thickness)
	{
		if (Color.A <= 0.0f) return;
		TArray<FVector2f> Points;
		Points.Reserve(2);
		Points.Add(A);
		Points.Add(B);
		FSlateDrawElement::MakeLines(Out, static_cast<uint32>(Layer), Geo.ToPaintGeometry(), MoveTemp(Points),
			ESlateDrawEffect::None, Color, true, Thickness);
	}

	void Arc(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Center, float Radius,
		float StartDeg, float EndDeg, const FLinearColor& Color, float Thickness, int32 Segments)
	{
		const float Sweep = EndDeg - StartDeg;
		const int32 Steps = FMath::Max(2, FMath::CeilToInt(static_cast<float>(FMath::Max(Segments, 3)) * FMath::Abs(Sweep) / 360.0f));
		TArray<FVector2f> Points;
		Points.Reserve(Steps + 1);
		for (int32 Index = 0; Index <= Steps; ++Index)
		{
			const double Degrees = StartDeg + static_cast<double>(Sweep) * Index / Steps;
			Points.Add(PolarPoint(Center, Radius, Degrees * kPi / 180.0));
		}
		Lines(Out, Geo, Layer, Points, Color, Thickness);
	}

	void Ring(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Center, float Radius,
		const FLinearColor& Color, float Thickness, int32 Segments)
	{
		Arc(Out, Geo, Layer, Center, Radius, 0.0f, 360.0f, Color, Thickness, Segments);
	}

	void Ticks(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Center, float InnerR,
		float OuterR, int32 Count, float PhaseDeg, const FLinearColor& Color, float Thickness, float SweepDeg)
	{
		if (Count <= 0) return;
		const bool bFullCircle = SweepDeg >= 359.99f;
		for (int32 Index = 0; Index < Count; ++Index)
		{
			const double Fraction = bFullCircle || Count == 1 ? static_cast<double>(Index) / Count : static_cast<double>(Index) / (Count - 1);
			const double Radians = (PhaseDeg + SweepDeg * Fraction) * kPi / 180.0;
			Line(Out, Geo, Layer, PolarPoint(Center, InnerR, Radians), PolarPoint(Center, OuterR, Radians), Color, Thickness);
		}
	}

	void SignalRings(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Center, float R,
		const FLinearColor& LineColor, const FLinearColor& Accent, double TimeSec, float Speed, float Alpha, float Spread,
		float Scale, bool bStar, bool bLabel)
	{
		const float S = FMath::Max(Scale, 0.01f);
		const double RotDeg = TimeSec * Speed;                // HTML: rot = t * speed (degrees)
		const double RotRad = RotDeg * kPi / 180.0;
		const float AccentAlpha = FMath::Min(1.0f, Alpha * 1.6f);

		// static hairline
		Ring(Out, Geo, Layer, Center, R + 8.0f * S, WithAlpha(LineColor, Alpha * 0.8f), 1.2f * S);

		// rotating tick ring (120 ticks, long every 10th, medium every 5th)
		const FLinearColor TickColor = WithAlpha(LineColor, Alpha);
		for (int32 Index = 0; Index < 120; ++Index)
		{
			const double Q = RotRad + Index * kPi / 60.0;
			const float Len = Index % 10 == 0 ? 15.0f : Index % 5 == 0 ? 9.0f : 4.0f;
			Line(Out, Geo, Layer, PolarPoint(Center, R + 16.0f * S, Q), PolarPoint(Center, R + (16.0f + Len) * S, Q), TickColor, 1.5f * S);
		}

		// counter-rotating arcs
		const float R2 = R + 46.0f * S;
		const double BaseDeg = -RotDeg * 1.7;
		static const float ArcRanges[3][2] = { { 0.0f, 64.0f }, { 150.0f, 172.0f }, { 214.0f, 296.0f } };
		for (const float (&Range)[2] : ArcRanges)
		{
			Arc(Out, Geo, Layer, Center, R2, static_cast<float>(BaseDeg + Range[0]), static_cast<float>(BaseDeg + Range[1]), TickColor, 4.0f * S);
		}
		Arc(Out, Geo, Layer, Center, R2, static_cast<float>(BaseDeg + 300.0), static_cast<float>(BaseDeg + 318.0),
			WithAlpha(Accent, AccentAlpha), 4.0f * S);

		// orbit marker (triangle) + bearing label
		const double MarkerRad = RotRad * 2.4;
		const FVector2f Marker = PolarPoint(Center, R2 + 14.0f * S, MarkerRad);
		{
			TArray<FVector2f> Triangle;
			Triangle.Add(Marker + FVector2f(static_cast<float>(FMath::Cos(MarkerRad) * -9.0 * S), static_cast<float>(FMath::Sin(MarkerRad) * -9.0 * S)));
			Triangle.Add(Marker + FVector2f(static_cast<float>(FMath::Cos(MarkerRad + 2.4) * 9.0 * S), static_cast<float>(FMath::Sin(MarkerRad + 2.4) * 9.0 * S)));
			Triangle.Add(Marker + FVector2f(static_cast<float>(FMath::Cos(MarkerRad - 2.4) * 9.0 * S), static_cast<float>(FMath::Sin(MarkerRad - 2.4) * 9.0 * S)));
			Poly(Out, Geo, Layer, Triangle, WithAlpha(Accent, AccentAlpha), true);
		}
		if (bLabel)
		{
			const double Bearing = PosMod(MarkerRad * 180.0 / kPi, 360.0);
			const FString Label = FString::Printf(TEXT("%03d°"), FMath::FloorToInt(static_cast<float>(Bearing)));
			const FVector2f LabelPos(Marker.X + static_cast<float>(FMath::Cos(MarkerRad) * 24.0 * S) - 16.0f * S,
				Marker.Y + static_cast<float>(FMath::Sin(MarkerRad) * 24.0 * S) + 5.0f * S);
			Text(Out, Geo, Layer, Label, Font(EFontRole::MonoBold, Pt(14.0f, S)), LabelPos, WithAlpha(LineColor, Alpha * 1.2f),
				0.0f, FVector2f(0.0f, 0.78f));
		}

		// cardinal ticks
		const FLinearColor CardinalColor = WithAlpha(LineColor, Alpha * 0.9f);
		for (int32 Index = 0; Index < 4; ++Index)
		{
			const double Q = Index * kPi / 2.0;
			Line(Out, Geo, Layer, PolarPoint(Center, R2 + 26.0f * S, Q), PolarPoint(Center, R2 + 46.0f * S, Q), CardinalColor, 2.0f * S);
		}

		// two expanding signal pulses
		const double Period = 2.4;
		for (int32 Index = 0; Index < 2; ++Index)
		{
			const float Phase = static_cast<float>(PosMod(TimeSec + Index * Period / 2.0, Period) / Period);
			Ring(Out, Geo, Layer, Center, R + Phase * Spread, WithAlpha(Accent, (1.0f - Phase) * 0.7f * AccentAlpha), 2.0f * S);
		}

		if (bStar)
		{
			// The star is concave: Poly fans from the first point, so the hub must be the centre (not a star vertex).
			TArray<FVector2f> Star;
			Star.Add(Center);
			for (int32 Index = 0; Index <= 10; ++Index)
			{
				const double Radius = Index % 2 ? R * 0.27 : R * 0.68;
				Star.Add(PolarPoint(Center, Radius, -kPi / 2.0 + Index * kPi / 5.0 + RotRad * 0.5));
			}
			Poly(Out, Geo, Layer, Star, WithAlpha(Accent, 0.9f), false);
		}
	}

	void Wave(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos, const FVector2f& Size,
		const FLinearColor& LineColor, const FLinearColor& Accent, double TimeSec, float Amp, float Scale)
	{
		if (Size.X <= 0.0f || Size.Y <= 0.0f) return;
		// Evaluate in HTML design pixels, convert on output.
		const double S = FMath::Max(Scale, 0.01f);
		const double W = Size.X / S, H = Size.Y / S, Mid = H * 0.5, AmpD = Amp / S;
		auto ToLocal = [&Pos, S](double X, double Y) { return FVector2f(Pos.X + static_cast<float>(X * S), Pos.Y + static_cast<float>(Y * S)); };

		FTriBatch Batch(Geo);
		const FLinearColor Baseline = WithAlpha(LineColor, 0.22f);
		Batch.Rect(ToLocal(0.0, Mid - 0.5), FVector2f(Size.X, static_cast<float>(S)), Baseline);
		for (double X = 0.0; X <= W; X += 30.0) Batch.Rect(ToLocal(X - 0.5, Mid - 3.0), FVector2f(static_cast<float>(S), static_cast<float>(6.0 * S)), Baseline);

		const double BlipX = PosMod(TimeSec * 190.0, W + 240.0) - 120.0;
		auto Height = [&](double X, double T)
		{
			const double Bx = PosMod(T * 190.0, W + 240.0) - 120.0;
			const double D = (X - Bx) / 15.0;
			const double Value = Mid + AmpD * (FMath::Sin(X * 0.021 + T * 2.1) * 0.42 + FMath::Sin(X * 0.057 - T * 3.3) * 0.22 + FMath::Sin(X * 0.0063 + T * 0.7) * 0.18)
				- AmpD * 1.7 * FMath::Exp(-D * D) + AmpD * 1.1 * FMath::Exp(-((D - 1.8) * (D - 1.8)));
			return FMath::Clamp(Value, 2.0, H - 2.0);
		};

		if (BlipX >= 0.0 && BlipX <= W) Batch.Rect(ToLocal(BlipX - 1.0, 2.0), FVector2f(static_cast<float>(2.0 * S), static_cast<float>((H - 4.0) * S)), WithAlpha(Accent, 0.8f));
		Batch.Flush(Out, Layer);

		struct FStroke { double Lag; float Alpha; float Width; };
		static const FStroke Strokes[2] = { { 0.3, 0.25f, 1.0f }, { 0.0, 0.85f, 1.6f } };
		for (const FStroke& Stroke : Strokes)
		{
			TArray<FVector2f> Points;
			Points.Reserve(static_cast<int32>(W / 3.0) + 2);
			for (double X = 0.0; X <= W; X += 3.0) Points.Add(ToLocal(X, Height(X, TimeSec - Stroke.Lag)));
			Lines(Out, Geo, Layer, Points, WithAlpha(LineColor, Stroke.Alpha), Stroke.Width * static_cast<float>(S));
		}
	}

	void Particles(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& RegionPos,
		const FVector2f& RegionSize, int32 Count, const FLinearColor& Color, float Alpha, double TimeSec, float Scale)
	{
		if (Count <= 0 || RegionSize.X <= 0.0f || RegionSize.Y <= 0.0f) return;
		const double S = FMath::Max(Scale, 0.01f);
		const double RegionW = RegionSize.X / S, RegionH = RegionSize.Y / S;
		// Same Park-Miller sequence as the HTML (seed 7) so the layout matches; motion is the closed form of its integrator.
		uint64 Seed = 7;
		auto Random = [&Seed]()
		{
			Seed = (Seed * 16807ULL) % 2147483647ULL;
			return static_cast<double>(Seed) / 2147483647.0;
		};

		FTriBatch Batch(Geo);
		const double Period = RegionH + 20.0;
		for (int32 Index = 0; Index < Count; ++Index)
		{
			const double X0 = Random() * RegionW;
			const double Y0 = Random() * RegionH;
			const double Size = 1.5 + Random() * 3.2;
			const double Rise = 6.0 + Random() * 16.0;
			const double Phase = Random() * 6.28;
			const bool bCross = Random() < 0.18;

			const double Y = -10.0 + PosMod((Y0 + 10.0) - Rise * TimeSec, Period);
			const double X = X0 + 5.0 * (FMath::Cos(Phase) - FMath::Cos(TimeSec * 0.6 + Phase)) / 0.6;
			const float Opacity = Alpha * static_cast<float>(0.45 + 0.55 * FMath::Abs(FMath::Sin(TimeSec * 0.9 + Phase)));
			const FLinearColor Tint = WithAlpha(Color, Opacity);
			auto ToLocal = [&RegionPos, S](double LocalX, double LocalY) { return FVector2f(RegionPos.X + static_cast<float>(LocalX * S), RegionPos.Y + static_cast<float>(LocalY * S)); };
			if (bCross)
			{
				Batch.Rect(ToLocal(X - 5.0, Y - 0.7), FVector2f(static_cast<float>(10.0 * S), static_cast<float>(1.4 * S)), Tint);
				Batch.Rect(ToLocal(X - 0.7, Y - 5.0), FVector2f(static_cast<float>(1.4 * S), static_cast<float>(10.0 * S)), Tint);
			}
			else
			{
				Batch.Rect(ToLocal(X, Y), FVector2f(static_cast<float>(Size * S), static_cast<float>(Size * S)), Tint);
			}
		}
		Batch.Flush(Out, Layer);
	}

	void SegBar(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos, const FVector2f& Size,
		int32 Count, float Fraction, const FLinearColor& OnColor, const FLinearColor& OffColor, float Border, float Gap,
		const FLinearColor& OffBorderColor, double TimeSec, const FLinearColor& LeadColor)
	{
		if (Count <= 0 || Size.X <= 0.0f || Size.Y <= 0.0f) return;
		const float CellW = (Size.X - Gap * (Count - 1)) / Count;
		if (CellW <= 0.0f) return;
		const float Clamped = Saturate(Fraction);
		const int32 Lit = FMath::Min(Count, FMath::FloorToInt(Clamped * Count + 0.0001f));
		const bool bLeadVisible = TimeSec >= 0.0 && PosMod(TimeSec, 0.16) < 0.08;

		FTriBatch Batch(Geo);
		for (int32 Index = 0; Index < Count; ++Index)
		{
			const FVector2f CellPos(Pos.X + Index * (CellW + Gap), Pos.Y);
			const FVector2f CellSize(CellW, Size.Y);
			if (Index < Lit)
			{
				Batch.Rect(CellPos, CellSize, OnColor);
			}
			else if (Index == Lit && Clamped < 1.0f && TimeSec >= 0.0)
			{
				if (bLeadVisible) Batch.Rect(CellPos, CellSize, LeadColor);
			}
			else
			{
				Batch.Rect(CellPos, CellSize, OffColor);
				Batch.FrameRect(CellPos, CellSize, Border, OffBorderColor);
			}
		}
		Batch.Flush(Out, Layer);
	}

	void Ruler(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos, float Width,
		const FLinearColor& Color, float Scale)
	{
		if (Width <= 0.0f) return;
		const float S = FMath::Max(Scale, 0.01f);
		FTriBatch Batch(Geo);
		Batch.Rect(FVector2f(Pos.X, Pos.Y + 14.0f * S), FVector2f(Width, 2.0f * S), Color);
		const float Right = Pos.X + Width;
		for (int32 Index = 0;; ++Index)
		{
			const float X = Pos.X + Index * 20.0f * S;
			if (X >= Right) break;
			const bool bLong = Index % 5 == 0;
			const float Height = (bLong ? 15.0f : 7.0f) * S;
			Batch.Rect(FVector2f(X, Pos.Y + 16.0f * S - Height), FVector2f(FMath::Min(2.0f * S, Right - X), Height), Color);
		}
		Batch.Flush(Out, Layer);
	}

	void Pips(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos, int32 Count,
		int32 Filled, const FLinearColor& OnColor, const FLinearColor& OffColor, const FVector2f& PipSize, float Border, float Gap)
	{
		if (Count <= 0) return;
		FTriBatch Batch(Geo);
		for (int32 Index = 0; Index < Count; ++Index)
		{
			const FVector2f PipPos(Pos.X + Index * (PipSize.X + Gap), Pos.Y);
			if (Index < Filled) Batch.Rect(PipPos, PipSize, OnColor);
			else Batch.FrameRect(PipPos, PipSize, Border, OffColor);
		}
		Batch.Flush(Out, Layer);
	}

	void Stamp(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, ETex Which, const FVector2f& Center,
		const FVector2f& Size, const FLinearColor& Tint, float RotationDeg, float ElapsedSec)
	{
		if (ElapsedSec < 0.0f) return;
		const float T = Saturate(ElapsedSec / StampDurationSec);
		float Scale, Opacity = 1.0f;
		if (T < 0.45f)
		{
			const float E = Ease::CubicBezier(0.55f, 0.0f, 1.0f, 0.45f, T / 0.45f);
			Scale = FMath::Lerp(2.2f, 0.95f, E);
			Opacity = E;
		}
		else if (T < 0.68f)
		{
			Scale = FMath::Lerp(0.95f, 1.025f, Ease::CubicBezier(0.3f, 0.0f, 0.4f, 1.0f, (T - 0.45f) / 0.23f));
		}
		else
		{
			Scale = FMath::Lerp(1.025f, 1.0f, Ease::CubicBezier(0.25f, 0.1f, 0.25f, 1.0f, (T - 0.68f) / 0.32f));
		}
		FLinearColor Faded = Tint;
		Faded.A *= Opacity;
		Tex(Out, Geo, Layer, Which, Center - Size * 0.5f, Size, Faded, RotationDeg, Scale);
	}

	// ------------------------------------------------------------------ clipping
	void PushClipQuad(FSlateWindowElementList& Out, const FGeometry& Geo, const FVector2f& TL, const FVector2f& TR,
		const FVector2f& BL, const FVector2f& BR)
	{
		const FSlateRenderTransform& Transform = Geo.GetAccumulatedRenderTransform();
		Out.PushClip(FSlateClippingZone(Transform.TransformPoint(TL), Transform.TransformPoint(TR),
			Transform.TransformPoint(BL), Transform.TransformPoint(BR)));
	}

	void PushClipRect(FSlateWindowElementList& Out, const FGeometry& Geo, const FVector2f& Pos, const FVector2f& Size)
	{
		PushClipQuad(Out, Geo, Pos, FVector2f(Pos.X + Size.X, Pos.Y), FVector2f(Pos.X, Pos.Y + Size.Y), Pos + Size);
	}

	void PopClip(FSlateWindowElementList& Out)
	{
		Out.PopClip();
	}

	// ------------------------------------------------------------------ components
	void PaperPanel(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos, const FVector2f& Size,
		bool bShadow, float Scale, bool bGrain)
	{
		const float S = FMath::Max(Scale, 0.01f);
		const float Cut = 18.0f * S, Border = 3.0f * S;
		if (bShadow) CutBox(Out, Geo, Layer, Pos + FVector2f(8.0f * S, 8.0f * S), Size, Ink, Cut, ECorner::TL);
		CutBox(Out, Geo, Layer, Pos, Size, PaperL, Cut, ECorner::TL, Border, Ink);
		if (bGrain && HasTex(ETex::Grain))
		{
			const float InnerCut = FMath::Max(0.0f, Cut - 0.586f * Border);
			TiledCutOut(Out, Geo, Layer + 1, ETex::Grain, Pos + FVector2f(Border, Border), Size - FVector2f(2.0f * Border, 2.0f * Border),
				FLinearColor(1.0f, 1.0f, 1.0f, 0.6f), S, InnerCut, ECorner::TL);
		}
	}

	void InkPanel(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos, const FVector2f& Size,
		float Scale)
	{
		CutBox(Out, Geo, Layer, Pos, Size, InkA(0.94f), 18.0f * FMath::Max(Scale, 0.01f), ECorner::TL);
	}

	void PanelHeader(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos, float Width,
		const FString& Title, const FString& RuTag, float Scale, bool bCutTopLeft)
	{
		const float S = FMath::Max(Scale, 0.01f);
		const float Height = 46.0f * S;
		CutBox(Out, Geo, Layer, Pos, FVector2f(Width, Height), Ink, bCutTopLeft ? (18.0f - 0.586f * 3.0f) * S : 0.0f, ECorner::TL);
		const FSlateFontInfo TitleFont = Font(EFontRole::SansBlack, Pt(20.0f, S), 0.12f);
		const FVector2f TitleSize = TextSize(Title, TitleFont);
		const float TextX = Pos.X + 28.0f * S;
		const float CenterY = Pos.Y + Height * 0.5f;
		Text(Out, Geo, Layer + 1, Title, TitleFont, FVector2f(TextX, CenterY), PaperL, 0.0f, FVector2f(0.0f, 0.5f));
		if (!RuTag.IsEmpty())
		{
			Text(Out, Geo, Layer + 1, RuTag, Font(EFontRole::Russo, Pt(14.0f, S), 0.18f),
				FVector2f(TextX + TitleSize.X + 14.0f * S, CenterY), RedL, 0.0f, FVector2f(0.0f, 0.5f));
		}
	}

	namespace
	{
		enum class EButtonStyle : uint8 { Primary, Secondary, Ghost };

		void DrawButton(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, EButtonStyle Style, const FVector2f& Pos,
			const FVector2f& Size, const FString& Label, const FString& RuLabel, float HoverT, bool bEnabled,
			const FLinearColor& Tone, const FButtonLook& Look)
		{
			if (Size.X <= 0.0f || Size.Y <= 0.0f) return;
			const float S = FMath::Max(Look.Scale, 0.01f);
			const float CutPx = Look.CutPx >= 0.0f ? Look.CutPx : (Style == EButtonStyle::Ghost ? 0.0f : 22.0f);
			const float Cut = CutPx * S;
			const ECorner Corner = Cut > 0.0f ? ECorner::BR : ECorner::None;
			const float Hover = bEnabled ? Saturate(HoverT) : 0.0f;
			const float WipeX = Pos.X + Size.X * Ease::CssOut(Hover);
			const float HeightDesign = Size.Y / S;

			FLinearColor LabelColor = PaperL;
			if (!bEnabled)
			{
				// Disabled: PaperDD plate with an ink-55 inset border and ink hatching; the label stays full ink (CSS .btn.off .b-tx).
				CutBox(Out, Geo, Layer, Pos, Size, PaperDD, Cut, Corner, 3.0f * S, InkA(0.55f));
				TiledCutOut(Out, Geo, Layer + 1, ETex::Hatch, Pos + FVector2f(3.0f * S, 3.0f * S), Size - FVector2f(6.0f * S, 6.0f * S),
					InkA(0.12f), S, FMath::Max(0.0f, Cut - 1.8f * S), Corner == ECorner::BR ? ECorner::BR : ECorner::None);
				LabelColor = Ink;
			}
			else if (Style == EButtonStyle::Ghost)
			{
				if (Hover > 0.0f)
				{
					const float Edge = 2.0f * S;
					TArray<FVector2f> Inner, Wipe;
					BuildCutPoints(Pos + FVector2f(Edge, Edge), Size - FVector2f(2.0f * Edge, 2.0f * Edge), FMath::Max(0.0f, Cut - 0.586f * Edge), Corner, Inner);
					ClipPolyMaxX(Inner, WipeX, Wipe);
					Poly(Out, Geo, Layer, Wipe, Red, false);
				}
				CutBox(Out, Geo, Layer, Pos, Size, FLinearColor(0.0f, 0.0f, 0.0f, 0.0f), Cut, Corner, 2.0f * S, Tone);
				LabelColor = Tone;
			}
			else
			{
				CutBox(Out, Geo, Layer, Pos, Size, Style == EButtonStyle::Primary ? Red : Ink, Cut, Corner);
				if (Hover > 0.0f)
				{
					TArray<FVector2f> Full, Wipe;
					BuildCutPoints(Pos, Size, Cut, Corner, Full);
					ClipPolyMaxX(Full, WipeX, Wipe);
					Poly(Out, Geo, Layer, Wipe, Style == EButtonStyle::Primary ? Ink : Red, true);
				}
				if (Look.ScanT >= 0.0f)
				{
					// Busy scan: a 160 px block of thin PaperL bars sweeping across, clipped to the button shape.
					FTriBatch Batch(Geo);
					const float Travel = -170.0f * S + (Size.X + 190.0f * S) * Ease::CssInOut(Saturate(Look.ScanT));
					for (float Bar = 0.0f; Bar < 160.0f; Bar += 9.0f)
					{
						const float X0 = Pos.X + Travel + (Bar + 6.0f) * S;
						const float X1 = X0 + 3.0f * S;
						const float ClipX0 = FMath::Max(X0, Pos.X), ClipX1 = FMath::Min(X1, Pos.X + Size.X);
						if (ClipX1 <= ClipX0) continue;
						const float CutDrop = Cut > 0.0f ? FMath::Max(0.0f, ClipX1 - (Pos.X + Size.X - Cut)) : 0.0f;
						Batch.Rect(FVector2f(ClipX0, Pos.Y), FVector2f(ClipX1 - ClipX0, FMath::Max(0.0f, Size.Y - CutDrop)), PaperLA(0.4f));
					}
					Batch.Flush(Out, Layer + 1);
				}
			}

			// Labels
			const bool bStacked = Style == EButtonStyle::Ghost;
			const float LabelPx = Look.LabelPx > 0.0f ? Look.LabelPx : FMath::Max(10.0f, HeightDesign * (bStacked ? 0.32f : 0.46f));
			// The caller's tracking is used as is, disabled or not: the prototype states the disabled spacing explicitly (.btn.off b .14em).
			const float Tracking = Look.TrackingEm;
			const FSlateFontInfo LabelFont = Font(EFontRole::SansBlack, Pt(LabelPx, S), Tracking);
			const float RuPx = Look.RuPx > 0.0f ? Look.RuPx : LabelPx * (bStacked ? 0.58f : 0.54f);
			const float RuTracking = Look.RuTrackingEm >= 0.0f ? Look.RuTrackingEm : (bStacked ? 0.16f : 0.14f);
			const FSlateFontInfo RuFont = Font(Look.RuRole, Pt(RuPx, S), RuTracking);
			const FLinearColor RuColor = WithAlpha(LabelColor, LabelColor.A * (bStacked ? 0.85f : 0.92f));
			const FVector2f LabelSize = TextSize(Label, LabelFont);
			const FVector2f RuSize = RuLabel.IsEmpty() ? FVector2f::ZeroVector : TextSize(RuLabel, RuFont);
			const float CenterY = Pos.Y + Size.Y * 0.5f;

			if (bStacked)
			{
				const float Gap = 7.0f * S;
				const float Total = LabelSize.Y + (RuLabel.IsEmpty() ? 0.0f : Gap + RuSize.Y);
				const float CenterX = Pos.X + Size.X * 0.5f;
				const float Top = CenterY - Total * 0.5f;
				Text(Out, Geo, Layer + 2, Label, LabelFont, FVector2f(CenterX, Top), LabelColor, 0.0f, FVector2f(0.5f, 0.0f));
				Text(Out, Geo, Layer + 2, RuLabel, RuFont, FVector2f(CenterX, Top + LabelSize.Y + Gap), RuColor, 0.0f, FVector2f(0.5f, 0.0f));
			}
			else
			{
				const float Gap = RuLabel.IsEmpty() ? 0.0f : (Look.GapPx >= 0.0f ? Look.GapPx * S : Size.Y * 0.2f);
				const float Total = LabelSize.X + Gap + RuSize.X;
				const float Left = Look.LabelLeftPx >= 0.0f ? Look.LabelLeftPx * S : Size.Y * 0.426f;
				const float StartX = Look.bCenter ? Pos.X + (Size.X - Total) * 0.5f : Pos.X + Left;
				Text(Out, Geo, Layer + 2, Label, LabelFont, FVector2f(StartX, CenterY), LabelColor, 0.0f, FVector2f(0.0f, 0.5f));
				Text(Out, Geo, Layer + 2, RuLabel, RuFont, FVector2f(StartX + LabelSize.X + Gap, CenterY), RuColor, 0.0f, FVector2f(0.0f, 0.5f));
				if (!Look.Arrow.IsEmpty())
				{
					const float Slide = 14.0f * S * Ease::CssOut(Hover);
					Text(Out, Geo, Layer + 2, Look.Arrow, Font(EFontRole::SansBlack, Pt(LabelPx * 1.08f, S)),
						FVector2f(Pos.X + Size.X - Size.Y * 0.57f + Slide, CenterY), LabelColor, 0.0f, FVector2f(1.0f, 0.5f));
				}
			}
		}
	}

	void PrimaryButton(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos, const FVector2f& Size,
		const FString& Label, const FString& RuLabel, float HoverT, bool bEnabled, const FButtonLook& Look)
	{
		DrawButton(Out, Geo, Layer, EButtonStyle::Primary, Pos, Size, Label, RuLabel, HoverT, bEnabled, PaperL, Look);
	}

	void SecondaryButton(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos, const FVector2f& Size,
		const FString& Label, const FString& RuLabel, float HoverT, bool bEnabled, const FButtonLook& Look)
	{
		DrawButton(Out, Geo, Layer, EButtonStyle::Secondary, Pos, Size, Label, RuLabel, HoverT, bEnabled, PaperL, Look);
	}

	void GhostButton(FSlateWindowElementList& Out, const FGeometry& Geo, int32 Layer, const FVector2f& Pos, const FVector2f& Size,
		const FString& Label, const FString& RuLabel, float HoverT, bool bEnabled, const FLinearColor& Tone, const FButtonLook& Look)
	{
		DrawButton(Out, Geo, Layer, EButtonStyle::Ghost, Pos, Size, Label, RuLabel, HoverT, bEnabled, Tone, Look);
	}
}
