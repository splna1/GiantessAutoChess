"""Replayable source patch (N1, part 3): battle "first N times" (maxTimes) in the runtime, and self-test fixtures that
pick Stronghold-Protocol battle traits (kill every N, adjacent ammo, front-skill cap), 绝技 elite counting, the
roster's real copy-trigger card (RoundStart "trigger front Acquire") and leftover-funds-lost settlement."""
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
    '''			if (Condition.bFirstOnly)
			{
				int32& Fired = BattleTraitCounters.FindOrAdd(Key + TEXT("|first"));
				if (Fired++ > 0) continue;
			}''',
    '''			if (Condition.bFirstOnly)
			{
				int32& Fired = BattleTraitCounters.FindOrAdd(Key + TEXT("|first"));
				if (Fired++ > 0) continue;
			}
			if (Condition.MaxTimes > 0)
			{
				int32& Times = BattleTraitCounters.FindOrAdd(Key + TEXT("|times"));
				if (Times++ >= Condition.MaxTimes) continue;
			}''')], "|times")

patch(SRC / "TreadM2PactSelfTest.cpp", [
    # 绝技: members are elite units of any card
    ('''		const TArray<FString> PactMembers = Members(Def.PactId);
		int32 MaxTierReached = 0;''', '''		TArray<FString> PactMembers = Members(Def.PactId);
		const int32 FixtureStar = Def.bCountsEliteAll ? 2 : 1;
		if (Def.bCountsEliteAll)
		{
			for (const FString& Id : PactData->CardOrder)
			{
				if (PactMembers.Num() >= Def.Thresholds.Last() + 1) break;
				if (!IsHarmonyCard(PactData->Cards[Id])) PactMembers.Add(Id);
			}
		}
		int32 MaxTierReached = 0;'''),
    ('''			for (int32 Index = 0; Index < Count; ++Index) Inject(Player, PactMembers[Index], FIntPoint(Index % 8, 4 + Index / 8));''',
     '''			for (int32 Index = 0; Index < Count; ++Index) Inject(Player, PactMembers[Index], FIntPoint(Index % 8, 4 + Index / 8), FixtureStar);'''),
    # battle fixtures
    ('''			{ return T.Condition.Event == TEXT("Kill") && T.Condition.Every == 1 && T.Effects[0].PactSelector == TEXT("Pacts"); },
			TEXT("Kill"), 2, FIntPoint(3, 6), false);''',
     '''			{ return T.Condition.Event == TEXT("Kill") && T.Condition.Every >= 1 && T.Condition.MaxTimes == 0 && T.Condition.PerBattleCap == 0 &&
				T.Effects[0].PactSelector == TEXT("Pacts"); },
			TEXT("Kill"), 4, FIntPoint(3, 6), false);'''),
    ('''			{ return T.Condition.Event == TEXT("AmmoConsumed") && T.Condition.Source == TEXT("Front1"); }, TEXT("AmmoConsumed"), 14, FIntPoint(3, 6), true);''',
     '''			{ return T.Condition.Event == TEXT("AmmoConsumed") && (T.Condition.Source == TEXT("Front1") || T.Condition.Source == TEXT("Around4")); },
			TEXT("AmmoConsumed"), 14, FIntPoint(3, 6), true);'''),
    ('''			{ return T.Condition.PerBattleCap > 0 && T.Effects[0].PactSelector == TEXT("Pacts"); }, TEXT("SkillActivated"), 40, FIntPoint(3, 6), true);''',
     '''			{ return T.Condition.PerBattleCap > 0 && T.Condition.Event == TEXT("SkillActivated") && T.Condition.Source == TEXT("Front1") &&
				T.Effects[0].PactSelector == TEXT("Pacts"); }, TEXT("SkillActivated"), 400, FIntPoint(3, 6), true);'''),
    ('''			const FString Kill = FindCard([&](const FTreadM2Card&, const FTreadM2Trait& T)
				{ return T.Condition.Event == TEXT("Kill") && T.Condition.Every == 1 && T.Effects[0].PactSelector == TEXT("Pacts"); });''',
     '''			const FString Kill = FindCard([&](const FTreadM2Card&, const FTreadM2Trait& T)
				{ return T.Condition.Event == TEXT("Kill") && T.Condition.Every >= 1 && T.Condition.MaxTimes == 0 && T.Condition.PerBattleCap == 0 &&
					T.Effects[0].PactSelector == TEXT("Pacts"); });'''),
    ('''			OnBattleUnitEvent(Player, TEXT("Kill"), FTreadM1UnitInstance(*FindOwnedUnit(Player, KillId)));
			ScenarioCheck(TEXT("stackAmplifiedByBehindUnit"), Progress(TEXT("P2"), Pact).Stacks - Before == 2 &&''',
     '''			const FTreadM2Trait& KillTrait = PactData->FindCard(Kill)->Traits[0];
			for (int32 Kills = 0; Kills < FMath::Max(1, KillTrait.Condition.Every); ++Kills)
			{
				OnBattleUnitEvent(Player, TEXT("Kill"), FTreadM1UnitInstance(*FindOwnedUnit(Player, KillId)));
			}
			const FTreadM2Card* AmpCard = PactData->FindCard(Amp);
			const FTreadM2Effect* AmpEffect = AmpCard ? AmpCard->Traits[0].Effects.FindByPredicate([](const FTreadM2Effect& E) { return E.Op == TEXT("AmplifyFrontStackGain"); }) : nullptr;
			const int32 ExpectedGain = FMath::RoundToInt(KillTrait.Effects[0].BaseValue) + (AmpEffect ? FMath::RoundToInt(AmpEffect->BaseValue) : 0);
			ScenarioCheck(TEXT("stackAmplifiedByBehindUnit"), Progress(TEXT("P2"), Pact).Stacks - Before == ExpectedGain &&'''),
    # copy-trigger: Stronghold-Protocol has "<进入休整期时>触发身前一格的其他干员的“获得时”类效果"
    ('''			const FString SellTrigger = FindCard([&](const FTreadM2Card&, const FTreadM2Trait& T)
				{ return T.Trigger == ETreadM2Trigger::Sell && HasOp(T, TEXT("TriggerTraits")); });''',
     '''			const FString SellTrigger = FindCard([&](const FTreadM2Card&, const FTreadM2Trait& T)
				{ return T.Trigger == ETreadM2Trigger::Sell && HasOp(T, TEXT("TriggerTraits")); });
			const FString FrontTrigger = FindCard([&](const FTreadM2Card&, const FTreadM2Trait& T)
				{ return T.Trigger == ETreadM2Trigger::RoundStart && T.Targets == TEXT("Front1") && HasOp(T, TEXT("TriggerTraits")); });
			const FString AcquireCard = FindCard([&](const FTreadM2Card&, const FTreadM2Trait& T)
				{ return T.Trigger == ETreadM2Trigger::Acquire && HasOp(T, TEXT("AddStacks")) && !T.bActivationRequired; });
			if (SellTrigger.IsEmpty() && !FrontTrigger.IsEmpty() && !AcquireCard.IsEmpty())
			{
				FTreadM1PlayerState& Copier = MatchState.Players[2];
				ClearFixture(Copier);
				Inject(Copier, FrontTrigger, FIntPoint(5, 6));
				Inject(Copier, AcquireCard, FIntPoint(5, 5));
				const int32 CopyFrom = MatchState.TraitLog.Num();
				DispatchTraitEvent(Copier, ETreadM2Trigger::RoundStart, TEXT("EnterPreparation"));
				ScenarioCheck(TEXT("traitCopyTriggersOtherTraits"), LogHas(CopyFrom, TEXT("RoundStart"), TEXT("EnterPreparation"), TEXT("applied")) &&
					LogHas(CopyFrom, TEXT("RoundStart"), TEXT("EnterPreparation:Triggered"), TEXT("applied")));
			}
			else
			{'''),
    ('''			ScenarioCheck(TEXT("traitCopyTriggersOtherTraits"), LogHas(LogFrom, TEXT("Sell"), TEXT("Sell"), TEXT("applied")) &&
				LogHas(LogFrom, TEXT("Sell"), TEXT("Sell:Triggered")));
		}''',
     '''			ScenarioCheck(TEXT("traitCopyTriggersOtherTraits"), LogHas(LogFrom, TEXT("Sell"), TEXT("Sell"), TEXT("applied")) &&
				LogHas(LogFrom, TEXT("Sell"), TEXT("Sell:Triggered")));
			}
		}'''),
    # settlement: Stronghold-Protocol loses leftover funds
    ('''		ScenarioCheck(TEXT("pendingTraitIncomePaidAtSettlement"), bResolved && P0.LastSettlementIncome.Other == Pending && P0.PendingTraitIncome == 0 &&
			P0.Funds == FundsBeforeSettle + P0.LastSettlementIncome.Base + P0.LastSettlementIncome.Interest + P0.LastSettlementIncome.Streak + Pending);''',
     '''		const int32 Kept = HasN1Economy() && PactData->Economy.bLeftoverFundsLost && !P0.Flags.Contains(TEXT("flag:CarryOverFunds")) ? 0 : FundsBeforeSettle;
		ScenarioCheck(TEXT("pendingTraitIncomePaidAtSettlement"), bResolved && P0.LastSettlementIncome.Other == Pending && P0.PendingTraitIncome == 0 &&
			P0.Funds == Kept + P0.LastSettlementIncome.Base + P0.LastSettlementIncome.Interest + P0.LastSettlementIncome.Streak + Pending);'''),
], "FixtureStar")

