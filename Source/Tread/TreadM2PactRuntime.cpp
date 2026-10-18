// M2 pact layers and data-driven trait interpreter for ATreadM1MatchController.
// Every behaviour is selected by fields of Content/Data/Generated/{Pacts,Traits,M2_ItemSeeds,StrategyEffects}.json;
// no card id or operator name is referenced here.

#include "TreadM1MatchController.h"

#include "Misc/Paths.h"
#include "TimerManager.h"
#include "UnrealClient.h"

namespace
{
	static const TCHAR* TierNames[] = {TEXT("I"), TEXT("II"), TEXT("III"), TEXT("IV"), TEXT("V"), TEXT("VI")};
	static const int32 MaxTraitDepth = 3;

	bool OnBoard(const FTreadM1UnitInstance& Unit)
	{
		return Unit.Location == ETreadM1UnitLocation::Board && Unit.BoardCell.X >= 0 && Unit.BoardCell.Y >= 0;
	}

	int32 TierFor(const TArray<int32>& Thresholds, int32 Count)
	{
		int32 Tier = 0;
		for (int32 Index = 0; Index < Thresholds.Num(); ++Index)
		{
			if (Count >= Thresholds[Index]) Tier = Index + 1;
		}
		return Tier;
	}
}

void ATreadM1MatchController::LoadM2Data()
{
	PactData = MakeShared<FTreadM2PactData>();
	if (!PactData->Load(FPaths::ProjectContentDir()))
	{
		UE_LOG(LogTemp, Error, TEXT("Tread M2 pact data failed to load: %s"), *PactData->Error);
	}
	MatchState.PactDataVersion = PactData->bLoaded ? PactData->Version : FString(TEXT("unloaded:")) + PactData->Error;
}

bool ATreadM1MatchController::IsElite(const FTreadM1UnitInstance& Unit) const
{
	return Unit.UnitStar >= (PactData.IsValid() ? PactData->EliteStarAtLeast : 2);
}

int32 ATreadM1MatchController::PurchaseCostFor(const FString& CharacterId, int32 DrawnCost) const
{
	if (const FTreadM2Card* Card = PactData.IsValid() ? PactData->FindCard(CharacterId) : nullptr)
	{
		for (const FTreadM2Trait& Trait : Card->Traits)
		{
			for (const FTreadM2Effect& Effect : Trait.Effects)
			{
				if (Effect.Op == TEXT("PurchaseCostOverride")) return FMath::Max(0, FMath::RoundToInt(Effect.BaseValue));
			}
		}
	}
	return DrawnCost;
}

bool ATreadM1MatchController::HasN1Economy() const
{
	return PactData.IsValid() && PactData->bLoaded && PactData->Economy.bLoaded;
}

FString ATreadM1MatchController::CardTier(const FString& CharacterId) const
{
	const FTreadM2Card* Card = PactData.IsValid() ? PactData->FindCard(CharacterId) : nullptr;
	return Card ? Card->OperatorTier : FString();
}

int32 ATreadM1MatchController::TierPrice(const FString& OperatorTier) const
{
	if (HasN1Economy())
	{
		if (const int32* Price = PactData->Economy.PriceByTier.Find(OperatorTier)) return *Price;
	}
	for (int32 Index = 0; Index < UE_ARRAY_COUNT(TierNames); ++Index)
	{
		if (OperatorTier == TierNames[Index]) return FMath::Clamp(Index + 1, 1, 5);
	}
	return 1;
}

int32 ATreadM1MatchController::ShopUpgradeCost(const FTreadM1PlayerState& Player) const
{
	if (!HasN1Economy()) return MatchState.Rules.ExperiencePurchaseCost;
	const FTreadN1Economy& E = PactData->Economy;
	if (Player.Level >= E.MaxShopLevel || !E.UpgradePrices.IsValidIndex(Player.Level - 1)) return 0;
	return FMath::Max(0, E.UpgradePrices[Player.Level - 1] - Player.ShopUpgradeDiscount * E.UpgradeDiscountPerRound);
}

bool ATreadM1MatchController::DrawShopCard(const FTreadM1PlayerState& Player, FString& OutCharacterId, FString& OutTier)
{
	// Stronghold-Protocol shopOdds "copyWeighted": one copy drawn uniformly from all remaining pool copies of
	// cards whose tier is <= the shop level.
	const int32 MaxTier = FMath::Clamp(Player.Level, 1, UE_ARRAY_COUNT(TierNames));
	int32 Total = 0;
	TArray<TPair<const FTreadM1PoolBalance*, int32>> Weighted;
	for (const FTreadM1PoolBalance& Balance : MatchState.PoolLedger.Balances)
	{
		int32 Tier = 0;
		for (int32 Index = 0; Index < UE_ARRAY_COUNT(TierNames); ++Index) if (Balance.OperatorTier == TierNames[Index]) Tier = Index + 1;
		if (Tier == 0 || Tier > MaxTier || Balance.PoolCopiesAvailable <= 0) continue;
		Total += Balance.PoolCopiesAvailable;
		Weighted.Emplace(&Balance, Total);
	}
	if (Total <= 0) return false;
	const int32 Roll = RandomStream.RandRange(1, Total);
	for (const TPair<const FTreadM1PoolBalance*, int32>& Entry : Weighted)
	{
		if (Roll <= Entry.Value)
		{
			OutCharacterId = Entry.Key->CharacterId;
			OutTier = Entry.Key->OperatorTier;
			return true;
		}
	}
	return false;
}

FTreadM2PactProgress* ATreadM1MatchController::FindPactProgress(FTreadM1PlayerState& Player, const FString& PactId)
{
	return Player.Pacts.FindByPredicate([&](const FTreadM2PactProgress& Progress) { return Progress.PactId == PactId; });
}

const FTreadM2PactProgress* ATreadM1MatchController::FindPactProgress(const FTreadM1PlayerState& Player, const FString& PactId) const
{
	return Player.Pacts.FindByPredicate([&](const FTreadM2PactProgress& Progress) { return Progress.PactId == PactId; });
}

TArray<FString> ATreadM1MatchController::GetUnitPacts(const FTreadM1PlayerState& Player, const FTreadM1UnitInstance& Unit, bool bIncludeHarmony) const
{
	TArray<FString> Result;
	if (!PactData.IsValid()) return Result;
	// Clones count as the copied character (CharacterId already equals the source).
	if (const FTreadM2Card* Card = PactData->FindCard(Unit.CharacterId))
	{
		for (const FString& Pact : Card->CorePacts) Result.AddUnique(Pact);
		for (const FString& Pact : Card->AdjunctPacts) Result.AddUnique(Pact);
	}
	for (const FString& ItemId : Unit.EquipmentIds)
	{
		if (const FTreadM2Item* Item = PactData->FindItem(ItemId))
		{
			for (const FString& Pact : Item->ProvidesPacts) Result.AddUnique(Pact);
		}
	}
	if (bIncludeHarmony)
	{
		bool bHarmonyMember = false;
		for (const FString& Pact : Result)
		{
			const FTreadM2PactDef* Def = PactData->FindPact(Pact);
			bHarmonyMember |= Def && Def->bHarmony;
		}
		if (bHarmonyMember)
		{
			for (const FTreadM2PactProgress& Progress : Player.Pacts)
			{
				if (Progress.bActive && Progress.Kind == TEXT("Core")) Result.AddUnique(Progress.PactId);
			}
		}
	}
	return Result;
}

void ATreadM1MatchController::RecomputePacts(FTreadM1PlayerState& Player)
{
	if (!PactData.IsValid() || !PactData->bLoaded) return;
	if (Player.Pacts.Num() != PactData->Pacts.Num())
	{
		Player.Pacts.Reset();
		for (const FTreadM2PactDef& Def : PactData->Pacts)
		{
			FTreadM2PactProgress& Progress = Player.Pacts.AddDefaulted_GetRef();
			Progress.PactId = Def.PactId;
			Progress.Kind = Def.Kind;
			Progress.Thresholds = Def.Thresholds;
		}
	}
	TArray<bool> WasActive;
	for (const FTreadM2PactProgress& Progress : Player.Pacts) WasActive.Add(Progress.bActive);

	for (int32 Index = 0; Index < PactData->Pacts.Num(); ++Index)
	{
		const FTreadM2PactDef& Def = PactData->Pacts[Index];
		FTreadM2PactProgress& Progress = Player.Pacts[Index];
		bool bCountsBench = Def.bCountsBench;
		int32 ThresholdDelta = 0;
		for (const FTreadM2PactModifier& Modifier : Player.PactModifiers)
		{
			if (Modifier.PactId != Def.PactId) continue;
			bCountsBench |= Modifier.bCountsBench;
			ThresholdDelta += Modifier.ThresholdDelta;
		}
		Progress.Thresholds.Reset();
		for (const int32 Threshold : Def.Thresholds) Progress.Thresholds.Add(FMath::Max(1, Threshold + ThresholdDelta));
		TSet<FString> BoardMembers;
		TSet<FString> AllMembers;
		for (const FTreadM1UnitInstance& Unit : Player.BoardUnits)
		{
			if (GetUnitPacts(Player, Unit, false).Contains(Def.PactId) || (Def.bCountsEliteAll && IsElite(Unit)))
			{
				BoardMembers.Add(Unit.CharacterId);
				AllMembers.Add(Unit.CharacterId);
			}
		}
		int32 BenchMembers = 0;
		if (bCountsBench)
		{
			for (const FTreadM1UnitInstance& Unit : Player.BenchUnits)
			{
				if (GetUnitPacts(Player, Unit, false).Contains(Def.PactId))
				{
					BenchMembers += AllMembers.Contains(Unit.CharacterId) ? 0 : 1;
					AllMembers.Add(Unit.CharacterId);
				}
			}
		}
		Progress.BoardCount = BoardMembers.Num();
		Progress.BenchCount = BenchMembers;
		Progress.HarmonyBonus = 0;
		Progress.Count = AllMembers.Num();
		// document/166: 独行 is a solo pact - a second member switches it off (bonds.json maxCount = 1).
		const bool bOverCap = Def.MaxCount > 0 && Progress.Count > Def.MaxCount;
		Progress.ActiveTier = bOverCap ? 0 : TierFor(Progress.Thresholds, Progress.Count);
	}

	// 调和 (harmony): each already active core pact gains one member per harmony member.
	int32 HarmonyMembers = 0;
	for (int32 Index = 0; Index < PactData->Pacts.Num(); ++Index)
	{
		if (PactData->Pacts[Index].bHarmony && Player.Pacts[Index].ActiveTier > 0) HarmonyMembers += Player.Pacts[Index].Count;
	}
	for (int32 Index = 0; Index < PactData->Pacts.Num(); ++Index)
	{
		FTreadM2PactProgress& Progress = Player.Pacts[Index];
		if (HarmonyMembers > 0 && Progress.Kind == TEXT("Core") && Progress.ActiveTier > 0)
		{
			Progress.HarmonyBonus = HarmonyMembers;
			Progress.Count += HarmonyMembers;
			Progress.ActiveTier = TierFor(Progress.Thresholds, Progress.Count);
		}
		Progress.bActive = Progress.ActiveTier > 0;
		Progress.NextThreshold = Progress.Thresholds.IsValidIndex(Progress.ActiveTier) ? Progress.Thresholds[Progress.ActiveTier] : 0;
	}

	Player.ActivePactIds.Reset();
	for (int32 Index = 0; Index < Player.Pacts.Num(); ++Index)
	{
		FTreadM2PactProgress& Progress = Player.Pacts[Index];
		if (Progress.bActive) Player.ActivePactIds.Add(Progress.PactId);
		if (WasActive.IsValidIndex(Index) && WasActive[Index] != Progress.bActive)
		{
			RecordTraitLog(Player, ETreadM2Trigger::Passive, Progress.bActive ? TEXT("PactActivated") : TEXT("PactDeactivated"),
				nullptr, TEXT("pact:") + Progress.PactId, TEXT("Tier"), Progress.PactId, Progress.ActiveTier, Progress.Stacks, false,
				TEXT("event"), FString::Printf(TEXT("count=%d thresholds=%s"), Progress.Count,
					*FString::JoinBy(Progress.Thresholds, TEXT("/"), [](int32 Value) { return FString::FromInt(Value); })));
			Progress.LastChangeSequence = MatchState.TraitLog.Num();
		}
	}
	// A pact that just activated may owe stack milestones accumulated while inactive.
	for (const FTreadM2PactProgress& Progress : TArray<FTreadM2PactProgress>(Player.Pacts))
	{
		if (Progress.bActive) EvaluatePactMilestones(Player, Progress.PactId, ETreadM2Trigger::Passive);
	}
}

void ATreadM1MatchController::RecomputeAllPacts()
{
	for (FTreadM1PlayerState& Player : MatchState.Players)
	{
		RecomputePacts(Player);
	}
}

void ATreadM1MatchController::RecordTraitLog(const FTreadM1PlayerState& Player, ETreadM2Trigger Trigger, const FString& EventName,
	const FTreadM1UnitInstance* Unit, const FString& SourceId, const FString& Op, const FString& PactId,
	int32 Amount, int32 StacksAfter, bool bElite, const FString& Status, const FString& Detail)
{
	FTreadM2TraitLogEntry Entry;
	Entry.Sequence = MatchState.TraitLog.Num() + 1;
	Entry.RoundIndex = MatchState.RoundIndex;
	Entry.PlayerId = Player.PlayerId;
	Entry.Trigger = FTreadM2PactData::TriggerName(Trigger);
	Entry.Event = EventName;
	if (Unit)
	{
		Entry.UnitInstanceId = Unit->UnitInstanceId;
		Entry.CharacterId = Unit->CharacterId;
	}
	Entry.SourceId = SourceId;
	Entry.Op = Op;
	Entry.PactId = PactId;
	Entry.Amount = Amount;
	Entry.StacksAfter = StacksAfter;
	Entry.bElite = bElite;
	Entry.Status = Status;
	Entry.Detail = Detail;
	MatchState.TraitLog.Add(MoveTemp(Entry));
}

