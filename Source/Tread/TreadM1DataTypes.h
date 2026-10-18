#pragma once

#include "CoreMinimal.h"
#include "TreadM2PactTypes.h"
#include "TreadM1DataTypes.generated.h"

UENUM(BlueprintType)
enum class ETreadM1Phase : uint8
{
	MainMenu,
	R0Briefing,
	PreMatchBP,
	Preparation,
	Battle,
	Settlement,
	GameOver
};

UENUM(BlueprintType)
enum class ETreadM1MatchMode : uint8
{
	FreeCompetition
};

UENUM(BlueprintType)
enum class ETreadM1RoundType : uint8
{
	Briefing,
	PvE,
	PvP,
	Leader
};

UENUM(BlueprintType)
enum class ETreadM1UnitLocation : uint8
{
	Bench,
	Board,
	Removed
};

UENUM(BlueprintType)
enum class ETreadM1ShopLockMode : uint8
{
	AutoRefreshOnly
};

UENUM(BlueprintType)
enum class ETreadM1BenchPurchasePolicy : uint8
{
	RejectWhenFull
};

UENUM(BlueprintType)
enum class ETreadM1AutoBattleMode : uint8
{
	AlwaysOn
};

UENUM(BlueprintType)
enum class ETreadM1EliminationFlow : uint8
{
	DirectSettlement
};

UENUM(BlueprintType)
enum class ETreadM1AIPickState : uint8
{
	Waiting,
	Thinking,
	Selected,
	Confirmed
};

UENUM(BlueprintType)
enum class ETreadM1BattleEventType : uint8
{
	UnitDamaged,
	UnitDied,
	UnitTargetChanged,
	// M2 battle-event bus sources (appended; existing values keep their meaning).
	SkillActivated,
	AmmoConsumed,
	EnemyFrozen,
	/** document/175: an item proc fired (revive, undying save, burn tick). */
	ItemProc
};

UENUM(BlueprintType)
enum class ETreadM1RejectReason : uint8
{
	None,
	InvalidPhase,
	InsufficientFunds,
	BenchFull,
	ShopSlotEmpty,
	ShopSlotSold,
	ShopLocked,
	MaxLevelReached,
	PopulationLimitReached,
	InvalidTarget,
	NotOwnUnit,
	InvalidBoardCell,
	StrategyUnavailable,
	StrategyAlreadyChosen,
	StrategyLocked,
	PlayerHealthInsufficient,
	AlreadyConfirmed,
	AlreadyProcessed,
	PlayerEliminated,
	ScoutUnavailable,
	Unknown,
	ItemUnavailable,
	EquipmentFull,
	/** document/176: the reward offer is gone or already claimed. */
	RewardUnavailable
};

