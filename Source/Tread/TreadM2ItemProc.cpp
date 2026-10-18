// Item procs (document/175): the conditional / per-tick half of the M4 equipment catalogue.
//
// The battle simulation is deliberately abstract: one exchange is one battle second and every alive unit
// attacks once. The procs therefore model the Stronghold-Protocol effects as exchange-level rules
// (damage windows, stun uptime, lifesteal, burns, revives) instead of per-frame gameplay code. All
// numbers come from ItemCatalog.json, so the wiring tool stays the single source of truth.

#include "TreadM1MatchController.h"

namespace
{
	/** Equipment ids carry the base id and an `_a` / `_b` (Ⅱ) suffix; set bonuses match either. */
	bool HasEquippedBase(const FTreadM1UnitInstance& Unit, const FString& BaseId)
	{
		for (const FString& ItemId : Unit.EquipmentIds)
		{
			if (ItemId == BaseId || ItemId.StartsWith(BaseId + TEXT("_"))) return true;
		}
		return false;
	}
}

bool FTreadM2UnitProcs::IsEmpty() const
{
	return FMath::IsNearlyEqual(DamageScale, 1.0f) && FMath::IsNearlyEqual(DamageTakenScale, 1.0f) &&
		StunChance <= 0.0f && Lifesteal <= 0.0f && Regen <= 0.0f && ReviveCount == 0 && UndyingDuration <= 0.0f &&
		SpInitial == 0 && SpRegen <= 0.0f && AmmoRefundChance <= 0.0f && ExtraHitChance <= 0.0f &&
		ReflectScale <= 0.0f && AttackStack <= 0.0f && AttackPerSkill <= 0.0f && AttackSpeedFlat <= 0.0f &&
		BurnScale <= 0.0f && SilenceDuration <= 0.0f && HealthConditional <= 0.0f && !bTaunt && !bImmuneAbove &&
		SelfDot <= 0.0f && RedeployCount == 0 && NeighborAttackSpeed <= 0.0f && Penetrate <= 0.0f &&
		RecruitOnEquip.IsEmpty() && StealthDuration <= 0.0f && ShieldOnHealChance <= 0.0f && SellCounter <= 0 &&
		!bPostBattleTransform && SkillBuffValue <= 0.0f && AtkRamp <= 0.0f && AttackSpeedPerAcquire <= 0.0f &&
		FundsPerAcquire <= 0 && !bBondGrant;
}

