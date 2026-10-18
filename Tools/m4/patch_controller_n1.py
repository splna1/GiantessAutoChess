"""Replayable source patch (N1): ATreadM1MatchController uses the Stronghold-Protocol economy when
Content/Data/Generated/Economy.json is loaded (HasN1Economy()); without it the M1 graybox economy is unchanged.
Kept from Tread (owner decision 2026-10-08): 4 players, 12 rounds, PvP, 8 bench slots, 100 base health, 30 s prep."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
p = ROOT / "Source/Tread/TreadM1MatchController.cpp"
s = p.read_text(encoding="utf-8")
if "HasN1Economy()" in s:
    raise SystemExit("already patched")


def dedent1(text):
    return "\n".join(line[1:] if line.startswith("\t") else line for line in text.split("\n"))


def rep(old, new):
    global s
    for _ in range(3):
        if s.count(old) == 1:
            s = s.replace(old, new)
            return
        old, new = dedent1(old), dedent1(new)
    raise AssertionError(old[:120])


# Rules: refresh price and first upgrade price come from Economy.json.
rep('''	MatchState.Rules.MaxBenchSlots = MaxBenchSlots;
	InitializePoolLedger();''', '''	MatchState.Rules.MaxBenchSlots = MaxBenchSlots;
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
	InitializePoolLedger();''')

# Players start at shop level 1 with round-1 income, deploy cap 8.
rep('''		Player.Funds = 5;
		Player.Level = 3;
		Player.Experience = 0;
		Player.ExperienceToNextLevel = 6;
		Player.PopulationLimit = 3;''', '''		Player.Funds = 5;
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
		}''')

# Graybox rosters use real cards (lowest tiers first) with their bound tier and price.
rep('''			Unit.CharacterId = FString::Printf(TEXT("char_%03d"), PlayerIndex * 3 + Slot + 1);''', '''			Unit.CharacterId = FString::Printf(TEXT("char_%03d"), PlayerIndex * 3 + Slot + 1);
			if (HasN1Economy() && PactData->CardOrder.Num() > 0)
			{
				TArray<FString> LowTier;
				for (const FString& CharacterId : PactData->CardOrder)
				{
					if (CardTier(CharacterId) == TEXT("I") || CardTier(CharacterId) == TEXT("II")) LowTier.Add(CharacterId);
				}
				if (LowTier.Num() > 0) Unit.CharacterId = LowTier[(PlayerIndex * 3 + Slot) % LowTier.Num()];
			}''')
rep('''			Unit.Cost = 1 + ((PlayerIndex + Slot) % 5);''', '''			Unit.Cost = 1 + ((PlayerIndex + Slot) % 5);
			if (HasN1Economy() && !CardTier(Unit.CharacterId).IsEmpty())
			{
				Unit.OperatorTier = CardTier(Unit.CharacterId);
				Unit.Cost = TierPrice(Unit.OperatorTier);
			}''')

# Shared pool: one balance per bound card with its own tier and copies.
rep('''void ATreadM1MatchController::InitializePoolLedger()
{
	MatchState.PoolLedger = FTreadM1PoolLedger();''', '''void ATreadM1MatchController::InitializePoolLedger()
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
	}''')

rep('''		int32 ExpectedTotal = INDEX_NONE;
		for (int32 TierIndex = 0; TierIndex < UE_ARRAY_COUNT(PoolTierNames); ++TierIndex)''', '''		int32 ExpectedTotal = INDEX_NONE;
		if (HasN1Economy())
		{
			const FTreadM2Card* Card = PactData->FindCard(Balance.CharacterId);
			ExpectedTotal = Card && Card->OperatorTier == Balance.OperatorTier ? Card->PoolCopies : INDEX_NONE;
		}
		for (int32 TierIndex = 0; TierIndex < UE_ARRAY_COUNT(PoolTierNames) && !HasN1Economy(); ++TierIndex)''')
rep('''	return MatchState.PoolLedger.Balances.Num() == ShopCharacterCount * UE_ARRAY_COUNT(PoolTierNames);''', '''	if (HasN1Economy()) return MatchState.PoolLedger.Balances.Num() > 0;
	return MatchState.PoolLedger.Balances.Num() == ShopCharacterCount * UE_ARRAY_COUNT(PoolTierNames);''')

# Shop: slot count by shop level, copy-weighted draw of tier <= level, price by tier.
rep('''	for (int32 Slot = 0; Slot < MatchState.Rules.ShopSlotCount; ++Slot)
	{
		FTreadM1ShopSlot ShopSlot;
		ShopSlot.SlotIndex = Slot;
		bool bReserved = false;''', '''	const int32 SlotCount = HasN1Economy() ? PactData->Economy.SlotsForLevel(Player.Level) : MatchState.Rules.ShopSlotCount;
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
		}''')

# Purchase: band "first <pact> operator bought each round costs N".
rep('''	const int32 Price = FMath::Max(0, Slot.Cost + Player->ShopPriceDelta);''', '''	int32 Price = FMath::Max(0, Slot.Cost + Player->ShopPriceDelta);
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
	}''')
rep('''	Player->Funds -= Price;
	Player->FundsSpentThisRound += Price;
	++Player->AcquiredThisRound;''', '''	if (HasN1Economy() && Price < FMath::Max(0, Slot.Cost + Player->ShopPriceDelta))
	{
		Player->Flags.AddUnique(FString::Printf(TEXT("firstbuy@%d"), MatchState.RoundIndex));
	}
	Player->Funds -= Price;
	Player->FundsSpentThisRound += Price;
	++Player->AcquiredThisRound;''')

# Refresh: free refreshes first; count refreshes for traits.
rep('''	const int32 Cost = Player->Shop.RefreshCost;
	if (Player->Funds < Cost)
	{
		return Reject(ETreadM1RejectReason::InsufficientFunds, RequestId);
	}
	Player->Funds -= Cost;
	Player->FundsSpentThisRound += Cost;''', '''	const bool bFree = Player->FreeRefreshes > 0;
	const int32 Cost = bFree ? 0 : Player->Shop.RefreshCost;
	if (Player->Funds < Cost)
	{
		return Reject(ETreadM1RejectReason::InsufficientFunds, RequestId);
	}
	if (bFree) --Player->FreeRefreshes;
	Player->Funds -= Cost;
	Player->FundsSpentThisRound += Cost;
	++Player->RefreshesThisRound;''')

# Sell: Stronghold-Protocol sells every operator (normal or elite) for the tier's sell price.
rep('''	const int32 SalePrice = SoldUnit.bIsTransformClone ? 0
		: FMath::Max(0, SoldUnit.Cost * FMath::Max(1, SoldUnit.PoolCopiesHeld) - (SoldUnit.UnitStar > 1 ? 1 : 0));''', '''	int32 SalePrice = SoldUnit.bIsTransformClone ? 0
		: FMath::Max(0, SoldUnit.Cost * FMath::Max(1, SoldUnit.PoolCopiesHeld) - (SoldUnit.UnitStar > 1 ? 1 : 0));
	if (HasN1Economy() && !SoldUnit.bIsTransformClone)
	{
		const int32* Sell = PactData->Economy.SellByTier.Find(SoldUnit.OperatorTier);
		SalePrice = Sell ? *Sell : 1;
	}''')

# "Buy experience" becomes "upgrade the 调度中心" under N1.
rep('''	if (Player->Level >= 9)
	{
		return Reject(ETreadM1RejectReason::MaxLevelReached, RequestId);
	}
	if (Player->Funds < MatchState.Rules.ExperiencePurchaseCost)''', '''	if (HasN1Economy())
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
	if (Player->Funds < MatchState.Rules.ExperiencePurchaseCost)''')

# Income: Stronghold-Protocol income table, no interest or streak.
rep('''	FTreadM1IncomeBreakdown Income;
	Income.Base = MatchState.Rules.BaseIncome;''', '''	FTreadM1IncomeBreakdown Income;
	if (HasN1Economy())
	{
		const FTreadN1Economy& Economy = PactData->Economy;
		Income.Base = Economy.IncomeForRound(MatchState.RoundIndex + 1);
		Income.Interest = Economy.bInterest && MatchState.Rules.InterestFundsStep > 0 ? FMath::Min(MatchState.Rules.MaxInterest, Player.Funds / MatchState.Rules.InterestFundsStep) : 0;
		// Band 坎诺特: leftover funds carry over, +1 when at least 5 remain.
		if (Player.Flags.Contains(TEXT("flag:CarryOverFunds")) && Player.Funds >= 5) Income.Interest += 1;
		Income.Streak = Economy.bStreakIncome ? StreakReward(Player) : 0;
		Income.Other = Player.PendingTraitIncome;
		return Income;
	}
	Income.Base = MatchState.Rules.BaseIncome;''')

# Settlement: leftover funds are lost (unless carried over); no experience under N1.
rep('''		const FTreadM1IncomeBreakdown IncomeBreakdown = CalculateIncome(Player);
		const int32 Income = IncomeBreakdown.Base + IncomeBreakdown.Interest + IncomeBreakdown.Streak + IncomeBreakdown.Other;
		Player.Funds += Income;''', '''		const FTreadM1IncomeBreakdown IncomeBreakdown = CalculateIncome(Player);
		const int32 Income = IncomeBreakdown.Base + IncomeBreakdown.Interest + IncomeBreakdown.Streak + IncomeBreakdown.Other;
		if (HasN1Economy() && PactData->Economy.bLeftoverFundsLost && !Player.Flags.Contains(TEXT("flag:CarryOverFunds")))
		{
			Player.Funds = 0;
		}
		Player.Funds += Income;''')
rep('''		DispatchTraitEvent(Player, ETreadM2Trigger::Settlement, TEXT("Settlement"));
		ApplyExperience(Player, 2);''', '''		DispatchTraitEvent(Player, ETreadM2Trigger::Settlement, TEXT("Settlement"));
		if (!HasN1Economy()) ApplyExperience(Player, 2);''')

# New round: upgrade discount grows, per-round counters reset.
rep('''	for (FTreadM1PlayerState& Player : MatchState.Players)
	{
		Player.AcquiredThisRound = 0;
		Player.FundsSpentThisRound = 0;
	}''', '''	for (FTreadM1PlayerState& Player : MatchState.Players)
	{
		Player.AcquiredThisRound = 0;
		Player.FundsSpentThisRound = 0;
		Player.RefreshesThisRound = 0;
		if (HasN1Economy())
		{
			++Player.ShopUpgradeDiscount;
			Player.ExperienceToNextLevel = ShopUpgradeCost(Player);
		}
	}''')

# Strategies: the 40 Stronghold-Protocol bands when generated.
rep('''	const FString FilePath = FPaths::Combine(FPaths::ProjectContentDir(), TEXT("Data/Strategies.json"));''', '''	FString FilePath = FPaths::Combine(FPaths::ProjectContentDir(), TEXT("Data/Generated/Strategies40.json"));
	if (!FPaths::FileExists(FilePath)) FilePath = FPaths::Combine(FPaths::ProjectContentDir(), TEXT("Data/Strategies.json"));''')

p.write_text(s, encoding="utf-8")
print("patched controller")
