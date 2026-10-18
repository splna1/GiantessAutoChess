"""One-shot source patch: wires the M2 pact/trait event bus into TreadM1MatchController.cpp.

Kept under Tools/m2 so the edit is reviewable/replayable; every replacement asserts a unique anchor.
"""
from pathlib import Path

p = Path(__file__).resolve().parents[2] / "Source/Tread/TreadM1MatchController.cpp"
s = p.read_text(encoding="utf-8")
if "LoadM2Data();" in s:
    raise SystemExit("already patched")


def rep(a, b, count=1):
    global s
    assert s.count(a) == count, (s.count(a), a[:120])
    s = s.replace(a, b)


rep('''	MatchState = FTreadM1MatchState();
	MatchState.Seed = InSeed;''', '''	MatchState = FTreadM1MatchState();
	LoadM2Data();
	ResetBattleTraitState();
	MatchState.Seed = InSeed;''')
rep('''			ShopSlot.Cost = RandomStream.RandRange(1, 5);
			bReserved''', '''			ShopSlot.Cost = PurchaseCostFor(ShopSlot.CharacterId, RandomStream.RandRange(1, 5));
			bReserved''')
rep('''			RecordPoolLedger(TEXT("EliminationReturn"), Player.PlayerId, Unit, 1);''',
    '''			RecordPoolLedger(TEXT("EliminationReturn"), Player.PlayerId, Unit, FMath::Max(1, Unit.PoolCopiesHeld));''', 2)
rep('''	Income.Streak = StreakReward(Player);
	Income.Other = 0;''', '''	Income.Streak = StreakReward(Player);
	Income.Other = Player.PendingTraitIncome;''')
rep('''	if (Player->Funds < Slot.Cost)
	{
		return Reject(ETreadM1RejectReason::InsufficientFunds, RequestId);
	}
	if (!RecordPoolLedger(TEXT("Purchase"), PlayerId, Slot, -1))
	{
		return Reject(ETreadM1RejectReason::Unknown, RequestId);
	}
	Player->Funds -= Slot.Cost;''', '''	const int32 Price = FMath::Max(0, Slot.Cost + Player->ShopPriceDelta);
	if (Player->Funds < Price)
	{
		return Reject(ETreadM1RejectReason::InsufficientFunds, RequestId);
	}
	if (!RecordPoolLedger(TEXT("Purchase"), PlayerId, Slot, -1))
	{
		return Reject(ETreadM1RejectReason::Unknown, RequestId);
	}
	Player->Funds -= Price;
	Player->FundsSpentThisRound += Price;
	++Player->AcquiredThisRound;''')
rep('''	Slot.bIsSold = true;
	RefreshProjectedIncomes();''', '''	Slot.bIsSold = true;
	// M2: <获得时> traits, investor repeats and automatic same-star combine.
	HandleUnitAcquired(*Player, Unit.UnitInstanceId, TEXT("Purchase"), 0);
	RefreshProjectedIncomes();''')
rep('''	Player->Funds -= Cost;
	const bool bLocked = Player->Shop.bLocked;''', '''	Player->Funds -= Cost;
	Player->FundsSpentThisRound += Cost;
	const bool bLocked = Player->Shop.bLocked;''')
rep('''		Slot.bIsLockedByPlayer = bLocked;
	}
	RefreshProjectedIncomes();''', '''		Slot.bIsLockedByPlayer = bLocked;
	}
	DispatchTraitEvent(*Player, ETreadM2Trigger::ShopRefresh, TEXT("ShopRefresh"));
	RefreshProjectedIncomes();''')
rep('''	// A transform clone has no purchased pool copy or sale value. Selling it
	// only destroys the instance and writes a zero-delta audit event.
	Player->Funds += SoldUnit.bIsTransformClone ? 0 : SoldUnit.Cost;''', '''	// A transform clone has no purchased pool copy or sale value. Selling it
	// only destroys the instance and writes a zero-delta audit event. A combined
	// unit refunds every held copy minus the one-fund upgrade discount.
	const int32 SalePrice = SoldUnit.bIsTransformClone ? 0
		: FMath::Max(0, SoldUnit.Cost * FMath::Max(1, SoldUnit.PoolCopiesHeld) - (SoldUnit.UnitStar > 1 ? 1 : 0));
	Player->Funds += SalePrice;''')