FTreadM2UnitProcs ATreadM1MatchController::ComputeUnitProcs(const FTreadM1PlayerState& Player,
	const FTreadM1UnitInstance& Unit) const
{
	FTreadM2UnitProcs Out;
	if (!PactData.IsValid()) return Out;

	const FTreadM2Card* Card = PactData->FindCard(Unit.CharacterId);
	const bool bRanged = Card && (Card->AttackKind == TEXT("ranged") || Card->AttackKind == TEXT("heal"));
	const TArray<FString> Pacts = GetUnitPacts(Player, Unit, false);

	// "身前一格" follows the 阿戈尔 convention: right (X+1) is the front.
	bool bFrontEmpty = true;
	for (const FTreadM1UnitInstance& Other : Player.BoardUnits)
	{
		if (Other.UnitInstanceId == Unit.UnitInstanceId) continue;
		if (Other.BoardCell == Unit.BoardCell + FIntPoint(1, 0)) { bFrontEmpty = false; break; }
	}

	for (const FString& ItemId : Unit.EquipmentIds)
	{
		const FTreadM2Item* Item = PactData->FindItem(ItemId);
		if (!Item) continue;
		for (const FTreadM2ItemProc& Proc : Item->Procs)
		{
			if (!Proc.Partner.IsEmpty() && !HasEquippedBase(Unit, Proc.Partner)) continue;
			if (Proc.Condition == TEXT("Ranged") && !bRanged) continue;
			if (Proc.Condition == TEXT("Ground") && bRanged) continue;
			if (Proc.Condition == TEXT("FrontEmpty") && !bFrontEmpty) continue;
			if (Proc.Condition.StartsWith(TEXT("Pact:")) && !Pacts.Contains(Proc.Condition.RightChop(5))) continue;

			if (Proc.Op == TEXT("DamageScale"))
			{
				Out.DamageScale *= FMath::Max(0.1f, Proc.Value);
				Out.DamageScaleWindow = FMath::Max(Out.DamageScaleWindow, Proc.Window);
				Out.DamageScaleDecay = FMath::Max(Out.DamageScaleDecay, Proc.Decay);
			}
			else if (Proc.Op == TEXT("DamageTakenScale"))
			{
				Out.DamageTakenScale *= FMath::Clamp(Proc.Value, 0.1f, 1.0f);
			}
			else if (Proc.Op == TEXT("Stun"))
			{
				Out.StunChance = 1.0f - (1.0f - Out.StunChance) * (1.0f - FMath::Clamp(Proc.Chance, 0.0f, 1.0f));
				Out.StunDuration = FMath::Max(Out.StunDuration, Proc.Duration);
				Out.StunWindow = FMath::Max(Out.StunWindow, Proc.Window);
			}
			else if (Proc.Op == TEXT("Lifesteal")) Out.Lifesteal += Proc.Value;
			else if (Proc.Op == TEXT("Regen")) Out.Regen += Proc.Value;
			else if (Proc.Op == TEXT("Revive"))
			{
				Out.ReviveCount += FMath::Max(1, Proc.Count);
				Out.ReviveHealth = Proc.Value > 0.0f ? Proc.Value : 0.5f;
			}
			else if (Proc.Op == TEXT("Undying")) Out.UndyingDuration = FMath::Max(Out.UndyingDuration, Proc.Duration);
			else if (Proc.Op == TEXT("SpInitial"))
			{
				Out.SpInitial += FMath::RoundToInt(Proc.Value);
				Out.SpPerPactMember += Proc.PerPactMember;
			}
			else if (Proc.Op == TEXT("SpRegen")) Out.SpRegen += Proc.Value;
			else if (Proc.Op == TEXT("AmmoRefund"))
			{
				Out.AmmoRefundChance = FMath::Max(Out.AmmoRefundChance, Proc.Chance);
				Out.AmmoRefundPercent = FMath::Max(Out.AmmoRefundPercent, Proc.Percent);
				Out.AmmoRefundMax = FMath::Max(Out.AmmoRefundMax, Proc.Max);
			}
			else if (Proc.Op == TEXT("ExtraHit"))
			{
				Out.ExtraHitChance = 1.0f - (1.0f - Out.ExtraHitChance) * (1.0f - FMath::Clamp(Proc.Chance, 0.0f, 1.0f));
				Out.ExtraHitScale = FMath::Max(Out.ExtraHitScale, Proc.ValuePartner > 0.0f ? Proc.ValuePartner : Proc.Value);
			}
			else if (Proc.Op == TEXT("Reflect")) Out.ReflectScale += Proc.Value;
			else if (Proc.Op == TEXT("AttackStack"))
			{
				Out.AttackStack = FMath::Max(Out.AttackStack, Proc.Value);
				Out.AttackStackMax = FMath::Max(Out.AttackStackMax, Proc.Max);
			}
			else if (Proc.Op == TEXT("AttackPerSkill"))
			{
				Out.AttackPerSkill = FMath::Max(Out.AttackPerSkill, Proc.Value);
				Out.AttackPerSkillMax = FMath::Max(Out.AttackPerSkillMax, Proc.Max);
			}
			else if (Proc.Op == TEXT("AttackSpeedFlat")) Out.AttackSpeedFlat += Proc.Value;
			else if (Proc.Op == TEXT("Burn")) Out.BurnScale += Proc.Value;
			else if (Proc.Op == TEXT("Silence")) Out.SilenceDuration = FMath::Max(Out.SilenceDuration, Proc.Duration);
			else if (Proc.Op == TEXT("Taunt")) Out.bTaunt = true;
			else if (Proc.Op == TEXT("StatusImmune"))
			{
				Out.bImmuneAbove = true;
				Out.ImmuneHpRatio = FMath::Max(Out.ImmuneHpRatio, Proc.HpRatio);
			}
			else if (Proc.Op == TEXT("HealthConditional")) Out.HealthConditional += Proc.Value;
			else if (Proc.Op == TEXT("SelfDot")) Out.SelfDot += Proc.Value;
			else if (Proc.Op == TEXT("Redeploy"))
			{
				Out.RedeployCount += FMath::Max(1, Proc.Count);
				Out.RedeployHealth = Proc.Value > 0.0f ? Proc.Value : 0.4f;
			}
			else if (Proc.Op == TEXT("NeighborAttackSpeed")) Out.NeighborAttackSpeed += Proc.Value;
			else if (Proc.Op == TEXT("Penetrate")) Out.Penetrate += Proc.Value;
			else if (Proc.Op == TEXT("RecruitPactUnit")) Out.RecruitOnEquip = TEXT("Pact");
			else if (Proc.Op == TEXT("RecruitSameTierUnit")) Out.RecruitOnEquip = TEXT("Tier");
			else if (Proc.Op == TEXT("StealthAfterHit")) Out.StealthDuration = FMath::Max(Out.StealthDuration, Proc.Duration);
			else if (Proc.Op == TEXT("ShieldOnHeal"))
			{
				Out.ShieldOnHealChance = FMath::Max(Out.ShieldOnHealChance, Proc.Chance);
				Out.ShieldOnHealMax = FMath::Max(Out.ShieldOnHealMax, Proc.Max > 0 ? Proc.Max : 1);
			}
			else if (Proc.Op == TEXT("SellCounterRecruit")) Out.SellCounter = FMath::Max(Out.SellCounter, Proc.Count);
			else if (Proc.Op == TEXT("PostBattleTransform")) Out.bPostBattleTransform = true;
			else if (Proc.Op == TEXT("SkillWindowBuff"))
			{
				Out.SkillBuffValue = FMath::Max(Out.SkillBuffValue, Proc.Value);
				Out.SkillBuffDuration = FMath::Max(Out.SkillBuffDuration, Proc.Duration);
			}
			else if (Proc.Op == TEXT("AtkRamp"))
			{
				Out.AtkRamp = FMath::Max(Out.AtkRamp, Proc.Value);
				Out.AtkRampCap = FMath::Max(Out.AtkRampCap, Proc.Max);
			}
			else if (Proc.Op == TEXT("AttackSpeedPerAcquire"))
			{
				Out.AttackSpeedPerAcquire = FMath::Max(Out.AttackSpeedPerAcquire, Proc.Value);
				Out.AttackSpeedPerAcquireMax = FMath::Max(Out.AttackSpeedPerAcquireMax, Proc.Max);
			}
			else if (Proc.Op == TEXT("FundsPerAcquire"))
			{
				Out.FundsPerAcquire += FMath::RoundToInt(Proc.Value);
				Out.FundsPerAcquireMax = FMath::Max(Out.FundsPerAcquireMax, Proc.Max);
			}
			else if (Proc.Op == TEXT("BondGrant")) Out.bBondGrant = true;
		}
	}

	// 3_05: extra SP for every other board member sharing one of this unit's pacts.
	if (Out.SpPerPactMember > 0)
	{
		for (const FTreadM1UnitInstance& Other : Player.BoardUnits)
		{
			if (Other.UnitInstanceId == Unit.UnitInstanceId) continue;
			const TArray<FString> OtherPacts = GetUnitPacts(Player, Other, false);
			bool bShared = false;
			for (const FString& Pact : Pacts) { bShared |= OtherPacts.Contains(Pact); }
			if (bShared) Out.SpInitial += Out.SpPerPactMember;
		}
	}
	return Out;
}

