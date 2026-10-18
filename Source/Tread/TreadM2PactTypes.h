#pragma once

#include "CoreMinimal.h"
#include "TreadM2PactTypes.generated.h"

/** Event-bus trigger families.  Values mirror Traits.json "trigger" plus bus-only events. */
UENUM(BlueprintType)
enum class ETreadM2Trigger : uint8
{
	Acquire,
	RoundStart,
	RoundEnd,
	Battle,
	Sell,
	Passive,
	Deploy,
	Undeploy,
	Combine,
	Equip,
	MatchStart,
	BattleStart,
	BattleEnd,
	Settlement,
	ShopRefresh,
	BuyExperience
};

/** Runtime progress of one pact for one participant: member count and stacks are independent. */
USTRUCT(BlueprintType)
struct TREAD_API FTreadM2PactProgress
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Pact") FString PactId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Pact") FString Kind;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Pact") TArray<int32> Thresholds;
	/** Distinct member characters counted for activation (board, plus bench for bench-counted pacts). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Pact") int32 Count = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Pact") int32 BoardCount = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Pact") int32 BenchCount = 0;
	/** Extra members granted by an active 调和 (harmony) unit to an already active core pact. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Pact") int32 HarmonyBonus = 0;
	/** 0 = inactive, otherwise the index (1-based) of the highest reached threshold. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Pact") int32 ActiveTier = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Pact") int32 NextThreshold = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Pact") bool bActive = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Pact") int32 Stacks = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Pact") int32 LastStackDelta = 0;
	/** TraitLog sequence of the last stack/tier change; drives the UI highlight pulse. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Pact") int32 LastChangeSequence = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Pact") int32 EveryMilestonesPaid = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Pact") TArray<FString> OnceMilestonesReached;
};

/** Strategy-driven modifier applied to pact evaluation (threshold shift or bench counting). */
USTRUCT(BlueprintType)
struct TREAD_API FTreadM2PactModifier
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Pact") FString PactId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Pact") int32 ThresholdDelta = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Pact") bool bCountsBench = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Pact") FString SourceStrategyId;
};

/** One observable event-bus step: a trait, pact tier op, milestone or strategy effect. */
USTRUCT(BlueprintType)
struct TREAD_API FTreadM2TraitLogEntry
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Log") int32 Sequence = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Log") int32 RoundIndex = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Log") FString PlayerId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Log") FString Trigger;
	/** Concrete source event, e.g. Purchase, Kill, AmmoConsumed, SelfKnockedOut. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Log") FString Event;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Log") FString UnitInstanceId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Log") FString CharacterId;
	/** Trait id, "pact:<id>", "milestone:<id>" or "strategy:<id>". */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Log") FString SourceId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Log") FString Op;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Log") FString PactId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Log") int32 Amount = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Log") int32 StacksAfter = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Log") bool bElite = false;
	/** applied | skipped:<reason> | deferred-M4 | event */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Log") FString Status;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Log") FString Detail;
};

/** Pact state frozen when a battle starts; combat modifiers read only this snapshot. */
USTRUCT(BlueprintType)
struct TREAD_API FTreadM2BattlePactState
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Battle") FString PlayerId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Battle") int32 RoundIndex = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "M2|Battle") TArray<FTreadM2PactProgress> Pacts;
};
