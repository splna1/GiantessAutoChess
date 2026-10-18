#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "TreadM1DataTypes.h"
#include "TreadUIStyle.h"
#include "TreadM1MatchWidget.generated.h"

class ATreadM1MatchController;
class ATreadM3BoardPresenter;
class UButton;
class UCanvasPanel;
class UTexture2D;
class UTreadAudioDirector;
struct FSlateBrush;

/** Options of UTreadM1MatchWidget::DrawText (doc 157 section 5). */
enum class EHudText : uint8
{
	None = 0,
	Shadow = 1 << 0,    // 2 px ink drop shadow: PaperL text over the 3D scene
	Numbers = 1 << 1,   // digit runs switch to the numeral face (Stencil under SansBlack/Stencil, MonoBold otherwise)
	Center = 1 << 2,    // Position.X is the horizontal centre of the text
	Right = 1 << 3      // Position.X is the right edge of the text
};
ENUM_CLASS_FLAGS(EHudText);

/**
 * Runtime M1 HUD built as a native UMG widget.  The widget deliberately keeps
 * the visual layer data driven by MatchState and leaves all rule decisions to
 * ATreadM1MatchController.  The numeric layout mirrors document/M1_UI tokens
 * (1920x1080 reference, shortest-side DPI curve).
 */
UCLASS(BlueprintType)
class TREAD_API UTreadM1MatchWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	UTreadM1MatchWidget(const FObjectInitializer& ObjectInitializer);
	int32 GetScoutPlayerIndex() const { return ScoutPlayerIndex; }

	/** M4 evidence hooks for Python in PIE: open the roster audit panel at a page / close it. */
	UFUNCTION(BlueprintCallable, Category = "M4|Test")
	void SetRosterPanelForTest(bool bOpen, int32 Page);

	/** M4 evidence hook: draw a tooltip as if "shop", "bench" or "item" slot Index were hovered ("" clears). */
	UFUNCTION(BlueprintCallable, Category = "M4|Test")
	void SetForcedTooltipForTest(const FString& Kind, int32 Index);

	/** M4 evidence hook: open the full PNG portrait detail of a character ("" closes it). */
	UFUNCTION(BlueprintCallable, Category = "M4|Test")
	void SetPortraitDetailForTest(const FString& CharacterId);

	/** Evidence hook: collapse or expand one HUD panel ("battle" / "feed" / "pact" / "squad"). */
	UFUNCTION(BlueprintCallable, Category = "HUD|Test")
	void SetPanelCollapsedForTest(const FString& Panel, bool bCollapsed);

	/** Character whose PNG portrait detail is open, "" when closed. */
	UFUNCTION(BlueprintPure, Category = "M4|Test")
	FString GetPortraitDetailId() const { return DetailCharacterId; }

	/** The front-end widget covers the R0 briefing: the dev campaign map and its buttons stay hidden underneath. */
	void SetCampaignMapSuppressed(bool bSuppressed) { bCampaignMapSuppressed = bSuppressed; }

protected:
	virtual TSharedRef<SWidget> RebuildWidget() override;
	virtual void NativeConstruct() override;
	virtual void NativeTick(const FGeometry& MyGeometry, float InDeltaTime) override;
	virtual void NativeDestruct() override;
	virtual int32 NativePaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry,
		const FSlateRect& MyCullingRect, FSlateWindowElementList& OutDrawElements,
		int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;