void ATreadM1MatchController::BuildBattleSide(FTreadM2BattleSide& Side, FTreadM1PlayerState& Player)
{
	Side = FTreadM2BattleSide();
	Side.Player = &Player;
	for (int32 Index = 0; Index < Player.BoardUnits.Num(); ++Index)
	{
		const FTreadM1UnitInstance& Unit = Player.BoardUnits[Index];
		FTreadM2UnitCombat Combat = ComputeUnitCombat(Player, Unit);
		const FTreadM2UnitProcs Procs = ComputeUnitProcs(Player, Unit);
		// 6_03: attack speed grows with the operators acquired this round (max 3 layers).
		if (Procs.AttackSpeedPerAcquire > 0.0f)
		{
			const int32 AcquireLayers = FMath::Min(Player.AcquiredThisRound, FMath::Max(1, Procs.AttackSpeedPerAcquireMax));
			Combat.AttackMul = FMath::Clamp(Combat.AttackMul * (1.0f + 0.005f * Procs.AttackSpeedPerAcquire * AcquireLayers), 0.5f, 4.0f);
		}
		const int32 Health = FMath::Max(2, FMath::RoundToInt(
			(3 + Unit.Cost * Unit.UnitStar) * Combat.HealthMul * (1.0f + Procs.HealthConditional)));
		Side.Combat.Add(Combat);
		Side.Procs.Add(Procs);
		Side.Health.Add(Health);
		Side.MaxHealth.Add(Health);
		Side.StunUntil.Add(0);
		Side.ReviveLeft.Add(Procs.ReviveCount);
		Side.BurnUntil.Add(0);
		Side.BurnDamage.Add(0);
		Side.Attacks.Add(0);
		Side.Targets.Add(INDEX_NONE);
		Side.UndyingUntil.Add(0);
		Side.DamageScale.Add(1.0f);
		Side.AmmoRefundLeft.Add(Procs.AmmoRefundMax);
		Side.RedeployAt.Add(0);
		Side.RedeployLeft.Add(Procs.RedeployCount);
		Side.StealthUntil.Add(0);
		Side.Shield.Add(0);
		Side.Alive += Health > 0 ? 1 : 0;
	}
	// 3_01: the holder grants attack speed to the allies on its left and right cells.
	for (int32 Index = 0; Index < Side.Procs.Num() && Index < Player.BoardUnits.Num(); ++Index)
	{
		const float Aura = Side.Procs[Index].NeighborAttackSpeed;
		if (Aura <= 0.0f) continue;
		const FIntPoint Cell = Player.BoardUnits[Index].BoardCell;
		for (int32 Other = 0; Other < Side.Combat.Num() && Other < Player.BoardUnits.Num(); ++Other)
		{
			if (Other == Index) continue;
			const FIntPoint OtherCell = Player.BoardUnits[Other].BoardCell;
			if (FMath::Abs(OtherCell.X - Cell.X) != 1 || OtherCell.Y != Cell.Y) continue;
			Side.Combat[Other].AttackMul = FMath::Clamp(Side.Combat[Other].AttackMul * (1.0f + 0.005f * Aura), 0.5f, 4.0f);
		}
	}
}

