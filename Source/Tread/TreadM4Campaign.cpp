// M4 campaign (document/152 and the M4 plan): 16 stages from Campaign16.json, sequential unlock saved in
// UTreadCampaignSave, per-stage rule modifiers, and the scripted R1-R2 garrisons / R12 leaders of LeaderRounds.json.
// A free match (CampaignStage 0) keeps the M1 rehearsal pairings so the M1/M2 regressions stay comparable.

#include "TreadM1MatchController.h"

#include "Kismet/GameplayStatics.h"
#include "TreadCampaignSave.h"

namespace
{
	const TCHAR* ScriptedPlayerId = TEXT("SCRIPTED");
}

const FTreadM4CampaignStage* ATreadM1MatchController::ActiveCampaignStage() const
{
	return MatchState.CampaignStage > 0 && PactData.IsValid() ? PactData->FindStage(MatchState.CampaignStage) : nullptr;
}

const FTreadM4ScriptedOpponent* ATreadM1MatchController::ScriptedOpponentForRound() const
{
	const FTreadM4CampaignStage* Stage = ActiveCampaignStage();
	if (!Stage) return nullptr;
	if (MatchState.RoundType == ETreadM1RoundType::PvE) return PactData->FindGarrison(MatchState.RoundIndex);
	if (MatchState.RoundType == ETreadM1RoundType::Leader)
	{
		const FTreadM4ScriptedOpponent* Leader = PactData->FindLeader(Stage->LeaderId);
		return Leader ? Leader : PactData->FindLeader(PactData->DefaultLeaderId);
	}
	return nullptr;
}

void ATreadM1MatchController::BuildScriptedOpponent(const FTreadM4ScriptedOpponent& Def)
{
	const FTreadM4CampaignStage* Stage = ActiveCampaignStage();
	ScriptedState = FTreadM1PlayerState();
	ScriptedState.PlayerId = ScriptedPlayerId;
	ScriptedState.DisplayName = Def.DisplayName;
	ScriptedState.Level = Stage ? Stage->AiLevel * 2 : 2;
	TArray<FString> Characters = Def.UnitCharacters;
	TArray<int32> Stars = Def.UnitStars;
	if (Def.Kind == TEXT("Garrison") && Stage && !Def.ExtraUnitCharacterId.IsEmpty())
	{
		// garrisonBonus: "PvE守军每回合+N" adds N copies of the garrison's extra unit.
		for (int32 Extra = 0; Extra < Stage->GarrisonBonus; ++Extra)
		{
			Characters.Add(Def.ExtraUnitCharacterId);
			Stars.Add(1);
		}
	}
	for (int32 Index = 0; Index < Characters.Num(); ++Index)
	{
		FTreadM1UnitInstance Unit;
		Unit.UnitInstanceId = FString::Printf(TEXT("%s_%s_%02d"), ScriptedPlayerId, *Def.OpponentId, Index);
		Unit.CharacterId = Characters[Index];
		Unit.OperatorTier = CardTier(Unit.CharacterId);
		Unit.OriginalOperatorName = GetCardDisplayName(Unit.CharacterId);
		Unit.UnitStar = Stars.IsValidIndex(Index) ? Stars[Index] : 1;
		Unit.Cost = FMath::Max(1, TierPrice(Unit.OperatorTier));
		Unit.Location = ETreadM1UnitLocation::Board;
		// The scripted side stands on the enemy half, rows 0-3, filled from the front row back.
		Unit.BoardCell = FIntPoint(Index % 8, 3 - FMath::Min(3, Index / 8));
		Unit.OwnerPlayerId = ScriptedPlayerId;
		Unit.PoolCopiesHeld = 0;
		ScriptedState.BoardUnits.Add(Unit);
	}
	ScriptedState.PopulationUsed = ScriptedState.BoardUnits.Num();
	MatchState.ScriptedOpponentId = Def.OpponentId;
	MatchState.ScriptedOpponentName = Def.DisplayName;
	MatchState.ScriptedOpponentUnits = ScriptedState.BoardUnits;
	if (Def.Kind == TEXT("Leader"))
	{
		MatchState.ScriptedOpponentMaxHealth = Def.Health;
		MatchState.ScriptedOpponentHealth = Def.Health;
	}
}

int32 ATreadM1MatchController::ApplyDamageTaken(const FTreadM1PlayerState& Player, int32 Damage) const
{
	const FTreadM4CampaignStage* Stage = ActiveCampaignStage();
	if (!Stage || !Player.bIsHuman) return Damage;
	// damageTakenPercent: "战败时地标受到伤害+N%" scales the player's base-health loss.
	return FMath::Max(1, FMath::RoundToInt(Damage * Stage->DamageTakenPercent / 100.0f));
}

void ATreadM1MatchController::LoadCampaignProgress()
{
	ConqueredStages.Reset();
	if (UTreadCampaignSave* Save = Cast<UTreadCampaignSave>(UGameplayStatics::LoadGameFromSlot(UTreadCampaignSave::SlotName, 0)))
	{
		ConqueredStages = Save->ConqueredStages;
	}
}

void ATreadM1MatchController::SaveCampaignProgress() const
{
	UTreadCampaignSave* Save = Cast<UTreadCampaignSave>(UGameplayStatics::CreateSaveGameObject(UTreadCampaignSave::StaticClass()));
	if (!Save) return;
	Save->ConqueredStages = ConqueredStages;
	Save->LastStage = MatchState.CampaignStage;
	UGameplayStatics::SaveGameToSlot(Save, UTreadCampaignSave::SlotName, 0);
}