int32 ATreadM1MatchController::AcquireRepeatCount(const FTreadM1PlayerState& Player) const
{
	int32 Repeat = 1;
	if (!PactData.IsValid()) return Repeat;
	for (int32 Index = 0; Index < PactData->Pacts.Num() && Index < Player.Pacts.Num(); ++Index)
	{
		const FTreadM2PactDef& Def = PactData->Pacts[Index];
		const FTreadM2PactProgress& Progress = Player.Pacts[Index];
		if (!Progress.bActive) continue;
		for (const FTreadM2Effect& Op : Def.TierOps[Progress.ActiveTier - 1])
		{
			if (Op.Op == TEXT("AcquireRepeat")) Repeat = FMath::Max(Repeat, FMath::RoundToInt(Op.BaseValue));
		}
		for (const FTreadM2Milestone& Milestone : Def.Milestones)
		{
			if (Milestone.Op == TEXT("AcquireRepeat") &&
				Progress.OnceMilestonesReached.Contains(FString::Printf(TEXT("%s@%d"), *Milestone.Op, Milestone.AtLeast)))
			{
				Repeat = FMath::Max(Repeat, Milestone.Amount);
			}
		}
	}
	return Repeat;
}

void ATreadM1MatchController::EvaluatePactMilestones(FTreadM1PlayerState& Player, const FString& PactId, ETreadM2Trigger Trigger)
{
	const FTreadM2PactDef* Def = PactData.IsValid() ? PactData->FindPact(PactId) : nullptr;
	FTreadM2PactProgress* Progress = FindPactProgress(Player, PactId);
	if (!Def || !Progress || !Progress->bActive) return;
	for (const FTreadM2Milestone& Milestone : Def->Milestones)
	{
		int32 Times = 0;
		if (Milestone.Every > 0)
		{
			Times = FMath::Max(0, Progress->Stacks / Milestone.Every - Progress->EveryMilestonesPaid);
			Progress->EveryMilestonesPaid += Times;
		}
		else if (Milestone.AtLeast > 0)
		{
			const FString Key = FString::Printf(TEXT("%s@%d"), *Milestone.Op, Milestone.AtLeast);
			if (Progress->Stacks >= Milestone.AtLeast && !Progress->OnceMilestonesReached.Contains(Key))
			{
				Progress->OnceMilestonesReached.Add(Key);
				Times = 1;
			}
		}
		for (int32 Time = 0; Time < Times; ++Time)
		{
			const FString SourceId = TEXT("milestone:") + PactId;
			if (Milestone.Op == TEXT("GainFundsNextRound"))
			{
				Player.PendingTraitIncome += Milestone.Amount;
				RecordTraitLog(Player, Trigger, TEXT("StackMilestone"), nullptr, SourceId, Milestone.Op, PactId, Milestone.Amount,
					Progress->Stacks, false, TEXT("applied"));
			}
			else if (Milestone.Op == TEXT("GrantItem"))
			{
				GrantItemToPlayer(Player, Milestone.Item, 1, SourceId, Trigger);
			}
			else if (Milestone.Op == TEXT("ShopPriceDelta"))
			{
				Player.ShopPriceDelta += Milestone.Amount;
				RecordTraitLog(Player, Trigger, TEXT("StackMilestone"), nullptr, SourceId, Milestone.Op, PactId, Milestone.Amount,
					Progress->Stacks, false, TEXT("applied"));
			}
			else
			{
				// AcquireRepeat is read through OnceMilestonesReached; Flag milestones are observable state.
				if (!Milestone.Flag.IsEmpty()) Player.Flags.AddUnique(TEXT("flag:") + Milestone.Flag);
				RecordTraitLog(Player, Trigger, TEXT("StackMilestone"), nullptr, SourceId, Milestone.Op, PactId, Milestone.Amount,
					Progress->Stacks, false, Milestone.Op == TEXT("AcquireRepeat") ? TEXT("applied") : TEXT("deferred-M4"), Milestone.Flag);
			}
			// Milestones can grant items/flags; re-find the progress in case an equip changed counts.
			Progress = FindPactProgress(Player, PactId);
			if (!Progress) return;
		}
	}
}

int32 ATreadM1MatchController::AddPactStacks(FTreadM1PlayerState& Player, const FString& PactId, int32 Amount, bool bRequireActive,
	const FString& SourceId, const FTreadM1UnitInstance* SourceUnit, ETreadM2Trigger Trigger, const FString& EventName, bool bAllowAmplify)
{
	FTreadM2PactProgress* Progress = FindPactProgress(Player, PactId);
	if (!Progress)
	{
		RecordTraitLog(Player, Trigger, EventName, SourceUnit, SourceId, TEXT("AddStacks"), PactId, Amount, 0, false, TEXT("skipped:unknown-pact"));
		return 0;
	}
	if (Amount <= 0)
	{
		RecordTraitLog(Player, Trigger, EventName, SourceUnit, SourceId, TEXT("AddStacks"), PactId, 0, Progress->Stacks, false, TEXT("skipped:zero-amount"));
		return 0;
	}
	if (bRequireActive && !Progress->bActive)
	{
		RecordTraitLog(Player, Trigger, EventName, SourceUnit, SourceId, TEXT("AddStacks"), PactId, Amount, Progress->Stacks,
			SourceUnit && IsElite(*SourceUnit), TEXT("skipped:pact-inactive"));
		return 0;
	}
	if (ActiveBattleCapRemaining)
	{
		Amount = FMath::Min(Amount, *ActiveBattleCapRemaining);
		if (Amount <= 0)
		{
			RecordTraitLog(Player, Trigger, EventName, SourceUnit, SourceId, TEXT("AddStacks"), PactId, 0, Progress->Stacks, false, TEXT("skipped:battle-cap"));
			return 0;
		}
		*ActiveBattleCapRemaining -= Amount;
	}
	const int32 Cap = PactData.IsValid() ? PactData->StackCap : 999;
	const int32 Applied = FMath::Min(Amount, FMath::Max(0, Cap - Progress->Stacks));
	Progress->Stacks += Applied;
	Progress->LastStackDelta = Applied;
	RecordTraitLog(Player, Trigger, EventName, SourceUnit, SourceId, TEXT("AddStacks"), PactId, Applied, Progress->Stacks,
		SourceUnit && IsElite(*SourceUnit), TEXT("applied"));
	Progress->LastChangeSequence = MatchState.TraitLog.Num();
	EvaluatePactMilestones(Player, PactId, Trigger);

	// A unit directly behind the source may amplify trait-driven battle stack gains (AmplifyFrontStackGain).
	if (bAllowAmplify && Trigger == ETreadM2Trigger::Battle && SourceUnit && OnBoard(*SourceUnit) && PactData.IsValid())
	{
		const FIntPoint BehindCell = SourceUnit->BoardCell + FIntPoint(0, 1);
		for (const FTreadM1UnitInstance& Behind : TArray<FTreadM1UnitInstance>(Player.BoardUnits))
		{
			if (Behind.BoardCell != BehindCell) continue;
			const FTreadM2Card* Card = PactData->FindCard(Behind.CharacterId);
			if (!Card) continue;
			for (const FTreadM2Trait& Trait : Card->Traits)
			{
				for (const FTreadM2Effect& Effect : Trait.Effects)
				{
					if (Effect.Op != TEXT("AmplifyFrontStackGain")) continue;
					const int32 Extra = FMath::RoundToInt(IsElite(Behind) ? Effect.EliteValue : Effect.BaseValue);
					AddPactStacks(Player, PactId, Extra, bRequireActive, Trait.Id, &Behind, Trigger, TEXT("FrontTraitStackGain"), false);
				}
			}
		}
	}
	return Applied;
}

TArray<FTreadM1UnitInstance> ATreadM1MatchController::ResolveTargets(const FTreadM1PlayerState& Player, const FTreadM1UnitInstance& Anchor,
	const FString& Targets, const FString& TriggerFilter) const
{
	TArray<FTreadM1UnitInstance> Result;
	const auto UnitAt = [&](FIntPoint Cell, TArray<FTreadM1UnitInstance>& Out)
	{
		for (const FTreadM1UnitInstance& Unit : Player.BoardUnits)
		{
			if (Unit.BoardCell == Cell) Out.Add(Unit);
		}
	};
	if (Targets == TEXT("Self") || Targets.IsEmpty() || Targets.StartsWith(TEXT("Self")))
	{
		Result.Add(Anchor);
	}
	if (Targets == TEXT("Bench"))
	{
		Result.Append(Player.BenchUnits);
		return Result;
	}
	if (Targets == TEXT("TopRightBoardUnit"))
	{
		TArray<FTreadM1UnitInstance> Candidates;
		for (const FTreadM1UnitInstance& Unit : Player.BoardUnits)
		{
			const FTreadM2Card* Card = PactData.IsValid() ? PactData->FindCard(Unit.CharacterId) : nullptr;
			if (!Card || Unit.UnitInstanceId == Anchor.UnitInstanceId) continue;
			for (const FTreadM2Trait& Trait : Card->Traits)
			{
				if (FTreadM2PactData::TriggerName(Trait.Trigger) == TriggerFilter) { Candidates.Add(Unit); break; }
			}
		}
		Candidates.Sort([](const FTreadM1UnitInstance& A, const FTreadM1UnitInstance& B)
		{
			return A.BoardCell.Y != B.BoardCell.Y ? A.BoardCell.Y < B.BoardCell.Y : A.BoardCell.X > B.BoardCell.X;
		});
		if (Candidates.Num() > 0) Result.Add(Candidates[0]);
		return Result;
	}
	if (!OnBoard(Anchor)) return Result;
	if (Targets == TEXT("Front1") || Targets == TEXT("SelfAndFront1")) UnitAt(Anchor.BoardCell + FIntPoint(0, -1), Result);
	if (Targets == TEXT("SelfAndBehind1")) UnitAt(Anchor.BoardCell + FIntPoint(0, 1), Result);
	if (Targets == TEXT("Front2"))
	{
		UnitAt(Anchor.BoardCell + FIntPoint(0, -1), Result);
		UnitAt(Anchor.BoardCell + FIntPoint(0, -2), Result);
	}
	if (Targets == TEXT("FrontColumn"))
	{
		for (const FTreadM1UnitInstance& Unit : Player.BoardUnits)
		{
			if (Unit.BoardCell.X == Anchor.BoardCell.X && Unit.BoardCell.Y < Anchor.BoardCell.Y) Result.Add(Unit);
		}
	}
	return Result;
}

TArray<FString> ATreadM1MatchController::SelectPacts(const FTreadM1PlayerState& Player, const FTreadM2Effect& Effect,
	const FTreadM1UnitInstance& TraitOwner, const FTreadM1UnitInstance& Target, const FTreadM1UnitInstance& Anchor)
{
	const auto ActiveOnly = [&](const TArray<FString>& Pacts)
	{
		TArray<FString> Result;
		for (const FString& Pact : Pacts)
		{
			const FTreadM2PactProgress* Progress = FindPactProgress(Player, Pact);
			if (Progress && Progress->bActive) Result.Add(Pact);
		}
		return Result;
	};
	const FString& Selector = Effect.PactSelector;
	if (Selector == TEXT("Pacts")) return Effect.Pacts;
	if (Selector == TEXT("OwnPacts")) return GetUnitPacts(Player, TraitOwner, true);
	if (Selector == TEXT("OwnActivePacts")) return ActiveOnly(GetUnitPacts(Player, TraitOwner, true));
	if (Selector == TEXT("TargetActivePacts")) return ActiveOnly(GetUnitPacts(Player, Target, true));
	if (Selector == TEXT("SourceUnitActivePacts")) return ActiveOnly(GetUnitPacts(Player, Anchor, true));
	TArray<FString> Active;
	for (const FTreadM2PactProgress& Progress : Player.Pacts)
	{
		if (Progress.bActive) Active.Add(Progress.PactId);
	}
	if (Selector == TEXT("AllActivePacts")) return Active;
	if (Selector == TEXT("HighestActivePact"))
	{
		const FTreadM2PactProgress* Best = nullptr;
		for (const FTreadM2PactProgress& Progress : Player.Pacts)
		{
			if (Progress.bActive && (!Best || Progress.Stacks > Best->Stacks)) Best = &Progress;
		}
		return Best ? TArray<FString>{Best->PactId} : TArray<FString>();
	}
	if (Selector == TEXT("RandomActivePact"))
	{
		if (Active.Num() == 0) return Active;
		const FString Pick = Active[RandomStream.RandRange(0, Active.Num() - 1)];
		SyncRandomState();
		return {Pick};
	}
	return {};
}

int32 ATreadM1MatchController::ScaleAmount(const FTreadM1PlayerState& Player, const FTreadM2Effect& Effect,
	const FTreadM1UnitInstance& TraitOwner, const FString& PactId) const
{
	const double Value = IsElite(TraitOwner) ? Effect.EliteValue : Effect.BaseValue;
	double Scale = 1.0;
	const FString& Mode = Effect.AmountScale;
	if (Mode == TEXT("ShopLevel")) Scale = Player.Level;
	else if (Mode == TEXT("AcquiredThisRound")) Scale = Player.AcquiredThisRound;
	else if (Mode == TEXT("BenchCount")) Scale = Player.BenchUnits.Num();
	else if (Mode == TEXT("FundsSpentThisRound")) Scale = Player.FundsSpentThisRound;
	else if (Mode == TEXT("SameRowCount"))
	{
		int32 Row = 0;
		for (const FTreadM1UnitInstance& Unit : Player.BoardUnits) Row += OnBoard(TraitOwner) && Unit.BoardCell.Y == TraitOwner.BoardCell.Y ? 1 : 0;
		Scale = Row;
	}
	else if (Mode == TEXT("DistinctTiersInPact"))
	{
		TSet<FString> Tiers;
		for (const FTreadM1UnitInstance& Unit : Player.BoardUnits)
		{
			if (GetUnitPacts(Player, Unit, false).Contains(PactId)) Tiers.Add(Unit.OperatorTier);
		}
		Scale = Tiers.Num();
	}
	else if (Mode == TEXT("RefreshesThisRound")) Scale = Player.RefreshesThisRound;
	if (Effect.ScaleDivisor > 0) Scale = FMath::FloorToDouble(Scale / Effect.ScaleDivisor);
	int32 Amount = FMath::RoundToInt(Value * Scale);
	const int32 Cap = IsElite(TraitOwner) ? Effect.CapElite : Effect.CapBase;
	if (Cap > 0) Amount = FMath::Min(Amount, Cap);
	return Amount;
}

