#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "Input/CursorReply.h"
#include "Input/Reply.h"
#include "TreadM1DataTypes.h"
#include "TreadFrontEndWidget.generated.h"

class ATreadM1MatchController;
class UCanvasPanel;
class UEditableText;
class UNativeWidgetHost;
struct FFrontPaint;
struct FFrontEnv;

/** The four screens of the front end (doc 157 section 4.2); the numeric values are the sheet numbers Л.01 .. Л.04. */
enum class EFrontScreen : uint8 { None, Loading, Login, Select, Sortie };
enum class EFrontTrans : uint8 { None, Scan, Slab, Blinds };
enum class EFrontLogin : uint8 { Idle, Verifying };
enum class EFrontStageState : uint8 { Cleared, Front, Locked };
/** Clickable buttons that animate on hover (index into BtnHover). */
enum EFrontBtn : int32 { BtnLogin = 0, BtnGo, BtnLogout, BtnFree, BtnBack, BtnCount };

/** One campaign stage as the front end shows it: the controller view plus the numbers only the JSON data carries. */
struct FFrontStage
{
	int32 Index = 0;
	FString Country, ShortName, Landmark, City, Rule, Effect, Leader;
	int32 AiLevel = 1;
	bool bUnlocked = false;
	bool bConquered = false;
	int32 GarrisonBonus = 0, EnemyHpBonus = 0, StartGoldBonus = 0, IncomeBonus = 0, DamageTakenPercent = 100, PrepareDelta = 0;
	int32 LeaderSize = 0, LeaderHp = 0;
};

/** The running screen transition (scan / double slab / blinds). Frozen >= 0 pins it at that progress (test hook). */
struct FFrontTrans
{
	EFrontTrans Kind = EFrontTrans::None;
	EFrontScreen From = EFrontScreen::None;
	EFrontScreen To = EFrontScreen::None;
	double T0 = 0.0;
	float Dir = 1.0f;
	FString Cap, Ru;
	bool bSwapped = false;
	bool bLaunch = false;       // blinds that hand the stage to the controller when fully closed
	bool bLaunchOk = false;
	float Frozen = -1.0f;
};

struct FFrontScreenRt
{
	bool bOn = false;
	double T0 = 0.0;
	float ScanMs = 0.0f;
	bool bFinal = false;
};

/**
 * Front end shown over the R0 briefing: loading -> login -> campaign map -> sortie (doc 157 section 4).
 * All painting is custom (TreadUI style library) in the 1920x1080 design space of Tools/ui_proto/tread_ui.src.html;
 * two real UEditableText boxes handle the login input. The widget is visible only while the controller is in
 * MainMenu / R0Briefing (or while its own exit transition runs) and hands the chosen stage to the controller.
 */
UCLASS(BlueprintType)
class TREAD_API UTreadFrontEndWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	UTreadFrontEndWidget(const FObjectInitializer& ObjectInitializer);

	/** Test hooks (doc 157 4.3). Screen = loading|login|select|sortie: jumps without a transition, entrance animations final. */
	UFUNCTION(BlueprintCallable, Category = "UI|Test")
	void JumpToScreenForTest(const FString& Screen);

	/** Freeze the loading screen at Fraction (0..1) with its log and read-outs in the matching state. */
	UFUNCTION(BlueprintCallable, Category = "UI|Test")
	void SetLoadingProgressForTest(float Fraction);

	/** Fill the login form with Name and run the success sequence (stays on the login screen). */
	UFUNCTION(BlueprintCallable, Category = "UI|Test")
	void SubmitLoginForTest(const FString& Name);

	/** Hover stage Index (1..16, the stage number) as if the pointer were on its card; 0 clears. */
	UFUNCTION(BlueprintCallable, Category = "UI|Test")
	void HoverStageForTest(int32 Index);

	/** Select stage Index (1..16) and settle the dossier animation. */
	UFUNCTION(BlueprintCallable, Category = "UI|Test")
	void SelectStageForTest(int32 Index);

	/** Kind = scan|slab|blinds|none. Pin that transition (from the current screen to its natural target) at Progress 0..1. */
	UFUNCTION(BlueprintCallable, Category = "UI|Test")
	void FreezeTransitionForTest(const FString& Kind, float Progress);

	/** loading|login|select|sortie while visible, hidden when collapsed, none between screens. */
	UFUNCTION(BlueprintPure, Category = "UI|Test")
	FString GetScreenName() const;

	/** Entry point of the paint child widget (not for Blueprint). */
	int32 PaintFrontEnd(const FGeometry& Geometry, FSlateWindowElementList& Out, int32 LayerId) const;

