#include "TreadM1MatchController.h"

#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Engine/Engine.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "HAL/PlatformMisc.h"
#include "HAL/FileManager.h"
#include "Math/RandomStream.h"
#include "Misc/Crc.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "UObject/Class.h"
#include "TreadM0PerfActor.h"
#include "TimerManager.h"

namespace
{
	static const int32 MaxRounds = 12;
	static const int32 MaxBenchSlots = 8;
	static const int32 ShopSlots = 5;
	static const int32 ShopCharacterCount = 32;
	static const TCHAR* PoolTierNames[] = {TEXT("I"), TEXT("II"), TEXT("III"), TEXT("IV"), TEXT("V"), TEXT("VI")};
	static const int32 PoolTierTotals[] = {12, 14, 18, 16, 8, 5};

	FString GetString(const TSharedPtr<FJsonObject>& Object, const TCHAR* Key)
	{
		FString Value;
		return Object.IsValid() && Object->TryGetStringField(Key, Value) ? Value : FString();
	}

	int32 GetInt(const TSharedPtr<FJsonObject>& Object, const TCHAR* Key, int32 DefaultValue = 0)
	{
		double Value = 0.0;
		return Object.IsValid() && Object->TryGetNumberField(Key, Value) ? static_cast<int32>(Value) : DefaultValue;
	}
}

ATreadM1MatchController::ATreadM1MatchController()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;
	SetReplicates(false);
}

void ATreadM1MatchController::BeginPlay()
{
	Super::BeginPlay();
	LoadCampaignProgress();
	FString CampaignText;
	if (FParse::Value(FCommandLine::Get(), TEXT("TreadCampaign="), CampaignText))
	{
		// -TreadCampaign=N starts in stage N (developer entry: not gated by the unlock order).
		PendingCampaignStage = FMath::Max(0, FCString::Atoi(*CampaignText));
		bInitialized = false;
	}
	if (!bInitialized)
	{
		int64 Seed = 20260926;
		FString SeedText;
		if (FParse::Value(FCommandLine::Get(), TEXT("TreadSeed="), SeedText))
		{
			Seed = FCString::Atoi64(*SeedText);
		}
		InitializeMatch(Seed);
	}
	// Deterministic capture presets keep the evidence screenshots focused on a
	// single M1 phase without adding a second test-only state machine.
	FString CaptureStage;
	if (FParse::Value(FCommandLine::Get(), TEXT("TreadM1Capture="), CaptureStage))
	{
		CaptureStage = CaptureStage.ToUpper();
		if (CaptureStage == TEXT("BP"))
		{
			BeginPreMatchBP(TEXT("capture-bp"));
			ChoosePlayerStrategy(MatchState.BP.AvailableStrategyIds[0], TEXT("capture-player"));
			RunNextAIPick(TEXT("capture-ai-1"));
		}
		else if (CaptureStage == TEXT("SCOUT") || CaptureStage == TEXT("PREPARE") || CaptureStage == TEXT("BATTLE") || CaptureStage == TEXT("RESULT"))
		{
			BeginPreMatchBP(TEXT("capture-bp"));
			ChoosePlayerStrategy(MatchState.BP.AvailableStrategyIds[0], TEXT("capture-player"));
			int32 CaptureAIPick = 1;
			while (MatchState.BP.AiPickStates.Contains(ETreadM1AIPickState::Waiting))
			{
				RunNextAIPick(FString::Printf(TEXT("capture-ai-%d"), CaptureAIPick++));
			}
			ConfirmPreMatchBP(TEXT("capture-confirm"));
			if (CaptureStage == TEXT("SCOUT") || CaptureStage == TEXT("PREPARE"))
			{
				// Leave enough time for the editor/Slate evidence pass to inspect
				// the preparation shop and bench before the automatic timer fires.
				MatchState.PhaseTimeRemainingSec = 300.0f;
			}
			if (CaptureStage == TEXT("BATTLE") || CaptureStage == TEXT("RESULT"))
			{
				DeployAndStartBattle(TEXT("capture-deploy"));
				if (CaptureStage == TEXT("BATTLE"))
				{
					MatchState.PhaseTimeRemainingSec = 300.0f;
				}
				// BATTLE evidence must leave the match in the live automatic
				// battle phase. RESULT is the only capture that resolves and settles.
				if (CaptureStage == TEXT("RESULT"))
				{
					ResolveBattle(TEXT("capture-resolve"));
					SettleRound(TEXT("capture-settle"));
				}
			}
		}
	}
	// document/165: the AI turn mutates boards and purses, so it stays out of the deterministic self-tests.
	bAIOpponentsPlay = !FParse::Param(FCommandLine::Get(), TEXT("TreadM1SelfTest"))
		&& !FParse::Param(FCommandLine::Get(), TEXT("TreadM2SelfTest"))
		&& !FParse::Param(FCommandLine::Get(), TEXT("TreadM1UITest"));
	if (FParse::Param(FCommandLine::Get(), TEXT("TreadM1SelfTest")))
	{
		const bool bPassed = RunDeterministicSelfTest();
		FPlatformMisc::RequestExitWithStatus(false, bPassed ? 0 : 1);
	}
	FString M2Capture;
	if (FParse::Value(FCommandLine::Get(), TEXT("TreadM2Capture="), M2Capture))
	{
		BuildM2Showcase(M2Capture.ToUpper());
		FString ShotName;
		if (FParse::Value(FCommandLine::Get(), TEXT("TreadM2Shot="), ShotName))
		{
			// Let the HUD paint a few frames (and the highlight pulse settle) before capturing, then exit.
			FTimerHandle ShotTimer;
			GetWorldTimerManager().SetTimer(ShotTimer, FTimerDelegate::CreateWeakLambda(this, [this, ShotName]() { RequestM2Screenshot(ShotName); }), 4.0f, false);
		}
	}
	if (FParse::Param(FCommandLine::Get(), TEXT("TreadM2SelfTest")))
	{
		const bool bPassed = RunM2PactSelfTest();
		FPlatformMisc::RequestExitWithStatus(false, bPassed ? 0 : 1);
	}
	if (FParse::Param(FCommandLine::Get(), TEXT("TreadAudioSelfTest")))
	{
		// Give the audio device and the HUD one beat to come up before auditioning the catalogue.
		FTimerHandle AudioTimer;
		GetWorldTimerManager().SetTimer(AudioTimer, FTimerDelegate::CreateWeakLambda(this, [this]()
		{
			const bool bPassed = RunAudioSelfTest();
			FPlatformMisc::RequestExitWithStatus(false, bPassed ? 0 : 1);
		}), 2.0f, false);
	}
	// document/180: char_093 idle evidence - put it on the human board and frame it with a temporary camera,
	// then take a HighResShot and quit. Test-only; needs -TreadSkipFrontEnd and a preparation capture stage.
	if (FParse::Param(FCommandLine::Get(), TEXT("TreadChar093View")))
	{
		FTimerHandle StockTimer;
		GetWorldTimerManager().SetTimer(StockTimer, FTimerDelegate::CreateWeakLambda(this, [this]()
		{
			StockBoardForFixture(TEXT("P0"), {TEXT("char_093"), TEXT("char_021")});
		}), 1.5f, false);
		FTimerHandle CamTimer;
		GetWorldTimerManager().SetTimer(CamTimer, FTimerDelegate::CreateWeakLambda(this, [this]()
		{
			UWorld* World = GetWorld();
			APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
			if (!PC) return;
			const FVector Chest(-10000.0f, -70000.0f, 7000.0f);   // cell (0,4), chest height
			const FVector Loc = Chest + FVector(34000.0f, 34000.0f, 8000.0f);
			FActorSpawnParameters SpawnParams;
			SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			ACameraActor* Cam = World->SpawnActor<ACameraActor>(Loc, (Chest - Loc).Rotation(), SpawnParams);
			if (Cam)
			{
				Cam->GetCameraComponent()->SetFieldOfView(30.0f);
				PC->SetViewTarget(Cam);
			}
		}), 3.5f, false);
		FTimerHandle ShotTimer;
		GetWorldTimerManager().SetTimer(ShotTimer, FTimerDelegate::CreateWeakLambda(this, [this]()
		{
			// FScreenshotRequest path: HighResShot only writes from a focused game viewport, this always lands.
			RequestM2Screenshot(TEXT("Char093_180"));
		}), 5.5f, false);
		FTimerHandle QuitTimer;
		GetWorldTimerManager().SetTimer(QuitTimer, FTimerDelegate::CreateWeakLambda(this, [this]()
		{
			FPlatformMisc::RequestExit(false);
		}), 8.0f, false);
	}
	// document/180: the M0 perf actor used to live in the M0 game mode only; with the default game mode being
	// TreadM1GameMode that mode never ran, so -TreadM0Perf produced no report. Spawn it from here instead.
	if (FParse::Param(FCommandLine::Get(), TEXT("TreadM0Perf")) && GetWorld())
	{
		bool bHasPerfActor = false;
		for (TActorIterator<ATreadM0PerfActor> It(GetWorld()); It; ++It) { bHasPerfActor = true; break; }
		if (!bHasPerfActor) GetWorld()->SpawnActor<ATreadM0PerfActor>();
	}
}

void ATreadM1MatchController::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const bool bWasInBattle = MatchState.Phase == ETreadM1Phase::Battle;
	AdvancePreparationTimer(DeltaSeconds);
	// Automatic battles use the same authoritative resolver as the explicit
	// RunRound/self-test path.  Keep the live Battle phase observable for the
	// configured duration, then resolve exactly once when its timer expires.
	if (bWasInBattle && MatchState.Phase == ETreadM1Phase::Battle && DeltaSeconds > 0.0f)
	{
		if (bBattlePresenterActive && !bBattleHeld)
		{
			// document/12: resolve now (nothing else draws from the random stream during the battle, so the result is
			// the one the timer would produce) and keep the Battle phase while the presenter replays the events.
			bHoldSettlement = true;
			ResolveBattle(FString::Printf(TEXT("runtime:round-%d:battle-presented"), MatchState.RoundIndex));
			bHoldSettlement = false;
		}
		MatchState.PhaseTimeRemainingSec = FMath::Max(0.0f, MatchState.PhaseTimeRemainingSec - DeltaSeconds);
		if (MatchState.PhaseTimeRemainingSec <= 0.0f && bBattleHeld)
		{
			// The battle cap settles without waiting for the replay.
			FinishHeldBattle();
		}
		else if (MatchState.PhaseTimeRemainingSec <= 0.0f)
		{
			ResolveBattle(FString::Printf(TEXT("runtime:round-%d:battle-timer"), MatchState.RoundIndex));
		}
		else
		{
			OnStateChanged.Broadcast();
		}
	}
}

void ATreadM1MatchController::InitializeMatch(int64 InSeed)
{
	MatchState = FTreadM1MatchState();
	bBattleHeld = false;
	LoadM2Data();
	MatchState.CampaignStage = PactData.IsValid() && PactData->FindStage(PendingCampaignStage) ? PendingCampaignStage : 0;
	ActiveScriptedDef = nullptr;
	ResetBattleTraitState();
	ResetBattleMeters();
	MatchState.Seed = InSeed;
	MatchState.MatchId = FString::Printf(TEXT("m1-%lld"), InSeed);
	RandomStream.Initialize(NormalizeSeed(InSeed));
	SyncRandomState();
	MatchState.Phase = ETreadM1Phase::R0Briefing;
	MatchState.RoundIndex = 0;
	MatchState.RoundType = ETreadM1RoundType::Briefing;
	MatchState.PhaseTimeRemainingSec = 0.0f;
	MatchState.Rules.LevelExperienceTable.Reset();
	const int32 Experience[] = {2, 2, 6, 10, 20, 36, 56, 80, 0};
	for (int32 Index = 0; Index < UE_ARRAY_COUNT(Experience); ++Index)
	{
		FTreadM1LevelRule Rule;
		Rule.Level = Index + 1;
		Rule.ExperienceToNextLevel = Experience[Index];
		MatchState.Rules.LevelExperienceTable.Add(Rule);
	}
	// document/187: the owner wants a full 5-minute preparation window. Self-tests keep the old 30 s so the
	// scripted auto-transition checks still finish in their expected window.
	const bool bTestMode = FParse::Param(FCommandLine::Get(), TEXT("TreadM1SelfTest"))
		|| FParse::Param(FCommandLine::Get(), TEXT("TreadM2SelfTest"))
		|| FParse::Param(FCommandLine::Get(), TEXT("TreadM1UITest"));
	MatchState.Rules.PreparationDurationSec = bTestMode ? 30 : 300;
	if (const FTreadM4CampaignStage* Stage = ActiveCampaignStage())
	{
		MatchState.Rules.PreparationDurationSec = FMath::Max(300, 300 + Stage->PrepareSecondsDelta);
	}
	MatchState.Rules.BaseIncome = 5;
	MatchState.Rules.InterestFundsStep = 10;
	MatchState.Rules.MaxInterest = 5;
	MatchState.Rules.ExperiencePurchaseCost = 4;
	MatchState.Rules.ExperiencePurchaseAmount = 4;
	MatchState.Rules.ShopSlotCount = ShopSlots;
	MatchState.Rules.ShopRefreshCost = 2;
	MatchState.Rules.MaxBenchSlots = MaxBenchSlots;
	if (HasN1Economy())
	{
		const FTreadN1Economy& Economy = PactData->Economy;
		MatchState.Rules.ShopRefreshCost = Economy.RefreshPrice;
		MatchState.Rules.BaseIncome = Economy.IncomeForRound(1);
		MatchState.Rules.InterestFundsStep = 0;
		MatchState.Rules.MaxInterest = 0;
		MatchState.Rules.ExperiencePurchaseCost = Economy.UpgradePrices.Num() > 0 ? Economy.UpgradePrices[0] : 0;
		MatchState.Rules.ExperiencePurchaseAmount = 0;
	}
	InitializePoolLedger();
	BuildInitialPlayers();
	BuildAIPlaceholderRosters();
	LoadStrategies();
	MatchState.BP.Seed = InSeed;
	MatchState.BP.AiPickOrder = {TEXT("P1"), TEXT("P2"), TEXT("P3")};
	MatchState.BP.AiStrategyIds.Init(FString(), 3);
	MatchState.BP.AiPickStates.Init(ETreadM1AIPickState::Waiting, 3);
	// Seed the initial ScoutSnapshot/UI with deterministic ranks.  Ranks are
	// otherwise assigned only after the first battle, leaving the pre-match
	// roster showing zero ranks even though all four players are active.
	RankPlayers();
	RefreshScoutSnapshots();
	bInitialStrategyCostsApplied = false;
	BattleEventSequence = 0;
	UnitInstanceSequence = 0;
	CloneInstanceSequence = 0;
	LastSettledRoundIndex = 0;
	PoolReturnedPlayerIds.Reset();
	ProcessedRequests.Reset();
	bInitialized = true;
	OnStateChanged.Broadcast();
}

void ATreadM1MatchController::BuildInitialPlayers()
{
	MatchState.Players.Reset();
	for (int32 Index = 0; Index < 4; ++Index)
	{
		FTreadM1PlayerState Player;
		Player.PlayerId = FString::Printf(TEXT("P%d"), Index);
		Player.DisplayName = Index == 0 ? TEXT("玩家") : FString::Printf(TEXT("AI-%d"), Index);
		Player.bIsHuman = Index == 0;
		Player.Health = 100;
		Player.Funds = 5;
		Player.Level = 3;
		Player.Experience = 0;
		Player.ExperienceToNextLevel = 6;
		Player.PopulationLimit = 3;
		if (HasN1Economy())
		{
			const FTreadN1Economy& Economy = PactData->Economy;
			Player.Funds = Economy.IncomeForRound(1);
			Player.Level = Economy.StartShopLevel;
			Player.PopulationLimit = Economy.DeployCap;
			Player.ExperienceToNextLevel = ShopUpgradeCost(Player);
		}
		if (const FTreadM4CampaignStage* Stage = ActiveCampaignStage())
		{
			// Campaign modifiers (Campaign16.json modifierMapping): AI base health, player starting funds.
			if (!Player.bIsHuman) Player.Health += Stage->EnemyHpBonus;
			else Player.Funds = FMath::Max(0, Player.Funds + Stage->StartGoldBonus);
		}
		Player.NextRoundIncome = CalculateIncome(Player);
		Player.BenchUnitInstanceIds.Init(FString(), MaxBenchSlots);
		BuildShop(Player, 0);
		MatchState.Players.Add(Player);
	}
}

void ATreadM1MatchController::BuildAIPlaceholderRosters()
{
	// Deterministic graybox rosters make the four-player pairing and automatic
	// battle path observable before the final 100-card assets are imported. P0
	// receives a split board/bench loadout so the UI can demonstrate both sides
	// of the drag contract immediately after entering preparation.
	for (int32 PlayerIndex = 0; PlayerIndex < MatchState.Players.Num(); ++PlayerIndex)
	{
		FTreadM1PlayerState& Player = MatchState.Players[PlayerIndex];
		for (int32 Slot = 0; Slot < 3; ++Slot)
		{
			FTreadM1UnitInstance Unit;
			Unit.UnitInstanceId = FString::Printf(TEXT("%s_graybox_unit_%02d"), *Player.PlayerId, Slot + 1);
			Unit.CharacterId = FString::Printf(TEXT("char_%03d"), PlayerIndex * 3 + Slot + 1);
			if (HasN1Economy() && PactData->CardOrder.Num() > 0)
			{
				TArray<FString> LowTier;
				for (const FString& CharacterId : PactData->CardOrder)
				{
					if (CardTier(CharacterId) == TEXT("I") || CardTier(CharacterId) == TEXT("II")) LowTier.Add(CharacterId);
				}
				if (LowTier.Num() > 0) Unit.CharacterId = LowTier[(PlayerIndex * 3 + Slot) % LowTier.Num()];
			}
			Unit.OriginalOperatorName = PlayerIndex == 0
				? FString::Printf(TEXT("玩家占位角色%02d"), Slot + 1)
				: FString::Printf(TEXT("AI占位角色%02d"), PlayerIndex * 3 + Slot + 1);
			Unit.OperatorTier = PoolTierNames[(PlayerIndex + Slot) % UE_ARRAY_COUNT(PoolTierNames)];
			Unit.UnitStar = 1;
			Unit.Cost = 1 + ((PlayerIndex + Slot) % 5);
			if (HasN1Economy() && !CardTier(Unit.CharacterId).IsEmpty())
			{
				Unit.OperatorTier = CardTier(Unit.CharacterId);
				Unit.Cost = TierPrice(Unit.OperatorTier);
			}
			Unit.OwnerPlayerId = Player.PlayerId;
			const bool bStartOnBoard = PlayerIndex != 0 || Slot < 2;
			Unit.Location = bStartOnBoard ? ETreadM1UnitLocation::Board : ETreadM1UnitLocation::Bench;
			Unit.BoardCell = bStartOnBoard ? FIntPoint(Slot + (PlayerIndex == 0 ? 2 : 0), PlayerIndex == 0 ? 5 : PlayerIndex - 1) : FIntPoint(-1, -1);
			FTreadM1ShopSlot PoolSlot;
			PoolSlot.SlotIndex = Slot;
			PoolSlot.CharacterId = Unit.CharacterId;
			PoolSlot.OperatorTier = Unit.OperatorTier;
			PoolSlot.Cost = Unit.Cost;
			if (RecordPoolLedger(TEXT("Reserve"), Player.PlayerId, PoolSlot, -1))
			{
				RecordPoolLedger(TEXT("Purchase"), Player.PlayerId, PoolSlot, -1);
				if (bStartOnBoard)
				{
					Player.BoardUnits.Add(Unit);
					Player.PopulationUsed++;
				}
				else
				{
					Player.BenchUnits.Add(Unit);
					const int32 EmptyIndex = Player.BenchUnitInstanceIds.Find(FString());
					if (EmptyIndex != INDEX_NONE)
					{
						Player.BenchUnitInstanceIds[EmptyIndex] = Unit.UnitInstanceId;
					}
				}
			}
		}
	}
	RefreshProjectedIncomes();
}

