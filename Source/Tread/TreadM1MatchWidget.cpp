#include "TreadM1MatchWidget.h"

#include "Blueprint/WidgetTree.h"
#include "Components/Button.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "EngineUtils.h"
#include "Fonts/FontCache.h"
#include "Framework/Application/SlateApplication.h"
#include "Input/Reply.h"
#include "Misc/Parse.h"
#include "Rendering/SlateRenderer.h"
#include "Styling/CoreStyle.h"
#include "TreadDragController.h"
#include "TreadM1PlayerController.h"
#include "TreadM1MatchController.h"
#include "TreadM3BoardPresenter.h"
#include "TreadAudioDirector.h"
#include "Engine/Texture2D.h"
#include "Styling/SlateBrush.h"
#include "Kismet/GameplayStatics.h"

namespace
{
	using TreadUI::EFontRole;

	float ShortestSideScale(const FVector2D& Size)
	{
		// Geometry is already in UMG logical pixels: fit the reference once.
		return FMath::Max(0.01f, FMath::Min(Size.X / 1920.0f, Size.Y / 1080.0f));
	}

	/**
	 * Scale the HUD text is really rasterised at (the viewport DPI scaler times the widget transform), set once per NativePaint.
	 * Slate shapes glyphs at that scale with integer-pixel advances, so a measurement taken at scale 1 comes out several percent
	 * narrower than what is drawn and ellipsis / right alignment would be off.
	 */
	float GPaintFontScale = 1.0f;

	/** Text metrics in local px, taken from the same shaped glyph sequence the renderer draws. */
	struct FHudMetrics
	{
		float Width = 0.0f;
		float Height = 0.0f;
		/** Distance from the top of the line box to the baseline. */
		float BaselineY = 0.0f;
	};

	FHudMetrics MeasureHud(const FString& Value, const FSlateFontInfo& FontInfo)
	{
		FHudMetrics Metrics;
		if (FSlateApplication::IsInitialized())
		{
			if (FSlateRenderer* Renderer = FSlateApplication::Get().GetRenderer())
			{
				const float FontScale = FMath::Max(GPaintFontScale, 0.01f);
				const FShapedGlyphSequenceRef Shaped = Renderer->GetFontCache()->ShapeBidirectionalText(
					Value.IsEmpty() ? FString(TEXT(" ")) : Value, FontInfo, FontScale, TextBiDi::ETextDirection::LeftToRight, GetDefaultTextShapingMethod());
				Metrics.Width = Value.IsEmpty() ? 0.0f : static_cast<float>(Shaped->GetMeasuredWidth()) / FontScale;
				Metrics.Height = static_cast<float>(Shaped->GetMaxTextHeight()) / FontScale;
				// GetTextBaseline() is the (negative) descender, so the baseline sits that far above the bottom of the line box.
				Metrics.BaselineY = Metrics.Height + static_cast<float>(Shaped->GetTextBaseline()) / FontScale;
				if (Metrics.Height > 0.0f) return Metrics;
			}
		}
		// No renderer (-nullrhi) or fonts still loading: rough estimate.
		const FVector2f Estimate = TreadUI::TextSize(Value, FontInfo);
		Metrics.Width = Estimate.X;
		Metrics.Height = Estimate.Y;
		Metrics.BaselineY = Estimate.Y * 0.8f;
		return Metrics;
	}

	/** Width of a string in the unit the caller wraps / cuts in; lets the helpers below follow whatever DrawText really draws. */
	using FMeasureFn = TFunctionRef<float(const FString&)>;

	/** Value.Left(Count) plus the ellipsis. A space left dangling at the cut is dropped first so it never reads "word …". */
	FString CutWithEllipsis(const FString& Value, int32 Count)
	{
		FString Head = Value.Left(Count);
		Head.TrimEndInline();
		return Head + TEXT("…");
	}

	/** Value shortened with an ellipsis until Measure() of it fits MaxWidth. */
	FString EllipsizeWith(const FString& Value, FMeasureFn Measure, float MaxWidth)
	{
		if (Value.IsEmpty() || Measure(Value) <= MaxWidth) return Value;
		int32 Lo = 0, Hi = Value.Len();
		while (Lo < Hi)
		{
			const int32 Mid = (Lo + Hi + 1) / 2;
			if (Measure(CutWithEllipsis(Value, Mid)) <= MaxWidth) Lo = Mid; else Hi = Mid - 1;
		}
		return CutWithEllipsis(Value, Lo);
	}

	bool CharIn(TCHAR Character, const TCHAR* Set) { return Character != 0 && FCString::Strchr(Set, Character) != nullptr; }

	bool IsAsciiWordChar(TCHAR Character)
	{
		return (Character >= TEXT('0') && Character <= TEXT('9')) || (Character >= TEXT('a') && Character <= TEXT('z'))
			|| (Character >= TEXT('A') && Character <= TEXT('Z')) || Character == TEXT('.') || Character == TEXT('_');
	}

	/** Closing punctuation and trailing marks that must not start a line. */
	bool IsLineStartForbidden(TCHAR Character) { return CharIn(Character, TEXT("，。、：；！？）】」』》〉］｝”’％%…‥·,.:;!?)]}")); }

	/**
	 * Line-break rules (kinsoku): a line must not start with closing punctuation or a trailing mark ("：", "、", "%", "…"), must not end
	 * on an opening bracket, and a doubled dash / ellipsis or a Latin word / number ("25" "%") is never split.
	 */
	bool CanBreakBefore(const FString& Text, int32 Index)
	{
		if (Index <= 0 || Index >= Text.Len()) return true;
		const TCHAR Prev = Text[Index - 1];
		const TCHAR Next = Text[Index];
		if (IsLineStartForbidden(Next)) return false;
		if (CharIn(Prev, TEXT("（【「『《〈［｛“‘([{"))) return false;
		if (Prev == Next && (Prev == TEXT('—') || Prev == TEXT('…'))) return false;
		if (IsAsciiWordChar(Prev) && IsAsciiWordChar(Next)) return false;
		return true;
	}

	/**
	 * Breaks text into at most MaxLines lines whose Measure() fits MaxWidth; the last line gets an ellipsis if text remains.
	 * A break that would start a line with closing punctuation is fixed in one of two ways. With HangWidth > 0 the mark is pulled back
	 * onto the line it closes ("hanging punctuation") as long as the line then stays within MaxWidth + HangWidth; the caller must leave
	 * that much room. Otherwise the break moves back (up to 6 characters) so the character before the mark goes down with it, which only
	 * shortens the line. If no legal break is that close the plain hard cut stays.
	 */
	TArray<FString> WrapWith(const FString& Value, FMeasureFn Measure, float MaxWidth, int32 MaxLines, float HangWidth = 0.0f)
	{
		TArray<FString> Lines;
		FString Rest = Value.Replace(TEXT("\n"), TEXT(" "));
		while (!Rest.IsEmpty() && Lines.Num() < MaxLines)
		{
			if (Measure(Rest) <= MaxWidth)
			{
				Lines.Add(Rest);
				Rest.Reset();
				break;
			}
			// Longest prefix that fits (CJK text has no spaces to break on); always at least one character.
			int32 Lo = 1, Hi = Rest.Len();
			while (Lo < Hi)
			{
				const int32 Mid = (Lo + Hi + 1) / 2;
				if (Measure(Rest.Left(Mid)) <= MaxWidth) Lo = Mid; else Hi = Mid - 1;
			}
			int32 Cut = Lo;
			for (int32 Hang = 0; HangWidth > 0.0f && Hang < 2 && Cut < Rest.Len() && IsLineStartForbidden(Rest[Cut])
				&& Measure(Rest.Left(Cut + 1)) <= MaxWidth + HangWidth; ++Hang) ++Cut;
			const int32 Hung = Cut;
			for (int32 Back = 0; Cut > 1 && Back < 6 && !CanBreakBefore(Rest, Cut); ++Back) --Cut;
			if (!CanBreakBefore(Rest, Cut)) Cut = Hung;
			Lines.Add(Rest.Left(Cut));
			Rest = Rest.Mid(Cut);
		}
		if (!Rest.IsEmpty() && Lines.Num() > 0) Lines.Last() = EllipsizeWith(Lines.Last() + Rest, Measure, MaxWidth);
		return Lines;
	}

	/** Wrap for plain single-face text: MaxWidth in local px, measured from the shaped glyphs of FontInfo. */
	TArray<FString> WrapToWidth(const FString& Value, const FSlateFontInfo& FontInfo, float MaxWidth, int32 MaxLines)
	{
		return WrapWith(Value, [&FontInfo](const FString& Text) { return MeasureHud(Text, FontInfo).Width; }, MaxWidth, MaxLines);
	}

	FString JoinOr(const TArray<FString>& Values, const TCHAR* Separator, const TCHAR* Empty)
	{
		return Values.Num() > 0 ? FString::Join(Values, Separator) : FString(Empty);
	}

	FString EnumTail(const FString& Value)
	{
		int32 Index = INDEX_NONE;
		if (Value.FindLastChar(TEXT(':'), Index)) return Value.Mid(Index + 1);
		return Value;
	}

	/** One styled piece of a text line; Size is in design points (scaled by the caller). */
	struct FHudRun
	{
		FString Text;
		EFontRole Role = EFontRole::SansMedium;
		FLinearColor Color = FLinearColor::White;
		float Size = 16.0f;
		/** Optical size factor of this run (digits in a Latin face next to CJK glyphs); line layout still uses Size. */
		float SizeMul = 1.0f;
		/** Extra advance after this run in design px (optical gap between a numeral run's "%" and the CJK glyph that follows). */
		float PadAfter = 0.0f;
	};

	/** HUD tier ink: the library's tier II is green, which the HUD no longer uses, so it prints in a warm brown here. */
	FLinearColor HudTierColor(const FString& Roman)
	{
		if (Roman == TEXT("II")) return FLinearColor::FromSRGBColor(FColor(0x7A, 0x4B, 0x2A));
		return TreadUI::TierColor(Roman);
	}

	bool IsAsciiDigit(TCHAR Character) { return Character >= TEXT('0') && Character <= TEXT('9'); }

	/** Splits Value into base-face runs and numeral-face runs (digits, an inner '.', a trailing '%'). */
	void SplitNumberRuns(const FString& Value, const FHudRun& Base, EFontRole NumberRole, float NumberMul, TArray<FHudRun>& OutRuns)
	{
		OutRuns.Reset();
		FString Plain;
		const int32 Length = Value.Len();
		int32 Index = 0;
		const auto FlushPlain = [&]()
		{
			if (Plain.IsEmpty()) return;
			FHudRun Run = Base;
			Run.Text = Plain;
			OutRuns.Add(MoveTemp(Run));
			Plain.Reset();
		};
		while (Index < Length)
		{
			if (!IsAsciiDigit(Value[Index]))
			{
				Plain.AppendChar(Value[Index]);
				++Index;
				continue;
			}
			int32 End = Index + 1;
			while (End < Length && (IsAsciiDigit(Value[End]) || (Value[End] == TEXT('.') && End + 1 < Length && IsAsciiDigit(Value[End + 1])))) ++End;
			if (End < Length && Value[End] == TEXT('%')) ++End;
			FlushPlain();
			FHudRun Run = Base;
			Run.Text = Value.Mid(Index, End - Index);
			Run.Role = NumberRole;
			Run.SizeMul = NumberMul;
			// The mono face draws "%" edge to edge (ink spills ~0.015 em past its 0.6 em advance) while an ideograph has only ~0.08 em of
			// side bearing, so "25%的" fuses into one blob at HUD sizes. CSS adds a 1/8 em gap between numerals and ideographs; do the same.
			if (Run.Text.EndsWith(TEXT("%")) && End < Length && Value[End] >= 0x2E80)
				Run.PadAfter = 0.12f * Run.Size * Run.SizeMul * (96.0f / 72.0f);
			OutRuns.Add(MoveTemp(Run));
			Index = End;
		}
		FlushPlain();
	}

	/** Slate font of one run at the given layout scale (the optical size factor applies on top of the design size). */
	FSlateFontInfo RunFont(const FHudRun& Run, float Scale)
	{
		return TreadUI::Font(Run.Role, Run.Size * Run.SizeMul * Scale);
	}

	/** Numeral face DrawText switches digits to: Stencil under the display faces, MonoBold otherwise. */
	EFontRole HudNumberRole(EFontRole Role)
	{
		return (Role == EFontRole::SansBlack || Role == EFontRole::Stencil) ? EFontRole::Stencil : EFontRole::MonoBold;
	}

	/**
	 * The numeral faces have the same cap height as the sans (0.73 em, stencil 0.80 em) but CJK ideographs fill ~0.94 em, so digits
	 * between Chinese characters read like superscripts. Optically enlarge them (cap height ~0.84 em) when the text contains CJK;
	 * digits inside Latin text stay at 1.0 so they match the letters around them.
	 */
	float HudNumberMul(const FString& Value, EFontRole NumberRole)
	{
		bool bHasCjk = false;
		for (const TCHAR Character : Value) if (Character >= 0x2E80) { bHasCjk = true; break; }
		return !bHasCjk ? 1.0f : (NumberRole == EFontRole::Stencil ? 1.05f : 1.15f);
	}

	/** The runs DrawText lays out for Text: a single base run, or base + numeral runs when bNumbers is set. */
	void BuildHudRuns(const FString& Text, const FHudRun& Base, bool bNumbers, EFontRole NumberRole, float NumberMul, TArray<FHudRun>& OutRuns)
	{
		if (bNumbers)
		{
			SplitNumberRuns(Text, Base, NumberRole, NumberMul, OutRuns);
			return;
		}
		OutRuns.Reset();
		FHudRun Run = Base;
		Run.Text = Text;
		OutRuns.Add(MoveTemp(Run));
	}

	/** Width in local px of the runs laid end to end. */
	float MeasureRuns(const TArray<FHudRun>& Runs, float Scale)
	{
		float Total = 0.0f;
		for (const FHudRun& Run : Runs)
		{
			if (!Run.Text.IsEmpty()) Total += MeasureHud(Run.Text, RunFont(Run, Scale)).Width + Run.PadAfter * Scale;
		}
		return Total;
	}

	/**
	 * Draws the runs left to right on one shared baseline. The largest run (ties: the longest text) keeps the nominal
	 * placement, vertically centred on its own line box; every other run is dropped or lifted so its baseline lands on
	 * the same line, because faces with different ascent would otherwise float up or down (digits looked like superscripts).
	 * Position is local px; AlignX 0 / 0.5 / 1 = left / centre / right of Position.X. Returns the total width in local px.
	 */
	float DrawRuns(FSlateWindowElementList& Out, const FGeometry& Geometry, int32 Layer, float Scale,
		const FVector2D& Position, const TArray<FHudRun>& Runs, float AlignX, bool bShadow)
	{
		if (Runs.IsEmpty()) return 0.0f;
		float MaxSize = 0.0f;
		float Total = 0.0f;
		int32 RefIndex = INDEX_NONE;
		TArray<FSlateFontInfo, TInlineAllocator<4>> Fonts;
		TArray<FHudMetrics, TInlineAllocator<4>> Metrics;
		for (int32 Index = 0; Index < Runs.Num(); ++Index)
		{
			const FHudRun& Run = Runs[Index];
			MaxSize = FMath::Max(MaxSize, Run.Size);
			Fonts.Add(RunFont(Run, Scale));
			Metrics.Add(MeasureHud(Run.Text, Fonts.Last()));
			Total += Metrics.Last().Width + Run.PadAfter * Scale;
			if (Run.Text.IsEmpty()) continue;
			if (RefIndex == INDEX_NONE || Run.Size > Runs[RefIndex].Size || (Run.Size == Runs[RefIndex].Size && Run.Text.Len() > Runs[RefIndex].Text.Len())) RefIndex = Index;
		}
		if (RefIndex == INDEX_NONE) return 0.0f;
		float X = static_cast<float>(Position.X) - Total * AlignX;
		// Slate points are 96/72 px; a Roboto-style line box is ~1.17 em, so its centre sits ~0.78 pt-size below the top.
		const float CenterY = static_cast<float>(Position.Y) + MaxSize * Scale * 0.78f;
		const float BaselineY = CenterY - Metrics[RefIndex].Height * 0.5f + Metrics[RefIndex].BaselineY;
		const FVector2f ShadowOffset(2.0f * Scale, 2.0f * Scale);
		for (int32 Index = 0; Index < Runs.Num(); ++Index)
		{
			const FHudRun& Run = Runs[Index];
			if (!Run.Text.IsEmpty() && Run.Color.A > 0.0f)
			{
				// Top-left anchored: the line box top is chosen so this run's baseline meets the shared one.
				const FVector2f At(X, BaselineY - Metrics[Index].BaselineY);
				if (bShadow)
					TreadUI::TextShadow(Out, Geometry, Layer, Run.Text, Fonts[Index], At, Run.Color, ShadowOffset, TreadUI::InkA(Run.Color.A), 0.0f, FVector2f::ZeroVector);
				else
					TreadUI::Text(Out, Geometry, Layer, Run.Text, Fonts[Index], At, Run.Color, 0.0f, FVector2f::ZeroVector);
			}
			X += Metrics[Index].Width + Run.PadAfter * Scale;
		}
		return Total;
	}
}

UTreadM1MatchWidget::UTreadM1MatchWidget(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	SetIsFocusable(false);
}

ATreadM1MatchController* UTreadM1MatchWidget::FindMatchController() const
{
	if (!GetWorld()) return nullptr;
	for (TActorIterator<ATreadM1MatchController> It(GetWorld()); It; ++It) return *It;
	return nullptr;
}

TSharedRef<SWidget> UTreadM1MatchWidget::RebuildWidget()
{
	ShopAvatarButtons.Reset(); BPButtons.Reset(); ShopButtons.Reset(); RankButtons.Reset(); BenchButtons.Reset(); ItemButtons.Reset(); StageButtons.Reset();
	BuildInteractionLayer();
	return Super::RebuildWidget();
}

void UTreadM1MatchWidget::NativeConstruct()
{
	Super::NativeConstruct();
	// Fonts and textures of the paper / ink style (doc 157); loading now avoids a hitch on the first paint.
	TreadUI::Preload();
	Controller = FindMatchController();
	RequestPrefix = FGuid::NewGuid().ToString();
	FString Stage;
	if (FParse::Value(FCommandLine::Get(), TEXT("TreadM1Capture="), Stage)) CaptureStage = Stage.ToUpper();
	bScoutOpen = CaptureStage == TEXT("SCOUT");
	if (bScoutOpen) ScoutPlayerIndex = 1;
	FString M2Stage;
	if (FParse::Value(FCommandLine::Get(), TEXT("TreadM2Capture="), M2Stage) && M2Stage.ToUpper() == TEXT("SCOUT"))
	{
		// M2 evidence: the human's own read-only ScoutSnapshot with pact counts and stacks.
		bScoutOpen = true;
		ScoutPlayerIndex = 0;
	}
	SetVisibility(ESlateVisibility::SelfHitTestInvisible);
	if (Controller.IsValid())
	{
		Controller->OnStateChanged.AddDynamic(this, &UTreadM1MatchWidget::HandleStateChanged);
		Controller->OnPhaseChanged.AddDynamic(this, &UTreadM1MatchWidget::HandlePhaseChanged);
	}
	EnsureAudio();
}

bool UTreadM1MatchWidget::IsSlotHovered(const FString& Kind, int32 Index, const UButton* Button) const
{
	return (Button && Button->IsHovered()) || (ForcedTooltipKind == Kind && ForcedTooltipIndex == Index);
}

void UTreadM1MatchWidget::SetRosterPanelForTest(bool bOpen, int32 Page)
{
	bRosterOpen = bOpen;
	RosterPage = FMath::Max(0, Page);
	Invalidate(EInvalidateWidgetReason::Paint);
}

void UTreadM1MatchWidget::SetForcedTooltipForTest(const FString& Kind, int32 Index)
{
	ForcedTooltipKind = Kind;
	ForcedTooltipIndex = Kind.IsEmpty() ? INDEX_NONE : Index;
	Invalidate(EInvalidateWidgetReason::Paint);
}

bool UTreadM1MatchWidget::IsLongPress() const
{
	return FPlatformTime::Seconds() - PressStartSeconds >= LongPressSeconds;
}

void UTreadM1MatchWidget::OpenPortraitDetail(const FString& CharacterId)
{
	DetailCharacterId = CharacterId;
	Invalidate(EInvalidateWidgetReason::Paint);
}

void UTreadM1MatchWidget::ClosePortraitDetail()
{
	DetailCharacterId.Empty();
	Invalidate(EInvalidateWidgetReason::Paint);
}

void UTreadM1MatchWidget::SetPanelCollapsedForTest(const FString& Panel, bool bCollapsed)
{
	const FString Key = Panel.ToLower();
	if (Key == TEXT("battle")) bBattlePanelCollapsed = bCollapsed;
	else if (Key == TEXT("feed")) bFeedPanelCollapsed = bCollapsed;
	else if (Key == TEXT("pact")) bPactPanelCollapsed = bCollapsed;
	else if (Key == TEXT("squad")) bSquadPanelCollapsed = bCollapsed;
	Invalidate(EInvalidateWidgetReason::Paint);
}

void UTreadM1MatchWidget::SetPortraitDetailForTest(const FString& CharacterId)
{
	if (CharacterId.IsEmpty()) ClosePortraitDetail();
	else OpenPortraitDetail(CharacterId);
}

void UTreadM1MatchWidget::EnsureAudio()
{
	if (Audio || !Controller.IsValid()) return;
	Audio = NewObject<UTreadAudioDirector>(this);
	Audio->Initialize(Controller.Get());
}

void UTreadM1MatchWidget::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
	Super::NativeTick(MyGeometry, InDeltaTime);
	if (!Controller.IsValid()) Controller = FindMatchController();
	LayoutSize = MyGeometry.GetLocalSize();
	LayoutScale = ShortestSideScale(LayoutSize);
	RefreshInteraction(LayoutSize);
	if (APlayerController* PC = GetOwningPlayer())
	{
		if (UTreadDragController* Drag = PC->FindComponentByClass<UTreadDragController>())
		{
			Drag->SetInteractionGeometry(MyGeometry, LayoutScale);
			Drag->SetInteractionBlocked(bScoutOpen || bRosterOpen);
		}
	}
}

UButton* UTreadM1MatchWidget::MakeInvisibleButton(const FString& Name)
{
	UButton* Button = WidgetTree->ConstructWidget<UButton>(UButton::StaticClass(), FName(*Name));
	FButtonStyle Style;
	Style.SetNormal(FSlateNoResource());
	Style.SetHovered(FSlateNoResource());
	Style.SetPressed(FSlateNoResource());
	Style.SetDisabled(FSlateNoResource());
	Style.SetNormalPadding(FMargin(0));
	Style.SetPressedPadding(FMargin(0));
	Button->SetStyle(Style);
	Button->SetBackgroundColor(FLinearColor::Transparent);
	Button->OnClicked.AddDynamic(this, &UTreadM1MatchWidget::HandleAnyClick);
	Button->OnPressed.AddDynamic(this, &UTreadM1MatchWidget::HandleAnyPressed);
	Button->OnReleased.AddDynamic(this, &UTreadM1MatchWidget::HandleAnyReleased);
	InteractionCanvas->AddChild(Button);
	return Button;
}

