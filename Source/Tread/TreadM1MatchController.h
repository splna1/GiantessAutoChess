#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Math/RandomStream.h"
#include "TreadM1DataTypes.h"
#include "TreadM2PactData.h"
#include "TreadM1MatchController.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FTreadM1PhaseChanged, ETreadM1Phase, PreviousPhase, ETreadM1Phase, NewPhase);
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FTreadM1StateChanged);

/** Per-unit combat multipliers derived from active pacts and passive traits at battle start. */
struct FTreadM2UnitCombat
{
	float AttackMul = 1.0f;
	float HealthMul = 1.0f;
	float DamageTaken = 1.0f;
	int32 SkillEvery = 3;
};

/** Item procs aggregated for one unit at battle start (ItemCatalog.json "proc"; document/175). */
struct FTreadM2UnitProcs
{
	float DamageScale = 1.0f;
	float DamageScaleWindow = 0.0f;
	float DamageScaleDecay = 0.0f;
	float DamageTakenScale = 1.0f;
	float StunChance = 0.0f;
	float StunDuration = 0.0f;
	float StunWindow = 0.0f;
	float Lifesteal = 0.0f;
	float Regen = 0.0f;
	float ReviveHealth = 0.5f;
	int32 ReviveCount = 0;
	float UndyingDuration = 0.0f;
	int32 SpInitial = 0;
	int32 SpPerPactMember = 0;
	float SpRegen = 0.0f;
	float AmmoRefundChance = 0.0f;
	float AmmoRefundPercent = 0.0f;
	int32 AmmoRefundMax = 0;
	float ExtraHitChance = 0.0f;
	float ExtraHitScale = 0.0f;
	float ReflectScale = 0.0f;
	float AttackStack = 0.0f;
	int32 AttackStackMax = 0;
	float AttackPerSkill = 0.0f;
	int32 AttackPerSkillMax = 0;
	/** Flat attack-speed points from equipment (0.5% attack each, matching the combat stat conversion). */
	float AttackSpeedFlat = 0.0f;
	float BurnScale = 0.0f;
	float SilenceDuration = 0.0f;
	float HealthConditional = 0.0f;
	bool bTaunt = false;
	bool bImmuneAbove = false;
	float ImmuneHpRatio = 0.0f;
	bool bFrontEmpty = false;
	// Second wave (document/178): the fourteen rows that were still partial / deferred.
	float SelfDot = 0.0f;
	int32 RedeployCount = 0;
	float RedeployHealth = 0.4f;
	float NeighborAttackSpeed = 0.0f;
	float Penetrate = 0.0f;
	/** RecruitOnEquip: "Pact" (4_01) or "Tier" (5_04). */
	FString RecruitOnEquip;
	float StealthDuration = 0.0f;
	float ShieldOnHealChance = 0.0f;
	int32 ShieldOnHealMax = 0;
	int32 SellCounter = 0;
	bool bPostBattleTransform = false;
	float SkillBuffValue = 0.0f;
	float SkillBuffDuration = 0.0f;
	float AtkRamp = 0.0f;
	float AtkRampCap = 0.0f;
	float AttackSpeedPerAcquire = 0.0f;
	int32 AttackSpeedPerAcquireMax = 0;
	int32 FundsPerAcquire = 0;
	int32 FundsPerAcquireMax = 0;
	bool bBondGrant = false;

	bool IsEmpty() const;
};

/** One side of a battle pairing plus the per-unit proc runtime (document/175). */
struct FTreadM2BattleSide
{
	FTreadM1PlayerState* Player = nullptr;
	TArray<FTreadM2UnitCombat> Combat;
	TArray<FTreadM2UnitProcs> Procs;
	TArray<int32> Health;
	/** HP before 阿戈尔/summons/proc bonuses; the regen and revive fractions use it. */
	TArray<int32> MaxHealth;
	TArray<int32> StunUntil;
	TArray<int32> ReviveLeft;
	TArray<int32> BurnUntil;
	TArray<int32> BurnDamage;
	TArray<int32> Attacks;
	TArray<int32> Targets;
	TArray<int32> UndyingUntil;
	TArray<float> DamageScale;
	TArray<int32> AmmoRefundLeft;
	// Second wave (document/178).
	TArray<int32> RedeployAt;
	TArray<int32> RedeployLeft;
	TArray<int32> StealthUntil;
	TArray<int32> Shield;
	int32 Alive = 0;
};

/**
 * Authoritative, deterministic M1 match state machine.
 * The actor owns all four participant records and is intentionally data-only:
 * UI and Blueprint layers observe or issue commands through the functions below.
 */