void ATreadM1MatchController::InitializePoolLedger()
{
	MatchState.PoolLedger = FTreadM1PoolLedger();
	if (HasN1Economy())
	{
		for (const FString& CharacterId : PactData->CardOrder)
		{
			const FTreadM2Card* Card = PactData->FindCard(CharacterId);
			if (!Card || Card->OperatorTier.IsEmpty() || Card->PoolCopies <= 0) continue;
			FTreadM1PoolBalance Balance;
			Balance.CharacterId = CharacterId;
			Balance.OperatorTier = Card->OperatorTier;
			Balance.PoolCopiesTotal = Card->PoolCopies;
			Balance.PoolCopiesAvailable = Card->PoolCopies;
			MatchState.PoolLedger.Balances.Add(Balance);
			AppendPoolLedgerEntry(TEXT("Initialize"), TEXT(""), Balance.CharacterId, Balance.OperatorTier, TEXT(""), TEXT(""), TEXT(""), 0);
		}
		return;
	}
	for (int32 CharacterIndex = 1; CharacterIndex <= ShopCharacterCount; ++CharacterIndex)
	{
		for (int32 TierIndex = 0; TierIndex < UE_ARRAY_COUNT(PoolTierNames); ++TierIndex)
		{
			FTreadM1PoolBalance Balance;
			Balance.CharacterId = FString::Printf(TEXT("char_%03d"), CharacterIndex);
			Balance.OperatorTier = PoolTierNames[TierIndex];
			Balance.PoolCopiesTotal = PoolTierTotals[TierIndex];
			Balance.PoolCopiesAvailable = PoolTierTotals[TierIndex];
			MatchState.PoolLedger.Balances.Add(Balance);
			AppendPoolLedgerEntry(TEXT("Initialize"), TEXT(""), Balance.CharacterId, Balance.OperatorTier,
				TEXT(""), TEXT(""), TEXT(""), 0);
		}
	}
}

void ATreadM1MatchController::BuildShop(FTreadM1PlayerState& Player, int32 RefreshIndex)
{
	ReturnShopReservations(Player);
	const bool bWasLocked = Player.Shop.bLocked;
	Player.Shop.Slots.Reset();
	Player.Shop.RefreshIndex = RefreshIndex;
	Player.Shop.RefreshCost = MatchState.Rules.ShopRefreshCost > 0 ? MatchState.Rules.ShopRefreshCost : 2;
	Player.Shop.bLocked = bWasLocked;
	const int32 SlotCount = HasN1Economy() ? PactData->Economy.SlotsForLevel(Player.Level) : MatchState.Rules.ShopSlotCount;
	for (int32 Slot = 0; Slot < SlotCount; ++Slot)
	{
		FTreadM1ShopSlot ShopSlot;
		ShopSlot.SlotIndex = Slot;
		bool bReserved = false;
		if (HasN1Economy())
		{
			FString CharacterId, Tier;
			if (DrawShopCard(Player, CharacterId, Tier))
			{
				ShopSlot.CharacterId = CharacterId;
				ShopSlot.OperatorTier = Tier;
				ShopSlot.Cost = PurchaseCostFor(CharacterId, TierPrice(Tier));
				bReserved = RecordPoolLedger(TEXT("Reserve"), Player.PlayerId, ShopSlot, -1);
			}
			if (!bReserved)
			{
				ShopSlot.CharacterId.Empty();
				ShopSlot.OperatorTier = PoolTierNames[0];
				ShopSlot.Cost = 0;
				ShopSlot.bIsSold = true;
			}
			ShopSlot.bIsLockedByPlayer = Player.Shop.bLocked;
			Player.Shop.Slots.Add(ShopSlot);
			continue;
		}
		for (int32 Attempt = 0; Attempt < 256 && !bReserved; ++Attempt)
		{
			ShopSlot.CharacterId = FString::Printf(TEXT("char_%03d"), RandomStream.RandRange(1, ShopCharacterCount));
			ShopSlot.OperatorTier = PoolTierNames[RandomStream.RandRange(0, UE_ARRAY_COUNT(PoolTierNames) - 1)];
			ShopSlot.Cost = PurchaseCostFor(ShopSlot.CharacterId, RandomStream.RandRange(1, 5));
			bReserved = RecordPoolLedger(TEXT("Reserve"), Player.PlayerId, ShopSlot, -1);
		}
		if (!bReserved)
		{
			for (int32 CharacterIndex = 1; CharacterIndex <= ShopCharacterCount && !bReserved; ++CharacterIndex)
			{
				for (int32 TierIndex = 0; TierIndex < UE_ARRAY_COUNT(PoolTierNames) && !bReserved; ++TierIndex)
				{
					ShopSlot.CharacterId = FString::Printf(TEXT("char_%03d"), CharacterIndex);
					ShopSlot.OperatorTier = PoolTierNames[TierIndex];
					ShopSlot.Cost = 1;
					bReserved = RecordPoolLedger(TEXT("Reserve"), Player.PlayerId, ShopSlot, -1);
				}
			}
		}
		if (!bReserved)
		{
			ShopSlot.CharacterId.Empty();
			ShopSlot.OperatorTier = PoolTierNames[0];
			ShopSlot.Cost = 0;
			ShopSlot.bIsSold = true;
		}
		ShopSlot.bIsLockedByPlayer = Player.Shop.bLocked;
		Player.Shop.Slots.Add(ShopSlot);
	}
	// 远见 (document/171): at 80 layers its own cards cost 1 less, at 150 every card does.
	if (PactData.IsValid())
	{
		if (const FTreadM2PactProgress* Visi = FindPactProgress(Player, TEXT("远见")))
		{
			if (const FTreadM2PactDef* VisiDef = PactData->FindPact(TEXT("远见")))
			{
				const int32 Discount = FMath::RoundToInt(VisiDef->Params.FindRef(TEXT("discount")));
				const bool bAllCards = Visi->Stacks >= VisiDef->Params.FindRef(TEXT("layer2"));
				const bool bVisiCards = Visi->Stacks >= VisiDef->Params.FindRef(TEXT("layer1"));
				if (Discount > 0 && (bAllCards || bVisiCards))
				{
					for (FTreadM1ShopSlot& Slot : Player.Shop.Slots)
					{
						const bool bVisiCard = GetCardPacts(Slot.CharacterId).Contains(TEXT("远见"));
						if (bAllCards || bVisiCard)
						{
							Slot.Cost = FMath::Max(0, Slot.Cost - Discount);
						}
					}
				}
			}
		}
	}
	SyncRandomState();
}

void ATreadM1MatchController::ReturnShopReservations(FTreadM1PlayerState& Player, const FString& Action)
{
	for (FTreadM1ShopSlot& Slot : Player.Shop.Slots)
	{
		if (!Slot.bIsSold && !Slot.CharacterId.IsEmpty())
		{
			if (RecordPoolLedger(Action, Player.PlayerId, Slot, 1))
			{
				Slot.bIsSold = true;
				Slot.CharacterId.Empty();
			}
		}
	}
}

void ATreadM1MatchController::ReturnPlayerPoolAssets(FTreadM1PlayerState& Player)
{
	if (PoolReturnedPlayerIds.Contains(Player.PlayerId))
	{
		return;
	}
	PoolReturnedPlayerIds.Add(Player.PlayerId);
	ReturnShopReservations(Player, TEXT("EliminationReturn"));
	for (FTreadM1UnitInstance& Unit : Player.BenchUnits)
	{
		if (Unit.bIsTransformClone)
		{
			RecordPoolLedger(TEXT("CloneDestroy"), Player.PlayerId, Unit, 0);
		}
		else
		{
			RecordPoolLedger(TEXT("EliminationReturn"), Player.PlayerId, Unit, FMath::Max(1, Unit.PoolCopiesHeld));
		}
		Unit.Location = ETreadM1UnitLocation::Removed;
	}
	for (FTreadM1UnitInstance& Unit : Player.BoardUnits)
	{
		if (Unit.bIsTransformClone)
		{
			RecordPoolLedger(TEXT("CloneDestroy"), Player.PlayerId, Unit, 0);
		}
		else
		{
			RecordPoolLedger(TEXT("EliminationReturn"), Player.PlayerId, Unit, FMath::Max(1, Unit.PoolCopiesHeld));
		}
		Unit.Location = ETreadM1UnitLocation::Removed;
	}
	Player.BenchUnits.Reset();
	Player.BoardUnits.Reset();
	Player.BenchUnitInstanceIds.Init(FString(), MatchState.Rules.MaxBenchSlots);
	Player.PopulationUsed = 0;
}

int32 ATreadM1MatchController::NormalizeSeed(int64 InSeed) const
{
	const uint64 UnsignedSeed = static_cast<uint64>(InSeed);
	const uint32 MixedSeed = static_cast<uint32>(UnsignedSeed) ^ static_cast<uint32>(UnsignedSeed >> 32);
	return static_cast<int32>(MixedSeed);
}

void ATreadM1MatchController::SyncRandomState()
{
	MatchState.RandomStreamState = RandomStream.GetCurrentSeed();
}

void ATreadM1MatchController::LoadStrategies()
{
	MatchState.Strategies.Reset();
	FString FilePath = FPaths::Combine(FPaths::ProjectContentDir(), TEXT("Data/Generated/Strategies40.json"));
	if (!FPaths::FileExists(FilePath)) FilePath = FPaths::Combine(FPaths::ProjectContentDir(), TEXT("Data/Strategies.json"));
	FString JsonText;
	TSharedPtr<FJsonObject> Root;
	if (FFileHelper::LoadFileToString(JsonText, *FilePath) && FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(JsonText), Root) && Root.IsValid())
	{
		const TArray<TSharedPtr<FJsonValue>>* Items = nullptr;
		if (Root->TryGetArrayField(TEXT("strategies"), Items) && Items)
		{
			for (const TSharedPtr<FJsonValue>& Value : *Items)
			{
				const TSharedPtr<FJsonObject> Object = Value.IsValid() ? Value->AsObject() : nullptr;
				if (!Object.IsValid())
				{
					continue;
				}
				FTreadM1StrategyState Strategy;
				Strategy.StrategyId = GetString(Object, TEXT("strategyId"));
				Strategy.IssuerCharacterId = GetString(Object, TEXT("issuerCharacterId"));
				Strategy.OfferText = GetString(Object, TEXT("offerText"));
				Strategy.HpCost = GetInt(Object, TEXT("hpCost"));
				Strategy.Trigger = GetString(Object, TEXT("trigger"));
				Strategy.UnlockCondition = GetString(Object, TEXT("unlockCondition"));
				Strategy.bInitialOnly = Object->GetBoolField(TEXT("initialOnly"));
				Strategy.bBpEligible = Object->GetBoolField(TEXT("bpEligible"));
				Strategy.UniqueScope = GetString(Object, TEXT("uniqueScope"));
				const TArray<TSharedPtr<FJsonValue>>* Effects = nullptr;
				if (Object->TryGetArrayField(TEXT("effects"), Effects) && Effects)
				{
					for (const TSharedPtr<FJsonValue>& Effect : *Effects)
					{
						Strategy.Effects.Add(Effect->AsString());
					}
				}
				MatchState.Strategies.Add(MoveTemp(Strategy));
			}
		}
	}
	if (MatchState.Strategies.Num() == 0)
	{
		for (int32 Index = 0; Index < 32; ++Index)
		{
			FTreadM1StrategyState Strategy;
			Strategy.StrategyId = FString::Printf(TEXT("strategy_%03d"), Index + 1);
			Strategy.IssuerCharacterId = FString::Printf(TEXT("char_%03d"), Index + 1);
			Strategy.OfferText = TEXT("M1 fallback strategy");
			Strategy.Effects.Add(TEXT("NoOp"));
			Strategy.Trigger = TEXT("MatchStart");
			Strategy.UnlockCondition = TEXT("Always");
			MatchState.Strategies.Add(MoveTemp(Strategy));
		}
	}
}

void ATreadM1MatchController::SetPhase(ETreadM1Phase NewPhase)
{
	if (MatchState.Phase == NewPhase)
	{
		return;
	}
	const ETreadM1Phase Previous = MatchState.Phase;
	MatchState.Phase = NewPhase;
	OnPhaseChanged.Broadcast(Previous, NewPhase);
	OnStateChanged.Broadcast();
}

void ATreadM1MatchController::SetRoundTypeForCurrentRound()
{
	if (MatchState.RoundIndex <= 0)
	{
		MatchState.RoundType = ETreadM1RoundType::Briefing;
	}
	else if (MatchState.RoundIndex <= 2)
	{
		MatchState.RoundType = ETreadM1RoundType::PvE;
	}
	else if (MatchState.RoundIndex <= 11)
	{
		MatchState.RoundType = ETreadM1RoundType::PvP;
	}
	else
	{
		MatchState.RoundType = ETreadM1RoundType::Leader;
	}
}

bool ATreadM1MatchController::TryGetProcessedRequest(const FString& RequestId, FTreadM1CommandResult& OutResult) const
{
	if (RequestId.IsEmpty())
	{
		return false;
	}
	if (const FTreadM1CommandResult* Existing = ProcessedRequests.Find(RequestId))
	{
		OutResult = *Existing;
		return true;
	}
	return false;
}

void ATreadM1MatchController::CacheProcessedRequest(const FTreadM1CommandResult& Result)
{
	if (!Result.RequestId.IsEmpty())
	{
		ProcessedRequests.FindOrAdd(Result.RequestId) = Result;
	}
}

FTreadM1CommandResult ATreadM1MatchController::Accept(const FString& RequestId)
{
	FTreadM1CommandResult Result;
	Result.bAccepted = true;
	Result.ReasonCode = ETreadM1RejectReason::None;
	Result.RequestId = RequestId;
	CacheProcessedRequest(Result);
	return Result;
}

FTreadM1CommandResult ATreadM1MatchController::Reject(ETreadM1RejectReason Reason, const FString& RequestId)
{
	FTreadM1CommandResult Result;
	Result.bAccepted = false;
	Result.ReasonCode = Reason;
	Result.RequestId = RequestId;
	CacheProcessedRequest(Result);
	return Result;
}

int32 ATreadM1MatchController::StreakReward(const FTreadM1PlayerState& Player) const
{
	const int32 Streak = FMath::Max(Player.WinStreak, Player.LossStreak);
	return Streak >= 6 ? 3 : (Streak >= 4 ? 2 : (Streak >= 2 ? 1 : 0));
}

FTreadM1IncomeBreakdown ATreadM1MatchController::CalculateIncome(const FTreadM1PlayerState& Player) const
{
	FTreadM1IncomeBreakdown Income;
	if (HasN1Economy())
	{
		const FTreadN1Economy& Economy = PactData->Economy;
		Income.Base = Economy.IncomeForRound(MatchState.RoundIndex + 1);
		if (const FTreadM4CampaignStage* Stage = ActiveCampaignStage())
		{
			Income.Base += Player.bIsHuman ? Stage->IncomeBonus : FMath::Max(0, Stage->AiLevel - 1);
		}
		Income.Interest = Economy.bInterest && MatchState.Rules.InterestFundsStep > 0 ? FMath::Min(MatchState.Rules.MaxInterest, Player.Funds / MatchState.Rules.InterestFundsStep) : 0;
		// Band 坎诺特: leftover funds carry over, +1 when at least 5 remain.
		if (Player.Flags.Contains(TEXT("flag:CarryOverFunds")) && Player.Funds >= 5) Income.Interest += 1;
		Income.Streak = Economy.bStreakIncome ? StreakReward(Player) : 0;
		Income.Other = Player.PendingTraitIncome;
		return Income;
	}
	Income.Base = MatchState.Rules.BaseIncome;
	Income.Interest = MatchState.Rules.InterestFundsStep > 0
		? FMath::Min(MatchState.Rules.MaxInterest, Player.Funds / MatchState.Rules.InterestFundsStep)
		: 0;
	Income.Streak = StreakReward(Player);
	Income.Other = Player.PendingTraitIncome;
	return Income;
}

void ATreadM1MatchController::RefreshProjectedIncomes()
{
	for (FTreadM1PlayerState& Player : MatchState.Players)
	{
		Player.NextRoundIncome = CalculateIncome(Player);
	}
}

void ATreadM1MatchController::ApplyExperience(FTreadM1PlayerState& Player, int32 Amount)
{
	Player.Experience += FMath::Max(0, Amount);
	while (Player.Level < 9)
	{
		const int32 Required = Player.ExperienceToNextLevel;
		if (Required <= 0 || Player.Experience < Required)
		{
			break;
		}
		Player.Experience -= Required;
		++Player.Level;
		Player.PopulationLimit = Player.Level;
		Player.ExperienceToNextLevel = MatchState.Rules.LevelExperienceTable.IsValidIndex(Player.Level - 1)
			? MatchState.Rules.LevelExperienceTable[Player.Level - 1].ExperienceToNextLevel : 0;
	}
	if (Player.Level >= 9)
	{
		Player.Level = 9;
		Player.ExperienceToNextLevel = 0;
	}
}

FTreadM1PoolBalance* ATreadM1MatchController::FindPoolBalance(const FString& CharacterId, const FString& OperatorTier)
{
	return MatchState.PoolLedger.Balances.FindByPredicate([&](FTreadM1PoolBalance& Balance)
	{
		return Balance.CharacterId == CharacterId && Balance.OperatorTier == OperatorTier;
	});
}

const FTreadM1PoolBalance* ATreadM1MatchController::FindPoolBalance(const FString& CharacterId, const FString& OperatorTier) const
{
	return MatchState.PoolLedger.Balances.FindByPredicate([&](const FTreadM1PoolBalance& Balance)
	{
		return Balance.CharacterId == CharacterId && Balance.OperatorTier == OperatorTier;
	});
}

void ATreadM1MatchController::AppendPoolLedgerEntry(const FString& Action, const FString& PlayerId, const FString& CharacterId,
	const FString& OperatorTier, const FString& UnitInstanceId, const FString& CloneInstanceId,
	const FString& CopySourceCharacterId, int32 Delta)
{
	FTreadM1PoolLedgerEntry Entry;
	Entry.Revision = ++MatchState.PoolLedger.Revision;
	Entry.EntryId = FString::Printf(TEXT("ledger_%06d"), Entry.Revision);
	Entry.Action = Action;
	Entry.PlayerId = PlayerId;
	Entry.CharacterId = CharacterId;
	Entry.OperatorTier = OperatorTier;
	Entry.UnitInstanceId = UnitInstanceId;
	Entry.CloneInstanceId = CloneInstanceId;
	Entry.CopySourceCharacterId = CopySourceCharacterId;
	if (const FTreadM1PoolBalance* Balance = FindPoolBalance(CharacterId, OperatorTier))
	{
		Entry.PoolCopiesTotal = Balance->PoolCopiesTotal;
		Entry.PoolCopiesAvailable = Balance->PoolCopiesAvailable;
		Entry.ReservedCopies = Balance->ReservedCopies;
		Entry.OwnedCopies = Balance->OwnedCopies;
	}
	Entry.Delta = Delta;
	MatchState.PoolLedger.Entries.Add(MoveTemp(Entry));
}

