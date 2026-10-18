// Native M2 acceptance fixture: pact thresholds, harmony, bench counting, equipment pacts,
// event-bus coverage, stack modes, X/Y elite values, strategy bus and Scout/battle consistency.
// Fixture characters are selected by trait data properties, never by hard-coded operator names.

#include "TreadM1MatchController.h"

#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "HAL/FileManager.h"
#include "Misc/Crc.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

namespace
{
	int32 CardNumber(const FString& CharacterId)
	{
		return FCString::Atoi(*CharacterId.RightChop(5));
	}

	bool SamePacts(const TArray<FTreadM2PactProgress>& A, const TArray<FTreadM2PactProgress>& B)
	{
		if (A.Num() != B.Num()) return false;
		for (int32 Index = 0; Index < A.Num(); ++Index)
		{
			if (A[Index].PactId != B[Index].PactId || A[Index].Count != B[Index].Count || A[Index].Stacks != B[Index].Stacks ||
				A[Index].ActiveTier != B[Index].ActiveTier) return false;
		}
		return true;
	}
}

bool ATreadM1MatchController::WriteM2SelfTestReport(const FString& Path, const TMap<FString, bool>& NamedChecks,
	const TArray<FString>& Notes, const TSharedPtr<FJsonObject>& Extra) const
{
	TSharedPtr<FJsonObject> Root = Extra.IsValid() ? Extra : MakeShared<FJsonObject>();
	bool bOk = NamedChecks.Num() > 0;
	TSharedPtr<FJsonObject> Named = MakeShared<FJsonObject>();
	for (const TPair<FString, bool>& Check : NamedChecks)
	{
		Named->SetBoolField(Check.Key, Check.Value);
		bOk &= Check.Value;
	}
	Root->SetStringField(TEXT("schema"), TEXT("Tread.M2.PactSelfTest.v1"));
	Root->SetStringField(TEXT("producer"), TEXT("Tread C++ RunM2PactSelfTest"));
	Root->SetBoolField(TEXT("ok"), bOk);
	Root->SetObjectField(TEXT("namedChecks"), Named);
	TArray<TSharedPtr<FJsonValue>> NoteValues;
	for (const FString& Note : Notes) NoteValues.Add(MakeShared<FJsonValueString>(Note));
	Root->SetArrayField(TEXT("notes"), NoteValues);
	FString Output;
	FJsonSerializer::Serialize(Root.ToSharedRef(), TJsonWriterFactory<>::Create(&Output));
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(Path), true);
	return FFileHelper::SaveStringToFile(Output + TEXT("\n"), *Path, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
}