void ATreadM1MatchController::SyncBattleSide(FTreadM2BattleSide& Side)
{
	// 炎 summons append to BoardUnits/Health/Combat after the side was built.
	const int32 Count = FMath::Min(Side.Health.Num(), Side.Player->BoardUnits.Num());
	while (Side.Procs.Num() < Count) Side.Procs.Add(ComputeUnitProcs(*Side.Player, Side.Player->BoardUnits[Side.Procs.Num()]));
	while (Side.MaxHealth.Num() < Count) Side.MaxHealth.Add(Side.Health[Side.MaxHealth.Num()]);
	while (Side.StunUntil.Num() < Count) Side.StunUntil.Add(0);
	while (Side.ReviveLeft.Num() < Count) Side.ReviveLeft.Add(Side.Procs[Side.ReviveLeft.Num()].ReviveCount);
	while (Side.BurnUntil.Num() < Count) Side.BurnUntil.Add(0);
	while (Side.BurnDamage.Num() < Count) Side.BurnDamage.Add(0);
	while (Side.Attacks.Num() < Count) Side.Attacks.Add(0);
	while (Side.Targets.Num() < Count) Side.Targets.Add(INDEX_NONE);
	while (Side.UndyingUntil.Num() < Count) Side.UndyingUntil.Add(0);
	while (Side.DamageScale.Num() < Count) Side.DamageScale.Add(1.0f);
	while (Side.AmmoRefundLeft.Num() < Count) Side.AmmoRefundLeft.Add(Side.Procs[Side.AmmoRefundLeft.Num()].AmmoRefundMax);
	while (Side.RedeployAt.Num() < Count) Side.RedeployAt.Add(0);
	while (Side.RedeployLeft.Num() < Count) Side.RedeployLeft.Add(Side.Procs[Side.RedeployLeft.Num()].RedeployCount);
	while (Side.StealthUntil.Num() < Count) Side.StealthUntil.Add(0);
	while (Side.Shield.Num() < Count) Side.Shield.Add(0);
	Side.Alive = 0;
	for (int32 Index = 0; Index < Count; ++Index) Side.Alive += Side.Health[Index] > 0 ? 1 : 0;
}

void ATreadM1MatchController::ApplyBattleStartProcs(FTreadM2BattleSide& Side)
{
	for (int32 Index = 0; Index < Side.Health.Num() && Index < Side.Player->BoardUnits.Num(); ++Index)
	{
		if (Side.Health[Index] <= 0) continue;
		const FTreadM2UnitProcs& Procs = Side.Procs[Index];
		const FString& UnitId = Side.Player->BoardUnits[Index].UnitInstanceId;
		if (Procs.SpInitial > 0)
		{
			BattleSp.FindOrAdd(UnitId) = FMath::Clamp(BattleSp.FindRef(UnitId) + Procs.SpInitial, 0.0f, 100.0f);
		}
		if (Procs.UndyingDuration > 0.0f)
		{
			Side.UndyingUntil[Index] = FMath::CeilToInt(Procs.UndyingDuration);
		}
	}
}

void ATreadM1MatchController::TickBattleSideProcs(FTreadM2BattleSide& Side, int32 Exchange)
{
	for (int32 Index = 0; Index < Side.Health.Num(); ++Index)
	{
		if (Side.Health[Index] <= 0)
		{
			// 2_01: the redeploy timer brings the unit back after its shortened wait.
			if (Side.RedeployAt.IsValidIndex(Index) && Side.RedeployAt[Index] > 0 && Exchange >= Side.RedeployAt[Index])
			{
				Side.RedeployAt[Index] = 0;
				Side.Health[Index] = FMath::Max(2, FMath::RoundToInt(Side.MaxHealth[Index] * Side.Procs[Index].RedeployHealth));
				++Side.Alive;
				RecordBattleEvent(ETreadM1BattleEventType::ItemProc, Side.Player->PlayerId, Side.Player->PlayerId, 0,
					FString(), Side.Player->BoardUnits[Index].UnitInstanceId);
			}
			continue;
		}
		const FTreadM2UnitProcs& Procs = Side.Procs[Index];
		// 4_07: the opening damage window decays every second.
		if (Procs.DamageScaleWindow > 0.0f)
		{
			Side.DamageScale[Index] = Exchange >= Procs.DamageScaleWindow
				? 1.0f : FMath::Max(1.0f, Procs.DamageScale - Procs.DamageScaleDecay * Exchange);
		}
		if (Procs.Regen > 0.0f && Side.Health[Index] < Side.MaxHealth[Index])
		{
			Side.Health[Index] = FMath::Min(Side.MaxHealth[Index],
				Side.Health[Index] + FMath::RoundToInt(Side.MaxHealth[Index] * Procs.Regen));
			// 4_11: a heal can grant one shield stack.
			if (Procs.ShieldOnHealChance > 0.0f && Side.Shield[Index] < FMath::Max(1, Procs.ShieldOnHealMax) &&
				RandomStream.FRand() < Procs.ShieldOnHealChance)
			{
				++Side.Shield[Index];
			}
		}
		// 1_05: the holder bleeds its own max HP every battle second.
		if (Procs.SelfDot > 0.0f)
		{
			const FString UnitId = Side.Player->BoardUnits[Index].UnitInstanceId;
			ApplyBattleDamage(Side, Index, FMath::Max(1, FMath::RoundToInt(Side.MaxHealth[Index] * Procs.SelfDot)),
				Side.Player->PlayerId, UnitId);
		}
		if (Side.BurnUntil[Index] > Exchange && Side.BurnDamage[Index] > 0)
		{
			const FString UnitId = Side.Player->BoardUnits[Index].UnitInstanceId;
			ApplyBattleDamage(Side, Index, Side.BurnDamage[Index], Side.Player->PlayerId, UnitId);
		}
	}
}

