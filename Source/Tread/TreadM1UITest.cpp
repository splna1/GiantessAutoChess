#include "TreadM1UITest.h"

#include "Blueprint/WidgetBlueprintLibrary.h"
#include "Blueprint/WidgetTree.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Engine/GameViewportClient.h"
#include "EngineUtils.h"
#include "Framework/Application/SlateApplication.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformTime.h"
#include "Input/Events.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "TreadDragController.h"
#include "TreadM1MatchController.h"
#include "TreadM1MatchWidget.h"
#include "TreadM1PlayerController.h"
#include "UnrealClient.h"
#include "Widgets/SWindow.h"

namespace
{
	FVector2D BoardCenter(FIntPoint Cell)
	{
		return FVector2D(535.0f + (Cell.X + 0.5f) * 88.0f, 216.0f + (Cell.Y + 0.5f) * 88.0f);
	}
}

UTreadM1UITest::UTreadM1UITest()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = false;
}

void UTreadM1UITest::BeginPlay()
{
	Super::BeginPlay();
	if (FParse::Param(FCommandLine::Get(), TEXT("TreadM1UITest"))) StartTest();
}

void UTreadM1UITest::StartTest()
{
	if (bRunning) return;
	bRunning = true;
	bLastRunPassed = false;
	bFullGameMode = FParse::Param(FCommandLine::Get(), TEXT("TreadM1UITest")) &&
		FParse::Param(FCommandLine::Get(), TEXT("TreadM1UIFullTest"));
	bFull12Mode = bFullGameMode && FParse::Param(FCommandLine::Get(), TEXT("TreadM1UIFull12"));
	bExitOnComplete = GetWorld() && GetWorld()->WorldType != EWorldType::PIE &&
		FParse::Param(FCommandLine::Get(), TEXT("TreadM1UITest")) &&
		!FParse::Param(FCommandLine::Get(), TEXT("TreadM1UITestNoExit"));
	Step = 0;
	Checks.Reset();
	Inputs.Reset();
	Rounds.Reset();
	RoundHuds.Reset();
	FinalRanking.Reset();
	Screenshots.Reset();
	bRevisedStrategy = false;
	bSettlementReadyForClick = false;
	bHudReadyForDeploy = false;
	bFull12FixtureApplied = false;
	ScoutIndex = 0;
	FullRoundIndex = 0;
	RoundTwoPreparationAt = 0.0;
	RoundTwoAutoTransitionSeconds = 0.0;
	BattleStartedAt = 0.0;
	StartedAt = FPlatformTime::Seconds();
	NextActionAt = StartedAt + 1.0;
	const TCHAR* ScreenshotFolder = bFull12Mode ? TEXT("Reports/M1_UI_Full12") :
		(bFullGameMode ? TEXT("Reports/M1_UI_FullGame") : TEXT("Reports/M1_UI_Smoke"));
	ScreenshotDirectory = FPaths::ConvertRelativePathToFull(FPaths::Combine(FPaths::ProjectSavedDir(),
		ScreenshotFolder, FGuid::NewGuid().ToString(EGuidFormats::Digits)));
	IFileManager::Get().MakeDirectory(*ScreenshotDirectory, true);
	SetComponentTickEnabled(true);
}

bool UTreadM1UITest::Check(const FString& Name, bool bPassed, const FString& Detail)
{
	TSharedPtr<FJsonObject> Entry = MakeShared<FJsonObject>();
	Entry->SetStringField(TEXT("name"), Name);
	Entry->SetBoolField(TEXT("passed"), bPassed);
	Entry->SetStringField(TEXT("detail"), Detail);
	Entry->SetNumberField(TEXT("step"), Step);
	Entry->SetNumberField(TEXT("elapsedSeconds"), FPlatformTime::Seconds() - StartedAt);
	Checks.Add(Entry);
	if (!bPassed) Finish(false);
	return bPassed;
}

void UTreadM1UITest::SendPointer(FVector2D ReferencePosition, int32 Action)
{
	if (!Widget.IsValid() || !FSlateApplication::IsInitialized()) return;
	const FGeometry& Geometry = Widget->GetCachedGeometry();
	const FVector2D Size = Geometry.GetLocalSize();
	const float Scale = FMath::Max(0.01f, FMath::Min(Size.X / 1920.0f, Size.Y / 1080.0f));
	const FVector2D Absolute = Geometry.LocalToAbsolute(ReferencePosition * Scale);
	FSlateApplication& Slate = FSlateApplication::Get();
	const FVector2D Previous = Slate.GetCursorPos();
	Slate.SetCursorPos(Absolute);
	if (Action == 1) bLeftPressed = true;
	if (Action == 2) bLeftPressed = false;
	TSet<FKey> Buttons;
	if (bLeftPressed) Buttons.Add(EKeys::LeftMouseButton);
	const FPointerEvent Event(Slate.GetUserIndexForMouse(), FSlateApplication::CursorPointerIndex, Absolute, Previous, Buttons,
		Action == 0 ? EKeys::Invalid : EKeys::LeftMouseButton, 0.0f, FModifierKeysState());
	bool bHandled = false;
	if (Action == 0) bHandled = Slate.ProcessMouseMoveEvent(Event);
	else if (Action == 1)
	{
		const TSharedPtr<SWindow> Window = GetWorld()->GetGameViewport()->GetWindow();
		bHandled = Slate.ProcessMouseButtonDownEvent(Window.IsValid() ? Window->GetNativeWindow() : nullptr, Event);
	}
	else bHandled = Slate.ProcessMouseButtonUpEvent(Event);
	TSharedPtr<FJsonObject> Input = MakeShared<FJsonObject>();
	Input->SetNumberField(TEXT("step"), Step);
	Input->SetStringField(TEXT("event"), Action == 0 ? TEXT("Move") : Action == 1 ? TEXT("Down") : TEXT("Up"));
	Input->SetNumberField(TEXT("referenceX"), ReferencePosition.X);
	Input->SetNumberField(TEXT("referenceY"), ReferencePosition.Y);
	Input->SetBoolField(TEXT("handled"), bHandled);
	Inputs.Add(Input);
}