UCLASS(BlueprintType, meta=(DisplayName="Tread M1 Match Controller"))
class TREAD_API ATreadM1MatchController : public AActor
{
	GENERATED_BODY()

public:
	ATreadM1MatchController();

	UPROPERTY(BlueprintReadOnly, VisibleAnywhere, Category = "M1|State")
	FTreadM1MatchState MatchState;

	UPROPERTY(BlueprintAssignable, Category = "M1|Events")
	FTreadM1PhaseChanged OnPhaseChanged;

	UPROPERTY(BlueprintAssignable, Category = "M1|Events")
	FTreadM1StateChanged OnStateChanged;

	UFUNCTION(BlueprintCallable, Category = "M1|Match")
	void InitializeMatch(int64 InSeed = 20260926);

	UFUNCTION(BlueprintPure, Category = "M1|Match")
	FTreadM1MatchState GetMatchState() const { return MatchState; }

	UFUNCTION(BlueprintPure, Category = "M1|Match")
	ETreadM1Phase GetPhase() const { return MatchState.Phase; }

	UFUNCTION(BlueprintPure, Category = "M1|Match")
	int32 GetRoundIndex() const { return MatchState.RoundIndex; }

	UFUNCTION(BlueprintCallable, Category = "M1|BP")
	FTreadM1CommandResult ChoosePlayerStrategy(const FString& StrategyId, const FString& RequestId = TEXT(""));

	UFUNCTION(BlueprintCallable, Category = "M1|BP")
	FTreadM1CommandResult BeginPreMatchBP(const FString& RequestId = TEXT(""));

	UFUNCTION(BlueprintCallable, Category = "M1|BP")
	FTreadM1CommandResult RunNextAIPick(const FString& RequestId = TEXT(""));

	UFUNCTION(BlueprintCallable, Category = "M1|BP")
	FTreadM1CommandResult ConfirmPreMatchBP(const FString& RequestId = TEXT(""));

	UFUNCTION(BlueprintCallable, Category = "M1|Round")
	FTreadM1CommandResult BeginPreparation(const FString& RequestId = TEXT(""));

	UFUNCTION(BlueprintCallable, Category = "M1|Round")
	FTreadM1CommandResult DeployAndStartBattle(const FString& RequestId = TEXT(""));

	UFUNCTION(BlueprintCallable, Category = "M1|Round")
	FTreadM1CommandResult ResolveBattle(const FString& RequestId = TEXT(""));

	/** document/12: a board presenter replays battles. While one is registered, live battles resolve on their first
	 * tick and the Battle phase lasts until NotifyBattlePresentationFinished (or the battle cap). Explicit
	 * DeployAndStartBattle + ResolveBattle calls (self-tests) are unchanged. */
	void SetBattlePresenterActive(bool bActive) { bBattlePresenterActive = bActive; }
	void NotifyBattlePresentationFinished();

	UFUNCTION(BlueprintCallable, Category = "M1|Round")
	FTreadM1CommandResult SettleRound(const FString& RequestId = TEXT(""));

	UFUNCTION(BlueprintCallable, Category = "M1|Round")
	FTreadM1CommandResult AdvanceToNextRound(const FString& RequestId = TEXT(""));

	UFUNCTION(BlueprintCallable, Category = "M1|Round")
	FTreadM1CommandResult RunRound(const FString& RequestId = TEXT(""));

	UFUNCTION(BlueprintCallable, Category = "M1|Board")
	FTreadM1CommandResult MoveUnitToBoard(const FString& PlayerId, const FString& UnitInstanceId, FIntPoint BoardCell, const FString& RequestId = TEXT(""));

	UFUNCTION(BlueprintCallable, Category = "M1|Board")
	FTreadM1CommandResult MoveUnitToBench(const FString& PlayerId, const FString& UnitInstanceId, const FString& RequestId = TEXT(""));

	UFUNCTION(BlueprintCallable, Category = "M1|Board")
	FTreadM1CommandResult SwapBoardUnits(const FString& PlayerId, const FString& FirstUnitInstanceId, const FString& SecondUnitInstanceId, const FString& RequestId = TEXT(""));

	UFUNCTION(BlueprintCallable, Category = "M1|Economy")
	FTreadM1CommandResult PurchaseShopSlot(const FString& PlayerId, int32 SlotIndex, const FString& RequestId = TEXT(""));

	UFUNCTION(BlueprintCallable, Category = "M1|Economy")
	FTreadM1CommandResult RefreshShop(const FString& PlayerId, const FString& RequestId = TEXT(""));

	UFUNCTION(BlueprintCallable, Category = "M1|Economy")
	FTreadM1CommandResult ToggleShopLock(const FString& PlayerId, const FString& RequestId = TEXT(""));