int32 ATreadM1MatchController::SelectBattleTarget(const FTreadM2BattleSide& Defender, int32 Exchange) const
{
	const auto bIsHidden = [&Defender, Exchange](int32 Index)
	{
		return Defender.StealthUntil.IsValidIndex(Index) && Defender.StealthUntil[Index] > Exchange;
	};
	for (int32 Index = 0; Index < Defender.Health.Num(); ++Index)
	{
		if (Defender.Health[Index] > 0 && Defender.Procs[Index].bTaunt && !bIsHidden(Index)) return Index;
	}
	for (int32 Index = 0; Index < Defender.Health.Num(); ++Index)
	{
		if (Defender.Health[Index] > 0 && !bIsHidden(Index)) return Index;
	}
	// 4_04: if every survivor is hidden the attacker falls back to the first one instead of idling.
	for (int32 Index = 0; Index < Defender.Health.Num(); ++Index)
	{
		if (Defender.Health[Index] > 0) return Index;
	}
	return INDEX_NONE;
}

void ATreadM1MatchController::ApplyBattleDamage(FTreadM2BattleSide& Defender, int32 Index, int32 Damage,
	const FString& FromPlayerId, const FString& FromUnitId)
{
	if (!Defender.Health.IsValidIndex(Index) || Defender.Health[Index] <= 0) return;
	const FTreadM1UnitInstance& Unit = Defender.Player->BoardUnits[Index];
	const FTreadM2UnitProcs& Procs = Defender.Procs[Index];
	// 4_11: one shield stack eats the whole hit before any health is lost.
	if (Defender.Shield.IsValidIndex(Index) && Defender.Shield[Index] > 0)
	{
		--Defender.Shield[Index];
		RecordBattleEvent(ETreadM1BattleEventType::ItemProc, FromPlayerId, Defender.Player->PlayerId, 0,
			FromUnitId, Unit.UnitInstanceId);
		return;
	}
	// 3_09 / 6_05: the first lethal hit inside the window leaves 1 HP.
	if (Procs.UndyingDuration > 0.0f && Defender.UndyingUntil[Index] > 0 &&
		Defender.Health[Index] - Damage <= 0)
	{
		Defender.Health[Index] = 1;
		Defender.UndyingUntil[Index] = 0;
		RecordBattleEvent(ETreadM1BattleEventType::ItemProc, FromPlayerId, Defender.Player->PlayerId, 0,
			FromUnitId, Unit.UnitInstanceId);
		return;
	}
	Defender.Health[Index] -= Damage;
	BattleUnitHealth.Add(Unit.UnitInstanceId, FMath::Clamp(Defender.Health[Index] / 12.0f, 0.0f, 1.0f));
	RecordBattleEvent(ETreadM1BattleEventType::UnitDamaged, FromPlayerId, Defender.Player->PlayerId, Damage,
		FromUnitId, Unit.UnitInstanceId, FMath::Max(0, Defender.Health[Index]));
	// 4_04: the first damage taken turns the holder hidden for its window.
	if (Procs.StealthDuration > 0.0f && Defender.StealthUntil[Index] == 0)
	{
		Defender.StealthUntil[Index] = BattleExchangeIndex + FMath::Max(1, FMath::CeilToInt(Procs.StealthDuration));
	}
	if (Defender.Health[Index] > 0) return;
	ResolveBattleDeath(Defender, Index, FromPlayerId, FromUnitId, nullptr, INDEX_NONE);
}