void ATreadM1MatchController::RecordCampaignResult()
{
	if (!ActiveCampaignStage()) return;
	const FTreadM1PlayerState* Human = FindPlayer(TEXT("P0"));
	RankPlayers();
	const bool bWon = Human && !Human->bIsEliminated && Human->Rank == 1;
	if (!bWon)
	{
		// Defeat costs nothing: the stage stays unlocked and can be replayed.
		MatchState.CampaignResult = TEXT("Failed");
		return;
	}
	ConqueredStages.AddUnique(MatchState.CampaignStage);
	ConqueredStages.Sort();
	const int32 StageCount = PactData.IsValid() ? PactData->CampaignStages.Num() : 16;
	MatchState.CampaignResult = ConqueredStages.Num() >= StageCount ? TEXT("WorldDomination") : TEXT("Conquered");
	SaveCampaignProgress();
	// "Continue" re-initializes the match: point it at the next stage (a defeat keeps the same one for a replay).
	if (PactData->FindStage(MatchState.CampaignStage + 1)) PendingCampaignStage = MatchState.CampaignStage + 1;
}

TArray<FTreadM4CampaignStageView> ATreadM1MatchController::GetCampaignStages() const
{
	TArray<FTreadM4CampaignStageView> Out;
	if (!PactData.IsValid()) return Out;
	for (const FTreadM4CampaignStage& Stage : PactData->CampaignStages)
	{
		FTreadM4CampaignStageView View;
		View.Index = Stage.Index;
		View.Country = Stage.Country;
		View.Landmark = Stage.Landmark;
		View.Rule = Stage.Rule;
		View.Effect = Stage.Effect;
		View.AiLevel = Stage.AiLevel;
		View.bConquered = ConqueredStages.Contains(Stage.Index);
		// Sequential unlock: stage 1 is always open, stage N once N-1 is conquered.
		View.bUnlocked = Stage.Index == 1 || ConqueredStages.Contains(Stage.Index - 1) || View.bConquered;
		Out.Add(View);
	}
	return Out;
}

FTreadM1CommandResult ATreadM1MatchController::SelectCampaignStage(int32 StageIndex, const FString& RequestId)
{
	if (MatchState.Phase != ETreadM1Phase::R0Briefing && MatchState.Phase != ETreadM1Phase::MainMenu)
	{
		return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
	}
	if (StageIndex != 0)
	{
		const TArray<FTreadM4CampaignStageView> Stages = GetCampaignStages();
		const FTreadM4CampaignStageView* View = Stages.FindByPredicate([StageIndex](const FTreadM4CampaignStageView& S) { return S.Index == StageIndex; });
		if (!View || !View->bUnlocked)
		{
			return Reject(ETreadM1RejectReason::InvalidPhase, RequestId);
		}
	}
	PendingCampaignStage = StageIndex;
	InitializeMatch(MatchState.Seed);
	return Accept(RequestId);
}

void ATreadM1MatchController::SetCampaignProgressForTest(int32 Count)
{
	ConqueredStages.Reset();
	for (int32 Index = 1; Index <= Count; ++Index) ConqueredStages.Add(Index);
	SaveCampaignProgress();
	OnStateChanged.Broadcast();
}

bool ATreadM1MatchController::GrantItemForTest(const FString& PlayerId, const FString& ItemId)
{
	FTreadM1PlayerState* Player = FindPlayer(PlayerId);
	const FTreadM2Item* Item = FindItemData(ItemId);
	if (!Player || !Item) return false;
	Player->EquipmentIds.Add(Item->ItemId);
	OnStateChanged.Broadcast();
	return true;
}

FString ATreadM1MatchController::GetUnitCombatSummary(const FString& PlayerId, const FString& UnitInstanceId) const
{
	const FTreadM1PlayerState* Player = FindPlayer(PlayerId);
	if (!Player) return FString();
	for (const TArray<FTreadM1UnitInstance>* Units : {&Player->BenchUnits, &Player->BoardUnits})
	{
		for (const FTreadM1UnitInstance& Unit : *Units)
		{
			if (Unit.UnitInstanceId != UnitInstanceId) continue;
			const FTreadM2UnitCombat Combat = ComputeUnitCombat(*Player, Unit);
			return FString::Printf(TEXT("attack=%.3f health=%.3f damageTaken=%.3f skillEvery=%d spUnits=%d"), Combat.AttackMul, Combat.HealthMul,
				Combat.DamageTaken, Combat.SkillEvery, BattleSp.Num());
		}
	}
	return FString();
}

bool ATreadM1MatchController::SetUnitStarForTest(const FString& PlayerId, const FString& UnitInstanceId, int32 Star)
{
	FTreadM1PlayerState* Player = FindPlayer(PlayerId);
	if (!Player) return false;
	for (TArray<FTreadM1UnitInstance>* Units : { &Player->BenchUnits, &Player->BoardUnits })
	{
		for (FTreadM1UnitInstance& Unit : *Units)
		{
			if (Unit.UnitInstanceId != UnitInstanceId) continue;
			Unit.UnitStar = FMath::Clamp(Star, 1, 3);
			OnStateChanged.Broadcast();
			return true;
		}
	}
	return false;
}

FString ATreadM1MatchController::FinishCampaignForTest(bool bWon)
{
	if (!ActiveCampaignStage()) return TEXT("NoCampaign");
	if (FTreadM1PlayerState* Human = FindPlayer(TEXT("P0")))
	{
		for (FTreadM1PlayerState& Player : MatchState.Players)
		{
			Player.Health = Player.bIsHuman == bWon ? 100 : 1;
		}
		Human->bIsEliminated = !bWon;
	}
	MatchState.PhaseTimeRemainingSec = 0.0f;
	RecordCampaignResult();
	SetPhase(ETreadM1Phase::GameOver);
	return MatchState.CampaignResult;
}