rep('''	RecordPoolLedger(SoldUnit.bIsTransformClone ? TEXT("CloneDestroy") : TEXT("SellReturn"), PlayerId, SoldUnit,
		SoldUnit.bIsTransformClone ? 0 : 1);
	RefreshProjectedIncomes();''', '''	RecordPoolLedger(SoldUnit.bIsTransformClone ? TEXT("CloneDestroy") : TEXT("SellReturn"), PlayerId, SoldUnit,
		SoldUnit.bIsTransformClone ? 0 : FMath::Max(1, SoldUnit.PoolCopiesHeld));
	DispatchTraitEvent(*Player, ETreadM2Trigger::Sell, TEXT("Sell"), &SoldUnit);
	RefreshProjectedIncomes();''')
rep('''	Clone.CloneInstanceId = FString::Printf(TEXT("clone_%s_%04d"), *PlayerId, ++CloneInstanceSequence);''',
    '''	Clone.CloneInstanceId = FString::Printf(TEXT("clone_%s_%04d"), *PlayerId, ++CloneInstanceSequence);
	Clone.PoolCopiesHeld = 0;''')
rep('''	RecordPoolLedger(TEXT("CloneCreate"), PlayerId, Clone, 0);
	RefreshProjectedIncomes();''', '''	RecordPoolLedger(TEXT("CloneCreate"), PlayerId, Clone, 0);
	// Clones count as the copied character and may complete a same-star combine.
	TryAutoCombine(*Player, Clone.CharacterId, Clone.OperatorTier, 0);
	RefreshProjectedIncomes();''')
rep('''	Player->Funds -= MatchState.Rules.ExperiencePurchaseCost;
	ApplyExperience(*Player, MatchState.Rules.ExperiencePurchaseAmount);''', '''	Player->Funds -= MatchState.Rules.ExperiencePurchaseCost;
	Player->FundsSpentThisRound += MatchState.Rules.ExperiencePurchaseCost;
	ApplyExperience(*Player, MatchState.Rules.ExperiencePurchaseAmount);
	DispatchTraitEvent(*Player, ETreadM2Trigger::BuyExperience, TEXT("BuyExperience"));''')
rep('''	MatchState.RoundIndex = 1;
	SetRoundTypeForCurrentRound();
	MatchState.PhaseTimeRemainingSec = static_cast<float>(MatchState.Rules.PreparationDurationSec);
	RefreshProjectedIncomes();
	RefreshScoutSnapshots();
	return Accept(RequestId);''', '''	MatchState.RoundIndex = 1;
	SetRoundTypeForCurrentRound();
	MatchState.PhaseTimeRemainingSec = static_cast<float>(MatchState.Rules.PreparationDurationSec);
	for (FTreadM1PlayerState& Player : MatchState.Players)
	{
		RecomputePacts(Player);
		DispatchTraitEvent(Player, ETreadM2Trigger::MatchStart, TEXT("MatchStart"));
	}
	DispatchRoundTrigger(ETreadM2Trigger::RoundStart, TEXT("EnterPreparation"));
	RefreshProjectedIncomes();
	RefreshScoutSnapshots();
	return Accept(RequestId);''')
rep('''	MatchState.PhaseTimeRemainingSec = static_cast<float>(MatchState.Rules.PreparationDurationSec);
	RankPlayers();
	SetPhase(ETreadM1Phase::Preparation);''', '''	MatchState.PhaseTimeRemainingSec = static_cast<float>(MatchState.Rules.PreparationDurationSec);
	for (FTreadM1PlayerState& Player : MatchState.Players)
	{
		Player.AcquiredThisRound = 0;
		Player.FundsSpentThisRound = 0;
	}
	DispatchRoundTrigger(ETreadM2Trigger::RoundStart, TEXT("EnterPreparation"));
	RankPlayers();
	SetPhase(ETreadM1Phase::Preparation);''')
rep('''	MatchState.LastBattleResult.IncomeBreakdown = FTreadM1IncomeBreakdown();
	BuildPairings();''', '''	MatchState.LastBattleResult.IncomeBreakdown = FTreadM1IncomeBreakdown();
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
	BuildPairings();''')
rep('''	// Pairings were fixed at deployment, including the existing odd-player bye.
	MatchState.LastBattleResult.Outcomes.Reset();''', '''	// Pairings were fixed at deployment, including the existing odd-player bye.
	ResetBattleTraitState();
	MatchState.LastBattleResult.Outcomes.Reset();''')