	UFUNCTION(BlueprintCallable, Category = "M1|Economy")
	FTreadM1CommandResult SellUnit(const FString& PlayerId, const FString& UnitInstanceId, const FString& RequestId = TEXT(""));

	/** Create a transform clone from an owned target character. The clone occupies one population slot and never consumes PoolLedger copies. */
	UFUNCTION(BlueprintCallable, Category = "M1|Clone")
	FTreadM1CommandResult CreateTransformClone(const FString& PlayerId, const FString& CopySourceCharacterId, const FString& RequestId = TEXT(""));

	/** Create a transform clone from a concrete owned unit, preserving its current star/equipment snapshot. */
	UFUNCTION(BlueprintCallable, Category = "M1|Clone")
	FTreadM1CommandResult CreateTransformCloneFromUnit(const FString& PlayerId, const FString& SourceUnitInstanceId, const FString& RequestId = TEXT(""));

	/** Destroy an active transform clone by its stable cloneInstanceId. */
	UFUNCTION(BlueprintCallable, Category = "M1|Clone")
	FTreadM1CommandResult DestroyTransformClone(const FString& PlayerId, const FString& CloneInstanceId, const FString& RequestId = TEXT(""));

	UFUNCTION(BlueprintCallable, Category = "M1|Economy")
	FTreadM1CommandResult BuyExperience(const FString& PlayerId, const FString& RequestId = TEXT(""));

	UFUNCTION(BlueprintCallable, Category = "M1|Economy")
	void AdvancePreparationTimer(float DeltaSeconds);

	UFUNCTION(BlueprintPure, Category = "M1|Economy")
	FTreadM1IncomeBreakdown GetNextRoundIncome(const FString& PlayerId) const;

	UFUNCTION(BlueprintPure, Category = "M1|Pool")
	FTreadM1PoolBalance GetPoolBalance(const FString& CharacterId, const FString& OperatorTier) const;

	UFUNCTION(BlueprintPure, Category = "M1|Pool")
	bool ValidatePoolLedger() const;

	UFUNCTION(BlueprintCallable, Category = "M1|Test")
	bool RunDeterministicSelfTest(const FString& OutputPath = TEXT(""));

	/** N2 board check: stand one unit per character id on a player's board, in the order given, from
	 * cell (0,4) rightwards and downwards. Units come in through the same pool reserve and deploy
	 * commands a purchase takes, so the ledger, pact state and snapshots stay consistent; the
	 * population limit is the one rule the check lifts, since a round could never afford a full board. */
	UFUNCTION(BlueprintCallable, Category = "N2|Test")
	bool StockBoardForFixture(const FString& PlayerId, const TArray<FString>& CharacterIds);

	UFUNCTION(BlueprintPure, Category = "M1|Scout")
	bool CanScout() const;

	UFUNCTION(BlueprintPure, Category = "M1|Scout")
	FTreadM1ScoutSnapshot GetScoutSnapshot(const FString& PlayerId) const;

	/** Move an inventory item onto an owned unit (max 3). Item-provided pacts count immediately. */
	UFUNCTION(BlueprintCallable, Category = "M2|Pact")
	FTreadM1CommandResult EquipItem(const FString& PlayerId, const FString& ItemId, const FString& UnitInstanceId, const FString& RequestId = TEXT(""));

	/** document/176: three free item choices at the start of every preparation. */
	void RollRewardOffer(FTreadM1PlayerState& Player);
	int32 RewardTierCap(const FTreadM1PlayerState& Player) const;
	FTreadM1CommandResult ChooseReward(const FString& PlayerId, int32 Index, const FString& RequestId = TEXT(""));

	UFUNCTION(BlueprintPure, Category = "M2|Pact")
	TArray<FTreadM2PactProgress> GetPactProgress(const FString& PlayerId) const;

	UFUNCTION(BlueprintPure, Category = "M2|Pact")
	TArray<FString> GetCardPacts(const FString& CharacterId) const;

	/** "X/Y" trait value with the value in effect bracketed, e.g. "[2]/4" (1-star) or "2/[4]" (elite). */
	UFUNCTION(BlueprintPure, Category = "M2|Pact")
	FString GetTraitValueText(const FString& CharacterId, int32 UnitStar) const;

	UFUNCTION(BlueprintPure, Category = "M2|Pact")
	FString GetTraitSummary(const FString& CharacterId) const;

	/** N2: "<operator name>" of the card bound to a character model (Roster112), or the character id. */
	UFUNCTION(BlueprintPure, Category = "N1|Roster")
	FString GetCardDisplayName(const FString& CharacterId) const;