void UTreadM1UITest::Click(FVector2D Position)
{
	SendPointer(Position, 0);
	SendPointer(Position, 1);
	SendPointer(Position, 2);
}

void UTreadM1UITest::Drag(FVector2D Source, FVector2D Target)
{
	SendPointer(Source, 0);
	SendPointer(Source, 1);
	SendPointer((Source + Target) * 0.5f, 0);
	SendPointer(Target, 0);
	SendPointer(Target, 2);
}

FVector2D UTreadM1UITest::BenchPosition(const FString& UnitId) const
{
	const int32 Index = Match->MatchState.Players[0].BenchUnitInstanceIds.Find(UnitId);
	return FVector2D(682.0f + Index * 108.0f, 1019.0f);
}

FIntPoint UTreadM1UITest::UnitCell(const FString& UnitId) const
{
	const FTreadM1UnitInstance* Unit = Match->MatchState.Players[0].BoardUnits.FindByPredicate([&UnitId](const FTreadM1UnitInstance& Candidate) { return Candidate.UnitInstanceId == UnitId; });
	return Unit ? Unit->BoardCell : FIntPoint(-1, -1);
}

FString UTreadM1UITest::HumanRosterSignature() const
{
	if (!Match.IsValid() || Match->MatchState.Players.IsEmpty()) return TEXT("missing");
	const FTreadM1PlayerState& Player = Match->MatchState.Players[0];
	TArray<FString> Parts;
	Parts.Add(FString::Printf(TEXT("population:%d"), Player.PopulationUsed));
	for (const FString& UnitId : Player.BenchUnitInstanceIds) Parts.Add(TEXT("slot:") + UnitId);
	for (const FTreadM1UnitInstance& Unit : Player.BenchUnits) Parts.Add(TEXT("bench:") + Unit.UnitInstanceId);
	for (const FTreadM1UnitInstance& Unit : Player.BoardUnits)
		Parts.Add(FString::Printf(TEXT("board:%s:%d:%d"), *Unit.UnitInstanceId, Unit.BoardCell.X, Unit.BoardCell.Y));
	return FString::Join(Parts, TEXT("|"));
}

FString UTreadM1UITest::HumanShopSignature() const
{
	if (!Match.IsValid() || Match->MatchState.Players.IsEmpty()) return TEXT("missing");
	const FTreadM1ShopState& Shop = Match->MatchState.Players[0].Shop;
	TArray<FString> Parts;
	Parts.Add(FString::Printf(TEXT("refresh:%d:locked:%d"), Shop.RefreshIndex, Shop.bLocked ? 1 : 0));
	for (const FTreadM1ShopSlot& Slot : Shop.Slots)
		Parts.Add(FString::Printf(TEXT("%d:%s:%d"), Slot.SlotIndex, *Slot.CharacterId, Slot.bIsSold ? 1 : 0));
	return FString::Join(Parts, TEXT("|"));
}

bool UTreadM1UITest::RecordRoundResult(int32 ExpectedRound)
{
	if (!Match.IsValid()) return Check(TEXT("round_result_missing_match"), false);
	const FTreadM1MatchState& State = Match->MatchState;
	if (!Check(FString::Printf(TEXT("round_%d_result"), ExpectedRound),
		State.Phase == ETreadM1Phase::Settlement && State.RoundIndex == ExpectedRound &&
		State.LastBattleResult.RoundIndex == ExpectedRound && State.LastBattleResult.Outcomes.Num() >= 2)) return false;
	const double BattleElapsed = FPlatformTime::Seconds() - BattleStartedAt;
	if (bFull12Mode && !Check(FString::Printf(TEXT("round_%d_45s_battle_timer"), ExpectedRound),
		BattleStartedAt > 0.0 && BattleElapsed >= 38.0 && BattleElapsed <= 55.0,
		FString::Printf(TEXT("elapsed %.2fs"), BattleElapsed))) return false;
	TSharedPtr<FJsonObject> Entry = MakeShared<FJsonObject>();
	Entry->SetNumberField(TEXT("round"), ExpectedRound);
	Entry->SetStringField(TEXT("roundType"), UEnum::GetValueAsString(State.RoundType));
	Entry->SetNumberField(TEXT("outcomes"), State.LastBattleResult.Outcomes.Num());
	Entry->SetNumberField(TEXT("pairings"), State.LastBattleResult.Pairings.Num());
	Entry->SetNumberField(TEXT("humanHealth"), State.Players[0].Health);
	Entry->SetNumberField(TEXT("humanRank"), State.Players[0].Rank);
	if (bFull12Mode) Entry->SetNumberField(TEXT("battleElapsedSeconds"), BattleElapsed);
	Rounds.Add(Entry);
	return true;
}

