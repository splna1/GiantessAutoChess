"""Replayable source patch (N1): HUD shows the 40 Stronghold-Protocol strategies, operator names in the shop/bench and
the 调度中心 level/upgrade instead of experience. Adds two BlueprintPure display helpers to the controller."""
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


patch(SRC / "TreadM1MatchController.h", [(
    '''	UFUNCTION(BlueprintPure, Category = "M2|Pact")
	FString GetTraitSummary(const FString& CharacterId) const;''',
    '''	UFUNCTION(BlueprintPure, Category = "M2|Pact")
	FString GetTraitSummary(const FString& CharacterId) const;

	/** N2: "<operator name>" of the card bound to a character model (Roster112), or the character id. */
	UFUNCTION(BlueprintPure, Category = "N1|Roster")
	FString GetCardDisplayName(const FString& CharacterId) const;

	/** N1: current 调度中心 upgrade price for a player (0 at max level). */
	UFUNCTION(BlueprintPure, Category = "N1|Economy")
	int32 GetShopUpgradeCost(const FString& PlayerId) const;

	UFUNCTION(BlueprintPure, Category = "N1|Economy")
	bool UsesN1Economy() const { return HasN1Economy(); }''')], "GetCardDisplayName")

patch(SRC / "TreadM2PactRuntime.cpp", [(
    '''FString ATreadM1MatchController::GetItemDisplayName(const FString& ItemId) const
{''',
    '''FString ATreadM1MatchController::GetCardDisplayName(const FString& CharacterId) const
{
	const FTreadM2Card* Card = PactData.IsValid() ? PactData->FindCard(CharacterId) : nullptr;
	return Card && !Card->ReferenceOperatorName.IsEmpty() ? Card->ReferenceOperatorName : CharacterId;
}

int32 ATreadM1MatchController::GetShopUpgradeCost(const FString& PlayerId) const
{
	const FTreadM1PlayerState* Player = FindPlayer(PlayerId);
	return Player ? ShopUpgradeCost(*Player) : 0;
}

FString ATreadM1MatchController::GetItemDisplayName(const FString& ItemId) const
{''')], "GetCardDisplayName")