void ATreadM1MatchController::ResolveBattleDeath(FTreadM2BattleSide& Defender, int32 Index,
	const FString& FromPlayerId, const FString& FromUnitId, const FTreadM2BattleSide* Killer, int32 KillerIndex)
{
	if (!Defender.Health.IsValidIndex(Index) || Defender.Health[Index] > 0) return;
	const FTreadM1UnitInstance& Unit = Defender.Player->BoardUnits[Index];
	const FTreadM2UnitProcs& Procs = Defender.Procs[Index];
	// 4_12: the item's own revive budget is spent before the pact's.
	if (Defender.ReviveLeft[Index] > 0)
	{
		Defender.ReviveLeft[Index]--;
		Defender.Health[Index] = FMath::Max(2, FMath::RoundToInt(Defender.MaxHealth[Index] * Procs.ReviveHealth));
		RecordBattleEvent(ETreadM1BattleEventType::ItemProc, FromPlayerId, Defender.Player->PlayerId, 0,
			FromUnitId, Unit.UnitInstanceId);
		return;
	}
	// 2_01: the shortened redeploy timer returns the unit two exchanges later.
	if (Defender.RedeployLeft.IsValidIndex(Index) && Defender.RedeployLeft[Index] > 0)
	{
		Defender.RedeployLeft[Index]--;
		Defender.RedeployAt[Index] = BattleExchangeIndex + 2;
		--Defender.Alive;
		RecordBattleEvent(ETreadM1BattleEventType::ItemProc, FromPlayerId, Defender.Player->PlayerId, 0,
			FromUnitId, Unit.UnitInstanceId);
		return;
	}
	if (TryPactRevive(*Defender.Player, Defender.Player->BoardUnits[Index], Defender.Health[Index]))
	{
		PactOnKnockDown(*Defender.Player);
		return;
	}
	PactOnKnockDown(*Defender.Player);
	--Defender.Alive;
	RecordBattleEvent(ETreadM1BattleEventType::UnitDied, FromPlayerId, Defender.Player->PlayerId, 0,
		FromUnitId, Unit.UnitInstanceId, 0);
	OnBattleUnitEvent(*Defender.Player, TEXT("SelfKnockedOut"), Unit);
	if (Killer && Killer->Player && Killer->Player->BoardUnits.IsValidIndex(KillerIndex))
	{
		OnBattleUnitEvent(*Killer->Player, TEXT("Kill"), Killer->Player->BoardUnits[KillerIndex]);
	}
}

void ATreadM1MatchController::GrantRecruitFromItem(FTreadM1PlayerState& Player, const FTreadM1UnitInstance& Unit,
	const FTreadM2Item& Item)
{
	if (!PactData.IsValid()) return;
	bool bPactMode = false;
	for (const FTreadM2ItemProc& Proc : Item.Procs)
	{
		if (Proc.Op == TEXT("RecruitPactUnit") || Proc.Op == TEXT("SellCounterRecruit")) bPactMode = true;
	}
	const TArray<FString> UnitPacts = GetUnitPacts(Player, Unit, false);
	const FString CurrentTier = CardTier(Unit.CharacterId);
	TArray<FString> Candidates;
	for (const FString& CardId : PactData->CardOrder)
	{
		if (CardId == Unit.CharacterId) continue;
		if (bPactMode)
		{
			bool bShared = false;
			for (const FString& Pact : GetCardPacts(CardId)) bShared |= UnitPacts.Contains(Pact);
			if (!bShared) continue;
		}
		else if (CardTier(CardId) != CurrentTier)
		{
			continue;
		}
		Candidates.Add(CardId);
	}
	if (Candidates.Num() == 0) return;
	const FString Pick = Candidates[RandomStream.RandRange(0, Candidates.Num() - 1)];
	SyncRandomState();
	GrantUnitToPlayer(Player, Pick, Item.ItemId, ETreadM2Trigger::Equip, 0);
}

void ATreadM1MatchController::ApplyPostBattleItemTransforms()
{
	if (!PactData.IsValid()) return;
	for (FTreadM1PlayerState& Player : MatchState.Players)
	{
		if (Player.bIsEliminated) continue;
		for (FTreadM1UnitInstance& Unit : Player.BoardUnits)
		{
			FString TriggerItem;
			for (const FString& ItemId : Unit.EquipmentIds)
			{
				const FTreadM2Item* Item = PactData->FindItem(ItemId);
				if (!Item) continue;
				for (const FTreadM2ItemProc& Proc : Item->Procs)
				{
					if (Proc.Op == TEXT("PostBattleTransform")) TriggerItem = ItemId;
				}
			}
			if (TriggerItem.IsEmpty()) continue;
			const int32 CurrentTier = TierPrice(CardTier(Unit.CharacterId));
			TArray<FString> Higher;
			for (const FString& CardId : PactData->CardOrder)
			{
				if (CardId == Unit.CharacterId) continue;
				if (TierPrice(CardTier(CardId)) > CurrentTier) Higher.Add(CardId);
			}
			if (Higher.Num() == 0) continue;
			const FString Was = Unit.CharacterId;
			Unit.CharacterId = Higher[RandomStream.RandRange(0, Higher.Num() - 1)];
			Unit.OriginalOperatorName = GetCardDisplayName(Unit.CharacterId);
			RecordTraitLog(Player, ETreadM2Trigger::BattleEnd, TEXT("PostBattleTransform"), &Unit, TriggerItem,
				TEXT("Transform"), FString(), 1, 0, IsElite(Unit), TEXT("applied"), Was + TEXT("->") + Unit.CharacterId);
		}
	}
	SyncRandomState();
}

