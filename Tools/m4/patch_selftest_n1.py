"""Replayable source patch (N1): the M2 native self-test runs on the Stronghold-Protocol roster (112 cards, one tier
per card, shop size by 调度中心 level). Fixtures use each card's bound tier; check names are unchanged."""
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


FIXTURE_SLOT = '''	// N1: a card has exactly one bound tier; fixtures may address slots beyond the level's shop size.
	const FString BoundTier = CardTier(CharacterId);
	const FString UseTier = BoundTier.IsEmpty() ? Tier : BoundTier;
	while (HasN1Economy() && SlotIndex >= Player.Shop.Slots.Num() && SlotIndex < 8)
	{
		FTreadM1ShopSlot Extra;
		Extra.SlotIndex = Player.Shop.Slots.Num();
		Extra.bIsSold = true;
		Player.Shop.Slots.Add(Extra);
	}
'''

patch(SRC / "TreadM2PactSelfTest.cpp", [
    ('''		Unit.OperatorTier = TEXT("I");
		Unit.UnitStar = Star;''', '''		Unit.OperatorTier = CardTier(CharacterId).IsEmpty() ? TEXT("I") : CardTier(CharacterId);
		Unit.UnitStar = Star;'''),
    ('''			if (bShopRange && CardNumber(Id) > 32) continue;''', '''			if (bShopRange && !HasN1Economy() && CardNumber(Id) > 32) continue;'''),
    ('''	const auto StockShop = [this](FTreadM1PlayerState& Player, int32 SlotIndex, const FString& CharacterId, const FString& Tier)
	{
		FTreadM1ShopSlot& Slot = Player.Shop.Slots[SlotIndex];''', '''	const auto StockShop = [this](FTreadM1PlayerState& Player, int32 SlotIndex, const FString& CharacterId, const FString& Tier)
	{
''' + FIXTURE_SLOT.replace("\n\t", "\n\t\t").replace("\t// N1", "\t\t// N1", 1) + '''		if (!Player.Shop.Slots.IsValidIndex(SlotIndex)) return false;
		FTreadM1ShopSlot& Slot = Player.Shop.Slots[SlotIndex];'''),
    ('''		Slot.OperatorTier = Tier;
		Slot.Cost = PurchaseCostFor(CharacterId, 1);
		Slot.bIsSold = !RecordPoolLedger(TEXT("Reserve"), Player.PlayerId, Slot, -1);
		return !Slot.bIsSold;
	};''', '''		Slot.OperatorTier = UseTier;
		Slot.Cost = PurchaseCostFor(CharacterId, HasN1Economy() ? TierPrice(UseTier) : 1);
		Slot.bIsSold = !RecordPoolLedger(TEXT("Reserve"), Player.PlayerId, Slot, -1);
		return !Slot.bIsSold;
	};'''),
    ('''	bool bEveryCardHasTrait = PactData->Cards.Num() == 100;''', '''	bool bEveryCardHasTrait = PactData->Cards.Num() == (HasN1Economy() ? 112 : 100);'''),
], "BoundTier")

patch(SRC / "TreadM2PactRuntime.cpp", [
    ('''	if (!Player.Shop.Slots.IsValidIndex(SlotIndex)) return false;
	FTreadM1ShopSlot& Slot = Player.Shop.Slots[SlotIndex];
	if (!Slot.bIsSold && !Slot.CharacterId.IsEmpty()) RecordPoolLedger(TEXT("RefreshReturn"), Player.PlayerId, Slot, 1);
	Slot.CharacterId = CharacterId;
	Slot.OperatorTier = Tier;
	Slot.Cost = PurchaseCostFor(CharacterId, 1);''', FIXTURE_SLOT + '''	if (!Player.Shop.Slots.IsValidIndex(SlotIndex)) return false;
	FTreadM1ShopSlot& Slot = Player.Shop.Slots[SlotIndex];
	if (!Slot.bIsSold && !Slot.CharacterId.IsEmpty()) RecordPoolLedger(TEXT("RefreshReturn"), Player.PlayerId, Slot, 1);
	Slot.CharacterId = CharacterId;
	Slot.OperatorTier = UseTier;
	Slot.Cost = PurchaseCostFor(CharacterId, HasN1Economy() ? TierPrice(UseTier) : 1);'''),
], "const FString UseTier")
