"""Replayable source patch: M2 evidence capture preset (-TreadM2Capture=PACTS|BATTLE|SCOUT, -TreadM2Shot=<name>)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "Source/Tread"


def patch(path, pairs):
    s = path.read_text(encoding="utf-8")
    for a, b in pairs:
        assert s.count(a) == 1, (path.name, a[:90])
        s = s.replace(a, b)
    path.write_text(s, encoding="utf-8")


header = SRC / "TreadM1MatchController.h"
if "BuildM2Showcase" in header.read_text(encoding="utf-8"):
    raise SystemExit("already patched")

patch(header, [(
    "	void ResetBattleTraitState();\n",
    "	void ResetBattleTraitState();\n"
    "	/** Evidence/fixture helper: put CharacterId+Tier into a shop slot, returning any prior reservation first. */\n"
    "	bool StockShopSlotForFixture(FTreadM1PlayerState& Player, int32 SlotIndex, const FString& CharacterId, const FString& Tier);\n"
    "	/** Deterministic R2 showcase built with real commands for M2 screenshots (-TreadM2Capture). */\n"
    "	void BuildM2Showcase(const FString& Stage);\n"
    "	void RequestM2Screenshot(const FString& Name);\n",
)])

patch(SRC / "TreadM1MatchController.cpp", [
    ('#include "UObject/Class.h"\n', '#include "UObject/Class.h"\n#include "TimerManager.h"\n'),
    ("""	if (FParse::Param(FCommandLine::Get(), TEXT("TreadM2SelfTest")))""",
     """	FString M2Capture;
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
	if (FParse::Param(FCommandLine::Get(), TEXT("TreadM2SelfTest")))"""),
])

rt = SRC / "TreadM2PactRuntime.cpp"
s = rt.read_text(encoding="utf-8")
s = s.replace('#include "Misc/Paths.h"\n', '#include "Misc/Paths.h"\n#include "TimerManager.h"\n#include "UnrealClient.h"\n', 1)
s += r'''
bool ATreadM1MatchController::StockShopSlotForFixture(FTreadM1PlayerState& Player, int32 SlotIndex, const FString& CharacterId, const FString& Tier)
{
	if (!Player.Shop.Slots.IsValidIndex(SlotIndex)) return false;
	FTreadM1ShopSlot& Slot = Player.Shop.Slots[SlotIndex];
	if (!Slot.bIsSold && !Slot.CharacterId.IsEmpty()) RecordPoolLedger(TEXT("RefreshReturn"), Player.PlayerId, Slot, 1);
	Slot.CharacterId = CharacterId;
	Slot.OperatorTier = Tier;
	Slot.Cost = PurchaseCostFor(CharacterId, 1);
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

void ATreadM1MatchController::RequestM2Screenshot(const FString& Name)
{
	const FString Path = FPaths::ConvertRelativePathToFull(FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("Screenshots"), Name + TEXT(".png")));
	FScreenshotRequest::RequestScreenshot(Path, true, false, false, FIntRect(), true);
	UE_LOG(LogTemp, Display, TEXT("Tread M2 screenshot requested: %s"), *Path);
	FTimerHandle ExitTimer;
	GetWorldTimerManager().SetTimer(ExitTimer, FTimerDelegate::CreateLambda([]() { FPlatformMisc::RequestExit(false); }), 3.0f, false);
}
'''
rt.write_text(s, encoding="utf-8")

patch(SRC / "TreadM1MatchWidget.cpp", [(
    """	bScoutOpen = CaptureStage == TEXT("SCOUT");
	if (bScoutOpen) ScoutPlayerIndex = 1;""",
    """	bScoutOpen = CaptureStage == TEXT("SCOUT");
	if (bScoutOpen) ScoutPlayerIndex = 1;
	FString M2Stage;
	if (FParse::Value(FCommandLine::Get(), TEXT("TreadM2Capture="), M2Stage) && M2Stage.ToUpper() == TEXT("SCOUT"))
	{
		// M2 evidence: the human's own read-only ScoutSnapshot with pact counts and stacks.
		bScoutOpen = true;
		ScoutPlayerIndex = 0;
	}""",
)])
print("patched capture preset")