bool ATreadM1MatchController::TraitConditionMet(const FTreadM1PlayerState& Player, const FTreadM2Trait& Trait, const FTreadM1UnitInstance& TraitOwner) const
{
	const FTreadM2Condition& Condition = Trait.Condition;
	if (Condition.bOddRoundsOnly && MatchState.RoundIndex % 2 == 0) return false;
	if (Trait.Trigger == ETreadM2Trigger::ShopRefresh && Condition.bFirstOnly && Player.RefreshesThisRound != 1) return false;
	if (Condition.SameRowAtLeast > 0 && !(Condition.bEliteIgnoresCondition && IsElite(TraitOwner)))
	{
		if (!OnBoard(TraitOwner)) return false;
		int32 Row = 0;
		for (const FTreadM1UnitInstance& Unit : Player.BoardUnits) Row += Unit.BoardCell.Y == TraitOwner.BoardCell.Y ? 1 : 0;
		if (Row < Condition.SameRowAtLeast) return false;
	}
	return true;
}

void ATreadM1MatchController::ExecuteTrait(FTreadM1PlayerState& Player, const FTreadM2Trait& Trait, const FTreadM1UnitInstance& TraitOwner,
	const FTreadM1UnitInstance& Anchor, ETreadM2Trigger Trigger, const FString& EventName, int32 Depth)
{
	const bool bElite = IsElite(TraitOwner);
	if (!TraitConditionMet(Player, Trait, TraitOwner))
	{
		RecordTraitLog(Player, Trigger, EventName, &TraitOwner, Trait.Id, TEXT("Condition"), FString(), 0, 0, bElite, TEXT("skipped:condition"),
			FString::Printf(TEXT("sameRowAtLeast=%d"), Trait.Condition.SameRowAtLeast));
		return;
	}
	for (const FTreadM2Effect& Effect : Trait.Effects)
	{
		const int32 Value = FMath::RoundToInt(bElite ? Effect.EliteValue : Effect.BaseValue);
		if (Effect.Op == TEXT("AddStacks"))
		{
			const TArray<FTreadM1UnitInstance> Targets = Effect.PactSelector == TEXT("TargetActivePacts")
				? ResolveTargets(Player, TraitOwner, Trait.Targets) : TArray<FTreadM1UnitInstance>{TraitOwner};
			if (Targets.Num() == 0)
			{
				RecordTraitLog(Player, Trigger, EventName, &TraitOwner, Trait.Id, Effect.Op, FString(), 0, 0, bElite, TEXT("skipped:no-target"), Trait.Targets);
			}
			for (const FTreadM1UnitInstance& Target : Targets)
			{
				const TArray<FString> Pacts = SelectPacts(Player, Effect, TraitOwner, Target, Anchor);
				if (Pacts.Num() == 0)
				{
					RecordTraitLog(Player, Trigger, EventName, &TraitOwner, Trait.Id, Effect.Op, FString(), 0, 0, bElite,
						TEXT("skipped:no-pact"), Effect.PactSelector);
				}
				for (const FString& Pact : Pacts)
				{
					AddPactStacks(Player, Pact, ScaleAmount(Player, Effect, TraitOwner, Pact), Trait.bActivationRequired, Trait.Id, &TraitOwner,
						Trigger, EventName, true);
				}
			}
		}
		else if (Effect.Op == TEXT("GainFundsNextRound"))
		{
			Player.PendingTraitIncome += Value;
			RecordTraitLog(Player, Trigger, EventName, &TraitOwner, Trait.Id, Effect.Op, FString(), Value, 0, bElite, TEXT("applied"));
		}
		else if (Effect.Op == TEXT("GainFunds"))
		{
			Player.Funds += Value;
			RecordTraitLog(Player, Trigger, EventName, &TraitOwner, Trait.Id, Effect.Op, FString(), Value, 0, bElite, TEXT("applied"));
		}
		else if (Effect.Op == TEXT("GrantItem"))
		{
			for (int32 Index = 0; Index < Value; ++Index)
			{
				FString Item = Effect.Item;
				if (Item.IsEmpty() && Effect.ItemChoices.Num() > 0)
				{
					Item = Effect.ItemChoices[RandomStream.RandRange(0, Effect.ItemChoices.Num() - 1)];
					SyncRandomState();
				}
				GrantItemToPlayer(Player, Item, 1, Trait.Id, Trigger);
			}
		}
		else if (Effect.Op == TEXT("GrantUnit"))
		{
			if (Depth >= MaxTraitDepth)
			{
				RecordTraitLog(Player, Trigger, EventName, &TraitOwner, Trait.Id, Effect.Op, FString(), 0, 0, bElite, TEXT("skipped:depth"));
				continue;
			}
			for (int32 Index = 0; Index < Value; ++Index)
			{
				TArray<FString> Candidates;
				if (Effect.UnitSelector == TEXT("MostPopulatedPact"))
				{
					const FTreadM2PactProgress* Top = nullptr;
					for (const FTreadM2PactProgress& Progress : Player.Pacts)
					{
						if (Progress.Count > 0 && (!Top || Progress.Count > Top->Count)) Top = &Progress;
					}
					for (const FString& CharacterId : PactData->CardOrder)
					{
						const FTreadM2Card* Card = PactData->FindCard(CharacterId);
						const bool bInPact = Top && Card && (Card->CorePacts.Contains(Top->PactId) || Card->AdjunctPacts.Contains(Top->PactId));
						if (bInPact && CharacterId != TraitOwner.CharacterId) Candidates.Add(CharacterId);
					}
				}
				else if (Effect.UnitSelector == TEXT("TierPool"))
				{
					const int32 Tier = FMath::Clamp(bElite ? Effect.TierElite : Effect.TierBase, 1, 6);
					for (const FString& CharacterId : PactData->CardOrder)
					{
						if (CardTier(CharacterId) == TierNames[Tier - 1]) Candidates.Add(CharacterId);
					}
				}
				else
				{
					for (const FString& Operator : Effect.Operators)
					{
						if (const FString* CharacterId = PactData->OperatorToCharacter.Find(Operator)) Candidates.Add(*CharacterId);
					}
				}
				// Only characters that exist in the shared PoolLedger can be granted without inventing copies.
				Candidates.RemoveAll([this](const FString& CharacterId)
				{
					for (const TCHAR* Tier : TierNames)
					{
						const FTreadM1PoolBalance* Balance = FindPoolBalance(CharacterId, Tier);
						if (Balance && Balance->PoolCopiesAvailable > 0) return false;
					}
					return true;
				});
				if (Candidates.Num() == 0)
				{
					RecordTraitLog(Player, Trigger, EventName, &TraitOwner, Trait.Id, Effect.Op, FString(), 0, 0, bElite,
						TEXT("skipped:no-pool-candidate"), Effect.UnitSelector + TEXT(" ") + FString::Join(Effect.Operators, TEXT(",")));
					break;
				}
				const FString Pick = Candidates[RandomStream.RandRange(0, Candidates.Num() - 1)];
				SyncRandomState();
				GrantUnitToPlayer(Player, Pick, Trait.Id, Trigger, Depth + 1);
			}
		}
		else if (Effect.Op == TEXT("FreeRefresh"))
		{
			Player.FreeRefreshes += Value;
			RecordTraitLog(Player, Trigger, EventName, &TraitOwner, Trait.Id, Effect.Op, FString(), Value, 0, bElite, TEXT("applied"));
		}
		else if (Effect.Op == TEXT("TriggerTraits"))
		{
			if (Depth >= 1)
			{
				RecordTraitLog(Player, Trigger, EventName, &TraitOwner, Trait.Id, Effect.Op, FString(), 0, 0, bElite, TEXT("skipped:nested-trigger"));
				continue;
			}
			const ETreadM2Trigger Filter = FTreadM2PactData::ParseTrigger(Effect.TriggerFilter);
			const TArray<FTreadM1UnitInstance> Targets = ResolveTargets(Player, TraitOwner, Trait.Targets, Effect.TriggerFilter);
			int32 Fired = 0;
			for (const FTreadM1UnitInstance& Target : Targets)
			{
				if (Target.UnitInstanceId == TraitOwner.UnitInstanceId) continue;
				const FTreadM2Card* Card = PactData->FindCard(Target.CharacterId);
				if (!Card) continue;
				for (const FTreadM2Trait& Other : Card->Traits)
				{
					if (Other.Trigger != Filter) continue;
					const bool bTriggersOtherTraits = Other.Effects.ContainsByPredicate([](const FTreadM2Effect& E) { return E.Op == TEXT("TriggerTraits"); });
					if (bTriggersOtherTraits) continue;
					// "anchor=Self" copies the neighbour's trait onto the owner; otherwise the neighbour itself fires.
					const FTreadM1UnitInstance& NewOwner = Effect.Anchor == TEXT("Self") ? TraitOwner : Target;
					RecordTraitLog(Player, Trigger, EventName, &TraitOwner, Trait.Id, Effect.Op, FString(), 1, 0, bElite, TEXT("applied"),
						FString::Printf(TEXT("fires %s as %s"), *Other.Id, *NewOwner.UnitInstanceId));
					ExecuteTrait(Player, Other, NewOwner, NewOwner, Trigger, EventName + TEXT(":Triggered"), Depth + 1);
					++Fired;
				}
			}
			if (Fired == 0)
			{
				RecordTraitLog(Player, Trigger, EventName, &TraitOwner, Trait.Id, Effect.Op, FString(), 0, 0, bElite, TEXT("skipped:no-target"), Trait.Targets);
			}
		}
		else
		{
			// Combat-only (StackScaledStat/FlatStat are read by ComputeUnitCombat) or not yet interpreted ops.
			const bool bCombat = Effect.Op == TEXT("StackScaledStat") || Effect.Op == TEXT("FlatStat");
			RecordTraitLog(Player, Trigger, EventName, &TraitOwner, Trait.Id, Effect.Op, FString(), Value, 0, bElite,
				bCombat ? TEXT("applied:combat-modifier") : TEXT("deferred-M4"), Trait.RuntimeSupport);
		}
	}
}

void ATreadM1MatchController::ApplyPactTierOps(FTreadM1PlayerState& Player, ETreadM2Trigger Trigger, const FString& EventName)
{
	if (!PactData.IsValid()) return;
	// Resolve the active op list first: stack changes must not change which tiers fire this event.
	TArray<TPair<FString, FTreadM2Effect>> Pending;
	for (int32 Index = 0; Index < PactData->Pacts.Num() && Index < Player.Pacts.Num(); ++Index)
	{
		const FTreadM2PactProgress& Progress = Player.Pacts[Index];
		if (!Progress.bActive) continue;
		for (const FTreadM2Effect& Op : PactData->Pacts[Index].TierOps[Progress.ActiveTier - 1])
		{
			if (Op.Trigger == Trigger) Pending.Emplace(Progress.PactId, Op);
		}
	}
	for (const TPair<FString, FTreadM2Effect>& Item : Pending)
	{
		const FString SourceId = TEXT("pact:") + Item.Key;
		if (Item.Value.Op == TEXT("AddStacks"))
		{
			TArray<FString> Active;
			for (const FTreadM2PactProgress& Progress : Player.Pacts) if (Progress.bActive) Active.Add(Progress.PactId);
			for (const FString& Pact : Item.Value.PactSelector == TEXT("Pacts") ? Item.Value.Pacts : Active)
			{
				AddPactStacks(Player, Pact, FMath::RoundToInt(Item.Value.BaseValue), true, SourceId, nullptr, Trigger, EventName, false);
			}
		}
		else
		{
			RecordTraitLog(Player, Trigger, EventName, nullptr, SourceId, Item.Value.Op, Item.Key, 0, 0, false, TEXT("deferred-M4"));
		}
	}
}