protected:
	virtual TSharedRef<SWidget> RebuildWidget() override;
	virtual void ReleaseSlateResources(bool bReleaseChildren) override;
	virtual void NativeConstruct() override;
	virtual void NativeDestruct() override;
	virtual void NativeTick(const FGeometry& MyGeometry, float InDeltaTime) override;
	virtual FReply NativeOnMouseButtonDown(const FGeometry& InGeometry, const FPointerEvent& InMouseEvent) override;
	virtual FReply NativeOnMouseButtonUp(const FGeometry& InGeometry, const FPointerEvent& InMouseEvent) override;
	virtual FReply NativeOnMouseMove(const FGeometry& InGeometry, const FPointerEvent& InMouseEvent) override;
	virtual FReply NativeOnMouseWheel(const FGeometry& InGeometry, const FPointerEvent& InMouseEvent) override;
	virtual void NativeOnMouseLeave(const FPointerEvent& InMouseEvent) override;
	virtual FCursorReply NativeOnCursorQuery(const FGeometry& InGeometry, const FPointerEvent& InCursorEvent) override;

private:
	// ---- widgets
	UPROPERTY() TObjectPtr<UCanvasPanel> RootCanvas;
	UPROPERTY() TObjectPtr<UNativeWidgetHost> PaintHost;
	UPROPERTY() TObjectPtr<UEditableText> CallsignText;
	UPROPERTY() TObjectPtr<UEditableText> PasswordText;
	TSharedPtr<SWidget> PaintWidget;
	TWeakObjectPtr<ATreadM1MatchController> Controller;

	UFUNCTION() void HandlePhaseChanged(ETreadM1Phase PreviousPhase, ETreadM1Phase NewPhase);
	UFUNCTION() void HandleStateChanged();
	UFUNCTION() void HandleCallsignChanged(const FText& Text);
	UFUNCTION() void HandlePasswordChanged(const FText& Text);
	UFUNCTION() void HandleInputCommitted(const FText& Text, ETextCommit::Type CommitMethod);

	ATreadM1MatchController* FindController() const;
	void BindController();
	UEditableText* MakeInputText(const TCHAR* Name, bool bPassword, int32 ZOrder);

	// ---- visibility / flow
	bool WantsVisible() const;
	void SyncVisibility();
	void ShowFrontEnd();
	void HideFrontEnd();
	void ResetFlow();
	void SetChromeTargets(EFrontScreen S, bool bHeld);
	void EnterScreen(EFrontScreen S, float ScanMs, bool bFinal);
	void LeaveScreen(EFrontScreen S);
	FFrontEnv EnvFor(EFrontScreen S, double Now) const;
	void BeginLoading();
	void BeginLogin();
	void BeginSelect();
	void BeginSortie();
	bool StartTransition(EFrontTrans Kind, EFrontScreen To, float Dir, const FString& Cap, const FString& Ru, bool bLaunch);
	void UpdateTransition(double Now);
	void LaunchMatch();
	void FinishExit();
	float TransElapsedMs(double Now) const;
	float ScanBarY(double Now) const;

	// ---- data
	void LoadStageExtras();
	void FinishStageText(FFrontStage& Stage);
	void RefreshStages();
	EFrontStageState StateOf(int32 StageNo) const;
	int32 ClearedCount() const;

	// ---- per frame
	void UpdateViewMetrics(const FVector2f& Size);
	void TickLoading(double Now);
	void TickLogin(double Now, float Dt);
	void TickSelect(double Now, float Dt);
	void TickSortie(double Now);
	void TickChrome(float Dt);
	void ComputeHover(const FVector2f& DesignPos, int32& OutBtn, int32& OutCard) const;
	void UpdateHover(double Now, float Dt);
	void ShowTip(int32 StageNo);
	void HideTip();
	bool AreInputsLive() const;
	void ApplyInputStyle();
	FVector2f ShakeOffset(double Now) const;
	void UpdateInputWidgets(double Now);
	void UpdateMouse(const FGeometry& Geometry, const FPointerEvent& MouseEvent);

	// ---- actions
	void HandleClick();
	void DoLogin();
	void SelectStage(int32 StageNo);
	void DoSortie();
	void DoFreeMatch();

	// ---- painting
	void DrawScreen(FFrontPaint& P, EFrontScreen Which, double Now) const;
	void DrawLoading(FFrontPaint& P, const FFrontEnv& Env) const;
	void DrawLogin(FFrontPaint& P, const FFrontEnv& Env) const;
	void DrawSelect(FFrontPaint& P, const FFrontEnv& Env) const;
	void DrawCards(FFrontPaint& P, const FFrontEnv& Env) const;
	void DrawDossier(FFrontPaint& P, const FFrontEnv& Env) const;
	void DrawTip(FFrontPaint& P, const FFrontEnv& Env) const;
	void DrawSortie(FFrontPaint& P, const FFrontEnv& Env) const;
	void DrawTransitionFx(FFrontPaint& P, double Now) const;
	void DrawChrome(FFrontPaint& P, double Now) const;

	// ---- state: visibility and flow
	bool bShownNow = false;
	bool bLoggedIn = false;
	bool bExitRunning = false;
	FString Commander;
	FFrontScreenRt Scr[5];
	EFrontScreen Current = EFrontScreen::None;
	FFrontTrans Trans;
	double LastTick = 0.0;
	double NextControllerSearch = 0.0;

	// ---- state: chrome (print furniture)
	bool bChromeHold = false;
	bool bChromeInit = false;
	int32 SheetNo = 1;
	FLinearColor ChromeTop = FLinearColor::Black, ChromeBottom = FLinearColor::Black, ChromeAccent = FLinearColor::Red;
	FLinearColor ChromeTopTarget = FLinearColor::Black, ChromeBottomTarget = FLinearColor::Black, ChromeAccentTarget = FLinearColor::Red;

	// ---- state: view and pointer
	FVector2f ViewSize = FVector2f(1920.0f, 1080.0f);
	float ViewScale = 1.0f;
	FVector2f ViewOrigin = FVector2f::ZeroVector;
	FVector2f MouseLocal = FVector2f::ZeroVector;
	FVector2f MouseDesign = FVector2f::ZeroVector;
	bool bMouseIn = false;
	int32 HoverBtn = -1;
	float BtnHover[BtnCount] = {};
	float CardHover[16] = {};
	int32 HoverCardMouse = 0;
	int32 ForcedHover = 0;
	int32 EffHover = 0;

	// ---- state: loading
	double LoadT0 = 0.0;
	float LoadStopMs = 1.0e9f;
	bool bLoadHold = false;
	bool bLoadFrozen = false;
	/** Set by the test hooks: pins the login ticker at its start phase (text fully inside the strip). */
	bool bTickerPinned = false;
	bool bLoadReady = false;
	double LoadReadyT = -1.0;
	double LoadGoAt = -1.0;
	double LastJitter = 0.0;
	FString PmIo = TEXT("000.0"), PmSync = TEXT("00.00"), PmBlk = TEXT("0x0000"), PmTemp = TEXT("00.0"), PmHz = TEXT("47.20");

	// ---- state: login
	EFrontLogin LoginPhase = EFrontLogin::Idle;
	double LoginT0 = -1.0;
	bool bLoginHold = false;
	double FocusAt = -1.0;
	float FocusBar[2] = {};
	float FocusLine[2] = {};
	FString CallsignValue;
	int32 PasswordLen = 0;
	float LastFontScale = -1.0f;
	float LastPaintScale = -1.0f;   // paint font scale the input styles were built for
	float FieldLineHeight = 40.0f;
	float PasswordLineHeight = 40.0f;   // password box uses a smaller font (bullet size), so its own line height

	// ---- state: select
	TArray<FFrontStage> Stages;
	TArray<FFrontStage> ExtraStages;
	bool bExtrasLoaded = false;
	double NextStageRefresh = 0.0;
	int32 SelIdx = 0;
	double SelChangeT = 0.0;
	bool bDosShown = false;
	double DosShowT = 0.0;
	int32 DosContent = 0;
	double SwapStartT = -1.0;
	int32 PendingSel = 0;
	double BlkInT = -1.0e9;
	double RollT0 = -1.0e9;
	double SortieStampT = -1.0;
	double SortieGoAt = -1.0;
	int32 SortieGoStage = 0;
	FString DosNotice;
	double DosNoticeT = 0.0;
	FString PmSelHz = TEXT("47.2");
	double NextSelHz = 0.0;
	int32 TipStage = 0;
	double TipShowT = -1.0;
	double TipHideT = -1.0;
	FVector2f TipPos = FVector2f::ZeroVector;
	int32 TipSide = 0;
	float TipH = 206.0f;
	TArray<FString> TipLand, TipRuleText, TipEff;

	// ---- state: sortie
	int32 SortieStage = 0;
	bool bSortieHold = false;
	double SortieDoneT = -1.0;
	bool bLaunchStarted = false;
};