bool ATreadM1MatchController::ApplyPoolLedgerDelta(const FString& Action, const FString& PlayerId, const FString& CharacterId,
	const FString& OperatorTier, const FString& UnitInstanceId, const FString& CloneInstanceId,
	const FString& CopySourceCharacterId, int32 Delta)
{
	// Transform copies are owned instances and intentionally never consume the shared pool.
	if (!CloneInstanceId.IsEmpty() || Action == TEXT("CloneCreate") || Action == TEXT("CloneDestroy"))
	{
		AppendPoolLedgerEntry(Action, PlayerId, CharacterId, OperatorTier, UnitInstanceId, CloneInstanceId, CopySourceCharacterId, 0);
		return true;
	}
	FTreadM1PoolBalance* Balance = FindPoolBalance(CharacterId, OperatorTier);
	if (!Balance)
	{
		return false;
	}
	int32 AvailableDelta = 0;
	int32 ReservedDelta = 0;
	int32 OwnedDelta = 0;
	if (Action == TEXT("Reserve"))
	{
		ReservedDelta = -Delta;
		AvailableDelta = Delta;
	}
	else if (Action == TEXT("Purchase"))
	{
		ReservedDelta = Delta;
		OwnedDelta = -Delta;
	}
	else if (Action == TEXT("RefreshReturn") || Action == TEXT("SellReturn") || Action == TEXT("EliminationReturn"))
	{
		AvailableDelta = Delta;
		if (Action == TEXT("RefreshReturn") || (Action == TEXT("EliminationReturn") && UnitInstanceId.IsEmpty())) ReservedDelta = -Delta;
		else OwnedDelta = -Delta;
	}
	else if (Action == TEXT("CombineConsume"))
	{
		OwnedDelta = Delta;
	}
	else if (Action == TEXT("Initialize"))
	{
		AvailableDelta = 0;
	}
	else
	{
		return false;
	}
	if (Balance->PoolCopiesAvailable + AvailableDelta < 0 ||
		Balance->ReservedCopies + ReservedDelta < 0 || Balance->OwnedCopies + OwnedDelta < 0)
	{
		return false;
	}
	if (Balance->PoolCopiesAvailable + AvailableDelta + Balance->ReservedCopies + ReservedDelta + Balance->OwnedCopies + OwnedDelta != Balance->PoolCopiesTotal)
	{
		return false;
	}
	Balance->PoolCopiesAvailable += AvailableDelta;
	Balance->ReservedCopies += ReservedDelta;
	Balance->OwnedCopies += OwnedDelta;
	AppendPoolLedgerEntry(Action, PlayerId, CharacterId, OperatorTier, UnitInstanceId, CloneInstanceId, CopySourceCharacterId, Delta);
	return true;
}

bool ATreadM1MatchController::RecordPoolLedger(const FString& Action, const FString& PlayerId, const FTreadM1ShopSlot& Slot, int32 Delta)
{
	return ApplyPoolLedgerDelta(Action, PlayerId, Slot.CharacterId, Slot.OperatorTier, TEXT(""), TEXT(""), TEXT(""), Delta);
}

bool ATreadM1MatchController::RecordPoolLedger(const FString& Action, const FString& PlayerId, const FTreadM1UnitInstance& Unit, int32 Delta)
{
	return ApplyPoolLedgerDelta(Action, PlayerId, Unit.CharacterId, Unit.OperatorTier, Unit.UnitInstanceId, Unit.CloneInstanceId, Unit.CopySourceCharacterId, Delta);
}

FTreadM1PoolBalance ATreadM1MatchController::GetPoolBalance(const FString& CharacterId, const FString& OperatorTier) const
{
	if (const FTreadM1PoolBalance* Balance = FindPoolBalance(CharacterId, OperatorTier))
	{
		return *Balance;
	}
	return FTreadM1PoolBalance();
}

bool ATreadM1MatchController::ValidatePoolLedger() const
{
	TSet<FString> Keys;
	for (const FTreadM1PoolBalance& Balance : MatchState.PoolLedger.Balances)
	{
		const FString Key = Balance.CharacterId + TEXT("+") + Balance.OperatorTier;
		if (Keys.Contains(Key))
		{
			return false;
		}
		Keys.Add(Key);
		int32 ExpectedTotal = INDEX_NONE;
		if (HasN1Economy())
		{
			const FTreadM2Card* Card = PactData->FindCard(Balance.CharacterId);
			ExpectedTotal = Card && Card->OperatorTier == Balance.OperatorTier ? Card->PoolCopies : INDEX_NONE;
		}
		for (int32 TierIndex = 0; TierIndex < UE_ARRAY_COUNT(PoolTierNames) && !HasN1Economy(); ++TierIndex)
		{
			if (Balance.OperatorTier == PoolTierNames[TierIndex])
			{
				ExpectedTotal = PoolTierTotals[TierIndex];
				break;
			}
		}
		if (Balance.PoolCopiesTotal < 0 || Balance.PoolCopiesAvailable < 0 || Balance.ReservedCopies < 0 || Balance.OwnedCopies < 0 ||
			ExpectedTotal == INDEX_NONE || Balance.PoolCopiesTotal != ExpectedTotal ||
			Balance.PoolCopiesAvailable + Balance.ReservedCopies + Balance.OwnedCopies != Balance.PoolCopiesTotal)
		{
			return false;
		}
	}
	if (HasN1Economy()) return MatchState.PoolLedger.Balances.Num() > 0;
	return MatchState.PoolLedger.Balances.Num() == ShopCharacterCount * UE_ARRAY_COUNT(PoolTierNames);
}

FTreadM1CommandResult ATreadM1MatchController::PurchaseShopSlot(const FString& PlayerId, int32 SlotIndex, const FString& RequestId)
{
	FTreadM1CommandResult CachedResult;
	if (TryGetProcessedRequest(RequestId, CachedResult))
	{
		return CachedResult;
	}

	if (MatchState.Phase != ETreadM1Phase::Preparation)
	{
		return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
	}
	FTreadM1PlayerState* Player = FindPlayer(PlayerId);
	if (!Player || Player->bIsEliminated)
	{
		return Reject(ETreadM1RejectReason::PlayerEliminated, RequestId);
	}
	if (!Player->Shop.Slots.IsValidIndex(SlotIndex))
	{
		return Reject(ETreadM1RejectReason::ShopSlotEmpty, RequestId);
	}
	FTreadM1ShopSlot& Slot = Player->Shop.Slots[SlotIndex];
	if (Slot.bIsSold || Slot.CharacterId.IsEmpty())
	{
		return Reject(ETreadM1RejectReason::ShopSlotSold, RequestId);
	}
	if (Player->BenchUnits.Num() >= MatchState.Rules.MaxBenchSlots)
	{
		return Reject(ETreadM1RejectReason::BenchFull, RequestId);
	}
	int32 Price = FMath::Max(0, Slot.Cost + Player->ShopPriceDelta);
	if (HasN1Economy() && Player->Flags.Contains(TEXT("flag:FirstBuyPrice")))
	{
		const FTreadM2StrategyBus* Bus = PactData->FindStrategy(Player->InitialStrategyId);
		const FTreadM2Card* Card = PactData->FindCard(Slot.CharacterId);
		const FString RoundKey = FString::Printf(TEXT("firstbuy@%d"), MatchState.RoundIndex);
		for (const FTreadM2StrategyEffect& Item : Bus ? Bus->Effects : TArray<FTreadM2StrategyEffect>())
		{
			if (Item.Effect.Op != TEXT("FirstBuyPrice") || !Card || Player->Flags.Contains(RoundKey)) continue;
			for (const FString& Pact : Item.Effect.Pacts)
			{
				if (Card->CorePacts.Contains(Pact) || Card->AdjunctPacts.Contains(Pact)) Price = FMath::Min(Price, FMath::RoundToInt(Item.Effect.BaseValue));
			}
		}
	}
	if (Player->Funds < Price)
	{
		return Reject(ETreadM1RejectReason::InsufficientFunds, RequestId);
	}
	if (!RecordPoolLedger(TEXT("Purchase"), PlayerId, Slot, -1))
	{
		return Reject(ETreadM1RejectReason::Unknown, RequestId);
	}
	if (HasN1Economy() && Price < FMath::Max(0, Slot.Cost + Player->ShopPriceDelta))
	{
		Player->Flags.AddUnique(FString::Printf(TEXT("firstbuy@%d"), MatchState.RoundIndex));
	}
	Player->Funds -= Price;
	Player->FundsSpentThisRound += Price;
	++Player->AcquiredThisRound;
	FTreadM1UnitInstance Unit;
	Unit.UnitInstanceId = FString::Printf(TEXT("%s_unit_%04d"), *PlayerId, ++UnitInstanceSequence);
	Unit.CharacterId = Slot.CharacterId;
	Unit.OperatorTier = Slot.OperatorTier;
	Unit.OriginalOperatorName = Slot.CharacterId;
	Unit.Cost = Slot.Cost;
	Unit.OwnerPlayerId = PlayerId;
	Unit.Location = ETreadM1UnitLocation::Bench;
	Player->BenchUnits.Add(Unit);
	const int32 EmptyIndex = Player->BenchUnitInstanceIds.Find(FString());
	if (EmptyIndex != INDEX_NONE)
	{
		Player->BenchUnitInstanceIds[EmptyIndex] = Unit.UnitInstanceId;
	}
	else
	{
		Player->BenchUnitInstanceIds.Add(Unit.UnitInstanceId);
	}
	Slot.bIsSold = true;
	// M2: <获得时> traits, investor repeats and automatic same-star combine.
	HandleUnitAcquired(*Player, Unit.UnitInstanceId, TEXT("Purchase"), 0);
	RefreshProjectedIncomes();
	RefreshScoutSnapshots();
	OnStateChanged.Broadcast();
	return Accept(RequestId);
}

float ATreadM1MatchController::AmmoAttackMultiplier(const FTreadM1PlayerState& Player, const FTreadM1UnitInstance& Unit) const
{
	if (!PactData.IsValid())
	{
		return 1.0f;
	}
	const int32 Spent = BattleAmmoSpent.FindRef(Unit.UnitInstanceId);
	if (Spent <= 0)
	{
		return 1.0f;
	}
	for (const FString& Pact : GetUnitPacts(Player, Unit, false))
	{
		const FTreadM2PactDef* Def = PactData->FindPact(Pact);
		if (Def && Def->AmmoAtkPerRound > 0.0f && Def->AmmoMaxAtkMul > 1.0f)
		{
			return FMath::Min(Def->AmmoMaxAtkMul, 1.0f + Spent * Def->AmmoAtkPerRound);
		}
	}
	return 1.0f;
}

void ATreadM1MatchController::FeedForesightLayers(FTreadM1PlayerState& Player)
{
	if (!PactData.IsValid() || !PactData->bLoaded)
	{
		return;
	}
	// 远见 counts on the bench and gains a layer with every shop refresh; its milestones pay the funds.
	for (const FTreadM2PactDef& Def : PactData->Pacts)
	{
		if (Def.PactId != TEXT("远见"))
		{
			continue;
		}
		if (const FTreadM2PactProgress* Progress = FindPactProgress(Player, Def.PactId))
		{
			if (Progress->bActive)
			{
				AddPactStacks(Player, Def.PactId, 1, false, TEXT("Refresh"), nullptr, ETreadM2Trigger::ShopRefresh,
					TEXT("ForesightRefresh"), false);
			}
		}
		return;
	}
}

FTreadM1CommandResult ATreadM1MatchController::RefreshShop(const FString& PlayerId, const FString& RequestId)
{
	FTreadM1CommandResult CachedResult;
	if (TryGetProcessedRequest(RequestId, CachedResult))
	{
		return CachedResult;
	}

	if (MatchState.Phase != ETreadM1Phase::Preparation)
	{
		return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
	}
	FTreadM1PlayerState* Player = FindPlayer(PlayerId);
	if (!Player || Player->bIsEliminated)
	{
		return Reject(ETreadM1RejectReason::PlayerEliminated, RequestId);
	}
	const bool bFree = Player->FreeRefreshes > 0;
	const int32 Cost = bFree ? 0 : Player->Shop.RefreshCost;
	if (Player->Funds < Cost)
	{
		return Reject(ETreadM1RejectReason::InsufficientFunds, RequestId);
	}
	if (bFree) --Player->FreeRefreshes;
	Player->Funds -= Cost;
	Player->FundsSpentThisRound += Cost;
	++Player->RefreshesThisRound;
	const bool bLocked = Player->Shop.bLocked;
	BuildShop(*Player, Player->Shop.RefreshIndex + 1);
	Player->Shop.bLocked = bLocked;
	for (FTreadM1ShopSlot& Slot : Player->Shop.Slots)
	{
		Slot.bIsLockedByPlayer = bLocked;
	}
	DispatchTraitEvent(*Player, ETreadM2Trigger::ShopRefresh, TEXT("ShopRefresh"));
	FeedForesightLayers(*Player);
	// 奇迹 (document/171): the refresh itself may hand out a free refresh.
	TryMiracleFreeRefresh(*Player);
	RefreshProjectedIncomes();
	RefreshScoutSnapshots();
	OnStateChanged.Broadcast();
	return Accept(RequestId);
}

FTreadM1CommandResult ATreadM1MatchController::ToggleShopLock(const FString& PlayerId, const FString& RequestId)
{
	FTreadM1CommandResult CachedResult;
	if (TryGetProcessedRequest(RequestId, CachedResult))
	{
		return CachedResult;
	}

	if (MatchState.Phase != ETreadM1Phase::Preparation)
	{
		return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
	}
	FTreadM1PlayerState* Player = FindPlayer(PlayerId);
	if (!Player || Player->bIsEliminated)
	{
		return Reject(ETreadM1RejectReason::PlayerEliminated, RequestId);
	}
	Player->Shop.bLocked = !Player->Shop.bLocked;
	for (FTreadM1ShopSlot& Slot : Player->Shop.Slots)
	{
		Slot.bIsLockedByPlayer = Player->Shop.bLocked;
	}
	OnStateChanged.Broadcast();
	return Accept(RequestId);
}

FTreadM1CommandResult ATreadM1MatchController::SellUnit(const FString& PlayerId, const FString& UnitInstanceId, const FString& RequestId)
{
	FTreadM1CommandResult CachedResult;
	if (TryGetProcessedRequest(RequestId, CachedResult))
	{
		return CachedResult;
	}

	if (MatchState.Phase != ETreadM1Phase::Preparation)
	{
		return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
	}
	FTreadM1PlayerState* Player = FindPlayer(PlayerId);
	if (!Player || Player->bIsEliminated)
	{
		return Reject(ETreadM1RejectReason::PlayerEliminated, RequestId);
	}
	FTreadM1UnitInstance SoldUnit;
	bool bFound = false;
	bool bRemovedFromBoard = false;
	for (int32 Index = 0; Index < Player->BenchUnits.Num(); ++Index)
	{
		if (Player->BenchUnits[Index].UnitInstanceId == UnitInstanceId)
		{
			SoldUnit = Player->BenchUnits[Index];
			Player->BenchUnits.RemoveAt(Index);
			bFound = true;
			break;
		}
	}
	if (!bFound)
	{
		for (int32 Index = 0; Index < Player->BoardUnits.Num(); ++Index)
		{
			if (Player->BoardUnits[Index].UnitInstanceId == UnitInstanceId)
			{
				SoldUnit = Player->BoardUnits[Index];
				Player->BoardUnits.RemoveAt(Index);
				Player->PopulationUsed = FMath::Max(0, Player->PopulationUsed - 1);
				bRemovedFromBoard = true;
				bFound = true;
				break;
			}
		}
	}
	if (!bFound || SoldUnit.OwnerPlayerId != PlayerId)
	{
		return Reject(ETreadM1RejectReason::NotOwnUnit, RequestId);
	}
	// A transform clone has no purchased pool copy or sale value. Selling it
	// only destroys the instance and writes a zero-delta audit event. A combined
	// unit refunds every held copy minus the one-fund upgrade discount.
	int32 SalePrice = SoldUnit.bIsTransformClone ? 0
		: FMath::Max(0, SoldUnit.Cost * FMath::Max(1, SoldUnit.PoolCopiesHeld) - (SoldUnit.UnitStar > 1 ? 1 : 0));
	if (HasN1Economy() && !SoldUnit.bIsTransformClone)
	{
		const int32* Sell = PactData->Economy.SellByTier.Find(SoldUnit.OperatorTier);
		SalePrice = Sell ? *Sell : 1;
	}
	Player->Funds += SalePrice;
	if (SoldUnit.bIsTransformClone && !bRemovedFromBoard)
	{
		Player->PopulationUsed = FMath::Max(0, Player->PopulationUsed - 1);
	}
	SoldUnit.Location = ETreadM1UnitLocation::Removed;
	if (!bRemovedFromBoard)
	{
		const int32 BenchSlot = Player->BenchUnitInstanceIds.Find(SoldUnit.UnitInstanceId);
		if (BenchSlot != INDEX_NONE)
		{
			Player->BenchUnitInstanceIds[BenchSlot].Empty();
		}
	}
	RecordPoolLedger(SoldUnit.bIsTransformClone ? TEXT("CloneDestroy") : TEXT("SellReturn"), PlayerId, SoldUnit,
		SoldUnit.bIsTransformClone ? 0 : FMath::Max(1, SoldUnit.PoolCopiesHeld));
	DispatchTraitEvent(*Player, ETreadM2Trigger::Sell, TEXT("Sell"), &SoldUnit);
	// document/178: 5_07 counts sales and pays one operator of the holder's pact every N.
	++Player->SoldCount;
	for (const FTreadM1UnitInstance& BoardUnit : Player->BoardUnits)
	{
		for (const FString& ItemId : BoardUnit.EquipmentIds)
		{
			const FTreadM2Item* Item = PactData.IsValid() ? PactData->FindItem(ItemId) : nullptr;
			if (!Item) continue;
			for (const FTreadM2ItemProc& Proc : Item->Procs)
			{
				if (Proc.Op != TEXT("SellCounterRecruit")) continue;
				if (Player->SoldCount < FMath::Max(1, Proc.Count)) continue;
				Player->SoldCount = 0;
				GrantRecruitFromItem(*Player, BoardUnit, *Item);
			}
		}
	}
	RefreshProjectedIncomes();
	RefreshScoutSnapshots();
	OnStateChanged.Broadcast();
	return Accept(RequestId);
}

FTreadM1CommandResult ATreadM1MatchController::CreateTransformClone(const FString& PlayerId,
	const FString& CopySourceCharacterId, const FString& RequestId)
{
	FTreadM1CommandResult CachedResult;
	if (TryGetProcessedRequest(RequestId, CachedResult))
	{
		return CachedResult;
	}

	if (MatchState.Phase != ETreadM1Phase::Preparation)
	{
		return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
	}
	if (CopySourceCharacterId.IsEmpty())
	{
		return Reject(ETreadM1RejectReason::InvalidTarget, RequestId);
	}
	FTreadM1PlayerState* Player = FindPlayer(PlayerId);
	if (!Player || Player->bIsEliminated)
	{
		return Reject(ETreadM1RejectReason::PlayerEliminated, RequestId);
	}
	for (const FTreadM1UnitInstance& Unit : Player->BoardUnits)
	{
		if (!Unit.bIsTransformClone && Unit.CharacterId == CopySourceCharacterId)
		{
			return CreateTransformCloneInternal(PlayerId, Unit, RequestId);
		}
	}
	for (const FTreadM1UnitInstance& Unit : Player->BenchUnits)
	{
		if (!Unit.bIsTransformClone && Unit.CharacterId == CopySourceCharacterId)
		{
			return CreateTransformCloneInternal(PlayerId, Unit, RequestId);
		}
	}
	return Reject(ETreadM1RejectReason::InvalidTarget, RequestId);
}

