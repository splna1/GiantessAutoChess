"""Replayable source patch (N1): Stronghold-Protocol economy helpers and new trait ops in TreadM2PactRuntime.cpp.
Every anchor must match exactly once; re-running on a patched file stops with "already patched"."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
p = ROOT / "Source/Tread/TreadM2PactRuntime.cpp"
s = p.read_text(encoding="utf-8")
if "DrawShopCard" in s:
    raise SystemExit("already patched")


def dedent1(text):
    return "\n".join(line[1:] if line.startswith("\t") else line for line in text.split("\n"))


def rep(old, new):
    """Replace one exact anchor; falls back to the same block one tab shallower (anchors were written by eye)."""
    global s
    for _ in range(3):
        if s.count(old) == 1:
            s = s.replace(old, new)
            return
        old, new = dedent1(old), dedent1(new)
    raise AssertionError(old[:120])


rep('''FTreadM2PactProgress* ATreadM1MatchController::FindPactProgress(FTreadM1PlayerState& Player, const FString& PactId)
{''', '''bool ATreadM1MatchController::HasN1Economy() const
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
{''')

# 绝技: every elite unit on the board counts as a member.
rep('''		for (const FTreadM1UnitInstance& Unit : Player.BoardUnits)
		{
			if (GetUnitPacts(Player, Unit, false).Contains(Def.PactId))
			{
				BoardMembers.Add(Unit.CharacterId);''', '''		for (const FTreadM1UnitInstance& Unit : Player.BoardUnits)
		{
			if (GetUnitPacts(Player, Unit, false).Contains(Def.PactId) || (Def.bCountsEliteAll && IsElite(Unit)))
			{
				BoardMembers.Add(Unit.CharacterId);''')

# Scales: refreshes this round, integer divisor, per-trait cap.
rep('''		Scale = Tiers.Num();
	}
	return FMath::RoundToInt(Value * Scale);''', '''		Scale = Tiers.Num();
	}
	else if (Mode == TEXT("RefreshesThisRound")) Scale = Player.RefreshesThisRound;
	if (Effect.ScaleDivisor > 0) Scale = FMath::FloorToDouble(Scale / Effect.ScaleDivisor);
	int32 Amount = FMath::RoundToInt(Value * Scale);
	const int32 Cap = IsElite(TraitOwner) ? Effect.CapElite : Effect.CapBase;
	if (Cap > 0) Amount = FMath::Min(Amount, Cap);
	return Amount;''')

# Conditions: odd rounds only; first active refresh of the round.
rep('''bool ATreadM1MatchController::TraitConditionMet(const FTreadM1PlayerState& Player, const FTreadM2Trait& Trait, const FTreadM1UnitInstance& TraitOwner) const
{
	const FTreadM2Condition& Condition = Trait.Condition;''', '''bool ATreadM1MatchController::TraitConditionMet(const FTreadM1PlayerState& Player, const FTreadM2Trait& Trait, const FTreadM1UnitInstance& TraitOwner) const
{
	const FTreadM2Condition& Condition = Trait.Condition;
	if (Condition.bOddRoundsOnly && MatchState.RoundIndex % 2 == 0) return false;
	if (Trait.Trigger == ETreadM2Trigger::ShopRefresh && Condition.bFirstOnly && Player.RefreshesThisRound != 1) return false;''')

# Trait op: free shop refreshes.
rep('''		else if (Effect.Op == TEXT("TriggerTraits"))
		{
			if (Depth >= 1)''', '''		else if (Effect.Op == TEXT("FreeRefresh"))
		{
			Player.FreeRefreshes += Value;
			RecordTraitLog(Player, Trigger, EventName, &TraitOwner, Trait.Id, Effect.Op, FString(), Value, 0, bElite, TEXT("applied"));
		}
		else if (Effect.Op == TEXT("TriggerTraits"))
		{
			if (Depth >= 1)''')

# GrantUnit selector: a free recruit from one tier (elite owners use the elite tier).
rep('''				else
				{
					for (const FString& Operator : Effect.Operators)
					{
						if (const FString* CharacterId = PactData->OperatorToCharacter.Find(Operator)) Candidates.Add(*CharacterId);
					}
				}''', '''				else if (Effect.UnitSelector == TEXT("TierPool"))
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
				}''')

# Bench condition: the trait also works from the bench while any listed pact is active.
rep('''				if (Trait.Trigger != Trigger || (!OnBoard(Unit) && !Trait.bWorksOnBench)) continue;''', '''				if (Trait.Trigger != Trigger) continue;
				bool bBenchOk = Trait.bWorksOnBench;
				for (const FString& Pact : Trait.Condition.BenchIfAnyActive)
				{
					const FTreadM2PactProgress* Progress = FindPactProgress(Player, Pact);
					bBenchOk |= Progress && Progress->bActive;
				}
				if (!OnBoard(Unit) && !bBenchOk) continue;''')

# ShopRefresh traits (board, and bench when the trait allows it).
rep('''		else if (Trigger == ETreadM2Trigger::BattleStart)
		{''', '''		else if (Trigger == ETreadM2Trigger::ShopRefresh)
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
		{''')

# Strategy (band) ops: round-scheduled effects and persistent economy flags.
rep('''		if (Effect.bOnce) Player.Flags.Add(OnceKey);
		if (Effect.Op == TEXT("GainFunds"))''', '''		if (Effect.bOnce) Player.Flags.Add(OnceKey);
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
		else if (Effect.Op == TEXT("GainFunds"))''')

# Strategy bus: a band whose op names a round fires at the RoundStart of that round, not only at MatchStart.
rep('''	const FTreadM2StrategyBus* Bus = PactData.IsValid() ? PactData->FindStrategy(Player.InitialStrategyId) : nullptr;
	if (!Bus || Bus->Trigger != FTreadM2PactData::TriggerName(Trigger)) return;''', '''	const FTreadM2StrategyBus* Bus = PactData.IsValid() ? PactData->FindStrategy(Player.InitialStrategyId) : nullptr;
	if (!Bus) return;
	const bool bScheduled = Trigger == ETreadM2Trigger::RoundStart && Bus->Effects.ContainsByPredicate(
		[](const FTreadM2StrategyEffect& Item) { return Item.bApplied && Item.Effect.OnRound > 0; });
	if (Bus->Trigger != FTreadM2PactData::TriggerName(Trigger) && !bScheduled) return;''')
rep('''		const FTreadM2Effect& Effect = Item.Effect;
		const int32 Value = FMath::RoundToInt(Effect.BaseValue);
		if (!Item.bApplied)''', '''		const FTreadM2Effect& Effect = Item.Effect;
		const int32 Value = FMath::RoundToInt(Effect.BaseValue);
		// MatchStart runs the unscheduled ops; RoundStart runs only the ops scheduled for this round.
		if (Trigger == ETreadM2Trigger::RoundStart && Bus->Trigger != FTreadM2PactData::TriggerName(Trigger) &&
			(!Item.bApplied || Effect.OnRound <= 0)) continue;
		if (Trigger != ETreadM2Trigger::RoundStart && Item.bApplied && Effect.OnRound > 0) continue;
		if (!Item.bApplied)''')

# Battle source "Around4": units orthogonally adjacent to the trait owner.
rep('''			else if (Condition.Source == TEXT("FrontColumn"))''', '''			else if (Condition.Source == TEXT("Around4"))
			{
				const FIntPoint D = Actor.BoardCell - TraitOwner.BoardCell;
				bSource = OnBoard(TraitOwner) && FMath::Abs(D.X) + FMath::Abs(D.Y) == 1;
			}
			else if (Condition.Source == TEXT("FrontColumn"))''')

# Combat: pact base bonus while active (pact members, or everyone for AllUnits pacts).
rep('''				for (const FTreadM2CombatStat& PerStack : Def.CombatPerStack)
				{
					Stat.FindOrAdd(PerStack.Stat) += FMath::Min(1.0f, static_cast<float>(PerStack.PerStack * Progress.Stacks));
				}''', '''				for (const FTreadM2CombatStat& PerStack : Def.CombatPerStack)
				{
					Stat.FindOrAdd(PerStack.Stat) += FMath::Min(1.0f, static_cast<float>(PerStack.PerStack * Progress.Stacks));
				}
				for (const FTreadM2CombatStat& Base : Def.BaseStats)
				{
					Stat.FindOrAdd(Base.Stat) += static_cast<float>(Base.PerStack);
				}''')

# GrantUnit: the bound operator's tier and price, not a random tier.
rep('''	TArray<int32> TierOrder = {0, 1, 2, 3, 4, 5};
	for (int32 Index = TierOrder.Num() - 1; Index > 0; --Index) TierOrder.Swap(Index, RandomStream.RandRange(0, Index));
	SyncRandomState();
	for (const int32 TierIndex : TierOrder)
	{
		FTreadM1ShopSlot Slot;
		Slot.CharacterId = CharacterId;
		Slot.OperatorTier = TierNames[TierIndex];
		Slot.Cost = FMath::Clamp(TierIndex + 1, 1, 5);''', '''	TArray<int32> TierOrder = {0, 1, 2, 3, 4, 5};
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
		Slot.Cost = TierPrice(Slot.OperatorTier);''')

p.write_text(s, encoding="utf-8")
print("patched runtime")