W = SRC / "TreadM1MatchWidget.cpp"
patch(W, [
    # 40 BP cards in an 8 x 5 grid
    ('''	for (int32 Index = 0; Index < 32; ++Index)
	{
		BPButtons.Add''', '''	for (int32 Index = 0; Index < 40; ++Index)
	{
		BPButtons.Add'''),
    ('''		SetButtonRect(BPButtons[Index], RefVec(16 + Col * 158, 208 + Row * 186), RefVec(148, 176), 51);''',
     '''		SetButtonRect(BPButtons[Index], RefVec(16 + Col * 158, 208 + Row * 146), RefVec(148, 138), 51);'''),
    ('''	DrawText(Out, Geometry, Layer + 3, TEXT("32 策略候选 / 当前唯一选择"), RefVec(1320, 140), 20, Funds, true);
	for (int32 Index = 0; Index < 32; ++Index)
	{
		const int32 Col = Index % 8; const int32 Row = Index / 8;
		const float X = 16 + Col * 158; const float Y = 208 + Row * 186;''',
     '''	const int32 StrategyCount = FMath::Clamp(Controller->MatchState.Strategies.Num(), 1, 40);
	DrawText(Out, Geometry, Layer + 3, FString::Printf(TEXT("%d 策略候选 / 当前唯一选择"), StrategyCount), RefVec(1320, 140), 20, Funds, true);
	for (int32 Index = 0; Index < StrategyCount; ++Index)
	{
		const int32 Col = Index % 8; const int32 Row = Index / 8;
		const float X = 16 + Col * 158; const float Y = 208 + Row * 146;'''),
    ('''		DrawPanel(Out, Geometry, Layer + 2, RefVec(X, Y), RefVec(148, 176), CardColor, bPlayerSelected || bOccupied);''',
     '''		DrawPanel(Out, Geometry, Layer + 2, RefVec(X, Y), RefVec(148, 138), CardColor, bPlayerSelected || bOccupied);'''),
    ('''		DrawText(Out, Geometry, Layer + 4, Id, RefVec(X + 12, Y + 48), 15, TextPrimary, true, RefVec(128, 48));''',
     '''		// Strategy name = its 【effect】 heading; the full text shows in the right-hand detail panel.
		FString CardTitle = Id;
		if (const FTreadM1StrategyState* Strategy = Controller->MatchState.Strategies.FindByPredicate([&Id](const FTreadM1StrategyState& S) { return S.StrategyId == Id; }))
		{
			FString Head, Rest;
			CardTitle = Strategy->OfferText.Split(TEXT("】"), &Head, &Rest) ? Head.Replace(TEXT("【"), TEXT("")) : Strategy->OfferText.Left(8);
		}
		DrawText(Out, Geometry, Layer + 4, CardTitle, RefVec(X + 12, Y + 44), 15, TextPrimary, true, RefVec(128, 48));'''),
    ('''		DrawText(Out, Geometry, Layer + 4, CardStatus, RefVec(X + 12, Y + 142), 15, StatusColor, true);''',
     '''		DrawText(Out, Geometry, Layer + 4, CardStatus, RefVec(X + 12, Y + 108), 15, StatusColor, true);'''),
    ('''	DrawText(Out, Geometry, Layer + 4, Controller->MatchState.BP.PlayerStrategyId.IsEmpty() ? TEXT("请选择一张策略卡") : Controller->MatchState.BP.PlayerStrategyId, RefVec(1340, 244), 24, PlayerText, true);''',
     '''	DrawText(Out, Geometry, Layer + 4, Controller->MatchState.BP.PlayerStrategyId.IsEmpty() ? TEXT("请选择一张策略卡") : Controller->MatchState.BP.PlayerStrategyId, RefVec(1340, 232), 20, PlayerText, true);
	if (const FTreadM1StrategyState* Picked = Controller->MatchState.Strategies.FindByPredicate([this](const FTreadM1StrategyState& S) { return S.StrategyId == Controller->MatchState.BP.PlayerStrategyId; }))
	{
		DrawText(Out, Geometry, Layer + 4, Picked->OfferText, RefVec(1340, 262), 14, TextSecondary, false, RefVec(500, 60));
	}'''),
    # shop: operator names
    ('''				DrawText(Out, Geometry, Layer + 3, ShopSlot.bIsSold ? TEXT("已售出") : FString::Printf(TEXT("%s  ·  阶级 %s"), *ShopSlot.CharacterId, *ShopSlot.OperatorTier), RefVec(1620, Y + 12), 16, ShopSlot.bIsSold ? TextSecondary : TextPrimary, true);''',
     '''				DrawText(Out, Geometry, Layer + 3, ShopSlot.bIsSold ? TEXT("已售出") : FString::Printf(TEXT("%s  ·  阶级 %s"), *Controller->GetCardDisplayName(ShopSlot.CharacterId), *ShopSlot.OperatorTier), RefVec(1620, Y + 12), 16, ShopSlot.bIsSold ? TextSecondary : TextPrimary, true, RefVec(270, 24));'''),
    # refresh / upgrade buttons and level line
    ('''	DrawText(Out, Geometry, Layer + 3, TEXT("刷新 ¤2"), RefVec(1620, 565), 17, TextPrimary, true);''',
     '''	DrawText(Out, Geometry, Layer + 3, P && P->FreeRefreshes > 0 ? FString::Printf(TEXT("免费刷新 ×%d"), P->FreeRefreshes)
		: FString::Printf(TEXT("刷新 ¤%d"), Controller->MatchState.Rules.ShopRefreshCost), RefVec(1620, 565), 17, TextPrimary, true);'''),
    ('''	DrawText(Out, Geometry, Layer + 3, TEXT("经验 ¤4"), RefVec(1770, 565), 17, TextPrimary, true);''',
     '''	DrawText(Out, Geometry, Layer + 3, !Controller->UsesN1Economy() ? FString(TEXT("经验 ¤4"))
		: (P && Controller->GetShopUpgradeCost(P->PlayerId) > 0 ? FString::Printf(TEXT("升级 ¤%d"), Controller->GetShopUpgradeCost(P->PlayerId)) : FString(TEXT("已满级"))),
		RefVec(1770, 565), 17, TextPrimary, true);'''),
    ('''			DrawText(Out, Geometry, Layer + 2, FString::Printf(TEXT("经验 %d / %d"), P->Experience, P->ExperienceToNextLevel), RefVec(1604, 614), 17, TextSecondary);''',
     '''			DrawText(Out, Geometry, Layer + 2, Controller->UsesN1Economy() ? FString::Printf(TEXT("调度中心 Lv %d / 6"), P->Level)
				: FString::Printf(TEXT("经验 %d / %d"), P->Experience, P->ExperienceToNextLevel), RefVec(1604, 614), 17, TextSecondary);'''),
    ('''			DrawText(Out, Geometry, Layer + 2, FString::Printf(TEXT("下轮收入：基础 %d + 利息 %d + 连胜/败 %d + 特质 %d"), P->NextRoundIncome.Base, P->NextRoundIncome.Interest, P->NextRoundIncome.Streak, P->NextRoundIncome.Other), RefVec(1266, 657), 17, Funds);''',
     '''			DrawText(Out, Geometry, Layer + 2, Controller->UsesN1Economy()
				? FString::Printf(TEXT("下轮收入：基础 %d + 特质 %d（剩余资金不保留）"), P->NextRoundIncome.Base, P->NextRoundIncome.Other + P->NextRoundIncome.Interest)
				: FString::Printf(TEXT("下轮收入：基础 %d + 利息 %d + 连胜/败 %d + 特质 %d"), P->NextRoundIncome.Base, P->NextRoundIncome.Interest, P->NextRoundIncome.Streak, P->NextRoundIncome.Other), RefVec(1266, 657), 17, Funds);'''),
    # bench: operator names
    ('''					DrawText(Out, Geometry, Layer + 4, Unit.CharacterId, RefVec(X + 10, 994), 14, TextPrimary, true);''',
     '''					DrawText(Out, Geometry, Layer + 4, Controller->GetCardDisplayName(Unit.CharacterId), RefVec(X + 10, 994), 14, TextPrimary, true, RefVec(86, 22));'''),
], "GetCardDisplayName")

H = SRC / "TreadM1MatchWidget.h"
print("widget header unchanged (BPButtons is a TArray)")