FTreadM1CommandResult ATreadM1MatchController::CreateTransformCloneFromUnit(const FString& PlayerId,
	const FString& SourceUnitInstanceId, const FString& RequestId)
{
	FTreadM1CommandResult CachedResult;
	if (TryGetProcessedRequest(RequestId, CachedResult))
	{
		return CachedResult;
	}

	if (MatchState.Phase != ETreadM1Phase::Preparation)
	{
		return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
	}
	FTreadM1PlayerState* Player = FindPlayer(PlayerId);
	if (!Player || Player->bIsEliminated)
	{
		return Reject(ETreadM1RejectReason::PlayerEliminated, RequestId);
	}
	for (const FTreadM1UnitInstance& Unit : Player->BoardUnits)
	{
		if (Unit.UnitInstanceId == SourceUnitInstanceId)
		{
			return Unit.bIsTransformClone ? Reject(ETreadM1RejectReason::InvalidTarget, RequestId)
				: CreateTransformCloneInternal(PlayerId, Unit, RequestId);
		}
	}
	for (const FTreadM1UnitInstance& Unit : Player->BenchUnits)
	{
		if (Unit.UnitInstanceId == SourceUnitInstanceId)
		{
			return Unit.bIsTransformClone ? Reject(ETreadM1RejectReason::InvalidTarget, RequestId)
				: CreateTransformCloneInternal(PlayerId, Unit, RequestId);
		}
	}
	return Reject(ETreadM1RejectReason::NotOwnUnit, RequestId);
}

FTreadM1CommandResult ATreadM1MatchController::CreateTransformCloneInternal(const FString& PlayerId,
	const FTreadM1UnitInstance& SourceUnit, const FString& RequestId)
{
	FTreadM1PlayerState* Player = FindPlayer(PlayerId);
	if (!Player || SourceUnit.OwnerPlayerId != PlayerId || SourceUnit.bIsTransformClone)
	{
		return Reject(ETreadM1RejectReason::InvalidTarget, RequestId);
	}
	if (Player->BenchUnits.Num() >= MatchState.Rules.MaxBenchSlots)
	{
		return Reject(ETreadM1RejectReason::BenchFull, RequestId);
	}
	if (Player->PopulationUsed >= Player->PopulationLimit)
	{
		return Reject(ETreadM1RejectReason::PopulationLimitReached, RequestId);
	}
	FTreadM1UnitInstance Clone;
	Clone.UnitInstanceId = FString::Printf(TEXT("%s_clone_unit_%04d"), *PlayerId, ++UnitInstanceSequence);
	Clone.CharacterId = SourceUnit.CharacterId;
	Clone.OriginalOperatorName = SourceUnit.OriginalOperatorName;
	Clone.OperatorTier = SourceUnit.OperatorTier;
	Clone.UnitStar = SourceUnit.UnitStar;
	Clone.Cost = SourceUnit.Cost;
	Clone.Location = ETreadM1UnitLocation::Bench;
	Clone.OwnerPlayerId = PlayerId;
	Clone.EquipmentIds = SourceUnit.EquipmentIds;
	Clone.bIsTransformClone = true;
	Clone.CopySourceCharacterId = SourceUnit.CharacterId;
	Clone.CloneInstanceId = FString::Printf(TEXT("clone_%s_%04d"), *PlayerId, ++CloneInstanceSequence);
	Clone.PoolCopiesHeld = 0;
	Player->BenchUnits.Add(Clone);
	const int32 EmptyIndex = Player->BenchUnitInstanceIds.Find(FString());
	if (EmptyIndex != INDEX_NONE)
	{
		Player->BenchUnitInstanceIds[EmptyIndex] = Clone.UnitInstanceId;
	}
	else
	{
		Player->BenchUnitInstanceIds.Add(Clone.UnitInstanceId);
	}
	++Player->PopulationUsed;
	RecordPoolLedger(TEXT("CloneCreate"), PlayerId, Clone, 0);
	// Clones count as the copied character and may complete a same-star combine.
	TryAutoCombine(*Player, Clone.CharacterId, Clone.OperatorTier, 0);
	RefreshProjectedIncomes();
	RefreshScoutSnapshots();
	OnStateChanged.Broadcast();
	return Accept(RequestId);
}

FTreadM1CommandResult ATreadM1MatchController::DestroyTransformClone(const FString& PlayerId,
	const FString& CloneInstanceId, const FString& RequestId)
{
	FTreadM1CommandResult CachedResult;
	if (TryGetProcessedRequest(RequestId, CachedResult))
	{
		return CachedResult;
	}

	if (MatchState.Phase != ETreadM1Phase::Preparation)
	{
		return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
	}
	FTreadM1PlayerState* Player = FindPlayer(PlayerId);
	if (!Player || Player->bIsEliminated)
	{
		return Reject(ETreadM1RejectReason::PlayerEliminated, RequestId);
	}
	FTreadM1UnitInstance DestroyedClone;
	bool bFound = false;
	bool bRemovedFromBoard = false;
	for (int32 Index = 0; Index < Player->BenchUnits.Num(); ++Index)
	{
		if (Player->BenchUnits[Index].CloneInstanceId == CloneInstanceId)
		{
			DestroyedClone = Player->BenchUnits[Index];
			Player->BenchUnits.RemoveAt(Index);
			bFound = true;
			break;
		}
	}
	if (!bFound)
	{
		for (int32 Index = 0; Index < Player->BoardUnits.Num(); ++Index)
		{
			if (Player->BoardUnits[Index].CloneInstanceId == CloneInstanceId)
			{
				DestroyedClone = Player->BoardUnits[Index];
				Player->BoardUnits.RemoveAt(Index);
				bRemovedFromBoard = true;
				bFound = true;
				break;
			}
		}
	}
	if (!bFound || !DestroyedClone.bIsTransformClone || DestroyedClone.OwnerPlayerId != PlayerId)
	{
		return Reject(ETreadM1RejectReason::InvalidTarget, RequestId);
	}
	DestroyedClone.Location = ETreadM1UnitLocation::Removed;
	if (!bRemovedFromBoard)
	{
		const int32 BenchSlot = Player->BenchUnitInstanceIds.Find(DestroyedClone.UnitInstanceId);
		if (BenchSlot != INDEX_NONE)
		{
			Player->BenchUnitInstanceIds[BenchSlot].Empty();
		}
	}
	Player->PopulationUsed = FMath::Max(0, Player->PopulationUsed - 1);
	RecordPoolLedger(TEXT("CloneDestroy"), PlayerId, DestroyedClone, 0);
	RefreshProjectedIncomes();
	RefreshScoutSnapshots();
	OnStateChanged.Broadcast();
	return Accept(RequestId);
}

FTreadM1CommandResult ATreadM1MatchController::BuyExperience(const FString& PlayerId, const FString& RequestId)
{
	FTreadM1CommandResult CachedResult;
	if (TryGetProcessedRequest(RequestId, CachedResult))
	{
		return CachedResult;
	}

	if (MatchState.Phase != ETreadM1Phase::Preparation)
	{
		return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
	}
	FTreadM1PlayerState* Player = FindPlayer(PlayerId);
	if (!Player || Player->bIsEliminated)
	{
		return Reject(ETreadM1RejectReason::PlayerEliminated, RequestId);
	}
	if (HasN1Economy())
	{
		if (Player->Level >= PactData->Economy.MaxShopLevel)
		{
			return Reject(ETreadM1RejectReason::MaxLevelReached, RequestId);
		}
		const int32 UpgradeCost = ShopUpgradeCost(*Player);
		if (Player->Funds < UpgradeCost)
		{
			return Reject(ETreadM1RejectReason::InsufficientFunds, RequestId);
		}
		Player->Funds -= UpgradeCost;
		Player->FundsSpentThisRound += UpgradeCost;
		++Player->Level;
		Player->ShopUpgradeDiscount = 0;
		Player->ExperienceToNextLevel = ShopUpgradeCost(*Player);
		DispatchTraitEvent(*Player, ETreadM2Trigger::BuyExperience, TEXT("ShopUpgrade"));
		RefreshProjectedIncomes();
		RefreshScoutSnapshots();
		OnStateChanged.Broadcast();
		return Accept(RequestId);
	}
	if (Player->Level >= 9)
	{
		return Reject(ETreadM1RejectReason::MaxLevelReached, RequestId);
	}
	if (Player->Funds < MatchState.Rules.ExperiencePurchaseCost)
	{
		return Reject(ETreadM1RejectReason::InsufficientFunds, RequestId);
	}
	Player->Funds -= MatchState.Rules.ExperiencePurchaseCost;
	Player->FundsSpentThisRound += MatchState.Rules.ExperiencePurchaseCost;
	ApplyExperience(*Player, MatchState.Rules.ExperiencePurchaseAmount);
	DispatchTraitEvent(*Player, ETreadM2Trigger::BuyExperience, TEXT("BuyExperience"));
	RefreshProjectedIncomes();
	RefreshScoutSnapshots();
	OnStateChanged.Broadcast();
	return Accept(RequestId);
}

void ATreadM1MatchController::AdvancePreparationTimer(float DeltaSeconds)
{
	if (MatchState.Phase != ETreadM1Phase::Preparation || DeltaSeconds <= 0.0f)
	{
		return;
	}
	MatchState.PhaseTimeRemainingSec = FMath::Max(0.0f, MatchState.PhaseTimeRemainingSec - DeltaSeconds);
	if (MatchState.PhaseTimeRemainingSec <= 0.0f)
	{
		DeployAndStartBattle(FString::Printf(TEXT("runtime:round-%d:preparation-timer"), MatchState.RoundIndex));
	}
	else
	{
		OnStateChanged.Broadcast();
	}
}

FTreadM1IncomeBreakdown ATreadM1MatchController::GetNextRoundIncome(const FString& PlayerId) const
{
	if (const FTreadM1PlayerState* Player = FindPlayer(PlayerId))
	{
		return Player->NextRoundIncome;
	}
	return FTreadM1IncomeBreakdown();
}

FTreadM1CommandResult ATreadM1MatchController::BeginPreMatchBP(const FString& RequestId)
{
	FTreadM1CommandResult CachedResult;
	if (TryGetProcessedRequest(RequestId, CachedResult))
	{
		return CachedResult;
	}

	if (MatchState.Phase != ETreadM1Phase::R0Briefing)
	{
		return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
	}
	TArray<FString> Ids;
	for (const FTreadM1StrategyState& Strategy : MatchState.Strategies)
	{
		if (Strategy.bBpEligible)
		{
			Ids.Add(Strategy.StrategyId);
		}
	}
	for (int32 Index = Ids.Num() - 1; Index > 0; --Index)
	{
		Ids.Swap(Index, RandomStream.RandRange(0, Index));
	}
	SyncRandomState();
	MatchState.BP.BannedStrategyIds.Reset();
	MatchState.BP.AvailableStrategyIds.Reset();
	for (int32 Index = 0; Index < Ids.Num(); ++Index)
	{
		(Index < MatchState.BP.SystemBanCount ? MatchState.BP.BannedStrategyIds : MatchState.BP.AvailableStrategyIds).Add(Ids[Index]);
	}
	MatchState.BP.PlayerStrategyId.Empty();
	MatchState.BP.AiStrategyIds.Init(FString(), 3);
	MatchState.BP.AiPickStates.Init(ETreadM1AIPickState::Waiting, 3);
	MatchState.BP.bConfirmed = false;
	SetPhase(ETreadM1Phase::PreMatchBP);
	return Accept(RequestId);
}

FTreadM1CommandResult ATreadM1MatchController::ChoosePlayerStrategy(const FString& StrategyId, const FString& RequestId)
{
	FTreadM1CommandResult CachedResult;
	if (TryGetProcessedRequest(RequestId, CachedResult))
	{
		return CachedResult;
	}

	if (MatchState.Phase != ETreadM1Phase::PreMatchBP)
	{
		return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
	}
	if (!IsAvailableStrategy(StrategyId))
	{
		return Reject(ETreadM1RejectReason::StrategyUnavailable, RequestId);
	}
	if (MatchState.BP.bConfirmed)
	{
		return Reject(ETreadM1RejectReason::StrategyLocked, RequestId);
	}
	for (const FString& AiStrategy : MatchState.BP.AiStrategyIds)
	{
		if (AiStrategy == StrategyId)
		{
			return Reject(ETreadM1RejectReason::StrategyAlreadyChosen, RequestId);
		}
	}
	MatchState.BP.PlayerStrategyId = StrategyId;
	OnStateChanged.Broadcast();
	return Accept(RequestId);
}

FTreadM1CommandResult ATreadM1MatchController::RunNextAIPick(const FString& RequestId)
{
	FTreadM1CommandResult CachedResult;
	if (TryGetProcessedRequest(RequestId, CachedResult))
	{
		return CachedResult;
	}

	if (MatchState.Phase != ETreadM1Phase::PreMatchBP)
	{
		return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
	}
	if (MatchState.BP.PlayerStrategyId.IsEmpty())
	{
		return Reject(ETreadM1RejectReason::StrategyUnavailable, RequestId);
	}
	for (int32 Index = 0; Index < MatchState.BP.AiPickStates.Num(); ++Index)
	{
		if (MatchState.BP.AiPickStates[Index] == ETreadM1AIPickState::Waiting)
		{
			MatchState.BP.AiPickStates[Index] = ETreadM1AIPickState::Thinking;
			TArray<FString> Candidates;
			for (const FString& Candidate : MatchState.BP.AvailableStrategyIds)
			{
				if (Candidate == MatchState.BP.PlayerStrategyId || MatchState.BP.AiStrategyIds.Contains(Candidate))
				{
					continue;
				}
				Candidates.Add(Candidate);
			}
			if (Candidates.Num() > 0)
			{
				MatchState.BP.AiStrategyIds[Index] = Candidates[RandomStream.RandRange(0, Candidates.Num() - 1)];
			}
			SyncRandomState();
			MatchState.BP.AiPickStates[Index] = ETreadM1AIPickState::Confirmed;
			OnStateChanged.Broadcast();
			return MatchState.BP.AiStrategyIds[Index].IsEmpty() ? Reject(ETreadM1RejectReason::StrategyUnavailable, RequestId) : Accept(RequestId);
		}
	}
	return Reject(ETreadM1RejectReason::AlreadyConfirmed, RequestId);
}

FTreadM1CommandResult ATreadM1MatchController::ConfirmPreMatchBP(const FString& RequestId)
{
	FTreadM1CommandResult CachedResult;
	if (TryGetProcessedRequest(RequestId, CachedResult))
	{
		return CachedResult;
	}

	if (MatchState.Phase != ETreadM1Phase::PreMatchBP)
	{
		return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
	}
	if (MatchState.BP.PlayerStrategyId.IsEmpty() || MatchState.BP.AiStrategyIds.Contains(FString()) || MatchState.BP.AiStrategyIds.Num() != 3)
	{
		return Reject(ETreadM1RejectReason::StrategyUnavailable, RequestId);
	}
	TSet<FString> Chosen;
	Chosen.Add(MatchState.BP.PlayerStrategyId);
	for (const FString& StrategyId : MatchState.BP.AiStrategyIds)
	{
		if (Chosen.Contains(StrategyId))
		{
			return Reject(ETreadM1RejectReason::StrategyAlreadyChosen, RequestId);
		}
		Chosen.Add(StrategyId);
	}
	MatchState.BP.bConfirmed = true;
	ApplyInitialStrategyCosts();
	SetPhase(ETreadM1Phase::Preparation);
	MatchState.RoundIndex = 1;
	SetRoundTypeForCurrentRound();
	MatchState.PhaseTimeRemainingSec = static_cast<float>(MatchState.Rules.PreparationDurationSec);
	// document/176: round 1 enters preparation here (BeginPreparation rolls rewards for rounds 2+).
	for (FTreadM1PlayerState& Player : MatchState.Players)
	{
		if (!Player.bIsEliminated)
		{
			RollRewardOffer(Player);
		}
	}
	// document/165: the AI turn must also run in round 1, or the first battle meets three placeholder boards.
	RunAIPreparation();
	for (FTreadM1PlayerState& Player : MatchState.Players)
	{
		RecomputePacts(Player);
		DispatchTraitEvent(Player, ETreadM2Trigger::MatchStart, TEXT("MatchStart"));
	}
	DispatchRoundTrigger(ETreadM2Trigger::RoundStart, TEXT("EnterPreparation"));
	RefreshProjectedIncomes();
	RefreshScoutSnapshots();
	return Accept(RequestId);
}

void ATreadM1MatchController::ApplyInitialStrategyCosts()
{
	if (bInitialStrategyCostsApplied)
	{
		return;
	}
	bInitialStrategyCostsApplied = true;
	const TArray<FString> Chosen = {MatchState.BP.PlayerStrategyId, MatchState.BP.AiStrategyIds[0], MatchState.BP.AiStrategyIds[1], MatchState.BP.AiStrategyIds[2]};
	for (int32 Index = 0; Index < MatchState.Players.Num() && Index < Chosen.Num(); ++Index)
	{
		FTreadM1PlayerState& Player = MatchState.Players[Index];
		Player.InitialStrategyId = Chosen[Index];
		if (FTreadM1StrategyState* Strategy = FindStrategy(Chosen[Index]))
		{
			Player.Health = FMath::Max(0, Player.Health - Strategy->HpCost);
			if (Player.Health == 0)
			{
				Player.bIsEliminated = true;
				ReturnPlayerPoolAssets(Player);
			}
		}
	}
}

