#pragma once

#include "CoreMinimal.h"
#include "TreadM2PactTypes.h"

class FJsonObject;

/** One interpreted op from Traits.json / Pacts.json / StrategyEffects.json. */
struct FTreadM2Effect
{
	FString Op;
	/** Pact tier ops only: the trigger family the op listens to. */
	ETreadM2Trigger Trigger = ETreadM2Trigger::Passive;
	FString PactSelector;
	TArray<FString> Pacts;
	double BaseValue = 0.0;
	double EliteValue = 0.0;
	FString AmountScale = TEXT("Fixed");
	FString Item;
	TArray<FString> ItemChoices;
	FString RareItem;
	FString UnitSelector;
	TArray<FString> Operators;
	FString Stat;
	int32 PerStacks = 0;
	FString TriggerFilter;
	FString Anchor;
	bool bOnce = false;
	// N1 additions (Stronghold-Protocol traits/strategies).
	int32 ScaleDivisor = 0;
	int32 CapBase = 0;
	int32 CapElite = 0;
	int32 TierBase = 0;
	int32 TierElite = 0;
	int32 OnRound = 0;
	int32 Capital = 0;
	double SingleActiveAmount = 0.0;
};

struct FTreadM2Condition
{
	/** Battle source event: Kill, SelfKnockedOut, SkillActivated, AmmoConsumed, EnemyFrozen, BattleStart, FrontTraitStackGain. */
	FString Event;
	/** Which unit must produce Event relative to the trait owner: Self, Front1, FrontColumn. */
	FString Source = TEXT("Self");
	int32 Every = 0;
	bool bFirstOnly = false;
	int32 ChanceBase = 100;
	int32 ChanceElite = 100;
	int32 SameRowAtLeast = 0;
	bool bEliteIgnoresCondition = false;
	int32 PerBattleCap = 0;
	int32 RangeBase = 0;
	int32 RangeElite = 0;
	/** Battle: fire at most this many times per battle (e.g. "前3次击倒"). */
	int32 MaxTimes = 0;
	/** Preparation trait that also works from the bench while any of these pacts is active. */
	TArray<FString> BenchIfAnyActive;
	bool bOddRoundsOnly = false;
};

struct FTreadM2Trait
{
	FString Id;
	FString CardId;
	ETreadM2Trigger Trigger = ETreadM2Trigger::Passive;
	FString TriggerLabel;
	FTreadM2Condition Condition;
	FString Targets = TEXT("Self");
	bool bActivationRequired = true;
	bool bWorksOnBench = false;
	int32 RepeatCount = 1;
	TArray<FTreadM2Effect> Effects;
	FString DisplayText;
	/** Text with the elite (2-star and up) values, "" when the trait has no separate elite text. */
	FString EliteDisplayText;
	FString ValueText;
	FString RuntimeSupport;
	FString SourcePattern;
};

/** M4: the bound operator's combat numbers (Roster112 stats / eliteStats). */
struct FTreadM4OperatorStats
{
	int32 MaxHp = 0;
	int32 Atk = 0;
	int32 Def = 0;
	int32 Res = 0;
	int32 BlockCnt = 1;
	float Bat = 1.0f;
	float Aspd = 100.0f;
};

struct FTreadM2Card
{
	FString CharacterId;
	FString ReferenceOperatorName;
	FString Assignment;
	TArray<FString> CorePacts;
	TArray<FString> AdjunctPacts;
	FString Profession;
	bool bConsumesAmmo = false;
	int32 CombineCopies = 3;
	/** N1: the bound operator's tier (I..VI), shop price, sale value and shared-pool copies. */
	FString OperatorTier;
	int32 Price = 0;
	int32 SellPrice = 1;
	int32 PoolCopies = 0;
	TArray<FTreadM2Trait> Traits;
	/** M4 roster map (CharacterRosterMap.json, Tools/m4/build_roster_map.py); empty when the map is missing. */
	FString ModelName;
	FString ModelSet;
	/** Chest-up screenshot of the 3D model (shop / bench / roster avatar) and the PNG illustration (detail layer only). */
	FString AvatarAsset;
	FString PortraitAsset;
	TArray<FString> VoiceAssets;
	TArray<FString> VoiceLines;
	FString SubProfession;
	FString Position;
	FString AttackKind;
	FString SkillName;
	FTreadM4OperatorStats Stats;
	FTreadM4OperatorStats EliteStats;
};

struct FTreadM2Milestone
{
	int32 Every = 0;
	int32 AtLeast = 0;
	bool bOnce = false;
	FString Op;
	int32 Amount = 0;
	FString Item;
	FString Flag;
};

struct FTreadM2CombatStat
{
	FString Stat;
	double PerStack = 0.0;
};