void ATreadM1MatchController::RunBattleExchange(FTreadM2BattleSide& Attacker, FTreadM2BattleSide& Defender,
	int32 Exchange)
{
	for (int32 SourceIndex = 0; SourceIndex < Attacker.Player->BoardUnits.Num(); ++SourceIndex)
	{
		if (!Attacker.Health.IsValidIndex(SourceIndex) || Attacker.Health[SourceIndex] <= 0) continue;
		if (Attacker.StunUntil[SourceIndex] > Exchange) continue;
		const int32 TargetIndex = SelectBattleTarget(Defender, Exchange);
		if (TargetIndex == INDEX_NONE) break;
		const FTreadM1UnitInstance& SourceUnit = Attacker.Player->BoardUnits[SourceIndex];
		const FTreadM1UnitInstance& TargetUnit = Defender.Player->BoardUnits[TargetIndex];
		if (Attacker.Targets[SourceIndex] != TargetIndex)
		{
			Attacker.Targets[SourceIndex] = TargetIndex;
			RecordBattleEvent(ETreadM1BattleEventType::UnitTargetChanged, Attacker.Player->PlayerId,
				Defender.Player->PlayerId, 0, SourceUnit.UnitInstanceId, TargetUnit.UnitInstanceId);
		}
		const FTreadM2UnitProcs& SourceProcs = Attacker.Procs[SourceIndex];
		const FTreadM2UnitProcs& TargetProcs = Defender.Procs[TargetIndex];
		const float StackMul = 1.0f + 0.005f * SourceProcs.AttackStack * BattleAttackSpeedStacks.FindRef(SourceUnit.UnitInstanceId) +
			SourceProcs.AttackPerSkill * BattleSkillAtkStacks.FindRef(SourceUnit.UnitInstanceId) +
			0.005f * SourceProcs.AttackSpeedFlat;
		// 6_10: the post-skill window raises attack; 6_11 ramps it up over the battle.
		const float SkillMul = BattleSkillBuffUntil.FindRef(SourceUnit.UnitInstanceId) > Exchange
			? 1.0f + SourceProcs.SkillBuffValue : 1.0f;
		const float RampMul = 1.0f + FMath::Min(SourceProcs.AtkRampCap, SourceProcs.AtkRamp * Exchange);
		const int32 Base = FMath::RoundToInt(SourceUnit.Cost * SourceUnit.UnitStar * Attacker.Combat[SourceIndex].AttackMul *
			StackMul * SkillMul * RampMul * AmmoAttackMultiplier(*Attacker.Player, SourceUnit));
		// 3_03: magic-resist penetration eats part of the target's damage reduction.
		const float TakenMul = 1.0f - (1.0f - Defender.Combat[TargetIndex].DamageTaken) * (1.0f - FMath::Clamp(SourceProcs.Penetrate, 0.0f, 0.9f));
		int32 Damage = FMath::Max(1, FMath::RoundToInt(Base * Attacker.DamageScale[SourceIndex] *
			TakenMul * TargetProcs.DamageTakenScale));
		// 6_02 (拉特兰) / set bonuses: an extra damage instance rolled into the same hit.
		if (SourceProcs.ExtraHitChance > 0.0f && RandomStream.FRand() < SourceProcs.ExtraHitChance)
		{
			Damage += FMath::RoundToInt(Base * SourceProcs.ExtraHitScale);
		}
		// 4_11: a shield stack absorbs this hit entirely.
		if (Defender.Shield.IsValidIndex(TargetIndex) && Defender.Shield[TargetIndex] > 0)
		{
			--Defender.Shield[TargetIndex];
			RecordBattleEvent(ETreadM1BattleEventType::ItemProc, Attacker.Player->PlayerId,
				Defender.Player->PlayerId, 0, SourceUnit.UnitInstanceId, TargetUnit.UnitInstanceId);
			Damage = 0;
		}
		Defender.Health[TargetIndex] -= Damage;
		BattleUnitHealth.Add(TargetUnit.UnitInstanceId,
			FMath::Clamp(Defender.Health[TargetIndex] / 12.0f, 0.0f, 1.0f));
		RecordBattleEvent(ETreadM1BattleEventType::UnitDamaged, Attacker.Player->PlayerId,
			Defender.Player->PlayerId, Damage, SourceUnit.UnitInstanceId, TargetUnit.UnitInstanceId,
			FMath::Max(0, Defender.Health[TargetIndex]));
		// 4_04: the first hit taken turns the holder hidden for its window.
		if (TargetProcs.StealthDuration > 0.0f && Defender.StealthUntil[TargetIndex] == 0)
		{
			Defender.StealthUntil[TargetIndex] = Exchange + FMath::Max(1, FMath::CeilToInt(TargetProcs.StealthDuration));
		}
		HandleBattleAttack(*Attacker.Player, SourceUnit, Attacker.Attacks[SourceIndex], Attacker.Combat[SourceIndex],
			Defender.Player->PlayerId, TargetUnit.UnitInstanceId);
		if (Defender.Health[TargetIndex] <= 0)
		{
			ResolveBattleDeath(Defender, TargetIndex, Attacker.Player->PlayerId, SourceUnit.UnitInstanceId,
				&Attacker, SourceIndex);
		}
		if (SourceProcs.Lifesteal > 0.0f)
		{
			Attacker.Health[SourceIndex] = FMath::Min(Attacker.MaxHealth[SourceIndex],
				Attacker.Health[SourceIndex] + FMath::RoundToInt(Attacker.MaxHealth[SourceIndex] * SourceProcs.Lifesteal));
		}
		// 2_03 / 3_11 / 5_01 / 5_02 / 6_05: stun rolls, skipped by 4_10 while healthy.
		if (SourceProcs.StunChance > 0.0f && Defender.Health[TargetIndex] > 0 &&
			(SourceProcs.StunWindow <= 0.0f || Exchange <= SourceProcs.StunWindow) &&
			RandomStream.FRand() < SourceProcs.StunChance)
		{
			const bool bImmune = TargetProcs.bImmuneAbove && TargetProcs.ImmuneHpRatio > 0.0f &&
				Defender.Health[TargetIndex] > Defender.MaxHealth[TargetIndex] * TargetProcs.ImmuneHpRatio;
			if (!bImmune)
			{
				Defender.StunUntil[TargetIndex] = Exchange + FMath::Max(1, FMath::CeilToInt(SourceProcs.StunDuration)) + 1;
				RecordBattleEvent(ETreadM1BattleEventType::EnemyFrozen, Attacker.Player->PlayerId,
					Defender.Player->PlayerId, 0, SourceUnit.UnitInstanceId, TargetUnit.UnitInstanceId);
			}
		}
		// 3_08: silence blocks the target's skill/ammo handling for its window.
		if (SourceProcs.SilenceDuration > 0.0f && Defender.Health[TargetIndex] > 0)
		{
			BattleSilenceUntil.FindOrAdd(TargetUnit.UnitInstanceId) =
				Exchange + FMath::Max(1, FMath::CeilToInt(SourceProcs.SilenceDuration)) + 1;
		}
		// 4_09 / 6_05 / 6_06: a burn that ticks for three exchanges.
		if (SourceProcs.BurnScale > 0.0f && Defender.Health[TargetIndex] > 0)
		{
			Defender.BurnUntil[TargetIndex] = Exchange + 4;
			Defender.BurnDamage[TargetIndex] = FMath::Max(1, FMath::RoundToInt(Base * SourceProcs.BurnScale));
		}
		// 6_04 (阿戈尔): reflect a share of the hit back at the attacker.
		if (TargetProcs.ReflectScale > 0.0f && Attacker.Health[SourceIndex] > 0)
		{
			ApplyBattleDamage(Attacker, SourceIndex, FMath::Max(1, FMath::RoundToInt(Base * TargetProcs.ReflectScale)),
				Defender.Player->PlayerId, TargetUnit.UnitInstanceId);
		}
		// 4_03: stacking attack speed on every attack.
		if (SourceProcs.AttackStack > 0.0f)
		{
			int32& Stacks = BattleAttackSpeedStacks.FindOrAdd(SourceUnit.UnitInstanceId);
			Stacks = FMath::Min(Stacks + FMath::RoundToInt(SourceProcs.AttackStack),
				FMath::Max(1, SourceProcs.AttackStackMax));
		}
		// 4_08: spent-round refund, capped per battle.
		if (SourceProcs.AmmoRefundChance > 0.0f && Attacker.AmmoRefundLeft[SourceIndex] > 0 &&
			RandomStream.FRand() < SourceProcs.AmmoRefundChance && PactData.IsValid())
		{
			--Attacker.AmmoRefundLeft[SourceIndex];
			const int32 Refund = FMath::Max(1, FMath::RoundToInt(SourceProcs.AmmoRefundPercent * FMath::Max(1, PactData->AmmoPerAttack * 6)));
			BattleAmmo.FindOrAdd(SourceUnit.UnitInstanceId) += Refund;
		}
	}
}