bool UTreadM1UITest::RecordRoundHud(int32 ExpectedRound)
{
	if (!Match.IsValid() || !Widget.IsValid() || !Widget->WidgetTree) return Check(TEXT("round_hud_missing_objects"), false);
	const FTreadM1MatchState& State = Match->MatchState;
	const ETreadM1RoundType ExpectedType = ExpectedRound <= 2 ? ETreadM1RoundType::PvE :
		(ExpectedRound <= 11 ? ETreadM1RoundType::PvP : ETreadM1RoundType::Leader);
	const UWidget* Deploy = Widget->WidgetTree->FindWidget(TEXT("Deploy"));
	int32 Width = 0, Height = 0;
	if (APlayerController* PC = Cast<APlayerController>(GetOwner())) PC->GetViewportSize(Width, Height);
	if (!Check(FString::Printf(TEXT("round_%d_preparation_hud"), ExpectedRound),
		State.RoundIndex == ExpectedRound && State.RoundType == ExpectedType &&
		State.Phase == ETreadM1Phase::Preparation &&
		State.PhaseTimeRemainingSec > 0.0f &&
		Deploy && Deploy->GetVisibility() == ESlateVisibility::Visible &&
		Width == 1920 && Height == 1080,
		FString::Printf(TEXT("type=%s phase=%s timer=%.1f viewport=%dx%d"),
			*UEnum::GetValueAsString(State.RoundType), *UEnum::GetValueAsString(State.Phase),
			State.PhaseTimeRemainingSec, Width, Height))) return false;
	TSharedPtr<FJsonObject> Entry = MakeShared<FJsonObject>();
	Entry->SetNumberField(TEXT("round"), ExpectedRound);
	Entry->SetStringField(TEXT("hudPhase"), UEnum::GetValueAsString(State.Phase));
	Entry->SetStringField(TEXT("hudRoundType"), UEnum::GetValueAsString(State.RoundType));
	Entry->SetNumberField(TEXT("timerRemainingSeconds"), State.PhaseTimeRemainingSec);
	Entry->SetBoolField(TEXT("deployButtonVisible"), true);
	Entry->SetNumberField(TEXT("viewportWidth"), Width);
	Entry->SetNumberField(TEXT("viewportHeight"), Height);
	RoundHuds.Add(Entry);
	return true;
}

bool UTreadM1UITest::CheckGameOver()
{
	if (!Match.IsValid() || !Widget.IsValid()) return Check(TEXT("game_over_objects"), false);
	const FTreadM1MatchState& State = Match->MatchState;
	if (!Check(TEXT("natural_game_over"), State.Phase == ETreadM1Phase::GameOver &&
		State.RoundIndex >= 2 && State.RoundIndex <= 12 &&
		State.LastBattleResult.RoundIndex == State.RoundIndex && State.LastBattleResult.Outcomes.Num() >= 2)) return false;
	if (bFull12Mode && !Check(TEXT("full12_leader_game_over"), bFull12FixtureApplied &&
		State.RoundIndex == 12 && State.RoundType == ETreadM1RoundType::Leader &&
		Rounds.Num() == 12 && RoundHuds.Num() == 12)) return false;
	if (bFull12Mode)
	{
		int32 Width = 0, Height = 0;
		if (APlayerController* PC = Cast<APlayerController>(GetOwner())) PC->GetViewportSize(Width, Height);
		if (!Check(TEXT("full12_final_viewport_1920x1080"), Width == 1920 && Height == 1080)) return false;
	}
	TSet<int32> Ranks;
	TArray<TSharedPtr<FJsonValue>> Players;
	for (const FTreadM1PlayerState& Player : State.Players)
	{
		Ranks.Add(Player.Rank);
	}
	if (!Check(TEXT("four_final_ranks"), State.Players.Num() == 4 && Ranks.Num() == 4 &&
		Ranks.Contains(1) && Ranks.Contains(2) && Ranks.Contains(3) && Ranks.Contains(4))) return false;
	for (int32 Rank = 1; Rank <= 4; ++Rank)
	{
		const FTreadM1PlayerState* Player = State.Players.FindByPredicate([Rank](const FTreadM1PlayerState& P) { return P.Rank == Rank; });
		if (!Player) return Check(TEXT("final_rank_row_missing"), false);
		TSharedPtr<FJsonObject> Row = MakeShared<FJsonObject>();
		Row->SetStringField(TEXT("playerId"), Player->PlayerId);
		Row->SetStringField(TEXT("displayName"), Player->DisplayName);
		Row->SetNumberField(TEXT("rank"), Player->Rank);
		Row->SetNumberField(TEXT("health"), Player->Health);
		Row->SetBoolField(TEXT("eliminated"), Player->bIsEliminated);
		Players.Add(MakeShared<FJsonValueObject>(Row));
	}
	const UWidget* Continue = Widget->WidgetTree ? Widget->WidgetTree->FindWidget(TEXT("Continue")) : nullptr;
	if (!Check(TEXT("final_ranking_modal_visible"), Continue && Continue->GetVisibility() == ESlateVisibility::Visible)) return false;
	FinalRanking = MakeShared<FJsonObject>();
	FinalRanking->SetNumberField(TEXT("round"), State.RoundIndex);
	FinalRanking->SetArrayField(TEXT("rankedPlayers"), Players);
	FinalRanking->SetNumberField(TEXT("lastRoundOutcomes"), State.LastBattleResult.Outcomes.Num());
	return true;
}