void ATreadM1MatchController::DispatchStrategyEffects(FTreadM1PlayerState& Player, ETreadM2Trigger Trigger, const FString& EventName)
{
	const FTreadM2StrategyBus* Bus = PactData.IsValid() ? PactData->FindStrategy(Player.InitialStrategyId) : nullptr;
	if (!Bus) return;
	const bool bScheduled = Trigger == ETreadM2Trigger::RoundStart && Bus->Effects.ContainsByPredicate(
		[](const FTreadM2StrategyEffect& Item) { return Item.bApplied && Item.Effect.OnRound > 0; });
	if (Bus->Trigger != FTreadM2PactData::TriggerName(Trigger) && !bScheduled) return;
	const FString SourceId = TEXT("strategy:") + Bus->StrategyId;
	for (const FTreadM2StrategyEffect& Item : Bus->Effects)
	{
		const FTreadM2Effect& Effect = Item.Effect;
		const int32 Value = FMath::RoundToInt(Effect.BaseValue);
		// MatchStart runs the unscheduled ops; RoundStart runs only the ops scheduled for this round.
		if (Trigger == ETreadM2Trigger::RoundStart && Bus->Trigger != FTreadM2PactData::TriggerName(Trigger) &&
			(!Item.bApplied || Effect.OnRound <= 0)) continue;
		if (Trigger != ETreadM2Trigger::RoundStart && Item.bApplied && Effect.OnRound > 0) continue;
		if (!Item.bApplied)
		{
			RecordTraitLog(Player, Trigger, EventName, nullptr, SourceId, TEXT("Strategy"), FString(), 0, 0, false, TEXT("deferred-M4"), Item.Raw);
			continue;
		}
		const FString OnceKey = SourceId + TEXT(":once");
		if (Effect.bOnce && Player.Flags.Contains(OnceKey))
		{
			RecordTraitLog(Player, Trigger, EventName, nullptr, SourceId, Effect.Op, FString(), 0, 0, false, TEXT("skipped:once"), Item.Raw);
			continue;
		}
		if (Effect.bOnce) Player.Flags.Add(OnceKey);
		if (Effect.OnRound > 0 && MatchState.RoundIndex != Effect.OnRound)
		{
			RecordTraitLog(Player, Trigger, EventName, nullptr, SourceId, Effect.Op, FString(), Value, 0, false, TEXT("skipped:round"),
				FString::Printf(TEXT("round %d: %s"), Effect.OnRound, *Item.Raw));
			continue;
		}
		if (Effect.Op == TEXT("CarryOverFunds") || Effect.Op == TEXT("FirstBuyPrice"))
		{
			Player.Flags.AddUnique(TEXT("flag:") + Effect.Op);
			RecordTraitLog(Player, Trigger, EventName, nullptr, SourceId, Effect.Op, FString::Join(Effect.Pacts, TEXT(",")), Value, 0, false, TEXT("applied"), Item.Raw);
		}
		else if (Effect.Op == TEXT("GrantItem"))
		{
			GrantItemToPlayer(Player, Effect.Item, FMath::Max(1, Value), SourceId, Trigger);
		}
		else if (Effect.Op == TEXT("GainFunds"))
		{
			Player.Funds += Value;
			RecordTraitLog(Player, Trigger, EventName, nullptr, SourceId, Effect.Op, FString(), Value, 0, false, TEXT("applied"), Item.Raw);
		}
		else if (Effect.Op == TEXT("AddStacks"))
		{
			TArray<FString> Targets = Effect.Pacts;
			int32 Amount = Value;
			if (Effect.PactSelector == TEXT("AllActivePacts"))
			{
				Targets.Reset();
				for (const FTreadM2PactProgress& Progress : Player.Pacts) if (Progress.bActive) Targets.Add(Progress.PactId);
				// Band 余: a single active pact gets the larger amount.
				if (Targets.Num() == 1 && Effect.SingleActiveAmount > 0.0) Amount = FMath::RoundToInt(Effect.SingleActiveAmount);
			}
			else if (Effect.PactSelector == TEXT("RandomUnitPerTierPacts"))
			{
				// Band 华法琳: one random board unit of each distinct tier gives its own active pacts the stacks.
				Targets.Reset();
				TMap<FString, TArray<const FTreadM1UnitInstance*>> ByTier;
				for (const FTreadM1UnitInstance& Unit : Player.BoardUnits) ByTier.FindOrAdd(Unit.OperatorTier).Add(&Unit);
				TArray<FString> Tiers;
				ByTier.GetKeys(Tiers);
				Tiers.Sort();
				for (const FString& Tier : Tiers)
				{
					const TArray<const FTreadM1UnitInstance*>& Units = ByTier[Tier];
					const FTreadM1UnitInstance* Pick = Units[RandomStream.RandRange(0, Units.Num() - 1)];
					SyncRandomState();
					for (const FString& Pact : GetUnitPacts(Player, *Pick, true))
					{
						const FTreadM2PactProgress* Progress = FindPactProgress(Player, Pact);
						if (Progress && Progress->bActive) Targets.Add(Pact);
					}
				}
			}
			if (Targets.Num() == 0)
			{
				RecordTraitLog(Player, Trigger, EventName, nullptr, SourceId, Effect.Op, FString(), 0, 0, false, TEXT("skipped:no-pact"), Item.Raw);
			}
			for (const FString& Pact : Targets)
			{
				AddPactStacks(Player, Pact, Amount, false, SourceId, nullptr, Trigger, EventName, false);
			}
		}
		else if (Effect.Op == TEXT("PactThresholdDelta") || Effect.Op == TEXT("PactCountsBench"))
		{
			for (const FString& Pact : Effect.Pacts)
			{
				const bool bExists = Player.PactModifiers.ContainsByPredicate([&](const FTreadM2PactModifier& Modifier)
				{
					return Modifier.PactId == Pact && Modifier.SourceStrategyId == Bus->StrategyId;
				});
				if (!bExists)
				{
					FTreadM2PactModifier& Modifier = Player.PactModifiers.AddDefaulted_GetRef();
					Modifier.PactId = Pact;
					Modifier.SourceStrategyId = Bus->StrategyId;
					Modifier.ThresholdDelta = Effect.Op == TEXT("PactThresholdDelta") ? Value : 0;
					Modifier.bCountsBench = Effect.Op == TEXT("PactCountsBench");
				}
				RecordTraitLog(Player, Trigger, EventName, nullptr, SourceId, Effect.Op, Pact, Value, 0, false,
					bExists ? TEXT("skipped:already-applied") : TEXT("applied"), Item.Raw);
			}
			RecomputePacts(Player);
		}
		else
		{
			RecordTraitLog(Player, Trigger, EventName, nullptr, SourceId, Effect.Op, FString(), Value, 0, false, TEXT("deferred-M4"), Item.Raw);
		}
	}
}

void ATreadM1MatchController::DispatchTraitEvent(FTreadM1PlayerState& Player, ETreadM2Trigger Trigger, const FString& EventName,
	const FTreadM1UnitInstance* Subject, int32 Depth)
{
	if (!PactData.IsValid() || !PactData->bLoaded || Player.bIsEliminated) return;
	RecordTraitLog(Player, Trigger, EventName, Subject, TEXT("bus"), TEXT("Event"), FString(), 0, 0, Subject && IsElite(*Subject), TEXT("event"));
	if (Subject && (Trigger == ETreadM2Trigger::Acquire || Trigger == ETreadM2Trigger::Sell))
	{
		const FTreadM1UnitInstance Unit = *Subject;
		if (const FTreadM2Card* Card = PactData->FindCard(Unit.CharacterId))
		{
			const int32 Repeat = Trigger == ETreadM2Trigger::Acquire ? AcquireRepeatCount(Player) : 1;
			for (const FTreadM2Trait& Trait : Card->Traits)
			{
				if (Trait.Trigger != Trigger) continue;
				for (int32 Index = 0; Index < Trait.RepeatCount * Repeat; ++Index)
				{
					ExecuteTrait(Player, Trait, Unit, Unit, Trigger, EventName, Depth);
				}
			}
		}
	}
	else if (Trigger == ETreadM2Trigger::RoundStart || Trigger == ETreadM2Trigger::RoundEnd)
	{
		// Board traits fire in board order; bench traits only when the trait allows it.
		TArray<FTreadM1UnitInstance> Owners = Player.BoardUnits;
		Owners.Sort([](const FTreadM1UnitInstance& A, const FTreadM1UnitInstance& B)
		{
			return A.BoardCell.Y != B.BoardCell.Y ? A.BoardCell.Y < B.BoardCell.Y : A.BoardCell.X < B.BoardCell.X;
		});
		Owners.Append(Player.BenchUnits);
		for (const FTreadM1UnitInstance& Unit : Owners)
		{
			const FTreadM2Card* Card = PactData->FindCard(Unit.CharacterId);
			if (!Card) continue;
			for (const FTreadM2Trait& Trait : Card->Traits)
			{
				if (Trait.Trigger != Trigger) continue;
				bool bBenchOk = Trait.bWorksOnBench;
				for (const FString& Pact : Trait.Condition.BenchIfAnyActive)
				{
					const FTreadM2PactProgress* Progress = FindPactProgress(Player, Pact);
					bBenchOk |= Progress && Progress->bActive;
				}
				if (!OnBoard(Unit) && !bBenchOk) continue;
				for (int32 Index = 0; Index < Trait.RepeatCount; ++Index)
				{
					ExecuteTrait(Player, Trait, Unit, Unit, Trigger, EventName, Depth);
				}
			}
		}
		ApplyPactTierOps(Player, Trigger, EventName);
	}
	else if (Trigger == ETreadM2Trigger::ShopRefresh)
	{
		TArray<FTreadM1UnitInstance> Owners = Player.BoardUnits;
		Owners.Append(Player.BenchUnits);
		for (const FTreadM1UnitInstance& Unit : Owners)
		{
			const FTreadM2Card* Card = PactData->FindCard(Unit.CharacterId);
			if (!Card) continue;
			for (const FTreadM2Trait& Trait : Card->Traits)
			{
				if (Trait.Trigger == Trigger && (OnBoard(Unit) || Trait.bWorksOnBench)) ExecuteTrait(Player, Trait, Unit, Unit, Trigger, EventName, Depth);
			}
		}
	}
	else if (Trigger == ETreadM2Trigger::BattleStart)
	{
		for (const FTreadM1UnitInstance& Unit : TArray<FTreadM1UnitInstance>(Player.BoardUnits))
		{
			const FTreadM2Card* Card = PactData->FindCard(Unit.CharacterId);
			if (!Card) continue;
			for (const FTreadM2Trait& Trait : Card->Traits)
			{
				if (Trait.Trigger == ETreadM2Trigger::Battle && Trait.Condition.Event == TEXT("BattleStart"))
				{
					ExecuteTrait(Player, Trait, Unit, Unit, Trigger, EventName, Depth);
				}
			}
		}
	}
	DispatchStrategyEffects(Player, Trigger, EventName);
}

void ATreadM1MatchController::DispatchRoundTrigger(ETreadM2Trigger Trigger, const FString& EventName)
{
	for (FTreadM1PlayerState& Player : MatchState.Players)
	{
		if (Player.bIsEliminated) continue;
		RecomputePacts(Player);
		DispatchTraitEvent(Player, Trigger, EventName);
	}
}

void ATreadM1MatchController::GrantItemToPlayer(FTreadM1PlayerState& Player, const FString& ItemName, int32 Count,
	const FString& SourceId, ETreadM2Trigger Trigger)
{
	if (!PactData.IsValid()) return;
	for (int32 Index = 0; Index < Count; ++Index)
	{
		const FTreadM2Item* Item = PactData->FindItem(ItemName);
		if (Item && Item->EffectStatus == TEXT("placeholder"))
		{
			// A "random equipment" marker resolves to one concrete seed item.
			TArray<const FTreadM2Item*> Concrete;
			for (const FTreadM2Item& Candidate : PactData->Items)
			{
				if (Candidate.EffectStatus != TEXT("placeholder")) Concrete.Add(&Candidate);
			}
			Item = Concrete.Num() > 0 ? Concrete[RandomStream.RandRange(0, Concrete.Num() - 1)] : nullptr;
			SyncRandomState();
		}
		if (!Item)
		{
			RecordTraitLog(Player, Trigger, TEXT("GrantItem"), nullptr, SourceId, TEXT("GrantItem"), FString(), 0, 0, false,
				TEXT("skipped:unknown-item"), ItemName);
			continue;
		}
		Player.EquipmentIds.Add(Item->ItemId);
		RecordTraitLog(Player, Trigger, TEXT("GrantItem"), nullptr, SourceId, TEXT("GrantItem"), FString::Join(Item->ProvidesPacts, TEXT(",")),
			1, 0, false, TEXT("applied"), Item->DisplayName);
	}
}

FTreadM1UnitInstance* ATreadM1MatchController::FindOwnedUnit(FTreadM1PlayerState& Player, const FString& UnitInstanceId)
{
	if (FTreadM1UnitInstance* Unit = Player.BenchUnits.FindByPredicate([&](const FTreadM1UnitInstance& U) { return U.UnitInstanceId == UnitInstanceId; }))
	{
		return Unit;
	}
	return Player.BoardUnits.FindByPredicate([&](const FTreadM1UnitInstance& U) { return U.UnitInstanceId == UnitInstanceId; });
}

bool ATreadM1MatchController::GrantUnitToPlayer(FTreadM1PlayerState& Player, const FString& CharacterId, const FString& SourceId,
	ETreadM2Trigger Trigger, int32 Depth)
{
	if (Player.BenchUnits.Num() >= MatchState.Rules.MaxBenchSlots)
	{
		RecordTraitLog(Player, Trigger, TEXT("GrantUnit"), nullptr, SourceId, TEXT("GrantUnit"), FString(), 0, 0, false, TEXT("skipped:bench-full"), CharacterId);
		return false;
	}
	TArray<int32> TierOrder = {0, 1, 2, 3, 4, 5};
	const FString BoundTier = CardTier(CharacterId);
	if (!BoundTier.IsEmpty())
	{
		TierOrder.Reset();
		for (int32 Index = 0; Index < UE_ARRAY_COUNT(TierNames); ++Index) if (BoundTier == TierNames[Index]) TierOrder.Add(Index);
	}
	for (int32 Index = TierOrder.Num() - 1; Index > 0; --Index) TierOrder.Swap(Index, RandomStream.RandRange(0, Index));
	SyncRandomState();
	for (const int32 TierIndex : TierOrder)
	{
		FTreadM1ShopSlot Slot;
		Slot.CharacterId = CharacterId;
		Slot.OperatorTier = TierNames[TierIndex];
		Slot.Cost = TierPrice(Slot.OperatorTier);
		const FTreadM1PoolBalance* Balance = FindPoolBalance(CharacterId, Slot.OperatorTier);
		if (!Balance || Balance->PoolCopiesAvailable <= 0) continue;
		if (!RecordPoolLedger(TEXT("Reserve"), Player.PlayerId, Slot, -1)) continue;
		if (!RecordPoolLedger(TEXT("Purchase"), Player.PlayerId, Slot, -1)) return false;
		FTreadM1UnitInstance Unit;
		Unit.UnitInstanceId = FString::Printf(TEXT("%s_unit_%04d"), *Player.PlayerId, ++UnitInstanceSequence);
		Unit.CharacterId = CharacterId;
		Unit.OperatorTier = Slot.OperatorTier;
		Unit.OriginalOperatorName = CharacterId;
		Unit.Cost = Slot.Cost;
		Unit.OwnerPlayerId = Player.PlayerId;
		Unit.Location = ETreadM1UnitLocation::Bench;
		Player.BenchUnits.Add(Unit);
		const int32 EmptyIndex = Player.BenchUnitInstanceIds.Find(FString());
		if (EmptyIndex != INDEX_NONE) Player.BenchUnitInstanceIds[EmptyIndex] = Unit.UnitInstanceId;
		else Player.BenchUnitInstanceIds.Add(Unit.UnitInstanceId);
		++Player.AcquiredThisRound;
		RecordTraitLog(Player, Trigger, TEXT("GrantUnit"), &Unit, SourceId, TEXT("GrantUnit"), FString(), 1, 0, false, TEXT("applied"));
		HandleUnitAcquired(Player, Unit.UnitInstanceId, TEXT("Grant"), Depth);
		return true;
	}
	RecordTraitLog(Player, Trigger, TEXT("GrantUnit"), nullptr, SourceId, TEXT("GrantUnit"), FString(), 0, 0, false, TEXT("skipped:pool-empty"), CharacterId);
	return false;
}