	/** M4: UE model display name of a character (CharacterRosterMap.json), or "" without the roster map. */
	UFUNCTION(BlueprintPure, Category = "M4|Roster")
	FString GetCardModelName(const FString& CharacterId) const;

	/** M4: avatar texture path (/Game/Tread/UI/Avatars/T_Avatar_<id>): chest-up screenshot of the character's 3D model. */
	UFUNCTION(BlueprintPure, Category = "M4|Roster")
	FString GetCardAvatarPath(const FString& CharacterId) const;

	/** M4: portrait texture path (/Game/Tread/UI/Portraits/T_Portrait_<id>): the PNG illustration, detail layer only. */
	UFUNCTION(BlueprintPure, Category = "M4|Roster")
	FString GetCardPortraitPath(const FString& CharacterId) const;

	/** M4: every card id in roster order (112), for the roster audit panel. */
	UFUNCTION(BlueprintPure, Category = "M4|Roster")
	TArray<FString> GetRosterCharacterIds() const;

	/** M4: shared SFX / BGM SoundWave path by key (e.g. "purchase", "battle"), "" if unknown. */
	UFUNCTION(BlueprintPure, Category = "M4|Audio")
	FString GetSfxAssetPath(const FString& Key) const;
	UFUNCTION(BlueprintPure, Category = "M4|Audio")
	FString GetBgmAssetPath(const FString& Key) const;

	/** M4 campaign: pick a stage in the R0 briefing (unlocked stages only, 0 = free match); restarts the match
	 * with the same seed under that stage's rules. */
	UFUNCTION(BlueprintCallable, Category = "M4|Campaign")
	FTreadM1CommandResult SelectCampaignStage(int32 StageIndex, const FString& RequestId = TEXT(""));

	UFUNCTION(BlueprintPure, Category = "M4|Campaign")
	TArray<FTreadM4CampaignStageView> GetCampaignStages() const;

	/** M4 test/evidence hook: overwrite the saved progress with the first Count stages conquered. */
	UFUNCTION(BlueprintCallable, Category = "M4|Test")
	void SetCampaignProgressForTest(int32 Count);

	/** M4 test hook: put an item (ItemCatalog / StrategyItems id) into a player's inventory. */
	UFUNCTION(BlueprintCallable, Category = "M4|Test")
	bool GrantItemForTest(const FString& PlayerId, const FString& ItemId);

	/** M4 test hook: "attack=.. health=.. damageTaken=.." battle multipliers of an owned unit (equipment included). */
	UFUNCTION(BlueprintPure, Category = "M4|Test")
	FString GetUnitCombatSummary(const FString& PlayerId, const FString& UnitInstanceId) const;

	/** M4 test hook: finish the current campaign match as won (true) or lost, recording the result like GameOver. */
	UFUNCTION(BlueprintCallable, Category = "M4|Test")
	FString FinishCampaignForTest(bool bWon);

	/** M4 evidence hook: set an owned unit's star (2+ shows the elite stats / traits in the card tooltip). */
	UFUNCTION(BlueprintCallable, Category = "M4|Test")
	bool SetUnitStarForTest(const FString& PlayerId, const FString& UnitInstanceId, int32 Star);

	/** M4: the loaded item (ItemCatalog / StrategyItems / seeds) or nullptr. */
	const FTreadM2Item* FindItemData(const FString& ItemIdOrName) const { return PactData.IsValid() ? PactData->FindItem(ItemIdOrName) : nullptr; }

	/** M4: the loaded card (roster, pacts, traits, stats) or nullptr. */
	const FTreadM2Card* FindCardData(const FString& CharacterId) const { return PactData.IsValid() ? PactData->FindCard(CharacterId) : nullptr; }

	/** N1: current 调度中心 upgrade price for a player (0 at max level). */
	UFUNCTION(BlueprintPure, Category = "N1|Economy")
	int32 GetShopUpgradeCost(const FString& PlayerId) const;

	UFUNCTION(BlueprintPure, Category = "N1|Economy")
	bool UsesN1Economy() const { return HasN1Economy(); }

	UFUNCTION(BlueprintPure, Category = "M2|Pact")
	FString GetItemDisplayName(const FString& ItemId) const;

	UFUNCTION(BlueprintPure, Category = "M2|Pact")
	bool IsPactDataLoaded() const { return PactData.IsValid() && PactData->bLoaded; }

	UFUNCTION(BlueprintCallable, Category = "M2|Test")
	bool RunM2PactSelfTest(const FString& OutputPath = TEXT(""));
	/** document/177: audio acceptance - loads and plays one of every BGM/SFX/voice/footstep. */
	bool RunAudioSelfTest(const FString& OutputPath = TEXT(""));