USTRUCT(BlueprintType)
struct TREAD_API FTreadM1UnitInstance
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Unit") FString UnitInstanceId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Unit") FString CharacterId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Unit") FString OriginalOperatorName;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Unit") FString OperatorTier;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Unit") int32 UnitStar = 1;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Unit") int32 Cost = 1;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Unit") ETreadM1UnitLocation Location = ETreadM1UnitLocation::Bench;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Unit") FIntPoint BoardCell = FIntPoint(-1, -1);
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Unit") FString OwnerPlayerId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Unit") TArray<FString> EquipmentIds;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Unit") bool bIsTransformClone = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Unit") FString CopySourceCharacterId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Unit") FString CloneInstanceId;
	/** Shared-pool copies represented by this instance (1 for a bought unit, sum of parts after a combine, 0 for a clone). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Unit") int32 PoolCopiesHeld = 1;
};

USTRUCT(BlueprintType)
struct TREAD_API FTreadM1ShopSlot
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Shop") int32 SlotIndex = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Shop") FString CharacterId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Shop") FString OperatorTier;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Shop") int32 Cost = 1;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Shop") bool bIsSold = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Shop") bool bIsLockedByPlayer = false;
};

USTRUCT(BlueprintType)
struct TREAD_API FTreadM1ShopState
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Shop") TArray<FTreadM1ShopSlot> Slots;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Shop") bool bLocked = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Shop") ETreadM1ShopLockMode LockMode = ETreadM1ShopLockMode::AutoRefreshOnly;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Shop") int32 RefreshCost = 2;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Shop") int32 RefreshIndex = 0;
};

USTRUCT(BlueprintType)
struct TREAD_API FTreadM1IncomeBreakdown
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Economy") int32 Base = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Economy") int32 Interest = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Economy") int32 Streak = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Economy") int32 Other = 0;
};

USTRUCT(BlueprintType)
struct TREAD_API FTreadM1PlayerState
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Player") FString PlayerId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Player") FString DisplayName;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Player") bool bIsHuman = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Player") bool bIsEliminated = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Player") int32 Rank = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Player") int32 Health = 100;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Player") int32 Funds = 5;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Player") int32 Level = 3;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Player") int32 Experience = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Player") int32 ExperienceToNextLevel = 6;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Player") int32 PopulationUsed = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Player") int32 PopulationLimit = 3;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Player") int32 WinStreak = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Player") int32 LossStreak = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Player") FString InitialStrategyId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Player") FTreadM1ShopState Shop;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Player") TArray<FString> BenchUnitInstanceIds;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Player") TArray<FTreadM1UnitInstance> BenchUnits;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Player") TArray<FTreadM1UnitInstance> BoardUnits;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Player") FTreadM1IncomeBreakdown NextRoundIncome;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Player") TArray<FString> EquipmentIds;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Player") TArray<FString> ActivePactIds;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Pact") TArray<FTreadM2PactProgress> Pacts;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Pact") TArray<FTreadM2PactModifier> PactModifiers;
	/** Trait/pact funds promised for the next settlement; paid as IncomeBreakdown.Other. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Economy") int32 PendingTraitIncome = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Economy") int32 AcquiredThisRound = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Economy") int32 FundsSpentThisRound = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Economy") int32 ShopPriceDelta = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Economy") FTreadM1IncomeBreakdown LastSettlementIncome;
	/** Once-only strategy/pact flags, e.g. strategy_021:once or flag:DeployCostHalved. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Pact") TArray<FString> Flags;
	// N1 (Stronghold-Protocol economy): Level is the 调度中心 (shop) level; upgrades replace bought experience.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "N1|Economy") int32 RefreshesThisRound = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "N1|Economy") int32 FreeRefreshes = 0;
	/** Rounds since the last shop upgrade; each lowers the upgrade price by Economy.upgradeDiscountPerRound. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "N1|Economy") int32 ShopUpgradeDiscount = 0;
	/** document/176: free three-choice item reward rolled at the start of every preparation. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "N1|Economy") TArray<FString> RewardOffer;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "N1|Economy") bool bRewardClaimed = false;
	/** document/178: 5_07 counts every sale; 6_03 pays at most N times per round. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "N1|Economy") int32 SoldCount = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "N1|Economy") int32 AcquireFundsCount = 0;
};

USTRUCT(BlueprintType)
struct TREAD_API FTreadM1StrategyState
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Strategy") FString StrategyId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Strategy") FString IssuerCharacterId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Strategy") FString OfferText;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Strategy") int32 HpCost = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Strategy") TArray<FString> Effects;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Strategy") FString Trigger;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Strategy") FString UnlockCondition;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Strategy") bool bInitialOnly = true;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Strategy") bool bBpEligible = true;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Strategy") FString UniqueScope = TEXT("StrategyId");
};

USTRUCT(BlueprintType)
struct TREAD_API FTreadM1BPState
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|BP") int32 CandidateCount = 40;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|BP") int32 SystemBanCount = 4;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|BP") int32 PlayerPickCount = 1;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|BP") int32 AiPickCount = 3;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|BP") TArray<FString> AiPickOrder;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|BP") bool bPlayerCanReviseUntilAiConfirmed = true;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|BP") bool bHasCountdown = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|BP") bool bAiSelectionStartsAfterPlayerPick = true;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|BP") int64 Seed = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|BP") TArray<FString> BannedStrategyIds;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|BP") TArray<FString> AvailableStrategyIds;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|BP") FString PlayerStrategyId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|BP") TArray<FString> AiStrategyIds;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|BP") TArray<ETreadM1AIPickState> AiPickStates;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|BP") bool bConfirmed = false;
};

USTRUCT(BlueprintType)
struct TREAD_API FTreadM1AIPickStatus
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|BP") FString PlayerId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|BP") ETreadM1AIPickState State = ETreadM1AIPickState::Waiting;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|BP") FString StrategyId;
};

USTRUCT(BlueprintType)
struct TREAD_API FTreadM1LevelRule
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Rules") int32 Level = 1;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Rules") int32 ExperienceToNextLevel = 0;
};

USTRUCT(BlueprintType)
struct TREAD_API FTreadM1MatchRules
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Rules") TArray<FTreadM1LevelRule> LevelExperienceTable;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Rules") ETreadM1BenchPurchasePolicy BenchPurchasePolicy = ETreadM1BenchPurchasePolicy::RejectWhenFull;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Rules") ETreadM1ShopLockMode ShopLockMode = ETreadM1ShopLockMode::AutoRefreshOnly;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Rules") bool bBpHasCountdown = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Rules") bool bAiSelectionStartsAfterPlayerPick = true;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Rules") bool bDeployCompletesPreparation = true;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Rules") ETreadM1AutoBattleMode AutoBattleMode = ETreadM1AutoBattleMode::AlwaysOn;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Rules") ETreadM1EliminationFlow PlayerEliminationFlow = ETreadM1EliminationFlow::DirectSettlement;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Economy") int32 PreparationDurationSec = 30;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Economy") int32 BaseIncome = 5;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Economy") int32 InterestFundsStep = 10;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Economy") int32 MaxInterest = 5;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Economy") int32 ExperiencePurchaseCost = 4;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Economy") int32 ExperiencePurchaseAmount = 4;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Economy") int32 ShopSlotCount = 5;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Economy") int32 ShopRefreshCost = 2;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Economy") int32 MaxBenchSlots = 8;
};

USTRUCT(BlueprintType)
struct TREAD_API FTreadM1PactStack
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pact") FString PactId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pact") int32 StackCount = 0;
};

USTRUCT(BlueprintType)
struct TREAD_API FTreadM1ScoutSnapshot
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Scout") FString PlayerId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Scout") FString DisplayName;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Scout") int32 Rank = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Scout") int32 Health = 100;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Scout") int32 Funds = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Scout") int32 Level = 1;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Scout") int32 PopulationUsed = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Scout") int32 PopulationLimit = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Scout") FTreadM1IncomeBreakdown NextRoundIncome;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Scout") TArray<FTreadM1UnitInstance> BoardUnits;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Scout") TArray<FString> BenchUnitInstanceIds;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Scout") TArray<FTreadM1UnitInstance> BenchUnits;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Scout") TArray<FString> EquipmentIds;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Scout") TArray<FString> ActivePactIds;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Scout") TArray<FTreadM1PactStack> PactStacks;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Scout") TArray<FTreadM2PactProgress> Pacts;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Scout") bool bReadOnly = true;
};

USTRUCT(BlueprintType)
struct TREAD_API FTreadM1BattlePairing
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") FString PlayerId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") FString OpponentId;
};

USTRUCT(BlueprintType)
struct TREAD_API FTreadM1BattleOutcome
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") FString PlayerId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") FString Outcome;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") int32 SurvivingUnitCount = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") int32 HealthBefore = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") int32 HealthAfter = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") int32 RankBefore = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") int32 RankAfter = 0;
};

USTRUCT(BlueprintType)
struct TREAD_API FTreadM1BattleResult
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") int32 RoundIndex = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") TArray<FTreadM1BattlePairing> Pairings;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") TArray<FTreadM1BattleOutcome> Outcomes;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") FTreadM1IncomeBreakdown IncomeBreakdown;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") TArray<FString> EliminatedPlayerIds;
};

USTRUCT(BlueprintType)
struct TREAD_API FTreadM1BattleEvent
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") FString EventId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") int32 Sequence = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") int32 RoundIndex = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") ETreadM1BattleEventType EventType = ETreadM1BattleEventType::UnitDamaged;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") FString SourcePlayerId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") FString SourceUnitInstanceId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") FString TargetPlayerId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") FString TargetUnitInstanceId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") int32 Amount = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") int32 TargetHealthAfter = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") FString NewTargetUnitInstanceId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Battle") float TimeSec = 0.0f;
};

USTRUCT(BlueprintType)
struct TREAD_API FTreadM1CommandResult
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Command") bool bAccepted = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Command") ETreadM1RejectReason ReasonCode = ETreadM1RejectReason::None;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Command") FString RequestId;
};

USTRUCT(BlueprintType)
struct TREAD_API FTreadM1PoolLedgerEntry
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pool") FString EntryId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pool") int32 Revision = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pool") FString Action;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pool") FString PlayerId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pool") FString CharacterId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pool") FString OperatorTier;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pool") FString UnitInstanceId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pool") FString CloneInstanceId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pool") FString CopySourceCharacterId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pool") int32 PoolCopiesTotal = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pool") int32 PoolCopiesAvailable = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pool") int32 ReservedCopies = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pool") int32 OwnedCopies = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pool") int32 Delta = 0;
};

USTRUCT(BlueprintType)
struct TREAD_API FTreadM1PoolBalance
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pool") FString CharacterId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pool") FString OperatorTier;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pool") int32 PoolCopiesTotal = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pool") int32 PoolCopiesAvailable = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pool") int32 ReservedCopies = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pool") int32 OwnedCopies = 0;
};

USTRUCT(BlueprintType)
struct TREAD_API FTreadM1PoolLedger
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pool") int32 Revision = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pool") TArray<FTreadM1PoolBalance> Balances;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Pool") TArray<FTreadM1PoolLedgerEntry> Entries;
};

/** M4: one campaign stage as the UI and tests see it. */
USTRUCT(BlueprintType)
struct TREAD_API FTreadM4CampaignStageView
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M4|Campaign") int32 Index = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M4|Campaign") FString Country;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M4|Campaign") FString Landmark;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M4|Campaign") FString Rule;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M4|Campaign") FString Effect;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M4|Campaign") int32 AiLevel = 1;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M4|Campaign") bool bUnlocked = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M4|Campaign") bool bConquered = false;
};