void ATreadM1MatchController::HandleUnitAcquired(FTreadM1PlayerState& Player, const FString& UnitInstanceId, const FString& EventName, int32 Depth)
{
	const FTreadM1UnitInstance* Found = FindOwnedUnit(Player, UnitInstanceId);
	if (!Found) return;
	const FTreadM1UnitInstance Unit = *Found;
	// 6_03: acquiring an operator pays funds, capped per round.
	if (PactData.IsValid())
	{
		for (const FTreadM1UnitInstance& BoardUnit : Player.BoardUnits)
		{
			for (const FString& ItemId : BoardUnit.EquipmentIds)
			{
				const FTreadM2Item* Item = PactData->FindItem(ItemId);
				if (!Item) continue;
				for (const FTreadM2ItemProc& Proc : Item->Procs)
				{
					if (Proc.Op != TEXT("FundsPerAcquire")) continue;
					const int32 Cap = FMath::Max(1, Proc.Max);
					if (Player.AcquireFundsCount >= Cap) continue;
					++Player.AcquireFundsCount;
					const int32 Paid = FMath::Max(1, FMath::RoundToInt(Proc.Value));
					Player.Funds += Paid;
					RecordTraitLog(Player, ETreadM2Trigger::Acquire, TEXT("FundsPerAcquire"), &BoardUnit, ItemId,
						Proc.Op, FString(), Paid, 0, IsElite(BoardUnit), TEXT("applied"));
				}
			}
		}
	}
	RecomputePacts(Player);
	DispatchTraitEvent(Player, ETreadM2Trigger::Acquire, EventName, &Unit, Depth);
	TryAutoCombine(Player, Unit.CharacterId, Unit.OperatorTier, Depth);
	RecomputePacts(Player);
}

bool ATreadM1MatchController::TryAutoCombine(FTreadM1PlayerState& Player, const FString& CharacterId, const FString& OperatorTier, int32 Depth)
{
	if (!PactData.IsValid()) return false;
	const FTreadM2Card* Card = PactData->FindCard(CharacterId);
	const int32 Needed = Card ? Card->CombineCopies : 3;
	for (int32 Star = 1; Star < 3; ++Star)
	{
		TArray<FTreadM1UnitInstance> Parts;
		for (const FTreadM1UnitInstance& Unit : Player.BoardUnits)
			if (Unit.CharacterId == CharacterId && Unit.OperatorTier == OperatorTier && Unit.UnitStar == Star) Parts.Add(Unit);
		for (const FTreadM1UnitInstance& Unit : Player.BenchUnits)
			if (Unit.CharacterId == CharacterId && Unit.OperatorTier == OperatorTier && Unit.UnitStar == Star) Parts.Add(Unit);
		if (Parts.Num() < Needed) continue;
		// Keep a normal (non-clone) instance, preferring one already on the board.
		Parts.StableSort([](const FTreadM1UnitInstance& A, const FTreadM1UnitInstance& B)
		{
			if (A.bIsTransformClone != B.bIsTransformClone) return !A.bIsTransformClone;
			return (A.Location == ETreadM1UnitLocation::Board) && (B.Location != ETreadM1UnitLocation::Board);
		});
		Parts.SetNum(Needed);
		FTreadM1UnitInstance Result = Parts[0];
		int32 Copies = 0;
		TArray<FString> Equipment;
		for (const FTreadM1UnitInstance& Part : Parts)
		{
			Copies += Part.PoolCopiesHeld;
			Equipment.Append(Part.EquipmentIds);
		}
		for (int32 Index = 1; Index < Parts.Num(); ++Index)
		{
			const FTreadM1UnitInstance& Part = Parts[Index];
			const int32 BoardIndex = Player.BoardUnits.IndexOfByPredicate([&](const FTreadM1UnitInstance& U) { return U.UnitInstanceId == Part.UnitInstanceId; });
			if (BoardIndex != INDEX_NONE)
			{
				Player.BoardUnits.RemoveAt(BoardIndex);
				Player.PopulationUsed = FMath::Max(0, Player.PopulationUsed - 1);
			}
			else
			{
				Player.BenchUnits.RemoveAll([&](const FTreadM1UnitInstance& U) { return U.UnitInstanceId == Part.UnitInstanceId; });
				const int32 Slot = Player.BenchUnitInstanceIds.Find(Part.UnitInstanceId);
				if (Slot != INDEX_NONE) Player.BenchUnitInstanceIds[Slot].Empty();
				// Clones occupy population even on the bench.
				if (Part.bIsTransformClone) Player.PopulationUsed = FMath::Max(0, Player.PopulationUsed - 1);
			}
			AppendPoolLedgerEntry(TEXT("Combine"), Player.PlayerId, Part.CharacterId, Part.OperatorTier, Part.UnitInstanceId,
				Part.CloneInstanceId, Part.CopySourceCharacterId, 0);
		}
		FTreadM1UnitInstance* Kept = FindOwnedUnit(Player, Result.UnitInstanceId);
		if (!Kept) return false;
		Kept->UnitStar = Star + 1;
		Kept->PoolCopiesHeld = Copies;
		Kept->EquipmentIds.Reset();
		for (const FString& ItemId : Equipment)
		{
			if (Kept->EquipmentIds.Num() < 3) Kept->EquipmentIds.Add(ItemId);
			else Player.EquipmentIds.Add(ItemId);
		}
		const FTreadM1UnitInstance Combined = *Kept;
		AppendPoolLedgerEntry(TEXT("Combine"), Player.PlayerId, Combined.CharacterId, Combined.OperatorTier, Combined.UnitInstanceId,
			Combined.CloneInstanceId, Combined.CopySourceCharacterId, 0);
		RecomputePacts(Player);
		RecordTraitLog(Player, ETreadM2Trigger::Combine, TEXT("Combine"), &Combined, TEXT("combine"), TEXT("Combine"), FString(), Needed, 0,
			IsElite(Combined), TEXT("applied"), FString::Printf(TEXT("star %d -> %d, poolCopiesHeld=%d"), Star, Star + 1, Copies));
		DispatchTraitEvent(Player, ETreadM2Trigger::Combine, TEXT("Combine"), &Combined, Depth);
		if (Depth < MaxTraitDepth)
		{
			HandleUnitAcquired(Player, Combined.UnitInstanceId, TEXT("CombineResult"), Depth + 1);
		}
		return true;
	}
	return false;
}

FTreadM2UnitCombat ATreadM1MatchController::ComputeUnitCombat(const FTreadM1PlayerState& Player, const FTreadM1UnitInstance& Unit) const
{
	FTreadM2UnitCombat Combat;
	if (!PactData.IsValid() || !PactData->bLoaded) return Combat;
	TMap<FString, float> Stat;
	const TArray<FString> UnitPacts = GetUnitPacts(Player, Unit, true);
	for (int32 Index = 0; Index < PactData->Pacts.Num() && Index < Player.Pacts.Num(); ++Index)
	{
		const FTreadM2PactDef& Def = PactData->Pacts[Index];
		const FTreadM2PactProgress& Progress = Player.Pacts[Index];
		if (!Progress.bActive) continue;
		const bool bApplies = Def.CombatScope == TEXT("AllUnits") || UnitPacts.Contains(Def.PactId);
		if (bApplies)
		{
			for (const FTreadM2CombatStat& PerStack : Def.CombatPerStack)
			{
				Stat.FindOrAdd(PerStack.Stat) += FMath::Min(1.0f, static_cast<float>(PerStack.PerStack * Progress.Stacks));
			}
			for (const FTreadM2CombatStat& Base : Def.BaseStats)
			{
				Stat.FindOrAdd(Base.Stat) += static_cast<float>(Base.PerStack);
			}
		}
		for (const FTreadM2Effect& Op : Def.TierOps[Progress.ActiveTier - 1])
		{
			if (Op.Op == TEXT("CombatFlat")) Stat.FindOrAdd(Op.Stat) += static_cast<float>(Op.BaseValue);
		}
	}
	if (const FTreadM2Card* Card = PactData->FindCard(Unit.CharacterId))
	{
		for (const FTreadM2Trait& Trait : Card->Traits)
		{
			if (Trait.Trigger != ETreadM2Trigger::Passive) continue;
			for (const FTreadM2Effect& Effect : Trait.Effects)
			{
				const float Value = static_cast<float>(IsElite(Unit) ? Effect.EliteValue : Effect.BaseValue);
				if (Effect.Op == TEXT("FlatStat"))
				{
					Stat.FindOrAdd(Effect.Stat) += Effect.Stat == TEXT("SkillRegen") ? Value : Value / 100.0f;
				}
				else if (Effect.Op == TEXT("StackScaledStat") && Effect.PerStacks > 0)
				{
					int32 Stacks = 0;
					const TArray<FString> Source = Effect.PactSelector == TEXT("OwnCorePacts") ? UnitPacts : Effect.Pacts;
					for (const FString& Pact : Source)
					{
						const FTreadM2PactProgress* Progress = FindPactProgress(Player, Pact);
						const FTreadM2PactDef* Def = PactData->FindPact(Pact);
						if (Progress && Def && (Effect.PactSelector != TEXT("OwnCorePacts") || Def->Kind == TEXT("Core"))) Stacks += Progress->Stacks;
					}
					Stat.FindOrAdd(Effect.Stat) += FMath::Min(1.0f, (Stacks / Effect.PerStacks) * Value / 100.0f);
				}
			}
		}
	}
	// M4: equipment stat bonuses (ItemCatalog.json "combat"; the Ⅱ version is its own item id).
	for (const FString& ItemId : Unit.EquipmentIds)
	{
		if (const FTreadM2Item* Item = PactData->FindItem(ItemId))
		{
			for (const TPair<FString, float>& Bonus : Item->Combat) Stat.FindOrAdd(Bonus.Key) += Bonus.Value;
		}
	}
	const float AttackHealth = Stat.FindRef(TEXT("AttackHealth"));
	Combat.AttackMul = FMath::Clamp(1.0f + Stat.FindRef(TEXT("Attack")) + Stat.FindRef(TEXT("Damage")) + AttackHealth +
		0.5f * Stat.FindRef(TEXT("AttackSpeed")), 0.5f, 4.0f);
	Combat.HealthMul = FMath::Clamp(1.0f + Stat.FindRef(TEXT("Health")) + AttackHealth, 0.5f, 4.0f);
	Combat.DamageTaken = 1.0f - FMath::Clamp(0.5f * Stat.FindRef(TEXT("Defense")) + Stat.FindRef(TEXT("DamageReduction")), 0.0f, 0.6f);
	Combat.SkillEvery = FMath::Max(1, PactData->SkillEveryAttacks - (Stat.FindRef(TEXT("SkillRegen")) >= 0.25f ? 1 : 0));
	return Combat;
}

void ATreadM1MatchController::ResetBattleMeters()
{
	BattleSp.Reset();
	BattleAmmo.Reset();
	BattleAmmoSpent.Reset();
	BattleUnitHealth.Reset();
	BattleUnitSpMax.Reset();
	// document/175: proc runtime is per battle too.
	BattleAttackSpeedStacks.Reset();
	BattleSkillAtkStacks.Reset();
	BattleSilenceUntil.Reset();
	BattleSkillBuffUntil.Reset();
	BattleExchangeIndex = 0;
}

void ATreadM1MatchController::ResetBattleTraitState()
{
	BattleTraitCounters.Reset();
	ActiveBattleCapRemaining = nullptr;
}

void ATreadM1MatchController::HandleBattleAttack(FTreadM1PlayerState& Player, const FTreadM1UnitInstance& Unit, int32& AttackCount,
	const FTreadM2UnitCombat& Combat, const FString& TargetPlayerId, const FString& TargetUnitId)
{
	if (!PactData.IsValid() || !PactData->bLoaded) return;
	// document/175: 3_08 silence removes the unit's special abilities (SP, ammo, skill) for its window.
	if (BattleSilenceUntil.FindRef(Unit.UnitInstanceId) > BattleExchangeIndex) return;
	++AttackCount;
	const FTreadM2Card* Card = PactData->FindCard(Unit.CharacterId);
	// 拉特兰 (document/168): a ranged unit spends rounds from its magazine; an empty magazine falls back to a plain
	// shot. The magazine starts loaded and is refilled by every skill cast below.
	int32& Magazine = BattleAmmo.FindOrAdd(Unit.UnitInstanceId);
	if (Magazine <= 0 && AttackCount <= 1)
	{
		Magazine = FMath::Max(1, PactData->AmmoPerAttack * 6);
	}
	if (Card && Card->bConsumesAmmo)
	{
		// The event stream stays exactly as before (the deterministic M1 baseline depends on it); the magazine only
		// decides whether this round counts towards the 拉特兰 attack bonus.
		for (int32 Ammo = 0; Ammo < PactData->AmmoPerAttack; ++Ammo)
		{
			if (Magazine > 0)
			{
				--Magazine;
				++BattleAmmoSpent.FindOrAdd(Unit.UnitInstanceId);
			}
			RecordBattleEvent(ETreadM1BattleEventType::AmmoConsumed, Player.PlayerId, TargetPlayerId, 1, Unit.UnitInstanceId, TargetUnitId);
			OnBattleUnitEvent(Player, TEXT("AmmoConsumed"), Unit);
		}
	}
	// 技力 (document/167): every attack carries SP; the skill fires when the unit can pay for it. The default is
	// deliberately the old cadence - SpMax 100 and SpPerAttack 100 / SkillEvery put the first cast on the same attack
	// as before, so the deterministic self-tests keep their numbers.
	const TArray<FString> UnitPactsSp = GetUnitPacts(Player, Unit, false);
	float SpMax = 100.0f;
	int32 SpGain = FMath::Max(1, FMath::RoundToInt(100.0f / FMath::Max(1, Combat.SkillEvery)));
	int32 SpInitial = 0;
	for (const FString& Pact : UnitPactsSp)
	{
		const FTreadM2PactProgress* Progress = FindPactProgress(Player, Pact);
		const FTreadM2PactDef* Def = PactData->FindPact(Pact);
		if (!Progress || !Def || !Progress->bActive)
		{
			continue;
		}
		// 绝技 tier 2 (5 elite units) lowers the skill cost.
		if (Def->SpCostRatio > 0.0f && Def->SpCostRatio < 1.0f && Progress->ActiveTier >= 2)
		{
			SpMax *= Def->SpCostRatio;
		}
		// 迅捷: a share of attacks grants extra SP.
		if (Def->SpPerAttack > 0 && Def->SpChance > 0.0f)
		{
			if (RandomStream.FRand() < Def->SpChance)
			{
				// 精锐 units get the elite number from bonds.json (迅捷 power_sp instead of normal_sp).
				const bool bElite = Unit.UnitStar >= PactData->EliteStarAtLeast;
				SpGain += (bElite && Def->SpElitePerAttack > 0) ? Def->SpElitePerAttack : Def->SpPerAttack;
			}
		}
		SpInitial = FMath::Max(SpInitial, Def->SpInitial);
	}
	float& Sp = BattleSp.FindOrAdd(Unit.UnitInstanceId);
	if (Sp <= 0.0f && SpInitial > 0)
	{
		Sp = static_cast<float>(SpInitial);
	}
	Sp += static_cast<float>(SpGain);
	bool bCastSkill = false;
	while (Sp >= SpMax)
	{
		Sp -= SpMax;
		bCastSkill = true;
	}
	if (bCastSkill)
	{
		// 拉特兰: every skill reloads the magazine (the pact raises how much).
		int32 Reload = PactData->AmmoPerAttack * 3;
		for (const FString& Pact : UnitPactsSp)
		{
			const FTreadM2PactProgress* Progress = FindPactProgress(Player, Pact);
			const FTreadM2PactDef* Def = PactData->FindPact(Pact);
			if (Progress && Def && Progress->bActive && Def->AmmoPerSkill > 0)
			{
				Reload = FMath::RoundToInt(Def->AmmoPerSkill * (1.0f + Def->AmmoGrantBonus
					+ 0.015f * static_cast<float>(Progress->Stacks)));
				break;
			}
		}
		BattleAmmo.FindOrAdd(Unit.UnitInstanceId) += FMath::Max(0, Reload);
		BattleUnitSpMax.Add(Unit.UnitInstanceId, SpMax);
		RecordBattleEvent(ETreadM1BattleEventType::SkillActivated, Player.PlayerId, TargetPlayerId, 0, Unit.UnitInstanceId, TargetUnitId);
		OnBattleUnitEvent(Player, TEXT("SkillActivated"), Unit);
		// 3_04: every skill use adds one capped attack stack (document/175).
		const FTreadM2UnitProcs SkillProcs = ComputeUnitProcs(Player, Unit);
		if (SkillProcs.AttackPerSkill > 0.0f)
		{
			int32& SkillStacks = BattleSkillAtkStacks.FindOrAdd(Unit.UnitInstanceId);
			SkillStacks = FMath::Min(SkillStacks + 1, FMath::Max(1, SkillProcs.AttackPerSkillMax));
		}
		// 6_10: the skill opens a 20 s attack window.
		if (SkillProcs.SkillBuffValue > 0.0f)
		{
			BattleSkillBuffUntil.FindOrAdd(Unit.UnitInstanceId) =
				BattleExchangeIndex + FMath::Max(1, FMath::CeilToInt(SkillProcs.SkillBuffDuration));
		}
		const TArray<FString> UnitPacts = GetUnitPacts(Player, Unit, false);
		for (const FTreadM2PactDef& Def : PactData->Pacts)
		{
			if (Def.bSkillAppliesFreeze && UnitPacts.Contains(Def.PactId))
			{
				RecordBattleEvent(ETreadM1BattleEventType::EnemyFrozen, Player.PlayerId, TargetPlayerId, 0, Unit.UnitInstanceId, TargetUnitId);
				OnBattleUnitEvent(Player, TEXT("EnemyFrozen"), Unit);
				break;
			}
		}
	}
}


