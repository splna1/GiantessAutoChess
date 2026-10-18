"""Replayable source patch (N1, part 2):
  * strategy bus AddStacks supports pact selectors (AllActivePacts / RandomUnitPerTierPacts) and the
    "only one active pact" amount of band 余;
  * the M2 self-test keeps its check names but uses Stronghold-Protocol semantics where they differ
    (sale value = tier sell price; strategies are bands: setup flags at MatchStart, stacks at RoundEnd;
    a neighbour card may have only adjunct pacts)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "Source/Tread"


def dedent1(text):
    return "\n".join(line[1:] if line.startswith("\t") else line for line in text.split("\n"))


def patch(path, pairs, marker):
    s = path.read_text(encoding="utf-8")
    if marker in s:
        print("already patched", path.name)
        return
    for old, new in pairs:
        for _ in range(3):
            if s.count(old) == 1:
                s = s.replace(old, new)
                break
            old, new = dedent1(old), dedent1(new)
        else:
            raise AssertionError(path.name + ": " + old[:120])
    path.write_text(s, encoding="utf-8")
    print("patched", path.name)


patch(SRC / "TreadM2PactRuntime.cpp", [(
    '''		else if (Effect.Op == TEXT("AddStacks"))
		{
			for (const FString& Pact : Effect.Pacts)
			{
				AddPactStacks(Player, Pact, Value, false, SourceId, nullptr, Trigger, EventName, false);
			}
		}''',
    '''		else if (Effect.Op == TEXT("AddStacks"))
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
		}''')], "RandomUnitPerTierPacts")

patch(SRC / "TreadM2PactSelfTest.cpp", [
    ('''		const FString NeighbourPact = PactData->FindCard(NeighbourCard)->CorePacts[0];''',
     '''		const FTreadM2Card* NeighbourData = PactData->FindCard(NeighbourCard);
		const FString NeighbourPact = !NeighbourData ? FString() : NeighbourData->CorePacts.Num() > 0 ? NeighbourData->CorePacts[0]
			: (NeighbourData->AdjunctPacts.Num() > 0 ? NeighbourData->AdjunctPacts[0] : FString());'''),
    ('''		ScenarioCheck(TEXT("eventSellCombinedRefund"), bSold && P0.Funds == FundsBeforeSell + FMath::Max(0, CostEach * 3 - 1) &&''',
     '''		// N1 (Stronghold-Protocol): every operator, normal or elite, sells for the tier's sell price.
		const int32* N1Sell = HasN1Economy() ? PactData->Economy.SellByTier.Find(CardTier(NoActCard)) : nullptr;
		const int32 ExpectedRefund = HasN1Economy() ? (N1Sell ? *N1Sell : 1) : FMath::Max(0, CostEach * 3 - 1);
		ScenarioCheck(TEXT("eventSellCombinedRefund"), bSold && P0.Funds == FundsBeforeSell + ExpectedRefund &&'''),
    ('''		bool bStrategy = FundsStrategy && StackStrategy && DeferredStrategy;
		if (bStrategy)''',
     '''		if (HasN1Economy())
		{
			// Bands: economy flags at MatchStart, stacks when preparation ends, unsupported buffs logged as deferred.
			FundsStrategy = PactData->Strategies.FindByPredicate([](const FTreadM2StrategyBus& Bus)
			{
				return Bus.Trigger == TEXT("MatchStart") && Bus.Effects.ContainsByPredicate([](const FTreadM2StrategyEffect& E)
					{ return E.bApplied && (E.Effect.Op == TEXT("CarryOverFunds") || E.Effect.Op == TEXT("FirstBuyPrice")); });
			});
			StackStrategy = PactData->Strategies.FindByPredicate([](const FTreadM2StrategyBus& Bus)
			{
				return Bus.Trigger == TEXT("RoundEnd") && Bus.Effects.Num() > 0 && Bus.Effects[0].bApplied && Bus.Effects[0].Effect.Op == TEXT("AddStacks");
			});
			DeferredStrategy = PactData->Strategies.FindByPredicate([](const FTreadM2StrategyBus& Bus)
			{
				return Bus.Trigger == TEXT("MatchStart") && Bus.Effects.Num() > 0 && !Bus.Effects[0].bApplied;
			});
		}
		bool bStrategy = FundsStrategy && StackStrategy && DeferredStrategy;
		if (bStrategy && HasN1Economy())
		{
			From = MatchState.TraitLog.Num();
			P0.InitialStrategyId = FundsStrategy->StrategyId;
			DispatchTraitEvent(P0, ETreadM2Trigger::MatchStart, TEXT("MatchStart"));
			bStrategy &= P0.Flags.Contains(TEXT("flag:CarryOverFunds")) || P0.Flags.Contains(TEXT("flag:FirstBuyPrice"));
			P0.Flags.Remove(TEXT("flag:CarryOverFunds"));
			P0.Flags.Remove(TEXT("flag:FirstBuyPrice"));
			P0.InitialStrategyId = DeferredStrategy->StrategyId;
			DispatchTraitEvent(P0, ETreadM2Trigger::MatchStart, TEXT("MatchStart"));
			bStrategy &= LogHas(From, TEXT("MatchStart"), TEXT("MatchStart"), TEXT("deferred-M4"));
			P0.InitialStrategyId = StackStrategy->StrategyId;
		}
		else if (bStrategy)'''),
    ('''		ScenarioCheck(TEXT("strategyEffectsOnEventBus"), bStrategy && LogHas(From, TEXT("BattleStart"), TEXT("BattleStart"), TEXT("applied"),
			StackStrategy ? StackStrategy->Effects[0].Effect.Pacts[0] : FString()));''',
     '''		bool bStrategyStacks = false;
		for (int32 Index = From; Index < MatchState.TraitLog.Num() && StackStrategy; ++Index)
		{
			const FTreadM2TraitLogEntry& Entry = MatchState.TraitLog[Index];
			bStrategyStacks |= Entry.SourceId == TEXT("strategy:") + StackStrategy->StrategyId && Entry.Op == TEXT("AddStacks") && Entry.Status == TEXT("applied");
		}
		ScenarioCheck(TEXT("strategyEffectsOnEventBus"), bStrategy && bStrategyStacks);'''),
], "N1Sell")

patch(SRC / "TreadM2PactSelfTest.cpp", [
    ('''			return T.Trigger == ETreadM2Trigger::RoundEnd && T.Condition.SameRowAtLeast > 0 && HasOp(T, TEXT("AddStacks"));''',
     '''			// M2 data: "若同一行有N名干员" (condition); Stronghold-Protocol: "同一行每有1名干员" (SameRowCount scale).
			return T.Trigger == ETreadM2Trigger::RoundEnd && HasOp(T, TEXT("AddStacks")) && T.Effects[0].Pacts.Num() > 0 &&
				(T.Condition.SameRowAtLeast > 0 || T.Effects[0].AmountScale == TEXT("SameRowCount"));'''),
    ('''		Inject(P0, Members(RowPact, RowCard).Last(), FIntPoint(2, 6));''',
     '''		const TArray<FString> RowMembers = Members(RowPact, RowCard);
		if (RowMembers.Num() > 0) Inject(P0, RowMembers.Last(), FIntPoint(2, 6));'''),
], "RowMembers")
