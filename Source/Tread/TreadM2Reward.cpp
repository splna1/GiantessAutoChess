// N1 reward offer (document/176): Economy.json "rewardOffer" - three free item choices at the start of
// every preparation. The offer is rolled per player, costs nothing (price 0), cannot be refreshed or
// frozen, and expires at the end of the round. The AI simply takes the first choice.

#include "TreadM1MatchController.h"

int32 ATreadM1MatchController::RewardTierCap(const FTreadM1PlayerState& Player) const
{
	if (!PactData.IsValid()) return 1;
	const FTreadN1Economy& Economy = PactData->Economy;
	return FMath::Clamp(Player.Level + Economy.RewardTierOffset, 1, FMath::Max(1, Economy.RewardMaxTier));
}

void ATreadM1MatchController::RollRewardOffer(FTreadM1PlayerState& Player)
{
	Player.RewardOffer.Reset();
	Player.bRewardClaimed = false;
	if (!PactData.IsValid() || !PactData->bLoaded || !PactData->Economy.bLoaded) return;

	const int32 Count = FMath::Clamp(PactData->Economy.RewardCount, 0, 8);
	if (Count <= 0) return;
	const int32 Cap = RewardTierCap(Player);

	TArray<const FTreadM2Item*> Pool;
	for (const FTreadM2Item& Item : PactData->Items)
	{
		if (Item.ItemId.IsEmpty() || Item.bSpell) continue;
		if (Item.Tier < 1 || Item.Tier > Cap) continue;
		Pool.Add(&Item);
	}
	for (int32 Pick = 0; Pick < Count && Pool.Num() > 0; ++Pick)
	{
		const int32 Index = RandomStream.RandRange(0, Pool.Num() - 1);
		Player.RewardOffer.Add(Pool[Index]->ItemId);
		Pool.RemoveAt(Index);
	}
	SyncRandomState();
}

FTreadM1CommandResult ATreadM1MatchController::ChooseReward(const FString& PlayerId, int32 Index,
	const FString& RequestId)
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
	if (Player->bRewardClaimed || !Player->RewardOffer.IsValidIndex(Index))
	{
		return Reject(ETreadM1RejectReason::RewardUnavailable, RequestId);
	}
	const FString ItemId = Player->RewardOffer[Index];
	const FTreadM2Item* Item = PactData.IsValid() ? PactData->FindItem(ItemId) : nullptr;
	if (!Item)
	{
		return Reject(ETreadM1RejectReason::ItemUnavailable, RequestId);
	}
	Player->EquipmentIds.Add(Item->ItemId);
	Player->bRewardClaimed = true;
	RecordTraitLog(*Player, ETreadM2Trigger::Passive, TEXT("RewardOffer"), nullptr, Item->ItemId,
		TEXT("ChooseReward"), FString(), 1, 0, false, TEXT("applied"), Item->DisplayName);
	RefreshScoutSnapshots();
	OnStateChanged.Broadcast();
	return Accept(RequestId);
}