bool ATreadM1MatchController::TryMiracleFreeRefresh(FTreadM1PlayerState& Player)
{
	if (!PactData.IsValid())
	{
		return false;
	}
	const FTreadM2PactProgress* Mira = FindPactProgress(Player, TEXT("奇迹"));
	const FTreadM2PactDef* MiraDef = PactData->FindPact(TEXT("奇迹"));
	if (!Mira || !MiraDef || !Mira->bActive)
	{
		return false;
	}
	const float Chance = MiraDef->Params.FindRef(TEXT("baseprob")) + MiraDef->Params.FindRef(TEXT("prob")) * Mira->Stacks;
	if (RandomStream.FRand() < FMath::Clamp(Chance, 0.0f, 1.0f))
	{
		Player.FreeRefreshes += 1;
		return true;
	}
	return false;
}

bool ATreadM1MatchController::TryPactRevive(FTreadM1PlayerState& Player, const FTreadM1UnitInstance& Unit, int32& Health)
{
	if (!PactData.IsValid() || Health > 0)
	{
		return false;
	}
	if (BattleRevivedUnits.Contains(Unit.UnitInstanceId))
	{
		return false;
	}
	const TArray<FString> UnitPacts = GetUnitPacts(Player, Unit, false);
	// 阿戈尔 [5]: the first three 阿戈尔 units get one revive each, no roll.
	if (UnitPacts.Contains(TEXT("阿戈尔")))
	{
		const FTreadM2PactProgress* Agir = FindPactProgress(Player, TEXT("阿戈尔"));
		const FTreadM2PactDef* AgirDef = PactData->FindPact(TEXT("阿戈尔"));
		const int32 Budget = AgirDef ? static_cast<int32>(AgirDef->Params.FindRef(TEXT("max_free_respawn_cnt"))) : 3;
		if (Agir && Agir->bActive && Agir->Count >= 5 && BattleAgirRevives < FMath::Max(1, Budget))
		{
			++BattleAgirRevives;
			BattleRevivedUnits.Add(Unit.UnitInstanceId);
			Health = FMath::Max(2, FMath::RoundToInt(40.0f));
			return true;
		}
	}
	// 不屈: a ground unit gets back up with a chance that grows with the pact's stacks.
	const FTreadM2PactProgress* Indom = FindPactProgress(Player, TEXT("不屈"));
	const FTreadM2PactDef* IndomDef = PactData->FindPact(TEXT("不屈"));
	if (Indom && IndomDef && Indom->bActive)
	{
		const float Chance = IndomDef->Params.FindRef(TEXT("base_prob")) + IndomDef->Params.FindRef(TEXT("prob_per_stack")) * Indom->Stacks;
		if (RandomStream.FRand() < FMath::Clamp(Chance, 0.0f, 1.0f))
		{
			BattleRevivedUnits.Add(Unit.UnitInstanceId);
			Health = FMath::Max(2, FMath::RoundToInt(35.0f));
			return true;
		}
	}
	return false;
}

void ATreadM1MatchController::PactOnKnockDown(FTreadM1PlayerState& Player)
{
	const FTreadM2PactProgress* Indom = FindPactProgress(Player, TEXT("不屈"));
	const FTreadM2PactDef* IndomDef = PactData->FindPact(TEXT("不屈"));
	if (!Indom || !IndomDef || !Indom->bActive || Indom->Count < 3)
	{
		return;
	}
	const float Amount = IndomDef->Params.FindRef(TEXT("sp"));
	for (const FTreadM1UnitInstance& Unit : Player.BoardUnits)
	{
		BattleSp.FindOrAdd(Unit.UnitInstanceId) += Amount;
	}
}

void ATreadM1MatchController::ApplyAgirDevour(FTreadM1PlayerState& Player, TArray<int32>& Health, TArray<FTreadM2UnitCombat>& Combat)
{
	if (!PactData.IsValid())
	{
		return;
	}
	const FTreadM2PactProgress* Agir = FindPactProgress(Player, TEXT("阿戈尔"));
	if (!Agir || !Agir->bActive || Agir->Count < 3)
	{
		return;
	}
	// 阿戈尔 that stand further left (and then further up) devour first, per the bond text.
	TArray<int32> Order;
	for (int32 Index = 0; Index < Player.BoardUnits.Num(); ++Index)
	{
		if (GetUnitPacts(Player, Player.BoardUnits[Index], false).Contains(TEXT("阿戈尔")))
		{
			Order.Add(Index);
		}
	}
	Order.StableSort([&Player](int32 A, int32 B)
	{
		const FIntPoint CA = Player.BoardUnits[A].BoardCell;
		const FIntPoint CB = Player.BoardUnits[B].BoardCell;
		return CA.X != CB.X ? CA.X < CB.X : CA.Y < CB.Y;
	});

	TSet<int32> Devoured;
	for (const int32 Index : Order)
	{
		const FIntPoint Front(Player.BoardUnits[Index].BoardCell.X + 1, Player.BoardUnits[Index].BoardCell.Y);
		int32 Victim = INDEX_NONE;
		for (int32 Candidate = 0; Candidate < Player.BoardUnits.Num(); ++Candidate)
		{
			if (Candidate == Index || Devoured.Contains(Candidate)) continue;
			if (Health.IsValidIndex(Candidate) && Health[Candidate] <= 0) continue;
			if (Player.BoardUnits[Candidate].BoardCell == Front) { Victim = Candidate; break; }
		}
		if (Victim == INDEX_NONE || !Health.IsValidIndex(Victim) || !Combat.IsValidIndex(Index))
		{
			continue;
		}
		Devoured.Add(Victim);
		// The swallow is a pact trigger, not a removal: the teammate is bitten for a third of its health and stays in the
		// battle (the pact's revive brings it straight back if the bite would have taken it down). The 阿戈尔 still
		// absorbs the attack and part of what it bit off.
		const float VictimHealth = static_cast<float>(Health[Victim]);
		const int32 VictimCost = Player.BoardUnits[Victim].Cost;
		const int32 Bite = FMath::Max(1, FMath::RoundToInt(VictimHealth * 0.34f));
		int32 VictimLeft = Health[Victim] - Bite;
		if (VictimLeft <= 0)
		{
			// The swallow would take the teammate down: that is the trigger the pact's in-place revive exists for.
			// With the revive budget spent the teammate really falls - it starts the battle at 0 and sits it out.
			VictimLeft = 0;
			TryPactRevive(Player, Player.BoardUnits[Victim], VictimLeft);
		}
		Health[Victim] = VictimLeft;
		Combat[Index].AttackMul = FMath::Clamp(Combat[Index].AttackMul * (1.0f + 0.2f * VictimCost), 0.5f, 6.0f);
		if (Health.IsValidIndex(Index))
		{
			Health[Index] += FMath::Max(1, FMath::RoundToInt(Bite * 0.5f));
		}
		// Layers equal to the devoured unit's tier (I..VI -> 1..6).
		const FString Tier = CardTier(Player.BoardUnits[Victim].CharacterId);
		const int32 TierIndex = Tier == TEXT("I") ? 1 : Tier == TEXT("II") ? 2 : Tier == TEXT("III") ? 3
			: Tier == TEXT("IV") ? 4 : Tier == TEXT("V") ? 5 : Tier == TEXT("VI") ? 6 : 1;
		AddPactStacks(Player, TEXT("阿戈尔"), TierIndex, false, TEXT("AgirDevour"),
			&Player.BoardUnits[Index], ETreadM2Trigger::BattleStart, TEXT("AgirDevour"), false);
	}
}

void ATreadM1MatchController::ApplyYanSummon(FTreadM1PlayerState& Player, TArray<int32>& Health, TArray<FTreadM2UnitCombat>& Combat)
{
	if (!PactData.IsValid())
	{
		return;
	}
	const FTreadM2PactProgress* Yan = FindPactProgress(Player, TEXT("炎"));
	const FTreadM2PactDef* YanDef = PactData->FindPact(TEXT("炎"));
	if (!Yan || !YanDef || !Yan->bActive || Yan->Count < 6)
	{
		return;
	}
	// The summon is a copy of the team's highest-star 炎 unit, carrying 30% of the team's 炎 attack/health totals; at
	// 9 members there are two of them, stronger and heavily damage-resistant (bonds.json `ex_bond_char_cnt`).
	const FTreadM1UnitInstance* Best = nullptr;
	int32 SumAtk = 0;
	int32 SumHp = 0;
	for (int32 Index = 0; Index < Player.BoardUnits.Num(); ++Index)
	{
		const FTreadM1UnitInstance& Unit = Player.BoardUnits[Index];
		if (!GetUnitPacts(Player, Unit, false).Contains(TEXT("炎")))
		{
			continue;
		}
		if (!Best || Unit.UnitStar > Best->UnitStar) Best = &Unit;
		SumAtk += Unit.Cost * Unit.UnitStar;
		SumHp += Health.IsValidIndex(Index) ? Health[Index] : 0;
	}
	if (!Best)
	{
		return;
	}
	const int32 EliteMembers = static_cast<int32>(YanDef->Params.FindRef(TEXT("ex_bond_char_cnt")));
	const bool bElite = Yan->Count >= FMath::Max(6, EliteMembers);
	const int32 Count = bElite ? 2 : 1;
	const float AtkMul = bElite ? FMath::Max(1.0f, YanDef->Params.FindRef(TEXT("atk"))) : 1.0f;
	for (int32 Summon = 0; Summon < Count; ++Summon)
	{
		FTreadM1UnitInstance Copy = *Best;
		Copy.UnitInstanceId = FString::Printf(TEXT("SUMMON_yan_%d"), ++BattleSummonSerial);
		Copy.BoardCell = FIntPoint(FMath::Clamp(2 + Summon, 0, 7), 1);
		Player.BoardUnits.Add(Copy);
		Health.Add(FMath::Max(2, FMath::RoundToInt(SumHp * 0.3f / FMath::Max(1, Count))));
		FTreadM2UnitCombat SummonCombat = ComputeUnitCombat(Player, Copy);
		SummonCombat.AttackMul *= AtkMul * 0.3f;
		if (bElite)
		{
			SummonCombat.DamageTaken *= 0.1f;
		}
		Combat.Add(SummonCombat);
	}
}

void ATreadM1MatchController::StripSummons(FTreadM1PlayerState& Player)
{
	Player.BoardUnits.RemoveAll([](const FTreadM1UnitInstance& Unit)
	{
		return Unit.UnitInstanceId.StartsWith(TEXT("SUMMON_"));
	});
}

void ATreadM1MatchController::HandleBattleExchange(float Seconds)
{
	if (!PactData.IsValid() || Seconds <= 0.0f)
	{
		return;
	}
	// 技力 trickle (document/168): every unit that carries SP recovers a little each battle second, so long fights
	// cast more often even without 迅捷.
	if (PactData->SpRegenPerSecond > 0.0f)
	{
		for (TPair<FString, float>& Pair : BattleSp)
		{
			Pair.Value += PactData->SpRegenPerSecond * Seconds;
		}
	}
	for (const FTreadM1PlayerState& Player : MatchState.Players)
	{
		for (const FTreadM1UnitInstance& Unit : Player.BoardUnits)
		{
			if (!BattleUnitSpMax.Contains(Unit.UnitInstanceId))
			{
				BattleUnitSpMax.Add(Unit.UnitInstanceId, 100.0f);
			}
		}
	}
}