void ATreadM1MatchController::RunAIPreparation()
{
	if (!bAIOpponentsPlay || !HasN1Economy() || !PactData)
	{
		return;
	}
	const int32 BenchCap = FMath::Max(1, MatchState.Rules.MaxBenchSlots);
	// Front-to-back ladder on the AI half (rows 0-3, row 3 touches the middle of the board). The presentation mirrors
	// these cells for the enemy board, so the same layout reads as "front line first".
	static const FIntPoint Ladder[] = {
		FIntPoint(2, 3), FIntPoint(3, 3), FIntPoint(4, 3), FIntPoint(1, 3), FIntPoint(5, 3),
		FIntPoint(2, 2), FIntPoint(3, 2), FIntPoint(4, 2), FIntPoint(1, 2), FIntPoint(5, 2),
		FIntPoint(0, 2), FIntPoint(6, 2), FIntPoint(2, 1), FIntPoint(3, 1), FIntPoint(4, 1),
		FIntPoint(1, 1), FIntPoint(5, 1), FIntPoint(2, 0), FIntPoint(3, 0), FIntPoint(4, 0)};

	for (FTreadM1PlayerState& Player : MatchState.Players)
	{
		if (Player.bIsHuman || Player.bIsEliminated)
		{
			continue;
		}
		const FString PlayerId = Player.PlayerId;

		// 1) Keep the 调度中心 moving: one level per round while it stays affordable with a small reserve.
		if (Player.Level < PactData->Economy.MaxShopLevel)
		{
			const int32 UpgradeCost = ShopUpgradeCost(Player);
			if (UpgradeCost > 0 && Player.Funds >= UpgradeCost + 2)
			{
				BuyExperience(PlayerId, FString());
			}
		}

		// 2) Buy: copies that are close to a merge first, then the cheapest affordable slot.
		for (int32 Attempt = 0; Attempt < 6; ++Attempt)
		{
			if (Player.BenchUnits.Num() + Player.BoardUnits.Num() >= BenchCap + Player.PopulationLimit)
			{
				break;
			}
			int32 BestSlot = INDEX_NONE;
			int32 BestScore = MIN_int32;
			int32 BestCost = MAX_int32;
			for (int32 SlotIndex = 0; SlotIndex < Player.Shop.Slots.Num(); ++SlotIndex)
			{
				const FTreadM1ShopSlot& ShopSlot = Player.Shop.Slots[SlotIndex];
				if (ShopSlot.bIsSold || ShopSlot.Cost > Player.Funds)
				{
					continue;
				}
				int32 Owned = 0;
				for (const FTreadM1UnitInstance& Unit : Player.BenchUnits)
				{
					Owned += Unit.CharacterId == ShopSlot.CharacterId ? 1 : 0;
				}
				for (const FTreadM1UnitInstance& Unit : Player.BoardUnits)
				{
					Owned += Unit.CharacterId == ShopSlot.CharacterId ? 1 : 0;
				}
				const int32 Score = Owned * 100 - ShopSlot.Cost;
				if (Score > BestScore || (Score == BestScore && ShopSlot.Cost < BestCost))
				{
					BestScore = Score;
					BestCost = ShopSlot.Cost;
					BestSlot = SlotIndex;
				}
			}
			if (BestSlot == INDEX_NONE)
			{
				break;
			}
			if (!PurchaseShopSlot(PlayerId, BestSlot, FString()).bAccepted)
			{
				break;
			}
		}

		// 3) Nothing affordable in the shop: one paid refresh (never while broke).
		bool bAffordableSlot = false;
		for (const FTreadM1ShopSlot& ShopSlot : Player.Shop.Slots)
		{
			bAffordableSlot |= !ShopSlot.bIsSold && ShopSlot.Cost <= Player.Funds;
		}
		if (!bAffordableSlot && Player.Funds >= 2)
		{
			RefreshShop(PlayerId, FString());
		}

		// 4) Deploy the strongest bench units, one per ladder cell, up to the population limit.
		TArray<FTreadM1UnitInstance> Candidates = Player.BenchUnits;
		Candidates.StableSort([](const FTreadM1UnitInstance& A, const FTreadM1UnitInstance& B)
		{
			return A.UnitStar != B.UnitStar ? A.UnitStar > B.UnitStar : A.Cost > B.Cost;
		});
		for (const FTreadM1UnitInstance& Candidate : Candidates)
		{
			if (Player.BoardUnits.Num() >= Player.PopulationLimit)
			{
				break;
			}
			FIntPoint Target = FIntPoint(-1, -1);
			for (const FIntPoint& Cell : Ladder)
			{
				bool bTaken = false;
				for (const FTreadM1UnitInstance& OnBoard : Player.BoardUnits)
				{
					bTaken |= OnBoard.BoardCell == Cell;
				}
				if (!bTaken)
				{
					Target = Cell;
					break;
				}
			}
			if (Target.X < 0)
			{
				break;
			}
			MoveUnitToBoard(PlayerId, Candidate.UnitInstanceId, Target, FString());
		}
		// 5) Equip: spend the inventory on the strongest deployed units, three slots each (document/175).
		{
			TArray<FString> Items = Player.EquipmentIds;
			for (const FString& ItemId : Items)
			{
				FTreadM1UnitInstance* Best = nullptr;
				for (FTreadM1UnitInstance& Owned : Player.BoardUnits)
				{
					if (Owned.EquipmentIds.Num() >= 3) continue;
					if (!Best || Owned.Cost * Owned.UnitStar > Best->Cost * Best->UnitStar) Best = &Owned;
				}
				if (!Best) break;
				EquipItem(PlayerId, ItemId, Best->UnitInstanceId, FString());
			}
		}
		// 6) Claim the free reward offer (document/176): the AI always takes the first choice.
		if (!Player.bRewardClaimed && Player.RewardOffer.Num() > 0)
		{
			ChooseReward(PlayerId, 0);
		}
		UE_LOG(LogTemp, Display, TEXT("Tread AI %s: L%d funds=%d board=%d bench=%d shop=%d"), *PlayerId,
			Player.Level, Player.Funds, Player.BoardUnits.Num(), Player.BenchUnits.Num(), Player.Shop.Slots.Num());
	}
	RefreshProjectedIncomes();
	RefreshScoutSnapshots();
}

FTreadM1CommandResult ATreadM1MatchController::BeginPreparation(const FString& RequestId)
{
	FTreadM1CommandResult CachedResult;
	if (TryGetProcessedRequest(RequestId, CachedResult))
	{
		return CachedResult;
	}

	if (MatchState.Phase != ETreadM1Phase::Settlement)
	{
		return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
	}
	const FTreadM1CommandResult Settlement = SettleRound(FString());
	if (!Settlement.bAccepted)
	{
		return Reject(Settlement.ReasonCode, RequestId);
	}
	const FTreadM1PlayerState* Human = FindPlayer(TEXT("P0"));
	if (LivingPlayerCount() <= 1 || (Human && Human->bIsEliminated) || MatchState.RoundIndex >= MaxRounds)
	{
		MatchState.PhaseTimeRemainingSec = 0.0f;
		RecordCampaignResult();
		SetPhase(ETreadM1Phase::GameOver);
		return Accept(RequestId);
	}
	++MatchState.RoundIndex;
	SetRoundTypeForCurrentRound();
	// M4: last round's garrison/leader leaves the board; the next scripted opponent is built at deployment.
	MatchState.ScriptedOpponentId.Reset();
	MatchState.ScriptedOpponentName.Reset();
	MatchState.ScriptedOpponentUnits.Reset();
	for (FTreadM1PlayerState& Player : MatchState.Players)
	{
		if (!Player.bIsEliminated)
		{
			if (!Player.Shop.bLocked)
			{
				BuildShop(Player, Player.Shop.RefreshIndex + 1);
			}
		}
	}
	MatchState.PhaseTimeRemainingSec = static_cast<float>(MatchState.Rules.PreparationDurationSec);
	for (FTreadM1PlayerState& Player : MatchState.Players)
	{
		Player.AcquiredThisRound = 0;
		Player.AcquireFundsCount = 0;
		Player.FundsSpentThisRound = 0;
		Player.RefreshesThisRound = 0;
		if (HasN1Economy())
		{
			++Player.ShopUpgradeDiscount;
			Player.ExperienceToNextLevel = ShopUpgradeCost(Player);
		}
	}
	DispatchRoundTrigger(ETreadM2Trigger::RoundStart, TEXT("EnterPreparation"));
	RankPlayers();
	// document/171: 炎 summons leave the board before the player can touch it again.
	for (FTreadM1PlayerState& Player : MatchState.Players)
	{
		StripSummons(Player);
	}
	SetPhase(ETreadM1Phase::Preparation);
	// document/176: every player entering preparation gets three free item choices.
	for (FTreadM1PlayerState& Player : MatchState.Players)
	{
		if (!Player.bIsEliminated)
		{
			RollRewardOffer(Player);
		}
	}
	// document/165: the other three players take their turn here (level up, buy, refresh, deploy).
	RunAIPreparation();
	RefreshProjectedIncomes();
	RefreshScoutSnapshots();
	return Accept(RequestId);
}

FTreadM1CommandResult ATreadM1MatchController::DeployAndStartBattle(const FString& RequestId)
{
	FTreadM1CommandResult CachedResult;
	if (TryGetProcessedRequest(RequestId, CachedResult))
	{
		return CachedResult;
	}

	if (MatchState.Phase != ETreadM1Phase::Preparation)
	{
		return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
	}
	// The battle UI observes these pairings as soon as the phase changes.
	// Resolving must use the same opponents rather than drawing a second shuffle.
	MatchState.LastBattleResult.RoundIndex = MatchState.RoundIndex;
	MatchState.LastBattleResult.Outcomes.Reset();
	MatchState.LastBattleResult.EliminatedPlayerIds.Reset();
	MatchState.LastBattleResult.IncomeBreakdown = FTreadM1IncomeBreakdown();
	// M2: <休整期结束时> traits and pact tier ops, then battle-start strategy effects.
	// Combat reads the pact state frozen here, which is also what ScoutSnapshot holds.
	DispatchRoundTrigger(ETreadM2Trigger::RoundEnd, TEXT("PreparationEnd"));
	for (FTreadM1PlayerState& Player : MatchState.Players)
	{
		DispatchTraitEvent(Player, ETreadM2Trigger::BattleStart, TEXT("BattleStart"));
	}
	RefreshProjectedIncomes();
	RefreshScoutSnapshots();
	SnapshotBattlePactStates();
	MatchState.ScriptedOpponentId.Reset();
	MatchState.ScriptedOpponentName.Reset();
	MatchState.ScriptedOpponentUnits.Reset();
	ActiveScriptedDef = ScriptedOpponentForRound();
	if (ActiveScriptedDef)
	{
		// Campaign R1-R2 / R12: every living player fights the scripted opponent instead of another player.
		BuildScriptedOpponent(*ActiveScriptedDef);
		MatchState.LastBattleResult.Pairings.Reset();
		for (const FTreadM1PlayerState& Player : MatchState.Players)
		{
			if (Player.bIsEliminated) continue;
			FTreadM1BattlePairing Pairing;
			Pairing.PlayerId = Player.PlayerId;
			Pairing.OpponentId = ScriptedState.PlayerId;
			MatchState.LastBattleResult.Pairings.Add(Pairing);
		}
		MatchState.PhaseTimeRemainingSec = ActiveScriptedDef->TimeoutSec;
	}
	else
	{
		BuildPairings();
		MatchState.PhaseTimeRemainingSec = 45.0f;
	}
	SetPhase(ETreadM1Phase::Battle);
	return Accept(RequestId);
}

int32 ATreadM1MatchController::BoardStrength(const FTreadM1PlayerState& Player) const
{
	int32 Strength = Player.Level * 2 + Player.PopulationUsed;
	for (const FTreadM1UnitInstance& Unit : Player.BoardUnits)
	{
		Strength += Unit.Cost * Unit.UnitStar;
	}
	return Strength;
}

void ATreadM1MatchController::BuildPairings()
{
	MatchState.LastBattleResult.Pairings.Reset();
	TArray<FString> ActiveIds;
	for (const FTreadM1PlayerState& Player : MatchState.Players)
	{
		if (!Player.bIsEliminated)
		{
			ActiveIds.Add(Player.PlayerId);
		}
	}
	for (int32 Index = ActiveIds.Num() - 1; Index > 0; --Index)
	{
		ActiveIds.Swap(Index, RandomStream.RandRange(0, Index));
	}
	SyncRandomState();
	for (int32 Index = 0; Index + 1 < ActiveIds.Num(); Index += 2)
	{
		FTreadM1BattlePairing Pairing;
		Pairing.PlayerId = ActiveIds[Index];
		Pairing.OpponentId = ActiveIds[Index + 1];
		MatchState.LastBattleResult.Pairings.Add(Pairing);
	}
}

FTreadM1CommandResult ATreadM1MatchController::ResolveBattle(const FString& RequestId)
{
	FTreadM1CommandResult CachedResult;
	if (TryGetProcessedRequest(RequestId, CachedResult))
	{
		return CachedResult;
	}

	if (MatchState.Phase != ETreadM1Phase::Battle)
	{
		return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
	}
	if (bBattleHeld)
	{
		// Already resolved for the presentation: an explicit resolve just ends the replay.
		FinishHeldBattle();
		return Accept(RequestId);
	}
	// Pairings were fixed at deployment, including the existing odd-player bye.
	ResetBattleTraitState();
	ResetBattleMeters();
	MatchState.LastBattleResult.Outcomes.Reset();
	MatchState.LastBattleResult.EliminatedPlayerIds.Reset();
	for (const FTreadM1BattlePairing& Pairing : MatchState.LastBattleResult.Pairings)
	{
		FTreadM1PlayerState* Left = FindPlayer(Pairing.PlayerId);
		FTreadM1PlayerState* Right = FindPlayer(Pairing.OpponentId);
		const bool bScripted = !Right && ActiveScriptedDef && Pairing.OpponentId == ScriptedState.PlayerId;
		if (bScripted) Right = &ScriptedState;
		if (!Left || !Right)
		{
			continue;
		}
		const int32 LeftBefore = Left->Health;
		const int32 RightBefore = Right->Health;
		FTreadM2BattleSide LeftSide;
		FTreadM2BattleSide RightSide;
		BuildBattleSide(LeftSide, *Left);
		BuildBattleSide(RightSide, *Right);
		// document/171: 炎 summons join the battle here (they never exist outside it).
		BattleSummonSerial = 0;
		ApplyYanSummon(*Left, LeftSide.Health, LeftSide.Combat);
		ApplyYanSummon(*Right, RightSide.Health, RightSide.Combat);
		// document/174: 阿戈尔 devour the unit one cell in front of them before the first exchange.
		ApplyAgirDevour(*Left, LeftSide.Health, LeftSide.Combat);
		ApplyAgirDevour(*Right, RightSide.Health, RightSide.Combat);
		SyncBattleSide(LeftSide);
		SyncBattleSide(RightSide);
		// HUD bars start full for both sides; the battle drains them as units take damage (document/168).
		BattleUnitHealth.Reset();
		for (int32 Index = 0; Index < Left->BoardUnits.Num(); ++Index)
		{
			BattleUnitHealth.Add(Left->BoardUnits[Index].UnitInstanceId, 1.0f);
		}
		for (int32 Index = 0; Index < Right->BoardUnits.Num(); ++Index)
		{
			BattleUnitHealth.Add(Right->BoardUnits[Index].UnitInstanceId, 1.0f);
		}
		// document/175: opening item procs (initial SP, first-lethal-hit windows).
		ApplyBattleStartProcs(LeftSide);
		ApplyBattleStartProcs(RightSide);
		for (int32 Exchange = 0; Exchange < 64 && LeftSide.Alive > 0 && RightSide.Alive > 0; ++Exchange)
		{
			// One exchange is one battle second: the SP trickle and the HUD bars advance here (document/168).
			BattleExchangeIndex = Exchange;
			HandleBattleExchange(1.0f);
			TickBattleSideProcs(LeftSide, Exchange);
			TickBattleSideProcs(RightSide, Exchange);
			if (LeftSide.Alive <= 0 || RightSide.Alive <= 0) break;
			RunBattleExchange(LeftSide, RightSide, Exchange);
			if (LeftSide.Alive <= 0 || RightSide.Alive <= 0) break;
			RunBattleExchange(RightSide, LeftSide, Exchange);
		}
		const int32 LeftAlive = LeftSide.Alive;
		const int32 RightAlive = RightSide.Alive;
		if (bScripted)
		{
			// LeaderRounds.json settlement: the player loses base health per surviving opponent unit, or a win
			// pays funds and (leaders) takes the leader's shared health down per surviving player unit.
			const FTreadM4ScriptedOpponent& Def = *ActiveScriptedDef;
			const bool bPlayerWins = RightAlive == 0 || (LeftAlive > 0 && BoardStrength(*Left) + LeftAlive * 2 >= BoardStrength(ScriptedState) + RightAlive * 2);
			FTreadM1BattleOutcome Outcome;
			Outcome.PlayerId = Left->PlayerId;
			Outcome.Outcome = bPlayerWins ? TEXT("Win") : TEXT("Lose");
			Outcome.SurvivingUnitCount = LeftAlive;
			Outcome.HealthBefore = LeftBefore;
			Outcome.RankBefore = Left->Rank;
			if (bPlayerWins)
			{
				Left->PendingTraitIncome += Def.WinFunds;
				const int32 LeaderDamage = Def.WinDamageBase + Def.WinDamagePerSurvivor * LeftAlive;
				MatchState.ScriptedOpponentHealth = FMath::Max(0, MatchState.ScriptedOpponentHealth - LeaderDamage);
				RecordBattleEvent(ETreadM1BattleEventType::UnitDamaged, Left->PlayerId, ScriptedState.PlayerId, LeaderDamage);
				Left->WinStreak++;
				Left->LossStreak = 0;
			}
			else
			{
				const int32 Damage = ApplyDamageTaken(*Left, Def.LossBase + Def.LossPerSurvivor * RightAlive);
				Left->Health = FMath::Max(0, Left->Health - Damage);
				RecordBattleEvent(ETreadM1BattleEventType::UnitDamaged, ScriptedState.PlayerId, Left->PlayerId, Damage);
				if (Left->Health == 0)
				{
					Left->bIsEliminated = true;
					ReturnPlayerPoolAssets(*Left);
					MatchState.LastBattleResult.EliminatedPlayerIds.Add(Left->PlayerId);
				}
				Left->LossStreak++;
				Left->WinStreak = 0;
			}
			Outcome.HealthAfter = Left->Health;
			Outcome.RankAfter = Left->Rank;
			MatchState.LastBattleResult.Outcomes.Add(Outcome);
			continue;
		}
		const int32 LeftPower = BoardStrength(*Left) + LeftAlive * 2 + RandomStream.RandRange(0, 2);
		const int32 RightPower = BoardStrength(*Right) + RightAlive * 2 + RandomStream.RandRange(0, 2);
		FTreadM1PlayerState* Winner = LeftPower >= RightPower ? Left : Right;
		FTreadM1PlayerState* Loser = Winner == Left ? Right : Left;
		const int32 Damage = ApplyDamageTaken(*Loser, FMath::Max(1, 2 + FMath::Abs(LeftPower - RightPower) + (MatchState.RoundIndex / 3)));
		Loser->Health = FMath::Max(0, Loser->Health - Damage);
		if (Loser->Health == 0)
		{
			Loser->bIsEliminated = true;
			ReturnPlayerPoolAssets(*Loser);
			MatchState.LastBattleResult.EliminatedPlayerIds.Add(Loser->PlayerId);
		}
		Winner->WinStreak++;
		Winner->LossStreak = 0;
		Loser->LossStreak++;
		Loser->WinStreak = 0;
		FTreadM1BattleOutcome WinnerOutcome;
		WinnerOutcome.PlayerId = Winner->PlayerId;
		WinnerOutcome.Outcome = TEXT("Win");
		WinnerOutcome.SurvivingUnitCount = Winner == Left ? LeftAlive : RightAlive;
		WinnerOutcome.HealthBefore = Winner == Left ? LeftBefore : RightBefore;
		WinnerOutcome.HealthAfter = Winner->Health;
		WinnerOutcome.RankBefore = Winner->Rank;
		WinnerOutcome.RankAfter = Winner->Rank;
		MatchState.LastBattleResult.Outcomes.Add(WinnerOutcome);
		FTreadM1BattleOutcome LoserOutcome;
		LoserOutcome.PlayerId = Loser->PlayerId;
		LoserOutcome.Outcome = TEXT("Lose");
		LoserOutcome.SurvivingUnitCount = Winner == Left ? RightAlive : LeftAlive;
		LoserOutcome.HealthBefore = Loser == Left ? LeftBefore : RightBefore;
		LoserOutcome.HealthAfter = Loser->Health;
		LoserOutcome.RankBefore = Loser->Rank;
		LoserOutcome.RankAfter = Loser->Rank;
		MatchState.LastBattleResult.Outcomes.Add(LoserOutcome);
		RecordBattleEvent(ETreadM1BattleEventType::UnitDamaged, Winner->PlayerId, Loser->PlayerId, Damage);
	}
	// document/178: 5_08 replaces its holder with a random higher-tier operator after the battle.
	ApplyPostBattleItemTransforms();
	SyncRandomState();
	for (FTreadM1PlayerState& Player : MatchState.Players)
	{
		DispatchTraitEvent(Player, ETreadM2Trigger::BattleEnd, TEXT("BattleEnd"));
	}
	ResetBattleTraitState();
	RankPlayers();
	for (FTreadM1BattleOutcome& Outcome : MatchState.LastBattleResult.Outcomes)
	{
		if (const FTreadM1PlayerState* Player = FindPlayer(Outcome.PlayerId))
		{
			Outcome.RankAfter = Player->Rank;
		}
	}
	if (bHoldSettlement)
	{
		bBattleHeld = true;
		MatchState.bBattleAwaitingPresentation = true;
		OnStateChanged.Broadcast();
		return Accept(RequestId);
	}
	SetPhase(ETreadM1Phase::Settlement);
	MatchState.PhaseTimeRemainingSec = 0.0f;
	// Publish a complete result to the modal: timer-driven battles must award
	// income too, and a later explicit settlement cannot award it twice.
	SettleRound(FString());
	return Accept(RequestId);
}