void UTreadM1MatchWidget::BuildInteractionLayer()
{
	InteractionCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("M1InteractionCanvas"));
	WidgetTree->RootWidget = InteractionCanvas;
	InteractionCanvas->SetVisibility(ESlateVisibility::SelfHitTestInvisible);
	for (int32 Index = 0; Index < 40; ++Index)
	{
		BPButtons.Add(MakeInvisibleButton(FString::Printf(TEXT("BPCard_%02d"), Index)));
	}
	for (int32 Index = 0; Index < 5; ++Index)
	{
		ShopButtons.Add(MakeInvisibleButton(FString::Printf(TEXT("ShopCard_%02d"), Index)));
		ShopAvatarButtons.Add(MakeInvisibleButton(FString::Printf(TEXT("ShopAvatar_%02d"), Index)));
	}
	for (int32 Index = 0; Index < 4; ++Index)
	{
		RankButtons.Add(MakeInvisibleButton(FString::Printf(TEXT("Rank_%02d"), Index)));
	}
	// document/176: three hit boxes for the free reward choices.
	for (int32 Index = 0; Index < 3; ++Index)
	{
		RewardButtons.Add(MakeInvisibleButton(FString::Printf(TEXT("Reward_%02d"), Index)));
	}
	for (int32 Index = 0; Index < 8; ++Index)
	{
		BenchButtons.Add(MakeInvisibleButton(FString::Printf(TEXT("Bench_%02d"), Index)));
	}
	ConfirmButton = MakeInvisibleButton(TEXT("BPConfirm"));
	DeployButton = MakeInvisibleButton(TEXT("Deploy"));
	ScoutCloseButton = MakeInvisibleButton(TEXT("ScoutClose"));
	ContinueButton = MakeInvisibleButton(TEXT("Continue"));
	StartButton = MakeInvisibleButton(TEXT("StartParis"));
	RefreshButton = MakeInvisibleButton(TEXT("RefreshShop"));
	LockButton = MakeInvisibleButton(TEXT("LockShop"));
	ExperienceButton = MakeInvisibleButton(TEXT("BuyExperience"));
	BoardButton = MakeInvisibleButton(TEXT("BoardInput"));
	for (int32 Index = 0; Index < InventorySlots; ++Index)
	{
		ItemButtons.Add(MakeInvisibleButton(FString::Printf(TEXT("Item_%02d"), Index)));
	}
	for (int32 Index = 0; Index < 16; ++Index)
	{
		StageButtons.Add(MakeInvisibleButton(FString::Printf(TEXT("Stage_%02d"), Index + 1)));
	}
	FreeMatchButton = MakeInvisibleButton(TEXT("FreeMatch"));
	RosterButton = MakeInvisibleButton(TEXT("RosterOpen"));
	AudienceButton = MakeInvisibleButton(TEXT("AudienceCamera"));
	RosterPrevButton = MakeInvisibleButton(TEXT("RosterPrev"));
	RosterNextButton = MakeInvisibleButton(TEXT("RosterNext"));
	RosterCloseButton = MakeInvisibleButton(TEXT("RosterClose"));
	DetailButton = MakeInvisibleButton(TEXT("PortraitDetail"));
	BattleZoomButton = MakeInvisibleButton(TEXT("BattleZoom"));
	FeedZoomButton = MakeInvisibleButton(TEXT("FeedZoom"));
	PactZoomButton = MakeInvisibleButton(TEXT("PactZoom"));
	SquadZoomButton = MakeInvisibleButton(TEXT("SquadZoom"));
}

void UTreadM1MatchWidget::SetButtonRect(UButton* Button, const FVector2D& Position, const FVector2D& Size, int32 ZOrder) const
{
	if (!Button) return;
	if (UCanvasPanelSlot* CanvasSlot = Cast<UCanvasPanelSlot>(Button->Slot))
	{
		CanvasSlot->SetPosition(Position);
		CanvasSlot->SetSize(Size);
		CanvasSlot->SetZOrder(ZOrder);
	}
}