rep('''		TArray<int32> LeftUnitHealth;
		TArray<int32> RightUnitHealth;
		for (const FTreadM1UnitInstance& Unit : Left->BoardUnits)
		{
			LeftUnitHealth.Add(FMath::Max(2, 3 + Unit.Cost * Unit.UnitStar));
		}
		for (const FTreadM1UnitInstance& Unit : Right->BoardUnits)
		{
			RightUnitHealth.Add(FMath::Max(2, 3 + Unit.Cost * Unit.UnitStar));
		}''', '''		TArray<int32> LeftUnitHealth;
		TArray<int32> RightUnitHealth;
		TArray<FTreadM2UnitCombat> LeftCombat;
		TArray<FTreadM2UnitCombat> RightCombat;
		TArray<int32> LeftAttacks;
		TArray<int32> RightAttacks;
		for (const FTreadM1UnitInstance& Unit : Left->BoardUnits)
		{
			LeftCombat.Add(ComputeUnitCombat(*Left, Unit));
			LeftUnitHealth.Add(FMath::Max(2, FMath::RoundToInt((3 + Unit.Cost * Unit.UnitStar) * LeftCombat.Last().HealthMul)));
		}
		for (const FTreadM1UnitInstance& Unit : Right->BoardUnits)
		{
			RightCombat.Add(ComputeUnitCombat(*Right, Unit));
			RightUnitHealth.Add(FMath::Max(2, FMath::RoundToInt((3 + Unit.Cost * Unit.UnitStar) * RightCombat.Last().HealthMul)));
		}
		LeftAttacks.Init(0, LeftUnitHealth.Num());
		RightAttacks.Init(0, RightUnitHealth.Num());''')
for a, b, A, B in (("Left", "Right", "LeftCombat", "RightCombat"), ("Right", "Left", "RightCombat", "LeftCombat")):
    alive = "RightAlive" if b == "Right" else "LeftAlive"
    rep(f'''				const int32 Damage = FMath::Max(1, {a}->BoardUnits[SourceIndex].Cost * {a}->BoardUnits[SourceIndex].UnitStar);
				{b}UnitHealth[TargetIndex] -= Damage;
				RecordBattleEvent(ETreadM1BattleEventType::UnitDamaged, {a}->PlayerId, {b}->PlayerId, Damage,
					{a}->BoardUnits[SourceIndex].UnitInstanceId, {b}->BoardUnits[TargetIndex].UnitInstanceId,
					FMath::Max(0, {b}UnitHealth[TargetIndex]));
				if ({b}UnitHealth[TargetIndex] <= 0)
				{{
					--{alive};
					RecordBattleEvent(ETreadM1BattleEventType::UnitDied, {a}->PlayerId, {b}->PlayerId, 0,
						{a}->BoardUnits[SourceIndex].UnitInstanceId, {b}->BoardUnits[TargetIndex].UnitInstanceId, 0);
				}}''', f'''				const int32 Damage = FMath::Max(1, FMath::RoundToInt({a}->BoardUnits[SourceIndex].Cost * {a}->BoardUnits[SourceIndex].UnitStar *
					{A}[SourceIndex].AttackMul * {B}[TargetIndex].DamageTaken));
				{b}UnitHealth[TargetIndex] -= Damage;
				RecordBattleEvent(ETreadM1BattleEventType::UnitDamaged, {a}->PlayerId, {b}->PlayerId, Damage,
					{a}->BoardUnits[SourceIndex].UnitInstanceId, {b}->BoardUnits[TargetIndex].UnitInstanceId,
					FMath::Max(0, {b}UnitHealth[TargetIndex]));
				HandleBattleAttack(*{a}, {a}->BoardUnits[SourceIndex], {a}Attacks[SourceIndex], {A}[SourceIndex],
					{b}->PlayerId, {b}->BoardUnits[TargetIndex].UnitInstanceId);
				if ({b}UnitHealth[TargetIndex] <= 0)
				{{
					--{alive};
					RecordBattleEvent(ETreadM1BattleEventType::UnitDied, {a}->PlayerId, {b}->PlayerId, 0,
						{a}->BoardUnits[SourceIndex].UnitInstanceId, {b}->BoardUnits[TargetIndex].UnitInstanceId, 0);
					OnBattleUnitEvent(*{a}, TEXT("Kill"), {a}->BoardUnits[SourceIndex]);
					OnBattleUnitEvent(*{b}, TEXT("SelfKnockedOut"), {b}->BoardUnits[TargetIndex]);
				}}''')
rep('''	SyncRandomState();
	RankPlayers();
	for (FTreadM1BattleOutcome& Outcome : MatchState.LastBattleResult.Outcomes)''', '''	SyncRandomState();
	for (FTreadM1PlayerState& Player : MatchState.Players)
	{
		DispatchTraitEvent(Player, ETreadM2Trigger::BattleEnd, TEXT("BattleEnd"));
	}
	ResetBattleTraitState();
	RankPlayers();
	for (FTreadM1BattleOutcome& Outcome : MatchState.LastBattleResult.Outcomes)''')
