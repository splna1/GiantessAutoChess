#include "TreadM2PactData.h"

#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "UObject/Class.h"

namespace
{
	TSharedPtr<FJsonObject> LoadJson(const FString& Path, FString& OutError)
	{
		FString Text;
		TSharedPtr<FJsonObject> Root;
		if (!FFileHelper::LoadFileToString(Text, *Path))
		{
			OutError = FString::Printf(TEXT("missing %s"), *Path);
			return nullptr;
		}
		if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
		{
			OutError = FString::Printf(TEXT("invalid json %s"), *Path);
			return nullptr;
		}
		return Root;
	}

	FString Str(const TSharedPtr<FJsonObject>& Object, const TCHAR* Key, const FString& Default = FString())
	{
		FString Value;
		return Object.IsValid() && Object->TryGetStringField(Key, Value) ? Value : Default;
	}

	double Num(const TSharedPtr<FJsonObject>& Object, const TCHAR* Key, double Default = 0.0)
	{
		double Value = Default;
		return Object.IsValid() && Object->TryGetNumberField(Key, Value) ? Value : Default;
	}

	bool Bool(const TSharedPtr<FJsonObject>& Object, const TCHAR* Key, bool Default = false)
	{
		bool Value = Default;
		return Object.IsValid() && Object->TryGetBoolField(Key, Value) ? Value : Default;
	}

	TArray<FString> Strings(const TSharedPtr<FJsonObject>& Object, const TCHAR* Key)
	{
		TArray<FString> Result;
		const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
		if (Object.IsValid() && Object->TryGetArrayField(Key, Values) && Values)
		{
			for (const TSharedPtr<FJsonValue>& Value : *Values)
			{
				FString Item;
				if (Value.IsValid() && Value->TryGetString(Item)) Result.Add(Item);
			}
		}
		return Result;
	}

	const TArray<TSharedPtr<FJsonValue>>* Array(const TSharedPtr<FJsonObject>& Object, const TCHAR* Key)
	{
		const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
		return Object.IsValid() && Object->TryGetArrayField(Key, Values) ? Values : nullptr;
	}
}

ETreadM2Trigger FTreadM2PactData::ParseTrigger(const FString& Name)
{
	const UEnum* Enum = StaticEnum<ETreadM2Trigger>();
	const int64 Value = Enum ? Enum->GetValueByNameString(Name) : INDEX_NONE;
	return Value == INDEX_NONE ? ETreadM2Trigger::Passive : static_cast<ETreadM2Trigger>(Value);
}

FString FTreadM2PactData::TriggerName(ETreadM2Trigger Trigger)
{
	const UEnum* Enum = StaticEnum<ETreadM2Trigger>();
	return Enum ? Enum->GetNameStringByValue(static_cast<int64>(Trigger)) : TEXT("Unknown");
}

FTreadM2Effect FTreadM2PactData::ParseEffect(const TSharedPtr<FJsonObject>& Object)
{
	FTreadM2Effect Effect;
	Effect.Op = Str(Object, TEXT("op"));
	Effect.Trigger = ParseTrigger(Str(Object, TEXT("trigger"), TEXT("Passive")));
	Effect.PactSelector = Str(Object, TEXT("pactSelector"));
	Effect.Pacts = Strings(Object, TEXT("pacts"));
	Effect.BaseValue = Num(Object, TEXT("baseValue"));
	Effect.EliteValue = Num(Object, TEXT("eliteValue"), Effect.BaseValue);
	Effect.AmountScale = Str(Object, TEXT("amountScale"), TEXT("Fixed"));
	Effect.Item = Str(Object, TEXT("item"));
	Effect.ItemChoices = Strings(Object, TEXT("itemChoices"));
	Effect.RareItem = Str(Object, TEXT("rareItem"));
	Effect.UnitSelector = Str(Object, TEXT("unitSelector"));
	Effect.Operators = Strings(Object, TEXT("operators"));
	Effect.Stat = Str(Object, TEXT("stat"));
	Effect.PerStacks = static_cast<int32>(Num(Object, TEXT("perStacks")));
	Effect.TriggerFilter = Str(Object, TEXT("triggerFilter"));
	Effect.Anchor = Str(Object, TEXT("anchor"));
	Effect.bOnce = Bool(Object, TEXT("once"));
	Effect.ScaleDivisor = static_cast<int32>(Num(Object, TEXT("scaleDivisor")));
	Effect.CapBase = static_cast<int32>(Num(Object, TEXT("capBase")));
	Effect.CapElite = static_cast<int32>(Num(Object, TEXT("capElite"), Effect.CapBase));
	Effect.TierBase = static_cast<int32>(Num(Object, TEXT("tierBase")));
	Effect.TierElite = static_cast<int32>(Num(Object, TEXT("tierElite"), Effect.TierBase));
	Effect.OnRound = static_cast<int32>(Num(Object, TEXT("onRound")));
	Effect.Capital = static_cast<int32>(Num(Object, TEXT("capital")));
	Effect.SingleActiveAmount = Num(Object, TEXT("singleActiveAmount"));
	return Effect;
}