	/** HUD: 0..1 health and 0..1 技力 for a unit on the given player's board (document/168). */
	UFUNCTION(BlueprintPure, Category = "Battle|HUD")
	float GetUnitHealthFraction(const FString& PlayerId, const FString& UnitInstanceId) const;
	UFUNCTION(BlueprintPure, Category = "Battle|HUD")
	float GetUnitSpFraction(const FString& PlayerId, const FString& UnitInstanceId) const;
	UFUNCTION(BlueprintPure, Category = "Battle|HUD")
	int32 GetUnitAmmo(const FString& PlayerId, const FString& UnitInstanceId) const;
	/** 拉特兰: the attack multiplier this unit has stacked by spending rounds (document/170 HUD readout). */
	UFUNCTION(BlueprintPure, Category = "Battle|HUD")
	float GetUnitAmmoMultiplier(const FString& PlayerId, const FString& UnitInstanceId) const;
	/** 远见: how many of the player's bench units carry the pact (the 整备区 layers, document/170 HUD readout). */
	UFUNCTION(BlueprintPure, Category = "Battle|HUD")
	int32 GetForesightBenchCount(const FString& PlayerId) const;


protected:
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

private:
	void SetPhase(ETreadM1Phase NewPhase);
	void SetRoundTypeForCurrentRound();
	void LoadStrategies();
	void BuildInitialPlayers();
	void BuildAIPlaceholderRosters();
	void InitializePoolLedger();
	void BuildShop(FTreadM1PlayerState& Player, int32 RefreshIndex);
	void ReturnShopReservations(FTreadM1PlayerState& Player, const FString& Action = TEXT("RefreshReturn"));
	void ReturnPlayerPoolAssets(FTreadM1PlayerState& Player);
	void RefreshProjectedIncomes();
	FTreadM1IncomeBreakdown CalculateIncome(const FTreadM1PlayerState& Player) const;
	void ApplyExperience(FTreadM1PlayerState& Player, int32 Amount);
	int32 StreakReward(const FTreadM1PlayerState& Player) const;
	bool RecordPoolLedger(const FString& Action, const FString& PlayerId, const FTreadM1UnitInstance& Unit, int32 Delta);
	bool RecordPoolLedger(const FString& Action, const FString& PlayerId, const FTreadM1ShopSlot& Slot, int32 Delta);
	FTreadM1PoolBalance* FindPoolBalance(const FString& CharacterId, const FString& OperatorTier);
	const FTreadM1PoolBalance* FindPoolBalance(const FString& CharacterId, const FString& OperatorTier) const;
	bool ApplyPoolLedgerDelta(const FString& Action, const FString& PlayerId, const FString& CharacterId,
		const FString& OperatorTier, const FString& UnitInstanceId, const FString& CloneInstanceId,
		const FString& CopySourceCharacterId, int32 Delta);
	void AppendPoolLedgerEntry(const FString& Action, const FString& PlayerId, const FString& CharacterId,
		const FString& OperatorTier, const FString& UnitInstanceId, const FString& CloneInstanceId,
		const FString& CopySourceCharacterId, int32 Delta);
	/** document/165: the AI opponents buy, level, refresh and deploy like a player (off in self-tests). */
	bool bAIOpponentsPlay = true;
	void RunAIPreparation();