USTRUCT(BlueprintType)
struct TREAD_API FTreadM1MatchState
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Match") FString SchemaVersion = TEXT("Tread.M1.DataContract.v1");
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Match") FString MatchId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Match") int64 Seed = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Match") FString RandomStreamAlgorithm = TEXT("UE.FRandomStream.v1");
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Match") int32 RandomStreamState = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Match") ETreadM1MatchMode Mode = ETreadM1MatchMode::FreeCompetition;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Match") ETreadM1Phase Phase = ETreadM1Phase::MainMenu;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Match") int32 RoundIndex = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Match") ETreadM1RoundType RoundType = ETreadM1RoundType::Briefing;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Match") float PhaseTimeRemainingSec = 0.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Match") FTreadM1MatchRules Rules;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Match") TArray<FTreadM1PlayerState> Players;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Match") TArray<FTreadM1StrategyState> Strategies;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Match") FTreadM1BPState BP;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Match") FTreadM1PoolLedger PoolLedger;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Match") TArray<FTreadM1ScoutSnapshot> ScoutSnapshots;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Match") FTreadM1BattleResult LastBattleResult;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M1|Match") TArray<FTreadM1BattleEvent> BattleEvents;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Match") FString PactDataVersion;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Match") TArray<FTreadM2TraitLogEntry> TraitLog;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Match") TArray<FTreadM2BattlePactState> BattlePactStates;
	/** M4: campaign stage of this match (0 = free match with the M1 rehearsal pairings). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M4|Campaign") int32 CampaignStage = 0;
	/** M4: the scripted opponent of the current battle (R1-R2 garrison / R12 leader), "" in PvP rounds. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M4|Campaign") FString ScriptedOpponentId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M4|Campaign") FString ScriptedOpponentName;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M4|Campaign") int32 ScriptedOpponentHealth = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M4|Campaign") int32 ScriptedOpponentMaxHealth = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M4|Campaign") TArray<FTreadM1UnitInstance> ScriptedOpponentUnits;
	/** M4: "" during play, then "Conquered", "Failed" or "WorldDomination" (stage 16 conquered) at GameOver. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M4|Campaign") FString CampaignResult;
	/** document/12: the battle is resolved and its events wait for the 3D replay; Settlement follows the replay
	 * (or the battle cap). Health and outcomes already hold the result, so the HUD shows HealthBefore meanwhile. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Battle|Presentation") bool bBattleAwaitingPresentation = false;
};