void UTreadM1UITest::Capture(const FString& Stage)
{
	const FString Path = FPaths::Combine(ScreenshotDirectory, Stage + TEXT(".png"));
	Screenshots.Add(Path);
	FScreenshotRequest::RequestScreenshot(Path, true, false, false, FIntRect(), true);
}

void UTreadM1UITest::AdvanceStep()
{
	++Step;
	NextActionAt = FPlatformTime::Seconds() + 0.35;
}

void UTreadM1UITest::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	if (!bRunning) return;
	const double Now = FPlatformTime::Seconds();
	const double TimeoutSeconds = bFull12Mode ? 1200.0 : (bFullGameMode ? 900.0 : 120.0);
	if (Now - StartedAt > TimeoutSeconds)
	{
		Check(TEXT("run_timeout"), false, FString::Printf(TEXT("Live Slate flow exceeded %.0f seconds"), TimeoutSeconds));
		return;
	}
	if (Now < NextActionAt) return;
	if (!Match.IsValid()) for (TActorIterator<ATreadM1MatchController> It(GetWorld()); It; ++It) { Match = *It; break; }
	if (!Widget.IsValid())
	{
		TArray<UUserWidget*> Widgets;
		UWidgetBlueprintLibrary::GetAllWidgetsOfClass(this, Widgets, UTreadM1MatchWidget::StaticClass(), true);
		for (UUserWidget* Candidate : Widgets) if (Candidate->GetWorld() == GetWorld()) { Widget = Cast<UTreadM1MatchWidget>(Candidate); break; }
	}
	if (!Match.IsValid() || !Widget.IsValid() || !FSlateApplication::IsInitialized() || !GetWorld()->GetGameViewport() || Widget->GetCachedGeometry().GetLocalSize().X < 10.0f) return;
	ATreadM1PlayerController* PC = Cast<ATreadM1PlayerController>(GetOwner());
	if (!PC || !PC->DragController || Match->MatchState.Players.Num() == 0) return;
	const FTreadM1PlayerState& Player = Match->MatchState.Players[0];
	UTreadDragController* DragController = PC->DragController;
	const auto BenchContains = [&]() { return Player.BenchUnitInstanceIds.Contains(DraggedUnitId); };
	const auto ConfirmedAIs = [&]() { return Match->MatchState.BP.AiPickStates.FilterByPredicate([](ETreadM1AIPickState State) { return State == ETreadM1AIPickState::Confirmed; }).Num(); };
	switch (Step)
	{
	case 0:
		if (!Check(TEXT("initial_menu"), Match->GetPhase() == ETreadM1Phase::R0Briefing)) return;
		Click(FVector2D(960, 698));
		break;
	case 1:
		if (!Check(TEXT("menu_click_opens_bp"), Match->GetPhase() == ETreadM1Phase::PreMatchBP)) return;
		Click(FVector2D(90, 280));
		break;
	case 2:
		if (!Check(TEXT("bp_card_selects_strategy"), !Match->MatchState.BP.PlayerStrategyId.IsEmpty())) return;
		FirstStrategyId = Match->MatchState.BP.PlayerStrategyId;
		Capture(TEXT("BP"));
		Click(FVector2D(1590, 964));
		break;
	case 3:
	case 5:
		if (!Check(FString::Printf(TEXT("confirm_ai_%d"), Step - 2), ConfirmedAIs() == Step - 2 && Match->GetPhase() == ETreadM1Phase::PreMatchBP)) return;
		Click(FVector2D(1590, 964));
		break;
	case 4:
		if (!Check(TEXT("two_ai_confirmed_before_revision"), ConfirmedAIs() == 2 && Match->GetPhase() == ETreadM1Phase::PreMatchBP)) return;
		if (!bRevisedStrategy)
		{
			int32 RevisionIndex = INDEX_NONE;
			for (int32 Index = 0; Index < Match->MatchState.BP.AvailableStrategyIds.Num(); ++Index)
			{
				const FString& Candidate = Match->MatchState.BP.AvailableStrategyIds[Index];
				if (Candidate != FirstStrategyId && !Match->MatchState.BP.AiStrategyIds.Contains(Candidate)) { RevisionIndex = Index; break; }
			}
			if (!Check(TEXT("bp_revision_candidate_available"), RevisionIndex != INDEX_NONE)) return;
			RevisedStrategyId = Match->MatchState.BP.AvailableStrategyIds[RevisionIndex];
			Click(FVector2D(90 + (RevisionIndex % 8) * 158, 280 + (RevisionIndex / 8) * 186));
			bRevisedStrategy = true;
			NextActionAt = Now + 0.35;
			return;
		}
		if (!Check(TEXT("bp_revised_before_final_ai"), Match->MatchState.BP.PlayerStrategyId == RevisedStrategyId &&
			Match->MatchState.BP.PlayerStrategyId != FirstStrategyId && ConfirmedAIs() == 2)) return;
		Capture(TEXT("BP_Revised"));
		Click(FVector2D(1590, 964));
		break;
	case 6:
		if (!Check(TEXT("bp_confirm_enters_preparation"), Match->GetPhase() == ETreadM1Phase::Preparation && Player.BenchUnits.Num() > 0 && Player.BoardUnits.Num() > 0)) return;
		if (bFull12Mode)
		{
			if (!Check(TEXT("full12_fixture_four_players"), Match->MatchState.RoundIndex == 1 &&
				Match->MatchState.Players.Num() == 4 && !bFull12FixtureApplied)) return;
			// This is the fixture's sole direct match-state mutation. Every later
			// transition and player action still comes from Slate mouse input/timers.
			for (FTreadM1PlayerState& FixturePlayer : Match->MatchState.Players) FixturePlayer.Health = 1000;
			bFull12FixtureApplied = true;
			Match->OnStateChanged.Broadcast();
			if (!RecordRoundHud(1)) return;
		}
		Capture(TEXT("Preparation"));
		DraggedUnitId = Player.BenchUnits[0].UnitInstanceId;
		SwappedUnitId = Player.BoardUnits[0].UnitInstanceId;
		ExpectedCost = Player.BenchUnits[0].Cost;
		FundsBefore = Player.Funds;
		Drag(BenchPosition(DraggedUnitId), BoardCenter(FIntPoint(0, 6)));
		break;
	case 7:
		if (!Check(TEXT("bench_to_board_release"), UnitCell(DraggedUnitId) == FIntPoint(0, 6) && DragController->GetDragState() == ETreadDragState::Idle)) return;
		Drag(BoardCenter(FIntPoint(0, 6)), BoardCenter(UnitCell(SwappedUnitId)));
		break;
	case 8:
		if (!Check(TEXT("board_swap"), UnitCell(SwappedUnitId) == FIntPoint(0, 6) && UnitCell(DraggedUnitId) == FIntPoint(2, 5))) return;
		Drag(BoardCenter(UnitCell(DraggedUnitId)), FVector2D(682, 1019));
		break;
	case 9:
		if (!Check(TEXT("board_to_bench_release"), BenchContains() && UnitCell(DraggedUnitId).X == -1)) return;
		Drag(BenchPosition(DraggedUnitId), BoardCenter(FIntPoint(0, 1)));
		break;
	case 10:
		if (!Check(TEXT("illegal_enemy_half_returns_source"), BenchContains() && DragController->GetDragState() == ETreadDragState::Idle)) return;
		Drag(BenchPosition(DraggedUnitId), FVector2D(400, 800));
		break;
	case 11:
		if (!Check(TEXT("illegal_outside_returns_source"), BenchContains() && DragController->GetDragState() == ETreadDragState::Idle)) return;
		Drag(BenchPosition(DraggedUnitId), FVector2D(160, 1019));
		break;
	case 12:
		if (!Check(TEXT("sell_release_once"), !BenchContains() && Player.Funds == FundsBefore + ExpectedCost)) return;
		FundsBefore = Player.Funds;
		SendPointer(FVector2D(160, 1019), 2);
		break;
	case 13:
		if (!Check(TEXT("duplicate_release_does_not_sell_twice"), Player.Funds == FundsBefore && DragController->GetDragState() == ETreadDragState::Idle)) return;
		ShopSlot = INDEX_NONE;
		for (int32 Index = 0; Index < Player.Shop.Slots.Num(); ++Index)
			if (!Player.Shop.Slots[Index].bIsSold && (ShopSlot == INDEX_NONE || Player.Shop.Slots[Index].Cost < Player.Shop.Slots[ShopSlot].Cost)) ShopSlot = Index;
		if (!Check(TEXT("shop_has_affordable_card"), ShopSlot != INDEX_NONE && Player.Shop.Slots[ShopSlot].Cost <= Player.Funds)) return;
		ExpectedCost = Player.Shop.Slots[ShopSlot].Cost;
		Click(FVector2D(1748, 212 + ShopSlot * 74));
		break;
	case 14:
		if (!Check(TEXT("shop_purchase_click"), Player.Shop.Slots[ShopSlot].bIsSold && Player.Funds == FundsBefore - ExpectedCost)) return;
		Click(FVector2D(1845, 141));
		break;
	case 15:
		if (!Check(TEXT("lock_shop_click"), Player.Shop.bLocked)) return;
		Click(FVector2D(1845, 141));
		break;
	case 16:
		if (!Check(TEXT("unlock_shop_click"), !Player.Shop.bLocked)) return;
		FundsBefore = Player.Funds;
		RefreshBefore = Player.Shop.RefreshIndex;
		Click(FVector2D(1673, 577));
		break;
	case 17:
		if (!Check(TEXT("refresh_shop_click"), Player.Shop.RefreshIndex == RefreshBefore + 1 && Player.Funds == FundsBefore - Match->MatchState.Rules.ShopRefreshCost)) return;
		FundsBefore = Player.Funds;
		ExperienceBefore = Player.Experience;
		Click(FVector2D(1823, 577));
		break;
	case 18:
		if (!Check(TEXT("experience_click"), Player.Funds == FundsBefore - Match->MatchState.Rules.ExperiencePurchaseCost && Player.Experience != ExperienceBefore)) return;
		ScoutPoolRevisionBefore = Match->MatchState.PoolLedger.Revision;
		ScoutPoolEntriesBefore = Match->MatchState.PoolLedger.Entries.Num();
		ScoutFundsBefore = Player.Funds;
		BattleRosterBefore = HumanRosterSignature();
		BattleShopBefore = HumanShopSignature();
		ScoutIndex = 0;
		Click(FVector2D(1480, 37));
		break;
	case 19:
		{
			const UWidget* Close = Widget->WidgetTree->FindWidget(TEXT("ScoutClose"));
			if (!Check(FString::Printf(TEXT("scout_player_%d_read_only"), ScoutIndex),
				Close && Close->GetVisibility() == ESlateVisibility::Visible &&
				Widget->GetScoutPlayerIndex() == ScoutIndex &&
				Match->MatchState.Players.IsValidIndex(ScoutIndex) &&
				Match->MatchState.ScoutSnapshots.IsValidIndex(ScoutIndex) &&
				Match->MatchState.ScoutSnapshots[ScoutIndex].bReadOnly &&
				Match->MatchState.ScoutSnapshots[ScoutIndex].PlayerId == Match->MatchState.Players[ScoutIndex].PlayerId &&
				Match->MatchState.ScoutSnapshots[ScoutIndex].BoardUnits.Num() == Match->MatchState.Players[ScoutIndex].BoardUnits.Num() &&
				Match->MatchState.PoolLedger.Revision == ScoutPoolRevisionBefore &&
				Match->MatchState.PoolLedger.Entries.Num() == ScoutPoolEntriesBefore &&
				Player.Funds == ScoutFundsBefore && HumanRosterSignature() == BattleRosterBefore &&
				HumanShopSignature() == BattleShopBefore)) return;
			Capture(ScoutIndex == 3 ? TEXT("Scout") : FString::Printf(TEXT("Scout_Player_%d"), ScoutIndex));
			if (ScoutIndex < 3)
			{
				++ScoutIndex;
				Click(FVector2D(1480 + (ScoutIndex % 2) * 276, 37 + (ScoutIndex / 2) * 38));
				NextActionAt = Now + 0.35;
				return;
			}
			LastDragSession = DragController->GetDragSessionId();
			Drag(BoardCenter(UnitCell(SwappedUnitId)), BoardCenter(FIntPoint(1, 6)));
		}
		break;
	case 20:
		if (!Check(TEXT("scout_blocks_drag"), DragController->GetDragSessionId() == LastDragSession && UnitCell(SwappedUnitId) == FIntPoint(0, 6))) return;
		Click(FVector2D(1525, 135));
		break;
	case 21:
		{
			const UWidget* Close = Widget->WidgetTree->FindWidget(TEXT("ScoutClose"));
			if (!Check(TEXT("close_scout_click"), Close && Close->GetVisibility() == ESlateVisibility::Collapsed)) return;
			Click(FVector2D(1795, 1021));
		}
		break;
	case 22:
		if (!Check(TEXT("deploy_click_starts_battle"), Match->GetPhase() == ETreadM1Phase::Battle)) return;
		RoundBefore = Match->MatchState.RoundIndex;
		BattleStartedAt = Now;
		Capture(TEXT("Battle"));
		break;
	case 23:
		if (Match->GetPhase() == ETreadM1Phase::Battle) return;
		if (!Check(TEXT("natural_battle_reaches_settlement"), Match->GetPhase() == ETreadM1Phase::Settlement && Match->MatchState.LastBattleResult.Outcomes.Num() > 0)) return;
		if (bFullGameMode && !RecordRoundResult(1)) return;
		Capture(TEXT("Result"));
		break;
	case 24:
		Click(FVector2D(1530, 932));
		break;
	case 25:
		if (!Check(TEXT("continue_click_starts_next_round"), Match->GetPhase() == ETreadM1Phase::Preparation && Match->MatchState.RoundIndex == RoundBefore + 1)) return;
		for (const FString& Path : Screenshots) if (!Check(TEXT("screenshot_written"), IFileManager::Get().FileSize(*Path) > 0, Path)) return;
		if (!bFullGameMode) { Finish(true); return; }
		if (bFull12Mode && !RecordRoundHud(2)) return;
		FullRoundIndex = 2;
		RoundTwoPreparationAt = Now;
		break;
	case 26:
		if (Match->GetPhase() == ETreadM1Phase::Preparation) return;
		RoundTwoAutoTransitionSeconds = Now - RoundTwoPreparationAt;
		if (!Check(TEXT("round_2_preparation_timer_auto_deploy"),
			Match->GetPhase() == ETreadM1Phase::Battle && Match->MatchState.RoundIndex == 2 &&
			FMath::Abs(RoundTwoAutoTransitionSeconds - Match->MatchState.Rules.PreparationDurationSec) <= 5.0,
			FString::Printf(TEXT("elapsed %.2fs, configured %ds"), RoundTwoAutoTransitionSeconds,
				Match->MatchState.Rules.PreparationDurationSec))) return;
		BattleRosterBefore = HumanRosterSignature();
		BattleShopBefore = HumanShopSignature();
		BattleFundsBefore = Player.Funds;
		BattleStartedAt = Now;
		LastDragSession = DragController->GetDragSessionId();
		Drag(BoardCenter(UnitCell(SwappedUnitId)), BoardCenter(FIntPoint(7, 7)));
		break;
	case 27:
		if (!Check(TEXT("battle_rejects_mouse_drag"), Match->GetPhase() == ETreadM1Phase::Battle &&
			HumanRosterSignature() == BattleRosterBefore && Player.Funds == BattleFundsBefore &&
			DragController->GetDragSessionId() == LastDragSession)) return;
		Click(FVector2D(1748, 212));
		break;
	case 28:
		if (!Check(TEXT("battle_rejects_shop_click"), Match->GetPhase() == ETreadM1Phase::Battle &&
			HumanRosterSignature() == BattleRosterBefore && HumanShopSignature() == BattleShopBefore &&
			Player.Funds == BattleFundsBefore)) return;
		break;
	case 29:
		if (!bSettlementReadyForClick)
		{
			if (Match->GetPhase() == ETreadM1Phase::Battle) return;
			if (!RecordRoundResult(2)) return;
			Capture(TEXT("Round_2_Result"));
			bSettlementReadyForClick = true;
			NextActionAt = Now + 0.35; // Let UMG NativeTick expose the result button.
			return;
		}
		if (!Check(TEXT("round_2_continue_button_visible"), Match->GetPhase() == ETreadM1Phase::Settlement &&
			Widget->WidgetTree->FindWidget(TEXT("Continue")) &&
			Widget->WidgetTree->FindWidget(TEXT("Continue"))->GetVisibility() == ESlateVisibility::Visible)) return;
		Click(FVector2D(1530, 932));
		bSettlementReadyForClick = false;
		break;
	case 30:
		if (Match->GetPhase() == ETreadM1Phase::GameOver)
		{
			if (bFull12Mode && !Check(TEXT("full12_no_early_game_over"), false,
				FString::Printf(TEXT("GameOver after round %d"), Match->MatchState.RoundIndex))) return;
			Step = 34;
			break;
		}
		if (!Check(TEXT("round_3_after_continue"), Match->GetPhase() == ETreadM1Phase::Preparation && Match->MatchState.RoundIndex == 3,
			FString::Printf(TEXT("phase=%s round=%d lastReleaseDrag=%d"), *UEnum::GetValueAsString(Match->GetPhase()),
				Match->MatchState.RoundIndex, DragController->WasLastReleaseDrag() ? 1 : 0))) return;
		FullRoundIndex = 3;
		break;
	case 31:
		if (!Check(FString::Printf(TEXT("round_%d_preparation"), FullRoundIndex),
			Match->GetPhase() == ETreadM1Phase::Preparation && Match->MatchState.RoundIndex == FullRoundIndex)) return;
		if (bFull12Mode && !bHudReadyForDeploy)
		{
			if (!RecordRoundHud(FullRoundIndex)) return;
			if (FullRoundIndex == 3) Capture(TEXT("Round_3_PvP"));
			if (FullRoundIndex == 12) Capture(TEXT("Round_12_Leader"));
			bHudReadyForDeploy = true;
			NextActionAt = Now + 0.35; // Render the HUD capture before pressing Deploy.
			return;
		}
		Click(FVector2D(1795, 1021));
		bHudReadyForDeploy = false;
		break;
	case 32:
		if (!Check(FString::Printf(TEXT("round_%d_deploy_button"), FullRoundIndex),
			Match->GetPhase() == ETreadM1Phase::Battle && Match->MatchState.RoundIndex == FullRoundIndex)) return;
		BattleStartedAt = Now;
		break;
	case 33:
		if (!bSettlementReadyForClick)
		{
			if (Match->GetPhase() == ETreadM1Phase::Battle) return;
			if (!RecordRoundResult(FullRoundIndex)) return;
			bSettlementReadyForClick = true;
			NextActionAt = Now + 0.35;
			return;
		}
		if (!Check(FString::Printf(TEXT("round_%d_continue_button_visible"), FullRoundIndex),
			Match->GetPhase() == ETreadM1Phase::Settlement &&
			Widget->WidgetTree->FindWidget(TEXT("Continue")) &&
			Widget->WidgetTree->FindWidget(TEXT("Continue"))->GetVisibility() == ESlateVisibility::Visible)) return;
		Click(FVector2D(1530, 932));
		bSettlementReadyForClick = false;
		break;
	case 34:
		if (Match->GetPhase() == ETreadM1Phase::GameOver)
		{
			if (bFull12Mode && !Check(TEXT("full12_no_early_game_over"), FullRoundIndex == 12,
				FString::Printf(TEXT("GameOver after round %d"), FullRoundIndex))) return;
			break;
		}
		if (!Check(FString::Printf(TEXT("round_%d_continue"), FullRoundIndex),
			Match->GetPhase() == ETreadM1Phase::Preparation && Match->MatchState.RoundIndex == FullRoundIndex + 1 &&
			FullRoundIndex < 12,
			FString::Printf(TEXT("phase=%s round=%d lastReleaseDrag=%d"), *UEnum::GetValueAsString(Match->GetPhase()),
				Match->MatchState.RoundIndex, DragController->WasLastReleaseDrag() ? 1 : 0))) return;
		++FullRoundIndex;
		Step = 30; // AdvanceStep returns to the preparation button for the next round.
		break;
	case 35:
		if (!CheckGameOver()) return;
		Capture(TEXT("GameOver"));
		break;
	case 36:
		if (IFileManager::Get().FileSize(*FPaths::Combine(ScreenshotDirectory, TEXT("GameOver.png"))) <= 0) return;
		for (const FString& Path : Screenshots)
			if (!Check(TEXT("full_game_screenshot_written"), IFileManager::Get().FileSize(*Path) > 0, Path)) return;
		Finish(true);
		return;
	default:
		Finish(false);
		return;
	}
	AdvanceStep();
}