private:
	UPROPERTY()
	UCanvasPanel* InteractionCanvas = nullptr;

	UPROPERTY()
	TArray<UButton*> BPButtons;

	UPROPERTY()
	TArray<UButton*> ShopButtons;

	/** document/176: three invisible hit boxes over the free reward cards. */
	UPROPERTY()
	TArray<UButton*> RewardButtons;

	UPROPERTY()
	TArray<UButton*> RankButtons;

	UPROPERTY()
	TArray<UButton*> BenchButtons;

	UPROPERTY()
	UButton* ConfirmButton = nullptr;

	UPROPERTY()
	UButton* DeployButton = nullptr;

	UPROPERTY()
	UButton* ScoutCloseButton = nullptr;

	UPROPERTY()
	UButton* ContinueButton = nullptr;
	UPROPERTY() UButton* StartButton = nullptr;
	UPROPERTY() UButton* RefreshButton = nullptr;
	UPROPERTY() UButton* LockButton = nullptr;
	UPROPERTY() UButton* ExperienceButton = nullptr;
	UPROPERTY() UButton* BoardButton = nullptr;
	/** M4 roster audit panel: open, previous/next page, close. */
	UPROPERTY() UButton* RosterButton = nullptr;
	UPROPERTY() UButton* BattleZoomButton = nullptr;
	UPROPERTY() UButton* FeedZoomButton = nullptr;
	UPROPERTY() UButton* PactZoomButton = nullptr;
	UPROPERTY() UButton* SquadZoomButton = nullptr;
	/** document/12 / 125 §4: Board_Camera <-> Audience_Camera during the battle (mouse only). */
	UPROPERTY() UButton* AudienceButton = nullptr;
	UPROPERTY() UButton* RosterPrevButton = nullptr;
	UPROPERTY() UButton* RosterNextButton = nullptr;
	UPROPERTY() UButton* RosterCloseButton = nullptr;
	/** M4 avatar interaction: a click on a shop avatar opens the PNG detail (the rest of the card buys), long press closes. */
	UPROPERTY() TArray<UButton*> ShopAvatarButtons;
	UPROPERTY() UButton* DetailButton = nullptr;
	FString DetailCharacterId;
	double PressStartSeconds = 0.0;
	static constexpr double LongPressSeconds = 0.6;
	bool IsLongPress() const;
	void OpenPortraitDetail(const FString& CharacterId);
	void ClosePortraitDetail();
	void DrawPortraitDetail(const FGeometry& Geometry, FSlateWindowElementList& OutDrawElements, int32 LayerId) const;

	/** M4 BGM / SFX / voice lines; presentation only, created once the match controller is found. */
	UPROPERTY() TObjectPtr<UTreadAudioDirector> Audio;
	/** M4 avatar ("A|id") and portrait ("P|id") textures, loaded on first draw. */
	UPROPERTY() TMap<FString, TObjectPtr<UTexture2D>> PortraitTextures;
	/** One brush per texture key; shared pointers keep the brush addresses stable while Slate draws. */
	mutable TMap<FString, TSharedPtr<FSlateBrush>> PortraitBrushes;
	/** M4 equipment inventory chips (first 8 items); click one, then a bench unit, to equip it. */
	UPROPERTY() TArray<UButton*> ItemButtons;
	int32 PendingItemIndex = INDEX_NONE;
	FString ForcedTooltipKind;
	int32 ForcedTooltipIndex = INDEX_NONE;
	bool IsSlotHovered(const FString& Kind, int32 Index, const UButton* Button) const;
	static constexpr int32 InventorySlots = 8;
	/** M4 campaign map in the R0 briefing: 16 stage cards plus the free-match card. */
	UPROPERTY() TArray<UButton*> StageButtons;
	UPROPERTY() UButton* FreeMatchButton = nullptr;
	bool bCampaignMapSuppressed = false;
	/** Real time of the last phase change: drives the result stamps. */
	double PhaseChangedAtSeconds = 0.0;
	/** Country of the running campaign stage for the top bar (resolved once per stage). */
	mutable int32 CachedCountryStage = INDEX_NONE;
	mutable FString CachedCountry;
	bool bRosterOpen = false;
	int32 RosterPage = 0;
	static constexpr int32 RosterPerPage = 32;

	TWeakObjectPtr<ATreadM1MatchController> Controller;
	mutable TWeakObjectPtr<ATreadM3BoardPresenter> BoardPresenter;
	mutable bool bPresenterSearched = false;
	/** M3 maps only: the 3D board presenter; nullptr on the M1 graybox map (2D grid path). */
	ATreadM3BoardPresenter* FindBoardPresenter() const;
	FString CaptureStage;
	bool bScoutOpen = false;
	int32 ScoutPlayerIndex = 1;
	int32 PendingBenchIndex = INDEX_NONE;
	float LayoutScale = 1.0f;
	FVector2D LayoutSize = FVector2D(1920.0f, 1080.0f);
	uint64 RequestSequence = 0;
	FString RequestPrefix;
	FString StatusMessage;
	FString NextRequestId();
	void ShowCommandResult(const FTreadM1CommandResult& Result);
	const FTreadM1UnitInstance* GetBenchUnit(int32 Index) const;

	ATreadM1MatchController* FindMatchController() const;
	void BuildInteractionLayer();
	void RefreshInteraction(const FVector2D& LocalSize);
	void SetButtonRect(UButton* Button, const FVector2D& Position, const FVector2D& Size, int32 ZOrder = 1) const;
	UButton* MakeInvisibleButton(const FString& Name);
	void HandleBPCard(int32 CardIndex);
	void HandleShopCard(int32 SlotIndex);
	void HandleRankCard(int32 PlayerIndex);
	/** document/176: claim one of the three free item rewards. */
	void HandleRewardCard(int32 Index);
	void HandleBenchCard(int32 BenchIndex);
	void HandleConfirm();
	void HandleDeploy();
	void HandleCloseScout();
	void HandleContinue();
	UFUNCTION()
	void HandleAnyClick();
	UFUNCTION()
	void HandleAnyPressed();
	UFUNCTION() void HandleAnyReleased();
	UFUNCTION()
	void HandleStateChanged();
	UFUNCTION()
	void HandlePhaseChanged(ETreadM1Phase PreviousPhase, ETreadM1Phase NewPhase);
	void DrawAll(const FGeometry& Geometry, FSlateWindowElementList& OutDrawElements, int32 LayerId) const;
	void DrawBase(const FGeometry& Geometry, FSlateWindowElementList& OutDrawElements, int32 LayerId) const;
	void DrawBoard(const FGeometry& Geometry, FSlateWindowElementList& OutDrawElements, int32 LayerId) const;
	void DrawDrag(const FGeometry& Geometry, FSlateWindowElementList& OutDrawElements, int32 LayerId) const;
	void DrawBP(const FGeometry& Geometry, FSlateWindowElementList& OutDrawElements, int32 LayerId) const;
	void DrawScout(const FGeometry& Geometry, FSlateWindowElementList& OutDrawElements, int32 LayerId) const;
	void DrawPreparation(const FGeometry& Geometry, FSlateWindowElementList& OutDrawElements, int32 LayerId) const;
	/** document/176: the free three-choice item strip shown during preparation. */
	void DrawRewardOffer(const FGeometry& Geometry, FSlateWindowElementList& OutDrawElements, int32 LayerId) const;
	void DrawBattle(const FGeometry& Geometry, FSlateWindowElementList& OutDrawElements, int32 LayerId) const;

	/** document/168: squad status panel - portrait, health bar and the green 技力 bar for every fielded unit. */
	void DrawSquadPanel(const FGeometry& Geometry, FSlateWindowElementList& OutDrawElements, int32 LayerId) const;

	/** document/170: HUD panels collapse to their title bar (only the text plus the enlarge button remains). */
	bool bBattlePanelCollapsed = false;
	bool bFeedPanelCollapsed = false;
	bool bPactPanelCollapsed = false;
	bool bSquadPanelCollapsed = false;
	void DrawResult(const FGeometry& Geometry, FSlateWindowElementList& OutDrawElements, int32 LayerId) const;
	/** M4: Avatar = chest-up screenshot of the 3D model (shop / bench / roster / tooltip), Portrait = the PNG illustration
	 *  (detail layer only).  Both are drawn whole, never cropped. */
	enum class ECharacterImage : uint8 { Avatar, Portrait };
	/** Draws the character's image into the rect; false (nothing drawn) when the character has none. */
	bool DrawCharacterImage(FSlateWindowElementList& OutDrawElements, const FGeometry& Geometry, int32 LayerId,
		const FString& CharacterId, const FVector2D& Position, const FVector2D& Size, ECharacterImage Image) const;
	void DrawCardTooltip(const FGeometry& Geometry, FSlateWindowElementList& OutDrawElements, int32 LayerId,
		const FString& CharacterId, int32 UnitStar, const FVector2D& Anchor) const;
	void DrawRoster(const FGeometry& Geometry, FSlateWindowElementList& OutDrawElements, int32 LayerId) const;
	void DrawInventory(const FGeometry& Geometry, FSlateWindowElementList& OutDrawElements, int32 LayerId, const FTreadM1PlayerState& PlayerState) const;
	void EnsureAudio();
	void DrawCampaignMap(const FGeometry& Geometry, FSlateWindowElementList& OutDrawElements, int32 LayerId) const;
	static FVector2D StageCardPosition(int32 Index) { return FVector2D(150 + (Index % 8) * 204, 196 + (Index / 8) * 134); }
	/** M2 pact tiers, stacks, trait X/Y values and event-bus log. bCompact = battle-phase summary. */
	void DrawPacts(const FGeometry& Geometry, FSlateWindowElementList& OutDrawElements, int32 LayerId,
		const FVector2D& Origin, const FVector2D& Size, const FTreadM1PlayerState& PlayerState, bool bCompact) const;
	// ---- Paper / ink / red look (doc 157 section 5). All positions and sizes are local px (RefVec); font sizes are Slate
	// points in the 1920x1080 design space and are scaled inside. A panel occupies LayerId..LayerId+1, so everything that
	// sits on it must use a higher layer (Slate draws one layer by element type, not by call order).
	/** PaperL panel, 3 px ink border, top-left cut; bShadow adds the 8 px ink drop shadow (BgPanel / BgRaised). */
	void DrawPaper(FSlateWindowElementList& OutDrawElements, const FGeometry& Geometry, int32 LayerId,
		const FVector2D& Position, const FVector2D& Size, bool bShadow) const;
	/** Inset well (BgInset): Fill plus a 1 px ink-30 frame. Quad at LayerId, frame at LayerId+1. */
	void DrawInset(FSlateWindowElementList& OutDrawElements, const FGeometry& Geometry, int32 LayerId,
		const FVector2D& Position, const FVector2D& Size, const FLinearColor& Fill) const;
	/** Flat colour block. BorderPx / CutPx are design px; a border or cut makes it one custom-verts element. */
	void DrawBlock(FSlateWindowElementList& OutDrawElements, const FGeometry& Geometry, int32 LayerId,
		const FVector2D& Position, const FVector2D& Size, const FLinearColor& Fill, float BorderPx = 0.0f,
		const FLinearColor& BorderColor = FLinearColor::Black, float CutPx = 0.0f) const;
	void DrawFrame(FSlateWindowElementList& OutDrawElements, const FGeometry& Geometry, int32 LayerId,
		const FVector2D& Position, const FVector2D& Size, const FLinearColor& Color, float ThicknessPx) const;
	/** Full-screen modal ground: opaque Paper + tiled Grain + stretched Vignette, all on LayerId. */
	void DrawScrim(FSlateWindowElementList& OutDrawElements, const FGeometry& Geometry, int32 LayerId) const;
	/** Ink title bar of a panel (TreadUI::PanelHeader); Width in local px. Layers LayerId..LayerId+1. */
	void DrawHeader(FSlateWindowElementList& OutDrawElements, const FGeometry& Geometry, int32 LayerId,
		const FVector2D& Position, float Width, const FString& Title, const FString& RuTag) const;
	enum class EHudButton : uint8 { Primary, Secondary };
	/** Painted button over an invisible UButton: red (Primary) or ink (Secondary), HoverSource drives the ink wipe. LayerId..LayerId+2.
	 *  LabelPt is the wanted label size in design Slate points (0 = from the button height); it shrinks until label + tag fit. */
	void DrawButton(FSlateWindowElementList& OutDrawElements, const FGeometry& Geometry, int32 LayerId,
		const FVector2D& Position, const FVector2D& Size, const FString& Label, const FString& RuLabel,
		EHudButton ButtonStyle, const UButton* HoverSource, bool bEnabled, float LabelPt = 0.0f) const;
	/** Command-failure message (StatusMessage) on an ink plate; the text keeps its old anchor (640, 935). */
	void DrawStatus(FSlateWindowElementList& OutDrawElements, const FGeometry& Geometry, int32 LayerId) const;
	/** Text with its top at Position.Y (nominal line box) and left at Position.X. Bounds is in design px: wider text is cut
	 *  with an ellipsis (the 2000 default means unbounded). */
	void DrawText(FSlateWindowElementList& OutDrawElements, const FGeometry& Geometry, int32 LayerId,
		const FString& Value, const FVector2D& Position, float FontSize, const FLinearColor& Color,
		TreadUI::EFontRole Role = TreadUI::EFontRole::SansMedium, const FVector2D& Bounds = FVector2D(2000.0f, 200.0f),
		EHudText Flags = EHudText::None) const;
	/** Width of Value in design px. With EHudText::Numbers it measures the numeral-face runs DrawText would draw for the same flags. */
	float MeasureText(const FString& Value, float FontSize, TreadUI::EFontRole Role, EHudText Flags = EHudText::None) const;
	/** Breaks Value into at most MaxLines lines of at most MaxWidth design px, measured like DrawText draws it with the same Flags
	 *  (so wrapped lines never trip DrawText's own Bounds ellipsis). Lines never start with closing punctuation: with HangWidth > 0 the
	 *  mark hangs past MaxWidth by up to HangWidth design px (the caller's Bounds must allow it), otherwise the preceding character
	 *  goes down with it. The last line ends in "…" when text remains. */
	TArray<FString> WrapText(const FString& Value, float FontSize, TreadUI::EFontRole Role, float MaxWidth, int32 MaxLines,
		EHudText Flags = EHudText::None, float HangWidth = 0.0f) const;
	void DrawDivider(FSlateWindowElementList& OutDrawElements, const FGeometry& Geometry, int32 LayerId,
		const FVector2D& Position, const FVector2D& Size, const FLinearColor& Color) const;
	float Ref(float Value) const { return Value * LayoutScale; }
	FVector2D RefVec(float X, float Y) const { return FVector2D(Ref(X), Ref(Y)); }
	/** ProjectWorldToScreen output (viewport pixels) -> the design px that Ref() / RefVec() place elements in. */
	FVector2D ScreenToDesign(const FGeometry& Geometry, const FVector2D& Screen) const;
	FLinearColor TierColor(const FString& Tier) const;
	FLinearColor FactionTextColor(int32 PlayerIndex) const;
	FString PhaseLabel() const;
	FString RoundLabel() const;
	const FTreadM1PlayerState* GetHumanPlayer() const;
	/** Base health as the HUD may show it: before the battle result while the 3D replay still runs. */
	int32 ShownHealth(const FTreadM1PlayerState& Who) const;
	void DrawWorldDomination(const FGeometry& Geometry, FSlateWindowElementList& OutDrawElements, int32 LayerId) const;
	void DrawBattleOverlay(const FGeometry& Geometry, FSlateWindowElementList& OutDrawElements, int32 LayerId, ATreadM3BoardPresenter* Presenter) const;
	const FTreadM1ScoutSnapshot* GetScoutSnapshotForIndex(int32 PlayerIndex) const;
};