bool ATreadM1MatchController::RunM2PactSelfTest(const FString& OutputPath)
{
	const int64 Seed = 20260926;
	TMap<FString, bool> Checks;
	TArray<FString> Notes;
	TSharedPtr<FJsonObject> Extra = MakeShared<FJsonObject>();
	const auto Check = [&Checks](const FString& Name, bool bPassed)
	{
		const bool* Previous = Checks.Find(Name);
		Checks.Add(Name, bPassed && (!Previous || *Previous));
	};

	// ------------------------------------------------------------------ helpers
	const auto StartPreparation = [this, Seed]()
	{
		InitializeMatch(Seed);
		BeginPreMatchBP(TEXT("m2-bp"));
		ChoosePlayerStrategy(MatchState.BP.AvailableStrategyIds[0], TEXT("m2-player"));
		for (int32 Pick = 0; Pick < 3; ++Pick) RunNextAIPick(FString::Printf(TEXT("m2-ai-%d"), Pick));
		ConfirmPreMatchBP(TEXT("m2-confirm"));
		MatchState.PhaseTimeRemainingSec = 600.0f;
		for (FTreadM1PlayerState& Player : MatchState.Players) Player.Health = 1000;
	};
	const auto ClearFixture = [](FTreadM1PlayerState& Player)
	{
		// Pact-math fixtures only; pool-ledger scenarios below use real commands instead.
		Player.BoardUnits.Reset();
		Player.BenchUnits.Reset();
		Player.BenchUnitInstanceIds.Init(FString(), 8);
		Player.PopulationUsed = 0;
		Player.Pacts.Reset();
		Player.PactModifiers.Reset();
		Player.EquipmentIds.Reset();
	};
	const auto Inject = [this](FTreadM1PlayerState& Player, const FString& CharacterId, FIntPoint Cell, int32 Star = 1, bool bBench = false)
	{
		FTreadM1UnitInstance Unit;
		Unit.UnitInstanceId = FString::Printf(TEXT("%s_m2fx_%04d"), *Player.PlayerId, ++UnitInstanceSequence);
		Unit.CharacterId = CharacterId;
		Unit.OriginalOperatorName = CharacterId;
		Unit.OperatorTier = CardTier(CharacterId).IsEmpty() ? TEXT("I") : CardTier(CharacterId);
		Unit.UnitStar = Star;
		Unit.Cost = 1;
		Unit.OwnerPlayerId = Player.PlayerId;
		Unit.PoolCopiesHeld = 0;
		if (bBench)
		{
			Unit.Location = ETreadM1UnitLocation::Bench;
			const int32 Slot = Player.BenchUnitInstanceIds.Find(FString());
			if (Slot != INDEX_NONE) Player.BenchUnitInstanceIds[Slot] = Unit.UnitInstanceId;
			Player.BenchUnits.Add(Unit);
		}
		else
		{
			Unit.Location = ETreadM1UnitLocation::Board;
			Unit.BoardCell = Cell;
			Player.BoardUnits.Add(Unit);
			++Player.PopulationUsed;
		}
		RecomputePacts(Player);
		return Unit.UnitInstanceId;
	};
	const auto IsHarmonyCard = [this](const FTreadM2Card& Card)
	{
		for (const FString& Pact : Card.AdjunctPacts)
		{
			const FTreadM2PactDef* Def = PactData->FindPact(Pact);
			if (Def && Def->bHarmony) return true;
		}
		return false;
	};
	const auto Members = [this, &IsHarmonyCard](const FString& PactId, const FString& Exclude = FString())
	{
		TArray<FString> Result;
		for (const FString& Id : PactData->CardOrder)
		{
			const FTreadM2Card& Card = PactData->Cards[Id];
			const bool bMember = Card.CorePacts.Contains(PactId) || Card.AdjunctPacts.Contains(PactId);
			const FTreadM2PactDef* Def = PactData->FindPact(PactId);
			if (bMember && Id != Exclude && (Def->bHarmony || !IsHarmonyCard(Card))) Result.Add(Id);
		}
		return Result;
	};
	const auto FindCard = [this](TFunctionRef<bool(const FTreadM2Card&, const FTreadM2Trait&)> Predicate, bool bShopRange = false)
	{
		for (const FString& Id : PactData->CardOrder)
		{
			const FTreadM2Card& Card = PactData->Cards[Id];
			if (bShopRange && !HasN1Economy() && CardNumber(Id) > 32) continue;
			for (const FTreadM2Trait& Trait : Card.Traits)
			{
				if (Predicate(Card, Trait)) return Id;
			}
		}
		return FString();
	};
	const auto HasOp = [](const FTreadM2Trait& Trait, const TCHAR* Op)
	{
		return Trait.Effects.ContainsByPredicate([Op](const FTreadM2Effect& Effect) { return Effect.Op == Op; });
	};
	const auto Progress = [this](const FString& PlayerId, const FString& PactId) -> FTreadM2PactProgress
	{
		const FTreadM1PlayerState* Player = FindPlayer(PlayerId);
		const FTreadM2PactProgress* Found = Player ? FindPactProgress(*Player, PactId) : nullptr;
		return Found ? *Found : FTreadM2PactProgress();
	};
	// Fill board row 7 upward with members so PactId reaches its first threshold.
	const auto ActivateWithMembers = [&](FTreadM1PlayerState& Player, const FString& PactId, const FString& Exclude, int32 StartX = 0, int32 Row = 7)
	{
		const FTreadM2PactDef* Def = PactData->FindPact(PactId);
		int32 X = StartX;
		for (const FString& Id : Members(PactId, Exclude))
		{
			const FTreadM2PactProgress* Current = FindPactProgress(Player, PactId);
			if (Current && Current->bActive) break;
			if (Player.BoardUnits.ContainsByPredicate([&](const FTreadM1UnitInstance& U) { return U.CharacterId == Id; })) continue;
			Inject(Player, Id, FIntPoint(X % 8, Row - X / 8));
			++X;
		}
		return Def && FindPactProgress(Player, PactId) && FindPactProgress(Player, PactId)->bActive;
	};
	const auto LogHas = [this](int32 FromSequence, const FString& Trigger, const FString& Event, const FString& Status = FString(), const FString& PactId = FString())
	{
		for (int32 Index = FMath::Max(0, FromSequence); Index < MatchState.TraitLog.Num(); ++Index)
		{
			const FTreadM2TraitLogEntry& Entry = MatchState.TraitLog[Index];
			if ((Trigger.IsEmpty() || Entry.Trigger == Trigger) && (Event.IsEmpty() || Entry.Event == Event) &&
				(Status.IsEmpty() || Entry.Status.StartsWith(Status)) && (PactId.IsEmpty() || Entry.PactId == PactId)) return true;
		}
		return false;
	};
	const auto StockShop = [this](FTreadM1PlayerState& Player, int32 SlotIndex, const FString& CharacterId, const FString& Tier)
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
	};

	// ------------------------------------------------------------------ A. data
	InitializeMatch(Seed);
	if (!IsPactDataLoaded())
	{
		Check(TEXT("dataLoaded"), false);
		Notes.Add(MatchState.PactDataVersion);
		const FString Path = OutputPath.IsEmpty() ? FPaths::Combine(FPaths::ProjectDir(), TEXT("Saved/Reports/M2_Pact_SelfTest.json")) : OutputPath;
		WriteM2SelfTestReport(Path, Checks, Notes, Extra);
		return false;
	}
	int32 CoreCount = 0;
	int32 AdjunctCount = 0;
	for (const FTreadM2PactDef& Def : PactData->Pacts)
	{
		CoreCount += Def.Kind == TEXT("Core") ? 1 : 0;
		AdjunctCount += Def.Kind == TEXT("Adjunct") ? 1 : 0;
	}
	Check(TEXT("dataLoaded"), true);
	Check(TEXT("pacts8Core15Adjunct"), CoreCount == 8 && AdjunctCount == 15);
	bool bEveryCardHasTrait = PactData->Cards.Num() == (HasN1Economy() ? 112 : 100);
	TSet<FString> TriggerKinds;
	for (const TPair<FString, FTreadM2Card>& Pair : PactData->Cards)
	{
		bEveryCardHasTrait &= Pair.Value.Traits.Num() >= 1;
		for (const FTreadM2Trait& Trait : Pair.Value.Traits) TriggerKinds.Add(FTreadM2PactData::TriggerName(Trait.Trigger));
	}
	Check(TEXT("hundredCardsEachWithTrait"), bEveryCardHasTrait);
	Check(TEXT("traitTriggerCoverage"), TriggerKinds.Contains(TEXT("Acquire")) && TriggerKinds.Contains(TEXT("RoundStart")) &&
		TriggerKinds.Contains(TEXT("RoundEnd")) && TriggerKinds.Contains(TEXT("Battle")) && TriggerKinds.Contains(TEXT("Sell")));

	// ------------------------------------------------------------------ B. thresholds on real boards
	TArray<TSharedPtr<FJsonValue>> ActivationRows;
	bool bThresholds = true;
	bool bDefaultsAndSpecials = true;
	for (const FTreadM2PactDef& Def : PactData->Pacts)
	{
		TArray<FString> PactMembers = Members(Def.PactId);
		const int32 FixtureStar = Def.bCountsEliteAll ? 2 : 1;
		if (Def.bCountsEliteAll)
		{
			for (const FString& Id : PactData->CardOrder)
			{
				if (PactMembers.Num() >= Def.Thresholds.Last() + 1) break;
				if (!IsHarmonyCard(PactData->Cards[Id])) PactMembers.Add(Id);
			}
		}
		int32 MaxTierReached = 0;
		bool bPactOk = true;
		for (int32 Count = 0; Count <= PactMembers.Num() && Count <= Def.Thresholds.Last() + 1; ++Count)
		{
			FTreadM1PlayerState& Player = MatchState.Players[1];
			ClearFixture(Player);
			RecomputePacts(Player);
			for (int32 Index = 0; Index < Count; ++Index) Inject(Player, PactMembers[Index], FIntPoint(Index % 8, 4 + Index / 8), FixtureStar);
			const FTreadM2PactProgress* Current = FindPactProgress(Player, Def.PactId);
			int32 Expected = 0;
			for (int32 Tier = 0; Tier < Def.Thresholds.Num(); ++Tier) Expected = Count >= Def.Thresholds[Tier] ? Tier + 1 : Expected;
			// document/166: 独行 (the only capped bond) is switched off again by a second member.
			if (Def.MaxCount > 0 && Count > Def.MaxCount) Expected = 0;
			// Distinct members on board give Count; harmony bonus only applies with a harmony card (excluded here).
			bPactOk &= Current && Current->Count == Count && Current->ActiveTier == Expected && Current->bActive == (Expected > 0);
			MaxTierReached = FMath::Max(MaxTierReached, Current ? Current->ActiveTier : 0);
		}
		bThresholds &= bPactOk;
		TSharedPtr<FJsonObject> Row = MakeShared<FJsonObject>();
		Row->SetStringField(TEXT("pactId"), Def.PactId);
		Row->SetStringField(TEXT("kind"), Def.Kind);
		Row->SetStringField(TEXT("thresholds"), FString::JoinBy(Def.Thresholds, TEXT("/"), [](int32 V) { return FString::FromInt(V); }));
		Row->SetNumberField(TEXT("members"), PactMembers.Num());
		Row->SetNumberField(TEXT("maxTierReachedOnBoard"), MaxTierReached);
		Row->SetNumberField(TEXT("tiers"), Def.Thresholds.Num());
		Row->SetBoolField(TEXT("allTiersReachable"), MaxTierReached == Def.Thresholds.Num());
		Row->SetBoolField(TEXT("thresholdMathOk"), bPactOk);
		Row->SetStringField(TEXT("sourceStatus"), Def.SourceStatus);
		ActivationRows.Add(MakeShared<FJsonValueObject>(Row));
		if (MaxTierReached == 0) bThresholds = false;
		if (MaxTierReached < Def.Thresholds.Num())
		{
			Notes.Add(FString::Printf(TEXT("%s: only %d member cards, tier %d/%d reachable (thresholds %s, %s)"), *Def.PactId, PactMembers.Num(),
				MaxTierReached, Def.Thresholds.Num(), *FString::JoinBy(Def.Thresholds, TEXT("/"), [](int32 V) { return FString::FromInt(V); }), *Def.SourceStatus));
		}
		if (Def.SourceStatus == TEXT("missing-in-reference"))
		{
			bDefaultsAndSpecials &= Def.Thresholds == (Def.Kind == TEXT("Core") ? TArray<int32>{3, 6} : TArray<int32>{2, 3});
		}
	}
	Extra->SetArrayField(TEXT("pactActivation"), ActivationRows);
	Check(TEXT("everyPactActivatesByThreshold"), bThresholds);
	const FTreadM2PactDef* Harmony = PactData->Pacts.FindByPredicate([](const FTreadM2PactDef& Def) { return Def.bHarmony; });
	const FTreadM2PactDef* Agir = PactData->FindPact(TEXT("阿戈尔"));
	bDefaultsAndSpecials &= Harmony && Harmony->Thresholds == TArray<int32>{1};
	bDefaultsAndSpecials &= Agir && Agir->Thresholds == TArray<int32>{3, 5};
	Check(TEXT("specialThresholdsFromData"), bDefaultsAndSpecials);

	// 技力 (document/167): the SP numbers from bonds.json must reach the runtime pact definitions.
	{
		const FTreadM2PactDef* Swift = PactData->FindPact(TEXT("迅捷"));
		const FTreadM2PactDef* Sunts = PactData->FindPact(TEXT("绝技"));
		const FTreadM2PactDef* Solo = PactData->FindPact(TEXT("独行"));
		const bool bSpLoaded = Swift && Swift->SpPerAttack == 12 && FMath::IsNearlyEqual(Swift->SpChance, 0.2f, 0.001f)
			&& Sunts && FMath::IsNearlyEqual(Sunts->SpCostRatio, 0.7f, 0.001f)
			&& Solo && Solo->SpInitial == 15;
		Check(TEXT("spNumbersFromData"), bSpLoaded);
	}

	// ------------------------------------------------------------------ C. harmony
	{
		FTreadM1PlayerState& Player = MatchState.Players[1];
		const FString HarmonyCard = FindCard([&](const FTreadM2Card& Card, const FTreadM2Trait&) { return IsHarmonyCard(Card); });
		FString CorePact;
		for (const FTreadM2PactDef& Def : PactData->Pacts)
		{
			if (Def.Kind == TEXT("Core") && Def.Thresholds.Num() >= 2 && Members(Def.PactId).Num() >= Def.Thresholds[1] - 1) { CorePact = Def.PactId; break; }
		}
		const FTreadM2PactDef* Core = PactData->FindPact(CorePact);
		bool bHarmony = !HarmonyCard.IsEmpty() && Core;
		if (bHarmony)
		{
			const TArray<FString> CoreMembers = Members(CorePact);
			// Below the first threshold: harmony does not create an activation.
			ClearFixture(Player);
			for (int32 Index = 0; Index < Core->Thresholds[0] - 1; ++Index) Inject(Player, CoreMembers[Index], FIntPoint(Index, 4));
			Inject(Player, HarmonyCard, FIntPoint(7, 7));
			bHarmony &= Progress(TEXT("P1"), CorePact).HarmonyBonus == 0 && !Progress(TEXT("P1"), CorePact).bActive;
			// One below the second threshold plus harmony reaches the second tier.
			ClearFixture(Player);
			for (int32 Index = 0; Index < Core->Thresholds[1] - 1; ++Index) Inject(Player, CoreMembers[Index], FIntPoint(Index % 8, 4 + Index / 8));
			const int32 TierWithout = Progress(TEXT("P1"), CorePact).ActiveTier;
			const FString HarmonyUnit = Inject(Player, HarmonyCard, FIntPoint(7, 7));
			const FTreadM2PactProgress After = Progress(TEXT("P1"), CorePact);
			bHarmony &= TierWithout == 1 && After.HarmonyBonus == 1 && After.Count == Core->Thresholds[1] && After.ActiveTier == 2;
			const FTreadM1UnitInstance* Unit = FindOwnedUnit(Player, HarmonyUnit);
			bHarmony &= Unit && GetUnitPacts(Player, *Unit, true).Contains(CorePact) && !GetUnitPacts(Player, *Unit, false).Contains(CorePact);
		}
		Check(TEXT("harmonyCountsActiveCorePlusOne"), bHarmony);
	}

	// ------------------------------------------------------------------ D. bench counting
	{
		FTreadM1PlayerState& Player = MatchState.Players[1];
		FString BenchPact;
		FString BoardOnlyPact;
		for (const FTreadM2PactDef& Def : PactData->Pacts)
		{
			if (Def.bCountsBench && BenchPact.IsEmpty() && Members(Def.PactId).Num() >= Def.Thresholds[0]) BenchPact = Def.PactId;
			if (!Def.bCountsBench && !Def.bHarmony && BoardOnlyPact.IsEmpty() && Members(Def.PactId).Num() >= Def.Thresholds[0]) BoardOnlyPact = Def.PactId;
		}
		ClearFixture(Player);
		const FTreadM2PactDef* Def = PactData->FindPact(BenchPact);
		const TArray<FString> BenchMembers = Members(BenchPact);
		for (int32 Index = 0; Def && Index < Def->Thresholds[0]; ++Index) Inject(Player, BenchMembers[Index], FIntPoint(-1, -1), 1, true);
		const FTreadM2PactDef* BoardDef = PactData->FindPact(BoardOnlyPact);
		const TArray<FString> BoardMembers = Members(BoardOnlyPact);
		for (int32 Index = 0; BoardDef && Index < BoardDef->Thresholds[0]; ++Index)
		{
			if (!Player.BenchUnits.ContainsByPredicate([&](const FTreadM1UnitInstance& U) { return U.CharacterId == BoardMembers[Index]; }))
				Inject(Player, BoardMembers[Index], FIntPoint(-1, -1), 1, true);
		}
		const FTreadM2PactProgress Bench = Progress(TEXT("P1"), BenchPact);
		const FTreadM2PactProgress BoardOnly = Progress(TEXT("P1"), BoardOnlyPact);
		Check(TEXT("benchCountsForEconomyPacts"), Def && Bench.bActive && Bench.BenchCount >= Def->Thresholds[0] && Bench.BoardCount == 0 &&
			BoardDef && !BoardOnly.bActive && BoardOnly.Count == 0);
		TArray<FString> BenchPacts;
		for (const FTreadM2PactDef& Each : PactData->Pacts) if (Each.bCountsBench) BenchPacts.Add(Each.PactId);
		Extra->SetStringField(TEXT("benchCountedPacts"), FString::Join(BenchPacts, TEXT(",")));
	}

	// ------------------------------------------------------------------ E-L. live command scenario (deterministic, replayed twice)
	const auto Scenario = [&](bool bRecordChecks) -> FString
	{
		const auto ScenarioCheck = [&](const FString& Name, bool bPassed) { if (bRecordChecks) Check(Name, bPassed); };
		StartPreparation();
		FTreadM1PlayerState& P0 = MatchState.Players[0];
		P0.Funds = 200;
		// Clear P0 through real sell commands so the shared ledger stays exact.
		while (P0.BoardUnits.Num() > 0) SellUnit(TEXT("P0"), P0.BoardUnits[0].UnitInstanceId);
		while (P0.BenchUnits.Num() > 0) SellUnit(TEXT("P0"), P0.BenchUnits[0].UnitInstanceId);
		P0.Funds = 200;

		// Acquire with activationRequired=false stacks inactive pacts.
		const FString NoActCard = FindCard([&](const FTreadM2Card&, const FTreadM2Trait& T)
		{
			return T.Trigger == ETreadM2Trigger::Acquire && !T.bActivationRequired && T.Effects.Num() == 1 &&
				T.Effects[0].PactSelector == TEXT("OwnPacts") && T.Effects[0].AmountScale == TEXT("Fixed");
		}, true);
		const FTreadM2Card* NoAct = PactData->FindCard(NoActCard);
		int32 From = MatchState.TraitLog.Num();
		bool bNoAct = NoAct && StockShop(P0, 0, NoActCard, TEXT("I")) && PurchaseShopSlot(TEXT("P0"), 0, TEXT("m2-buy-noact-1")).bAccepted;
		const FString FirstPact = NoAct ? (NoAct->CorePacts.Num() > 0 ? NoAct->CorePacts[0] : NoAct->AdjunctPacts[0]) : FString();
		const int32 BaseValue = NoAct ? FMath::RoundToInt(NoAct->Traits[0].Effects[0].BaseValue) : 0;
		const int32 EliteValue = NoAct ? FMath::RoundToInt(NoAct->Traits[0].Effects[0].EliteValue) : 0;
		bNoAct &= !Progress(TEXT("P0"), FirstPact).bActive && Progress(TEXT("P0"), FirstPact).Stacks == BaseValue;
		ScenarioCheck(TEXT("inactiveStackingWhenActivationNotRequired"), bNoAct && LogHas(From, TEXT("Acquire"), TEXT("Purchase"), TEXT("applied"), FirstPact));
		ScenarioCheck(TEXT("eventAcquireOnPurchase"), LogHas(From, TEXT("Acquire"), TEXT("Purchase"), TEXT("event")));

		// Three copies -> automatic 2-star combine, elite value on the combined acquire, pool copies held.
		const FTreadM1PoolBalance BalanceBefore = GetPoolBalance(NoActCard, TEXT("I"));
		From = MatchState.TraitLog.Num();
		bool bCombine = StockShop(P0, 1, NoActCard, TEXT("I")) && PurchaseShopSlot(TEXT("P0"), 1, TEXT("m2-buy-noact-2")).bAccepted &&
			StockShop(P0, 2, NoActCard, TEXT("I")) && PurchaseShopSlot(TEXT("P0"), 2, TEXT("m2-buy-noact-3")).bAccepted;
		const FTreadM1UnitInstance* Combined = P0.BenchUnits.FindByPredicate([&](const FTreadM1UnitInstance& U) { return U.CharacterId == NoActCard; });
		const FString CombinedId = Combined ? Combined->UnitInstanceId : FString();
		const int32 SameCharacterUnits = P0.BenchUnits.FilterByPredicate([&](const FTreadM1UnitInstance& U) { return U.CharacterId == NoActCard; }).Num();
		bCombine &= Combined && SameCharacterUnits == 1 && Combined->UnitStar == 2 && Combined->PoolCopiesHeld == 3 &&
			GetPoolBalance(NoActCard, TEXT("I")).OwnedCopies == BalanceBefore.OwnedCopies + 2 && ValidatePoolLedger();
		ScenarioCheck(TEXT("eventCombineThreeCopies"), bCombine && LogHas(From, TEXT("Combine"), TEXT("Combine"), TEXT("event")));
		ScenarioCheck(TEXT("eliteValueOnCombinedAcquire"), bCombine && LogHas(From, TEXT("Acquire"), TEXT("CombineResult"), TEXT("applied"), FirstPact) &&
			Progress(TEXT("P0"), FirstPact).Stacks == BaseValue * 3 + EliteValue);
		ScenarioCheck(TEXT("valueTextXY"), GetTraitValueText(NoActCard, 1) == FString::Printf(TEXT("[%d]/%d"), BaseValue, EliteValue) &&
			GetTraitValueText(NoActCard, 2) == FString::Printf(TEXT("%d/[%d]"), BaseValue, EliteValue));

		// Combine-copies override (2 copies) from data.
		const FString TwoCopyCard = FindCard([&](const FTreadM2Card& C, const FTreadM2Trait&) { return C.CombineCopies == 2; }, true);
		bool bTwoCopy = !TwoCopyCard.IsEmpty() && StockShop(P0, 3, TwoCopyCard, TEXT("II")) && PurchaseShopSlot(TEXT("P0"), 3, TEXT("m2-buy-two-1")).bAccepted &&
			StockShop(P0, 4, TwoCopyCard, TEXT("II")) && PurchaseShopSlot(TEXT("P0"), 4, TEXT("m2-buy-two-2")).bAccepted;
		const FTreadM1UnitInstance* TwoStar = P0.BenchUnits.FindByPredicate([&](const FTreadM1UnitInstance& U) { return U.CharacterId == TwoCopyCard; });
		ScenarioCheck(TEXT("combineCopiesFromData"), bTwoCopy && TwoStar && TwoStar->UnitStar == 2 && TwoStar->PoolCopiesHeld == 2);
		const FString TwoStarId = TwoStar ? TwoStar->UnitInstanceId : FString();

		// Deploy / undeploy events.
		From = MatchState.TraitLog.Num();
		const bool bDeploy = MoveUnitToBoard(TEXT("P0"), CombinedId, FIntPoint(0, 7), TEXT("m2-deploy")).bAccepted;
		const bool bUndeploy = MoveUnitToBench(TEXT("P0"), CombinedId, TEXT("m2-undeploy")).bAccepted;
		ScenarioCheck(TEXT("eventDeployUndeploy"), bDeploy && bUndeploy && LogHas(From, TEXT("Deploy"), TEXT("MoveToBoard"), TEXT("event")) &&
			LogHas(From, TEXT("Undeploy"), TEXT("MoveToBench"), TEXT("event")));

		// Sell a combined unit: refund held copies minus one, return 3 copies, sale trait/strategy bus event.
		From = MatchState.TraitLog.Num();
		const int32 FundsBeforeSell = P0.Funds;
		const FTreadM1PoolBalance BeforeSell = GetPoolBalance(NoActCard, TEXT("I"));
		const int32 CostEach = PurchaseCostFor(NoActCard, 1);
		const bool bSold = SellUnit(TEXT("P0"), CombinedId, TEXT("m2-sell-combined")).bAccepted;
		// N1 (Stronghold-Protocol): every operator, normal or elite, sells for the tier's sell price.
		const int32* N1Sell = HasN1Economy() ? PactData->Economy.SellByTier.Find(CardTier(NoActCard)) : nullptr;
		const int32 ExpectedRefund = HasN1Economy() ? (N1Sell ? *N1Sell : 1) : FMath::Max(0, CostEach * 3 - 1);
		ScenarioCheck(TEXT("eventSellCombinedRefund"), bSold && P0.Funds == FundsBeforeSell + ExpectedRefund &&
			GetPoolBalance(NoActCard, TEXT("I")).PoolCopiesAvailable == BeforeSell.PoolCopiesAvailable + 3 && ValidatePoolLedger() &&
			LogHas(From, TEXT("Sell"), TEXT("Sell"), TEXT("event")));

		// Sell trait -> funds promised for the next settlement (paid as IncomeBreakdown.Other).
		const FString SellFundsCard = FindCard([&](const FTreadM2Card&, const FTreadM2Trait& T)
		{
			return T.Trigger == ETreadM2Trigger::Sell && HasOp(T, TEXT("GainFundsNextRound"));
		}, true);
		From = MatchState.TraitLog.Num();
		const int32 PendingBefore = P0.PendingTraitIncome;
		const bool bSellTrait = StockShop(P0, 0, SellFundsCard, TEXT("III")) && PurchaseShopSlot(TEXT("P0"), 0, TEXT("m2-buy-sellfunds")).bAccepted &&
			SellUnit(TEXT("P0"), P0.BenchUnits.Last().UnitInstanceId, TEXT("m2-sell-funds")).bAccepted;
		ScenarioCheck(TEXT("sellTraitPromisesFunds"), bSellTrait && P0.PendingTraitIncome > PendingBefore &&
			LogHas(From, TEXT("Sell"), TEXT("Sell"), TEXT("applied")) && P0.NextRoundIncome.Other == P0.PendingTraitIncome);

		// Equipment-provided pact: grant an item that provides a pact and equip it.
		const FTreadM2Item* PactItem = PactData->Items.FindByPredicate([](const FTreadM2Item& Item) { return Item.ProvidesPacts.Num() > 0; });
		bool bEquip = PactItem != nullptr && !TwoStarId.IsEmpty();
		if (bEquip)
		{
			From = MatchState.TraitLog.Num();
			const FString ItemPact = PactItem->ProvidesPacts[0];
			const int32 CountBefore = Progress(TEXT("P0"), ItemPact).Count;
			GrantItemToPlayer(P0, PactItem->DisplayName, 1, TEXT("m2-fixture"), ETreadM2Trigger::Passive);
			bEquip &= MoveUnitToBoard(TEXT("P0"), TwoStarId, FIntPoint(1, 7), TEXT("m2-deploy-two")).bAccepted &&
				EquipItem(TEXT("P0"), PactItem->ItemId, TwoStarId, TEXT("m2-equip")).bAccepted;
			const FTreadM1UnitInstance* Equipped = FindOwnedUnit(P0, TwoStarId);
			bEquip &= Equipped && GetUnitPacts(P0, *Equipped, false).Contains(ItemPact) && Progress(TEXT("P0"), ItemPact).Count == CountBefore + 1 &&
				LogHas(From, TEXT("Equip"), TEXT("Equip"), TEXT("applied"));
			bEquip &= !EquipItem(TEXT("P0"), PactItem->ItemId, TwoStarId, TEXT("m2-equip-missing")).bAccepted;
		}
		ScenarioCheck(TEXT("equipmentProvidesPact"), bEquip);

		// Strategy bus: MatchStart funds, BattleStart pact stacks, and deferred effects are all observable.
		const FTreadM2StrategyBus* FundsStrategy = PactData->Strategies.FindByPredicate([](const FTreadM2StrategyBus& Bus)
		{
			return Bus.Trigger == TEXT("MatchStart") && Bus.Effects.Num() > 0 && Bus.Effects[0].bApplied && Bus.Effects[0].Effect.Op == TEXT("GainFunds");
		});
		const FTreadM2StrategyBus* StackStrategy = PactData->Strategies.FindByPredicate([](const FTreadM2StrategyBus& Bus)
		{
			return Bus.Trigger == TEXT("BattleStart") && Bus.Effects.Num() > 0 && Bus.Effects[0].bApplied && Bus.Effects[0].Effect.Op == TEXT("AddStacks");
		});
		const FTreadM2StrategyBus* DeferredStrategy = PactData->Strategies.FindByPredicate([](const FTreadM2StrategyBus& Bus)
		{
			return Bus.Trigger == TEXT("RoundStart") && Bus.Effects.Num() > 0 && !Bus.Effects[0].bApplied;
		});
		if (HasN1Economy())
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
		else if (bStrategy)
		{
			From = MatchState.TraitLog.Num();
			P0.InitialStrategyId = FundsStrategy->StrategyId;
			const int32 FundsBefore = P0.Funds;
			DispatchTraitEvent(P0, ETreadM2Trigger::MatchStart, TEXT("MatchStart"));
			bStrategy &= P0.Funds == FundsBefore + FMath::RoundToInt(FundsStrategy->Effects[0].Effect.BaseValue);
			P0.InitialStrategyId = DeferredStrategy->StrategyId;
			DispatchTraitEvent(P0, ETreadM2Trigger::RoundStart, TEXT("EnterPreparation"));
			bStrategy &= LogHas(From, TEXT("RoundStart"), TEXT("EnterPreparation"), TEXT("deferred-M4"));
			P0.InitialStrategyId = StackStrategy->StrategyId;
		}

		// RoundEnd: same-row condition (同行) and self+neighbour (邻格) stacking on the live deploy path.
		const FString RowCard = FindCard([&](const FTreadM2Card&, const FTreadM2Trait& T)
		{
			// M2 data: "若同一行有N名干员" (condition); Stronghold-Protocol: "同一行每有1名干员" (SameRowCount scale).
			return T.Trigger == ETreadM2Trigger::RoundEnd && HasOp(T, TEXT("AddStacks")) && T.Effects[0].Pacts.Num() > 0 &&
				(T.Condition.SameRowAtLeast > 0 || T.Effects[0].AmountScale == TEXT("SameRowCount"));
		});
		const FString NeighbourCard = FindCard([&](const FTreadM2Card&, const FTreadM2Trait& T)
		{
			return T.Trigger == ETreadM2Trigger::RoundEnd && T.Targets == TEXT("SelfAndBehind1");
		});
		const FTreadM2Card* Row = PactData->FindCard(RowCard);
		const FString RowPact = Row ? Row->Traits[0].Effects[0].Pacts[0] : FString();
		Inject(P0, RowCard, FIntPoint(3, 6));
		ActivateWithMembers(P0, RowPact, RowCard, 4, 6);
		Inject(P0, NeighbourCard, FIntPoint(2, 5));
		const FTreadM2Card* NeighbourData = PactData->FindCard(NeighbourCard);
		const FString NeighbourPact = !NeighbourData ? FString() : NeighbourData->CorePacts.Num() > 0 ? NeighbourData->CorePacts[0]
			: (NeighbourData->AdjunctPacts.Num() > 0 ? NeighbourData->AdjunctPacts[0] : FString());
		ActivateWithMembers(P0, NeighbourPact, NeighbourCard, 0, 4);
		const TArray<FString> RowMembers = Members(RowPact, RowCard);
		if (RowMembers.Num() > 0) Inject(P0, RowMembers.Last(), FIntPoint(2, 6));
		RefreshScoutSnapshots();
		const int32 RowStacksBefore = Progress(TEXT("P0"), RowPact).Stacks;
		From = MatchState.TraitLog.Num();
		const bool bDeployed = DeployAndStartBattle(TEXT("m2-deploy-r1")).bAccepted;
		ScenarioCheck(TEXT("eventRoundEndOnDeploy"), bDeployed && LogHas(From, TEXT("RoundEnd"), TEXT("PreparationEnd"), TEXT("event")));
		ScenarioCheck(TEXT("stackSameRowCondition"), Progress(TEXT("P0"), RowPact).Stacks > RowStacksBefore &&
			LogHas(From, TEXT("RoundEnd"), TEXT("PreparationEnd"), TEXT("applied"), RowPact));
		bool bNeighbour = false;
		for (int32 Index = From; Index < MatchState.TraitLog.Num(); ++Index)
		{
			const FTreadM2TraitLogEntry& Entry = MatchState.TraitLog[Index];
			bNeighbour |= Entry.SourceId == PactData->FindCard(NeighbourCard)->Traits[0].Id && Entry.Status == TEXT("applied") && Entry.Op == TEXT("AddStacks");
		}
		ScenarioCheck(TEXT("stackSelfAndNeighbour"), bNeighbour);
		bool bStrategyStacks = false;
		for (int32 Index = From; Index < MatchState.TraitLog.Num() && StackStrategy; ++Index)
		{
			const FTreadM2TraitLogEntry& Entry = MatchState.TraitLog[Index];
			bStrategyStacks |= Entry.SourceId == TEXT("strategy:") + StackStrategy->StrategyId && Entry.Op == TEXT("AddStacks") && Entry.Status == TEXT("applied");
		}
		ScenarioCheck(TEXT("strategyEffectsOnEventBus"), bStrategy && bStrategyStacks);

		// Scout snapshot == frozen battle pact state == live state at deploy, for all four participants.
		bool bScoutBattle = MatchState.BattlePactStates.Num() == 4;
		for (const FTreadM2BattlePactState& State : MatchState.BattlePactStates)
		{
			const FTreadM1PlayerState* Player = FindPlayer(State.PlayerId);
			const FTreadM1ScoutSnapshot* Scout = MatchState.ScoutSnapshots.FindByPredicate([&](const FTreadM1ScoutSnapshot& S) { return S.PlayerId == State.PlayerId; });
			bScoutBattle &= Player && Scout && SamePacts(State.Pacts, Player->Pacts) && SamePacts(State.Pacts, Scout->Pacts);
			int32 StackSum = 0;
			for (const FTreadM2PactProgress& Each : State.Pacts) StackSum += Each.Stacks;
			int32 ScoutStackSum = 0;
			for (const FTreadM1PactStack& Each : Scout ? Scout->PactStacks : TArray<FTreadM1PactStack>()) ScoutStackSum += Each.StackCount;
			bScoutBattle &= StackSum == ScoutStackSum;
		}
		ScenarioCheck(TEXT("scoutMatchesBattlePactState"), bScoutBattle);

		// Battle stacking modes, driven through the generic battle-event entry point.
		const auto BattleCase = [&](const FString& Name, TFunctionRef<bool(const FTreadM2Card&, const FTreadM2Trait&)> Predicate,
			const FString& Event, int32 Repeats, FIntPoint OwnerCell, bool bActorIsFront)
		{
			const FString Card = FindCard(Predicate);
			const FTreadM2Card* Def = PactData->FindCard(Card);
			if (!Def) { ScenarioCheck(Name, false); return; }
			FTreadM1PlayerState& Player = MatchState.Players[2];
			ClearFixture(Player);
			const FString OwnerId = Inject(Player, Card, OwnerCell);
			const FTreadM2Effect* Stack = Def->Traits[0].Effects.FindByPredicate([](const FTreadM2Effect& E) { return E.Op == TEXT("AddStacks"); });
			const FString Pact = Stack && Stack->Pacts.Num() > 0 ? Stack->Pacts[0]
				: (Def->CorePacts.Num() > 0 ? Def->CorePacts[0] : Def->AdjunctPacts[0]);
			FString ActorId = OwnerId;
			if (bActorIsFront) ActorId = Inject(Player, Members(Pact, Card).Last(), OwnerCell + FIntPoint(0, -1));
			ActivateWithMembers(Player, Pact, Card, 0, 4);
			if (Def->Traits[0].Condition.SameRowAtLeast > 0)
			{
				for (int32 Extra = 0; Extra < Def->Traits[0].Condition.SameRowAtLeast; ++Extra) Inject(Player, Members(Pact, Card)[Extra], FIntPoint(Extra + 4, OwnerCell.Y));
			}
			const int32 Before = Progress(Player.PlayerId, Pact).Stacks;
			const int32 LogFrom = MatchState.TraitLog.Num();
			ResetBattleTraitState();
			for (int32 Index = 0; Index < Repeats; ++Index)
			{
				const FTreadM1UnitInstance* Actor = FindOwnedUnit(Player, ActorId);
				if (Actor) OnBattleUnitEvent(Player, Event, FTreadM1UnitInstance(*Actor));
			}
			const int32 Gained = Progress(Player.PlayerId, Pact).Stacks - Before;
			const FTreadM2Condition& Condition = Def->Traits[0].Condition;
			bool bOk = Gained > 0 && LogHas(LogFrom, TEXT("Battle"), Event, TEXT("applied"));
			if (Condition.bFirstOnly) bOk &= Gained == FMath::RoundToInt(Stack->BaseValue);
			if (Condition.Every > 1) bOk &= Gained == (Repeats / Condition.Every) * FMath::RoundToInt(Stack->BaseValue);
			if (Condition.PerBattleCap > 0) bOk &= Gained == Condition.PerBattleCap;
			if (Condition.ChanceBase < 100) bOk &= LogHas(LogFrom, TEXT("Battle"), Event, TEXT("skipped:chance"));
			ScenarioCheck(Name, bOk);
		};
		BattleCase(TEXT("stackOnKill"), [&](const FTreadM2Card&, const FTreadM2Trait& T)
			{ return T.Condition.Event == TEXT("Kill") && T.Condition.Every >= 1 && T.Condition.MaxTimes == 0 && T.Condition.PerBattleCap == 0 &&
				T.Effects[0].PactSelector == TEXT("Pacts"); },
			TEXT("Kill"), 4, FIntPoint(3, 6), false);
		BattleCase(TEXT("stackOnSelfKnockedOut"), [&](const FTreadM2Card&, const FTreadM2Trait& T)
			{ return T.Condition.Event == TEXT("SelfKnockedOut"); }, TEXT("SelfKnockedOut"), 1, FIntPoint(3, 6), false);
		BattleCase(TEXT("stackOnFirstSkillOnly"), [&](const FTreadM2Card&, const FTreadM2Trait& T)
			{ return T.Condition.Event == TEXT("SkillActivated") && T.Condition.bFirstOnly; }, TEXT("SkillActivated"), 3, FIntPoint(3, 6), false);
		BattleCase(TEXT("stackOnFrontAmmoEveryN"), [&](const FTreadM2Card&, const FTreadM2Trait& T)
			{ return T.Condition.Event == TEXT("AmmoConsumed") && (T.Condition.Source == TEXT("Front1") || T.Condition.Source == TEXT("Around4")); },
			TEXT("AmmoConsumed"), 14, FIntPoint(3, 6), true);
		BattleCase(TEXT("stackOnFrontSkillPerBattleCap"), [&](const FTreadM2Card&, const FTreadM2Trait& T)
			{ return T.Condition.PerBattleCap > 0 && T.Condition.Event == TEXT("SkillActivated") && T.Condition.Source == TEXT("Front1") &&
				T.Effects[0].PactSelector == TEXT("Pacts"); }, TEXT("SkillActivated"), 400, FIntPoint(3, 6), true);
		BattleCase(TEXT("stackOnEnemyFrozenChance"), [&](const FTreadM2Card&, const FTreadM2Trait& T)
			{ return T.Condition.Event == TEXT("EnemyFrozen") && T.Condition.ChanceBase < 100; }, TEXT("EnemyFrozen"), 30, FIntPoint(3, 6), false);

		// Amplifier behind a battle-stacking unit adds extra stacks to its front neighbour's gains.
		{
			const FString Kill = FindCard([&](const FTreadM2Card&, const FTreadM2Trait& T)
				{ return T.Condition.Event == TEXT("Kill") && T.Condition.Every >= 1 && T.Condition.MaxTimes == 0 && T.Condition.PerBattleCap == 0 &&
					T.Effects[0].PactSelector == TEXT("Pacts"); });
			const FString Amp = FindCard([&](const FTreadM2Card&, const FTreadM2Trait& T) { return HasOp(T, TEXT("AmplifyFrontStackGain")); });
			FTreadM1PlayerState& Player = MatchState.Players[2];
			ClearFixture(Player);
			const FString KillId = Inject(Player, Kill, FIntPoint(3, 5));
			Inject(Player, Amp, FIntPoint(3, 6));
			const FString Pact = PactData->FindCard(Kill)->Traits[0].Effects[0].Pacts[0];
			ActivateWithMembers(Player, Pact, Kill, 0, 7);
			const int32 Before = Progress(TEXT("P2"), Pact).Stacks;
			ResetBattleTraitState();
			const FTreadM2Trait& KillTrait = PactData->FindCard(Kill)->Traits[0];
			for (int32 Kills = 0; Kills < FMath::Max(1, KillTrait.Condition.Every); ++Kills)
			{
				OnBattleUnitEvent(Player, TEXT("Kill"), FTreadM1UnitInstance(*FindOwnedUnit(Player, KillId)));
			}
			const FTreadM2Card* AmpCard = PactData->FindCard(Amp);
			const FTreadM2Effect* AmpEffect = AmpCard ? AmpCard->Traits[0].Effects.FindByPredicate([](const FTreadM2Effect& E) { return E.Op == TEXT("AmplifyFrontStackGain"); }) : nullptr;
			const int32 ExpectedGain = FMath::RoundToInt(KillTrait.Effects[0].BaseValue) + (AmpEffect ? FMath::RoundToInt(AmpEffect->BaseValue) : 0);
			ScenarioCheck(TEXT("stackAmplifiedByBehindUnit"), Progress(TEXT("P2"), Pact).Stacks - Before == ExpectedGain &&
				LogHas(MatchState.TraitLog.Num() - 3, TEXT("Battle"), TEXT("FrontTraitStackGain"), TEXT("applied")));
		}

		// activationRequired=true is skipped while the pact is inactive.
		{
			const FString Knock = FindCard([&](const FTreadM2Card&, const FTreadM2Trait& T) { return T.Condition.Event == TEXT("SelfKnockedOut"); });
			FTreadM1PlayerState& Player = MatchState.Players[2];
			ClearFixture(Player);
			const FString Id = Inject(Player, Knock, FIntPoint(0, 7));
			const int32 LogFrom = MatchState.TraitLog.Num();
			OnBattleUnitEvent(Player, TEXT("SelfKnockedOut"), FTreadM1UnitInstance(*FindOwnedUnit(Player, Id)));
			ScenarioCheck(TEXT("activationRequiredSkipsInactivePact"), LogHas(LogFrom, TEXT("Battle"), TEXT("SelfKnockedOut"), TEXT("skipped:pact-inactive")));
		}

		// Sell-trigger copying another unit's RoundEnd trait (复制特质).
		{
			const FString SellTrigger = FindCard([&](const FTreadM2Card&, const FTreadM2Trait& T)
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
			{
			FTreadM1PlayerState& Player = MatchState.Players[2];
			ClearFixture(Player);
			Inject(Player, RowCard, FIntPoint(5, 5));
			const FString SellerId = Inject(Player, SellTrigger, FIntPoint(-1, -1), 1, true);
			const int32 LogFrom = MatchState.TraitLog.Num();
			DispatchTraitEvent(Player, ETreadM2Trigger::Sell, TEXT("Sell"), FindOwnedUnit(Player, SellerId));
			ScenarioCheck(TEXT("traitCopyTriggersOtherTraits"), LogHas(LogFrom, TEXT("Sell"), TEXT("Sell"), TEXT("applied")) &&
				LogHas(LogFrom, TEXT("Sell"), TEXT("Sell:Triggered")));
			}
		}

		// Resolve the live battle and settle: pending trait income is paid once as Other.
		const int32 Pending = P0.PendingTraitIncome;
		const int32 FundsBeforeSettle = P0.Funds;
		const bool bResolved = ResolveBattle(TEXT("m2-resolve-r1")).bAccepted;
		const int32 Kept = HasN1Economy() && PactData->Economy.bLeftoverFundsLost && !P0.Flags.Contains(TEXT("flag:CarryOverFunds")) ? 0 : FundsBeforeSettle;
		ScenarioCheck(TEXT("pendingTraitIncomePaidAtSettlement"), bResolved && P0.LastSettlementIncome.Other == Pending && P0.PendingTraitIncome == 0 &&
			P0.Funds == Kept + P0.LastSettlementIncome.Base + P0.LastSettlementIncome.Interest + P0.LastSettlementIncome.Streak + Pending);
		From = MatchState.TraitLog.Num();
		const bool bNext = AdvanceToNextRound(TEXT("m2-next-r2")).bAccepted;
		ScenarioCheck(TEXT("eventRoundStartOnNextRound"), bNext && LogHas(From, TEXT("RoundStart"), TEXT("EnterPreparation"), TEXT("event")));

		FString Signature;
		for (const FTreadM2TraitLogEntry& Entry : MatchState.TraitLog)
		{
			Signature += FString::Printf(TEXT("%d:%s:%s:%s:%s:%s:%d:%d:%s|"), Entry.Sequence, *Entry.PlayerId, *Entry.Trigger, *Entry.Event,
				*Entry.SourceId, *Entry.PactId, Entry.Amount, Entry.StacksAfter, *Entry.Status);
		}
		return Signature;
	};
	const FString FirstScenario = Scenario(true);
	const FString SecondScenario = Scenario(false);
	Check(TEXT("sameSeedTraitLogReplayEqual"), !FirstScenario.IsEmpty() && FirstScenario == SecondScenario);
	Extra->SetStringField(TEXT("scenarioTraitLogCrc32"), FString::Printf(TEXT("%08x"), FCrc::StrCrc32(*FirstScenario)));

	// ------------------------------------------------------------------ M. full 12-round match with live battle events
	{
		StartPreparation();
		// Durable fixture board for P0: three elite members of the skill-freeze pact plus an ammo user, so the
		// live resolver reaches skill/freeze/ammo events before units die. Pool copies are not touched (0 held).
		{
			FTreadM1PlayerState& P0 = MatchState.Players[0];
			const FTreadM2PactDef* FreezePact = PactData->Pacts.FindByPredicate([](const FTreadM2PactDef& Def) { return Def.bSkillAppliesFreeze; });
			int32 Placed = 0;
			for (const FString& Id : FreezePact ? Members(FreezePact->PactId) : TArray<FString>())
			{
				if (Placed >= 3) break;
				Inject(P0, Id, FIntPoint(Placed, 7), 3);
				++Placed;
			}
			const FString Ammo = FindCard([&](const FTreadM2Card& Card, const FTreadM2Trait&) { return Card.bConsumesAmmo; });
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
			}
			RefreshScoutSnapshots();
		}
		TSet<FString> BattleEventKinds;
		bool bConsistent = true;
		bool bRounds = true;
		for (int32 Round = 1; Round <= 12; ++Round)
		{
			if (Round > 1) bRounds &= AdvanceToNextRound(FString::Printf(TEXT("m2-full-next-%d"), Round)).bAccepted;
			bRounds &= DeployAndStartBattle(FString::Printf(TEXT("m2-full-deploy-%d"), Round)).bAccepted;
			for (const FTreadM2BattlePactState& State : MatchState.BattlePactStates)
			{
				const FTreadM1ScoutSnapshot* Scout = MatchState.ScoutSnapshots.FindByPredicate([&](const FTreadM1ScoutSnapshot& S) { return S.PlayerId == State.PlayerId; });
				const FTreadM1PlayerState* Player = FindPlayer(State.PlayerId);
				bConsistent &= Scout && Player && SamePacts(State.Pacts, Scout->Pacts) && SamePacts(State.Pacts, Player->Pacts);
			}
			bRounds &= ResolveBattle(FString::Printf(TEXT("m2-full-resolve-%d"), Round)).bAccepted;
		}
		for (const FTreadM1BattleEvent& Event : MatchState.BattleEvents)
		{
			const UEnum* Enum = StaticEnum<ETreadM1BattleEventType>();
			BattleEventKinds.Add(Enum ? Enum->GetNameStringByValue(static_cast<int64>(Event.EventType)) : FString());
		}
		TSet<FString> LogTriggers;
		for (const FTreadM2TraitLogEntry& Entry : MatchState.TraitLog) LogTriggers.Add(Entry.Trigger + TEXT(":") + Entry.Event);
		Check(TEXT("fullMatchTwelveRoundsWithPacts"), bRounds && MatchState.RoundIndex == 12 && ValidatePoolLedger());
		Check(TEXT("fourPlayerScoutMatchesBattleEachRound"), bConsistent);
		Check(TEXT("battleEmitsSkillAmmoFrozenEvents"), BattleEventKinds.Contains(TEXT("SkillActivated")) &&
			BattleEventKinds.Contains(TEXT("AmmoConsumed")) && BattleEventKinds.Contains(TEXT("EnemyFrozen")) && BattleEventKinds.Contains(TEXT("UnitDied")));
		TArray<TSharedPtr<FJsonValue>> Kinds;
		for (const FString& Kind : BattleEventKinds) Kinds.Add(MakeShared<FJsonValueString>(Kind));
		Extra->SetArrayField(TEXT("fullMatchBattleEventKinds"), Kinds);
		Extra->SetNumberField(TEXT("fullMatchTraitLogEntries"), MatchState.TraitLog.Num());
		TArray<FString> SortedTriggers = LogTriggers.Array();
		SortedTriggers.Sort();
		TArray<TSharedPtr<FJsonValue>> TriggerValues;
		for (const FString& Trigger : SortedTriggers) TriggerValues.Add(MakeShared<FJsonValueString>(Trigger));
		Extra->SetArrayField(TEXT("fullMatchTraitLogTriggerEvents"), TriggerValues);
		TArray<TSharedPtr<FJsonValue>> Players;
		for (const FTreadM1PlayerState& Player : MatchState.Players)
		{
			TSharedPtr<FJsonObject> Row = MakeShared<FJsonObject>();
			Row->SetStringField(TEXT("playerId"), Player.PlayerId);
			Row->SetStringField(TEXT("activePacts"), FString::Join(Player.ActivePactIds, TEXT(",")));
			TArray<FString> Stacks;
			for (const FTreadM2PactProgress& Each : Player.Pacts) if (Each.Stacks > 0) Stacks.Add(FString::Printf(TEXT("%s=%d"), *Each.PactId, Each.Stacks));
			Row->SetStringField(TEXT("stacks"), FString::Join(Stacks, TEXT(",")));
			Players.Add(MakeShared<FJsonValueObject>(Row));
		}
		Extra->SetArrayField(TEXT("fullMatchFinalPactState"), Players);
	}

	// ------------------------------------------------------------------ G. pact mechanics (document/171-172)
	{
		// G1. the numbers actually came from bonds.json
		const FTreadM2PactDef* Yan = PactData->FindPact(TEXT("炎"));
		const FTreadM2PactDef* Indom = PactData->FindPact(TEXT("不屈"));
		const FTreadM2PactDef* Mira = PactData->FindPact(TEXT("奇迹"));
		const FTreadM2PactDef* AgirParams = PactData->FindPact(TEXT("阿戈尔"));
		const FTreadM2PactDef* Visi = PactData->FindPact(TEXT("远见"));
		const bool bParams = Yan && Indom && Mira && Agir && Visi
			&& FMath::IsNearlyEqual(Yan->Params.FindRef(TEXT("power_bond_char_cnt")), 6.0f, 0.01f)
			&& FMath::IsNearlyEqual(Yan->Params.FindRef(TEXT("ex_bond_char_cnt")), 9.0f, 0.01f)
			&& FMath::IsNearlyEqual(Yan->Params.FindRef(TEXT("atk")), 1.5f, 0.01f)
			&& FMath::IsNearlyEqual(Indom->Params.FindRef(TEXT("base_prob")), 0.18f, 0.001f)
			&& FMath::IsNearlyEqual(Indom->Params.FindRef(TEXT("prob_per_stack")), 0.004f, 0.0001f)
			&& FMath::IsNearlyEqual(Mira->Params.FindRef(TEXT("baseprob")), 0.18f, 0.001f)
			&& FMath::IsNearlyEqual(AgirParams->Params.FindRef(TEXT("max_free_respawn_cnt")), 3.0f, 0.01f)
			&& FMath::IsNearlyEqual(Visi->Params.FindRef(TEXT("layer1")), 80.0f, 0.01f)
			&& FMath::IsNearlyEqual(Visi->Params.FindRef(TEXT("layer2")), 150.0f, 0.01f);
		Check(TEXT("pactMechanicParamsFromSource"), bParams);

		// G2. 阿戈尔 [5]: the first three 阿戈尔 units each revive exactly once (no roll).
		FTreadM1PlayerState& PlayerG = MatchState.Players[1];
		ClearFixture(PlayerG);
		const TArray<FString> AgirMembers = Members(TEXT("阿戈尔"));
		int32 AgirPlaced = 0;
		for (const FString& Id : AgirMembers)
		{
			if (AgirPlaced >= 5) break;
			Inject(PlayerG, Id, FIntPoint(AgirPlaced % 8, 4 + AgirPlaced / 8));
			++AgirPlaced;
		}
		RecomputePacts(PlayerG);
		BattleAgirRevives = 0;
		BattleRevivedUnits.Reset();
		const FTreadM1UnitInstance* AgirUnit = PlayerG.BoardUnits.FindByPredicate([&](const FTreadM1UnitInstance& Unit)
		{
			return GetUnitPacts(PlayerG, Unit, false).Contains(TEXT("阿戈尔"));
		});
		int32 AgirHealth = 0;
		const bool bAgirRevived = AgirUnit && TryPactRevive(PlayerG, *AgirUnit, AgirHealth) && AgirHealth > 0;
		AgirHealth = 0;
		const bool bAgirSecondRefused = AgirUnit && !TryPactRevive(PlayerG, *AgirUnit, AgirHealth);
		Check(TEXT("agirRevivesEachAgirOnce"), bAgirRevived && bAgirSecondRefused);

		// G2b. 阿戈尔 devour: the unit one cell in front (right = front) leaves the battle, the 阿戈尔 grows.
		FTreadM1PlayerState& PlayerD = MatchState.Players[1];
		ClearFixture(PlayerD);
		const TArray<FString> DevourMembers = Members(TEXT("阿戈尔"));
		int32 DevourPlaced = 0;
		for (const FString& Id : DevourMembers)
		{
			if (DevourPlaced >= 3) break;
			Inject(PlayerD, Id, FIntPoint(0, 2 + DevourPlaced));
			++DevourPlaced;
		}
		const FString Bait = TEXT("char_001");   // 维多利亚/奥术, never an 阿戈尔
		Inject(PlayerD, Bait, FIntPoint(1, 4));
		RecomputePacts(PlayerD);

		int32 BaitIndex = INDEX_NONE;
		TArray<int32> AgirIndices;
		for (int32 Index = 0; Index < PlayerD.BoardUnits.Num(); ++Index)
		{
			if (PlayerD.BoardUnits[Index].CharacterId == Bait) BaitIndex = Index;
			else if (GetUnitPacts(PlayerD, PlayerD.BoardUnits[Index], false).Contains(TEXT("阿戈尔"))) AgirIndices.Add(Index);
		}
		TArray<int32> DevourHealth;
		TArray<FTreadM2UnitCombat> DevourCombat;
		for (const FTreadM1UnitInstance& Unit : PlayerD.BoardUnits)
		{
			DevourHealth.Add(30);
			DevourCombat.Add(ComputeUnitCombat(PlayerD, Unit));
		}
		float AttackBefore = 0.0f;
		for (const int32 Index : AgirIndices) AttackBefore = FMath::Max(AttackBefore, DevourCombat[Index].AttackMul);
		const FTreadM2PactProgress* AgirBefore = FindPactProgress(PlayerD, TEXT("阿戈尔"));
		const int32 StacksBefore = AgirBefore ? AgirBefore->Stacks : 0;

		ApplyAgirDevour(PlayerD, DevourHealth, DevourCombat);

		float AttackAfter = 0.0f;
		for (const int32 Index : AgirIndices) AttackAfter = FMath::Max(AttackAfter, DevourCombat[Index].AttackMul);
		const FTreadM2PactProgress* AgirAfter = FindPactProgress(PlayerD, TEXT("阿戈尔"));
		// The teammate is bitten, never removed: it comes back on the spot (owner's clarification, document/174).
		const bool bVictimSurvives = BaitIndex != INDEX_NONE && DevourHealth.IsValidIndex(BaitIndex) && DevourHealth[BaitIndex] > 0;
		const bool bGrew = AttackAfter > AttackBefore + 0.001f;
		const bool bAgirLayers = AgirAfter && AgirAfter->Stacks > StacksBefore;
		const bool bDevour = bVictimSurvives && bGrew && bAgirLayers;
		// With the revive budget spent a lethal bite really takes the teammate down (document/174 rev.4).
		bool bFallsWhenBudgetSpent = false;
		if (bDevour && BaitIndex != INDEX_NONE)
		{
			DevourHealth[BaitIndex] = 1;
			BattleAgirRevives = 99;
			ApplyAgirDevour(PlayerD, DevourHealth, DevourCombat);
			bFallsWhenBudgetSpent = DevourHealth[BaitIndex] == 0;
		}
		Check(TEXT("agirDevoursFrontCell"), bDevour);
		Check(TEXT("agirDevourFallsWhenReviveBudgetSpent"), bFallsWhenBudgetSpent);

		// G3. 炎 [6/9]: one summon at 6 members, two at 9, all of them stripped again for the preparation phase.
		FTreadM1PlayerState& PlayerY = MatchState.Players[1];
		ClearFixture(PlayerY);
		const TArray<FString> YanMembers = Members(TEXT("炎"));
		int32 YanPlaced = 0;
		for (const FString& Id : YanMembers)
		{
			if (YanPlaced >= 6) break;
			Inject(PlayerY, Id, FIntPoint(YanPlaced % 8, 4 + YanPlaced / 8));
			++YanPlaced;
		}
		RecomputePacts(PlayerY);
		TArray<int32> YanHealth;
		TArray<FTreadM2UnitCombat> YanCombat;
		for (const FTreadM1UnitInstance& Unit : PlayerY.BoardUnits)
		{
			YanHealth.Add(40);
			YanCombat.Add(ComputeUnitCombat(PlayerY, Unit));
		}
		const int32 YanBefore = PlayerY.BoardUnits.Num();
		BattleSummonSerial = 0;
		ApplyYanSummon(PlayerY, YanHealth, YanCombat);
		const int32 YanAfterSix = PlayerY.BoardUnits.Num() - YanBefore;
		int32 YanPlaced9 = YanPlaced;
		for (const FString& Id : YanMembers)
		{
			if (YanPlaced9 >= 9) break;
			if (PlayerY.BoardUnits.ContainsByPredicate([&](const FTreadM1UnitInstance& Unit) { return Unit.CharacterId == Id; })) continue;
			Inject(PlayerY, Id, FIntPoint(YanPlaced9 % 8, 4 + YanPlaced9 / 8));
			++YanPlaced9;
		}
		RecomputePacts(PlayerY);
		YanHealth.Reset();
		YanCombat.Reset();
		for (const FTreadM1UnitInstance& Unit : PlayerY.BoardUnits)
		{
			YanHealth.Add(40);
			YanCombat.Add(ComputeUnitCombat(PlayerY, Unit));
		}
		const int32 YanBeforeNine = PlayerY.BoardUnits.Num();
		ApplyYanSummon(PlayerY, YanHealth, YanCombat);
		const int32 YanAfterNine = PlayerY.BoardUnits.Num() - YanBeforeNine;
		StripSummons(PlayerY);
		const bool bSummonsGone = !PlayerY.BoardUnits.ContainsByPredicate([](const FTreadM1UnitInstance& Unit)
		{
			return Unit.UnitInstanceId.StartsWith(TEXT("SUMMON_"));
		});
		Check(TEXT("yanSummonOneThenTwoAndStripped"), YanAfterSix == 1 && YanAfterNine == 2 && bSummonsGone);

		// G4. 远见: a refresh feeds a layer, and 150 layers discount every shop card by 1.
		FTreadM1PlayerState& PlayerV = MatchState.Players[1];
		ClearFixture(PlayerV);
		int32 VisiPlaced = 0;
		for (const FString& Id : Members(TEXT("远见")))
		{
			if (VisiPlaced >= 2) break;
			Inject(PlayerV, Id, FIntPoint(VisiPlaced % 8, 4 + VisiPlaced / 8));
			++VisiPlaced;
		}
		RecomputePacts(PlayerV);
		const FTreadM2PactProgress* VisiBefore = FindPactProgress(PlayerV, TEXT("远见"));
		const int32 LayersBefore = VisiBefore ? VisiBefore->Stacks : 0;
		FeedForesightLayers(PlayerV);
		FeedForesightLayers(PlayerV);
		const FTreadM2PactProgress* VisiAfter = FindPactProgress(PlayerV, TEXT("远见"));
		const bool bLayers = VisiAfter && VisiAfter->Stacks >= LayersBefore + 2;

		AddPactStacks(PlayerV, TEXT("远见"), 200, false, TEXT("SelfTest"), nullptr, ETreadM2Trigger::Passive, TEXT("ForesightDiscount"), false);
		BuildShop(PlayerV, PlayerV.Shop.RefreshIndex + 1);
		bool bDiscount = true;
		int32 Discounted = 0;
		for (const FTreadM1ShopSlot& ShopSlot : PlayerV.Shop.Slots)
		{
			if (ShopSlot.bIsSold || ShopSlot.CharacterId.IsEmpty()) continue;
			const int32 Base = PurchaseCostFor(ShopSlot.CharacterId, TierPrice(ShopSlot.OperatorTier));
			const int32 Expected = FMath::Max(0, Base - 1);
			if (ShopSlot.Cost > Expected) bDiscount = false;
			if (ShopSlot.Cost < Base) ++Discounted;
		}
		Check(TEXT("foresightLayerPerRefreshAndDiscount"), bLayers && bDiscount && Discounted > 0);

		// G5. 不屈: with the pact active the knock-down roll revives sometimes but not always (18 % at 0 stacks).
		FTreadM1PlayerState& PlayerI = MatchState.Players[1];
		ClearFixture(PlayerI);
		int32 IndomPlaced = 0;
		for (const FString& Id : Members(TEXT("不屈")))
		{
			if (IndomPlaced >= 2) break;
			Inject(PlayerI, Id, FIntPoint(IndomPlaced % 8, 4 + IndomPlaced / 8));
			++IndomPlaced;
		}
		RecomputePacts(PlayerI);
		const FTreadM1UnitInstance* IndomUnit = PlayerI.BoardUnits.Num() > 0 ? &PlayerI.BoardUnits[0] : nullptr;
		int32 IndomRevives = 0;
		if (IndomUnit)
		{
			for (int32 Try = 0; Try < 100; ++Try)
			{
				BattleRevivedUnits.Reset();
				int32 IndomHealth = 0;
				if (TryPactRevive(PlayerI, *IndomUnit, IndomHealth) && IndomHealth > 0)
				{
					++IndomRevives;
				}
			}
		}
		Check(TEXT("indomReviveRolls"), IndomRevives > 0 && IndomRevives < 100);

		// G6. 奇迹: the same roll hands out free refreshes over a hundred tries.
		FTreadM1PlayerState& PlayerM = MatchState.Players[1];
		ClearFixture(PlayerM);
		int32 MiraPlaced = 0;
		for (const FString& Id : Members(TEXT("奇迹")))
		{
			if (MiraPlaced >= 2) break;
			Inject(PlayerM, Id, FIntPoint(MiraPlaced % 8, 4 + MiraPlaced / 8));
			++MiraPlaced;
		}
		RecomputePacts(PlayerM);
		const int32 FreeBefore = PlayerM.FreeRefreshes;
		int32 MiraHits = 0;
		for (int32 Try = 0; Try < 100; ++Try)
		{
			if (TryMiracleFreeRefresh(PlayerM)) ++MiraHits;
		}
		Check(TEXT("miracleFreeRefreshRolls"), MiraHits > 0 && MiraHits < 100 && PlayerM.FreeRefreshes == FreeBefore + MiraHits);
	}

	// ------------------------------------------------------------------ H. item procs (document/175)
	{
		// The earlier sections end in Settlement or GameOver; the proc fixture needs Preparation again.
		StartPreparation();
		int32 ProcItems = 0;
		int32 AppliedItems = 0;
		for (const FTreadM2Item& Item : PactData->Items)
		{
			if (Item.Procs.Num() > 0) ++ProcItems;
			if (Item.RuntimeSupport == TEXT("applied")) ++AppliedItems;
		}
		Check(TEXT("itemProcsLoadedFromData"), ProcItems >= 20 && AppliedItems >= 40);

		const FString ProcCharacter = PactData->CardOrder.Num() > 0 ? PactData->CardOrder[0] : TEXT("char_001");
		FTreadM1PlayerState& PlayerP = MatchState.Players[1];
		ClearFixture(PlayerP);
		const FString ProcUnit = Inject(PlayerP, ProcCharacter, FIntPoint(0, 4));
		FTreadM1UnitInstance* Equipped = FindOwnedUnit(PlayerP, ProcUnit);
		if (Equipped)
		{
			Equipped->EquipmentIds.Add(TEXT("chess_item_3_11_e_a"));
			Equipped->EquipmentIds.Add(TEXT("chess_item_4_12_e_a"));
		}
		const FTreadM2UnitProcs ProcStats = Equipped ? ComputeUnitProcs(PlayerP, *Equipped) : FTreadM2UnitProcs();
		Check(TEXT("itemProcAggregates"), ProcStats.StunChance >= 1.0f && ProcStats.ReviveCount >= 1);

		FTreadM2BattleSide ProcSide;
		BuildBattleSide(ProcSide, PlayerP);
		const int32 ProcMaxHealth = ProcSide.MaxHealth.Num() > 0 ? ProcSide.MaxHealth[0] : 0;
		if (ProcSide.Health.Num() > 0) ProcSide.Health[0] = 0;
		ResolveBattleDeath(ProcSide, 0, TEXT("Pa"), TEXT("Pb"), nullptr, INDEX_NONE);
		Check(TEXT("itemProcReviveKeepsUnit"), ProcSide.Health.Num() > 0 && ProcSide.Health[0] > 0 &&
			ProcSide.Health[0] <= ProcMaxHealth && ProcSide.ReviveLeft[0] == 0);

		FTreadM1PlayerState& PlayerS = MatchState.Players[2];
		ClearFixture(PlayerS);
		const FString SpUnit = Inject(PlayerS, ProcCharacter, FIntPoint(0, 4));
		if (FTreadM1UnitInstance* SpOwner = FindOwnedUnit(PlayerS, SpUnit))
		{
			SpOwner->EquipmentIds = {TEXT("chess_item_3_05_e_a")};
		}
		BattleSp.Reset();
		FTreadM2BattleSide SpSide;
		BuildBattleSide(SpSide, PlayerS);
		ApplyBattleStartProcs(SpSide);
		Check(TEXT("itemProcSpInitial"), BattleSp.FindRef(SpUnit) >= 3.0f);
		BattleSp.Reset();

		// 4_02 taunt: the taunter is focused even when it is not the first living unit.
		FTreadM1PlayerState& PlayerT = MatchState.Players[3];
		ClearFixture(PlayerT);
		Inject(PlayerT, ProcCharacter, FIntPoint(0, 4));
		const FString TauntUnit = Inject(PlayerT, ProcCharacter, FIntPoint(1, 4));
		if (FTreadM1UnitInstance* TauntOwner = FindOwnedUnit(PlayerT, TauntUnit))
		{
			TauntOwner->EquipmentIds = {TEXT("chess_item_4_02_e_a")};
		}
		FTreadM2BattleSide TauntSide;
		BuildBattleSide(TauntSide, PlayerT);
		Check(TEXT("itemProcTauntTargeting"), TauntSide.Health.Num() >= 2 && SelectBattleTarget(TauntSide, 0) == 1);

		// AI equips what it owns: grant one item, run the AI turn, expect a worn item.
		FTreadM1PlayerState& PlayerA = MatchState.Players[1];
		ClearFixture(PlayerA);
		Inject(PlayerA, ProcCharacter, FIntPoint(2, 3));
		GrantItemForTest(PlayerA.PlayerId, TEXT("chess_item_3_09_e_a"));
		const bool bAiPlayBefore = bAIOpponentsPlay;
		bAIOpponentsPlay = true;
		RunAIPreparation();
		bAIOpponentsPlay = bAiPlayBefore;
		bool bAiEquipped = false;
		for (const FTreadM1UnitInstance& Owned : PlayerA.BoardUnits) bAiEquipped |= Owned.EquipmentIds.Num() > 0;
		Check(TEXT("aiEquipsItems"), bAiEquipped);
	}

	// ------------------------------------------------------------------ I. reward offer (document/176)
	{
		StartPreparation();
		FTreadM1PlayerState& HumanR = MatchState.Players[0];
		const int32 Offered = HumanR.RewardOffer.Num();
		bool bOfferValid = Offered == FMath::Clamp(PactData->Economy.RewardCount, 0, 8) && Offered > 0;
		for (const FString& ItemId : HumanR.RewardOffer)
		{
			const FTreadM2Item* Item = FindItemData(ItemId);
			bOfferValid &= Item && Item->Tier >= 1 && Item->Tier <= RewardTierCap(HumanR);
		}
		Check(TEXT("rewardOfferThreeChoices"), bOfferValid && !HumanR.bRewardClaimed);

		const int32 InventoryBefore = HumanR.EquipmentIds.Num();
		const FString FirstChoice = HumanR.RewardOffer.Num() > 0 ? HumanR.RewardOffer[0] : FString();
		const FTreadM1CommandResult Claimed = ChooseReward(HumanR.PlayerId, 0, TEXT("m2-reward-1"));
		const bool bGranted = Claimed.bAccepted && HumanR.EquipmentIds.Num() == InventoryBefore + 1 &&
			HumanR.EquipmentIds.Contains(FirstChoice) && HumanR.bRewardClaimed;
		const FTreadM1CommandResult Again = ChooseReward(HumanR.PlayerId, 0, TEXT("m2-reward-2"));
		Check(TEXT("rewardChooseGrantsItem"), bGranted && !Again.bAccepted &&
			Again.ReasonCode == ETreadM1RejectReason::RewardUnavailable);

		// The AI claims its own offer during its preparation turn.
		FTreadM1PlayerState& AiR = MatchState.Players[1];
		const bool bAiPlayBeforeR = bAIOpponentsPlay;
		bAIOpponentsPlay = true;
		RunAIPreparation();
		bAIOpponentsPlay = bAiPlayBeforeR;
		Check(TEXT("aiClaimsReward"), AiR.bRewardClaimed && AiR.EquipmentIds.Num() > 0);
	}

	// ------------------------------------------------------------------ J. second proc wave (document/178)
	{
		StartPreparation();
		int32 ProcItemsJ = 0;
		for (const FTreadM2Item& Item : PactData->Items) ProcItemsJ += Item.Procs.Num() > 0 ? 1 : 0;
		Check(TEXT("itemProcSecondWaveLoaded"), ProcItemsJ >= 40);

		const FString JCharacter = PactData->CardOrder.Num() > 0 ? PactData->CardOrder[0] : TEXT("char_001");
		FTreadM1PlayerState& PlayerJ = MatchState.Players[1];
		ClearFixture(PlayerJ);
		const FString JUnit = Inject(PlayerJ, JCharacter, FIntPoint(0, 4));
		FTreadM1UnitInstance* JOwner = FindOwnedUnit(PlayerJ, JUnit);
		if (JOwner)
		{
			JOwner->EquipmentIds = {TEXT("chess_item_1_05_e_a"), TEXT("chess_item_2_01_e_a"),
				TEXT("chess_item_4_04_e_a"), TEXT("chess_item_4_11_e_a")};
		}
		const FTreadM2UnitProcs JProcs = JOwner ? ComputeUnitProcs(PlayerJ, *JOwner) : FTreadM2UnitProcs();
		Check(TEXT("itemProcSecondWaveAggregates"), JProcs.SelfDot > 0.0f && JProcs.RedeployCount > 0 &&
			JProcs.StealthDuration > 0.0f && JProcs.ShieldOnHealChance > 0.0f);

		FTreadM2BattleSide JSide;
		BuildBattleSide(JSide, PlayerJ);
		const int32 JHealthBefore = JSide.Health.Num() > 0 ? JSide.Health[0] : 0;
		BattleExchangeIndex = 0;
		TickBattleSideProcs(JSide, 0);
		const bool bSelfDot = JSide.Health.Num() > 0 && JSide.Health[0] < JHealthBefore;
		JSide.Health[0] = 0;
		ResolveBattleDeath(JSide, 0, TEXT("Ja"), TEXT("Jb"), nullptr, INDEX_NONE);
		const bool bRedeployScheduled = JSide.RedeployAt.Num() > 0 && JSide.RedeployAt[0] > 0;
		TickBattleSideProcs(JSide, 2);
		Check(TEXT("itemProcSelfDotAndRedeploy"), bSelfDot && bRedeployScheduled && JSide.Health[0] > 0);

		// 4_11 shield eats a hit; 4_04 stealth then hides the unit from target selection.
		FTreadM1PlayerState& PlayerK = MatchState.Players[2];
		ClearFixture(PlayerK);
		const FString KUnit = Inject(PlayerK, JCharacter, FIntPoint(0, 4));
		Inject(PlayerK, JCharacter, FIntPoint(1, 4));
		if (FTreadM1UnitInstance* KOwner = FindOwnedUnit(PlayerK, KUnit)) KOwner->EquipmentIds = {TEXT("chess_item_4_04_e_a")};
		FTreadM2BattleSide KSide;
		BuildBattleSide(KSide, PlayerK);
		const int32 KHealthBefore = KSide.Health[0];
		KSide.Shield[0] = 1;
		ApplyBattleDamage(KSide, 0, 5, TEXT("Ka"), TEXT("Kb"));
		const bool bShieldAbsorbed = KSide.Health[0] == KHealthBefore && KSide.Shield[0] == 0;
		ApplyBattleDamage(KSide, 0, 1, TEXT("Ka"), TEXT("Kb"));
		const bool bStealthActive = KSide.StealthUntil[0] > 0 && SelectBattleTarget(KSide, 0) == 1;
		Check(TEXT("itemProcShieldAndStealth"), bShieldAbsorbed && bStealthActive);

		// 3_01 aura: the neighbour's attack multiplier rises once the aura item is equipped.
		FTreadM1PlayerState& PlayerL = MatchState.Players[3];
		ClearFixture(PlayerL);
		const FString Lua = Inject(PlayerL, JCharacter, FIntPoint(0, 4));
		Inject(PlayerL, JCharacter, FIntPoint(1, 4));
		FTreadM2BattleSide LBefore;
		BuildBattleSide(LBefore, PlayerL);
		const float LNeighbourBefore = LBefore.Combat.Num() > 1 ? LBefore.Combat[1].AttackMul : 0.0f;
		if (FTreadM1UnitInstance* AuraOwner = FindOwnedUnit(PlayerL, Lua))
		{
			AuraOwner->EquipmentIds = {TEXT("chess_item_3_01_e_a")};
		}
		FTreadM2BattleSide LAfter;
		BuildBattleSide(LAfter, PlayerL);
		Check(TEXT("itemProcNeighborAura"), LAfter.Combat.Num() > 1 && LAfter.Combat[1].AttackMul > LNeighbourBefore);

		// 5_08: the holder comes back as a higher-tier operator after the battle.
		FTreadM1PlayerState& PlayerTf = MatchState.Players[1];
		ClearFixture(PlayerTf);
		FString LowTier;
		for (const FString& CardId : PactData->CardOrder)
		{
			if (TierPrice(CardTier(CardId)) <= 1) { LowTier = CardId; break; }
		}
		const FString TfUnit = Inject(PlayerTf, LowTier.IsEmpty() ? JCharacter : LowTier, FIntPoint(0, 4));
		if (FTreadM1UnitInstance* TfOwner = FindOwnedUnit(PlayerTf, TfUnit))
		{
			TfOwner->EquipmentIds = {TEXT("chess_item_5_08_e_a")};
		}
		const int32 TierBefore = FindOwnedUnit(PlayerTf, TfUnit) ? TierPrice(CardTier(FindOwnedUnit(PlayerTf, TfUnit)->CharacterId)) : 0;
		ApplyPostBattleItemTransforms();
		const int32 TierAfter = FindOwnedUnit(PlayerTf, TfUnit) ? TierPrice(CardTier(FindOwnedUnit(PlayerTf, TfUnit)->CharacterId)) : 0;
		Check(TEXT("itemProcPostBattleTransform"), TierAfter > TierBefore);

		// 6_03: acquiring an operator pays two funds, capped per round.
		FTreadM1PlayerState& PlayerF = MatchState.Players[2];
		ClearFixture(PlayerF);
		const FString FUnit = Inject(PlayerF, JCharacter, FIntPoint(0, 4));
		if (FTreadM1UnitInstance* FOwner = FindOwnedUnit(PlayerF, FUnit))
		{
			FOwner->EquipmentIds = {TEXT("chess_item_6_03_e_a")};
		}
		PlayerF.Funds = 0;
		PlayerF.AcquireFundsCount = 0;
		GrantUnitToPlayer(PlayerF, PactData->CardOrder.Num() > 1 ? PactData->CardOrder[1] : JCharacter,
			TEXT("m2-acquire"), ETreadM2Trigger::Passive, 0);
		Check(TEXT("itemProcAcquireFunds"), PlayerF.Funds >= 2 && PlayerF.AcquireFundsCount == 1);
	}

	Extra->SetStringField(TEXT("pactDataVersion"), MatchState.PactDataVersion);
	Extra->SetNumberField(TEXT("seed"), static_cast<double>(Seed));
	const FString Path = OutputPath.IsEmpty() ? FPaths::Combine(FPaths::ProjectDir(), TEXT("Saved/Reports/M2_Pact_SelfTest.json")) : OutputPath;
	const bool bSaved = WriteM2SelfTestReport(Path, Checks, Notes, Extra);
	bool bOk = bSaved;
	for (const TPair<FString, bool>& Pair : Checks) bOk &= Pair.Value;
	InitializeMatch(Seed);
	return bOk;
}