rep('''		const int32 Income = IncomeBreakdown.Base + IncomeBreakdown.Interest + IncomeBreakdown.Streak + IncomeBreakdown.Other;
		Player.Funds += Income;
		ApplyExperience(Player, 2);''', '''		const int32 Income = IncomeBreakdown.Base + IncomeBreakdown.Interest + IncomeBreakdown.Streak + IncomeBreakdown.Other;
		Player.Funds += Income;
		// Trait/pact funds promised during the round are paid exactly once, here, as IncomeBreakdown.Other.
		Player.LastSettlementIncome = IncomeBreakdown;
		Player.PendingTraitIncome = 0;
		DispatchTraitEvent(Player, ETreadM2Trigger::Settlement, TEXT("Settlement"));
		ApplyExperience(Player, 2);''')
rep('''			if (!Unit.bIsTransformClone) ++Player->PopulationUsed;
			const int32 BenchSlot = Player->BenchUnitInstanceIds.Find(UnitInstanceId);
			if (BenchSlot != INDEX_NONE)
			{
				Player->BenchUnitInstanceIds[BenchSlot].Empty();
			}
			RefreshScoutSnapshots();''', '''			if (!Unit.bIsTransformClone) ++Player->PopulationUsed;
			const int32 BenchSlot = Player->BenchUnitInstanceIds.Find(UnitInstanceId);
			if (BenchSlot != INDEX_NONE)
			{
				Player->BenchUnitInstanceIds[BenchSlot].Empty();
			}
			RecomputePacts(*Player);
			DispatchTraitEvent(*Player, ETreadM2Trigger::Deploy, TEXT("MoveToBoard"), &Unit);
			RefreshScoutSnapshots();''')
rep('''			else
			{
				Player->BenchUnitInstanceIds.Add(UnitInstanceId);
			}
			RefreshScoutSnapshots();''', '''			else
			{
				Player->BenchUnitInstanceIds.Add(UnitInstanceId);
			}
			RecomputePacts(*Player);
			DispatchTraitEvent(*Player, ETreadM2Trigger::Undeploy, TEXT("MoveToBench"), &Unit);
			RefreshScoutSnapshots();''')
rep('''void ATreadM1MatchController::RefreshScoutSnapshots()
{
	MatchState.ScoutSnapshots.Reset();''', '''void ATreadM1MatchController::RefreshScoutSnapshots()
{
	// Pact counts follow every roster mutation; the snapshot then mirrors them read-only.
	RecomputeAllPacts();
	MatchState.ScoutSnapshots.Reset();''')
rep('''		Snapshot.ActivePactIds = Player.ActivePactIds;
		Snapshot.bReadOnly = true;''', '''		Snapshot.ActivePactIds = Player.ActivePactIds;
		Snapshot.Pacts = Player.Pacts;
		for (const FTreadM2PactProgress& Progress : Player.Pacts)
		{
			if (Progress.Stacks <= 0) continue;
			FTreadM1PactStack& Stack = Snapshot.PactStacks.AddDefaulted_GetRef();
			Stack.PactId = Progress.PactId;
			Stack.StackCount = Progress.Stacks;
		}
		Snapshot.bReadOnly = true;''')
# M1 economy regression: trait funds promised during the round are paid as Other at settlement.
rep('''				FTreadM1PlayerState IncomeInput = After;
				IncomeInput.Funds = Before.Funds;''', '''				FTreadM1PlayerState IncomeInput = After;
				IncomeInput.Funds = Before.Funds;
				IncomeInput.PendingTraitIncome = After.LastSettlementIncome.Other;''')
rep('''	if (FParse::Param(FCommandLine::Get(), TEXT("TreadM1SelfTest")))
	{
		const bool bPassed = RunDeterministicSelfTest();
		FPlatformMisc::RequestExitWithStatus(false, bPassed ? 0 : 1);
	}''', '''	if (FParse::Param(FCommandLine::Get(), TEXT("TreadM1SelfTest")))
	{
		const bool bPassed = RunDeterministicSelfTest();
		FPlatformMisc::RequestExitWithStatus(false, bPassed ? 0 : 1);
	}
	if (FParse::Param(FCommandLine::Get(), TEXT("TreadM2SelfTest")))
	{
		const bool bPassed = RunM2PactSelfTest();
		FPlatformMisc::RequestExitWithStatus(false, bPassed ? 0 : 1);
	}''')
p.write_text(s, encoding="utf-8")
print("patched", p)