struct FTreadM2PactDef
{
	FString PactId;
	FString Kind;
	TArray<int32> Thresholds;
	TArray<FString> TierTexts;
	/** Ops per tier (index 0 = first threshold). Only the highest active tier's ops apply. */
	TArray<TArray<FTreadM2Effect>> TierOps;
	bool bCountsBench = false;
	bool bHarmony = false;
	bool bSkillAppliesFreeze = false;
	TArray<FTreadM2CombatStat> CombatPerStack;
	/** Flat bonus while the pact is active (PerStack holds the value). */
	TArray<FTreadM2CombatStat> BaseStats;
	/** 绝技: every elite unit on the board counts as a member. */
	bool bCountsEliteAll = false;
	/** 0 = no cap; 独行 (soloShip) is the only pact with maxCount 1, inactive at 2+ members. */
	int32 MaxCount = 0;

	// 技力 (SP), document/167: skills are paid for with an attack-carried resource. The pact numbers come from
	// bonds.json `bb` (迅捷 swiftShip / 绝技 suntShip / 独行 soloShip).
	int32 SpPerAttack = 0;
	float SpChance = 0.0f;
	float SpCostRatio = 1.0f;
	int32 SpInitial = 0;

	/** 精锐 units get the elite SP value from 迅捷 (power_sp instead of normal_sp). */
	int32 SpElitePerAttack = 0;

	// 拉特兰 ammo (document/168): skills reload, attacks spend, spent rounds add attack.
	int32 AmmoPerSkill = 0;
	float AmmoGrantBonus = 0.0f;
	float AmmoAtkPerRound = 0.0f;
	float AmmoMaxAtkMul = 1.0f;

	/** Every numeric bond param from bonds.json `bb` (document/171), so mechanics read the source numbers. */
	TMap<FString, float> Params;
	FString CombatScope;
	TArray<FTreadM2Milestone> Milestones;
	FString SourceStatus;
};

/** One item proc (ItemCatalog.json "proc"; document/175). Values are already in simulation units. */
struct FTreadM2ItemProc
{
	/** DamageScale, DamageTakenScale, Stun, Lifesteal, Regen, Revive, Undying, SpInitial, SpRegen, AmmoRefund,
	 *  ExtraHit, Reflect, AttackStack, AttackPerSkill, AttackSpeedFlat, Burn, Taunt, StatusImmune,
	 *  HealthConditional, Silence. */
	FString Op;
	float Value = 0.0f;
	/** ExtraHit: the scale used while the partner item is equipped. */
	float ValuePartner = 0.0f;
	float Chance = 1.0f;
	/** Stun/Silence/Undying: seconds. */
	float Duration = 0.0f;
	/** Stun/DamageScale: only active during the first N battle seconds (0 = whole battle). */
	float Window = 0.0f;
	/** DamageScale: lost per battle second after the first one. */
	float Decay = 0.0f;
	float HpRatio = 0.0f;
	float Percent = 0.0f;
	int32 Count = 0;
	int32 Max = 0;
	int32 PerPactMember = 0;
	/** "", Ground, Ranged, FrontEmpty, Stunned, Pact:<name>. */
	FString Condition;
	/** Set bonus: the proc only fires while this base item is equipped too. */
	FString Partner;
};

struct FTreadM2Item
{
	FString ItemId;
	FString DisplayName;
	TArray<FString> ProvidesPacts;
	FString EffectStatus;
	/** M4 ItemCatalog.json / StrategyItems.json: texts, battle-sim stat bonuses, on-equip op and support status. */
	FString EffectText;
	FString EliteEffectText;
	FString Category;
	FString RuntimeSupport;
	FString SupportNote;
	bool bElite = false;
	bool bConsumedOnEquip = false;
	bool bSpell = false;
	/** ItemCatalog.json "tier" (1..6); the reward offer rolls items up to a level-based cap. */
	int32 Tier = 1;
	TMap<FString, float> Combat;
	FString OnEquipOp;
	int32 OnEquipValue = 0;
	int32 OnEquipMax = 0;
	/** ItemCatalog.json "proc": the conditional/per-tick half of the effect (document/175). */
	TArray<FTreadM2ItemProc> Procs;
};

struct FTreadM2StrategyEffect
{
	FString Raw;
	bool bApplied = false;
	FTreadM2Effect Effect;
};

struct FTreadM2StrategyBus
{
	FString StrategyId;
	FString Trigger;
	TArray<FTreadM2StrategyEffect> Effects;
};

/** N1 economy (Content/Data/Generated/Economy.json); bLoaded=false keeps the M1 graybox economy. */
struct FTreadN1Economy
{
	bool bLoaded = false;
	TArray<int32> IncomeByRound;
	bool bLeftoverFundsLost = false;
	bool bInterest = true;
	bool bStreakIncome = true;
	TMap<FString, int32> PriceByTier;
	TMap<FString, int32> SellByTier;
	int32 RefreshPrice = 2;
	int32 StartShopLevel = 1;
	int32 MaxShopLevel = 6;
	TArray<int32> UpgradePrices;
	int32 UpgradeDiscountPerRound = 1;
	TMap<int32, int32> ChessSlotsByLevel;
	int32 DeployCap = 8;