	/** M4 campaign: the active stage, its scripted opponent for this round, and the progress save. */
	const FTreadM4CampaignStage* ActiveCampaignStage() const;
	const FTreadM4ScriptedOpponent* ScriptedOpponentForRound() const;
	void BuildScriptedOpponent(const FTreadM4ScriptedOpponent& Def);
	void LoadCampaignProgress();
	void SaveCampaignProgress() const;
	void RecordCampaignResult();
	int32 ApplyDamageTaken(const FTreadM1PlayerState& Player, int32 Damage) const;
	/** The scripted side of R1-R2 / R12 campaign battles; never in MatchState.Players. */
	FTreadM1PlayerState ScriptedState;
	const FTreadM4ScriptedOpponent* ActiveScriptedDef = nullptr;
	int32 PendingCampaignStage = 0;
	/** document/12 battle hold (see SetBattlePresenterActive). */
	bool bBattlePresenterActive = false;
	bool bHoldSettlement = false;
	bool bBattleHeld = false;
	void FinishHeldBattle();
	TArray<int32> ConqueredStages;
	/** M4: run a "装备时销毁" item's op (ItemCatalog onEquip) for the unit it was equipped on. */
	void ApplyItemOnEquip(FTreadM1PlayerState& Player, FTreadM1UnitInstance& Unit, const FTreadM2Item& Item);
	/** M4: funds paid with every settlement by equipped "each round" items (Flags item:EachRoundFunds:N). */
	int32 EachRoundFundsBonus(const FTreadM1PlayerState& Player) const;
	FTreadM1CommandResult CreateTransformCloneInternal(const FString& PlayerId, const FTreadM1UnitInstance& SourceUnit,
		const FString& RequestId);
	void SyncRandomState();
	int32 NormalizeSeed(int64 InSeed) const;
	void RefreshScoutSnapshots();
	void ApplyInitialStrategyCosts();
	void BuildPairings();
	void RecordBattleEvent(ETreadM1BattleEventType EventType, const FString& SourcePlayerId,
		const FString& TargetPlayerId, int32 Amount, const FString& SourceUnitId = TEXT(""),
		const FString& TargetUnitId = TEXT(""), int32 TargetHealthAfterOverride = INDEX_NONE);
	/** Return a previously completed command for the same idempotency key. Empty
	 * request ids intentionally remain non-idempotent for local/editor calls. */
	bool TryGetProcessedRequest(const FString& RequestId, FTreadM1CommandResult& OutResult) const;
	void CacheProcessedRequest(const FTreadM1CommandResult& Result);
	FTreadM1CommandResult Accept(const FString& RequestId);
	FTreadM1CommandResult Reject(ETreadM1RejectReason Reason, const FString& RequestId);
	FTreadM1PlayerState* FindPlayer(const FString& PlayerId);
	const FTreadM1PlayerState* FindPlayer(const FString& PlayerId) const;
	FTreadM1StrategyState* FindStrategy(const FString& StrategyId);
	bool IsAvailableStrategy(const FString& StrategyId) const;
	int32 LivingPlayerCount() const;
	int32 BoardStrength(const FTreadM1PlayerState& Player) const;
	void RankPlayers();
	FString PhaseName(ETreadM1Phase Phase) const;
	FString RoundTypeName(ETreadM1RoundType RoundType) const;
	bool WriteSelfTestReport(const FString& Path, const TArray<FString>& PhaseTrace, const TArray<bool>& StepResults,
		bool bSameSeedReplayEqual, uint32 ReplaySignature, const TArray<int32>& AcceptedRounds,
		const TArray<FString>& AcceptedRoundTypes, const TMap<FString, bool>& NamedChecks) const;
	bool WritePoolLedgerReport(const FString& Path) const;