void UTreadM1UITest::Finish(bool bPassed)
{
	if (!bRunning) return;
	bRunning = false;
	bLastRunPassed = bPassed;
	SetComponentTickEnabled(false);
	TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetBoolField(TEXT("passed"), bPassed);
	Root->SetStringField(TEXT("mode"), bFull12Mode ? TEXT("full12") : (bFullGameMode ? TEXT("fullGame") : TEXT("smoke")));
	Root->SetStringField(TEXT("inputPath"), TEXT("Live FSlateApplication mouse events -> native/WBP widget -> MatchController"));
	if (bFull12Mode)
	{
		Root->SetBoolField(TEXT("fixtureAppliedAtRound1"), bFull12FixtureApplied);
		Root->SetNumberField(TEXT("fixturePlayerHealth"), 1000);
		Root->SetStringField(TEXT("fixtureScope"), TEXT("Set four player Health fields once after BP; all subsequent actions use Slate input or live timers"));
	}
	Root->SetStringField(TEXT("worldType"), GetWorld() && GetWorld()->WorldType == EWorldType::PIE ? TEXT("PIE") : TEXT("Game"));
	Root->SetStringField(TEXT("timestampUtc"), FDateTime::UtcNow().ToIso8601());
	Root->SetNumberField(TEXT("elapsedSeconds"), FPlatformTime::Seconds() - StartedAt);
	Root->SetNumberField(TEXT("lastStep"), Step);
	if (Match.IsValid())
	{
		Root->SetStringField(TEXT("phase"), UEnum::GetValueAsString(Match->GetPhase()));
		Root->SetNumberField(TEXT("seed"), Match->MatchState.Seed);
		Root->SetNumberField(TEXT("round"), Match->MatchState.RoundIndex);
	}
	int32 Width = 0, Height = 0;
	if (APlayerController* PC = Cast<APlayerController>(GetOwner())) PC->GetViewportSize(Width, Height);
	Root->SetNumberField(TEXT("viewportWidth"), Width);
	Root->SetNumberField(TEXT("viewportHeight"), Height);
	TArray<TSharedPtr<FJsonValue>> CheckValues, InputValues, ShotValues, RoundValues, HudValues;
	for (const TSharedPtr<FJsonObject>& Entry : Checks) CheckValues.Add(MakeShared<FJsonValueObject>(Entry));
	for (const TSharedPtr<FJsonObject>& Entry : Inputs) InputValues.Add(MakeShared<FJsonValueObject>(Entry));
	for (const FString& Path : Screenshots) ShotValues.Add(MakeShared<FJsonValueString>(Path));
	for (const TSharedPtr<FJsonObject>& Entry : Rounds) RoundValues.Add(MakeShared<FJsonValueObject>(Entry));
	for (const TSharedPtr<FJsonObject>& Entry : RoundHuds) HudValues.Add(MakeShared<FJsonValueObject>(Entry));
	Root->SetArrayField(TEXT("checks"), CheckValues);
	Root->SetArrayField(TEXT("inputs"), InputValues);
	Root->SetArrayField(TEXT("screenshots"), ShotValues);
	if (bFullGameMode)
	{
		Root->SetNumberField(TEXT("roundTwoAutoPreparationSeconds"), RoundTwoAutoTransitionSeconds);
		Root->SetArrayField(TEXT("rounds"), RoundValues);
		if (bFull12Mode) Root->SetArrayField(TEXT("roundHuds"), HudValues);
		if (FinalRanking.IsValid()) Root->SetObjectField(TEXT("finalRanking"), FinalRanking);
	}
	FString Json;
	FJsonSerializer::Serialize(Root, TJsonWriterFactory<>::Create(&Json));
	const TCHAR* ReportName = bFull12Mode ? TEXT("Reports/M1_UI_Full12.json") :
		(bFullGameMode ? TEXT("Reports/M1_UI_FullGame.json") : TEXT("Reports/M1_UI_Smoke.json"));
	const FString ReportPath = FPaths::Combine(FPaths::ProjectSavedDir(), ReportName);
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(ReportPath), true);
	const bool bSaved = FFileHelper::SaveStringToFile(Json, *ReportPath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
	UE_LOG(LogTemp, Display, TEXT("Tread M1 Slate UI %s: %s, report %s"),
		bFull12Mode ? TEXT("full R1-R12") : (bFullGameMode ? TEXT("full game") : TEXT("smoke")),
		bPassed && bSaved ? TEXT("PASS") : TEXT("FAIL"), *ReportPath);
	if (bExitOnComplete) FPlatformMisc::RequestExitWithStatus(false, bPassed && bSaved ? 0 : 1);
}