patch(SRC / "TreadM2PactSelfTest.cpp", [(
    '''			const FString Ammo = FindCard([&](const FTreadM2Card& Card, const FTreadM2Trait&) { return Card.bConsumesAmmo; });
			Inject(P0, Ammo, FIntPoint(4, 7), 3);''',
    '''			const FString Ammo = FindCard([&](const FTreadM2Card& Card, const FTreadM2Trait&) { return Card.bConsumesAmmo; });
			Inject(P0, Ammo, FIntPoint(4, 7), 3);
			// N1 pact bonuses make P0 one-shot the 1-star AI rosters; durable AI fixtures keep battles long enough for the
			// third attack (skill) to happen. Pool copies are not touched (0 held).
			for (int32 AiIndex = 1; HasN1Economy() && AiIndex < MatchState.Players.Num(); ++AiIndex)
			{
				FTreadM1PlayerState& Ai = MatchState.Players[AiIndex];
				int32 Added = 0;
				for (const FString& Id : PactData->CardOrder)
				{
					if (Added >= 3) break;
					if (Ai.BoardUnits.ContainsByPredicate([&](const FTreadM1UnitInstance& U) { return U.CharacterId == Id; })) continue;
					Inject(Ai, Id, FIntPoint(5 + Added, 3), 3);
					++Added;
				}
			}''')], "durable AI fixtures")