float ATreadM1MatchController::GetUnitHealthFraction(const FString& PlayerId, const FString& UnitInstanceId) const
{
	return BattleUnitHealth.FindRef(UnitInstanceId);
}

float ATreadM1MatchController::GetUnitSpFraction(const FString& PlayerId, const FString& UnitInstanceId) const
{
	const float SpMax = FMath::Max(1.0f, BattleUnitSpMax.FindRef(UnitInstanceId));
	const float Sp = BattleSp.FindRef(UnitInstanceId);
	return FMath::Clamp(Sp / SpMax, 0.0f, 1.0f);
}

float ATreadM1MatchController::GetUnitAmmoMultiplier(const FString& PlayerId, const FString& UnitInstanceId) const
{
	const FTreadM1PlayerState* Player = FindPlayer(PlayerId);
	if (!Player)
	{
		return 1.0f;
	}
	for (const FTreadM1UnitInstance& Unit : Player->BoardUnits)
	{
		if (Unit.UnitInstanceId == UnitInstanceId)
		{
			return AmmoAttackMultiplier(*Player, Unit);
		}
	}
	return 1.0f;
}

int32 ATreadM1MatchController::GetForesightBenchCount(const FString& PlayerId) const
{
	const FTreadM1PlayerState* Player = FindPlayer(PlayerId);
	if (!Player || !PactData.IsValid())
	{
		return 0;
	}
	int32 Count = 0;
	for (const FTreadM1UnitInstance& Unit : Player->BenchUnits)
	{
		if (GetUnitPacts(*Player, Unit, false).Contains(TEXT("远见")))
		{
			++Count;
		}
	}
	return Count;
}

int32 ATreadM1MatchController::GetUnitAmmo(const FString& PlayerId, const FString& UnitInstanceId) const
{
	return BattleAmmo.FindRef(UnitInstanceId);
}

void ATreadM1MatchController::OnBattleUnitEvent(FTreadM1PlayerState& Player, const FString& EventName, const FTreadM1UnitInstance& Actor)
{
	if (!PactData.IsValid() || !PactData->bLoaded) return;
	for (const FTreadM1UnitInstance& TraitOwner : TArray<FTreadM1UnitInstance>(Player.BoardUnits))
	{
		const FTreadM2Card* Card = PactData->FindCard(TraitOwner.CharacterId);
		if (!Card) continue;
		for (const FTreadM2Trait& Trait : Card->Traits)
		{
			const FTreadM2Condition& Condition = Trait.Condition;
			if (Trait.Trigger != ETreadM2Trigger::Battle || Condition.Event != EventName) continue;
			bool bSource = false;
			if (Condition.Source == TEXT("Self")) bSource = Actor.UnitInstanceId == TraitOwner.UnitInstanceId;
			else if (Condition.Source == TEXT("Front1")) bSource = OnBoard(TraitOwner) && Actor.BoardCell == TraitOwner.BoardCell + FIntPoint(0, -1);
			else if (Condition.Source == TEXT("Around4"))
			{
				const FIntPoint D = Actor.BoardCell - TraitOwner.BoardCell;
				bSource = OnBoard(TraitOwner) && FMath::Abs(D.X) + FMath::Abs(D.Y) == 1;
			}
			else if (Condition.Source == TEXT("FrontColumn"))
			{
				const int32 Range = IsElite(TraitOwner) ? Condition.RangeElite : Condition.RangeBase;
				bSource = OnBoard(TraitOwner) && Actor.BoardCell.X == TraitOwner.BoardCell.X && Actor.BoardCell.Y < TraitOwner.BoardCell.Y &&
					Actor.BoardCell.Y >= TraitOwner.BoardCell.Y - Range;
			}
			if (!bSource) continue;
			const FString Key = TraitOwner.UnitInstanceId + TEXT("|") + Trait.Id;
			if (Condition.Every > 0)
			{
				int32& Count = BattleTraitCounters.FindOrAdd(Key + TEXT("|count"));
				if (++Count % Condition.Every != 0) continue;
			}
			if (Condition.bFirstOnly)
			{
				int32& Fired = BattleTraitCounters.FindOrAdd(Key + TEXT("|first"));
				if (Fired++ > 0) continue;
			}
			if (Condition.MaxTimes > 0)
			{
				int32& Times = BattleTraitCounters.FindOrAdd(Key + TEXT("|times"));
				if (Times++ >= Condition.MaxTimes) continue;
			}
			const int32 Chance = IsElite(TraitOwner) ? Condition.ChanceElite : Condition.ChanceBase;
			if (Chance < 100)
			{
				const int32 Roll = RandomStream.RandRange(1, 100);
				SyncRandomState();
				if (Roll > Chance)
				{
					RecordTraitLog(Player, ETreadM2Trigger::Battle, EventName, &TraitOwner, Trait.Id, TEXT("Chance"), FString(), Roll, 0,
						IsElite(TraitOwner), TEXT("skipped:chance"), FString::Printf(TEXT("roll=%d chance=%d"), Roll, Chance));
					continue;
				}
			}
			int32* Cap = nullptr;
			if (Condition.PerBattleCap > 0)
			{
				Cap = &BattleTraitCounters.FindOrAdd(Key + TEXT("|cap"), Condition.PerBattleCap);
			}
			ActiveBattleCapRemaining = Cap;
			ExecuteTrait(Player, Trait, TraitOwner, Actor, ETreadM2Trigger::Battle, EventName, 0);
			ActiveBattleCapRemaining = nullptr;
		}
	}
}

void ATreadM1MatchController::SnapshotBattlePactStates()
{
	MatchState.BattlePactStates.Reset();
	for (const FTreadM1PlayerState& Player : MatchState.Players)
	{
		if (Player.bIsEliminated) continue;
		FTreadM2BattlePactState& State = MatchState.BattlePactStates.AddDefaulted_GetRef();
		State.PlayerId = Player.PlayerId;
		State.RoundIndex = MatchState.RoundIndex;
		State.Pacts = Player.Pacts;
	}
}

FTreadM1CommandResult ATreadM1MatchController::EquipItem(const FString& PlayerId, const FString& ItemId,
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
	const FTreadM2Item* Item = PactData.IsValid() ? PactData->FindItem(ItemId) : nullptr;
	const int32 InventoryIndex = Item ? Player->EquipmentIds.Find(Item->ItemId) : INDEX_NONE;
	if (InventoryIndex == INDEX_NONE)
	{
		return Reject(ETreadM1RejectReason::ItemUnavailable, RequestId);
	}
	FTreadM1UnitInstance* Unit = FindOwnedUnit(*Player, UnitInstanceId);
	if (!Unit)
	{
		return Reject(ETreadM1RejectReason::NotOwnUnit, RequestId);
	}
	if (Item->bSpell)
	{
		// M4 special items (StrategyItems.json) are used on a unit, not worn.  画卷 copies the unit (elite state
		// and equipment included) as a transform clone, which never draws from the shared pool; the bounty
		// spells need a bounty system Tread does not have and stay disabled.
		if (Item->ItemId != TEXT("chess_item_6_02_m"))
		{
			RecordTraitLog(*Player, ETreadM2Trigger::Equip, TEXT("UseSpell"), Unit, Item->ItemId, TEXT("UseSpell"), FString(), 0, 0,
				IsElite(*Unit), TEXT("deferred:") + Item->SupportNote, Item->DisplayName);
			return Reject(ETreadM1RejectReason::ItemUnavailable, RequestId);
		}
		const FTreadM1UnitInstance Source = *Unit;
		Player->EquipmentIds.RemoveAt(InventoryIndex);
		const FTreadM1CommandResult Cloned = CreateTransformCloneInternal(PlayerId, Source, FString());
		if (!Cloned.bAccepted)
		{
			if (FTreadM1PlayerState* OwnerState = FindPlayer(PlayerId)) OwnerState->EquipmentIds.Add(Item->ItemId);
			return Reject(Cloned.ReasonCode, RequestId);
		}
		if (FTreadM1PlayerState* OwnerState = FindPlayer(PlayerId))
		{
			RecordTraitLog(*OwnerState, ETreadM2Trigger::Equip, TEXT("UseSpell"), &Source, Item->ItemId, TEXT("CopyUnit"), FString(), 1, 0,
				IsElite(Source), TEXT("applied"), Item->DisplayName);
		}
		RefreshScoutSnapshots();
		OnStateChanged.Broadcast();
		return Accept(RequestId);
	}
	if (Unit->EquipmentIds.Num() >= 3)
	{
		return Reject(ETreadM1RejectReason::EquipmentFull, RequestId);
	}
	Player->EquipmentIds.RemoveAt(InventoryIndex);
	Unit->EquipmentIds.Add(Item->ItemId);
	if (Item->bConsumedOnEquip)
	{
		// M4: "装备时销毁" items run their op and leave the unit's slot free again.
		Unit->EquipmentIds.RemoveSingle(Item->ItemId);
		ApplyItemOnEquip(*Player, *Unit, *Item);
		Unit = FindOwnedUnit(*Player, UnitInstanceId);
		if (!Unit)
		{
			RecomputePacts(*Player);
			RefreshScoutSnapshots();
			OnStateChanged.Broadcast();
			return Accept(RequestId);
		}
	}
	const FTreadM1UnitInstance Equipped = *Unit;
	RecomputePacts(*Player);
	RecordTraitLog(*Player, ETreadM2Trigger::Equip, TEXT("Equip"), &Equipped, Item->ItemId, TEXT("Equip"),
		FString::Join(Item->ProvidesPacts, TEXT(",")), 1, 0, IsElite(Equipped), TEXT("applied"), Item->DisplayName);
	DispatchTraitEvent(*Player, ETreadM2Trigger::Equip, TEXT("Equip"), &Equipped);
	RefreshScoutSnapshots();
	OnStateChanged.Broadcast();
	return Accept(RequestId);
}

TArray<FTreadM2PactProgress> ATreadM1MatchController::GetPactProgress(const FString& PlayerId) const
{
	const FTreadM1PlayerState* Player = FindPlayer(PlayerId);
	return Player ? Player->Pacts : TArray<FTreadM2PactProgress>();
}

TArray<FString> ATreadM1MatchController::GetCardPacts(const FString& CharacterId) const
{
	TArray<FString> Result;
	if (const FTreadM2Card* Card = PactData.IsValid() ? PactData->FindCard(CharacterId) : nullptr)
	{
		Result = Card->CorePacts;
		Result.Append(Card->AdjunctPacts);
	}
	return Result;
}

FString ATreadM1MatchController::GetTraitValueText(const FString& CharacterId, int32 UnitStar) const
{
	const FTreadM2Card* Card = PactData.IsValid() ? PactData->FindCard(CharacterId) : nullptr;
	if (!Card || Card->Traits.Num() == 0) return FString();
	for (const FTreadM2Effect& Effect : Card->Traits[0].Effects)
	{
		if (Effect.Op == TEXT("PurchaseCostOverride") || Effect.Op == TEXT("CombineCopies") || Effect.Op == TEXT("TriggerTraits")) continue;
		const FString Base = FString::SanitizeFloat(Effect.BaseValue, 0);
		const FString Elite = FString::SanitizeFloat(Effect.EliteValue, 0);
		const bool bElite = UnitStar >= PactData->EliteStarAtLeast;
		return bElite ? FString::Printf(TEXT("%s/[%s]"), *Base, *Elite) : FString::Printf(TEXT("[%s]/%s"), *Base, *Elite);
	}
	return FString();
}

FString ATreadM1MatchController::GetTraitSummary(const FString& CharacterId) const
{
	const FTreadM2Card* Card = PactData.IsValid() ? PactData->FindCard(CharacterId) : nullptr;
	return Card && Card->Traits.Num() > 0 ? Card->Traits[0].DisplayText : FString();
}

FString ATreadM1MatchController::GetCardDisplayName(const FString& CharacterId) const
{
	const FTreadM2Card* Card = PactData.IsValid() ? PactData->FindCard(CharacterId) : nullptr;
	return Card && !Card->ReferenceOperatorName.IsEmpty() ? Card->ReferenceOperatorName : CharacterId;
}

FString ATreadM1MatchController::GetCardModelName(const FString& CharacterId) const
{
	const FTreadM2Card* Card = FindCardData(CharacterId);
	return Card ? Card->ModelName : FString();
}

FString ATreadM1MatchController::GetCardAvatarPath(const FString& CharacterId) const
{
	const FTreadM2Card* Card = FindCardData(CharacterId);
	return Card ? Card->AvatarAsset : FString();
}

FString ATreadM1MatchController::GetCardPortraitPath(const FString& CharacterId) const
{
	const FTreadM2Card* Card = FindCardData(CharacterId);
	return Card ? Card->PortraitAsset : FString();
}

TArray<FString> ATreadM1MatchController::GetRosterCharacterIds() const
{
	return PactData.IsValid() ? PactData->CardOrder : TArray<FString>();
}

FString ATreadM1MatchController::GetSfxAssetPath(const FString& Key) const
{
	const FString* Path = PactData.IsValid() ? PactData->SfxAssets.Find(Key) : nullptr;
	return Path ? *Path : FString();
}

FString ATreadM1MatchController::GetBgmAssetPath(const FString& Key) const
{
	const FString* Path = PactData.IsValid() ? PactData->BgmAssets.Find(Key) : nullptr;
	return Path ? *Path : FString();
}

int32 ATreadM1MatchController::GetShopUpgradeCost(const FString& PlayerId) const
{
	const FTreadM1PlayerState* Player = FindPlayer(PlayerId);
	return Player ? ShopUpgradeCost(*Player) : 0;
}

int32 ATreadM1MatchController::EachRoundFundsBonus(const FTreadM1PlayerState& Player) const
{
	int32 Total = 0;
	for (const FString& Flag : Player.Flags)
	{
		FString Amount;
		if (Flag.Split(TEXT("item:EachRoundFunds:"), nullptr, &Amount)) Total += FCString::Atoi(*Amount);
	}
	return Total;
}