	// ---- M2 pact/trait event bus (TreadM2PactRuntime.cpp) ----
	void LoadM2Data();
	void RecomputePacts(FTreadM1PlayerState& Player);
	void RecomputeAllPacts();
	TArray<FString> GetUnitPacts(const FTreadM1PlayerState& Player, const FTreadM1UnitInstance& Unit, bool bIncludeHarmony) const;
	FTreadM2PactProgress* FindPactProgress(FTreadM1PlayerState& Player, const FString& PactId);
	const FTreadM2PactProgress* FindPactProgress(const FTreadM1PlayerState& Player, const FString& PactId) const;
	bool IsElite(const FTreadM1UnitInstance& Unit) const;
	int32 PurchaseCostFor(const FString& CharacterId, int32 DrawnCost) const;
	// ---- N1 Stronghold-Protocol economy (TreadM2PactRuntime.cpp) ----
	bool HasN1Economy() const;
	/** Tier of the operator bound to a character (Roster112); empty when the card has none. */
	FString CardTier(const FString& CharacterId) const;
	int32 TierPrice(const FString& OperatorTier) const;
	int32 ShopUpgradeCost(const FTreadM1PlayerState& Player) const;
	/** Copy-weighted draw of one shop card (tier <= shop level) from the remaining shared-pool copies. */
	bool DrawShopCard(const FTreadM1PlayerState& Player, FString& OutCharacterId, FString& OutTier);
	void DispatchTraitEvent(FTreadM1PlayerState& Player, ETreadM2Trigger Trigger, const FString& EventName,
		const FTreadM1UnitInstance* Subject = nullptr, int32 Depth = 0);
	void DispatchRoundTrigger(ETreadM2Trigger Trigger, const FString& EventName);
	void ExecuteTrait(FTreadM1PlayerState& Player, const FTreadM2Trait& Trait, const FTreadM1UnitInstance& TraitOwner,
		const FTreadM1UnitInstance& Anchor, ETreadM2Trigger Trigger, const FString& EventName, int32 Depth);
	bool TraitConditionMet(const FTreadM1PlayerState& Player, const FTreadM2Trait& Trait, const FTreadM1UnitInstance& TraitOwner) const;
	TArray<FString> SelectPacts(const FTreadM1PlayerState& Player, const FTreadM2Effect& Effect, const FTreadM1UnitInstance& TraitOwner,
		const FTreadM1UnitInstance& Target, const FTreadM1UnitInstance& Anchor);
	int32 ScaleAmount(const FTreadM1PlayerState& Player, const FTreadM2Effect& Effect, const FTreadM1UnitInstance& TraitOwner, const FString& PactId) const;
	int32 AddPactStacks(FTreadM1PlayerState& Player, const FString& PactId, int32 Amount, bool bRequireActive, const FString& SourceId,
		const FTreadM1UnitInstance* SourceUnit, ETreadM2Trigger Trigger, const FString& EventName, bool bAllowAmplify);
	void EvaluatePactMilestones(FTreadM1PlayerState& Player, const FString& PactId, ETreadM2Trigger Trigger);
	void ApplyPactTierOps(FTreadM1PlayerState& Player, ETreadM2Trigger Trigger, const FString& EventName);
	void DispatchStrategyEffects(FTreadM1PlayerState& Player, ETreadM2Trigger Trigger, const FString& EventName);
	int32 AcquireRepeatCount(const FTreadM1PlayerState& Player) const;
	void GrantItemToPlayer(FTreadM1PlayerState& Player, const FString& ItemName, int32 Count, const FString& SourceId, ETreadM2Trigger Trigger);
	bool GrantUnitToPlayer(FTreadM1PlayerState& Player, const FString& CharacterId, const FString& SourceId, ETreadM2Trigger Trigger, int32 Depth);
	void HandleUnitAcquired(FTreadM1PlayerState& Player, const FString& UnitInstanceId, const FString& EventName, int32 Depth);
	bool TryAutoCombine(FTreadM1PlayerState& Player, const FString& CharacterId, const FString& OperatorTier, int32 Depth);
	FTreadM1UnitInstance* FindOwnedUnit(FTreadM1PlayerState& Player, const FString& UnitInstanceId);
	TArray<FTreadM1UnitInstance> ResolveTargets(const FTreadM1PlayerState& Player, const FTreadM1UnitInstance& Anchor,
		const FString& Targets, const FString& TriggerFilter = FString()) const;
	void RecordTraitLog(const FTreadM1PlayerState& Player, ETreadM2Trigger Trigger, const FString& EventName,
		const FTreadM1UnitInstance* Unit, const FString& SourceId, const FString& Op, const FString& PactId,
		int32 Amount, int32 StacksAfter, bool bElite, const FString& Status, const FString& Detail = FString());
	FTreadM2UnitCombat ComputeUnitCombat(const FTreadM1PlayerState& Player, const FTreadM1UnitInstance& Unit) const;
	void HandleBattleAttack(FTreadM1PlayerState& Player, const FTreadM1UnitInstance& Unit, int32& AttackCount,
		const FTreadM2UnitCombat& Combat, const FString& TargetPlayerId, const FString& TargetUnitId);
	void OnBattleUnitEvent(FTreadM1PlayerState& Player, const FString& EventName, const FTreadM1UnitInstance& Actor);

	// ---- Item procs (ItemCatalog.json "proc"; document/175) ----
	FTreadM2UnitProcs ComputeUnitProcs(const FTreadM1PlayerState& Player, const FTreadM1UnitInstance& Unit) const;
	void BuildBattleSide(FTreadM2BattleSide& Side, FTreadM1PlayerState& Player);
	void SyncBattleSide(FTreadM2BattleSide& Side);
	void ApplyBattleStartProcs(FTreadM2BattleSide& Side);
	void TickBattleSideProcs(FTreadM2BattleSide& Side, int32 Exchange);
	int32 SelectBattleTarget(const FTreadM2BattleSide& Defender, int32 Exchange) const;
	void RunBattleExchange(FTreadM2BattleSide& Attacker, FTreadM2BattleSide& Defender, int32 Exchange);
	void ApplyBattleDamage(FTreadM2BattleSide& Defender, int32 Index, int32 Damage,
		const FString& FromPlayerId, const FString& FromUnitId);
	/** Item revive -> pact revive -> knock-down; Killer may be null for burn ticks. */
	void ResolveBattleDeath(FTreadM2BattleSide& Defender, int32 Index, const FString& FromPlayerId,
		const FString& FromUnitId, const FTreadM2BattleSide* Killer, int32 KillerIndex);
	/** document/178: 4_01 / 5_04 run their special recruit when equipped. */
	void GrantRecruitFromItem(FTreadM1PlayerState& Player, const FTreadM1UnitInstance& Unit, const FTreadM2Item& Item);
	/** document/178: 5_08 upgrades the holder to a random higher-tier operator after the battle. */
	void ApplyPostBattleItemTransforms();
	void SnapshotBattlePactStates();
	/** 拉特兰: spent rounds raise this unit's attack (document/168). */
	float AmmoAttackMultiplier(const FTreadM1PlayerState& Player, const FTreadM1UnitInstance& Unit) const;
	/** 远见: one layer per shop refresh (document/168). */
	void FeedForesightLayers(FTreadM1PlayerState& Player);