void ATreadM1MatchController::FinishHeldBattle()
{
	if (!bBattleHeld) return;
	bBattleHeld = false;
	MatchState.bBattleAwaitingPresentation = false;
	SetPhase(ETreadM1Phase::Settlement);
	MatchState.PhaseTimeRemainingSec = 0.0f;
	SettleRound(FString());
}

void ATreadM1MatchController::NotifyBattlePresentationFinished()
{
	if (bBattleHeld && MatchState.Phase == ETreadM1Phase::Battle) FinishHeldBattle();
}

FTreadM1CommandResult ATreadM1MatchController::SettleRound(const FString& RequestId)
{
	FTreadM1CommandResult CachedResult;
	if (TryGetProcessedRequest(RequestId, CachedResult))
	{
		return CachedResult;
	}

	if (MatchState.Phase != ETreadM1Phase::Settlement)
	{
		return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
	}
	if (LastSettledRoundIndex == MatchState.RoundIndex)
	{
		return Accept(RequestId);
	}
	if (MatchState.LastBattleResult.RoundIndex != MatchState.RoundIndex || MatchState.RoundIndex <= 0)
	{
		return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
	}
	LastSettledRoundIndex = MatchState.RoundIndex;
	MatchState.LastBattleResult.IncomeBreakdown = FTreadM1IncomeBreakdown();
	for (FTreadM1PlayerState& Player : MatchState.Players)
	{
		if (Player.bIsEliminated)
		{
			continue;
		}
		const FTreadM1IncomeBreakdown IncomeBreakdown = CalculateIncome(Player);
		const int32 Income = IncomeBreakdown.Base + IncomeBreakdown.Interest + IncomeBreakdown.Streak + IncomeBreakdown.Other;
		if (HasN1Economy() && PactData->Economy.bLeftoverFundsLost && !Player.Flags.Contains(TEXT("flag:CarryOverFunds")))
		{
			Player.Funds = 0;
		}
		Player.Funds += Income;
		// Trait/pact funds promised during the round are paid exactly once, here, as IncomeBreakdown.Other.
		Player.LastSettlementIncome = IncomeBreakdown;
		// M4 items such as 精打细算玩偶 pay every settlement; the next promise starts from them.
		Player.PendingTraitIncome = EachRoundFundsBonus(Player);
		DispatchTraitEvent(Player, ETreadM2Trigger::Settlement, TEXT("Settlement"));
		if (!HasN1Economy()) ApplyExperience(Player, 2);
		// document/176: an unclaimed reward offer expires with the round.
		if (HasN1Economy() && PactData->Economy.bRewardExpiresAtRoundEnd)
		{
			Player.RewardOffer.Reset();
			Player.bRewardClaimed = false;
		}
		if (Player.bIsHuman)
		{
			MatchState.LastBattleResult.IncomeBreakdown = IncomeBreakdown;
		}
	}
	RankPlayers();
	RefreshProjectedIncomes();
	RefreshScoutSnapshots();
	OnStateChanged.Broadcast();
	return Accept(RequestId);
}

FTreadM1CommandResult ATreadM1MatchController::AdvanceToNextRound(const FString& RequestId)
{
	FTreadM1CommandResult CachedResult;
	if (TryGetProcessedRequest(RequestId, CachedResult))
	{
		return CachedResult;
	}

	if (MatchState.Phase != ETreadM1Phase::Settlement)
	{
		return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
	}
	return BeginPreparation(RequestId);
}

FTreadM1CommandResult ATreadM1MatchController::RunRound(const FString& RequestId)
{
	FTreadM1CommandResult CachedResult;
	if (TryGetProcessedRequest(RequestId, CachedResult))
	{
		return CachedResult;
	}
	if (MatchState.Phase == ETreadM1Phase::GameOver || MatchState.Phase == ETreadM1Phase::MainMenu)
	{
		return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
	}

	// Cache only the completed composite result under the caller's key.
	const auto ChildRequestId = [&RequestId](const FString& Suffix)
	{
		return RequestId.IsEmpty() ? FString() : RequestId + TEXT(":") + Suffix;
	};
	FTreadM1CommandResult Result;
	if (MatchState.Phase == ETreadM1Phase::Settlement)
	{
		Result = AdvanceToNextRound(ChildRequestId(TEXT("advance")));
		if (!Result.bAccepted) return Reject(Result.ReasonCode, RequestId);
		if (MatchState.Phase == ETreadM1Phase::GameOver) return Accept(RequestId);
	}
	if (MatchState.Phase == ETreadM1Phase::R0Briefing)
	{
		Result = BeginPreMatchBP(ChildRequestId(TEXT("bp")));
		if (!Result.bAccepted) return Reject(Result.ReasonCode, RequestId);
	}
	if (MatchState.Phase == ETreadM1Phase::PreMatchBP)
	{
		if (MatchState.BP.PlayerStrategyId.IsEmpty())
		{
			if (MatchState.BP.AvailableStrategyIds.IsEmpty())
			{
				return Reject(ETreadM1RejectReason::StrategyUnavailable, RequestId);
			}
			Result = ChoosePlayerStrategy(MatchState.BP.AvailableStrategyIds[0], ChildRequestId(TEXT("player")));
			if (!Result.bAccepted) return Reject(Result.ReasonCode, RequestId);
		}
		for (int32 Pick = 0; Pick < MatchState.BP.AiPickStates.Num() &&
			MatchState.BP.AiPickStates.Contains(ETreadM1AIPickState::Waiting); ++Pick)
		{
			Result = RunNextAIPick(ChildRequestId(FString::Printf(TEXT("ai-%d"), Pick)));
			if (!Result.bAccepted) return Reject(Result.ReasonCode, RequestId);
		}
		Result = ConfirmPreMatchBP(ChildRequestId(TEXT("confirm")));
		if (!Result.bAccepted) return Reject(Result.ReasonCode, RequestId);
	}
	if (MatchState.Phase == ETreadM1Phase::Preparation)
	{
		Result = DeployAndStartBattle(ChildRequestId(TEXT("deploy")));
		if (!Result.bAccepted) return Reject(Result.ReasonCode, RequestId);
	}
	if (MatchState.Phase == ETreadM1Phase::Battle)
	{
		Result = ResolveBattle(ChildRequestId(TEXT("resolve")));
		if (!Result.bAccepted) return Reject(Result.ReasonCode, RequestId);
	}
	Result = SettleRound(ChildRequestId(TEXT("settle")));
	return Result.bAccepted ? Accept(RequestId) : Reject(Result.ReasonCode, RequestId);
}

FTreadM1CommandResult ATreadM1MatchController::MoveUnitToBoard(const FString& PlayerId,
	const FString& UnitInstanceId, FIntPoint BoardCell, const FString& RequestId)
{
	FTreadM1CommandResult CachedResult;
	if (TryGetProcessedRequest(RequestId, CachedResult))
	{
		return CachedResult;
	}

	if (MatchState.Phase != ETreadM1Phase::Preparation)
	{
		return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
	}
	if (BoardCell.X < 0 || BoardCell.X > 7 || BoardCell.Y < 0 || BoardCell.Y > 7)
	{
		return Reject(ETreadM1RejectReason::InvalidBoardCell, RequestId);
	}
	FTreadM1PlayerState* Player = FindPlayer(PlayerId);
	if (!Player || Player->bIsEliminated)
	{
		return Reject(ETreadM1RejectReason::PlayerEliminated, RequestId);
	}
	for (const FTreadM1UnitInstance& Existing : Player->BoardUnits)
	{
		if (Existing.BoardCell == BoardCell && Existing.UnitInstanceId != UnitInstanceId)
		{
			return Reject(ETreadM1RejectReason::InvalidBoardCell, RequestId);
		}
	}
	// A board unit may be repositioned during Preparation.  Swapping with an
	// occupied cell remains an explicit SwapBoardUnits command so callers can
	// distinguish Move versus Swap in their drag preview.
	for (FTreadM1UnitInstance& Existing : Player->BoardUnits)
	{
		if (Existing.UnitInstanceId == UnitInstanceId)
		{
			Existing.BoardCell = BoardCell;
			RefreshScoutSnapshots();
			OnStateChanged.Broadcast();
			return Accept(RequestId);
		}
	}
	for (int32 Index = 0; Index < Player->BenchUnits.Num(); ++Index)
	{
		if (Player->BenchUnits[Index].UnitInstanceId == UnitInstanceId)
		{
			if (!Player->BenchUnits[Index].bIsTransformClone && Player->PopulationUsed >= Player->PopulationLimit)
			{
				return Reject(ETreadM1RejectReason::PopulationLimitReached, RequestId);
			}
			FTreadM1UnitInstance Unit = Player->BenchUnits[Index];
			Player->BenchUnits.RemoveAt(Index);
			Unit.Location = ETreadM1UnitLocation::Board;
			Unit.BoardCell = BoardCell;
			Player->BoardUnits.Add(Unit);
			if (!Unit.bIsTransformClone) ++Player->PopulationUsed;
			// UnitInstanceId may alias the removed bench element (fixture callers pass
			// BenchUnits.Last().UnitInstanceId by const ref), so only the copy is safe here.
			const int32 BenchSlot = Player->BenchUnitInstanceIds.Find(Unit.UnitInstanceId);
			if (BenchSlot != INDEX_NONE)
			{
				Player->BenchUnitInstanceIds[BenchSlot].Empty();
			}
			RecomputePacts(*Player);
			DispatchTraitEvent(*Player, ETreadM2Trigger::Deploy, TEXT("MoveToBoard"), &Unit);
			RefreshScoutSnapshots();
			OnStateChanged.Broadcast();
			return Accept(RequestId);
		}
	}
	return Reject(ETreadM1RejectReason::NotOwnUnit, RequestId);
}

FTreadM1CommandResult ATreadM1MatchController::MoveUnitToBench(const FString& PlayerId,
	const FString& UnitInstanceId, const FString& RequestId)
{
	FTreadM1CommandResult CachedResult;
	if (TryGetProcessedRequest(RequestId, CachedResult))
	{
		return CachedResult;
	}

	if (MatchState.Phase != ETreadM1Phase::Preparation)
	{
		return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
	}
	FTreadM1PlayerState* Player = FindPlayer(PlayerId);
	if (!Player || Player->bIsEliminated)
	{
		return Reject(ETreadM1RejectReason::PlayerEliminated, RequestId);
	}
	if (Player->BenchUnits.Num() >= MatchState.Rules.MaxBenchSlots)
	{
		return Reject(ETreadM1RejectReason::BenchFull, RequestId);
	}
	for (int32 Index = 0; Index < Player->BoardUnits.Num(); ++Index)
	{
		if (Player->BoardUnits[Index].UnitInstanceId == UnitInstanceId)
		{
			FTreadM1UnitInstance Unit = Player->BoardUnits[Index];
			Player->BoardUnits.RemoveAt(Index);
			Unit.Location = ETreadM1UnitLocation::Bench;
			Unit.BoardCell = FIntPoint(-1, -1);
			Player->BenchUnits.Add(Unit);
			if (!Unit.bIsTransformClone) Player->PopulationUsed = FMath::Max(0, Player->PopulationUsed - 1);
			const int32 EmptyIndex = Player->BenchUnitInstanceIds.Find(FString());
			// Same aliasing hazard as MoveUnitToBoard: UnitInstanceId may point into the
			// board array that RemoveAt just destroyed, so assign from the copy.
			if (EmptyIndex != INDEX_NONE)
			{
				Player->BenchUnitInstanceIds[EmptyIndex] = Unit.UnitInstanceId;
			}
			else
			{
				Player->BenchUnitInstanceIds.Add(Unit.UnitInstanceId);
			}
			RecomputePacts(*Player);
			DispatchTraitEvent(*Player, ETreadM2Trigger::Undeploy, TEXT("MoveToBench"), &Unit);
			RefreshScoutSnapshots();
			OnStateChanged.Broadcast();
			return Accept(RequestId);
		}
	}
	return Reject(ETreadM1RejectReason::NotOwnUnit, RequestId);
}

FTreadM1CommandResult ATreadM1MatchController::SwapBoardUnits(const FString& PlayerId,
	const FString& FirstUnitInstanceId, const FString& SecondUnitInstanceId, const FString& RequestId)
{
	FTreadM1CommandResult CachedResult;
	if (TryGetProcessedRequest(RequestId, CachedResult))
	{
		return CachedResult;
	}

	if (MatchState.Phase != ETreadM1Phase::Preparation)
	{
		return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
	}
	FTreadM1PlayerState* Player = FindPlayer(PlayerId);
	if (!Player || Player->bIsEliminated)
	{
		return Reject(ETreadM1RejectReason::PlayerEliminated, RequestId);
	}
	int32 FirstIndex = INDEX_NONE;
	int32 SecondIndex = INDEX_NONE;
	for (int32 Index = 0; Index < Player->BoardUnits.Num(); ++Index)
	{
		if (Player->BoardUnits[Index].UnitInstanceId == FirstUnitInstanceId) FirstIndex = Index;
		if (Player->BoardUnits[Index].UnitInstanceId == SecondUnitInstanceId) SecondIndex = Index;
	}
	if (FirstIndex == INDEX_NONE || SecondIndex == INDEX_NONE || FirstIndex == SecondIndex)
	{
		return Reject(ETreadM1RejectReason::NotOwnUnit, RequestId);
	}
	Swap(Player->BoardUnits[FirstIndex].BoardCell, Player->BoardUnits[SecondIndex].BoardCell);
	RefreshScoutSnapshots();
	OnStateChanged.Broadcast();
	return Accept(RequestId);
}

void ATreadM1MatchController::RefreshScoutSnapshots()
{
	// Pact counts follow every roster mutation; the snapshot then mirrors them read-only.
	RecomputeAllPacts();
	MatchState.ScoutSnapshots.Reset();
	for (const FTreadM1PlayerState& Player : MatchState.Players)
	{
		FTreadM1ScoutSnapshot Snapshot;
		Snapshot.PlayerId = Player.PlayerId;
		Snapshot.DisplayName = Player.DisplayName;
		Snapshot.Rank = Player.Rank;
		Snapshot.Health = Player.Health;
		Snapshot.Funds = Player.Funds;
		Snapshot.Level = Player.Level;
		Snapshot.PopulationUsed = Player.PopulationUsed;
		Snapshot.PopulationLimit = Player.PopulationLimit;
		Snapshot.NextRoundIncome = Player.NextRoundIncome;
		Snapshot.BoardUnits = Player.BoardUnits;
		Snapshot.BenchUnitInstanceIds = Player.BenchUnitInstanceIds;
		Snapshot.BenchUnits = Player.BenchUnits;
		Snapshot.EquipmentIds = Player.EquipmentIds;
		Snapshot.ActivePactIds = Player.ActivePactIds;
		Snapshot.Pacts = Player.Pacts;
		for (const FTreadM2PactProgress& Progress : Player.Pacts)
		{
			if (Progress.Stacks <= 0) continue;
			FTreadM1PactStack& Stack = Snapshot.PactStacks.AddDefaulted_GetRef();
			Stack.PactId = Progress.PactId;
			Stack.StackCount = Progress.Stacks;
		}
		Snapshot.bReadOnly = true;
		MatchState.ScoutSnapshots.Add(MoveTemp(Snapshot));
	}
}

bool ATreadM1MatchController::CanScout() const
{
	return MatchState.Phase == ETreadM1Phase::Preparation || MatchState.Phase == ETreadM1Phase::PreMatchBP || MatchState.Phase == ETreadM1Phase::R0Briefing;
}

FTreadM1ScoutSnapshot ATreadM1MatchController::GetScoutSnapshot(const FString& PlayerId) const
{
	for (const FTreadM1ScoutSnapshot& Snapshot : MatchState.ScoutSnapshots)
	{
		if (Snapshot.PlayerId == PlayerId)
		{
			return CanScout() ? Snapshot : FTreadM1ScoutSnapshot();
		}
	}
	return FTreadM1ScoutSnapshot();
}

void ATreadM1MatchController::RecordBattleEvent(ETreadM1BattleEventType EventType, const FString& SourcePlayerId, const FString& TargetPlayerId, int32 Amount, const FString& SourceUnitId, const FString& TargetUnitId, int32 TargetHealthAfterOverride)
{
	FTreadM1BattleEvent Event;
	Event.EventId = FString::Printf(TEXT("battle_%04d"), ++BattleEventSequence);
	Event.Sequence = BattleEventSequence;
	Event.RoundIndex = MatchState.RoundIndex;
	Event.EventType = EventType;
	Event.SourcePlayerId = SourcePlayerId;
	Event.TargetPlayerId = TargetPlayerId;
	Event.SourceUnitInstanceId = SourceUnitId;
	Event.TargetUnitInstanceId = TargetUnitId;
	Event.Amount = Amount;
	if (TargetHealthAfterOverride != INDEX_NONE)
	{
		Event.TargetHealthAfter = TargetHealthAfterOverride;
	}
	else if (const FTreadM1PlayerState* Target = FindPlayer(TargetPlayerId))
	{
		Event.TargetHealthAfter = Target->Health;
	}
	if (EventType == ETreadM1BattleEventType::UnitTargetChanged)
	{
		Event.NewTargetUnitInstanceId = TargetUnitId;
	}
	Event.TimeSec = static_cast<float>(Event.Sequence) * 0.1f;
	MatchState.BattleEvents.Add(MoveTemp(Event));
}

FTreadM1PlayerState* ATreadM1MatchController::FindPlayer(const FString& PlayerId)
{
	return MatchState.Players.FindByPredicate([&PlayerId](FTreadM1PlayerState& Player) { return Player.PlayerId == PlayerId; });
}

const FTreadM1PlayerState* ATreadM1MatchController::FindPlayer(const FString& PlayerId) const
{
	return MatchState.Players.FindByPredicate([&PlayerId](const FTreadM1PlayerState& Player) { return Player.PlayerId == PlayerId; });
}

FTreadM1StrategyState* ATreadM1MatchController::FindStrategy(const FString& StrategyId)
{
	return MatchState.Strategies.FindByPredicate([&StrategyId](FTreadM1StrategyState& Strategy) { return Strategy.StrategyId == StrategyId; });
}

bool ATreadM1MatchController::IsAvailableStrategy(const FString& StrategyId) const
{
	return MatchState.BP.AvailableStrategyIds.Contains(StrategyId);
}

int32 ATreadM1MatchController::LivingPlayerCount() const
{
	int32 Count = 0;
	for (const FTreadM1PlayerState& Player : MatchState.Players)
	{
		Count += Player.bIsEliminated ? 0 : 1;
	}
	return Count;
}

void ATreadM1MatchController::RankPlayers()
{
	TArray<int32> Indices;
	for (int32 Index = 0; Index < MatchState.Players.Num(); ++Index)
	{
		Indices.Add(Index);
	}
	Indices.Sort([this](int32 A, int32 B)
	{
		const FTreadM1PlayerState& Left = MatchState.Players[A];
		const FTreadM1PlayerState& Right = MatchState.Players[B];
		if (Left.bIsEliminated != Right.bIsEliminated)
		{
			return !Left.bIsEliminated;
		}
		if (Left.Health != Right.Health)
		{
			return Left.Health > Right.Health;
		}
		return Left.PlayerId < Right.PlayerId;
	});
	for (int32 RankIndex = 0; RankIndex < Indices.Num(); ++RankIndex)
	{
		MatchState.Players[Indices[RankIndex]].Rank = RankIndex + 1;
	}
}