void ATreadM1MatchController::ApplyItemOnEquip(FTreadM1PlayerState& Player, FTreadM1UnitInstance& Unit, const FTreadM2Item& Item)
{
	const FString Op = Item.OnEquipOp;
	FString Status = TEXT("applied");
	int32 Amount = Item.OnEquipValue;
	if (Op == TEXT("GainFundsRandom"))
	{
		Amount = RandomStream.RandRange(Item.OnEquipValue, FMath::Max(Item.OnEquipValue, Item.OnEquipMax));
		SyncRandomState();
		Player.Funds += Amount;
	}
	else if (Op == TEXT("GainFundsNextRound"))
	{
		Player.PendingTraitIncome += Amount;
	}
	else if (Op == TEXT("GainFundsEachRound"))
	{
		// Paid with every settlement from now on (EachRoundFundsBonus), starting with the coming one.
		Player.Flags.Add(FString::Printf(TEXT("item:EachRoundFunds:%d"), Amount));
		Player.PendingTraitIncome += Amount;
	}
	else if (Op == TEXT("AddOwnPactStacks"))
	{
		for (const FString& Pact : GetCardPacts(Unit.CharacterId))
		{
			AddPactStacks(Player, Pact, Amount, false, Item.ItemId, &Unit, ETreadM2Trigger::Equip, TEXT("ItemPactStacks"), false);
		}
	}
	else if (Op == TEXT("SetPopulationLimit"))
	{
		Player.PopulationLimit = FMath::Max(Player.PopulationLimit, Amount);
	}
	else if (Op == TEXT("PromoteElite"))
	{
		Unit.UnitStar = FMath::Max(Unit.UnitStar, PactData.IsValid() ? PactData->EliteStarAtLeast : 2);
	}
	else if (Op == TEXT("RecruitFromShop") || Op == TEXT("RecruitSamePact") || Op == TEXT("RecruitSameOperator"))
	{
		TArray<FString> Candidates;
		if (Op == TEXT("RecruitFromShop"))
		{
			for (const FTreadM1ShopSlot& Slot : Player.Shop.Slots) if (!Slot.bIsSold) Candidates.Add(Slot.CharacterId);
		}
		else
		{
			int32 Owned = 0;
			for (const FTreadM1UnitInstance& Other : Player.BenchUnits) Owned += Other.CharacterId == Unit.CharacterId ? 1 : 0;
			for (const FTreadM1UnitInstance& Other : Player.BoardUnits) Owned += Other.CharacterId == Unit.CharacterId ? 1 : 0;
			if (Op == TEXT("RecruitSameOperator") && Owned >= 2)
			{
				Candidates.Add(Unit.CharacterId);
			}
			else if (PactData.IsValid())
			{
				const TArray<FString> UnitPacts = GetCardPacts(Unit.CharacterId);
				for (const FString& CardId : PactData->CardOrder)
				{
					if (CardId == Unit.CharacterId) continue;
					for (const FString& Pact : GetCardPacts(CardId))
					{
						if (UnitPacts.Contains(Pact)) { Candidates.Add(CardId); break; }
					}
				}
			}
		}
		int32 Granted = 0;
		for (int32 Copy = 0; Copy < FMath::Max(1, Amount) && Candidates.Num() > 0; ++Copy)
		{
			const int32 Pick = RandomStream.RandRange(0, Candidates.Num() - 1);
			SyncRandomState();
			Granted += GrantUnitToPlayer(Player, Candidates[Pick], Item.ItemId, ETreadM2Trigger::Equip, 0) ? 1 : 0;
		}
		Amount = Granted;
		if (Granted == 0) Status = TEXT("skipped:no-candidate-or-bench-full");
	}
	else if (Item.Procs.ContainsByPredicate([](const FTreadM2ItemProc& Proc)
		{ return Proc.Op == TEXT("RecruitPactUnit") || Proc.Op == TEXT("RecruitSameTierUnit"); }))
	{
		// document/178: 4_01 / 5_04 special recruit (the runtime grants one candidate instead of a 3-way pick).
		GrantRecruitFromItem(Player, Unit, Item);
		Amount = 1;
	}
	else
	{
		Status = TEXT("deferred:") + Item.SupportNote;
	}
	RecordTraitLog(Player, ETreadM2Trigger::Equip, TEXT("ItemOnEquip"), &Unit, Item.ItemId, Op, FString(), Amount, 0,
		IsElite(Unit), Status, Item.DisplayName);
}

FString ATreadM1MatchController::GetItemDisplayName(const FString& ItemId) const
{
	const FTreadM2Item* Item = PactData.IsValid() ? PactData->FindItem(ItemId) : nullptr;
	return Item ? Item->DisplayName : ItemId;
}

bool ATreadM1MatchController::StockShopSlotForFixture(FTreadM1PlayerState& Player, int32 SlotIndex, const FString& CharacterId, const FString& Tier)
{
	// N1: a card has exactly one bound tier; fixtures may address slots beyond the level's shop size.
	const FString BoundTier = CardTier(CharacterId);
	const FString UseTier = BoundTier.IsEmpty() ? Tier : BoundTier;
	while (HasN1Economy() && SlotIndex >= Player.Shop.Slots.Num() && SlotIndex < 8)
	{
		FTreadM1ShopSlot Extra;
		Extra.SlotIndex = Player.Shop.Slots.Num();
		Extra.bIsSold = true;
		Player.Shop.Slots.Add(Extra);
	}
	if (!Player.Shop.Slots.IsValidIndex(SlotIndex)) return false;
	FTreadM1ShopSlot& Slot = Player.Shop.Slots[SlotIndex];
	if (!Slot.bIsSold && !Slot.CharacterId.IsEmpty()) RecordPoolLedger(TEXT("RefreshReturn"), Player.PlayerId, Slot, 1);
	Slot.CharacterId = CharacterId;
	Slot.OperatorTier = UseTier;
	Slot.Cost = PurchaseCostFor(CharacterId, HasN1Economy() ? TierPrice(UseTier) : 1);
	Slot.bIsSold = !RecordPoolLedger(TEXT("Reserve"), Player.PlayerId, Slot, -1);
	return !Slot.bIsSold;
}

void ATreadM1MatchController::BuildM2Showcase(const FString& Stage)
{
	if (!IsPactDataLoaded()) return;
	BeginPreMatchBP(TEXT("m2cap-bp"));
	ChoosePlayerStrategy(MatchState.BP.AvailableStrategyIds[0], TEXT("m2cap-player"));
	for (int32 Pick = 0; Pick < 3; ++Pick) RunNextAIPick(FString::Printf(TEXT("m2cap-ai-%d"), Pick));
	ConfirmPreMatchBP(TEXT("m2cap-confirm"));
	FTreadM1PlayerState* P0 = FindPlayer(TEXT("P0"));
	if (!P0) return;
	// Showcase funds are a capture fixture; every roster change below uses the normal commands.
	P0->Funds = 80;
	while (P0->BoardUnits.Num() > 0) SellUnit(TEXT("P0"), P0->BoardUnits[0].UnitInstanceId, FString());
	while (P0->BenchUnits.Num() > 0) SellUnit(TEXT("P0"), P0->BenchUnits[0].UnitInstanceId, FString());
	for (int32 Index = 0; Index < 6; ++Index) BuyExperience(TEXT("P0"), FString::Printf(TEXT("m2cap-xp-%d"), Index));

	// Pick showcase cards by data: the first purchasable card of a core pact with three members,
	// a no-activation acquire-stacker to demonstrate a three-copy combine, and two members of an adjunct pact.
	const auto ShopRange = [](const FString& Id) { return FCString::Atoi(*Id.RightChop(5)) <= 32; };
	TArray<FString> Core;
	FString CorePact;
	for (const FTreadM2PactDef& Def : PactData->Pacts)
	{
		if (Def.Kind != TEXT("Core")) continue;
		Core.Reset();
		for (const FString& Id : PactData->CardOrder)
		{
			const FTreadM2Card& Card = PactData->Cards[Id];
			if (ShopRange(Id) && Card.CorePacts.Contains(Def.PactId) && Card.Traits[0].Trigger != ETreadM2Trigger::Acquire) Core.Add(Id);
		}
		if (Core.Num() >= 3) { CorePact = Def.PactId; break; }
	}
	FString Stacker;
	for (const FString& Id : PactData->CardOrder)
	{
		const FTreadM2Trait& Trait = PactData->Cards[Id].Traits[0];
		if (ShopRange(Id) && Trait.Trigger == ETreadM2Trigger::Acquire && !Trait.bActivationRequired &&
			PactData->Cards[Id].AdjunctPacts.Num() > 0 && Trait.Effects[0].PactSelector == TEXT("OwnPacts")) { Stacker = Id; break; }
	}
	const FString StackerAdjunct = Stacker.IsEmpty() ? FString() : PactData->Cards[Stacker].AdjunctPacts[0];
	FString AdjunctPartner;
	for (const FString& Id : PactData->CardOrder)
	{
		const FTreadM2Card& Card = PactData->Cards[Id];
		if (ShopRange(Id) && Id != Stacker && Card.AdjunctPacts.Contains(StackerAdjunct) && !Core.Contains(Id)) { AdjunctPartner = Id; break; }
	}
	TArray<FString> Buys;
	for (int32 Index = 0; Index < 3 && Index < Core.Num(); ++Index) Buys.Add(Core[Index]);
	Buys.Add(Stacker); Buys.Add(Stacker); Buys.Add(Stacker);
	Buys.Add(AdjunctPartner);
	int32 Request = 0;
	for (const FString& Id : Buys)
	{
		if (Id.IsEmpty()) continue;
		StockShopSlotForFixture(*P0, 0, Id, TEXT("I"));
		PurchaseShopSlot(TEXT("P0"), 0, FString::Printf(TEXT("m2cap-buy-%d"), Request++));
	}
	// Deploy everything that fits, front row first.
	int32 Cell = 0;
	for (const FTreadM1UnitInstance& Unit : TArray<FTreadM1UnitInstance>(P0->BenchUnits))
	{
		if (MoveUnitToBoard(TEXT("P0"), Unit.UnitInstanceId, FIntPoint(2 + Cell % 5, 6 - Cell / 5), FString::Printf(TEXT("m2cap-deploy-%d"), Cell)).bAccepted) ++Cell;
	}
	// Equipment-provided pact on the first board unit.
	if (const FTreadM2Item* Item = PactData->Items.FindByPredicate([](const FTreadM2Item& I) { return I.ProvidesPacts.Num() > 0; }))
	{
		GrantItemToPlayer(*P0, Item->DisplayName, 1, TEXT("m2-showcase"), ETreadM2Trigger::Passive);
		if (P0->BoardUnits.Num() > 0) EquipItem(TEXT("P0"), Item->ItemId, P0->BoardUnits.Last().UnitInstanceId, TEXT("m2cap-equip"));
	}
	for (FTreadM1PlayerState& Player : MatchState.Players) Player.Health = FMath::Max(Player.Health, 60);
	// One full round so RoundEnd, battle and settlement stacks/funds are visible in R2 preparation.
	DeployAndStartBattle(TEXT("m2cap-r1-deploy"));
	if (Stage == TEXT("BATTLE"))
	{
		MatchState.PhaseTimeRemainingSec = 300.0f;
		return;
	}
	ResolveBattle(TEXT("m2cap-r1-resolve"));
	AdvanceToNextRound(TEXT("m2cap-r2"));
	MatchState.PhaseTimeRemainingSec = 300.0f;
	if (Stage == TEXT("BATTLE2"))
	{
		DeployAndStartBattle(TEXT("m2cap-r2-deploy"));
		MatchState.PhaseTimeRemainingSec = 300.0f;
	}
	UE_LOG(LogTemp, Display, TEXT("Tread M2 showcase %s: core=%s stacker=%s partner=%s board=%d bench=%d log=%d"), *Stage, *CorePact, *Stacker,
		*AdjunctPartner, P0->BoardUnits.Num(), P0->BenchUnits.Num(), MatchState.TraitLog.Num());
	OnStateChanged.Broadcast();
}

bool ATreadM1MatchController::StockBoardForFixture(const FString& PlayerId, const TArray<FString>& CharacterIds)
{
	FTreadM1PlayerState* Player = FindPlayer(PlayerId);
	if (!Player || MatchState.Phase != ETreadM1Phase::Preparation)
	{
		return false;
	}
	// The check wants a board the shop could never hand out in one round, so the population limit is
	// lifted the same way BuildM2Showcase lifts funds. Everything else stays on the normal path: the
	// units are reserved out of the pool and deployed with the command the drag UI uses.
	Player->PopulationLimit = FMath::Max(Player->PopulationLimit, CharacterIds.Num());
	while (Player->BoardUnits.Num() > 0) SellUnit(PlayerId, Player->BoardUnits[0].UnitInstanceId, FString());
	while (Player->BenchUnits.Num() > 0) SellUnit(PlayerId, Player->BenchUnits[0].UnitInstanceId, FString());

	int32 Deployed = 0;
	for (const FString& CharacterId : CharacterIds)
	{
		const FIntPoint Cell(Deployed % 8, 4 + Deployed / 8);
		if (Cell.Y > 7) break;
		// One at a time: the bench only holds Rules.MaxBenchSlots, the board is what the check needs.
		if (!GrantUnitToPlayer(*Player, CharacterId, TEXT("n2-board-check"), ETreadM2Trigger::Passive, 0)) continue;
		if (Player->BenchUnits.Num() == 0) continue;
		if (MoveUnitToBoard(PlayerId, Player->BenchUnits.Last().UnitInstanceId, Cell, FString()).bAccepted)
		{
			++Deployed;
		}
	}
	OnStateChanged.Broadcast();
	UE_LOG(LogTemp, Display, TEXT("Tread N2 board check fixture: %d/%d units deployed for %s"), Deployed, CharacterIds.Num(), *PlayerId);
	return Deployed > 0;
}

void ATreadM1MatchController::RequestM2Screenshot(const FString& Name)
{
	const FString Path = FPaths::ConvertRelativePathToFull(FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("Screenshots"), Name + TEXT(".png")));
	FScreenshotRequest::RequestScreenshot(Path, true, false, false, FIntRect(), true);
	UE_LOG(LogTemp, Display, TEXT("Tread M2 screenshot requested: %s"), *Path);
	FTimerHandle ExitTimer;
	GetWorldTimerManager().SetTimer(ExitTimer, FTimerDelegate::CreateLambda([]() { FPlatformMisc::RequestExit(false); }), 3.0f, false);
}