	/** document/171 pact mechanics. */
	bool TryPactRevive(FTreadM1PlayerState& Player, const FTreadM1UnitInstance& Unit, int32& Health);
	/** 奇迹: one roll for a free refresh (extracted so the self-test can drive it). */
	bool TryMiracleFreeRefresh(FTreadM1PlayerState& Player);
	void ApplyYanSummon(FTreadM1PlayerState& Player, TArray<int32>& Health, TArray<FTreadM2UnitCombat>& Combat);

	/** 阿戈尔 [3]: each 阿戈尔 unit devours the unit one cell in front of it (right = front) at battle start. */
	void ApplyAgirDevour(FTreadM1PlayerState& Player, TArray<int32>& Health, TArray<FTreadM2UnitCombat>& Combat);
	void StripSummons(FTreadM1PlayerState& Player);
	/** 不屈 2 档: every knock-down hands the whole team +sp 技力. */
	void PactOnKnockDown(FTreadM1PlayerState& Player);

	void ResetBattleTraitState();
	/** Clears the per-battle meters (SP / ammo / HUD bars); called when a battle starts, not when it ends. */
	void ResetBattleMeters();
	/** Evidence/fixture helper: put CharacterId+Tier into a shop slot, returning any prior reservation first. */
	bool StockShopSlotForFixture(FTreadM1PlayerState& Player, int32 SlotIndex, const FString& CharacterId, const FString& Tier);
	/** Deterministic R2 showcase built with real commands for M2 screenshots (-TreadM2Capture). */
	void BuildM2Showcase(const FString& Stage);
	void RequestM2Screenshot(const FString& Name);
	bool WriteM2SelfTestReport(const FString& Path, const TMap<FString, bool>& NamedChecks, const TArray<FString>& Notes,
		const TSharedPtr<class FJsonObject>& Extra) const;

	bool bInitialized = false;
	bool bInitialStrategyCostsApplied = false;
	int32 BattleEventSequence = 0;
	int32 UnitInstanceSequence = 0;
	int32 CloneInstanceSequence = 0;
	/** Settlement is once per round, even when a caller uses a fresh request id. */
	int32 LastSettledRoundIndex = 0;
	FRandomStream RandomStream;
	TSet<FString> PoolReturnedPlayerIds;
	/** Command results retained for the lifetime of one match. This prevents a
	 * retried UI/network command from applying economy, board, or phase changes
	 * twice while returning the original result payload. */
	TMap<FString, FTreadM1CommandResult> ProcessedRequests;

	/** Loaded once per InitializeMatch from Content/Data/Generated (Pacts/Traits/ItemSeeds/StrategyEffects). */
	TSharedPtr<FTreadM2PactData> PactData;
	/** Per-battle trait counters (every-N, first-only, per-battle caps). Reset at each ResolveBattle. */
	TMap<FString, int32> BattleTraitCounters;

	/** 技力 (document/167): per-unit SP carried between attacks, keyed by unit instance id. */
	TMap<FString, float> BattleSp;

	/** 拉特兰 ammunition (document/168): rounds granted by skills and spent by attacks. */
	TMap<FString, int32> BattleAmmo;
	TMap<FString, int32> BattleAmmoSpent;
	/** document/171: 阿戈尔 revives left this battle and the units that already used their single revive. */
	int32 BattleAgirRevives = 0;
	TSet<FString> BattleRevivedUnits;
	int32 BattleSummonSerial = 0;
	/** 0..1 bars for the HUD squad panel, keyed by unit instance id. */
	TMap<FString, float> BattleUnitHealth;
	TMap<FString, float> BattleUnitSpMax;
	/** Advances the SP trickle and the HUD bars once per battle exchange (document/168). */
	void HandleBattleExchange(float Seconds);
	/** document/175 proc runtime: stacks and silence windows keyed by unit instance id. */
	TMap<FString, int32> BattleAttackSpeedStacks;
	TMap<FString, int32> BattleSkillAtkStacks;
	TMap<FString, int32> BattleSilenceUntil;
	/** document/178: 6_10 attack window after a skill cast, keyed by unit instance id. */
	TMap<FString, int32> BattleSkillBuffUntil;
	int32 BattleExchangeIndex = 0;
	int32* ActiveBattleCapRemaining = nullptr;
};