	/** Economy.json "rewardOffer": three free item choices at the start of every preparation (document/176). */
	int32 RewardCount = 3;
	int32 RewardTierOffset = 1;
	int32 RewardMaxTier = 6;
	int32 RewardPrice = 0;
	bool bRewardRefreshable = false;
	bool bRewardFreezable = false;
	bool bRewardExpiresAtRoundEnd = true;

	int32 IncomeForRound(int32 Round) const { return IncomeByRound.Num() == 0 ? 0 : IncomeByRound[FMath::Clamp(Round, 0, IncomeByRound.Num() - 1)]; }
	int32 SlotsForLevel(int32 Level) const { const int32* Value = ChessSlotsByLevel.Find(Level); return Value ? *Value : 5; }
};

/** M4 LeaderRounds.json: a scripted opponent, an R1-R2 garrison or an R12 leader (campaign stages). */
struct FTreadM4ScriptedOpponent
{
	int32 Round = 0;
	FString OpponentId;
	FString Kind;
	FString DisplayName;
	TArray<FString> UnitCharacters;
	TArray<int32> UnitStars;
	/** Garrisons only: the unit added once per point of the stage's garrisonBonus. */
	FString ExtraUnitCharacterId;
	int32 Health = 0;
	FString Behavior;
	float TimeoutSec = 45.0f;
	int32 LossBase = 0;
	int32 LossPerSurvivor = 0;
	int32 WinFunds = 0;
	int32 WinDamageBase = 0;
	int32 WinDamagePerSurvivor = 0;
};

/** M4 Campaign16.json: one campaign stage and its rule modifiers (mapping in Tools/m4/build_campaign_data.py). */
struct FTreadM4CampaignStage
{
	int32 Index = 0;
	FString Country;
	FString Landmark;
	FString Rule;
	FString Effect;
	FString LeaderId;
	int32 AiLevel = 1;
	int32 GarrisonBonus = 0;
	int32 EnemyHpBonus = 0;
	int32 StartGoldBonus = 0;
	int32 IncomeBonus = 0;
	int32 DamageTakenPercent = 100;
	int32 PrepareSecondsDelta = 0;
};

/** Immutable M2 pact/trait data set loaded from Content/Data/Generated. */
class TREAD_API FTreadM2PactData
{
public:
	bool Load(const FString& ContentDir);

	bool bLoaded = false;
	FString Error;
	FString Version;
	int32 EliteStarAtLeast = 2;
	int32 StackCap = 999;
	int32 SkillEveryAttacks = 3;

	/** 技力 recovered by every living unit per battle second (document/168, Pacts.json rules). */
	float SpRegenPerSecond = 0.0f;
	int32 AmmoPerAttack = 1;

	TArray<FTreadM2PactDef> Pacts;
	TMap<FString, int32> PactIndex;
	TMap<FString, FTreadM2Card> Cards;
	TArray<FString> CardOrder;
	TMap<FString, FString> OperatorToCharacter;
	TArray<FTreadM2Item> Items;
	TArray<FTreadM2StrategyBus> Strategies;
	FTreadN1Economy Economy;
	/** M4 roster map: version ("" when absent) and the shared SFX / BGM SoundWave paths by key. */
	FString RosterVersion;
	/** M4 scripted opponents and campaign stages (empty when the files are missing). */
	TArray<FTreadM4ScriptedOpponent> Garrisons;
	TArray<FTreadM4ScriptedOpponent> Leaders;
	FString DefaultLeaderId;
	TArray<FTreadM4CampaignStage> CampaignStages;
	const FTreadM4CampaignStage* FindStage(int32 Index) const { return CampaignStages.FindByPredicate([Index](const FTreadM4CampaignStage& S) { return S.Index == Index; }); }
	const FTreadM4ScriptedOpponent* FindGarrison(int32 Round) const { return Garrisons.FindByPredicate([Round](const FTreadM4ScriptedOpponent& O) { return O.Round == Round; }); }
	const FTreadM4ScriptedOpponent* FindLeader(const FString& Id) const { return Leaders.FindByPredicate([&Id](const FTreadM4ScriptedOpponent& O) { return O.OpponentId == Id; }); }
	TMap<FString, FString> SfxAssets;
	TMap<FString, FString> BgmAssets;

	const FTreadM2PactDef* FindPact(const FString& PactId) const;
	const FTreadM2Card* FindCard(const FString& CharacterId) const;
	const FTreadM2Item* FindItem(const FString& ItemIdOrName) const;
	const FTreadM2StrategyBus* FindStrategy(const FString& StrategyId) const;

	static ETreadM2Trigger ParseTrigger(const FString& Name);
	static FString TriggerName(ETreadM2Trigger Trigger);
	static FTreadM2Effect ParseEffect(const TSharedPtr<FJsonObject>& Object);
};