FString ATreadM1MatchController::PhaseName(ETreadM1Phase Phase) const
{
	const UEnum* Enum = StaticEnum<ETreadM1Phase>();
	return Enum ? Enum->GetNameStringByValue(static_cast<int64>(Phase)) : TEXT("Unknown");
}

FString ATreadM1MatchController::RoundTypeName(ETreadM1RoundType RoundType) const
{
	const UEnum* Enum = StaticEnum<ETreadM1RoundType>();
	return Enum ? Enum->GetNameStringByValue(static_cast<int64>(RoundType)) : TEXT("Unknown");
}

bool ATreadM1MatchController::WriteSelfTestReport(const FString& Path, const TArray<FString>& PhaseTrace,
	const TArray<bool>& StepResults, bool bSameSeedReplayEqual, uint32 ReplaySignature,
	const TArray<int32>& AcceptedRounds, const TArray<FString>& AcceptedRoundTypes,
	const TMap<FString, bool>& NamedChecks) const
{
	TSharedPtr<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetStringField(TEXT("schema"), TEXT("Tread.M1.MatchSelfTest.v2"));
	Root->SetStringField(TEXT("producer"), TEXT("Tread C++ RunDeterministicSelfTest"));
	Root->SetStringField(TEXT("acceptanceFixture"), TEXT("1000 HP per participant set once after BP; no resurrection or per-round HP reset"));
	Root->SetBoolField(TEXT("ok"), !StepResults.Contains(false) && bSameSeedReplayEqual);
	Root->SetBoolField(TEXT("sameSeedReplayEqual"), bSameSeedReplayEqual);
	Root->SetStringField(TEXT("replaySignatureCrc32"), FString::Printf(TEXT("%08x"), ReplaySignature));
	Root->SetStringField(TEXT("matchId"), MatchState.MatchId);
	Root->SetNumberField(TEXT("seed"), static_cast<double>(MatchState.Seed));
	Root->SetStringField(TEXT("randomStreamAlgorithm"), MatchState.RandomStreamAlgorithm);
	Root->SetNumberField(TEXT("randomStreamState"), MatchState.RandomStreamState);
	Root->SetNumberField(TEXT("players"), MatchState.Players.Num());
	Root->SetNumberField(TEXT("roundsCompleted"), LastSettledRoundIndex);
	Root->SetNumberField(TEXT("roundIndex"), MatchState.RoundIndex);
	Root->SetNumberField(TEXT("pairings"), MatchState.LastBattleResult.Pairings.Num());
	Root->SetNumberField(TEXT("battleEvents"), MatchState.BattleEvents.Num());
	Root->SetNumberField(TEXT("scoutSnapshots"), MatchState.ScoutSnapshots.Num());
	Root->SetNumberField(TEXT("processedRequestCount"), ProcessedRequests.Num());
	Root->SetBoolField(TEXT("requestIdempotency"), NamedChecks.FindRef(TEXT("requestIdempotency")));
	TSharedPtr<FJsonObject> Named = MakeShared<FJsonObject>();
	for (const TPair<FString, bool>& Check : NamedChecks) Named->SetBoolField(Check.Key, Check.Value);
	Root->SetObjectField(TEXT("namedChecks"), Named);
	Root->SetBoolField(TEXT("gameOver"), MatchState.Phase == ETreadM1Phase::GameOver);
	TArray<TSharedPtr<FJsonValue>> RoundValues;
	for (const int32 Round : AcceptedRounds)
	{
		RoundValues.Add(MakeShared<FJsonValueNumber>(static_cast<double>(Round)));
	}
	Root->SetArrayField(TEXT("acceptedRounds"), RoundValues);
	TArray<TSharedPtr<FJsonValue>> RoundTypes;
	for (const FString& Type : AcceptedRoundTypes) RoundTypes.Add(MakeShared<FJsonValueString>(Type));
	Root->SetArrayField(TEXT("acceptedRoundTypes"), RoundTypes);
	TSharedPtr<FJsonObject> BP = MakeShared<FJsonObject>();
	const auto StringValues = [](const TArray<FString>& Values)
	{
		TArray<TSharedPtr<FJsonValue>> Result;
		for (const FString& Value : Values) Result.Add(MakeShared<FJsonValueString>(Value));
		return Result;
	};
	BP->SetArrayField(TEXT("banned"), StringValues(MatchState.BP.BannedStrategyIds));
	BP->SetArrayField(TEXT("available"), StringValues(MatchState.BP.AvailableStrategyIds));
	TArray<FString> Chosen = {MatchState.BP.PlayerStrategyId};
	Chosen.Append(MatchState.BP.AiStrategyIds);
	BP->SetArrayField(TEXT("chosen"), StringValues(Chosen));
	Root->SetObjectField(TEXT("bp"), BP);
	TArray<TSharedPtr<FJsonValue>> EventTypes;
	TSet<FString> SeenEventTypes;
	for (const FTreadM1BattleEvent& Event : MatchState.BattleEvents)
	{
		const UEnum* EventEnum = StaticEnum<ETreadM1BattleEventType>();
		const FString Name = EventEnum ? EventEnum->GetNameStringByValue(static_cast<int64>(Event.EventType)) : TEXT("Unknown");
		if (!SeenEventTypes.Contains(Name))
		{
			SeenEventTypes.Add(Name);
			EventTypes.Add(MakeShared<FJsonValueString>(Name));
		}
	}
	Root->SetArrayField(TEXT("eventTypes"), EventTypes);
	TArray<TSharedPtr<FJsonValue>> RosterCounts;
	for (const FTreadM1PlayerState& Player : MatchState.Players)
	{
		TSharedPtr<FJsonObject> Roster = MakeShared<FJsonObject>();
		Roster->SetStringField(TEXT("playerId"), Player.PlayerId);
		Roster->SetNumberField(TEXT("board"), Player.BoardUnits.Num());
		Roster->SetNumberField(TEXT("bench"), Player.BenchUnits.Num());
		Roster->SetBoolField(TEXT("eliminated"), Player.bIsEliminated);
		RosterCounts.Add(MakeShared<FJsonValueObject>(Roster));
	}
	Root->SetArrayField(TEXT("rosters"), RosterCounts);
	TArray<TSharedPtr<FJsonValue>> Trace;
	for (const FString& Phase : PhaseTrace)
	{
		Trace.Add(MakeShared<FJsonValueString>(Phase));
	}
	Root->SetArrayField(TEXT("phaseTrace"), Trace);
	TArray<TSharedPtr<FJsonValue>> Checks;
	for (bool Passed : StepResults)
	{
		Checks.Add(MakeShared<FJsonValueBoolean>(Passed));
	}
	Root->SetArrayField(TEXT("stepResults"), Checks);
	FString Output;
	FJsonSerializer::Serialize(Root.ToSharedRef(), TJsonWriterFactory<>::Create(&Output));
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(Path), true);
	return FFileHelper::SaveStringToFile(Output + TEXT("\n"), *Path);
}

bool ATreadM1MatchController::WritePoolLedgerReport(const FString& Path) const
{
	TSharedPtr<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetStringField(TEXT("schema"), TEXT("Tread.M1.PoolLedger.Conservation.v1"));
	Root->SetBoolField(TEXT("ok"), ValidatePoolLedger());
	Root->SetNumberField(TEXT("participants"), MatchState.Players.Num());
	TSharedPtr<FJsonObject> TierTotals = MakeShared<FJsonObject>();
	for (int32 TierIndex = 0; TierIndex < UE_ARRAY_COUNT(PoolTierNames); ++TierIndex)
	{
		TierTotals->SetNumberField(PoolTierNames[TierIndex], PoolTierTotals[TierIndex]);
	}
	Root->SetObjectField(TEXT("tierTotals"), TierTotals);
	TSharedPtr<FJsonObject> Counts = MakeShared<FJsonObject>();
	Counts->SetNumberField(TEXT("balanceKeys"), MatchState.PoolLedger.Balances.Num());
	Counts->SetNumberField(TEXT("ledgerEntries"), MatchState.PoolLedger.Entries.Num());
	Counts->SetNumberField(TEXT("revision"), MatchState.PoolLedger.Revision);
	Root->SetObjectField(TEXT("ledger"), Counts);
	TArray<TSharedPtr<FJsonValue>> Checks;
	for (const TCHAR* Check : {TEXT("shared ledger for four participants"), TEXT("characterId + operatorTier balance key"),
		TEXT("tier totals I/II/III/IV/V/VI = 12/14/18/16/8/5"), TEXT("shop reserve and purchase conservation"),
		TEXT("refresh returns unsold reservations"), TEXT("sell returns owned copy"), TEXT("elimination returns shop and owned copies"),
		TEXT("clone instances do not change shared pool")})
	{
		Checks.Add(MakeShared<FJsonValueString>(Check));
	}
	Root->SetArrayField(TEXT("checks"), Checks);
	FString Output;
	FJsonSerializer::Serialize(Root.ToSharedRef(), TJsonWriterFactory<>::Create(&Output));
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(Path), true);
	return FFileHelper::SaveStringToFile(Output + TEXT("\n"), *Path);
}