bool FTreadM2PactData::Load(const FString& ContentDir)
{
	*this = FTreadM2PactData();
	const FString Dir = FPaths::Combine(ContentDir, TEXT("Data/Generated"));
	const TSharedPtr<FJsonObject> PactRoot = LoadJson(FPaths::Combine(Dir, TEXT("Pacts.json")), Error);
	const TSharedPtr<FJsonObject> TraitRoot = PactRoot.IsValid() ? LoadJson(FPaths::Combine(Dir, TEXT("Traits.json")), Error) : nullptr;
	const TSharedPtr<FJsonObject> ItemRoot = TraitRoot.IsValid() ? LoadJson(FPaths::Combine(Dir, TEXT("M2_ItemSeeds.json")), Error) : nullptr;
	const TSharedPtr<FJsonObject> StrategyRoot = ItemRoot.IsValid() ? LoadJson(FPaths::Combine(Dir, TEXT("StrategyEffects.json")), Error) : nullptr;
	if (!StrategyRoot.IsValid())
	{
		return false;
	}
	Version = Str(PactRoot, TEXT("schemaVersion")) + TEXT("+") + Str(TraitRoot, TEXT("schemaVersion"));

	const TSharedPtr<FJsonObject>* Rules = nullptr;
	if (PactRoot->TryGetObjectField(TEXT("rules"), Rules) && Rules)
	{
		EliteStarAtLeast = static_cast<int32>(Num(*Rules, TEXT("eliteStarAtLeast"), 2));
		StackCap = static_cast<int32>(Num(*Rules, TEXT("stackCap"), 999));
		const TSharedPtr<FJsonObject>* Battle = nullptr;
		if ((*Rules)->TryGetObjectField(TEXT("battle"), Battle) && Battle)
		{
			SkillEveryAttacks = FMath::Max(1, static_cast<int32>(Num(*Battle, TEXT("skillEveryAttacks"), 3)));
			AmmoPerAttack = FMath::Max(0, static_cast<int32>(Num(*Battle, TEXT("ammoPerAttack"), 1)));
		}
		{
			// Battle-wide SP trickle: every living unit recovers this much 技力 per battle second (document/168).
			SpRegenPerSecond = FMath::Max(0.0f, static_cast<float>(Num(*Rules, TEXT("spRegenPerSecond"), 0.0)));
		}
	}

	if (const TArray<TSharedPtr<FJsonValue>>* Values = Array(PactRoot, TEXT("pacts")))
	{
		for (const TSharedPtr<FJsonValue>& Value : *Values)
		{
			const TSharedPtr<FJsonObject> Object = Value->AsObject();
			FTreadM2PactDef Def;
			Def.PactId = Str(Object, TEXT("pactId"));
			Def.Kind = Str(Object, TEXT("kind"));
			Def.bCountsBench = Bool(Object, TEXT("countsBench"));
			Def.bHarmony = Bool(Object, TEXT("isHarmony"));
			Def.bSkillAppliesFreeze = Bool(Object, TEXT("skillAppliesFreeze"));
			Def.CombatScope = Str(Object, TEXT("combatScope"));
			Def.SourceStatus = Str(Object, TEXT("sourceStatus"));
			Def.bCountsEliteAll = Bool(Object, TEXT("countsEliteAll"));
	Def.MaxCount = static_cast<int32>(Num(Object, TEXT("maxCount"), 0));
	const TSharedPtr<FJsonObject>* ParamsObject = nullptr;
	if (Object->TryGetObjectField(TEXT("params"), ParamsObject) && ParamsObject && ParamsObject->IsValid())
	{
		for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : (*ParamsObject)->Values)
		{
			if (Pair.Value.IsValid() && Pair.Value->Type == EJson::Number)
			{
				Def.Params.Add(Pair.Key, static_cast<float>(Pair.Value->AsNumber()));
			}
		}
	}
	const TSharedPtr<FJsonObject>* AmmoObject = nullptr;
	if (Object->TryGetObjectField(TEXT("ammo"), AmmoObject) && AmmoObject && AmmoObject->IsValid())
	{
		Def.AmmoPerSkill = static_cast<int32>(Num(*AmmoObject, TEXT("perSkill"), 0));
		Def.AmmoGrantBonus = static_cast<float>(Num(*AmmoObject, TEXT("grantBonus"), 0.0));
		Def.AmmoAtkPerRound = static_cast<float>(Num(*AmmoObject, TEXT("atkPerRound"), 0.0));
		Def.AmmoMaxAtkMul = static_cast<float>(Num(*AmmoObject, TEXT("maxAtkMul"), 1.0));
	}
	const TSharedPtr<FJsonObject>* SpObject = nullptr;
	if (Object->TryGetObjectField(TEXT("sp"), SpObject) && SpObject && SpObject->IsValid())
	{
		Def.SpPerAttack = static_cast<int32>(Num(*SpObject, TEXT("perAttack"), 0));
		Def.SpChance = static_cast<float>(Num(*SpObject, TEXT("chance"), 0.0));
		Def.SpCostRatio = static_cast<float>(Num(*SpObject, TEXT("costRatio"), 1.0));
		Def.SpInitial = static_cast<int32>(Num(*SpObject, TEXT("initial"), 0));
		Def.SpElitePerAttack = static_cast<int32>(Num(*SpObject, TEXT("elitePerAttack"), 0));
	}
			if (const TArray<TSharedPtr<FJsonValue>>* Bases = Array(Object, TEXT("baseStats")))
			{
				for (const TSharedPtr<FJsonValue>& Base : *Bases)
				{
					FTreadM2CombatStat& Combat = Def.BaseStats.AddDefaulted_GetRef();
					Combat.Stat = Str(Base->AsObject(), TEXT("stat"));
					Combat.PerStack = Num(Base->AsObject(), TEXT("value"));
				}
			}
			if (const TArray<TSharedPtr<FJsonValue>>* Tiers = Array(Object, TEXT("tiers")))
			{
				for (const TSharedPtr<FJsonValue>& Tier : *Tiers)
				{
					const TSharedPtr<FJsonObject> TierObject = Tier->AsObject();
					Def.Thresholds.Add(static_cast<int32>(Num(TierObject, TEXT("count"))));
					Def.TierTexts.Add(Str(TierObject, TEXT("text")));
					TArray<FTreadM2Effect>& Ops = Def.TierOps.AddDefaulted_GetRef();
					if (const TArray<TSharedPtr<FJsonValue>>* OpValues = Array(TierObject, TEXT("ops")))
					{
						for (const TSharedPtr<FJsonValue>& Op : *OpValues) Ops.Add(ParseEffect(Op->AsObject()));
					}
				}
			}
			if (const TArray<TSharedPtr<FJsonValue>>* Stats = Array(Object, TEXT("combatPerStack")))
			{
				for (const TSharedPtr<FJsonValue>& Stat : *Stats)
				{
					FTreadM2CombatStat& Combat = Def.CombatPerStack.AddDefaulted_GetRef();
					Combat.Stat = Str(Stat->AsObject(), TEXT("stat"));
					Combat.PerStack = Num(Stat->AsObject(), TEXT("perStack"));
				}
			}
			if (const TArray<TSharedPtr<FJsonValue>>* Milestones = Array(Object, TEXT("stackMilestones")))
			{
				for (const TSharedPtr<FJsonValue>& MilestoneValue : *Milestones)
				{
					const TSharedPtr<FJsonObject> MilestoneObject = MilestoneValue->AsObject();
					FTreadM2Milestone& Milestone = Def.Milestones.AddDefaulted_GetRef();
					Milestone.Every = static_cast<int32>(Num(MilestoneObject, TEXT("every")));
					Milestone.AtLeast = static_cast<int32>(Num(MilestoneObject, TEXT("atLeast")));
					Milestone.bOnce = Bool(MilestoneObject, TEXT("once"));
					Milestone.Op = Str(MilestoneObject, TEXT("op"));
					Milestone.Amount = static_cast<int32>(Num(MilestoneObject, TEXT("amount")));
					Milestone.Item = Str(MilestoneObject, TEXT("item"));
					Milestone.Flag = Str(MilestoneObject, TEXT("flag"));
				}
			}
			PactIndex.Add(Def.PactId, Pacts.Num());
			Pacts.Add(MoveTemp(Def));
		}
	}

	if (const TArray<TSharedPtr<FJsonValue>>* Values = Array(TraitRoot, TEXT("cards")))
	{
		for (const TSharedPtr<FJsonValue>& Value : *Values)
		{
			const TSharedPtr<FJsonObject> Object = Value->AsObject();
			FTreadM2Card Card;
			Card.CharacterId = Str(Object, TEXT("characterId"));
			Card.ReferenceOperatorName = Str(Object, TEXT("referenceOperatorName"));
			Card.Assignment = Str(Object, TEXT("assignment"));
			Card.CorePacts = Strings(Object, TEXT("corePacts"));
			Card.AdjunctPacts = Strings(Object, TEXT("adjunctPacts"));
			Card.Profession = Str(Object, TEXT("profession"));
			Card.bConsumesAmmo = Bool(Object, TEXT("consumesAmmo"));
			Card.CombineCopies = FMath::Max(2, static_cast<int32>(Num(Object, TEXT("combineCopies"), 3)));
			Card.OperatorTier = Str(Object, TEXT("operatorTier"));
			Card.Price = static_cast<int32>(Num(Object, TEXT("price")));
			Card.SellPrice = static_cast<int32>(Num(Object, TEXT("sellPrice"), 1));
			Card.PoolCopies = static_cast<int32>(Num(Object, TEXT("poolCopies")));
			if (const TArray<TSharedPtr<FJsonValue>>* TraitValues = Array(Object, TEXT("traits")))
			{
				for (const TSharedPtr<FJsonValue>& TraitValue : *TraitValues)
				{
					const TSharedPtr<FJsonObject> TraitObject = TraitValue->AsObject();
					FTreadM2Trait Trait;
					Trait.Id = Str(TraitObject, TEXT("id"));
					Trait.CardId = Card.CharacterId;
					Trait.Trigger = ParseTrigger(Str(TraitObject, TEXT("trigger"), TEXT("Passive")));
					Trait.TriggerLabel = Str(TraitObject, TEXT("triggerLabel"));
					Trait.Targets = Str(TraitObject, TEXT("targets"), TEXT("Self"));
					Trait.bActivationRequired = Bool(TraitObject, TEXT("activationRequired"), true);
					Trait.bWorksOnBench = Bool(TraitObject, TEXT("worksOnBench"));
					Trait.RepeatCount = FMath::Max(1, static_cast<int32>(Num(TraitObject, TEXT("repeatCount"), 1)));
					Trait.DisplayText = Str(TraitObject, TEXT("displayText"));
					Trait.EliteDisplayText = Str(TraitObject, TEXT("eliteDisplayText"));
					Trait.ValueText = Str(TraitObject, TEXT("valueText"));
					Trait.RuntimeSupport = Str(TraitObject, TEXT("runtimeSupport"));
					Trait.SourcePattern = Str(TraitObject, TEXT("sourcePattern"));
					const TSharedPtr<FJsonObject>* ConditionObject = nullptr;
					if (TraitObject->TryGetObjectField(TEXT("triggerCondition"), ConditionObject) && ConditionObject)
					{
						FTreadM2Condition& Condition = Trait.Condition;
						Condition.Event = Str(*ConditionObject, TEXT("event"));
						Condition.Source = Str(*ConditionObject, TEXT("source"), TEXT("Self"));
						Condition.Every = static_cast<int32>(Num(*ConditionObject, TEXT("every")));
						Condition.bFirstOnly = Bool(*ConditionObject, TEXT("firstOnly"));
						Condition.ChanceBase = static_cast<int32>(Num(*ConditionObject, TEXT("chanceBase"), 100));
						Condition.ChanceElite = static_cast<int32>(Num(*ConditionObject, TEXT("chanceElite"), Condition.ChanceBase));
						Condition.SameRowAtLeast = static_cast<int32>(Num(*ConditionObject, TEXT("sameRowAtLeast")));
						Condition.bEliteIgnoresCondition = Bool(*ConditionObject, TEXT("eliteIgnoresCondition"));
						Condition.PerBattleCap = static_cast<int32>(Num(*ConditionObject, TEXT("perBattleCap")));
						Condition.RangeBase = static_cast<int32>(Num(*ConditionObject, TEXT("rangeBase")));
						Condition.RangeElite = static_cast<int32>(Num(*ConditionObject, TEXT("rangeElite"), Condition.RangeBase));
						Condition.MaxTimes = static_cast<int32>(Num(*ConditionObject, TEXT("maxTimes")));
						Condition.BenchIfAnyActive = Strings(*ConditionObject, TEXT("benchIfAnyActive"));
						Condition.bOddRoundsOnly = Bool(*ConditionObject, TEXT("oddRoundsOnly"));
					}
					if (const TArray<TSharedPtr<FJsonValue>>* Effects = Array(TraitObject, TEXT("effects")))
					{
						for (const TSharedPtr<FJsonValue>& Effect : *Effects) Trait.Effects.Add(ParseEffect(Effect->AsObject()));
					}
					Card.Traits.Add(MoveTemp(Trait));
				}
			}
			if (!Card.ReferenceOperatorName.IsEmpty()) OperatorToCharacter.Add(Card.ReferenceOperatorName, Card.CharacterId);
			CardOrder.Add(Card.CharacterId);
			Cards.Add(Card.CharacterId, MoveTemp(Card));
		}
	}

	if (const TArray<TSharedPtr<FJsonValue>>* Values = Array(ItemRoot, TEXT("items")))
	{
		for (const TSharedPtr<FJsonValue>& Value : *Values)
		{
			const TSharedPtr<FJsonObject> Object = Value->AsObject();
			FTreadM2Item& Item = Items.AddDefaulted_GetRef();
			Item.ItemId = Str(Object, TEXT("itemId"));
			Item.DisplayName = Str(Object, TEXT("displayName"));
			Item.ProvidesPacts = Strings(Object, TEXT("providesPacts"));
			Item.EffectStatus = Str(Object, TEXT("effectStatus"));
		}
	}

	// M4 item catalog: optional like the roster map.  Each catalog row enriches its seed row (same base id) and adds
	// the elite (Ⅱ) version as its own item, since a merged pair is a different item id.
	FString CatalogError;
	auto ReadCombat = [](const TSharedPtr<FJsonObject>& Row, const TCHAR* Key, TMap<FString, float>& Out)
	{
		const TSharedPtr<FJsonObject>* Map = nullptr;
		if (!Row->TryGetObjectField(Key, Map) || !Map) return;
		for (const auto& Pair : (*Map)->Values)
		{
			double Value = 0.0;
			if (Pair.Value.IsValid() && Pair.Value->TryGetNumber(Value)) Out.Add(FString(Pair.Key), static_cast<float>(Value));
		}
	};
	if (const TSharedPtr<FJsonObject> CatalogRoot = LoadJson(FPaths::Combine(Dir, TEXT("ItemCatalog.json")), CatalogError))
	{
		if (const TArray<TSharedPtr<FJsonValue>>* Values = Array(CatalogRoot, TEXT("items")))
		{
			for (const TSharedPtr<FJsonValue>& Value : *Values)
			{
				const TSharedPtr<FJsonObject> Row = Value->AsObject();
				if (!Row.IsValid()) continue;
				for (int32 Elite = 0; Elite < 2; ++Elite)
				{
					const FString Id = Str(Row, Elite ? TEXT("eliteItemId") : TEXT("itemId"));
					FTreadM2Item* Item = Items.FindByPredicate([&Id](const FTreadM2Item& Existing) { return Existing.ItemId == Id; });
					if (!Item)
					{
						Item = &Items.AddDefaulted_GetRef();
						Item->ItemId = Id;
						Item->DisplayName = Str(Row, TEXT("displayName")) + (Elite ? TEXT("·Ⅱ") : TEXT(""));
						Item->ProvidesPacts = Strings(Row, TEXT("providesPacts"));
					}
					Item->bElite = Elite == 1;
					Item->EffectText = Str(Row, Elite ? TEXT("eliteEffectText") : TEXT("effectText"));
					Item->EliteEffectText = Str(Row, TEXT("eliteEffectText"));
					Item->Category = Str(Row, TEXT("category"));
					Item->Tier = static_cast<int32>(Num(Row, TEXT("tier"), 1));
					Item->RuntimeSupport = Str(Row, TEXT("runtimeSupport"));
					Item->SupportNote = Str(Row, TEXT("supportNote"));
					Item->bConsumedOnEquip = Bool(Row, TEXT("consumedOnEquip"));
					ReadCombat(Row, Elite ? TEXT("eliteCombat") : TEXT("combat"), Item->Combat);
					const TSharedPtr<FJsonObject>* OnEquip = nullptr;
					if (Row->TryGetObjectField(TEXT("onEquip"), OnEquip) && OnEquip)
					{
						Item->OnEquipOp = Str(*OnEquip, TEXT("op"));
						Item->OnEquipValue = static_cast<int32>(Num(*OnEquip, Elite ? TEXT("eliteValue") : TEXT("baseValue"), 1));
						Item->OnEquipMax = static_cast<int32>(Num(*OnEquip, Elite ? TEXT("eliteMax") : TEXT("baseMax"), Item->OnEquipValue));
					}
					// document/175: conditional / per-tick item effects, expressed as procs the battle simulation runs.
					const TArray<TSharedPtr<FJsonValue>>* ProcValues = nullptr;
					if (Row->TryGetArrayField(TEXT("proc"), ProcValues) && ProcValues)
					{
						for (const TSharedPtr<FJsonValue>& ProcValue : *ProcValues)
						{
							const TSharedPtr<FJsonObject> Proc = ProcValue->AsObject();
							if (!Proc.IsValid()) continue;
							FTreadM2ItemProc& Out = Item->Procs.AddDefaulted_GetRef();
							Out.Op = Str(Proc, TEXT("op"));
							Out.Value = static_cast<float>(Num(Proc, TEXT("value"), 0.0));
							Out.ValuePartner = static_cast<float>(Num(Proc, TEXT("valuePartner"), 0.0));
							Out.Chance = static_cast<float>(Num(Proc, TEXT("chance"), 1.0));
							Out.Duration = static_cast<float>(Num(Proc, TEXT("duration"), 0.0));
							Out.Window = static_cast<float>(Num(Proc, TEXT("window"), 0.0));
							Out.Decay = static_cast<float>(Num(Proc, TEXT("decay"), 0.0));
							Out.HpRatio = static_cast<float>(Num(Proc, TEXT("hpRatio"), 0.0));
							Out.Percent = static_cast<float>(Num(Proc, TEXT("percent"), 0.0));
							Out.Count = static_cast<int32>(Num(Proc, TEXT("count"), 0.0));
							Out.Max = static_cast<int32>(Num(Proc, TEXT("max"), 0.0));
							Out.PerPactMember = static_cast<int32>(Num(Proc, TEXT("perPactMember"), 0.0));
							Out.Condition = Str(Proc, TEXT("condition"));
							Out.Partner = Str(Proc, TEXT("partner"));
						}
					}
				}
			}
		}
		Version += TEXT("+items");
	}
	if (const TSharedPtr<FJsonObject> SpellRoot = LoadJson(FPaths::Combine(Dir, TEXT("StrategyItems.json")), CatalogError))
	{
		if (const TArray<TSharedPtr<FJsonValue>>* Values = Array(SpellRoot, TEXT("items")))
		{
			for (const TSharedPtr<FJsonValue>& Value : *Values)
			{
				const TSharedPtr<FJsonObject> Row = Value->AsObject();
				if (!Row.IsValid()) continue;
				FTreadM2Item& Item = Items.AddDefaulted_GetRef();
				Item.ItemId = Str(Row, TEXT("itemId"));
				Item.DisplayName = Str(Row, TEXT("displayName"));
				Item.EffectText = Str(Row, TEXT("effectText"));
				Item.Category = TEXT("MAGIC");
				Item.RuntimeSupport = Str(Row, TEXT("runtimeSupport"));
				Item.SupportNote = Str(Row, TEXT("supportNote"));
				Item.bSpell = true;
			}
		}
	}

	if (const TArray<TSharedPtr<FJsonValue>>* Values = Array(StrategyRoot, TEXT("strategies")))
	{
		for (const TSharedPtr<FJsonValue>& Value : *Values)
		{
			const TSharedPtr<FJsonObject> Object = Value->AsObject();
			FTreadM2StrategyBus& Bus = Strategies.AddDefaulted_GetRef();
			Bus.StrategyId = Str(Object, TEXT("strategyId"));
			Bus.Trigger = Str(Object, TEXT("trigger"));
			if (const TArray<TSharedPtr<FJsonValue>>* Effects = Array(Object, TEXT("effects")))
			{
				for (const TSharedPtr<FJsonValue>& EffectValue : *Effects)
				{
					const TSharedPtr<FJsonObject> EffectObject = EffectValue->AsObject();
					FTreadM2StrategyEffect& Effect = Bus.Effects.AddDefaulted_GetRef();
					Effect.Raw = Str(EffectObject, TEXT("raw"));
					const TSharedPtr<FJsonObject>* OpObject = nullptr;
					Effect.bApplied = EffectObject->TryGetObjectField(TEXT("op"), OpObject) && OpObject;
					if (Effect.bApplied) Effect.Effect = ParseEffect(*OpObject);
				}
			}
		}
	}

	// N1 economy is optional: without Economy.json the M1 graybox economy stays in force.
	FString EconomyError;
	const TSharedPtr<FJsonObject> EconomyRoot = LoadJson(FPaths::Combine(Dir, TEXT("Economy.json")), EconomyError);
	if (EconomyRoot.IsValid())
	{
		FTreadN1Economy& E = Economy;
		E.bLoaded = true;
		if (const TArray<TSharedPtr<FJsonValue>>* Income = Array(EconomyRoot, TEXT("incomeByRound")))
		{
			for (const TSharedPtr<FJsonValue>& Value : *Income) E.IncomeByRound.Add(static_cast<int32>(Value->AsNumber()));
		}
		E.bLeftoverFundsLost = Bool(EconomyRoot, TEXT("leftoverFundsLost"));
		E.bInterest = Bool(EconomyRoot, TEXT("interest"));
		E.bStreakIncome = Bool(EconomyRoot, TEXT("streakIncome"));
		E.RefreshPrice = static_cast<int32>(Num(EconomyRoot, TEXT("refreshPrice"), 1));
		E.DeployCap = static_cast<int32>(Num(EconomyRoot, TEXT("deployCap"), 8));
		const TSharedPtr<FJsonObject>* Map = nullptr;
		for (const TPair<const TCHAR*, TMap<FString, int32>*> Pair : {TPair<const TCHAR*, TMap<FString, int32>*>(TEXT("priceByTier"), &E.PriceByTier),
			TPair<const TCHAR*, TMap<FString, int32>*>(TEXT("sellByTier"), &E.SellByTier)})
		{
			if (EconomyRoot->TryGetObjectField(Pair.Key, Map) && Map)
			{
				for (const TPair<FString, TSharedPtr<FJsonValue>>& Entry : (*Map)->Values) Pair.Value->Add(Entry.Key, static_cast<int32>(Entry.Value->AsNumber()));
			}
		}
		const TSharedPtr<FJsonObject>* Shop = nullptr;
		if (EconomyRoot->TryGetObjectField(TEXT("shopLevel"), Shop) && Shop)
		{
			E.StartShopLevel = static_cast<int32>(Num(*Shop, TEXT("start"), 1));
			E.MaxShopLevel = static_cast<int32>(Num(*Shop, TEXT("max"), 6));
			E.UpgradeDiscountPerRound = static_cast<int32>(Num(*Shop, TEXT("upgradeDiscountPerRound"), 1));
			if (const TArray<TSharedPtr<FJsonValue>>* Prices = Array(*Shop, TEXT("upgradePrices")))
			{
				for (const TSharedPtr<FJsonValue>& Value : *Prices) E.UpgradePrices.Add(static_cast<int32>(Value->AsNumber()));
			}
			const TSharedPtr<FJsonObject>* Slots = nullptr;
			if ((*Shop)->TryGetObjectField(TEXT("chessSlotsByLevel"), Slots) && Slots)
			{
				for (const TPair<FString, TSharedPtr<FJsonValue>>& Entry : (*Slots)->Values)
				{
					E.ChessSlotsByLevel.Add(FCString::Atoi(*Entry.Key), static_cast<int32>(Entry.Value->AsNumber()));
				}
			}
		}
		const TSharedPtr<FJsonObject>* Reward = nullptr;
		if (EconomyRoot->TryGetObjectField(TEXT("rewardOffer"), Reward) && Reward)
		{
			E.RewardCount = static_cast<int32>(Num(*Reward, TEXT("count"), 3));
			E.RewardTierOffset = static_cast<int32>(Num(*Reward, TEXT("tierOffset"), 1));
			E.RewardMaxTier = static_cast<int32>(Num(*Reward, TEXT("maxTier"), 6));
			E.RewardPrice = static_cast<int32>(Num(*Reward, TEXT("price"), 0));
			E.bRewardRefreshable = Bool(*Reward, TEXT("refreshable"));
			E.bRewardFreezable = Bool(*Reward, TEXT("freezable"));
			E.bRewardExpiresAtRoundEnd = Bool(*Reward, TEXT("expiresAtRoundEnd"));
		}
		Version += TEXT("+economy");
	}

	// M4 roster map: optional, so an older data set without it still loads; the UI then falls back to tier colours.
	FString RosterError;
	if (const TSharedPtr<FJsonObject> RosterRoot = LoadJson(FPaths::Combine(Dir, TEXT("CharacterRosterMap.json")), RosterError))
	{
		RosterVersion = Str(RosterRoot, TEXT("schemaVersion"));
		auto ReadAssetMap = [&RosterRoot](const TCHAR* Key, TMap<FString, FString>& Out)
		{
			const TSharedPtr<FJsonObject>* Map = nullptr;
			if (RosterRoot->TryGetObjectField(Key, Map) && Map)
			{
				for (const auto& Pair : (*Map)->Values)
				{
					FString Path;
					if (Pair.Value.IsValid() && Pair.Value->TryGetString(Path)) Out.Add(FString(Pair.Key), Path);
				}
			}
		};
		ReadAssetMap(TEXT("sfx"), SfxAssets);
		ReadAssetMap(TEXT("bgm"), BgmAssets);
		auto ReadStats = [](const TSharedPtr<FJsonObject>& Row, const TCHAR* Key, FTreadM4OperatorStats& Out)
		{
			const TSharedPtr<FJsonObject>* Stats = nullptr;
			if (!Row->TryGetObjectField(Key, Stats) || !Stats) return;
			Out.MaxHp = static_cast<int32>(Num(*Stats, TEXT("maxHp")));
			Out.Atk = static_cast<int32>(Num(*Stats, TEXT("atk")));
			Out.Def = static_cast<int32>(Num(*Stats, TEXT("def")));
			Out.Res = static_cast<int32>(Num(*Stats, TEXT("res")));
			Out.BlockCnt = static_cast<int32>(Num(*Stats, TEXT("blockCnt"), 1));
			Out.Bat = static_cast<float>(Num(*Stats, TEXT("bat"), 1.0));
			Out.Aspd = static_cast<float>(Num(*Stats, TEXT("aspd"), 100.0));
		};
		const TArray<TSharedPtr<FJsonValue>>* Rows = nullptr;
		if (RosterRoot->TryGetArrayField(TEXT("characters"), Rows) && Rows)
		{
			for (const TSharedPtr<FJsonValue>& Value : *Rows)
			{
				const TSharedPtr<FJsonObject> Row = Value.IsValid() ? Value->AsObject() : nullptr;
				FTreadM2Card* Card = Row.IsValid() ? Cards.Find(Str(Row, TEXT("characterId"))) : nullptr;
				if (!Card) continue;
				Card->ModelName = Str(Row, TEXT("ueModelName"));
				Card->ModelSet = Str(Row, TEXT("modelSet"));
				Card->AvatarAsset = Str(Row, TEXT("avatarAsset"));
				Card->PortraitAsset = Str(Row, TEXT("portraitAsset"));
				Card->VoiceAssets = Strings(Row, TEXT("voiceAssets"));
				Card->VoiceLines = Strings(Row, TEXT("voiceLines"));
				Card->SubProfession = Str(Row, TEXT("subProfession"));
				Card->Position = Str(Row, TEXT("position"));
				Card->AttackKind = Str(Row, TEXT("attackKind"));
				Card->SkillName = Str(Row, TEXT("skillName"));
				ReadStats(Row, TEXT("stats"), Card->Stats);
				ReadStats(Row, TEXT("eliteStats"), Card->EliteStats);
			}
		}
		Version += TEXT("+roster");
	}

	// M4 scripted opponents (LeaderRounds.json) and the campaign (Campaign16.json); both optional.
	FString CampaignError;
	if (const TSharedPtr<FJsonObject> LeaderRoot = LoadJson(FPaths::Combine(Dir, TEXT("LeaderRounds.json")), CampaignError))
	{
		auto ReadOpponents = [](const TSharedPtr<FJsonObject>& Root, const TCHAR* Key, TArray<FTreadM4ScriptedOpponent>& Out)
		{
			const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
			if (!Root->TryGetArrayField(Key, Values) || !Values) return;
			for (const TSharedPtr<FJsonValue>& Value : *Values)
			{
				const TSharedPtr<FJsonObject> Row = Value.IsValid() ? Value->AsObject() : nullptr;
				if (!Row.IsValid()) continue;
				FTreadM4ScriptedOpponent& Opponent = Out.AddDefaulted_GetRef();
				Opponent.Round = static_cast<int32>(Num(Row, TEXT("round")));
				Opponent.OpponentId = Str(Row, TEXT("opponentId"));
				Opponent.Kind = Str(Row, TEXT("kind"));
				Opponent.DisplayName = Str(Row, TEXT("displayName"));
				Opponent.ExtraUnitCharacterId = Str(Row, TEXT("extraUnitCharacterId"));
				Opponent.Health = static_cast<int32>(Num(Row, TEXT("health")));
				Opponent.Behavior = Str(Row, TEXT("behavior"));
				Opponent.TimeoutSec = static_cast<float>(Num(Row, TEXT("timeoutSec"), 45.0));
				const TArray<TSharedPtr<FJsonValue>>* Lineup = nullptr;
				if (Row->TryGetArrayField(TEXT("lineup"), Lineup) && Lineup)
				{
					for (const TSharedPtr<FJsonValue>& Unit : *Lineup)
					{
						const TSharedPtr<FJsonObject> UnitRow = Unit.IsValid() ? Unit->AsObject() : nullptr;
						if (!UnitRow.IsValid()) continue;
						Opponent.UnitCharacters.Add(Str(UnitRow, TEXT("characterId")));
						Opponent.UnitStars.Add(FMath::Max(1, static_cast<int32>(Num(UnitRow, TEXT("star"), 1))));
					}
				}
				const TSharedPtr<FJsonObject>* Settlement = nullptr;
				if (Row->TryGetObjectField(TEXT("settlement"), Settlement) && Settlement)
				{
					Opponent.LossBase = static_cast<int32>(Num(*Settlement, TEXT("lossBase")));
					Opponent.LossPerSurvivor = static_cast<int32>(Num(*Settlement, TEXT("lossPerSurvivor")));
					Opponent.WinFunds = static_cast<int32>(Num(*Settlement, TEXT("winFunds")));
					Opponent.WinDamageBase = static_cast<int32>(Num(*Settlement, TEXT("winDamageBase")));
					Opponent.WinDamagePerSurvivor = static_cast<int32>(Num(*Settlement, TEXT("winDamagePerSurvivor")));
				}
			}
		};
		ReadOpponents(LeaderRoot, TEXT("garrisons"), Garrisons);
		ReadOpponents(LeaderRoot, TEXT("leaders"), Leaders);
		DefaultLeaderId = Str(LeaderRoot, TEXT("defaultLeaderId"));
		Version += TEXT("+leaders");
	}
	if (const TSharedPtr<FJsonObject> CampaignRoot = LoadJson(FPaths::Combine(Dir, TEXT("Campaign16.json")), CampaignError))
	{
		if (const TArray<TSharedPtr<FJsonValue>>* Values = Array(CampaignRoot, TEXT("stages")))
		{
			for (const TSharedPtr<FJsonValue>& Value : *Values)
			{
				const TSharedPtr<FJsonObject> Row = Value.IsValid() ? Value->AsObject() : nullptr;
				if (!Row.IsValid()) continue;
				FTreadM4CampaignStage& Stage = CampaignStages.AddDefaulted_GetRef();
				Stage.Index = static_cast<int32>(Num(Row, TEXT("index")));
				Stage.Country = Str(Row, TEXT("country"));
				Stage.Landmark = Str(Row, TEXT("landmark"));
				Stage.Rule = Str(Row, TEXT("rule"));
				Stage.Effect = Str(Row, TEXT("effect"));
				Stage.LeaderId = Str(Row, TEXT("leaderId"));
				Stage.AiLevel = static_cast<int32>(Num(Row, TEXT("aiLevel"), 1));
				Stage.GarrisonBonus = static_cast<int32>(Num(Row, TEXT("garrisonBonus")));
				Stage.EnemyHpBonus = static_cast<int32>(Num(Row, TEXT("enemyHpBonus")));
				Stage.StartGoldBonus = static_cast<int32>(Num(Row, TEXT("startGoldBonus")));
				Stage.IncomeBonus = static_cast<int32>(Num(Row, TEXT("incomeBonus")));
				Stage.DamageTakenPercent = static_cast<int32>(Num(Row, TEXT("damageTakenPercent"), 100));
				Stage.PrepareSecondsDelta = static_cast<int32>(Num(Row, TEXT("prepareSecondsDelta")));
			}
		}
		Version += TEXT("+campaign");
	}

	if (Pacts.Num() == 0 || Cards.Num() == 0)
	{
		Error = TEXT("empty pact or trait data");
		return false;
	}
	bLoaded = true;
	return true;
}

const FTreadM2PactDef* FTreadM2PactData::FindPact(const FString& PactId) const
{
	const int32* Index = PactIndex.Find(PactId);
	return Index ? &Pacts[*Index] : nullptr;
}

const FTreadM2Card* FTreadM2PactData::FindCard(const FString& CharacterId) const
{
	return Cards.Find(CharacterId);
}

const FTreadM2Item* FTreadM2PactData::FindItem(const FString& ItemIdOrName) const
{
	return Items.FindByPredicate([&](const FTreadM2Item& Item)
	{
		return Item.ItemId == ItemIdOrName || Item.DisplayName == ItemIdOrName;
	});
}

const FTreadM2StrategyBus* FTreadM2PactData::FindStrategy(const FString& StrategyId) const
{
	return Strategies.FindByPredicate([&](const FTreadM2StrategyBus& Bus) { return Bus.StrategyId == StrategyId; });
}