patch(SRC / "TreadM1MatchController.cpp", [(
    '''				FTreadM1PlayerState ExpectedExperience = Before;
				ApplyExperience(ExpectedExperience, 2);
				bEconomy &= !After.bIsEliminated && After.Funds == Before.Funds + Income.Base + Income.Interest + Income.Streak + Income.Other &&
					After.Level == ExpectedExperience.Level && After.Experience == ExpectedExperience.Experience;''',
    '''				FTreadM1PlayerState ExpectedExperience = Before;
				if (!HasN1Economy()) ApplyExperience(ExpectedExperience, 2);
				// N1 (Stronghold-Protocol): leftover funds are lost at settlement unless a band carries them over.
				const bool bKeepsFunds = !HasN1Economy() || !PactData->Economy.bLeftoverFundsLost || After.Flags.Contains(TEXT("flag:CarryOverFunds"));
				const int32 Kept = bKeepsFunds ? Before.Funds : 0;
				bEconomy &= !After.bIsEliminated && After.Funds == Kept + Income.Base + Income.Interest + Income.Streak + Income.Other &&
					After.Level == ExpectedExperience.Level && After.Experience == ExpectedExperience.Experience;''')], "bKeepsFunds")

patch(SRC / "TreadM1MatchController.cpp", [
    ('''		Checks.Add(MatchState.Players.Num() == 4 && MatchState.Players[0].Shop.Slots.Num() == ShopSlots);
		Checks.Add(MatchState.PoolLedger.Balances.Num() == 192);''',
     '''		// N1: shop size follows the 调度中心 level and the pool holds one balance per bound card.
		const int32 ExpectedSlots = HasN1Economy() ? PactData->Economy.SlotsForLevel(MatchState.Players[0].Level) : ShopSlots;
		const int32 ExpectedBalances = HasN1Economy() ? PactData->CardOrder.Num() : 192;
		Checks.Add(MatchState.Players.Num() == 4 && MatchState.Players[0].Shop.Slots.Num() == ExpectedSlots);
		Checks.Add(MatchState.PoolLedger.Balances.Num() == ExpectedBalances);'''),
    ('''				if (Balance.OperatorTier == PoolTierNames[TierIndex] && Balance.PoolCopiesTotal != PoolTierTotals[TierIndex])''',
     '''				if (!HasN1Economy() && Balance.OperatorTier == PoolTierNames[TierIndex] && Balance.PoolCopiesTotal != PoolTierTotals[TierIndex])'''),
    ('''		Checks.Add(ReservedCopies == 4 * ShopSlots);''',
     '''		Checks.Add(ReservedCopies == 4 * ExpectedSlots);'''),
    ('''		Checks.Add(MatchState.BP.BannedStrategyIds.Num() == 4 && MatchState.BP.AvailableStrategyIds.Num() == 28);''',
     '''		Checks.Add(MatchState.BP.BannedStrategyIds.Num() == 4 && MatchState.BP.AvailableStrategyIds.Num() == MatchState.Strategies.Num() - 4);'''),
], "ExpectedBalances")