bool ATreadM1MatchController::RunDeterministicSelfTest(const FString& OutputPath)
{
	const int64 Seed = MatchState.Seed > 0 ? MatchState.Seed : 20260926;
	TArray<FString> PhaseTrace;
	TArray<bool> Checks;
	TMap<FString, bool> NamedChecks;
	const auto CheckNamed = [&Checks, &NamedChecks](const FString& Name, bool bPassed)
	{
		Checks.Add(bPassed);
		const bool* Previous = NamedChecks.Find(Name);
		NamedChecks.Add(Name, bPassed && (!Previous || *Previous));
	};
	const auto StateEquals = [this](const FTreadM1MatchState& Before)
	{
		return FTreadM1MatchState::StaticStruct()->CompareScriptStruct(&Before, &MatchState, 0);
	};
	const auto RunOneReplay = [this, Seed, &Checks, &CheckNamed, &StateEquals](TArray<FString>* OutTrace,
		TArray<int32>& OutAcceptedRounds, TArray<FString>& OutRoundTypes) -> FString
	{
		InitializeMatch(Seed);
		OutAcceptedRounds.Reset();
		OutRoundTypes.Reset();
		Checks.Add(MatchState.Players.Num() == 4);
		bool bEveryRosterVisible = MatchState.ScoutSnapshots.Num() == 4;
		for (const FTreadM1PlayerState& Player : MatchState.Players)
		{
			bEveryRosterVisible &= Player.BoardUnits.Num() + Player.BenchUnits.Num() > 0;
		}
		Checks.Add(bEveryRosterVisible);
		Checks.Add(MatchState.RandomStreamAlgorithm == TEXT("UE.FRandomStream.v1"));
		// N1: shop size follows the 调度中心 level and the pool holds one balance per bound card.
		const int32 ExpectedSlots = HasN1Economy() ? PactData->Economy.SlotsForLevel(MatchState.Players[0].Level) : ShopSlots;
		const int32 ExpectedBalances = HasN1Economy() ? PactData->CardOrder.Num() : 192;
		Checks.Add(MatchState.Players.Num() == 4 && MatchState.Players[0].Shop.Slots.Num() == ExpectedSlots);
		Checks.Add(MatchState.PoolLedger.Balances.Num() == ExpectedBalances);
		Checks.Add(ValidatePoolLedger());
		int32 ReservedCopies = 0;
		bool bTierTotalsValid = true;
		for (const FTreadM1PoolBalance& Balance : MatchState.PoolLedger.Balances)
		{
			ReservedCopies += Balance.ReservedCopies;
			for (int32 TierIndex = 0; TierIndex < UE_ARRAY_COUNT(PoolTierNames); ++TierIndex)
			{
				if (!HasN1Economy() && Balance.OperatorTier == PoolTierNames[TierIndex] && Balance.PoolCopiesTotal != PoolTierTotals[TierIndex])
				{
					bTierTotalsValid = false;
				}
			}
		}
		Checks.Add(bTierTotalsValid);
		Checks.Add(ReservedCopies == 4 * ExpectedSlots);
		if (OutTrace) OutTrace->Add(PhaseName(MatchState.Phase));
		Checks.Add(BeginPreMatchBP(TEXT("selftest-r0")).bAccepted);
		if (OutTrace) OutTrace->Add(PhaseName(MatchState.Phase));
		Checks.Add(MatchState.BP.BannedStrategyIds.Num() == 4 && MatchState.BP.AvailableStrategyIds.Num() == MatchState.Strategies.Num() - 4);
		const int32 AvailableAfterBP = MatchState.BP.AvailableStrategyIds.Num();
		const FTreadM1CommandResult DuplicateBP = BeginPreMatchBP(TEXT("selftest-r0"));
		Checks.Add(DuplicateBP.bAccepted && DuplicateBP.RequestId == TEXT("selftest-r0") &&
			MatchState.BP.AvailableStrategyIds.Num() == AvailableAfterBP && MatchState.Phase == ETreadM1Phase::PreMatchBP);
		if (MatchState.BP.AvailableStrategyIds.IsEmpty())
		{
			CheckNamed(TEXT("bpSetup"), false);
			return FString(TEXT("BP setup failed"));
		}
		Checks.Add(ChoosePlayerStrategy(MatchState.BP.AvailableStrategyIds[0], TEXT("selftest-player")).bAccepted);
		int32 SelfTestAIPick = 0;
		while (SelfTestAIPick < 3 && MatchState.BP.AiPickStates.Contains(ETreadM1AIPickState::Waiting))
		{
			Checks.Add(RunNextAIPick(FString::Printf(TEXT("selftest-ai-%d"), SelfTestAIPick++)).bAccepted);
		}
		Checks.Add(ConfirmPreMatchBP(TEXT("selftest-confirm")).bAccepted);
		if (OutTrace) OutTrace->Add(PhaseName(MatchState.Phase));
		Checks.Add(MatchState.Players[0].InitialStrategyId == MatchState.BP.PlayerStrategyId);
		bool bStrategyCostsCorrect = true;
		for (const FTreadM1PlayerState& Player : MatchState.Players)
		{
			const FTreadM1StrategyState* Strategy = FindStrategy(Player.InitialStrategyId);
			bStrategyCostsCorrect &= Strategy && Player.Health == FMath::Max(0, 100 - Strategy->HpCost);
		}
		const FTreadM1MatchState AfterConfirmation = MatchState;
		CheckNamed(TEXT("initialStrategyCostOnce"), bStrategyCostsCorrect &&
			ConfirmPreMatchBP(TEXT("selftest-confirm")).bAccepted && StateEquals(AfterConfirmation));
		// A one-time durability fixture reaches every boundary without reviving
		// eliminated participants or corrupting their returned pool ownership.
		for (FTreadM1PlayerState& Player : MatchState.Players) Player.Health = 1000;
		MatchState.Players[0].Funds = 100;
		const int32 PoolRevisionBeforePurchase = MatchState.PoolLedger.Revision;
		Checks.Add(PurchaseShopSlot(TEXT("P0"), 0, TEXT("selftest-purchase")).bAccepted);
		const int32 FundsAfterPurchase = MatchState.Players[0].Funds;
		const int32 BenchAfterPurchase = MatchState.Players[0].BenchUnits.Num();
		const FTreadM1MatchState AfterPurchase = MatchState;
		const FTreadM1CommandResult DuplicatePurchase = PurchaseShopSlot(TEXT("P0"), 0, TEXT("selftest-purchase"));
		CheckNamed(TEXT("duplicatePurchase"), DuplicatePurchase.bAccepted && StateEquals(AfterPurchase) &&
			MatchState.Players[0].Funds == FundsAfterPurchase && MatchState.Players[0].BenchUnits.Num() == BenchAfterPurchase);
		CheckNamed(TEXT("requestIdempotency"), DuplicatePurchase.bAccepted && StateEquals(AfterPurchase));
		Checks.Add(MatchState.PoolLedger.Revision == PoolRevisionBeforePurchase + 1 && ValidatePoolLedger());
		Checks.Add(RefreshShop(TEXT("P0"), TEXT("selftest-refresh")).bAccepted);
		Checks.Add(ValidatePoolLedger());
		const FString PurchasedUnitId = MatchState.Players[0].BenchUnits.Num() > 0
			? MatchState.Players[0].BenchUnits[0].UnitInstanceId : FString();
		Checks.Add(!PurchasedUnitId.IsEmpty() && SellUnit(TEXT("P0"), PurchasedUnitId, TEXT("selftest-sell")).bAccepted);
		Checks.Add(ValidatePoolLedger());
		// M1-06 lifecycle: a normal owned unit can produce and destroy a clone.
		Checks.Add(PurchaseShopSlot(TEXT("P0"), 1, TEXT("selftest-clone-source")).bAccepted);
		const FString CloneSourceUnitId = MatchState.Players[0].BenchUnits.Num() > 0
			? MatchState.Players[0].BenchUnits.Last().UnitInstanceId : FString();
		const FTreadM1PoolBalance CloneBalanceBefore = GetPoolBalance(
			MatchState.Players[0].BenchUnits.Num() > 0 ? MatchState.Players[0].BenchUnits.Last().CharacterId : TEXT("char_001"),
			MatchState.Players[0].BenchUnits.Num() > 0 ? MatchState.Players[0].BenchUnits.Last().OperatorTier : TEXT("I"));
		Checks.Add(!CloneSourceUnitId.IsEmpty() && CreateTransformCloneFromUnit(TEXT("P0"), CloneSourceUnitId,
			TEXT("selftest-clone-create")).bAccepted);
		FString CloneId;
		FString CloneSourceCharacterId;
		for (const FTreadM1UnitInstance& Unit : MatchState.Players[0].BenchUnits)
		{
			if (Unit.bIsTransformClone)
			{
				CloneId = Unit.CloneInstanceId;
				CloneSourceCharacterId = Unit.CopySourceCharacterId;
				break;
			}
		}
		Checks.Add(!CloneId.IsEmpty() && !CloneSourceCharacterId.IsEmpty());
		const FTreadM1PoolBalance CloneBalanceAfterCreate = GetPoolBalance(
			CloneSourceCharacterId,
			MatchState.Players[0].BenchUnits.Num() > 0 ? MatchState.Players[0].BenchUnits.Last().OperatorTier : TEXT("I"));
		Checks.Add(CloneBalanceBefore.PoolCopiesAvailable == CloneBalanceAfterCreate.PoolCopiesAvailable &&
			CloneBalanceBefore.ReservedCopies == CloneBalanceAfterCreate.ReservedCopies &&
			CloneBalanceBefore.OwnedCopies == CloneBalanceAfterCreate.OwnedCopies && ValidatePoolLedger());
		Checks.Add(DestroyTransformClone(TEXT("P0"), CloneId, TEXT("selftest-clone-destroy")).bAccepted);
		bool bSawCloneCreate = false;
		bool bSawCloneDestroy = false;
		for (const FTreadM1PoolLedgerEntry& Entry : MatchState.PoolLedger.Entries)
		{
			bSawCloneCreate |= Entry.Action == TEXT("CloneCreate") && Entry.CloneInstanceId == CloneId &&
				Entry.CopySourceCharacterId == CloneSourceCharacterId && Entry.Delta == 0;
			bSawCloneDestroy |= Entry.Action == TEXT("CloneDestroy") && Entry.CloneInstanceId == CloneId &&
				Entry.CopySourceCharacterId == CloneSourceCharacterId && Entry.Delta == 0;
		}
		Checks.Add(bSawCloneCreate && bSawCloneDestroy && ValidatePoolLedger());
		const FString BenchUnitId = MatchState.Players[0].BenchUnits.Num() > 0
			? MatchState.Players[0].BenchUnits[0].UnitInstanceId : FString();
		Checks.Add(!BenchUnitId.IsEmpty() && MoveUnitToBoard(TEXT("P0"), BenchUnitId, FIntPoint(0, 6), TEXT("selftest-board")).bAccepted);
		Checks.Add(MoveUnitToBench(TEXT("P0"), BenchUnitId, TEXT("selftest-bench")).bAccepted);
		Checks.Add(MatchState.Players[0].BoardUnits.Num() >= 2 && SwapBoardUnits(TEXT("P0"),
			MatchState.Players[0].BoardUnits[0].UnitInstanceId,
			MatchState.Players[0].BoardUnits[1].UnitInstanceId, TEXT("selftest-swap")).bAccepted);
		const FTreadM1MatchState BeforeScout = MatchState;
		bool bScoutReadOnly = CanScout();
		for (const FTreadM1PlayerState& Player : MatchState.Players)
		{
			const FTreadM1ScoutSnapshot Scout = GetScoutSnapshot(Player.PlayerId);
			bScoutReadOnly &= Scout.bReadOnly && Scout.PlayerId == Player.PlayerId &&
				Scout.BoardUnits.Num() == Player.BoardUnits.Num() && Scout.BenchUnits.Num() == Player.BenchUnits.Num();
		}
		CheckNamed(TEXT("scoutReadOnly"), bScoutReadOnly && StateEquals(BeforeScout));
		const FTreadM1CommandResult RejectedPurchase = PurchaseShopSlot(TEXT("P0"), -1, TEXT("selftest-reject-cache"));
		CheckNamed(TEXT("rejectedCommand"), !RejectedPurchase.bAccepted &&
			RejectedPurchase.ReasonCode == ETreadM1RejectReason::ShopSlotEmpty);
		for (int32 Round = 1; Round <= MaxRounds; ++Round)
		{
			bool bPrepared = MatchState.Phase == ETreadM1Phase::Preparation && MatchState.RoundIndex == Round;
			if (Round > 1)
			{
				const FString AdvanceKey = FString::Printf(TEXT("selftest-r%d-advance"), Round);
				bPrepared = AdvanceToNextRound(AdvanceKey).bAccepted &&
					MatchState.RoundIndex == Round && MatchState.Phase == ETreadM1Phase::Preparation;
				const FTreadM1MatchState AfterAdvance = MatchState;
				CheckNamed(TEXT("requestIdempotency"), AdvanceToNextRound(AdvanceKey).bAccepted && StateEquals(AfterAdvance));
			}
			const ETreadM1RoundType ExpectedType = Round <= 2 ? ETreadM1RoundType::PvE :
				(Round < MaxRounds ? ETreadM1RoundType::PvP : ETreadM1RoundType::Leader);
			const bool bRoundType = MatchState.RoundType == ExpectedType;
			const TArray<FTreadM1PlayerState> BeforePlayers = MatchState.Players;
			const int32 EventsBefore = MatchState.BattleEvents.Num();
			bool bResolved = false;
			if (Round == 2 || Round == 3)
			{
				// Exercise the same timer keys used by live PIE on consecutive
				// rounds. Fixed keys would return cached R2 results during R3.
				AdvancePreparationTimer(MatchState.PhaseTimeRemainingSec);
				const bool bDeployed = MatchState.Phase == ETreadM1Phase::Battle && MatchState.PhaseTimeRemainingSec == 45.0f;
				const TArray<FTreadM1BattlePairing> DeployedPairings = MatchState.LastBattleResult.Pairings;
				const FTreadM1MatchState AfterDeploy = MatchState;
				const FString DeployKey = FString::Printf(TEXT("runtime:round-%d:preparation-timer"), Round);
				const bool bDuplicateDeployUnchanged = DeployAndStartBattle(DeployKey).bAccepted && StateEquals(AfterDeploy);
				const FTreadM1MatchState BeforeBattleCommands = MatchState;
				const FTreadM1CommandResult BattlePurchase = PurchaseShopSlot(TEXT("P0"), 0);
				const FTreadM1CommandResult BattleMove = MoveUnitToBoard(TEXT("P0"), BenchUnitId, FIntPoint(0, 6));
				CheckNamed(TEXT("battleCommandGuards"), !BattlePurchase.bAccepted && !BattleMove.bAccepted &&
					BattlePurchase.ReasonCode == ETreadM1RejectReason::InvalidPhase && BattleMove.ReasonCode == ETreadM1RejectReason::InvalidPhase &&
					!CanScout() && GetScoutSnapshot(TEXT("P0")).PlayerId.IsEmpty() && StateEquals(BeforeBattleCommands));
				Tick(45.0f);
				bResolved = bDeployed && MatchState.Phase == ETreadM1Phase::Settlement;
				bool bPairingsUnchanged = DeployedPairings.Num() == MatchState.LastBattleResult.Pairings.Num();
				for (int32 PairIndex = 0; bPairingsUnchanged && PairIndex < DeployedPairings.Num(); ++PairIndex)
				{
					bPairingsUnchanged = DeployedPairings[PairIndex].PlayerId == MatchState.LastBattleResult.Pairings[PairIndex].PlayerId &&
						DeployedPairings[PairIndex].OpponentId == MatchState.LastBattleResult.Pairings[PairIndex].OpponentId;
				}
				CheckNamed(TEXT("battlePairingsFixedAtDeployment"), bDuplicateDeployUnchanged && bPairingsUnchanged &&
					DeployedPairings.Num() == 2 && MatchState.LastBattleResult.RoundIndex == Round);
				CheckNamed(FString::Printf(TEXT("timerRound%d"), Round), bResolved);
			}
			else
			{
				const FString RoundKey = FString::Printf(TEXT("selftest-r%d-run"), Round);
				bResolved = RunRound(RoundKey).bAccepted && MatchState.Phase == ETreadM1Phase::Settlement;
				const FTreadM1MatchState AfterRound = MatchState;
				CheckNamed(TEXT("requestIdempotency"), RunRound(RoundKey).bAccepted && StateEquals(AfterRound));
			}
			bool bEconomy = MatchState.Players.Num() == BeforePlayers.Num();
			for (int32 Index = 0; Index < BeforePlayers.Num(); ++Index)
			{
				const FTreadM1PlayerState& Before = BeforePlayers[Index];
				const FTreadM1PlayerState& After = MatchState.Players[Index];
				FTreadM1PlayerState IncomeInput = After;
				IncomeInput.Funds = Before.Funds;
				IncomeInput.PendingTraitIncome = After.LastSettlementIncome.Other;
				const FTreadM1IncomeBreakdown Income = CalculateIncome(IncomeInput);
				FTreadM1PlayerState ExpectedExperience = Before;
				if (!HasN1Economy()) ApplyExperience(ExpectedExperience, 2);
				// N1 (Stronghold-Protocol): leftover funds are lost at settlement unless a band carries them over.
				const bool bKeepsFunds = !HasN1Economy() || !PactData->Economy.bLeftoverFundsLost || After.Flags.Contains(TEXT("flag:CarryOverFunds"));
				const int32 Kept = bKeepsFunds ? Before.Funds : 0;
				bEconomy &= !After.bIsEliminated && After.Funds == Kept + Income.Base + Income.Interest + Income.Streak + Income.Other &&
					After.Level == ExpectedExperience.Level && After.Experience == ExpectedExperience.Experience;
			}
			const FTreadM1MatchState BeforeRepeatedSettlement = MatchState;
			const FString SettleKey = FString::Printf(TEXT("selftest-r%d-settle"), Round);
			const bool bSettlementOnce = SettleRound(SettleKey).bAccepted && StateEquals(BeforeRepeatedSettlement) &&
				SettleRound(SettleKey).bAccepted && StateEquals(BeforeRepeatedSettlement) &&
				SettleRound(SettleKey + TEXT("-fresh-key")).bAccepted && StateEquals(BeforeRepeatedSettlement);
			CheckNamed(TEXT("settlementOncePerRound"), bSettlementOnce && bEconomy);
			CheckNamed(TEXT("requestIdempotency"), bSettlementOnce);
			const FTreadM1MatchState BeforeRejectedRetry = MatchState;
			const FTreadM1CommandResult RejectedRetry = PurchaseShopSlot(TEXT("P0"), -1, TEXT("selftest-reject-cache"));
			CheckNamed(TEXT("requestIdempotency"), !RejectedRetry.bAccepted &&
				RejectedRetry.ReasonCode == RejectedPurchase.ReasonCode && StateEquals(BeforeRejectedRetry));
			const bool bBattleCommandsLocked = !PurchaseShopSlot(TEXT("P0"), 0, FString::Printf(TEXT("selftest-r%d-invalid-purchase"), Round)).bAccepted &&
				!MoveUnitToBoard(TEXT("P0"), BenchUnitId, FIntPoint(0, 6), FString::Printf(TEXT("selftest-r%d-invalid-move"), Round)).bAccepted;
			CheckNamed(TEXT("phaseCommandGuards"), bBattleCommandsLocked);
			TSet<FString> PairedPlayers;
			for (const FTreadM1BattlePairing& Pairing : MatchState.LastBattleResult.Pairings)
			{
				PairedPlayers.Add(Pairing.PlayerId);
				PairedPlayers.Add(Pairing.OpponentId);
			}
			const bool bRoundPassed = bPrepared && bResolved && bRoundType && bEconomy && bSettlementOnce &&
				LastSettledRoundIndex == Round && MatchState.LastBattleResult.RoundIndex == Round &&
				MatchState.LastBattleResult.Pairings.Num() == 2 && PairedPlayers.Num() == 4 &&
				MatchState.LastBattleResult.Outcomes.Num() == 4 && MatchState.BattleEvents.Num() > EventsBefore && ValidatePoolLedger();
			CheckNamed(FString::Printf(TEXT("round%d"), Round), bRoundPassed);
			if (bRoundPassed)
			{
				OutAcceptedRounds.Add(Round);
				OutRoundTypes.Add(RoundTypeName(MatchState.RoundType));
			}
			if (OutTrace)
			{
				OutTrace->Add(FString::Printf(TEXT("R%d:%s:%s"), Round, *RoundTypeName(MatchState.RoundType),
					bRoundPassed ? TEXT("PASS") : TEXT("FAIL")));
			}
			if (!bRoundPassed) break;
		}
		CheckNamed(TEXT("allTwelveRounds"), OutAcceptedRounds.Num() == MaxRounds && LastSettledRoundIndex == MaxRounds);
		bool bSawTarget = false;
		bool bSawDamage = false;
		bool bSawDeath = false;
		for (const FTreadM1BattleEvent& Event : MatchState.BattleEvents)
		{
			bSawTarget |= Event.EventType == ETreadM1BattleEventType::UnitTargetChanged && !Event.SourceUnitInstanceId.IsEmpty() && !Event.NewTargetUnitInstanceId.IsEmpty();
			bSawDamage |= Event.EventType == ETreadM1BattleEventType::UnitDamaged && !Event.SourceUnitInstanceId.IsEmpty() && !Event.TargetUnitInstanceId.IsEmpty() && Event.Amount > 0;
			bSawDeath |= Event.EventType == ETreadM1BattleEventType::UnitDied && !Event.TargetUnitInstanceId.IsEmpty();
		}
		CheckNamed(TEXT("unitBattleEvents"), bSawTarget && bSawDamage && bSawDeath);
		const bool bGameOver = AdvanceToNextRound(TEXT("selftest-gameover")).bAccepted &&
			MatchState.Phase == ETreadM1Phase::GameOver && MatchState.RoundIndex == MaxRounds;
		CheckNamed(TEXT("gameOverAfterRound12"), bGameOver);
		const FTreadM1MatchState AtGameOver = MatchState;
		CheckNamed(TEXT("requestIdempotency"), AdvanceToNextRound(TEXT("selftest-gameover")).bAccepted && StateEquals(AtGameOver));
		CheckNamed(TEXT("gameOverRejectsNewRound"), !RunRound(TEXT("selftest-after-gameover")).bAccepted && StateEquals(AtGameOver));
		if (OutTrace) OutTrace->Add(bGameOver ? TEXT("GameOver:PASS") : TEXT("GameOver:FAIL"));

		FString Signature;
		for (const FTreadM1PlayerState& Player : MatchState.Players)
		{
			Signature += FString::Printf(TEXT("P:%s:%d:%d:%d:%d|"), *Player.PlayerId, Player.Health, Player.Funds, Player.Level, Player.Rank);
			for (const FTreadM1ShopSlot& Slot : Player.Shop.Slots)
			{
				Signature += FString::Printf(TEXT("S:%s:%s:%d|"), *Slot.CharacterId, *Slot.OperatorTier, Slot.Cost);
			}
		}
		for (const FString& Id : MatchState.BP.BannedStrategyIds) Signature += TEXT("B:") + Id + TEXT("|");
		for (const FString& Id : MatchState.BP.AvailableStrategyIds) Signature += TEXT("A:") + Id + TEXT("|");
		Signature += TEXT("PLAYER:") + MatchState.BP.PlayerStrategyId + TEXT("|");
		for (const FString& Id : MatchState.BP.AiStrategyIds) Signature += TEXT("AI:") + Id + TEXT("|");
		for (const FTreadM1BattlePairing& Pairing : MatchState.LastBattleResult.Pairings)
		{
			Signature += TEXT("PAIR:") + Pairing.PlayerId + TEXT(":") + Pairing.OpponentId + TEXT("|");
		}
		for (const FTreadM1BattleOutcome& Outcome : MatchState.LastBattleResult.Outcomes)
		{
			Signature += FString::Printf(TEXT("O:%s:%s:%d:%d|"), *Outcome.PlayerId, *Outcome.Outcome, Outcome.HealthAfter, Outcome.RankAfter);
		}
		Signature += FString::Printf(TEXT("INCOME:%d:%d:%d:%d:RNG:%d"), MatchState.LastBattleResult.IncomeBreakdown.Base,
			MatchState.LastBattleResult.IncomeBreakdown.Interest, MatchState.LastBattleResult.IncomeBreakdown.Streak,
			MatchState.LastBattleResult.IncomeBreakdown.Other, MatchState.RandomStreamState);
		for (const FTreadM1BattleEvent& Event : MatchState.BattleEvents)
		{
			Signature += FString::Printf(TEXT("|EVENT:%s:%d:%d:%s:%s:%d:%d"), *Event.EventId, Event.RoundIndex,
				static_cast<int32>(Event.EventType), *Event.SourceUnitInstanceId, *Event.TargetUnitInstanceId, Event.Amount, Event.TargetHealthAfter);
		}
		for (const FTreadM1PoolLedgerEntry& Entry : MatchState.PoolLedger.Entries)
		{
			Signature += FString::Printf(TEXT("|POOL:%s:%s:%s:%s:%d:%d"), *Entry.EntryId, *Entry.Action,
				*Entry.PlayerId, *Entry.CharacterId, Entry.Delta, Entry.PoolCopiesAvailable);
		}
		return Signature;
	};

	// Separate combat-driven elimination fixture. It is discarded by the next
	// InitializeMatch; returned player assets are never resurrected in place.
	InitializeMatch(Seed);
	Checks.Add(RunRound(TEXT("elimination-setup")).bAccepted);
	Checks.Add(AdvanceToNextRound(TEXT("elimination-prepare")).bAccepted);
	TArray<FString> BoardIds;
	for (const FTreadM1UnitInstance& Unit : MatchState.Players[0].BoardUnits) BoardIds.Add(Unit.UnitInstanceId);
	for (const FString& Id : BoardIds) Checks.Add(MoveUnitToBench(TEXT("P0"), Id).bAccepted);
	MatchState.Players[0].Health = 1;
	MatchState.Players[0].Level = 1;
	const int32 HumanFunds = MatchState.Players[0].Funds;
	const bool bEliminationResolved = RunRound(TEXT("elimination-round")).bAccepted;
	const FTreadM1PlayerState& Eliminated = MatchState.Players[0];
	const bool bElimination = bEliminationResolved && Eliminated.Health == 0 && Eliminated.bIsEliminated &&
		Eliminated.BoardUnits.IsEmpty() && Eliminated.BenchUnits.IsEmpty() && Eliminated.Funds == HumanFunds &&
		PoolReturnedPlayerIds.Contains(TEXT("P0")) && MatchState.LastBattleResult.EliminatedPlayerIds.Contains(TEXT("P0")) && ValidatePoolLedger();
	const FTreadM1MatchState AfterElimination = MatchState;
	ReturnPlayerPoolAssets(MatchState.Players[0]);
	CheckNamed(TEXT("eliminationReturnsPoolOnce"), bElimination && StateEquals(AfterElimination));
	CheckNamed(TEXT("humanEliminationEndsMatch"), AdvanceToNextRound(TEXT("elimination-gameover")).bAccepted &&
		MatchState.Phase == ETreadM1Phase::GameOver && MatchState.RoundIndex == 2);

	// Default-health gameplay must also reach a legitimate terminal state.
	InitializeMatch(Seed);
	bool bNaturalMatch = true;
	for (int32 Round = 1; Round <= MaxRounds; ++Round)
	{
		bNaturalMatch &= RunRound(FString::Printf(TEXT("natural-r%d"), Round)).bAccepted;
		if (MatchState.Phase != ETreadM1Phase::Settlement) { bNaturalMatch = false; break; }
		bNaturalMatch &= AdvanceToNextRound(FString::Printf(TEXT("natural-next-%d"), Round)).bAccepted;
		if (MatchState.Phase == ETreadM1Phase::GameOver) break;
	}
	CheckNamed(TEXT("defaultHealthMatchEnds"), bNaturalMatch && MatchState.Phase == ETreadM1Phase::GameOver &&
		MatchState.RoundIndex >= 1 && MatchState.RoundIndex <= MaxRounds && ValidatePoolLedger());

	TArray<int32> AcceptedRounds;
	TArray<FString> AcceptedRoundTypes;
	const FString FirstReplay = RunOneReplay(&PhaseTrace, AcceptedRounds, AcceptedRoundTypes);
	const uint32 ReplaySignature = FCrc::StrCrc32(*FirstReplay);
	TArray<int32> ReplayedRounds;
	TArray<FString> ReplayedRoundTypes;
	const FString SecondReplay = RunOneReplay(nullptr, ReplayedRounds, ReplayedRoundTypes);
	CheckNamed(TEXT("replayRoundCoverage"), AcceptedRounds == ReplayedRounds && AcceptedRoundTypes == ReplayedRoundTypes);
	const bool bSameSeedReplayEqual = FirstReplay == SecondReplay;
	Checks.Add(bSameSeedReplayEqual);
	const FString Path = OutputPath.IsEmpty() ? FPaths::Combine(FPaths::ProjectDir(), TEXT("Saved/Reports/M1_Match_SelfTest.json")) : OutputPath;
	const bool bMatchReportSaved = WriteSelfTestReport(Path, PhaseTrace, Checks, bSameSeedReplayEqual, ReplaySignature, AcceptedRounds, AcceptedRoundTypes, NamedChecks);
	const FString PoolReportPath = FPaths::Combine(FPaths::ProjectDir(), TEXT("Saved/Reports/M1_PoolLedger_Conservation.json"));
	const bool bPoolReportSaved = WritePoolLedgerReport(PoolReportPath);
	return bMatchReportSaved && bPoolReportSaved && !Checks.Contains(false);
}