void UTreadM1MatchWidget::RefreshInteraction(const FVector2D& LocalSize)
{
	if (!InteractionCanvas) return;
	const bool bBP = Controller.IsValid() && Controller->MatchState.Phase == ETreadM1Phase::PreMatchBP;
	const bool bPrep = Controller.IsValid() && Controller->MatchState.Phase == ETreadM1Phase::Preparation;
	const bool bBattle = Controller.IsValid() && Controller->MatchState.Phase == ETreadM1Phase::Battle;
	const bool bResult = Controller.IsValid() && (Controller->MatchState.Phase == ETreadM1Phase::Settlement || Controller->MatchState.Phase == ETreadM1Phase::GameOver);
	// The scout view and the roster panel are modal: nothing underneath takes clicks or drags.
	const bool bModal = bScoutOpen || bRosterOpen;
	for (int32 Index = 0; Index < BPButtons.Num(); ++Index)
	{
		const int32 Col = Index % 8; const int32 Row = Index / 8;
		SetButtonRect(BPButtons[Index], RefVec(16 + Col * 158, 208 + Row * 146), RefVec(148, 138), 51);
		BPButtons[Index]->SetVisibility(bBP ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
		BPButtons[Index]->SetIsEnabled(bBP && Index < Controller->MatchState.BP.AvailableStrategyIds.Num());
	}
	for (int32 Index = 0; Index < ShopButtons.Num(); ++Index)
	{
		SetButtonRect(ShopButtons[Index], RefVec(1604, 178 + Index * 74), RefVec(288, 68), 22);
		ShopButtons[Index]->SetVisibility(bPrep && !bModal ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
		ShopButtons[Index]->SetIsEnabled(bPrep && Controller.IsValid() && Controller->MatchState.Players.Num() > 0 && Controller->MatchState.Players[0].Shop.Slots.IsValidIndex(Index));
		// The avatar square of the card: a click opens the PNG detail, the rest of the card still buys.
		const bool bUnsold = Controller.IsValid() && Controller->MatchState.Players.Num() > 0
			&& Controller->MatchState.Players[0].Shop.Slots.IsValidIndex(Index) && !Controller->MatchState.Players[0].Shop.Slots[Index].bIsSold;
		SetButtonRect(ShopAvatarButtons[Index], RefVec(1606, 181 + Index * 74), RefVec(62, 62), 23);
		ShopAvatarButtons[Index]->SetVisibility(bPrep && !bModal && bUnsold ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
	}
	// document/176: the free three-choice strip sits between the header and the board.
	const bool bRewardPlayer = Controller.IsValid() && Controller->MatchState.Players.Num() > 0;
	const FTreadM1PlayerState* RewardP = bRewardPlayer ? &Controller->MatchState.Players[0] : nullptr;
	const bool bRewardOpen = bPrep && !bModal && RewardP && RewardP->RewardOffer.Num() > 0 && !RewardP->bRewardClaimed;
	for (int32 Index = 0; Index < RewardButtons.Num(); ++Index)
	{
		SetButtonRect(RewardButtons[Index], RefVec(622 + Index * 188, 126), RefVec(176, 78), 25);
		const bool bHasChoice = RewardP && RewardP->RewardOffer.IsValidIndex(Index);
		RewardButtons[Index]->SetVisibility(bRewardOpen && bHasChoice ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
	}
	// The detail image closes on a long press; it only exists while a detail is open.
	SetButtonRect(DetailButton, RefVec(726, 164), RefVec(468, 702), 90);
	DetailButton->SetVisibility(!DetailCharacterId.IsEmpty() ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
	for (int32 Index = 0; Index < RankButtons.Num(); ++Index)
	{
		SetButtonRect(RankButtons[Index], RefVec(1356 + (Index % 2) * 276, 20 + (Index / 2) * 38), RefVec(260, 34), 23);
		RankButtons[Index]->SetVisibility((bPrep && !bBattle) ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
		RankButtons[Index]->SetIsEnabled(bPrep);
	}
	for (int32 Index = 0; Index < BenchButtons.Num(); ++Index)
	{
		SetButtonRect(BenchButtons[Index], RefVec(632 + Index * 108, 978), RefVec(100, 82), 22);
		BenchButtons[Index]->SetVisibility((bPrep && !bModal) ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
		BenchButtons[Index]->SetIsEnabled(bPrep);
	}
	SetButtonRect(ConfirmButton, RefVec(1320, 956), RefVec(540, 64), 52);
	ConfirmButton->SetVisibility(bBP ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
	ConfirmButton->SetIsEnabled(bBP && Controller.IsValid() && !Controller->MatchState.BP.PlayerStrategyId.IsEmpty());
	SetButtonRect(DeployButton, RefVec(1720, 996), RefVec(150, 50), 22);
	DeployButton->SetVisibility(bPrep && !bModal ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
	DeployButton->SetIsEnabled(bPrep);
	SetButtonRect(ScoutCloseButton, RefVec(1508, 118), RefVec(34, 34), 31);
	ScoutCloseButton->SetVisibility(bScoutOpen ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
	const bool bWorldDomination = Controller.IsValid() && Controller->GetPhase() == ETreadM1Phase::GameOver
		&& Controller->MatchState.CampaignResult == TEXT("WorldDomination");
	SetButtonRect(ContinueButton, bWorldDomination ? RefVec(750, 680) : RefVec(1220, 900), RefVec(420, 64), 61);
	ContinueButton->SetVisibility(bResult ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
	ContinueButton->SetIsEnabled(bResult);
	SetButtonRect(StartButton, RefVec(720, 660), RefVec(480, 76), 61);
	StartButton->SetVisibility(Controller.IsValid() && Controller->GetPhase() == ETreadM1Phase::R0Briefing && !bCampaignMapSuppressed ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
	SetButtonRect(RefreshButton, RefVec(1604, 554), RefVec(138, 46), 22);
	SetButtonRect(ExperienceButton, RefVec(1754, 554), RefVec(138, 46), 22);
	SetButtonRect(LockButton, RefVec(1798, 120), RefVec(94, 42), 22);
	for (UButton* Button : {RefreshButton, ExperienceButton, LockButton})
	{
		Button->SetVisibility(bPrep && !bModal ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
	}
	FVector2D BoardMin(535, 216), BoardMax(535 + 704, 216 + 704);
	if (ATreadM3BoardPresenter* Presenter = FindBoardPresenter())
	{
		FVector2D PMin, PMax;
		if (Presenter->ProjectBoardRect(GetOwningPlayer(), PMin, PMax))
		{
			const float K = FMath::Max(LayoutScale, KINDA_SMALL_NUMBER);
			BoardMin = FVector2D(FMath::Max(PMin.X / K, 0.0f), FMath::Max(PMin.Y / K, 100.0f));
			BoardMax = FVector2D(FMath::Min(PMax.X / K, 1920.0f), FMath::Min(PMax.Y / K, 960.0f));
		}
	}
	SetButtonRect(BoardButton, RefVec(BoardMin.X, BoardMin.Y), RefVec(BoardMax.X - BoardMin.X, BoardMax.Y - BoardMin.Y), 1);
	BoardButton->SetVisibility(bPrep && !bModal ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
	const FTreadM1PlayerState* Human = GetHumanPlayer();
	for (int32 Index = 0; Index < ItemButtons.Num(); ++Index)
	{
		SetButtonRect(ItemButtons[Index], RefVec(1264 + (Index % 4) * 158, 742 + (Index / 4) * 44), RefVec(150, 38), 22);
		const bool bHasItem = Human && Human->EquipmentIds.IsValidIndex(Index);
		ItemButtons[Index]->SetVisibility(bPrep && !bModal && bHasItem ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
	}
	const bool bBriefing = Controller.IsValid() && Controller->GetPhase() == ETreadM1Phase::R0Briefing && !bCampaignMapSuppressed;
	for (int32 Index = 0; Index < StageButtons.Num(); ++Index)
	{
		const FVector2D Card = StageCardPosition(Index);
		SetButtonRect(StageButtons[Index], RefVec(Card.X, Card.Y), RefVec(196, 124), 62);
		StageButtons[Index]->SetVisibility(bBriefing ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
	}
	SetButtonRect(FreeMatchButton, RefVec(1250, 668), RefVec(330, 60), 62);
	FreeMatchButton->SetVisibility(bBriefing ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
	SetButtonRect(RosterButton, RefVec(330, 990), RefVec(140, 50), 22);
	// Zoom buttons sit on the top-right corner of the four board panels (document/170).
	const bool bBoardPanels = Controller.IsValid() && (Controller->GetPhase() == ETreadM1Phase::Preparation
		|| Controller->GetPhase() == ETreadM1Phase::Battle || Controller->GetPhase() == ETreadM1Phase::Settlement);
	const TArray<UButton*> ZoomButtons = {BattleZoomButton, FeedZoomButton, PactZoomButton, SquadZoomButton};
	const TArray<FVector2D> ZoomRects = {FVector2D(304, 204), FVector2D(1872, 176), FVector2D(486, 556), FVector2D(1580, 478)};
	for (int32 Index = 0; Index < ZoomButtons.Num(); ++Index)
	{
		SetButtonRect(ZoomButtons[Index], RefVec(ZoomRects[Index].X, ZoomRects[Index].Y), RefVec(26, 26), 84);
		ZoomButtons[Index]->SetVisibility(bBoardPanels ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
	}
	SetButtonRect(AudienceButton, RefVec(1560, 440), RefVec(344, 56), 22);
	AudienceButton->SetVisibility(Controller.IsValid() && Controller->GetPhase() == ETreadM1Phase::Battle && FindBoardPresenter()
		? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
	RosterButton->SetVisibility(bPrep && !bModal ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
	SetButtonRect(RosterPrevButton, RefVec(1404, 126), RefVec(120, 42), 82);
	SetButtonRect(RosterNextButton, RefVec(1534, 126), RefVec(120, 42), 82);
	SetButtonRect(RosterCloseButton, RefVec(1664, 126), RefVec(110, 42), 82);
	for (UButton* Button : {RosterPrevButton, RosterNextButton, RosterCloseButton})
	{
		Button->SetVisibility(bRosterOpen ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
	}
	(void)LocalSize;
}

void UTreadM1MatchWidget::HandleStateChanged()
{
	if (Audio) Audio->HandleStateChanged();
	Invalidate(EInvalidateWidgetReason::Paint);
}
void UTreadM1MatchWidget::HandlePhaseChanged(ETreadM1Phase PreviousPhase, ETreadM1Phase NewPhase)
{
	if (NewPhase == ETreadM1Phase::Battle) { bScoutOpen = false; bRosterOpen = false; DetailCharacterId.Empty(); }
	PhaseChangedAtSeconds = TreadUI::RealTime();
	if (Audio) Audio->HandlePhaseChanged(PreviousPhase, NewPhase);
	Invalidate(EInvalidateWidgetReason::Paint);
}

void UTreadM1MatchWidget::HandleAnyClick()
{
	if (!Controller.IsValid()) return;
	if (APlayerController* PC = GetOwningPlayer())
		if (UTreadDragController* Drag = PC->FindComponentByClass<UTreadDragController>())
			if (Drag->WasLastReleaseDrag()) return;
	if (StartButton->IsHovered()) { ShowCommandResult(Controller->BeginPreMatchBP(NextRequestId())); return; }
	if (RosterButton && RosterButton->IsHovered()) { bRosterOpen = true; Invalidate(EInvalidateWidgetReason::Paint); return; }
	if (BattleZoomButton && BattleZoomButton->IsHovered()) { bBattlePanelCollapsed = !bBattlePanelCollapsed; Invalidate(EInvalidateWidgetReason::Paint); return; }
	if (FeedZoomButton && FeedZoomButton->IsHovered()) { bFeedPanelCollapsed = !bFeedPanelCollapsed; Invalidate(EInvalidateWidgetReason::Paint); return; }
	if (PactZoomButton && PactZoomButton->IsHovered()) { bPactPanelCollapsed = !bPactPanelCollapsed; Invalidate(EInvalidateWidgetReason::Paint); return; }
	if (SquadZoomButton && SquadZoomButton->IsHovered()) { bSquadPanelCollapsed = !bSquadPanelCollapsed; Invalidate(EInvalidateWidgetReason::Paint); return; }
	if (AudienceButton && AudienceButton->IsHovered())
	{
		if (ATreadM3BoardPresenter* Presenter = FindBoardPresenter()) Presenter->ToggleAudienceCamera();
		Invalidate(EInvalidateWidgetReason::Paint);
		return;
	}
	if (Controller->GetPhase() == ETreadM1Phase::R0Briefing)
	{
		for (int32 Index = 0; Index < StageButtons.Num(); ++Index)
		{
			if (StageButtons[Index] && StageButtons[Index]->IsHovered()) { ShowCommandResult(Controller->SelectCampaignStage(Index + 1, NextRequestId())); return; }
		}
		if (FreeMatchButton && FreeMatchButton->IsHovered()) { ShowCommandResult(Controller->SelectCampaignStage(0, NextRequestId())); return; }
	}
	if (bRosterOpen)
	{
		const int32 Pages = FMath::Max(1, FMath::DivideAndRoundUp(Controller->GetRosterCharacterIds().Num(), RosterPerPage));
		if (RosterCloseButton->IsHovered()) bRosterOpen = false;
		else if (RosterPrevButton->IsHovered()) RosterPage = (RosterPage + Pages - 1) % Pages;
		else if (RosterNextButton->IsHovered()) RosterPage = (RosterPage + 1) % Pages;
		Invalidate(EInvalidateWidgetReason::Paint);
		return;
	}
	// M4 portrait detail: a long press on the detail image or on any avatar closes it; a short click on the detail image
	// does nothing; a long press on an avatar never buys or selects.
	const bool bLongPress = IsLongPress();
	if (DetailButton && DetailButton->IsHovered())
	{
		if (bLongPress) ClosePortraitDetail();
		return;
	}
	for (int32 Index = 0; Index < ShopAvatarButtons.Num(); ++Index)
	{
		if (!ShopAvatarButtons[Index] || !ShopAvatarButtons[Index]->IsHovered()) continue;
		if (bLongPress) { if (!DetailCharacterId.IsEmpty()) ClosePortraitDetail(); return; }
		const FTreadM1PlayerState* Human = GetHumanPlayer();
		if (Human && Human->Shop.Slots.IsValidIndex(Index) && !Human->Shop.Slots[Index].bIsSold && Controller->MatchState.Phase == ETreadM1Phase::Preparation)
			OpenPortraitDetail(Human->Shop.Slots[Index].CharacterId);
		return;
	}
	if (bLongPress)
	{
		for (int32 Index = 0; Index < BenchButtons.Num(); ++Index)
		{
			if (BenchButtons[Index] && BenchButtons[Index]->IsHovered())
			{
				if (!DetailCharacterId.IsEmpty()) ClosePortraitDetail();
				return;
			}
		}
	}
	if (RefreshButton->IsHovered()) { ShowCommandResult(Controller->RefreshShop(TEXT("P0"), NextRequestId())); return; }
	if (LockButton->IsHovered()) { ShowCommandResult(Controller->ToggleShopLock(TEXT("P0"), NextRequestId())); return; }
	if (ExperienceButton->IsHovered()) { ShowCommandResult(Controller->BuyExperience(TEXT("P0"), NextRequestId())); return; }
	for (int32 Index = 0; Index < BPButtons.Num(); ++Index) if (BPButtons[Index] && BPButtons[Index]->IsHovered()) { HandleBPCard(Index); return; }
	// document/176: claiming a free reward must win over the shop card drawn underneath it.
	for (int32 Index = 0; Index < RewardButtons.Num(); ++Index) if (RewardButtons[Index] && RewardButtons[Index]->IsHovered()) { HandleRewardCard(Index); return; }
	for (int32 Index = 0; Index < ShopButtons.Num(); ++Index) if (ShopButtons[Index] && ShopButtons[Index]->IsHovered()) { HandleShopCard(Index); return; }
	for (int32 Index = 0; Index < RankButtons.Num(); ++Index) if (RankButtons[Index] && RankButtons[Index]->IsHovered()) { HandleRankCard(Index); return; }
	for (int32 Index = 0; Index < ItemButtons.Num(); ++Index)
	{
		if (ItemButtons[Index] && ItemButtons[Index]->IsHovered())
		{
			PendingItemIndex = PendingItemIndex == Index ? INDEX_NONE : Index;
			StatusMessage = PendingItemIndex == INDEX_NONE ? FString() : TEXT("已选中装备：点击备战席单位装备");
			Invalidate(EInvalidateWidgetReason::Paint);
			return;
		}
	}
	for (int32 Index = 0; Index < BenchButtons.Num(); ++Index) if (BenchButtons[Index] && BenchButtons[Index]->IsHovered()) { HandleBenchCard(Index); return; }
	if (ConfirmButton && ConfirmButton->IsHovered()) { HandleConfirm(); return; }
	if (DeployButton && DeployButton->IsHovered()) { HandleDeploy(); return; }
	if (ScoutCloseButton && ScoutCloseButton->IsHovered()) { HandleCloseScout(); return; }
	if (ContinueButton && ContinueButton->IsHovered()) { HandleContinue(); return; }
}

void UTreadM1MatchWidget::HandleAnyPressed()
{
	PressStartSeconds = FPlatformTime::Seconds();
	// Bench press is the only UMG entry point into the drag state machine.
	// The component samples the cursor itself, so this remains valid for both
	// native graybox buttons and future WBP_BenchSlot instances.
	if (!Controller.IsValid() || Controller->MatchState.Phase != ETreadM1Phase::Preparation || bScoutOpen) return;
	if (BoardButton && BoardButton->IsHovered())
	{
		if (APlayerController* PC = GetOwningPlayer())
			if (UTreadDragController* Drag = PC->FindComponentByClass<UTreadDragController>())
			{
				FVector2D CursorPosition;
				if (Drag->SampleCursorPosition(CursorPosition)) Drag->BeginBoardPressAtScreenPosition(CursorPosition);
			}
		return;
	}
	int32 BenchIndex = INDEX_NONE;
	for (int32 Index = 0; Index < BenchButtons.Num(); ++Index)
	{
		if (BenchButtons[Index] && BenchButtons[Index]->IsHovered()) { BenchIndex = Index; break; }
	}
	if (BenchIndex == INDEX_NONE || Controller->MatchState.Players.Num() == 0) return;
	const FTreadM1UnitInstance* Unit = GetBenchUnit(BenchIndex);
	if (!Unit) return;
	APlayerController* PC = GetOwningPlayer();
	if (!PC && GetWorld()) PC = GetWorld()->GetFirstPlayerController();
	if (PC)
	{
		if (UTreadDragController* Drag = PC->FindComponentByClass<UTreadDragController>())
		{
			Drag->BeginBenchPress(BenchIndex, Unit->UnitInstanceId);
		}
	}
}

void UTreadM1MatchWidget::HandleBPCard(int32 CardIndex)
{
	if (!Controller.IsValid() || !Controller->MatchState.BP.AvailableStrategyIds.IsValidIndex(CardIndex)) return;
	ShowCommandResult(Controller->ChoosePlayerStrategy(Controller->MatchState.BP.AvailableStrategyIds[CardIndex], NextRequestId()));
}

void UTreadM1MatchWidget::HandleShopCard(int32 SlotIndex)
{
	if (Controller.IsValid()) ShowCommandResult(Controller->PurchaseShopSlot(TEXT("P0"), SlotIndex, NextRequestId()));
}

void UTreadM1MatchWidget::HandleRewardCard(int32 Index)
{
	const FTreadM1PlayerState* Human = GetHumanPlayer();
	if (!Controller.IsValid() || !Human) return;
	ShowCommandResult(Controller->ChooseReward(Human->PlayerId, Index, NextRequestId()));
}

void UTreadM1MatchWidget::HandleRankCard(int32 PlayerIndex)
{
	if (!Controller.IsValid() || !Controller->CanScout()) return;
	ScoutPlayerIndex = FMath::Clamp(PlayerIndex, 0, Controller->MatchState.Players.Num() - 1);
	bScoutOpen = true;
	PendingBenchIndex = INDEX_NONE;
	Invalidate(EInvalidateWidgetReason::Paint);
}

void UTreadM1MatchWidget::HandleBenchCard(int32 BenchIndex)
{
	if (!Controller.IsValid() || Controller->MatchState.Players.Num() == 0) return;
	const FTreadM1UnitInstance* Unit = GetBenchUnit(BenchIndex);
	if (!Unit) return;
	const FTreadM1PlayerState* Human = GetHumanPlayer();
	if (PendingItemIndex != INDEX_NONE && Human && Human->EquipmentIds.IsValidIndex(PendingItemIndex))
	{
		// M4: a selected inventory item goes onto the clicked bench unit.
		const FString ItemId = Human->EquipmentIds[PendingItemIndex];
		PendingItemIndex = INDEX_NONE;
		ShowCommandResult(Controller->EquipItem(Human->PlayerId, ItemId, Unit->UnitInstanceId, NextRequestId()));
		return;
	}
	// A click inside the drag threshold remains a selection/detail action: it opens the PNG detail of the bench unit.
	// A move is only ever issued by UTreadDragController on mouse release.
	PendingBenchIndex = PendingBenchIndex == BenchIndex ? INDEX_NONE : BenchIndex;
	OpenPortraitDetail(Unit->CharacterId);
	Invalidate(EInvalidateWidgetReason::Paint);
}

void UTreadM1MatchWidget::HandleConfirm()
{
	if (!Controller.IsValid()) return;
	// One AI decision per click leaves the promised player re-pick window open.
	if (Controller->MatchState.BP.AiPickStates.Contains(ETreadM1AIPickState::Waiting))
		ShowCommandResult(Controller->RunNextAIPick(NextRequestId()));
	else
		ShowCommandResult(Controller->ConfirmPreMatchBP(NextRequestId()));
}

void UTreadM1MatchWidget::HandleDeploy() { if (Controller.IsValid()) ShowCommandResult(Controller->DeployAndStartBattle(NextRequestId())); }
void UTreadM1MatchWidget::HandleCloseScout() { bScoutOpen = false; Invalidate(EInvalidateWidgetReason::Paint); }
void UTreadM1MatchWidget::HandleContinue()
{
	if (!Controller.IsValid()) return;
	if (Controller->GetPhase() == ETreadM1Phase::GameOver)
	{
		Controller->InitializeMatch(Controller->MatchState.Seed);
		StatusMessage.Empty();
	}
	else ShowCommandResult(Controller->AdvanceToNextRound(NextRequestId()));
}

FString UTreadM1MatchWidget::NextRequestId()
{
	return FString::Printf(TEXT("ui-%s-%llu"), *RequestPrefix, ++RequestSequence);
}

void UTreadM1MatchWidget::ShowCommandResult(const FTreadM1CommandResult& Result)
{
	StatusMessage = Result.bAccepted ? FString() : FString::Printf(TEXT("操作未完成：%s"), *UEnum::GetValueAsString(Result.ReasonCode));
	Invalidate(EInvalidateWidgetReason::Paint);
}

const FTreadM1UnitInstance* UTreadM1MatchWidget::GetBenchUnit(int32 Index) const
{
	const FTreadM1PlayerState* P = GetHumanPlayer();
	if (!P || !P->BenchUnitInstanceIds.IsValidIndex(Index)) return nullptr;
	const FString& Id = P->BenchUnitInstanceIds[Index];
	return P->BenchUnits.FindByPredicate([&Id](const FTreadM1UnitInstance& Unit) { return Unit.UnitInstanceId == Id; });
}

void UTreadM1MatchWidget::HandleAnyReleased()
{
	if (APlayerController* PC = GetOwningPlayer())
		if (UTreadDragController* Drag = PC->FindComponentByClass<UTreadDragController>()) Drag->HandleLeftMouseReleased();
}

void UTreadM1MatchWidget::NativeDestruct()
{
	if (Controller.IsValid())
	{
		Controller->OnStateChanged.RemoveDynamic(this, &UTreadM1MatchWidget::HandleStateChanged);
		Controller->OnPhaseChanged.RemoveDynamic(this, &UTreadM1MatchWidget::HandlePhaseChanged);
	}
	if (Audio) Audio->Shutdown();
	Super::NativeDestruct();
}

FLinearColor UTreadM1MatchWidget::TierColor(const FString& Tier) const
{
	return HudTierColor(Tier);
}

FLinearColor UTreadM1MatchWidget::FactionTextColor(int32 PlayerIndex) const
{
	// Owner ruling (doc 157): player = blue, enemy = red. P0 is the player's blue ink, the three AIs use their faction colours.
	if (PlayerIndex == 0) return TreadUI::PlayerInk;
	return TreadUI::AiFactionColor(PlayerIndex);
}

FString UTreadM1MatchWidget::PhaseLabel() const
{
	if (!Controller.IsValid()) return TEXT("M1");
	switch (Controller->MatchState.Phase)
	{
	case ETreadM1Phase::PreMatchBP: return TEXT("赛前 BP");
	case ETreadM1Phase::Preparation: return TEXT("准备期");
	case ETreadM1Phase::Battle: return TEXT("自动战斗");
	case ETreadM1Phase::Settlement: return TEXT("结算");
	case ETreadM1Phase::GameOver: return TEXT("对局结束");
	default: return TEXT("R0 简报");
	}
}

FString UTreadM1MatchWidget::RoundLabel() const
{
	if (!Controller.IsValid()) return TEXT("M1");
	const FString Round = EnumTail(UEnum::GetValueAsString(Controller->MatchState.RoundType));
	return FString::Printf(TEXT("第 %d / 12 回合 · %s"), Controller->MatchState.RoundIndex, *Round);
}

const FTreadM1PlayerState* UTreadM1MatchWidget::GetHumanPlayer() const
{
	if (!Controller.IsValid()) return nullptr;
	for (const FTreadM1PlayerState& PlayerState : Controller->MatchState.Players) if (PlayerState.bIsHuman) return &PlayerState;
	return Controller->MatchState.Players.IsValidIndex(0) ? &Controller->MatchState.Players[0] : nullptr;
}

const FTreadM1ScoutSnapshot* UTreadM1MatchWidget::GetScoutSnapshotForIndex(int32 PlayerIndex) const
{
	if (!Controller.IsValid() || !Controller->MatchState.ScoutSnapshots.IsValidIndex(PlayerIndex)) return nullptr;
	return &Controller->MatchState.ScoutSnapshots[PlayerIndex];
}

// ---------------------------------------------------------------- paper / ink primitives (doc 157 section 5)

void UTreadM1MatchWidget::DrawPaper(FSlateWindowElementList& Out, const FGeometry& Geometry, int32 Layer,
	const FVector2D& Position, const FVector2D& Size, bool bShadow) const
{
	TreadUI::PaperPanel(Out, Geometry, Layer, TreadUI::V2(Position), TreadUI::V2(Size), bShadow, LayoutScale);
}

void UTreadM1MatchWidget::DrawInset(FSlateWindowElementList& Out, const FGeometry& Geometry, int32 Layer,
	const FVector2D& Position, const FVector2D& Size, const FLinearColor& Fill) const
{
	TreadUI::Quad(Out, Geometry, Layer, TreadUI::V2(Position), TreadUI::V2(Size), Fill);
	TreadUI::Frame(Out, Geometry, Layer + 1, TreadUI::V2(Position), TreadUI::V2(Size), TreadUI::InkA(0.3f), FMath::Max(1.0f, Ref(1.0f)));
}

void UTreadM1MatchWidget::DrawBlock(FSlateWindowElementList& Out, const FGeometry& Geometry, int32 Layer,
	const FVector2D& Position, const FVector2D& Size, const FLinearColor& Fill, float BorderPx,
	const FLinearColor& BorderColor, float CutPx) const
{
	if (BorderPx <= 0.0f && CutPx <= 0.0f)
	{
		TreadUI::Quad(Out, Geometry, Layer, TreadUI::V2(Position), TreadUI::V2(Size), Fill);
		return;
	}
	TreadUI::CutBox(Out, Geometry, Layer, TreadUI::V2(Position), TreadUI::V2(Size), Fill, Ref(CutPx),
		CutPx > 0.0f ? TreadUI::ECorner::TL : TreadUI::ECorner::None, Ref(BorderPx), BorderColor);
}

void UTreadM1MatchWidget::DrawFrame(FSlateWindowElementList& Out, const FGeometry& Geometry, int32 Layer,
	const FVector2D& Position, const FVector2D& Size, const FLinearColor& Color, float ThicknessPx) const
{
	TreadUI::Frame(Out, Geometry, Layer, TreadUI::V2(Position), TreadUI::V2(Size), Color, FMath::Max(1.0f, Ref(ThicknessPx)));
}

void UTreadM1MatchWidget::DrawScrim(FSlateWindowElementList& Out, const FGeometry& Geometry, int32 Layer) const
{
	// Opaque paper ground. All three elements are boxes on one layer, so they stay in submission order.
	const FVector2f Origin(0.0f, 0.0f);
	const FVector2f Full = TreadUI::V2(LayoutSize);
	TreadUI::Quad(Out, Geometry, Layer, Origin, Full, TreadUI::Paper);
	TreadUI::Tiled(Out, Geometry, Layer, TreadUI::ETex::Grain, Origin, Full, FLinearColor(1.0f, 1.0f, 1.0f, 0.6f), 1.0f);
	TreadUI::Tex(Out, Geometry, Layer, TreadUI::ETex::Vignette, Origin, Full, FLinearColor::White);
}

void UTreadM1MatchWidget::DrawHeader(FSlateWindowElementList& Out, const FGeometry& Geometry, int32 Layer,
	const FVector2D& Position, float Width, const FString& Title, const FString& RuTag) const
{
	TreadUI::PanelHeader(Out, Geometry, Layer, TreadUI::V2(Position), Width, Title, RuTag, LayoutScale, true);
}

void UTreadM1MatchWidget::DrawButton(FSlateWindowElementList& Out, const FGeometry& Geometry, int32 Layer,
	const FVector2D& Position, const FVector2D& Size, const FString& Label, const FString& RuLabel,
	EHudButton ButtonStyle, const UButton* HoverSource, bool bEnabled, float LabelPt) const
{
	TreadUI::FButtonLook Look;
	Look.Scale = LayoutScale;
	Look.bCenter = true;
	Look.TrackingEm = 0.06f;
	// The style library sizes labels in design px (pt / 0.75). Start from the wanted size and shrink until label + tag fit.
	const float DesignHeight = static_cast<float>(Size.Y) / FMath::Max(LayoutScale, KINDA_SMALL_NUMBER);
	float Pt = LabelPt > 0.0f ? LabelPt : DesignHeight * 0.46f * 0.75f;
	const float Available = static_cast<float>(Size.X) * 0.9f;
	const float TagGap = RuLabel.IsEmpty() ? 0.0f : static_cast<float>(Size.Y) * 0.2f;
	for (int32 Step = 0; Step < 16 && Pt > 8.0f; ++Step)
	{
		float Width = TreadUI::TextSize(Label, TreadUI::Font(EFontRole::SansBlack, Ref(Pt), Look.TrackingEm)).X;
		if (!RuLabel.IsEmpty()) Width += TagGap + TreadUI::TextSize(RuLabel, TreadUI::Font(EFontRole::Russo, Ref(Pt) * 0.54f, 0.14f)).X;
		if (Width <= Available) break;
		Pt -= 0.5f;
	}
	Look.LabelPx = Pt / 0.75f;
	// The default 22 px cut is too big for the 42-50 px HUD buttons.
	Look.CutPx = FMath::Min(22.0f, static_cast<float>(Size.Y) / FMath::Max(LayoutScale, KINDA_SMALL_NUMBER) * 0.4f);
	const float HoverT = HoverSource && HoverSource->IsHovered() ? 1.0f : 0.0f;
	if (ButtonStyle == EHudButton::Primary)
		TreadUI::PrimaryButton(Out, Geometry, Layer, TreadUI::V2(Position), TreadUI::V2(Size), Label, RuLabel, HoverT, bEnabled, Look);
	else
		TreadUI::SecondaryButton(Out, Geometry, Layer, TreadUI::V2(Position), TreadUI::V2(Size), Label, RuLabel, HoverT, bEnabled, Look);
}

void UTreadM1MatchWidget::DrawStatus(FSlateWindowElementList& Out, const FGeometry& Geometry, int32 Layer) const
{
	if (StatusMessage.IsEmpty()) return;
	const float Width = FMath::Min(MeasureText(StatusMessage, 16, EFontRole::SansBold) + 40.0f, 900.0f);
	// The text keeps its old anchor (640, 935); the ink plate only pads it.
	DrawBlock(Out, Geometry, Layer, RefVec(628, 929), RefVec(Width, 38), TreadUI::InkA(0.94f), 0.0f, FLinearColor::Black, 10.0f);
	DrawText(Out, Geometry, Layer + 1, StatusMessage, RefVec(640, 935), 16, TreadUI::Amber, EFontRole::SansBold, FVector2D(Width - 24.0f, 26.0f));
}

void UTreadM1MatchWidget::DrawDivider(FSlateWindowElementList& Out, const FGeometry& Geometry, int32 Layer,
	const FVector2D& Position, const FVector2D& Size, const FLinearColor& Color) const
{
	TreadUI::Quad(Out, Geometry, Layer, TreadUI::V2(Position), TreadUI::V2(Size), Color);
}

float UTreadM1MatchWidget::MeasureText(const FString& Value, float FontSize, EFontRole Role, EHudText Flags) const
{
	if (Value.IsEmpty()) return 0.0f;
	const float Scale = FMath::Max(LayoutScale, KINDA_SMALL_NUMBER);
	if (EnumHasAnyFlags(Flags, EHudText::Numbers))
	{
		// Measure exactly the runs DrawText would draw (numeral face + optical size), not the plain face.
		FHudRun Base;
		Base.Role = Role;
		Base.Size = FontSize;
		const EFontRole NumberRole = HudNumberRole(Role);
		TArray<FHudRun> Runs;
		BuildHudRuns(Value, Base, true, NumberRole, HudNumberMul(Value, NumberRole), Runs);
		return MeasureRuns(Runs, LayoutScale) / Scale;
	}
	return MeasureHud(Value, TreadUI::Font(Role, Ref(FontSize))).Width / Scale;
}

TArray<FString> UTreadM1MatchWidget::WrapText(const FString& Value, float FontSize, EFontRole Role, float MaxWidth, int32 MaxLines, EHudText Flags,
	float HangWidth) const
{
	// Same measure as DrawText, so a line that fits here is never ellipsized again by the Bounds check there.
	return WrapWith(Value, [this, FontSize, Role, Flags](const FString& Text) { return MeasureText(Text, FontSize, Role, Flags); }, MaxWidth, MaxLines, HangWidth);
}

void UTreadM1MatchWidget::DrawText(FSlateWindowElementList& Out, const FGeometry& Geometry, int32 Layer,
	const FString& Value, const FVector2D& Position, float FontSize, const FLinearColor& Color, EFontRole Role,
	const FVector2D& Bounds, EHudText Flags) const
{
	if (Value.IsEmpty() || Color.A <= 0.0f) return;
	FHudRun Base;
	Base.Role = Role;
	Base.Color = Color;
	Base.Size = FontSize;
	const bool bNumbers = EnumHasAnyFlags(Flags, EHudText::Numbers);
	const EFontRole NumberRole = HudNumberRole(Role);
	const float NumberMul = HudNumberMul(Value, NumberRole);
	TArray<FHudRun> Runs;
	BuildHudRuns(Value, Base, bNumbers, NumberRole, NumberMul, Runs);
	if (Bounds.X < 1999.0)
	{
		// CSS text-overflow: ellipsis against the design-px bounds.
		const float MaxWidth = Ref(static_cast<float>(Bounds.X));
		if (MeasureRuns(Runs, LayoutScale) > MaxWidth)
		{
			int32 Lo = 0, Hi = Value.Len();
			while (Lo < Hi)
			{
				const int32 Mid = (Lo + Hi + 1) / 2;
				BuildHudRuns(CutWithEllipsis(Value, Mid), Base, bNumbers, NumberRole, NumberMul, Runs);
				if (MeasureRuns(Runs, LayoutScale) <= MaxWidth) Lo = Mid; else Hi = Mid - 1;
			}
			BuildHudRuns(CutWithEllipsis(Value, Lo), Base, bNumbers, NumberRole, NumberMul, Runs);
		}
	}
	const float AlignX = EnumHasAnyFlags(Flags, EHudText::Center) ? 0.5f : EnumHasAnyFlags(Flags, EHudText::Right) ? 1.0f : 0.0f;
	DrawRuns(Out, Geometry, Layer, LayoutScale, Position, Runs, AlignX, EnumHasAnyFlags(Flags, EHudText::Shadow));
}

int32 UTreadM1MatchWidget::NativePaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry,
	const FSlateRect& MyCullingRect, FSlateWindowElementList& OutDrawElements, int32 LayerId,
	const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const
{
	const_cast<UTreadM1MatchWidget*>(this)->LayoutSize = AllottedGeometry.GetLocalSize();
	const_cast<UTreadM1MatchWidget*>(this)->LayoutScale = ShortestSideScale(LayoutSize);
	GPaintFontScale = AllottedGeometry.GetAccumulatedLayoutTransform().GetScale();
	TreadUI::SetPaintFontScale(GPaintFontScale);
	DrawAll(AllottedGeometry, OutDrawElements, LayerId);
	return LayerId + 100;
}

void UTreadM1MatchWidget::DrawAll(const FGeometry& Geometry, FSlateWindowElementList& Out, int32 Layer) const
{
	if (!Controller.IsValid()) return;
	// On the board phases the HUD panels sit above the world-space unit labels / health bars (DrawBoard uses Layer+5..Layer+17);
	// under the full-screen paper phases the top bar stays beneath the scrim as before.
	const bool bBoardPhase = Controller->GetPhase() == ETreadM1Phase::Preparation || Controller->GetPhase() == ETreadM1Phase::Battle;
	DrawBase(Geometry, Out, Layer + (bBoardPhase ? 13 : 0));
	if (Controller->GetPhase() == ETreadM1Phase::R0Briefing)
	{
		if (!bCampaignMapSuppressed) DrawCampaignMap(Geometry, Out, Layer + 20);
		DrawStatus(Out, Geometry, Layer + 40);
		return;
	}
	if (Controller->GetPhase() == ETreadM1Phase::Preparation || Controller->GetPhase() == ETreadM1Phase::Battle)
		DrawBoard(Geometry, Out, Layer + 5);
	// The squad panel is a persistent HUD element: it also stays readable over the settlement scrim, so the player can
	// compare the bars the moment the round ends (document/168).
	if (Controller->GetPhase() == ETreadM1Phase::Preparation || Controller->GetPhase() == ETreadM1Phase::Battle
		|| Controller->GetPhase() == ETreadM1Phase::Settlement)
		DrawSquadPanel(Geometry, Out, Layer + 70);
	if (Controller->MatchState.Phase == ETreadM1Phase::PreMatchBP) DrawBP(Geometry, Out, Layer + 20);
	else if (bScoutOpen) DrawScout(Geometry, Out, Layer + 30);
	else if (Controller->MatchState.Phase == ETreadM1Phase::Preparation) DrawPreparation(Geometry, Out, Layer + 20);
	else if (Controller->MatchState.Phase == ETreadM1Phase::Battle) DrawBattle(Geometry, Out, Layer + 40);
	else DrawResult(Geometry, Out, Layer + 60);
	if (bRosterOpen) DrawRoster(Geometry, Out, Layer + 80);
	if (!DetailCharacterId.IsEmpty()) DrawPortraitDetail(Geometry, Out, Layer + 90);
	DrawStatus(Out, Geometry, Layer + 98);
	DrawDrag(Geometry, Out, Layer + 99);
}

void UTreadM1MatchWidget::DrawBase(const FGeometry& Geometry, FSlateWindowElementList& Out, int32 Layer) const
{
	const FTreadM1PlayerState* PlayerState = GetHumanPlayer();
	const FLinearColor InkDim = TreadUI::InkA(0.7f);

	// Left block: "踏国 · 第 N 关 国名" (free match: "自由对局 · 巴黎") on an ink bar, the phase label below it.
	FString StageTitle = TEXT("自由对局 · 巴黎");
	const int32 StageIndex = Controller->MatchState.CampaignStage;
	if (StageIndex > 0)
	{
		if (CachedCountryStage != StageIndex)
		{
			for (const FTreadM4CampaignStageView& Stage : Controller->GetCampaignStages())
			{
				if (Stage.Index != StageIndex) continue;
				CachedCountryStage = StageIndex;
				CachedCountry = Stage.Country;
				break;
			}
		}
		StageTitle = FString::Printf(TEXT("踏国 · 第 %d 关 %s"), StageIndex, CachedCountryStage == StageIndex ? *CachedCountry : TEXT(""));
	}
	DrawPaper(Out, Geometry, Layer, RefVec(16, 12), RefVec(600, 84), false);
	DrawHeader(Out, Geometry, Layer + 2, RefVec(16, 12), Ref(600), StageTitle, TEXT("ТРЕАД"));
	DrawBlock(Out, Geometry, Layer + 2, RefVec(34, 71), RefVec(10, 10), TreadUI::Red);
	DrawText(Out, Geometry, Layer + 3, PhaseLabel(), RefVec(54, 64), 16, TreadUI::Ink, EFontRole::SansBold);

	// Centre block: round and timer in the stencil numerals, the timer turns red in the last 10 s.
	DrawPaper(Out, Geometry, Layer, RefVec(770, 12), RefVec(380, 84), false);
	// The round-type suffix never fit the 160 px slot and was ellipsized to "ROUND · 回合 · …"; the caption now stands alone.
	DrawText(Out, Geometry, Layer + 2, TEXT("ROUND · 回合"), RefVec(792, 22), 12, InkDim, EFontRole::Mono, FVector2D(166.0f, 20.0f));
	const FString RoundNumber = FString::Printf(TEXT("%02d"), Controller->MatchState.RoundIndex);
	DrawText(Out, Geometry, Layer + 2, RoundNumber, RefVec(792, 38), 34, TreadUI::Ink, EFontRole::Stencil);
	const float RoundX = 792.0f + MeasureText(RoundNumber, 34, EFontRole::Stencil) + 8.0f;
	DrawText(Out, Geometry, Layer + 2, TEXT("/ 12"), RefVec(RoundX, 60), 16, InkDim, EFontRole::MonoBold);
	DrawDivider(Out, Geometry, Layer + 2, RefVec(966, 24), RefVec(1, 58), TreadUI::InkA(0.3f));
	const float Remaining = Controller->MatchState.PhaseTimeRemainingSec;
	DrawText(Out, Geometry, Layer + 2, TEXT("TIMER · 倒计时"), RefVec(990, 22), 12, InkDim, EFontRole::Mono, FVector2D(150.0f, 20.0f));
	if (Remaining > 0.0f)
	{
		const FString Seconds = FString::Printf(TEXT("%02d"), FMath::CeilToInt(Remaining));
		DrawText(Out, Geometry, Layer + 2, Seconds, RefVec(990, 38), 34, Remaining <= 10.0f ? TreadUI::Red : TreadUI::Ink, EFontRole::Stencil);
		DrawText(Out, Geometry, Layer + 2, TEXT("s"), RefVec(990.0f + MeasureText(Seconds, 34, EFontRole::Stencil) + 6.0f, 60), 16, InkDim, EFontRole::MonoBold);
	}
	else
	{
		DrawText(Out, Geometry, Layer + 2, TEXT("—"), RefVec(990, 38), 34, TreadUI::InkA(0.55f), EFontRole::Stencil);
	}

	// Right block: the four players in their faction colours, "name ♥hp ¤funds".
	DrawPaper(Out, Geometry, Layer, RefVec(1344, 12), RefVec(560, 84), false);
	for (int32 Index = 0; Index < Controller->MatchState.Players.Num() && Index < 4; ++Index)
	{
		const FTreadM1PlayerState& P = Controller->MatchState.Players[Index];
		const float X = 1356 + (Index % 2) * 276; const float Y = 20 + (Index / 2) * 38;
		FLinearColor Tone = FactionTextColor(Index);
		if (P.bIsEliminated) Tone.A = 0.45f;
		// Colour rule: the player's heart is player blue, every AI heart / HP is enemy red; only the AI name keeps its faction tint.
		FLinearColor HeartTone = Index == 0 ? TreadUI::PlayerInk : TreadUI::Red;
		if (P.bIsEliminated) HeartTone.A = 0.45f;
		DrawText(Out, Geometry, Layer + 2, P.DisplayName, RefVec(X + 4, Y + 6), 16, Tone, Index == 0 ? EFontRole::SansBlack : EFontRole::SansBold, FVector2D(112.0f, 24.0f));
		DrawText(Out, Geometry, Layer + 2, FString::Printf(TEXT("♥%d"), ShownHealth(P)), RefVec(X + 124, Y + 7), 15, HeartTone, EFontRole::MonoBold, FVector2D(66.0f, 24.0f));
		DrawText(Out, Geometry, Layer + 2, FString::Printf(TEXT("¤%d"), P.Funds), RefVec(X + 192, Y + 7), 15, Tone, EFontRole::MonoBold, FVector2D(64.0f, 24.0f));
	}

	if (PlayerState)
	{
		DrawPaper(Out, Geometry, Layer, RefVec(16, 108), RefVec(320, 76), true);
		DrawText(Out, Geometry, Layer + 2, TEXT("策略"), RefVec(32, 124), 12, InkDim, EFontRole::Mono);
		DrawText(Out, Geometry, Layer + 2, PlayerState->InitialStrategyId, RefVec(68, 119), 17, TreadUI::PlayerInk, EFontRole::SansBlack, FVector2D(250.0f, 26.0f));
		// Stat row "♥ hp  ¤ funds  Lv n  人口 used/limit": the segments follow each other by their measured width with one shared gap
		// (14 design px, squeezed down to 8 when a 3-digit hp / funds value would push the row past the card), so no value ever touches
		// its neighbour. The old fixed x positions (30 / 96 / 160 / 214) left "100" and "¤" touching while "¤" and "5" drifted apart.
		// The player's own heart is player ink, as in the score board on the right.
		{
			const FString HealthText = FString::Printf(TEXT("♥ %d"), ShownHealth(*PlayerState));
			const FString FundsText = FString::Printf(TEXT("¤ %d"), PlayerState->Funds);
			const FString LevelText = FString::Printf(TEXT("Lv %d"), PlayerState->Level);
			const FString PopulationText = FString::Printf(TEXT("人口 %d/%d"), PlayerState->PopulationUsed, PlayerState->PopulationLimit);
			constexpr float RowLeft = 30.0f;
			constexpr float RowRight = 328.0f;   // card is x 16..336 with a 3 px border
			const float HealthWidth = MeasureText(HealthText, 14, EFontRole::MonoBold);
			const float FundsWidth = MeasureText(FundsText, 14, EFontRole::MonoBold);
			const float LevelWidth = MeasureText(LevelText, 14, EFontRole::MonoBold);
			const float PopulationWidth = MeasureText(PopulationText, 14, EFontRole::Mono, EHudText::Numbers);
			const float Gap = FMath::Clamp((RowRight - RowLeft - HealthWidth - FundsWidth - LevelWidth - PopulationWidth) / 3.0f, 8.0f, 14.0f);
			float RowX = RowLeft;
			DrawText(Out, Geometry, Layer + 2, HealthText, RefVec(RowX, 151), 14, TreadUI::PlayerInk, EFontRole::MonoBold);
			RowX += HealthWidth + Gap;
			DrawText(Out, Geometry, Layer + 2, FundsText, RefVec(RowX, 151), 14, TreadUI::Ochre, EFontRole::MonoBold);
			RowX += FundsWidth + Gap;
			DrawText(Out, Geometry, Layer + 2, LevelText, RefVec(RowX, 151), 14, TreadUI::Ink, EFontRole::MonoBold);
			RowX += LevelWidth + Gap;
			// The last segment may only use what is left of the card (up to the inner border, x 333); beyond that it is cut with an
			// ellipsis instead of spilling out. The 4 px slack keeps float rounding from cutting a row that exactly fills RowRight.
			DrawText(Out, Geometry, Layer + 2, PopulationText, RefVec(RowX, 151), 14, InkDim, EFontRole::Mono, FVector2D(FMath::Max(40.0f, RowRight + 4.0f - RowX), 24.0f), EHudText::Numbers);
		}
	}
}

void UTreadM1MatchWidget::DrawBP(const FGeometry& Geometry, FSlateWindowElementList& Out, int32 Layer) const
{
	const FLinearColor InkDim = TreadUI::InkA(0.7f);
	DrawScrim(Out, Geometry, Layer);
	// The last card row (y 792..930) used to hang out of the 908 panel bottom. Both panels now end at y 944 (14 px under the cards,
	// same bottom edge); the confirm button moved from y 932 to 956 to keep clear of them (click point 1590,964 stays inside).
	DrawPaper(Out, Geometry, Layer + 1, RefVec(16, 112), RefVec(1260, 832), true);
	DrawPaper(Out, Geometry, Layer + 1, RefVec(1292, 112), RefVec(612, 832), true);
	DrawHeader(Out, Geometry, Layer + 3, RefVec(16, 112), Ref(1260), TEXT("赛前策略 BP"), TEXT("ВЫБОР СТРАТЕГИИ"));
	DrawHeader(Out, Geometry, Layer + 3, RefVec(1292, 112), Ref(612), TEXT("选择状态"), TEXT("СТАТУС"));
	DrawText(Out, Geometry, Layer + 5, TEXT("系统 BAN 4  ·  你选择 1  ·  AI 1 / AI 2 / AI 3  ·  确认后开局"), RefVec(34, 171), 15, InkDim, EFontRole::Mono, FVector2D(1200.0f, 30.0f), EHudText::Numbers);
	const int32 StrategyCount = FMath::Clamp(Controller->MatchState.Strategies.Num(), 1, 40);
	DrawText(Out, Geometry, Layer + 5, FString::Printf(TEXT("%d 策略候选 / 当前唯一选择"), StrategyCount), RefVec(1880, 123), 15, TreadUI::PaperL,
		EFontRole::SansBold, FVector2D(560.0f, 26.0f), EHudText::Right | EHudText::Numbers);
	for (int32 Index = 0; Index < StrategyCount; ++Index)
	{
		const int32 Col = Index % 8; const int32 Row = Index / 8;
		const float X = 16 + Col * 158; const float Y = 208 + Row * 146;
		// Keep all 32 real IDs visible: the 28 offers first, followed by the
		// four system bans.  This also keeps the first 28 hit targets aligned
		// with AvailableStrategyIds while the BAN cards remain read-only.
		const bool bBannedCard = Index >= Controller->MatchState.BP.AvailableStrategyIds.Num();
		const int32 BannedIndex = Index - Controller->MatchState.BP.AvailableStrategyIds.Num();
		const FString Id = !bBannedCard && Controller->MatchState.BP.AvailableStrategyIds.IsValidIndex(Index)
			? Controller->MatchState.BP.AvailableStrategyIds[Index]
			: (Controller->MatchState.BP.BannedStrategyIds.IsValidIndex(BannedIndex)
				? Controller->MatchState.BP.BannedStrategyIds[BannedIndex]
				: FString::Printf(TEXT("strategy_%03d"), Index + 1));
		const bool bSystemBanned = bBannedCard || Controller->MatchState.BP.BannedStrategyIds.Contains(Id);
		const int32 OccupiedAiIndex = Controller->MatchState.BP.AiStrategyIds.IndexOfByKey(Id);
		const bool bOccupied = OccupiedAiIndex != INDEX_NONE;
		const bool bPlayerSelected = Controller->MatchState.BP.PlayerStrategyId == Id;
		const bool bHovered = !bSystemBanned && BPButtons.IsValidIndex(Index) && BPButtons[Index]->IsHovered();

		// Card: paper (selectable), PlayerInk (picked), AI-coloured outline (taken), hatched PaperDD (system ban).
		const FVector2D CardPos = RefVec(X, Y);
		const FVector2D CardSize = RefVec(148, 138);
		FLinearColor CardFill = TreadUI::Paper;
		FLinearColor CardEdge = bHovered ? TreadUI::Red : TreadUI::Ink;
		float CardBorder = bHovered ? 3.0f : 2.0f;
		if (bSystemBanned) { CardFill = TreadUI::PaperDD; CardEdge = TreadUI::InkA(0.55f); }
		else if (bPlayerSelected) { CardFill = TreadUI::PlayerInk; CardEdge = TreadUI::Ink; CardBorder = 3.0f; }
		else if (bOccupied) { CardEdge = TreadUI::AiFactionColor(OccupiedAiIndex + 1); CardBorder = 3.0f; }
		if (bPlayerSelected)
			TreadUI::CutBox(Out, Geometry, Layer + 2, TreadUI::V2(CardPos + RefVec(4, 4)), TreadUI::V2(CardSize), TreadUI::Ink, Ref(10), TreadUI::ECorner::TL);
		DrawBlock(Out, Geometry, Layer + 2, CardPos, CardSize, CardFill, CardBorder, CardEdge, 10.0f);
		if (bSystemBanned)
			TreadUI::Tiled(Out, Geometry, Layer + 3, TreadUI::ETex::Hatch, TreadUI::V2(CardPos + RefVec(2, 2)), TreadUI::V2(CardSize - RefVec(4, 4)), TreadUI::InkA(0.12f), LayoutScale);

		const FLinearColor IndexColor = bSystemBanned ? TreadUI::InkA(0.45f) : bPlayerSelected ? TreadUI::PaperL
			: HudTierColor(Index < 6 ? TEXT("I") : Index < 14 ? TEXT("II") : Index < 22 ? TEXT("III") : TEXT("IV"));
		DrawText(Out, Geometry, Layer + 5, FString::Printf(TEXT("%02d"), Index + 1), RefVec(X + 12, Y + 8), 22, IndexColor, EFontRole::Stencil);
		// Strategy name = its 【effect】 heading; the full text shows in the right-hand detail panel.
		FString CardTitle = Id;
		if (const FTreadM1StrategyState* Strategy = Controller->MatchState.Strategies.FindByPredicate([&Id](const FTreadM1StrategyState& S) { return S.StrategyId == Id; }))
		{
			FString Head, Rest;
			CardTitle = Strategy->OfferText.Split(TEXT("】"), &Head, &Rest) ? Head.Replace(TEXT("【"), TEXT("")) : Strategy->OfferText.Left(8);
		}
		const FLinearColor TitleColor = bSystemBanned ? TreadUI::InkA(0.55f) : bPlayerSelected ? TreadUI::PaperL : TreadUI::Ink;
		const TArray<FString> TitleLines = WrapToWidth(CardTitle, TreadUI::Font(EFontRole::SansBold, Ref(15)), Ref(126), 2);
		for (int32 Line = 0; Line < TitleLines.Num(); ++Line)
			DrawText(Out, Geometry, Layer + 5, TitleLines[Line], RefVec(X + 12, Y + 46 + Line * 22), 15, TitleColor, EFontRole::SansBold);
		FString CardStatus = TEXT("可选");
		FLinearColor StatusColor = InkDim;
		EFontRole StatusRole = EFontRole::SansMedium;
		if (bPlayerSelected) { CardStatus = TEXT("已选 ✓"); StatusColor = TreadUI::PaperL; StatusRole = EFontRole::SansBlack; }
		else if (bSystemBanned) { CardStatus = TEXT("系统 BAN"); StatusColor = TreadUI::Red; StatusRole = EFontRole::SansBlack; }
		else if (bOccupied) { CardStatus = FString::Printf(TEXT("AI %d 已选"), OccupiedAiIndex + 1); StatusColor = TreadUI::AiFactionColor(OccupiedAiIndex + 1); StatusRole = EFontRole::SansBlack; }
		DrawText(Out, Geometry, Layer + 5, CardStatus, RefVec(X + 12, Y + 108), 15, StatusColor, StatusRole, FVector2D(130.0f, 24.0f), EHudText::Numbers);
	}

	DrawText(Out, Geometry, Layer + 5, TEXT("你的选择"), RefVec(1320, 190), 16, InkDim, EFontRole::Mono);
	DrawInset(Out, Geometry, Layer + 2, RefVec(1320, 220), RefVec(540, 120), TreadUI::PaperDD);
	const bool bHasPick = !Controller->MatchState.BP.PlayerStrategyId.IsEmpty();
	DrawText(Out, Geometry, Layer + 5, bHasPick ? Controller->MatchState.BP.PlayerStrategyId : FString(TEXT("请选择一张策略卡")), RefVec(1340, 228), 20,
		bHasPick ? TreadUI::PlayerInk : InkDim, EFontRole::SansBlack, FVector2D(500.0f, 30.0f));
	if (const FTreadM1StrategyState* Picked = Controller->MatchState.Strategies.FindByPredicate([this](const FTreadM1StrategyState& S) { return S.StrategyId == Controller->MatchState.BP.PlayerStrategyId; }))
	{
		// Closing punctuation hangs past the 500 px measure (up to 19 px, one full-width mark; the inset ends at x 1860) instead of starting
		// the next line, so the draw bounds carry that slack too.
		const TArray<FString> OfferLines = WrapText(Picked->OfferText, 14, EFontRole::SansMedium, 500, 2, EHudText::Numbers, 19.0f);
		for (int32 Line = 0; Line < OfferLines.Num(); ++Line)
			DrawText(Out, Geometry, Layer + 5, OfferLines[Line], RefVec(1340, 262 + Line * 20), 14, TreadUI::Ink, EFontRole::SansMedium, FVector2D(521.0f, 24.0f), EHudText::Numbers);
	}
	DrawText(Out, Geometry, Layer + 5, TEXT("确认后生命代价只扣一次；AI 全部确认前可改选"), RefVec(1340, 308), 15, InkDim, EFontRole::SansMedium, FVector2D(500.0f, 26.0f));
	DrawText(Out, Geometry, Layer + 5, TEXT("AI 选择状态"), RefVec(1320, 376), 16, InkDim, EFontRole::Mono);
	for (int32 Index = 0; Index < 3; ++Index)
	{
		const bool bConfirmed = Controller->MatchState.BP.AiPickStates.IsValidIndex(Index) && Controller->MatchState.BP.AiPickStates[Index] == ETreadM1AIPickState::Confirmed;
		const FString Pick = Controller->MatchState.BP.AiStrategyIds.IsValidIndex(Index) ? Controller->MatchState.BP.AiStrategyIds[Index] : FString();
		DrawInset(Out, Geometry, Layer + 2, RefVec(1320, 410 + Index * 62), RefVec(540, 50), TreadUI::PaperDD);
		DrawText(Out, Geometry, Layer + 5, FString::Printf(TEXT("AI %d"), Index + 1), RefVec(1340, 420 + Index * 62), 18, TreadUI::AiFactionColor(Index + 1), EFontRole::SansBlack, FVector2D(2000.0f, 200.0f), EHudText::Numbers);
		DrawRuns(Out, Geometry, Layer + 5, LayoutScale, RefVec(1420, 423 + Index * 62), {
			{ bConfirmed ? FString(TEXT("已确认 ✓")) : FString(TEXT("等待中")), EFontRole::SansBold, bConfirmed ? TreadUI::Ink : InkDim, 16.0f },
			{ Pick.IsEmpty() ? FString() : FString(TEXT("   ")) + Pick, EFontRole::Mono, TreadUI::Ink, 14.0f } }, 0.0f, false);
	}
	DrawText(Out, Geometry, Layer + 5, TEXT("系统 BAN：4 张红色封禁策略"), RefVec(1320, 620), 16, TreadUI::Red, EFontRole::SansBold, FVector2D(2000.0f, 200.0f), EHudText::Numbers);
	// Legend: one swatch per card state.
	{
		float LegendX = 1320.0f;
		const auto Legend = [&](const TCHAR* Label, const FLinearColor& Fill, const FLinearColor& Edge, bool bHatch)
		{
			DrawBlock(Out, Geometry, Layer + 2, RefVec(LegendX, 674), RefVec(14, 14), Fill, 2.0f, Edge);
			if (bHatch) TreadUI::Tiled(Out, Geometry, Layer + 3, TreadUI::ETex::Hatch, TreadUI::V2(RefVec(LegendX + 2, 676)), TreadUI::V2(RefVec(10, 10)), TreadUI::InkA(0.2f), LayoutScale);
			DrawText(Out, Geometry, Layer + 5, Label, RefVec(LegendX + 20, 671), 14, InkDim, EFontRole::Mono);
			LegendX += 20.0f + MeasureText(Label, 14, EFontRole::Mono) + 20.0f;
		};
		Legend(TEXT("可选"), TreadUI::Paper, TreadUI::Ink, false);
		Legend(TEXT("已选"), TreadUI::PlayerInk, TreadUI::Ink, false);
		Legend(TEXT("已确认 ✓"), TreadUI::PaperDD, TreadUI::Ink, false);
		Legend(TEXT("被占用"), TreadUI::Paper, TreadUI::Red, false);
		Legend(TEXT("系统 BAN"), TreadUI::PaperDD, TreadUI::InkA(0.55f), true);
	}
	const bool bWaitingAi = Controller->MatchState.BP.AiPickStates.Contains(ETreadM1AIPickState::Waiting);
	DrawButton(Out, Geometry, Layer + 2, RefVec(1320, 956), RefVec(540, 64),
		bWaitingAi ? FString(TEXT("下一位 AI 选择")) : FString(TEXT("确认策略 · 开始 R1")), bWaitingAi ? FString(TEXT("ДАЛЕЕ")) : FString(TEXT("ПОДТВЕРДИТЬ")),
		EHudButton::Primary, ConfirmButton, bHasPick, 24.0f);
}

void UTreadM1MatchWidget::DrawScout(const FGeometry& Geometry, FSlateWindowElementList& Out, int32 Layer) const
{
	const FLinearColor InkDim = TreadUI::InkA(0.7f);
	// Dimmed band over the board, then the paper dossier.
	DrawBlock(Out, Geometry, Layer, RefVec(0, 96), FVector2D(LayoutSize.X, Ref(420)), TreadUI::InkA(0.45f));
	DrawPaper(Out, Geometry, Layer + 1, RefVec(370, 104), RefVec(1180, 392), true);
	DrawHeader(Out, Geometry, Layer + 3, RefVec(370, 104), Ref(1180), TEXT("ScoutSnapshot  ·  只读侦察"), TEXT("РАЗВЕДКА"));
	DrawText(Out, Geometry, Layer + 5, TEXT("准备期可查看 4 名参赛者；商店与隐藏策略不公开"), RefVec(396, 160), 16, InkDim, EFontRole::SansMedium, FVector2D(1000.0f, 26.0f), EHudText::Numbers);
	DrawInset(Out, Geometry, Layer + 2, RefVec(392, 196), RefVec(254, 274), TreadUI::PaperDD);
	for (int32 Index = 0; Index < Controller->MatchState.Players.Num() && Index < 4; ++Index)
	{
		const FTreadM1PlayerState& P = Controller->MatchState.Players[Index];
		const bool bPicked = Index == ScoutPlayerIndex;
		const FVector2D RowPos = RefVec(404, 208 + Index * 58);
		const FVector2D RowSize = RefVec(230, 48);
		if (bPicked)
		{
			DrawBlock(Out, Geometry, Layer + 4, RowPos, RowSize, TreadUI::PaperL, 2.0f, TreadUI::Ink);
			DrawBlock(Out, Geometry, Layer + 5, RowPos + RefVec(2, 2), RefVec(6, 44), TreadUI::Red);
		}
		else
		{
			DrawInset(Out, Geometry, Layer + 4, RowPos, RowSize, TreadUI::Paper);
		}
		DrawText(Out, Geometry, Layer + 6, FString::Printf(TEXT("%d  %s"), P.Rank > 0 ? P.Rank : Index + 1, *P.DisplayName), RefVec(418, 215 + Index * 58), 16, FactionTextColor(Index),
			bPicked ? EFontRole::SansBlack : EFontRole::SansBold, FVector2D(206.0f, 24.0f), EHudText::Numbers);
		DrawText(Out, Geometry, Layer + 6, FString::Printf(TEXT("♥ %d   ¤ %d   Lv %d"), P.Health, P.Funds, P.Level), RefVec(418, 238 + Index * 58), 14, InkDim, EFontRole::Mono, FVector2D(206.0f, 22.0f), EHudText::Numbers);
	}
	const FTreadM1ScoutSnapshot* Snapshot = GetScoutSnapshotForIndex(ScoutPlayerIndex);
	DrawText(Out, Geometry, Layer + 5, Snapshot ? FString::Printf(TEXT("%s 的棋盘阵容"), *Snapshot->DisplayName) : FString(TEXT("ScoutSnapshot")), RefVec(676, 195), 18, TreadUI::PlayerInk, EFontRole::SansBlack, FVector2D(420.0f, 28.0f));
	for (int32 Row = 0; Row < 4; ++Row) for (int32 Col = 0; Col < 8; ++Col) DrawInset(Out, Geometry, Layer + 2, RefVec(676 + Col * 54, 230 + Row * 48), RefVec(48, 42), TreadUI::PaperDD);
	if (Snapshot)
	{
		for (const FTreadM1UnitInstance& Unit : Snapshot->BoardUnits)
		{
			if (Unit.BoardCell.X < 0 || Unit.BoardCell.Y < 0) continue;
			// Human board cells use rows 4-7, while the current AI graybox
			// rosters use rows 0-3. Preserve the four local rows in either case.
			const int32 LocalRow = Unit.BoardCell.Y >= 4 ? Unit.BoardCell.Y - 4 : Unit.BoardCell.Y;
			if (Unit.BoardCell.X > 7 || LocalRow > 3) continue;
			const float X = 676 + Unit.BoardCell.X * 54; const float Y = 230 + LocalRow * 48;
			DrawBlock(Out, Geometry, Layer + 4, RefVec(X, Y), RefVec(48, 42), HudTierColor(Unit.OperatorTier), 2.0f, TreadUI::Ink);
			DrawText(Out, Geometry, Layer + 6, Unit.CharacterId.RightChop(5), RefVec(X + 5, Y + 6), 12, TreadUI::PaperL, EFontRole::MonoBold, FVector2D(40.0f, 18.0f));
			DrawText(Out, Geometry, Layer + 6, FString::Printf(TEXT("★%d"), Unit.UnitStar), RefVec(X + 5, Y + 22), 12, TreadUI::PaperL, EFontRole::MonoBold);
		}
		DrawText(Out, Geometry, Layer + 5, FString::Printf(TEXT("备战席 %d / 8    装备 %d    盟约层数 %d"), Snapshot->BenchUnits.Num(), Snapshot->EquipmentIds.Num(), Snapshot->PactStacks.Num()), RefVec(676, 442), 15, InkDim, EFontRole::Mono, FVector2D(420.0f, 24.0f), EHudText::Numbers);
		DrawText(Out, Geometry, Layer + 5, TEXT("盟约 · 人数 / 层数"), RefVec(1124, 195), 16, TreadUI::PlayerInk, EFontRole::SansBlack, FVector2D(410.0f, 26.0f));
		int32 ScoutRow = 0;
		for (const FTreadM2PactProgress& Pact : Snapshot->Pacts)
		{
			if ((Pact.Count <= 0 && Pact.Stacks <= 0) || ScoutRow >= 11) continue;
			const float Y = 224 + ScoutRow++ * 22;
			DrawText(Out, Geometry, Layer + 5, FString::Printf(TEXT("%s%s  %d/%d  层 %d"), Pact.bActive ? TEXT("● ") : TEXT("○ "), *Pact.PactId, Pact.Count,
				Pact.NextThreshold > 0 ? Pact.NextThreshold : (Pact.Thresholds.Num() > 0 ? Pact.Thresholds.Last() : 0), Pact.Stacks),
				RefVec(1124, Y), 14, Pact.bActive ? TreadUI::Ink : TreadUI::InkA(0.6f), Pact.bActive ? EFontRole::SansBold : EFontRole::Mono, FVector2D(410.0f, 22.0f), EHudText::Numbers);
		}
	}
	// Close chip over the right end of the ink bar (hit area of ScoutClose).
	DrawBlock(Out, Geometry, Layer + 5, RefVec(1508, 118), RefVec(34, 34), ScoutCloseButton && ScoutCloseButton->IsHovered() ? TreadUI::RedD : TreadUI::Red, 0.0f, FLinearColor::Black, 8.0f);
	DrawText(Out, Geometry, Layer + 6, TEXT("×"), RefVec(1525, 118), 22, TreadUI::PaperL, EFontRole::SansBlack, FVector2D(2000.0f, 200.0f), EHudText::Center);
}

FVector2D UTreadM1MatchWidget::ScreenToDesign(const FGeometry& Geometry, const FVector2D& Screen) const
{
	// ProjectWorldToScreen returns viewport pixels, while Ref() / RefVec() place elements in the widget's own design px
	// (the DPI-scaled 1920x1080 space). Treating one as the other squashed every world-anchored overlay towards the
	// top-left corner; the accumulated layout scale is exactly the local->absolute factor between the two spaces.
	const float PaintScale = FMath::Max(Geometry.GetAccumulatedLayoutTransform().GetScale(), KINDA_SMALL_NUMBER);
	return Screen / (PaintScale * FMath::Max(LayoutScale, KINDA_SMALL_NUMBER));
}

void UTreadM1MatchWidget::DrawBoard(const FGeometry& Geometry, FSlateWindowElementList& Out, int32 Layer) const
{
	const FTreadM1PlayerState* P = GetHumanPlayer();
	if (!P) return;
	UTreadDragController* Drag = GetOwningPlayer() ? GetOwningPlayer()->FindComponentByClass<UTreadDragController>() : nullptr;
	// "● 交战中 · 自动结算": PaperL with the ink shadow, a red dot blinks in front of it. Drawn well above the battle
	// banner (DrawBattle) so the banner never hides it.
	const auto DrawEngaged = [&](const FVector2D& Anchor, float SizePt, float AlignX)
	{
		const float Wave = FMath::Sin((GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0f) * 6.0f);
		DrawRuns(Out, Geometry, Layer + 50, LayoutScale, Anchor, {
			{ FString(TEXT("● ")), EFontRole::SansBlack, TreadUI::WithAlpha(TreadUI::Red, 0.5f + 0.5f * Wave), SizePt },
			{ FString(TEXT("交战中  ·  自动结算")), EFontRole::SansBlack, TreadUI::WithAlpha(TreadUI::PaperL, 0.85f + 0.15f * Wave), SizePt } }, AlignX, true);
	};
	if (ATreadM3BoardPresenter* Presenter = FindBoardPresenter())
	{
		// M3: units stand on the 3D board; the ring under each unit carries its health (document/159), so the HUD only
		// has to mirror the drop state and name the skill being cast. The tier / star plate stays on the head during
		// preparation and is dropped once the battle presentation runs (owner's call, 2026-10-17): in the fight the
		// ring alone has to carry the reading.
		Presenter->SetHoverCell(Drag && Drag->IsDragging() ? Drag->GetHoverBoardCell() : FIntPoint(-1, -1), Drag && Drag->IsHoverAllowed());
		Presenter->SetDraggedUnit(Drag && Drag->IsDragging() ? Drag->GetSourceUnitInstanceId() : FString());
		TArray<FTreadM3UnitAnchor> Anchors;
		Presenter->GetAnchors(Anchors);
		APlayerController* PC = GetOwningPlayer();
		const bool bShowPlate = Controller->GetPhase() == ETreadM1Phase::Preparation;
		const auto FindUnit = [this](const FString& UnitInstanceId) -> const FTreadM1UnitInstance*
		{
			for (const FTreadM1PlayerState& Player : Controller->MatchState.Players)
			{
				for (const FTreadM1UnitInstance& Unit : Player.BoardUnits)
				{
					if (Unit.UnitInstanceId == UnitInstanceId) return &Unit;
				}
			}
			return nullptr;
		};
		for (const FTreadM3UnitAnchor& A : Anchors)
		{
			FVector2D Screen;
			if (!PC || !UGameplayStatics::ProjectWorldToScreen(PC, A.HeadWorld, Screen, true)) continue;
			const FVector2D Local = ScreenToDesign(Geometry, Screen);
			const FTreadM1UnitInstance* Unit = bShowPlate ? FindUnit(A.UnitInstanceId) : nullptr;
			if (Unit)
			{
				// Label plate: player PlayerInk, enemy Red (both 90%); the text is PaperL.
				const FLinearColor LabelFill = A.bEnemy ? TreadUI::WithAlpha(TreadUI::Red, 0.9f) : TreadUI::WithAlpha(TreadUI::PlayerInk, 0.9f);
				const FString Stars = FString::ChrN(FMath::Clamp(Unit->UnitStar, 1, 3), TEXT('★'));
				DrawBlock(Out, Geometry, Layer + 1, RefVec(Local.X - 46, Local.Y - 30), RefVec(92, 28), LabelFill, 0.0f, FLinearColor::Black, 6.0f);
				DrawText(Out, Geometry, Layer + 3, FString::Printf(TEXT("%s %s"), *Unit->OperatorTier, *Stars), RefVec(Local.X, Local.Y - 27), 15,
					TreadUI::PaperL, EFontRole::SansBlack, FVector2D(2000.0f, 200.0f), EHudText::Center);
			}
			if (!A.SkillLabel.IsEmpty() && !A.bDead)
			{
				FLinearColor Color = A.SkillColor;
				Color.A = 1.0f - FMath::Max(0.0f, A.SkillAge01 - 0.7f) / 0.3f;
				DrawBlock(Out, Geometry, Layer + 3, RefVec(Local.X - 80, Local.Y - 66), RefVec(160, 30), TreadUI::InkA(0.80f * Color.A), 0.0f, FLinearColor::Black, 8.0f);
				DrawText(Out, Geometry, Layer + 4, A.SkillLabel, RefVec(Local.X - 74, Local.Y - 62), 16, Color, EFontRole::SansBlack, FVector2D(148.0f, 24.0f));
			}
		}
		DrawBattleOverlay(Geometry, Out, Layer + 6, Presenter);
		// M3: the line sits in the ink battle banner (750,118 420x66); DrawBattle adds the small label under it (keep the two in step).
		if (Controller->GetPhase() == ETreadM1Phase::Battle) DrawEngaged(RefVec(960, 124), 20.0f, 0.5f);
		return;
	}
	// 2D graybox board (M1_Match_Graybox regression baseline): own half in a dark blue tone, enemy half in a dark red tone.
	DrawText(Out, Geometry, Layer + 1, TEXT("巴黎 · 8 × 8  /  蓝色半场可部署"), RefVec(535, 184), 19, TreadUI::PaperL, EFontRole::SansBlack, FVector2D(704.0f, 30.0f), EHudText::Shadow | EHudText::Numbers);
	const FLinearColor OwnCell = TreadUI::WithAlpha(FMath::Lerp(TreadUI::Ink, TreadUI::PlayerInk, 0.55f), 0.92f);
	const FLinearColor EnemyCell = TreadUI::WithAlpha(FMath::Lerp(TreadUI::Ink, TreadUI::RedD, 0.6f), 0.92f);
	for (int32 Y = 0; Y < 8; ++Y)
	for (int32 X = 0; X < 8; ++X)
	{
		FLinearColor Color = Y >= 4 ? OwnCell : EnemyCell;
		if (Drag && Drag->IsDragging() && Drag->GetHoverBoardCell() == FIntPoint(X, Y)) Color = Drag->IsHoverAllowed() ? TreadUI::Player : TreadUI::Red;
		DrawBlock(Out, Geometry, Layer, RefVec(535 + X * 88, 216 + Y * 88), RefVec(85, 85), Color);
	}
	const auto DrawUnit = [&](const FTreadM1UnitInstance& Unit, FIntPoint Cell, bool bHuman)
	{
		if (Cell.X < 0 || Cell.X > 7 || Cell.Y < 0 || Cell.Y > 7) return;
		const float X = 541 + Cell.X * 88; const float Y = 222 + Cell.Y * 88;
		// Own blocks Player (light blue, ink text), enemy blocks Red (PaperL text).
		FLinearColor Tint = bHuman ? TreadUI::Player : TreadUI::Red;
		if (Drag && Drag->IsDragging() && Drag->GetSourceUnitInstanceId() == Unit.UnitInstanceId) Tint.A = 0.35f;
		const FLinearColor TextTone = bHuman ? TreadUI::Ink : TreadUI::PaperL;
		DrawBlock(Out, Geometry, Layer + 1, RefVec(X, Y), RefVec(73, 73), Tint, 2.0f, TreadUI::Ink);
		DrawText(Out, Geometry, Layer + 3, Unit.CharacterId, RefVec(X + 5, Y + 10), 13, TextTone, EFontRole::MonoBold, FVector2D(64.0f, 22.0f));
		DrawText(Out, Geometry, Layer + 3, FString::Printf(TEXT("%s  ★%d"), *Unit.OperatorTier, Unit.UnitStar), RefVec(X + 5, Y + 40), 15, TextTone, EFontRole::MonoBold, FVector2D(64.0f, 24.0f));
	};
	for (const FTreadM1UnitInstance& Unit : P->BoardUnits) DrawUnit(Unit, Unit.BoardCell, true);
	FString OpponentId = TEXT("P1");
	for (const FTreadM1BattlePairing& Pair : Controller->MatchState.LastBattleResult.Pairings)
	{
		if (Pair.PlayerId == P->PlayerId) OpponentId = Pair.OpponentId;
		else if (Pair.OpponentId == P->PlayerId) OpponentId = Pair.PlayerId;
	}
	const FTreadM1PlayerState* Opponent = Controller->MatchState.Players.FindByPredicate([&](const FTreadM1PlayerState& Other) { return Other.PlayerId == OpponentId; });
	if (Opponent)
		for (const FTreadM1UnitInstance& Unit : Opponent->BoardUnits) DrawUnit(Unit, FIntPoint(Unit.BoardCell.X, FMath::Clamp(Unit.BoardCell.Y, 0, 3)), false);
	else if (Controller->GetPhase() == ETreadM1Phase::Battle)
	{
		DrawBlock(Out, Geometry, Layer + 2, RefVec(810, 310), RefVec(160, 90), TreadUI::Red, 2.0f, TreadUI::Ink, 12.0f);
		DrawText(Out, Geometry, Layer + 3, TEXT("演练 / 领袖占位"), RefVec(890, 342), 16, TreadUI::PaperL, EFontRole::SansBlack, FVector2D(150.0f, 26.0f), EHudText::Center);
	}
	if (Controller->GetPhase() == ETreadM1Phase::Battle) DrawEngaged(RefVec(750, 551), 22.0f, 0.0f);
}

void UTreadM1MatchWidget::DrawDrag(const FGeometry& Geometry, FSlateWindowElementList& Out, int32 Layer) const
{
	UTreadDragController* Drag = GetOwningPlayer() ? GetOwningPlayer()->FindComponentByClass<UTreadDragController>() : nullptr;
	if (!Drag || !Drag->IsDragging()) return;
	const FVector2D CursorPosition = Drag->GetCursorReferencePosition();
	// Placeable = player blue, not placeable = red.
	const bool bAllowed = Drag->IsHoverAllowed();
	DrawBlock(Out, Geometry, Layer, RefVec(CursorPosition.X - 48, CursorPosition.Y - 40), RefVec(110, 80), TreadUI::WithAlpha(bAllowed ? TreadUI::Player : TreadUI::Red, 0.82f), 3.0f, TreadUI::Ink, 12.0f);
	DrawText(Out, Geometry, Layer + 1, bAllowed ? FString(TEXT("松手放置")) : FString(TEXT("不可放置")), RefVec(CursorPosition.X + 7, CursorPosition.Y - 14), 16, TreadUI::PaperL,
		EFontRole::SansBlack, FVector2D(2000.0f, 200.0f), EHudText::Center | EHudText::Shadow);
	if (Drag->GetHoverTarget() == ETreadDragTarget::Sell)
	{
		DrawBlock(Out, Geometry, Layer, RefVec(16, 968), RefVec(300, 100), TreadUI::Amber, 3.0f, TreadUI::Ink, 18.0f);
		DrawText(Out, Geometry, Layer + 1, TEXT("松手出售"), RefVec(166, 1001), 22, TreadUI::Ink, EFontRole::SansBlack, FVector2D(2000.0f, 200.0f), EHudText::Center);
	}
}

void UTreadM1MatchWidget::DrawPreparation(const FGeometry& Geometry, FSlateWindowElementList& Out, int32 Layer) const
{
	const FTreadM1PlayerState* P = GetHumanPlayer();
	const FLinearColor InkDim = TreadUI::InkA(0.7f);
	// Shop: the ink bar stops short of the lock button that sits at the panel's top right.
	DrawPaper(Out, Geometry, Layer, RefVec(1592, 108), RefVec(312, 504), true);
	DrawHeader(Out, Geometry, Layer + 2, RefVec(1592, 108), Ref(200), TEXT("商店"), FString());
	if (P) DrawText(Out, Geometry, Layer + 4, FString::Printf(TEXT("¤ %d"), P->Funds), RefVec(1780, 119), 16, TreadUI::Ochre, EFontRole::MonoBold, FVector2D(2000.0f, 200.0f), EHudText::Right);
	if (P)
	{
		for (int32 Index = 0; Index < P->Shop.Slots.Num(); ++Index)
		{
			const FTreadM1ShopSlot& ShopSlot = P->Shop.Slots[Index];
			const float Y = 178 + Index * 74;
			if (ShopSlot.bIsSold)
			{
				DrawInset(Out, Geometry, Layer + 2, RefVec(1604, Y), RefVec(288, 68), TreadUI::PaperDD);
				DrawText(Out, Geometry, Layer + 5, TEXT("已售出"), RefVec(1620, Y + 22), 16, TreadUI::InkA(0.55f), EFontRole::SansBold);
				continue;
			}
			const bool bHovered = ShopButtons.IsValidIndex(Index) && ShopButtons[Index]->IsHovered();
			DrawBlock(Out, Geometry, Layer + 2, RefVec(1604, Y), RefVec(288, 68), TreadUI::Paper, bHovered ? 3.0f : 2.0f, bHovered ? TreadUI::Red : TreadUI::Ink);
			// M4: the avatar (chest-up screenshot of the 3D model) on the left; the tier colour is the fallback frame.
			const bool bAvatar = DrawCharacterImage(Out, Geometry, Layer + 3, ShopSlot.CharacterId, RefVec(1606, Y + 3), RefVec(62, 62), ECharacterImage::Avatar);
			if (!bAvatar) DrawBlock(Out, Geometry, Layer + 3, RefVec(1606, Y + 3), RefVec(62, 62), HudTierColor(ShopSlot.OperatorTier));
			DrawFrame(Out, Geometry, Layer + 4, RefVec(1606, Y + 3), RefVec(62, 62), TreadUI::Ink, 2.0f);
			DrawText(Out, Geometry, Layer + 5, Controller->GetCardDisplayName(ShopSlot.CharacterId), RefVec(1676, Y + 10), 16, TreadUI::Ink, EFontRole::SansBlack, FVector2D(150.0f, 24.0f));
			// Tier numeral in its ink colour at the right edge of the card.
			DrawText(Out, Geometry, Layer + 5, ShopSlot.OperatorTier, RefVec(1882, Y + 5), 22, HudTierColor(ShopSlot.OperatorTier), EFontRole::Stencil, FVector2D(2000.0f, 200.0f), EHudText::Right);
			DrawText(Out, Geometry, Layer + 5, TEXT("阶级"), RefVec(1882, Y + 41), 11, InkDim, EFontRole::Mono, FVector2D(2000.0f, 200.0f), EHudText::Right);
			const FString CostText = FString::Printf(TEXT("¤ %d"), ShopSlot.Cost);
			DrawText(Out, Geometry, Layer + 5, CostText, RefVec(1676, Y + 37), 15, TreadUI::Ochre, EFontRole::MonoBold);
			const float ModelX = 1676.0f + MeasureText(CostText, 15, EFontRole::MonoBold) + 10.0f;
			DrawText(Out, Geometry, Layer + 5, Controller->GetCardModelName(ShopSlot.CharacterId), RefVec(ModelX, Y + 39), 13, InkDim, EFontRole::Mono, FVector2D(FMath::Max(40.0f, 1836.0f - ModelX), 20.0f));
		}
	}
	const bool bFreeRefresh = P && P->FreeRefreshes > 0;
	DrawButton(Out, Geometry, Layer + 2, RefVec(1604, 554), RefVec(138, 46),
		bFreeRefresh ? FString::Printf(TEXT("免费刷新 ×%d"), P->FreeRefreshes) : FString::Printf(TEXT("刷新 ¤%d"), Controller->MatchState.Rules.ShopRefreshCost),
		FString(), EHudButton::Primary, RefreshButton, true, 17.0f);
	FString UpgradeLabel = TEXT("经验 ¤4");
	bool bUpgradeEnabled = true;
	if (Controller->UsesN1Economy())
	{
		const int32 UpgradeCost = P ? Controller->GetShopUpgradeCost(P->PlayerId) : 0;
		bUpgradeEnabled = UpgradeCost > 0;
		UpgradeLabel = bUpgradeEnabled ? FString::Printf(TEXT("升级 ¤%d"), UpgradeCost) : FString(TEXT("已满级"));
	}
	DrawButton(Out, Geometry, Layer + 2, RefVec(1754, 554), RefVec(138, 46), UpgradeLabel, FString(), EHudButton::Primary, ExperienceButton, bUpgradeEnabled, 17.0f);
	const bool bLocked = P && P->Shop.bLocked;
	DrawButton(Out, Geometry, Layer + 2, RefVec(1798, 120), RefVec(94, 42), bLocked ? FString(TEXT("已锁定")) : FString(TEXT("锁店")), FString(), EHudButton::Secondary, LockButton, true, 16.0f);
	if (bLocked) DrawBlock(Out, Geometry, Layer + 5, RefVec(1798, 158), RefVec(66, 4), TreadUI::Ochre);
	if (P)
	{
		// Income breakdown sits on its own panel so it never draws straight over the 3D city.
		DrawPaper(Out, Geometry, Layer + 2, RefVec(1592, 606), RefVec(312, 40), false);
		DrawPaper(Out, Geometry, Layer + 2, RefVec(1252, 650), RefVec(652, 38), false);
		DrawText(Out, Geometry, Layer + 4, Controller->UsesN1Economy()
			? FString::Printf(TEXT("下轮收入：基础 %d + 特质 %d（剩余资金不保留）"), P->NextRoundIncome.Base, P->NextRoundIncome.Other + P->NextRoundIncome.Interest)
			: FString::Printf(TEXT("下轮收入：基础 %d + 利息 %d + 连胜/败 %d + 特质 %d"), P->NextRoundIncome.Base, P->NextRoundIncome.Interest, P->NextRoundIncome.Streak, P->NextRoundIncome.Other),
			RefVec(1272, 656), 17, TreadUI::Ochre, EFontRole::SansBold, FVector2D(620.0f, 28.0f), EHudText::Numbers);
		DrawPacts(Geometry, Out, Layer + 4, FVector2D(16, 196), FVector2D(504, 744), *P, false);
		DrawText(Out, Geometry, Layer + 4, Controller->UsesN1Economy() ? FString::Printf(TEXT("调度中心 Lv %d / 6"), P->Level)
			: FString::Printf(TEXT("经验 %d / %d"), P->Experience, P->ExperienceToNextLevel), RefVec(1612, 613), 17, InkDim, EFontRole::SansMedium, FVector2D(284.0f, 28.0f), EHudText::Numbers);
	}
	DrawPaper(Out, Geometry, Layer, RefVec(16, 968), RefVec(300, 100), false);
	DrawText(Out, Geometry, Layer + 2, TEXT("出售"), RefVec(38, 990), 18, TreadUI::Ink, EFontRole::SansBlack);
	DrawText(Out, Geometry, Layer + 2, TEXT("拖拽单位至此出售"), RefVec(38, 1022), 15, InkDim, EFontRole::SansMedium);
	DrawPaper(Out, Geometry, Layer, RefVec(616, 968), RefVec(884, 100), true);
	// The bench label sits on a small ink tab above its panel: pale text straight over the 3D scene vanished into the white board lines.
	DrawBlock(Out, Geometry, Layer + 2, RefVec(616, 936), RefVec(104, 32), TreadUI::InkA(0.94f), 0.0f, FLinearColor::Black, 8.0f);
	DrawText(Out, Geometry, Layer + 3, TEXT("备战席"), RefVec(632, 941), 16, TreadUI::PaperL, EFontRole::SansBlack);
	if (P)
	{
		for (int32 Index = 0; Index < 8; ++Index)
		{
			const float X = 632 + Index * 108;
			DrawInset(Out, Geometry, Layer + 2, RefVec(X, 978), RefVec(100, 82), TreadUI::PaperDD);
			if (const FTreadM1UnitInstance* BenchUnit = GetBenchUnit(Index))
			{
				const FTreadM1UnitInstance& Unit = *BenchUnit;
				const bool bMarked = PendingBenchIndex == Index || (BenchButtons.IsValidIndex(Index) && BenchButtons[Index]->IsHovered());
				DrawBlock(Out, Geometry, Layer + 4, RefVec(X + 4, 982), RefVec(92, 74), HudTierColor(Unit.OperatorTier), bMarked ? 3.0f : 2.0f, bMarked ? TreadUI::Red : TreadUI::Ink);
				// M4: the avatar fills the card under an ink name band; the tier colour shows as the frame.
				if (DrawCharacterImage(Out, Geometry, Layer + 5, Unit.CharacterId, RefVec(X + 15, 984), RefVec(70, 70), ECharacterImage::Avatar))
					DrawBlock(Out, Geometry, Layer + 6, RefVec(X + 7, 1027), RefVec(86, 26), TreadUI::InkA(0.72f));
				DrawText(Out, Geometry, Layer + 7, Controller->GetCardDisplayName(Unit.CharacterId), RefVec(X + 12, 1030), 13, TreadUI::PaperL, EFontRole::SansBlack, FVector2D(80.0f, 20.0f));
				DrawText(Out, Geometry, Layer + 7, FString::Printf(TEXT("★%d  %s"), Unit.UnitStar, *Unit.OperatorTier), RefVec(X + 10, 987), 12, TreadUI::PaperL, EFontRole::MonoBold, FVector2D(2000.0f, 200.0f), EHudText::Shadow | EHudText::Numbers);
				if (Unit.bIsTransformClone)
				{
					DrawBlock(Out, Geometry, Layer + 8, RefVec(X + 58, 984), RefVec(36, 20), TreadUI::Plum, 2.0f, TreadUI::Ink);
					DrawText(Out, Geometry, Layer + 9, TEXT("复制"), RefVec(X + 76, 985), 12, TreadUI::PaperL, EFontRole::SansBold, FVector2D(2000.0f, 200.0f), EHudText::Center);
				}
			}
		}
	}
	DrawPaper(Out, Geometry, Layer, RefVec(1510, 968), RefVec(386, 100), false);
	DrawText(Out, Geometry, Layer + 2, TEXT("准备完成"), RefVec(1532, 984), 18, TreadUI::PlayerInk, EFontRole::SansBlack);
	DrawText(Out, Geometry, Layer + 2, TEXT("部署后自动进入战斗"), RefVec(1532, 1014), 15, InkDim, EFontRole::SansMedium, FVector2D(182.0f, 24.0f));
	DrawButton(Out, Geometry, Layer + 2, RefVec(1720, 996), RefVec(150, 50), TEXT("部署"), TEXT("В БОЙ"), EHudButton::Primary, DeployButton, true, 20.0f);
	if (P) DrawInventory(Geometry, Out, Layer + 1, *P);
	DrawRewardOffer(Geometry, Out, Layer + 2);
	DrawButton(Out, Geometry, Layer + 2, RefVec(330, 990), RefVec(140, 50), TEXT("名册审核"), FString(), EHudButton::Secondary, RosterButton, true, 17.0f);

	// M4 card tooltip: the hovered shop card or bench unit, unless a drag is in progress.
	UTreadDragController* Drag = GetOwningPlayer() ? GetOwningPlayer()->FindComponentByClass<UTreadDragController>() : nullptr;
	if (P && !(Drag && Drag->IsDragging()))
	{
		for (int32 Index = 0; Index < ShopButtons.Num(); ++Index)
		{
			if ((IsSlotHovered(TEXT("shop"), Index, ShopButtons[Index]) || (ShopAvatarButtons.IsValidIndex(Index) && ShopAvatarButtons[Index]->IsHovered())) && P->Shop.Slots.IsValidIndex(Index) && !P->Shop.Slots[Index].bIsSold)
			{
				DrawCardTooltip(Geometry, Out, Layer + 40, P->Shop.Slots[Index].CharacterId, 1, FVector2D(1180, 120 + Index * 74));
			}
		}
		for (int32 Index = 0; Index < BenchButtons.Num(); ++Index)
		{
			const FTreadM1UnitInstance* BenchUnit = GetBenchUnit(Index);
			if (BenchUnit && IsSlotHovered(TEXT("bench"), Index, BenchButtons[Index]))
			{
				DrawCardTooltip(Geometry, Out, Layer + 40, BenchUnit->CharacterId, BenchUnit->UnitStar, FVector2D(FMath::Min(632.0f + Index * 108, 1500.0f), 520));
			}
		}
	}
}

bool UTreadM1MatchWidget::DrawCharacterImage(FSlateWindowElementList& Out, const FGeometry& Geometry, int32 Layer,
	const FString& CharacterId, const FVector2D& Position, const FVector2D& Size, ECharacterImage Image) const
{
	if (!Controller.IsValid()) return false;
	const bool bAvatar = Image == ECharacterImage::Avatar;
	const FString Path = bAvatar ? Controller->GetCardAvatarPath(CharacterId) : Controller->GetCardPortraitPath(CharacterId);
	if (Path.IsEmpty()) return false;
	const FString Key = FString::Printf(TEXT("%s|%s"), bAvatar ? TEXT("A") : TEXT("P"), *CharacterId);
	TSharedPtr<FSlateBrush>* Found = PortraitBrushes.Find(Key);
	if (!Found)
	{
		UTreadM1MatchWidget* Self = const_cast<UTreadM1MatchWidget*>(this);
		TObjectPtr<UTexture2D>* Cached = Self->PortraitTextures.Find(Key);
		UTexture2D* Texture = Cached ? Cached->Get()
			: LoadObject<UTexture2D>(nullptr, *(Path + TEXT(".") + FPaths::GetBaseFilename(Path)));
		if (!Cached) Self->PortraitTextures.Add(Key, Texture);
		TSharedPtr<FSlateBrush> Brush;
		if (Texture)
		{
			// Both images are drawn whole: the avatar is already a chest-up shot, the portrait is the detail image.
			Brush = MakeShared<FSlateBrush>();
			Brush->SetResourceObject(Texture);
			Brush->ImageSize = FVector2D(Texture->GetSizeX(), Texture->GetSizeY());
			Brush->DrawAs = ESlateBrushDrawType::Image;
		}
		Found = &PortraitBrushes.Add(Key, Brush);
	}
	if (!Found->IsValid()) return false;
	FSlateDrawElement::MakeBox(Out, Layer, Geometry.ToPaintGeometry(FVector2f(Size), FSlateLayoutTransform(FVector2f(Position))), Found->Get(), ESlateDrawEffect::None, FLinearColor::White);
	return true;
}

void UTreadM1MatchWidget::DrawPortraitDetail(const FGeometry& Geometry, FSlateWindowElementList& Out, int32 Layer) const
{
	const FTreadM2Card* Card = Controller.IsValid() ? Controller->FindCardData(DetailCharacterId) : nullptr;
	if (!Card) return;
	// The detail layer: name, the whole PNG portrait (468x702, aspect 2:3) and the close hint.
	DrawPaper(Out, Geometry, Layer, RefVec(700, 110), RefVec(520, 860), true);
	DrawHeader(Out, Geometry, Layer + 2, RefVec(700, 110), Ref(520), Card->ReferenceOperatorName, TEXT("ДОСЬЕ"));
	// Tier chip at the right end of the ink bar.
	DrawBlock(Out, Geometry, Layer + 3, RefVec(1140, 118), RefVec(64, 30), HudTierColor(Card->OperatorTier));
	DrawText(Out, Geometry, Layer + 4, Card->OperatorTier, RefVec(1172, 119), 18, TreadUI::PaperL, EFontRole::Stencil, FVector2D(2000.0f, 200.0f), EHudText::Center);
	if (!DrawCharacterImage(Out, Geometry, Layer + 2, DetailCharacterId, RefVec(726, 164), RefVec(468, 702), ECharacterImage::Portrait))
	{
		DrawBlock(Out, Geometry, Layer + 2, RefVec(726, 164), RefVec(468, 702), HudTierColor(Card->OperatorTier));
		DrawText(Out, Geometry, Layer + 4, TEXT("无立绘"), RefVec(960, 500), 22, TreadUI::PaperL, EFontRole::SansBlack, FVector2D(2000.0f, 200.0f), EHudText::Center);
	}
	DrawFrame(Out, Geometry, Layer + 3, RefVec(726, 164), RefVec(468, 702), TreadUI::Ink, 3.0f);
	DrawText(Out, Geometry, Layer + 4, FString::Printf(TEXT("模型：%s    长按立绘或头像关闭"), *Card->ModelName), RefVec(726, 884), 15, TreadUI::InkA(0.7f), EFontRole::Mono, FVector2D(468.0f, 24.0f));
}

void UTreadM1MatchWidget::DrawCardTooltip(const FGeometry& Geometry, FSlateWindowElementList& Out, int32 Layer,
	const FString& CharacterId, int32 UnitStar, const FVector2D& Anchor) const
{
	const FTreadM2Card* Card = Controller.IsValid() ? Controller->FindCardData(CharacterId) : nullptr;
	if (!Card) return;
	const FLinearColor InkDim = TreadUI::InkA(0.7f);
	const FVector2D Origin(FMath::Clamp(Anchor.X, 8.0, 1920.0 - 412.0), FMath::Clamp(Anchor.Y, 100.0, 1080.0 - 462.0));
	const bool bElite = UnitStar >= 2;
	DrawPaper(Out, Geometry, Layer, RefVec(Origin.X, Origin.Y), RefVec(404, 456), true);
	DrawBlock(Out, Geometry, Layer + 2, RefVec(Origin.X + 18, Origin.Y + 3), RefVec(383, 5), HudTierColor(Card->OperatorTier));
	if (!DrawCharacterImage(Out, Geometry, Layer + 2, CharacterId, RefVec(Origin.X + 12, Origin.Y + 14), RefVec(140, 140), ECharacterImage::Avatar))
	{
		DrawBlock(Out, Geometry, Layer + 2, RefVec(Origin.X + 12, Origin.Y + 14), RefVec(140, 140), HudTierColor(Card->OperatorTier));
		DrawText(Out, Geometry, Layer + 4, TEXT("无头像"), RefVec(Origin.X + 82, Origin.Y + 70), 15, TreadUI::PaperL, EFontRole::SansBlack, FVector2D(2000.0f, 200.0f), EHudText::Center);
	}
	DrawFrame(Out, Geometry, Layer + 3, RefVec(Origin.X + 12, Origin.Y + 14), RefVec(140, 140), TreadUI::Ink, 2.0f);
	DrawDivider(Out, Geometry, Layer + 2, RefVec(Origin.X + 12, Origin.Y + 426), RefVec(380, 1), TreadUI::InkA(0.25f));
	DrawText(Out, Geometry, Layer + 4, bElite ? TEXT("精英化 · 点击头像查看立绘") : TEXT("点击头像查看立绘"), RefVec(Origin.X + 14, Origin.Y + 430), 13,
		bElite ? TreadUI::Ochre : InkDim, bElite ? EFontRole::SansBold : EFontRole::SansMedium, FVector2D(380.0f, 22.0f));
	const float X = Origin.X + 166;
	float Y = Origin.Y + 16;
	DrawText(Out, Geometry, Layer + 4, Card->ReferenceOperatorName, RefVec(X, Y), 22, TreadUI::Ink, EFontRole::SansBlack, FVector2D(230.0f, 30.0f)); Y += 34;
	DrawText(Out, Geometry, Layer + 4, FString::Printf(TEXT("模型：%s"), *Card->ModelName), RefVec(X, Y), 14, InkDim, EFontRole::Mono, FVector2D(230.0f, 22.0f)); Y += 24;
	DrawRuns(Out, Geometry, Layer + 4, LayoutScale, RefVec(X, Y), {
		{ FString(TEXT("阶级 ")), EFontRole::SansMedium, InkDim, 14.0f },
		{ Card->OperatorTier, EFontRole::Stencil, HudTierColor(Card->OperatorTier), 16.0f },
		{ FString::Printf(TEXT("  ·  ¤%d  ·  ★%d"), Card->Price, UnitStar), EFontRole::MonoBold, TreadUI::Ochre, 14.0f } }, 0.0f, false); Y += 24;
	DrawText(Out, Geometry, Layer + 4, FString::Printf(TEXT("盟约：%s"), *JoinOr(Card->CorePacts, TEXT("、"), TEXT("—"))), RefVec(X, Y), 14, TreadUI::Ink, EFontRole::SansMedium, FVector2D(230.0f, 22.0f)); Y += 22;
	DrawText(Out, Geometry, Layer + 4, FString::Printf(TEXT("加盟约：%s"), *JoinOr(Card->AdjunctPacts, TEXT("、"), TEXT("—"))), RefVec(X, Y), 14, TreadUI::Ink, EFontRole::SansMedium, FVector2D(230.0f, 22.0f)); Y += 22;
	DrawText(Out, Geometry, Layer + 4, FString::Printf(TEXT("职业：%s · %s"), *Card->Profession, *Card->SubProfession), RefVec(X, Y), 14, InkDim, EFontRole::SansMedium, FVector2D(230.0f, 22.0f)); Y += 22;
	DrawText(Out, Geometry, Layer + 4, FString::Printf(TEXT("%s · 技能 %s"), Card->AttackKind == TEXT("ranged") ? TEXT("远程") : TEXT("近战"), *Card->SkillName), RefVec(X, Y), 14, InkDim, EFontRole::SansMedium, FVector2D(230.0f, 22.0f)); Y += 22;
	const FTreadM4OperatorStats& Stats = bElite ? Card->EliteStats : Card->Stats;
	DrawText(Out, Geometry, Layer + 4, FString::Printf(TEXT("生命 %d  攻击 %d"), Stats.MaxHp, Stats.Atk), RefVec(X, Y), 14, InkDim, EFontRole::SansMedium, FVector2D(230.0f, 22.0f), EHudText::Numbers); Y += 20;
	DrawText(Out, Geometry, Layer + 4, FString::Printf(TEXT("防御 %d  法抗 %d"), Stats.Def, Stats.Res), RefVec(X, Y), 14, InkDim, EFontRole::SansMedium, FVector2D(230.0f, 22.0f), EHudText::Numbers);
	Y = Origin.Y + 236;
	DrawDivider(Out, Geometry, Layer + 2, RefVec(Origin.X + 12, Y), RefVec(380, 1), TreadUI::InkA(0.35f));
	Y += 8;
	for (const FTreadM2Trait& Trait : Card->Traits)
	{
		for (const FString& Line : WrapText(bElite && !Trait.EliteDisplayText.IsEmpty() ? Trait.EliteDisplayText : Trait.DisplayText, 14, EFontRole::SansMedium, 376, 4, EHudText::Numbers))
		{
			if (Y > Origin.Y + 404) break;
			DrawText(Out, Geometry, Layer + 4, Line, RefVec(Origin.X + 14, Y), 14, TreadUI::Ink, EFontRole::SansMedium, FVector2D(380.0f, 22.0f), EHudText::Numbers);
			Y += 21;
		}
		Y += 4;
	}
}

void UTreadM1MatchWidget::DrawRewardOffer(const FGeometry& Geometry, FSlateWindowElementList& Out, int32 Layer) const
{
	const FTreadM1PlayerState* P = GetHumanPlayer();
	if (!P || P->RewardOffer.Num() == 0 || P->bRewardClaimed) return;
	const int32 Count = FMath::Min(3, P->RewardOffer.Num());
	const float StripW = 32.0f + Count * 188.0f;
	const float X0 = 960.0f - StripW * 0.5f;
	DrawPaper(Out, Geometry, Layer, RefVec(X0, 94), RefVec(StripW, 118), false);
	DrawBlock(Out, Geometry, Layer + 1, RefVec(X0 + 12, 100), RefVec(6, 18), TreadUI::Red);
	DrawText(Out, Geometry, Layer + 2, TEXT("战术补给 // 三选一 · 免费"), RefVec(X0 + 26, 98), 15, TreadUI::Ink, EFontRole::SansBlack);
	for (int32 Index = 0; Index < Count; ++Index)
	{
		const FString& ItemId = P->RewardOffer[Index];
		const FTreadM2Item* Item = Controller.IsValid() ? Controller->FindItemData(ItemId) : nullptr;
		const float X = X0 + 20.0f + Index * 188.0f;
		const bool bHovered = RewardButtons.IsValidIndex(Index) && RewardButtons[Index]->IsHovered();
		DrawBlock(Out, Geometry, Layer + 2, RefVec(X, 126), RefVec(176, 78), TreadUI::Paper,
			bHovered ? 3.0f : 2.0f, bHovered ? TreadUI::Red : TreadUI::Ink);
		DrawText(Out, Geometry, Layer + 4, Item ? Item->DisplayName : ItemId, RefVec(X + 10, 131), 14, TreadUI::Ink,
			EFontRole::SansBlack, FVector2D(126.0f, 20.0f));
		DrawText(Out, Geometry, Layer + 4, Item ? FString::Printf(TEXT("T%d"), Item->Tier) : FString(),
			RefVec(X + 150, 131), 13, TreadUI::Ochre, EFontRole::MonoBold);
		DrawText(Out, Geometry, Layer + 4, Item ? Item->EffectText : FString(), RefVec(X + 10, 153), 11,
			TreadUI::InkA(0.75f), EFontRole::SansMedium, FVector2D(158.0f, 30.0f));
		DrawText(Out, Geometry, Layer + 4, TEXT("领取 ›"), RefVec(X + 128, 181), 12, TreadUI::Red, EFontRole::SansBold);
	}
}

void UTreadM1MatchWidget::DrawInventory(const FGeometry& Geometry, FSlateWindowElementList& Out, int32 Layer, const FTreadM1PlayerState& P) const
{
	const FLinearColor InkDim = TreadUI::InkA(0.7f);
	DrawPaper(Out, Geometry, Layer, RefVec(1252, 696), RefVec(652, 140), true);
	DrawHeader(Out, Geometry, Layer + 2, RefVec(1252, 696), Ref(652), FString::Printf(TEXT("装备库存 %d"), P.EquipmentIds.Num()), FString());
	DrawText(Out, Geometry, Layer + 4, TEXT("点选装备，再点备战席单位装备"), RefVec(1440, 709), 13, TreadUI::PaperLA(0.75f), EFontRole::Mono, FVector2D(330.0f, 22.0f));
	const FTreadM2Item* Hovered = nullptr;
	for (int32 Index = 0; Index < InventorySlots && Index < P.EquipmentIds.Num(); ++Index)
	{
		const FTreadM2Item* Item = Controller->FindItemData(P.EquipmentIds[Index]);
		const float X = 1264 + (Index % 4) * 158;
		const float Y = 742 + (Index / 4) * 44;
		const bool bSelected = PendingItemIndex == Index;
		const bool bHovering = ItemButtons.IsValidIndex(Index) && ItemButtons[Index]->IsHovered();
		// Support state colours the left edge: applied = player blue, partial = amber, anything else = ink.
		const FLinearColor Edge = !Item ? TreadUI::InkA(0.3f) : Item->RuntimeSupport == TEXT("applied") ? TreadUI::PlayerInk
			: Item->RuntimeSupport == TEXT("partial") ? TreadUI::Amber : TreadUI::InkA(0.55f);
		DrawBlock(Out, Geometry, Layer + 2, RefVec(X, Y), RefVec(150, 38), bSelected ? TreadUI::PlayerInk : TreadUI::Paper, bHovering && !bSelected ? 3.0f : 2.0f, bHovering && !bSelected ? TreadUI::Red : TreadUI::Ink);
		DrawBlock(Out, Geometry, Layer + 3, RefVec(X + 2, Y + 2), RefVec(5, 34), Edge);
		DrawText(Out, Geometry, Layer + 5, Item ? Item->DisplayName : P.EquipmentIds[Index], RefVec(X + 14, Y + 8), 14, bSelected ? TreadUI::PaperL : TreadUI::Ink, EFontRole::SansBold, FVector2D(130.0f, 22.0f));
		if (IsSlotHovered(TEXT("item"), Index, ItemButtons.IsValidIndex(Index) ? ItemButtons[Index] : nullptr)) Hovered = Item;
	}
	if (P.EquipmentIds.Num() > InventorySlots)
		DrawText(Out, Geometry, Layer + 4, FString::Printf(TEXT("…另有 %d 件"), P.EquipmentIds.Num() - InventorySlots), RefVec(1800, 709), 13, TreadUI::PaperLA(0.75f), EFontRole::Mono, FVector2D(96.0f, 22.0f), EHudText::Numbers);
	if (Hovered)
	{
		const FString Support = Hovered->RuntimeSupport == TEXT("applied") ? TEXT("已生效 ✓")
			: Hovered->RuntimeSupport == TEXT("partial") ? TEXT("部分生效") : Hovered->RuntimeSupport.IsEmpty() ? TEXT("仅盟约") : TEXT("暂未实现");
		const FLinearColor SupportTone = Hovered->RuntimeSupport == TEXT("applied") ? TreadUI::PlayerInk
			: Hovered->RuntimeSupport == TEXT("partial") ? TreadUI::Amber : TreadUI::InkA(0.55f);
		DrawPaper(Out, Geometry, Layer + 20, RefVec(1252, 470), RefVec(652, 220), true);
		DrawHeader(Out, Geometry, Layer + 22, RefVec(1252, 470), Ref(652), Hovered->DisplayName, FString());
		DrawBlock(Out, Geometry, Layer + 23, RefVec(1790, 480), RefVec(100, 26), SupportTone);
		DrawText(Out, Geometry, Layer + 24, Support, RefVec(1840, 483), 14, TreadUI::PaperL, EFontRole::SansBold, FVector2D(2000.0f, 200.0f), EHudText::Center);
		float Y = 524;
		for (const FString& Line : WrapText(Hovered->EffectText, 14, EFontRole::SansMedium, 612, 3, EHudText::Numbers)) { DrawText(Out, Geometry, Layer + 24, Line, RefVec(1270, Y), 14, TreadUI::Ink, EFontRole::SansMedium, FVector2D(620.0f, 22.0f), EHudText::Numbers); Y += 21; }
		if (!Hovered->bElite && !Hovered->EliteEffectText.IsEmpty() && Hovered->EliteEffectText != Hovered->EffectText)
		{
			for (const FString& Line : WrapText(TEXT("Ⅱ：") + Hovered->EliteEffectText, 14, EFontRole::SansBold, 612, 2, EHudText::Numbers)) { DrawText(Out, Geometry, Layer + 24, Line, RefVec(1270, Y), 14, TreadUI::Ochre, EFontRole::SansBold, FVector2D(620.0f, 22.0f), EHudText::Numbers); Y += 21; }
		}
		DrawText(Out, Geometry, Layer + 24, FString::Printf(TEXT("盟约：%s"), *JoinOr(Hovered->ProvidesPacts, TEXT("、"), TEXT("—"))), RefVec(1270, Y + 4), 14, InkDim, EFontRole::SansMedium, FVector2D(620.0f, 22.0f));
		if (Hovered->RuntimeSupport != TEXT("applied") && !Hovered->SupportNote.IsEmpty())
			DrawText(Out, Geometry, Layer + 24, Hovered->SupportNote, RefVec(1270, Y + 28), 12, InkDim, EFontRole::Mono, FVector2D(620.0f, 20.0f));
	}
}

void UTreadM1MatchWidget::DrawRoster(const FGeometry& Geometry, FSlateWindowElementList& Out, int32 Layer) const
{
	const FLinearColor InkDim = TreadUI::InkA(0.7f);
	const TArray<FString> Ids = Controller->GetRosterCharacterIds();
	const int32 Pages = FMath::Max(1, FMath::DivideAndRoundUp(Ids.Num(), RosterPerPage));
	const int32 Page = FMath::Clamp(RosterPage, 0, Pages - 1);
	DrawScrim(Out, Geometry, Layer);
	DrawPaper(Out, Geometry, Layer + 1, RefVec(110, 110), RefVec(1700, 870), true);
	// The ink bar stops before the three page buttons that sit at the panel's top right.
	DrawHeader(Out, Geometry, Layer + 3, RefVec(110, 110), Ref(1282), TEXT("名册审核"), TEXT("РЕЕСТР"));
	DrawText(Out, Geometry, Layer + 5, FString::Printf(TEXT("%d 卡 · 第 %d / %d 页"), Ids.Num(), Page + 1, Pages), RefVec(1380, 121), 16, TreadUI::PaperL, EFontRole::SansBold, FVector2D(2000.0f, 200.0f), EHudText::Right | EHudText::Numbers);
	DrawText(Out, Geometry, Layer + 5, TEXT("原版干员名 / UE 模型名 / 阶级 · 价格 · 卡池 / 职业 / 盟约 / 加盟约 / 语音"), RefVec(140, 159), 14, InkDim, EFontRole::Mono, FVector2D(1230.0f, 24.0f));
	DrawButton(Out, Geometry, Layer + 2, RefVec(1404, 126), RefVec(120, 42), TEXT("上一页"), FString(), EHudButton::Secondary, RosterPrevButton, true, 18.0f);
	DrawButton(Out, Geometry, Layer + 2, RefVec(1534, 126), RefVec(120, 42), TEXT("下一页"), FString(), EHudButton::Secondary, RosterNextButton, true, 18.0f);
	DrawButton(Out, Geometry, Layer + 2, RefVec(1664, 126), RefVec(110, 42), TEXT("关闭"), FString(), EHudButton::Primary, RosterCloseButton, true, 18.0f);
	for (int32 Cell = 0; Cell < RosterPerPage; ++Cell)
	{
		const int32 Index = Page * RosterPerPage + Cell;
		if (!Ids.IsValidIndex(Index)) break;
		const FTreadM2Card* Card = Controller->FindCardData(Ids[Index]);
		if (!Card) continue;
		const float X = 130 + (Cell % 8) * 208;
		const float Y = 184 + (Cell / 8) * 196;
		DrawBlock(Out, Geometry, Layer + 2, RefVec(X, Y), RefVec(200, 188), TreadUI::Paper, 2.0f, TreadUI::Ink, 10.0f);
		DrawBlock(Out, Geometry, Layer + 3, RefVec(X + 12, Y + 2), RefVec(186, 5), HudTierColor(Card->OperatorTier));
		if (!DrawCharacterImage(Out, Geometry, Layer + 3, Card->CharacterId, RefVec(X + 5, Y + 14), RefVec(74, 74), ECharacterImage::Avatar))
		{
			DrawBlock(Out, Geometry, Layer + 3, RefVec(X + 5, Y + 14), RefVec(74, 74), HudTierColor(Card->OperatorTier));
			DrawText(Out, Geometry, Layer + 5, TEXT("无头像"), RefVec(X + 42, Y + 40), 14, TreadUI::PaperL, EFontRole::SansBlack, FVector2D(2000.0f, 200.0f), EHudText::Center);
		}
		DrawFrame(Out, Geometry, Layer + 4, RefVec(X + 5, Y + 14), RefVec(74, 74), TreadUI::Ink, 2.0f);
		DrawText(Out, Geometry, Layer + 5, Card->ReferenceOperatorName, RefVec(X + 86, Y + 10), 15, TreadUI::Ink, EFontRole::SansBlack, FVector2D(108.0f, 22.0f));
		DrawText(Out, Geometry, Layer + 5, Card->ModelName, RefVec(X + 86, Y + 33), 12, InkDim, EFontRole::Mono, FVector2D(108.0f, 18.0f));
		DrawRuns(Out, Geometry, Layer + 5, LayoutScale, RefVec(X + 86, Y + 52), {
			{ Card->OperatorTier, EFontRole::Stencil, HudTierColor(Card->OperatorTier), 14.0f },
			{ FString::Printf(TEXT("  ¤%d ×%d"), Card->Price, Card->PoolCopies), EFontRole::MonoBold, TreadUI::Ochre, 11.0f } }, 0.0f, false);
		DrawText(Out, Geometry, Layer + 5, Card->Profession, RefVec(X + 86, Y + 74), 12, InkDim, EFontRole::Mono, FVector2D(108.0f, 18.0f));
		DrawText(Out, Geometry, Layer + 5, JoinOr(Card->CorePacts, TEXT("、"), TEXT("—")), RefVec(X + 8, Y + 108), 12, TreadUI::Ink, EFontRole::SansMedium, FVector2D(184.0f, 20.0f));
		DrawText(Out, Geometry, Layer + 5, JoinOr(Card->AdjunctPacts, TEXT("、"), TEXT("—")), RefVec(X + 8, Y + 128), 12, InkDim, EFontRole::SansMedium, FVector2D(184.0f, 20.0f));
		DrawText(Out, Geometry, Layer + 5, FString::Printf(TEXT("%s · %s · 语音 %d"), *Card->CharacterId, *Card->ModelSet, Card->VoiceAssets.Num()), RefVec(X + 8, Y + 158), 11, TreadUI::InkA(0.55f), EFontRole::Mono, FVector2D(184.0f, 18.0f));
	}
}

void UTreadM1MatchWidget::DrawSquadPanel(const FGeometry& Geometry, FSlateWindowElementList& Out, int32 Layer) const
{
	const FTreadM1PlayerState* Human = GetHumanPlayer();
	if (!Human || Human->BoardUnits.Num() == 0) return;
	// The shop owns this corner during preparation; the squad bars matter while the fight is running.
	if (Controller->GetPhase() == ETreadM1Phase::Preparation) return;

	const int32 Rows = FMath::Min(Human->BoardUnits.Num(), 6);
	const float PanelX = 1310.0f;
	const float PanelY = 470.0f;
	const float PanelW = 300.0f;
	const float RowH = 58.0f;
	const float PanelH = 44.0f + Rows * RowH;

	DrawPaper(Out, Geometry, Layer, RefVec(PanelX, PanelY), RefVec(PanelW, bSquadPanelCollapsed ? 48.0f : PanelH), true);
	DrawHeader(Out, Geometry, Layer + 2, RefVec(PanelX, PanelY), Ref(PanelW), TEXT("小队"), TEXT("SQUAD // 技力"));
	DrawButton(Out, Geometry, Layer + 6, RefVec(PanelX + PanelW - 28.0f, PanelY + 8.0f), RefVec(22.0f, 22.0f),
		bSquadPanelCollapsed ? FString(TEXT("＋")) : FString(TEXT("－")), FString(), EHudButton::Secondary, SquadZoomButton, true, 14.0f);
	if (bSquadPanelCollapsed) return;

	for (int32 Index = 0; Index < Rows; ++Index)
	{
		const FTreadM1UnitInstance& Unit = Human->BoardUnits[Index];
		const float RowY = PanelY + 40.0f + Index * RowH;
		const FVector2D PortraitPos = RefVec(PanelX + 10.0f, RowY);
		const FVector2D PortraitSize = RefVec(46.0f, 46.0f);
		if (!DrawCharacterImage(Out, Geometry, Layer + 3, Unit.CharacterId, PortraitPos, PortraitSize, ECharacterImage::Avatar))
		{
			TreadUI::Quad(Out, Geometry, Layer + 3, FVector2f(PortraitPos), FVector2f(PortraitSize), TreadUI::Ink2);
		}

		const float BarX = PanelX + 64.0f;
		const float BarW = PanelW - 76.0f;
		// Before the battle is simulated there is no health data; show a full bar instead of an empty one.
		float HpFraction = Controller->GetUnitHealthFraction(Human->PlayerId, Unit.UnitInstanceId);
		if (HpFraction <= 0.0f) HpFraction = 1.0f;
		const float SpFraction = Controller->GetUnitSpFraction(Human->PlayerId, Unit.UnitInstanceId);

		DrawText(Out, Geometry, Layer + 3, FString::Printf(TEXT("%s  ★%d"), *Controller->GetCardDisplayName(Unit.CharacterId), Unit.UnitStar),
			RefVec(BarX, RowY + 1.0f), 12, TreadUI::Ink, EFontRole::SansBlack, FVector2D(BarW, 16.0f));

		// health: player blue
		TreadUI::Quad(Out, Geometry, Layer + 3, FVector2f(RefVec(BarX, RowY + 20.0f)), FVector2f(RefVec(BarW, 9.0f)), TreadUI::Ink2);
		TreadUI::Quad(Out, Geometry, Layer + 4, FVector2f(RefVec(BarX, RowY + 20.0f)),
			FVector2f(RefVec(BarW * FMath::Clamp(HpFraction, 0.0f, 1.0f), 9.0f)), TreadUI::PlayerInk);

		// 技力: green, drawn under the health bar so it reads as a second track
		TreadUI::Quad(Out, Geometry, Layer + 3, FVector2f(RefVec(BarX, RowY + 33.0f)), FVector2f(RefVec(BarW, 7.0f)), TreadUI::Ink2);
		TreadUI::Quad(Out, Geometry, Layer + 4, FVector2f(RefVec(BarX, RowY + 33.0f)),
			FVector2f(RefVec(BarW * FMath::Clamp(SpFraction, 0.0f, 1.0f), 7.0f)), FLinearColor(0.2f, 0.86f, 0.4f, 1.0f));

		// Numeric 技力 readout (document/169): right-aligned on the name line, green like the bar.
		DrawText(Out, Geometry, Layer + 4,
			FString::Printf(TEXT("技力 %d"), FMath::RoundToInt(SpFraction * 100.0f)),
			RefVec(BarX + BarW - 62.0f, RowY + 1.0f), 11, FLinearColor(0.2f, 0.86f, 0.4f, 1.0f),
			EFontRole::Mono, FVector2D(62.0f, 15.0f));

		const int32 Ammo = Controller->GetUnitAmmo(Human->PlayerId, Unit.UnitInstanceId);
		if (Ammo > 0)
		{
			DrawText(Out, Geometry, Layer + 4, FString::Printf(TEXT("弹药 %d"), Ammo),
				RefVec(BarX + BarW - 52.0f, RowY + 20.0f), 10, TreadUI::Amber, EFontRole::Mono, FVector2D(60.0f, 14.0f));
		}
	}
}

void UTreadM1MatchWidget::DrawBattle(const FGeometry& Geometry, FSlateWindowElementList& Out, int32 Layer) const
{
	const FLinearColor InkDim = TreadUI::InkA(0.7f);
	DrawPaper(Out, Geometry, Layer, RefVec(16, 196), RefVec(320, 340), true);
	DrawButton(Out, Geometry, Layer + 6, RefVec(310, 204), RefVec(22, 22),
		bBattlePanelCollapsed ? FString(TEXT("＋")) : FString(TEXT("－")), FString(), EHudButton::Secondary, BattleZoomButton, true, 14.0f);
	if (bBattlePanelCollapsed) return;
	DrawHeader(Out, Geometry, Layer + 2, RefVec(16, 196), Ref(320), TEXT("对阵"), TEXT("ПРОТИВНИК"));
	const TArray<FTreadM1BattlePairing>& Pairings = Controller->MatchState.LastBattleResult.Pairings;
	if (Pairings.Num() > 0)
	{
		// The list is in match order, not "mine first": take the pairing the human plays in (as player or as opponent), and fall back to
		// the first one when the human is in none. Colour follows who is human, never the position: the human is player blue, anyone else red.
		const FTreadM1PlayerState* Human = GetHumanPlayer();
		const FString HumanId = Human ? Human->PlayerId : FString();
		const FTreadM1BattlePairing* HumanPairing = HumanId.IsEmpty() ? nullptr
			: Pairings.FindByPredicate([&HumanId](const FTreadM1BattlePairing& Pair) { return Pair.PlayerId == HumanId || Pair.OpponentId == HumanId; });
		const FTreadM1BattlePairing& Pairing = HumanPairing ? *HumanPairing : Pairings[0];
		const bool bHumanListedSecond = HumanPairing && Pairing.OpponentId == HumanId && Pairing.PlayerId != HumanId;
		const FString& FirstId = bHumanListedSecond ? Pairing.OpponentId : Pairing.PlayerId;
		const FString& SecondId = bHumanListedSecond ? Pairing.PlayerId : Pairing.OpponentId;
		const auto SideColor = [&HumanId](const FString& Id) -> FLinearColor { return !HumanId.IsEmpty() && Id == HumanId ? TreadUI::PlayerInk : TreadUI::Red; };
		const FString& ScriptedName = Controller->MatchState.ScriptedOpponentName;
		DrawRuns(Out, Geometry, Layer + 4, LayoutScale, RefVec(36, 264), {
			{ FirstId, EFontRole::Stencil, SideColor(FirstId), 24.0f },
			{ FString(TEXT("  VS  ")), EFontRole::Russo, InkDim, 15.0f },
			{ ScriptedName.IsEmpty() ? SecondId : FString(TEXT("守军/领袖")), EFontRole::Stencil, ScriptedName.IsEmpty() ? SideColor(SecondId) : TreadUI::Red, 24.0f } }, 0.0f, false);
		if (!ScriptedName.IsEmpty())
		{
			DrawText(Out, Geometry, Layer + 4, ScriptedName, RefVec(36, 297), 15, TreadUI::Amber, EFontRole::SansBlack, FVector2D(284.0f, 22.0f));
			if (Controller->MatchState.ScriptedOpponentMaxHealth > 0)
				DrawText(Out, Geometry, Layer + 4, FString::Printf(TEXT("领袖生命 %d / %d"), Controller->MatchState.ScriptedOpponentHealth, Controller->MatchState.ScriptedOpponentMaxHealth), RefVec(36, 380), 16, TreadUI::Red, EFontRole::SansBlack, FVector2D(284.0f, 26.0f), EHudText::Numbers);
		}
	}
	DrawText(Out, Geometry, Layer + 4, TEXT("自动寻敌 · 目标切换事件流"), RefVec(36, 322), 16, InkDim, EFontRole::Mono, FVector2D(284.0f, 26.0f));
	DrawText(Out, Geometry, Layer + 4, FString::Printf(TEXT("BattleEvent  %d"), Controller->MatchState.BattleEvents.Num()), RefVec(36, 356), 16, InkDim, EFontRole::Mono, FVector2D(284.0f, 26.0f), EHudText::Numbers);
	DrawPaper(Out, Geometry, Layer, RefVec(1560, 168), RefVec(344, 260), true);
	DrawHeader(Out, Geometry, Layer + 2, RefVec(1560, 168), Ref(344), TEXT("击杀播报 / 伤害事件"), FString());
	DrawButton(Out, Geometry, Layer + 6, RefVec(1878, 176), RefVec(22, 22),
		bFeedPanelCollapsed ? FString(TEXT("＋")) : FString(TEXT("－")), FString(), EHudButton::Secondary, FeedZoomButton, true, 14.0f);
	if (bFeedPanelCollapsed)
	{
		if (ATreadM3BoardPresenter* FeedPresenter = FindBoardPresenter())
		{
			DrawButton(Out, Geometry, Layer + 2, RefVec(1560, 440), RefVec(344, 56),
				FeedPresenter->IsAudienceCamera() ? FString(TEXT("● 切回俯视镜头")) : FString(TEXT("切换观众镜头")), FString(),
				EHudButton::Secondary, AudienceButton, true, 20.0f);
		}
		return;
	}
	ATreadM3BoardPresenter* Presenter = FindBoardPresenter();
	if (Presenter)
	{
		DrawButton(Out, Geometry, Layer + 2, RefVec(1560, 440), RefVec(344, 56),
			Presenter->IsAudienceCamera() ? FString(TEXT("● 切回俯视镜头")) : FString(TEXT("切换观众镜头")), FString(), EHudButton::Secondary, AudienceButton, true, 20.0f);
	}
	// While the 3D replay runs the result is not spoiled: the board shows the fight, the feed waits for Settlement.
	const bool bReplaying = Presenter && Controller->MatchState.bBattleAwaitingPresentation;
	if (bReplaying) DrawText(Out, Geometry, Layer + 4, TEXT("战况见棋盘 · 结算后显示明细"), RefVec(1582, 240), 15, InkDim, EFontRole::SansMedium, FVector2D(300.0f, 24.0f));
	for (int32 Index = bReplaying ? Controller->MatchState.BattleEvents.Num() : FMath::Max(0, Controller->MatchState.BattleEvents.Num() - 4); Index < Controller->MatchState.BattleEvents.Num(); ++Index)
	{
		const FTreadM1BattleEvent& Event = Controller->MatchState.BattleEvents[Index];
		DrawText(Out, Geometry, Layer + 4, FString::Printf(TEXT("%s → %s  -%d"), *Event.SourcePlayerId, *Event.TargetPlayerId, Event.Amount), RefVec(1582, 232 + (Index % 4) * 38), 15, TreadUI::Red, EFontRole::Mono, FVector2D(300.0f, 24.0f), EHudText::Numbers);
	}
	if (const FTreadM1PlayerState* P = GetHumanPlayer()) DrawPacts(Geometry, Out, Layer + 4, FVector2D(16, 548), FVector2D(504, 416), *P, true);
	// Battle banner 750,118 420x66. Vertical rhythm (design px): ~10 above the ideographs (ink 128..154), ~8 between them and the
	// caps of the subtitle (162..174), ~10 below it. The ideograph line is drawn by DrawEngaged at y 124 (DrawBoard); the subtitle
	// line box starts at y 158. The old 54 px bar left 2.6 px between the two lines and 5.7 px under the subtitle.
	TreadUI::InkPanel(Out, Geometry, Layer + 1, TreadUI::V2(RefVec(750, 118)), TreadUI::V2(RefVec(420, 66)), LayoutScale);
	DrawText(Out, Geometry, Layer + 3, TEXT("AUTO BATTLE  ·  TARGETING ACTIVE"), RefVec(960, 158), 12, TreadUI::PaperLA(0.7f), EFontRole::Mono, FVector2D(2000.0f, 200.0f), EHudText::Center);
}

int32 UTreadM1MatchWidget::ShownHealth(const FTreadM1PlayerState& Who) const
{
	if (Controller.IsValid() && Controller->MatchState.bBattleAwaitingPresentation)
	{
		for (const FTreadM1BattleOutcome& Outcome : Controller->MatchState.LastBattleResult.Outcomes)
		{
			if (Outcome.PlayerId == Who.PlayerId) return Outcome.HealthBefore;
		}
	}
	return Who.Health;
}

void UTreadM1MatchWidget::DrawBattleOverlay(const FGeometry& Geometry, FSlateWindowElementList& Out, int32 Layer, ATreadM3BoardPresenter* Presenter) const
{
	// document/12 §6: damage / status numbers rise and fade above the units; the per-event colour stays, the ink shadow keeps it legible.
	APlayerController* PC = GetOwningPlayer();
	if (!Presenter || !PC) return;
	TArray<FTreadM3Floater> Floaters;
	Presenter->GetFloaters(Floaters);
	for (const FTreadM3Floater& F : Floaters)
	{
		FVector2D Screen;
		if (!UGameplayStatics::ProjectWorldToScreen(PC, F.World, Screen, true)) continue;
		const FVector2D Local = ScreenToDesign(Geometry, Screen);
		FLinearColor Color = F.Color;
		Color.A = 1.0f - FMath::Max(0.0f, F.Age01 - 0.6f) / 0.4f;
		const int32 Size = F.bBig ? 28 : 21;
		DrawText(Out, Geometry, Layer + 1, F.Text, RefVec(Local.X - 28, Local.Y - 70), Size, Color, EFontRole::SansBlack, FVector2D(2000.0f, 200.0f), EHudText::Shadow | EHudText::Numbers);
	}
}

void UTreadM1MatchWidget::DrawResult(const FGeometry& Geometry, FSlateWindowElementList& Out, int32 Layer) const
{
	const bool bGameOver = Controller->GetPhase() == ETreadM1Phase::GameOver;
	if (bGameOver && Controller->MatchState.CampaignResult == TEXT("WorldDomination"))
	{
		DrawWorldDomination(Geometry, Out, Layer);
		return;
	}
	const FLinearColor InkDim = TreadUI::InkA(0.7f);
	DrawScrim(Out, Geometry, Layer);
	// The panel wraps the continue button (hit area x 1220..1640, y 900..964); ruler and rows widen to match.
	DrawPaper(Out, Geometry, Layer + 1, RefVec(440, 210), RefVec(1240, 790), true);
	DrawHeader(Out, Geometry, Layer + 3, RefVec(440, 210), Ref(1240), bGameOver ? TEXT("对局结算") : TEXT("回合结算"), TEXT("ИТОГИ"));
	// Vertical rhythm (design px). Header bar ends at 256; title / subtitle / ruler / column header are each separated by >= 14-18 px,
	// and the rows are tall enough that the income line lands in the lower third, well above the continue button (hit rect y 900..964).
	const float RowH = bGameOver ? 56.0f : 72.0f;
	const float RowStride = bGameOver ? 66.0f : 86.0f;
	const float RowTop = 452.0f;
	const auto TextTop = [](float RowY, float Height, float Pt) { return RowY + Height * 0.5f - Pt * 0.78f; };
	DrawText(Out, Geometry, Layer + 5, bGameOver ? TEXT("对局结束 · 最终名次") : TEXT("战斗结算"), RefVec(486, 270), 30, TreadUI::Red, EFontRole::SansBlack);
	DrawText(Out, Geometry, Layer + 5, FString::Printf(TEXT("第 %d 回合 · 对局事件 %d"), Controller->MatchState.LastBattleResult.RoundIndex, Controller->MatchState.BattleEvents.Num()), RefVec(486, 328), 18, InkDim, EFontRole::SansMedium, FVector2D(900.0f, 28.0f), EHudText::Numbers);
	TreadUI::Ruler(Out, Geometry, Layer + 2, TreadUI::V2(RefVec(486, 374)), Ref(1148), TreadUI::InkA(0.55f), LayoutScale);
	const float ColumnY = 408.0f;
	if (bGameOver)
	{
		DrawText(Out, Geometry, Layer + 5, TEXT("名次"), RefVec(520, ColumnY), 15, InkDim, EFontRole::Mono);
		DrawText(Out, Geometry, Layer + 5, TEXT("玩家"), RefVec(660, ColumnY), 15, InkDim, EFontRole::Mono);
		DrawText(Out, Geometry, Layer + 5, TEXT("状态"), RefVec(1030, ColumnY), 15, InkDim, EFontRole::Mono);
		// Column heads share the left edge of their values (x 520 / 660 / 1030 / 1260); the last head used to sit at 1240, 20 px left of its values.
		DrawText(Out, Geometry, Layer + 5, TEXT("基地生命"), RefVec(1260, ColumnY), 15, InkDim, EFontRole::Mono);
		TArray<const FTreadM1PlayerState*> RankedPlayers;
		for (const FTreadM1PlayerState& P : Controller->MatchState.Players) RankedPlayers.Add(&P);
		RankedPlayers.Sort([](const FTreadM1PlayerState& Left, const FTreadM1PlayerState& Right)
		{
			return Left.Rank == Right.Rank ? Left.PlayerId < Right.PlayerId : Left.Rank < Right.Rank;
		});
		for (int32 Index = 0; Index < RankedPlayers.Num() && Index < 4; ++Index)
		{
			const FTreadM1PlayerState& P = *RankedPlayers[Index];
			const float Y = RowTop + Index * RowStride;
			if (P.bIsHuman)
			{
				DrawBlock(Out, Geometry, Layer + 2, RefVec(486, Y), RefVec(1148, RowH), TreadUI::PaperL, 2.0f, TreadUI::Ink);
				DrawBlock(Out, Geometry, Layer + 3, RefVec(488, Y + 2), RefVec(6, RowH - 4), TreadUI::PlayerInk);
			}
			else DrawInset(Out, Geometry, Layer + 2, RefVec(486, Y), RefVec(1148, RowH), TreadUI::PaperDD);
			DrawText(Out, Geometry, Layer + 5, FString::Printf(TEXT("# %d"), P.Rank), RefVec(520, TextTop(Y, RowH, 19)), 19, P.Rank == 1 ? TreadUI::Ochre : TreadUI::Ink, EFontRole::Stencil);
			DrawText(Out, Geometry, Layer + 5, P.DisplayName, RefVec(660, TextTop(Y, RowH, 17)), 17, P.bIsHuman ? TreadUI::PlayerInk : TreadUI::Ink, EFontRole::SansBlack, FVector2D(330.0f, 26.0f));
			DrawText(Out, Geometry, Layer + 5, P.bIsEliminated ? TEXT("已淘汰") : TEXT("存活 ✓"), RefVec(1030, TextTop(Y, RowH, 17)), 17, P.bIsEliminated ? TreadUI::Red : TreadUI::Ink, EFontRole::SansBold);
			DrawText(Out, Geometry, Layer + 5, FString::FromInt(P.Health), RefVec(1260, TextTop(Y, RowH, 17)), 17, TreadUI::Ink, EFontRole::MonoBold);
		}
		if (const FTreadM1PlayerState* P = GetHumanPlayer())
			DrawText(Out, Geometry, Layer + 5, FString::Printf(TEXT("本局名次：第 %d / %d 名"), P->Rank, RankedPlayers.Num()), RefVec(520, 730), 20, TreadUI::PlayerInk, EFontRole::SansBlack, FVector2D(900.0f, 30.0f), EHudText::Numbers);
	}
	else
	{
		DrawText(Out, Geometry, Layer + 5, TEXT("玩家"), RefVec(520, ColumnY), 15, InkDim, EFontRole::Mono);
		DrawText(Out, Geometry, Layer + 5, TEXT("结果"), RefVec(820, ColumnY), 15, InkDim, EFontRole::Mono);
		DrawText(Out, Geometry, Layer + 5, TEXT("生命"), RefVec(1030, ColumnY), 15, InkDim, EFontRole::Mono);
		DrawText(Out, Geometry, Layer + 5, TEXT("存活单位"), RefVec(1260, ColumnY), 15, InkDim, EFontRole::Mono);
		for (int32 Index = 0; Index < Controller->MatchState.LastBattleResult.Outcomes.Num() && Index < 4; ++Index)
		{
			const FTreadM1BattleOutcome& Outcome = Controller->MatchState.LastBattleResult.Outcomes[Index];
			const float Y = RowTop + Index * RowStride;
			const bool bHuman = Outcome.PlayerId == TEXT("P0");
			if (bHuman)
			{
				DrawBlock(Out, Geometry, Layer + 2, RefVec(486, Y), RefVec(1148, RowH), TreadUI::PaperL, 2.0f, TreadUI::Ink);
				DrawBlock(Out, Geometry, Layer + 3, RefVec(488, Y + 2), RefVec(6, RowH - 4), TreadUI::PlayerInk);
			}
			else DrawInset(Out, Geometry, Layer + 2, RefVec(486, Y), RefVec(1148, RowH), TreadUI::PaperDD);
			const bool bWin = Outcome.Outcome == TEXT("Win");
			const float ResultPt = bWin ? 26.0f : 20.0f;
			DrawText(Out, Geometry, Layer + 5, Outcome.PlayerId, RefVec(520, TextTop(Y, RowH, 22)), 22, bHuman ? TreadUI::PlayerInk : TreadUI::Ink, EFontRole::Stencil);
			// Win = large red with a star; loss = dimmed ink, so the two stay apart without green.
			DrawText(Out, Geometry, Layer + 5, bWin ? TEXT("★ 胜利") : TEXT("失败"), RefVec(820, TextTop(Y, RowH, ResultPt)), ResultPt, bWin ? TreadUI::Red : TreadUI::InkA(0.6f), EFontRole::SansBlack);
			DrawText(Out, Geometry, Layer + 5, FString::Printf(TEXT("%d → %d"), Outcome.HealthBefore, Outcome.HealthAfter), RefVec(1030, TextTop(Y, RowH, 20)), 20, Outcome.HealthAfter < Outcome.HealthBefore ? TreadUI::Red : TreadUI::Ink, EFontRole::MonoBold);
			DrawText(Out, Geometry, Layer + 5, FString::Printf(TEXT("%d"), Outcome.SurvivingUnitCount), RefVec(1260, TextTop(Y, RowH, 20)), 20, TreadUI::Ink, EFontRole::MonoBold);
		}
		DrawText(Out, Geometry, Layer + 5, FString::Printf(TEXT("收入  +%d 基础  +%d 利息  +%d 连胜/败"), Controller->MatchState.LastBattleResult.IncomeBreakdown.Base, Controller->MatchState.LastBattleResult.IncomeBreakdown.Interest, Controller->MatchState.LastBattleResult.IncomeBreakdown.Streak), RefVec(520, 812), 17, TreadUI::Ochre, EFontRole::SansBold, FVector2D(900.0f, 26.0f), EHudText::Numbers);
	}
	const FString& CampaignResult = Controller->MatchState.CampaignResult;
	if (bGameOver && Controller->MatchState.CampaignStage > 0)
	{
		const TArray<FTreadM4CampaignStageView> Stages = Controller->GetCampaignStages();
		const FTreadM4CampaignStageView* Stage = Stages.FindByPredicate([this](const FTreadM4CampaignStageView& S) { return S.Index == Controller->MatchState.CampaignStage; });
		const FString Country = Stage ? Stage->Country : FString();
		const bool bWon = CampaignResult == TEXT("Conquered") || CampaignResult == TEXT("WorldDomination");
		DrawText(Out, Geometry, Layer + 5, bWon ? FString::Printf(TEXT("第 %d 关 · 已占领 %s"), Controller->MatchState.CampaignStage, *Country)
			: FString::Printf(TEXT("第 %d 关 · 未能占领 %s（可无惩罚重打）"), Controller->MatchState.CampaignStage, *Country),
			RefVec(520, 780), 22, bWon ? TreadUI::Red : TreadUI::Amber, EFontRole::SansBlack, FVector2D(900.0f, 34.0f), EHudText::Numbers);
		int32 Conquered = 0;
		for (const FTreadM4CampaignStageView& S : Stages) Conquered += S.bConquered ? 1 : 0;
		DrawText(Out, Geometry, Layer + 5, FString::Printf(TEXT("战役进度 %d / %d"), Conquered, Stages.Num()), RefVec(520, 826), 17, InkDim, EFontRole::SansMedium, FVector2D(600.0f, 28.0f), EHudText::Numbers);
		// A conquered stage is stamped "cleared"; the stamp lands half a second after the panel appears.
		if (bWon)
			TreadUI::Stamp(Out, Geometry, Layer + 6, TreadUI::ETex::StampCleared, TreadUI::V2(RefVec(1500, 745)), TreadUI::V2(RefVec(230, 230)), TreadUI::Red, -12.0f,
				static_cast<float>(TreadUI::RealTime() - PhaseChangedAtSeconds) - 0.5f);
	}
	DrawButton(Out, Geometry, Layer + 20, RefVec(1220, 900), RefVec(420, 64),
		bGameOver ? (CampaignResult == TEXT("Conquered") ? FString(TEXT("前往下一关")) : FString(TEXT("返回战役地图"))) : FString(TEXT("继续")),
		bGameOver ? (CampaignResult == TEXT("Conquered") ? FString(TEXT("ВПЕРЁД")) : FString(TEXT("НАЗАД"))) : FString(TEXT("ДАЛЕЕ")),
		EHudButton::Primary, ContinueButton, true, 24.0f);
}

void UTreadM1MatchWidget::DrawWorldDomination(const FGeometry& Geometry, FSlateWindowElementList& Out, int32 Layer) const
{
	// M4: stage 16 conquered -> the world domination ending replaces the final ranking.
	DrawScrim(Out, Geometry, Layer);
	DrawPaper(Out, Geometry, Layer + 1, RefVec(360, 240), RefVec(1200, 540), true);
	DrawHeader(Out, Geometry, Layer + 3, RefVec(360, 240), Ref(1200), TEXT("最终报告"), TEXT("ПОБЕДА"));
	DrawText(Out, Geometry, Layer + 5, TEXT("世界统治达成"), RefVec(960, 304), 52, TreadUI::Red, EFontRole::SansBlack, FVector2D(2000.0f, 200.0f), EHudText::Center);
	DrawText(Out, Geometry, Layer + 5, TEXT("十六国全部占领：巴黎、华沙、伦敦、柏林……直至姬路城。"), RefVec(960, 410), 24, TreadUI::Ink, EFontRole::SansMedium, FVector2D(1120.0f, 36.0f), EHudText::Center);
	DrawText(Out, Geometry, Layer + 5, TEXT("巨像的脚步踏遍大陆，所有地标都在你的阴影之下。"), RefVec(960, 454), 22, TreadUI::InkA(0.7f), EFontRole::SansMedium, FVector2D(1120.0f, 34.0f), EHudText::Center);
	const TArray<FTreadM4CampaignStageView> Stages = Controller->GetCampaignStages();
	for (int32 Index = 0; Index < Stages.Num(); ++Index)
	{
		// "南斯拉夫 / 塞尔维亚" -> the first name only.
		FString Country = Stages[Index].Country;
		Country.Split(TEXT("/"), &Country, nullptr);
		DrawText(Out, Geometry, Layer + 5, FString::Printf(TEXT("%d %s"), Stages[Index].Index, *Country.TrimStartAndEnd()),
			RefVec(410 + (Index % 8) * 138, 530 + (Index / 8) * 46), 17, TreadUI::Red, EFontRole::SansBlack, FVector2D(130.0f, 28.0f), EHudText::Numbers);
	}
	DrawButton(Out, Geometry, Layer + 4, RefVec(750, 680), RefVec(420, 64), TEXT("返回战役地图"), TEXT("НАЗАД"), EHudButton::Primary, ContinueButton, true, 24.0f);
	TreadUI::Stamp(Out, Geometry, Layer + 8, TreadUI::ETex::StampApproved, TreadUI::V2(RefVec(1400, 725)), TreadUI::V2(RefVec(230, 230)), TreadUI::Red, 8.0f,
		static_cast<float>(TreadUI::RealTime() - PhaseChangedAtSeconds) - 0.5f);
}

void UTreadM1MatchWidget::DrawCampaignMap(const FGeometry& Geometry, FSlateWindowElementList& Out, int32 Layer) const
{
	// Development entry (the front end normally covers this phase): paper cards, same layout as before.
	const FLinearColor InkDim = TreadUI::InkA(0.7f);
	const TArray<FTreadM4CampaignStageView> Stages = Controller->GetCampaignStages();
	const int32 Selected = Controller->MatchState.CampaignStage;
	DrawScrim(Out, Geometry, Layer);
	DrawPaper(Out, Geometry, Layer + 1, RefVec(120, 110), RefVec(1680, 860), true);
	int32 Conquered = 0;
	for (const FTreadM4CampaignStageView& S : Stages) Conquered += S.bConquered ? 1 : 0;
	DrawHeader(Out, Geometry, Layer + 2, RefVec(120, 110), Ref(1680), TEXT("踏国 · 十六国战役"), TEXT("КАМПАНИЯ"));
	DrawText(Out, Geometry, Layer + 4, FString::Printf(TEXT("已占领 %d / %d · 顺序解锁 · 失败可无惩罚重打"), Conquered, Stages.Num()), RefVec(1776, 122), 14, TreadUI::PaperLA(0.8f), EFontRole::Mono, FVector2D(900.0f, 24.0f), EHudText::Right | EHudText::Numbers);
	for (int32 Index = 0; Index < Stages.Num() && Index < 16; ++Index)
	{
		const FTreadM4CampaignStageView& S = Stages[Index];
		const FVector2D Card = StageCardPosition(Index);
		const bool bSelected = S.Index == Selected;
		const bool bHovered = S.bUnlocked && !bSelected && StageButtons.IsValidIndex(Index) && StageButtons[Index]->IsHovered();
		// Selected = red card, conquered = light paper, frontier = paper, sealed = hatched dark paper.
		FLinearColor Fill = S.bConquered ? TreadUI::PaperL : S.bUnlocked ? TreadUI::Paper : TreadUI::PaperDD;
		FLinearColor Edge = S.bUnlocked ? TreadUI::Ink : TreadUI::InkA(0.55f);
		float Border = 2.0f;
		if (bSelected) { Fill = TreadUI::Red; Edge = TreadUI::Ink; Border = 3.0f; }
		else if (bHovered) { Edge = TreadUI::Red; Border = 3.0f; }
		DrawBlock(Out, Geometry, Layer + 3, RefVec(Card.X, Card.Y), RefVec(196, 124), Fill, Border, Edge, 12.0f);
		if (!S.bUnlocked) TreadUI::Tiled(Out, Geometry, Layer + 4, TreadUI::ETex::Hatch, TreadUI::V2(RefVec(Card.X + 3, Card.Y + 3)), TreadUI::V2(RefVec(190, 118)), TreadUI::InkA(0.12f), LayoutScale);
		const FLinearColor Tone = bSelected ? TreadUI::PaperL : S.bUnlocked ? TreadUI::Ink : TreadUI::InkA(0.45f);
		DrawBlock(Out, Geometry, Layer + 4, RefVec(Card.X + 14, Card.Y + 4), RefVec(180, 4), S.bConquered ? TreadUI::Ink : S.bUnlocked ? (bSelected ? TreadUI::PaperL : TreadUI::Red) : TreadUI::InkA(0.45f));
		DrawText(Out, Geometry, Layer + 5, FString::Printf(TEXT("%02d"), S.Index), RefVec(Card.X + 12, Card.Y + 12), 22, Tone, EFontRole::Stencil);
		const FLinearColor ChipFill = S.bConquered ? TreadUI::Ink : S.bUnlocked ? (bSelected ? TreadUI::Ink : TreadUI::Red) : TreadUI::InkA(0.55f);
		DrawBlock(Out, Geometry, Layer + 4, RefVec(Card.X + 112, Card.Y + 14), RefVec(76, 22), ChipFill);
		DrawText(Out, Geometry, Layer + 5, S.bConquered ? TEXT("已占领") : S.bUnlocked ? TEXT("可挑战") : TEXT("未解锁"), RefVec(Card.X + 150, Card.Y + 15), 13, TreadUI::PaperL, EFontRole::SansBold, FVector2D(2000.0f, 200.0f), EHudText::Center);
		DrawText(Out, Geometry, Layer + 5, S.Country, RefVec(Card.X + 12, Card.Y + 44), 18, Tone, EFontRole::SansBlack, FVector2D(176.0f, 28.0f));
		DrawText(Out, Geometry, Layer + 5, S.Landmark, RefVec(Card.X + 12, Card.Y + 72), 14, bSelected ? TreadUI::PaperLA(0.85f) : S.bUnlocked ? InkDim : TreadUI::InkA(0.45f), EFontRole::SansMedium, FVector2D(176.0f, 22.0f));
		DrawText(Out, Geometry, Layer + 5, FString::Printf(TEXT("AI 强度 %d"), S.AiLevel), RefVec(Card.X + 12, Card.Y + 98), 12, bSelected ? TreadUI::PaperLA(0.85f) : InkDim, EFontRole::Mono, FVector2D(176.0f, 20.0f), EHudText::Numbers);
	}
	const FTreadM4CampaignStageView* Current = Stages.FindByPredicate([Selected](const FTreadM4CampaignStageView& S) { return S.Index == Selected; });
	DrawPaper(Out, Geometry, Layer + 2, RefVec(150, 470), RefVec(1620, 170), false);
	if (Current)
	{
		DrawText(Out, Geometry, Layer + 4, FString::Printf(TEXT("第 %d 关：%s · %s"), Current->Index, *Current->Country, *Current->Landmark), RefVec(176, 486), 28, TreadUI::Ink, EFontRole::SansBlack, FVector2D(1500.0f, 42.0f), EHudText::Numbers);
		DrawText(Out, Geometry, Layer + 4, Current->Rule, RefVec(176, 540), 18, InkDim, EFontRole::SansMedium, FVector2D(1560.0f, 28.0f), EHudText::Numbers);
		DrawText(Out, Geometry, Layer + 4, FString::Printf(TEXT("关卡效果：%s"), *Current->Effect), RefVec(176, 576), 18, TreadUI::Ochre, EFontRole::SansBold, FVector2D(1560.0f, 28.0f), EHudText::Numbers);
		DrawText(Out, Geometry, Layer + 4, TEXT("R1–2 城市守军 · R3–11 四人对抗 · R12 领袖战（领袖阵容与生命来自数据表）"), RefVec(176, 612), 15, InkDim, EFontRole::Mono, FVector2D(1560.0f, 26.0f));
	}
	else
	{
		DrawText(Out, Geometry, Layer + 4, TEXT("自由对局 · 巴黎"), RefVec(176, 486), 28, TreadUI::Ink, EFontRole::SansBlack, FVector2D(1500.0f, 42.0f));
		DrawText(Out, Geometry, Layer + 4, TEXT("4 人自由竞争 · R1–2 演练 · R3–11 对抗 · R12 领袖战 · 不计入战役进度"), RefVec(176, 540), 18, InkDim, EFontRole::SansMedium, FVector2D(1560.0f, 28.0f), EHudText::Numbers);
		DrawText(Out, Geometry, Layer + 4, TEXT("点击上方关卡卡片进入战役关卡。"), RefVec(176, 576), 18, TreadUI::Ink, EFontRole::SansMedium, FVector2D(1560.0f, 28.0f));
	}
	DrawButton(Out, Geometry, Layer + 2, RefVec(720, 660), RefVec(480, 76),
		Current ? FString::Printf(TEXT("开始第 %d 关 · 进入赛前 BP"), Current->Index) : FString(TEXT("开始巴黎 · 进入赛前 BP")), TEXT("ВПЕРЁД"), EHudButton::Primary, StartButton, true, 24.0f);
	const bool bFreeSelected = Selected == 0;
	const bool bFreeHovered = !bFreeSelected && FreeMatchButton && FreeMatchButton->IsHovered();
	DrawBlock(Out, Geometry, Layer + 2, RefVec(1250, 668), RefVec(330, 60), bFreeSelected ? TreadUI::Red : TreadUI::Paper, bFreeSelected || bFreeHovered ? 3.0f : 2.0f, bFreeHovered ? TreadUI::Red : TreadUI::Ink, 12.0f);
	DrawText(Out, Geometry, Layer + 4, TEXT("自由对局（不计进度）"), RefVec(1415, 684), 18, bFreeSelected ? TreadUI::PaperL : TreadUI::Ink, EFontRole::SansBlack, FVector2D(2000.0f, 200.0f), EHudText::Center);
	DrawText(Out, Geometry, Layer + 3, TEXT("选择策略，购买角色，拖拽备战席单位到己方蓝色棋盘 · 准备期倒计时 · 自动战斗 · 全程鼠标操作"), RefVec(176, 780), 17, InkDim, EFontRole::SansMedium, FVector2D(1560.0f, 28.0f));
}

void UTreadM1MatchWidget::DrawPacts(const FGeometry& Geometry, FSlateWindowElementList& Out, int32 Layer,
	const FVector2D& Origin, const FVector2D& Size, const FTreadM1PlayerState& P, bool bCompact) const
{
	if (!Controller.IsValid()) return;
	const FLinearColor InkDim = TreadUI::InkA(0.7f);
	const int32 LatestSequence = Controller->MatchState.TraitLog.Num();
	const float Pulse = GetWorld() ? 0.5f + 0.5f * FMath::Sin(GetWorld()->GetTimeSeconds() * 5.0f) : 1.0f;
	DrawPaper(Out, Geometry, Layer, RefVec(Origin.X, Origin.Y), RefVec(Size.X, Size.Y), true);
	int32 ActiveCount = 0;
	int32 TotalStacks = 0;
	TArray<const FTreadM2PactProgress*> Rows;
	for (const FTreadM2PactProgress& Pact : P.Pacts)
	{
		ActiveCount += Pact.bActive ? 1 : 0;
		TotalStacks += Pact.Stacks;
		if ((Pact.Count > 0 || Pact.Stacks > 0) && (!bCompact || Pact.bActive || Pact.Stacks > 0)) Rows.Add(&Pact);
	}
	Rows.StableSort([](const FTreadM2PactProgress& A, const FTreadM2PactProgress& B)
	{
		if (A.ActiveTier != B.ActiveTier) return A.ActiveTier > B.ActiveTier;
		if (A.Count != B.Count) return A.Count > B.Count;
		return A.Stacks > B.Stacks;
	});
	DrawHeader(Out, Geometry, Layer + 2, RefVec(Origin.X, Origin.Y), Ref(Size.X), bCompact ? TEXT("盟约层数") : TEXT("盟约"), TEXT("СОЮЗЫ"));
	if (bCompact)
	{
		DrawButton(Out, Geometry, Layer + 6, RefVec(Origin.X + Size.X - 28, Origin.Y + 8), RefVec(22, 22),
			bPactPanelCollapsed ? FString(TEXT("＋")) : FString(TEXT("－")), FString(), EHudButton::Secondary, PactZoomButton, true, 14.0f);
		if (bPactPanelCollapsed) return;
	}
	DrawText(Out, Geometry, Layer + 4, bCompact ? TEXT("战斗快照") : TEXT("人数档位 / 层数"), RefVec(Origin.X + Size.X - 20, Origin.Y + 13), 13, TreadUI::PaperLA(0.75f), EFontRole::Mono, FVector2D(2000.0f, 200.0f), EHudText::Right);
	// The summary line must fit the 24 px slot between the ink bar and the first row, so it uses a smaller face.
	DrawText(Out, Geometry, Layer + 4, FString::Printf(TEXT("已激活 %d  ·  层数合计 %d  ·  待结算特质资金 ¤%d"), ActiveCount, TotalStacks, P.PendingTraitIncome),
		RefVec(Origin.X + 18, Origin.Y + 49), 13, InkDim, EFontRole::Mono, FVector2D(Size.X - 30.0f, 22.0f), EHudText::Numbers);
	if (bCompact)
	{
		// document/170: 拉特兰 ammo stacking and 远见 bench layers, on their own line under the summary.
		float AmmoMul = 1.0f;
		for (const FTreadM1UnitInstance& Unit : P.BoardUnits)
		{
			AmmoMul = FMath::Max(AmmoMul, Controller->GetUnitAmmoMultiplier(P.PlayerId, Unit.UnitInstanceId));
		}
		const int32 Foresight = Controller->GetForesightBenchCount(P.PlayerId);
		DrawText(Out, Geometry, Layer + 4,
			FString::Printf(TEXT("拉特兰 叠攻 ×%.2f   ·   远见 整备 %d 人"), AmmoMul, Foresight),
			RefVec(Origin.X + 18, Origin.Y + 70), 13,
			AmmoMul > 1.001f ? TreadUI::Amber : InkDim, EFontRole::Mono, FVector2D(Size.X - 36.0f, 20.0f));
	}

	const int32 MaxRows = bCompact ? 6 : 9;
	const float RowHeight = 40.0f;
	float Y = Origin.Y + (bCompact ? 96 : 70);
	if (Rows.Num() == 0)
	{
		DrawText(Out, Geometry, Layer + 4, TEXT("尚无盟约成员：上阵单位后显示人数与层数"), RefVec(Origin.X + 18, Y + 8), 15, InkDim, EFontRole::SansMedium, FVector2D(Size.X - 30.0f, 24.0f));
	}
	for (int32 Index = 0; Index < Rows.Num() && Index < MaxRows; ++Index, Y += RowHeight)
	{
		const FTreadM2PactProgress& Pact = *Rows[Index];
		const bool bCore = Pact.Kind == TEXT("Core");
		const bool bRecent = Pact.LastChangeSequence > 0 && Pact.LastChangeSequence > LatestSequence - 8;
		// Core pacts print in ochre, adjunct pacts in player blue; a recent change pulses towards amber.
		const FLinearColor Tone = bCore ? TreadUI::Ochre : TreadUI::PlayerInk;
		FLinearColor RowColor = Pact.bActive ? FMath::Lerp(TreadUI::PaperL, Tone, 0.28f) : TreadUI::PaperDD;
		if (bRecent) RowColor = FMath::Lerp(RowColor, TreadUI::Amber, 0.35f * Pulse);
		if (Pact.bActive) DrawBlock(Out, Geometry, Layer + 2, RefVec(Origin.X + 12, Y), RefVec(Size.X - 24, RowHeight - 4), RowColor, 2.0f, TreadUI::Ink);
		else DrawInset(Out, Geometry, Layer + 2, RefVec(Origin.X + 12, Y), RefVec(Size.X - 24, RowHeight - 4), RowColor);
		if (Pact.bActive) DrawDivider(Out, Geometry, Layer + 3, RefVec(Origin.X + 14, Y + 2), RefVec(4, RowHeight - 8), Tone);
		DrawText(Out, Geometry, Layer + 5, Pact.PactId, RefVec(Origin.X + 26, Y + 6), 17, Pact.bActive ? TreadUI::Ink : InkDim, EFontRole::SansBlack, FVector2D(102.0f, 26.0f));
		DrawBlock(Out, Geometry, Layer + 3, RefVec(Origin.X + 130, Y + 9), RefVec(38, 18), TreadUI::WithAlpha(Tone, Pact.bActive ? 1.0f : 0.55f));
		DrawText(Out, Geometry, Layer + 5, bCore ? TEXT("核心") : TEXT("加盟"), RefVec(Origin.X + 149, Y + 9), 12, TreadUI::PaperL, EFontRole::SansBold, FVector2D(2000.0f, 200.0f), EHudText::Center);
		// One pip per threshold: filled when reached, labelled with the member count it needs.
		for (int32 Tier = 0; Tier < Pact.Thresholds.Num(); ++Tier)
		{
			const bool bReached = Tier < Pact.ActiveTier;
			const float PipX = Origin.X + 172 + Tier * 34;
			DrawBlock(Out, Geometry, Layer + 3, RefVec(PipX, Y + 7), RefVec(28, 22), bReached ? Tone : TreadUI::PaperDD, bReached ? 2.0f : 1.0f, bReached ? TreadUI::Ink : TreadUI::InkA(0.55f));
			DrawText(Out, Geometry, Layer + 5, FString::FromInt(Pact.Thresholds[Tier]), RefVec(PipX + 14, Y + 9), 13, bReached ? TreadUI::PaperL : InkDim, EFontRole::MonoBold, FVector2D(2000.0f, 200.0f), EHudText::Center);
		}
		FString CountText = FString::Printf(TEXT("%d 人"), Pact.Count);
		if (Pact.HarmonyBonus > 0) CountText += FString::Printf(TEXT(" (调和+%d)"), Pact.HarmonyBonus);
		if (Pact.BenchCount > 0) CountText += FString::Printf(TEXT(" 备战+%d"), Pact.BenchCount);
		DrawText(Out, Geometry, Layer + 5, CountText, RefVec(Origin.X + 248, Y + 9), 14, TreadUI::Ink, EFontRole::SansMedium, FVector2D(150.0f, 24.0f), EHudText::Numbers);
		DrawText(Out, Geometry, Layer + 5, FString::Printf(TEXT("层 %d"), Pact.Stacks), RefVec(Origin.X + Size.X - 110, Y + 6), 17, Pact.Stacks > 0 ? TreadUI::Ink : InkDim, EFontRole::SansBlack, FVector2D(60.0f, 26.0f), EHudText::Numbers);
		if (bRecent && Pact.LastStackDelta > 0)
		{
			DrawText(Out, Geometry, Layer + 5, FString::Printf(TEXT("+%d"), Pact.LastStackDelta), RefVec(Origin.X + Size.X - 48, Y + 8), 14, TreadUI::PlayerInk, EFontRole::SansBlack, FVector2D(36.0f, 24.0f), EHudText::Numbers);
		}
	}
	if (bCompact) Y = Origin.Y + 70 + MaxRows * RowHeight;
	else
	{
		// Trait values of the participant's units: [current] is base for 1-star, elite for 2-star and above.
		Y = Origin.Y + 70 + MaxRows * RowHeight + 6;
		const FString TraitHeader = TEXT("单位特质  数值 X/Y（[ ] 为当前生效，精锐取后值）");
		float TraitPt = 14.0f;
		while (TraitPt > 11.0f && MeasureText(TraitHeader, TraitPt, EFontRole::SansBlack) > Size.X - 40.0f) TraitPt -= 0.5f;
		DrawText(Out, Geometry, Layer + 4, TraitHeader, RefVec(Origin.X + 18, Y), TraitPt, TreadUI::PlayerInk, EFontRole::SansBlack, FVector2D(Size.X - 40.0f, 24.0f));
		Y += 24;
		TArray<FTreadM1UnitInstance> Units = P.BoardUnits;
		Units.Append(P.BenchUnits);
		for (int32 Index = 0; Index < Units.Num() && Index < 4; ++Index)
		{
			const FTreadM1UnitInstance& Unit = Units[Index];
			FString Summary = Controller->GetTraitSummary(Unit.CharacterId);
			if (Summary.Len() > 14) Summary = CutWithEllipsis(Summary, 13);
			DrawText(Out, Geometry, Layer + 4, FString::Printf(TEXT("%s ★%d  %s  %s"), *Unit.CharacterId.RightChop(5), Unit.UnitStar,
				*Controller->GetTraitValueText(Unit.CharacterId, Unit.UnitStar), *Summary), RefVec(Origin.X + 18, Y + Index * 22), 13,
				Unit.UnitStar >= 2 ? TreadUI::Ochre : InkDim, Unit.UnitStar >= 2 ? EFontRole::SansBold : EFontRole::Mono, FVector2D(Size.X - 40.0f, 22.0f));
		}
		Y += 4 * 22 + 6;
	}
	DrawText(Out, Geometry, Layer + 4, TEXT("触发日志"), RefVec(Origin.X + 18, Y), 14, TreadUI::PlayerInk, EFontRole::SansBlack);
	Y += 24;
	int32 Lines = 0;
	const int32 MaxLines = bCompact ? 3 : 5;
	for (int32 Index = Controller->MatchState.TraitLog.Num() - 1; Index >= 0 && Lines < MaxLines; --Index)
	{
		const FTreadM2TraitLogEntry& Entry = Controller->MatchState.TraitLog[Index];
		if (Entry.PlayerId != P.PlayerId || Entry.Status == TEXT("event")) continue;
		const bool bApplied = Entry.Status.StartsWith(TEXT("applied"));
		FString Line = FString::Printf(TEXT("R%d %s·%s %s %s"), Entry.RoundIndex, *Entry.Trigger, *Entry.Event, *Entry.Op, *Entry.PactId);
		if (Entry.Op == TEXT("AddStacks")) Line += FString::Printf(TEXT(" +%d→%d"), Entry.Amount, Entry.StacksAfter);
		else if (Entry.Amount != 0) Line += FString::Printf(TEXT(" %d"), Entry.Amount);
		if (!bApplied) Line += TEXT("  ") + Entry.Status;
		// Keep every log line inside the panel; long statuses would otherwise spill over the 3D board.
		DrawText(Out, Geometry, Layer + 4, Line, RefVec(Origin.X + 18, Y + Lines * 22), 13, bApplied ? TreadUI::PlayerInk : InkDim, EFontRole::Mono, FVector2D(Size.X - 40.0f, 22.0f));
		++Lines;
	}
}

ATreadM3BoardPresenter* UTreadM1MatchWidget::FindBoardPresenter() const
{
	if (!bPresenterSearched && GetWorld())
	{
		bPresenterSearched = true;
		for (TActorIterator<ATreadM3BoardPresenter> It(GetWorld()); It; ++It) { BoardPresenter = *It; break; }
	}
	return BoardPresenter.Get();
}
