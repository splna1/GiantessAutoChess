#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "TreadBuildingDestructionManager.generated.h"

class UHierarchicalInstancedStaticMeshComponent;
class UInstancedStaticMeshComponent;
class UStaticMesh;
class UStaticMeshComponent;
class USceneComponent;
class UNiagaraSystem;

UENUM()
enum class ETreadAutoTestMode : uint8
{
	/** Kill every registered building in one pass (render/perf regression, document/160 section 3.5). */
	DestroyBand,
	/** Fire a few area hits and let the load-bearing cascade do the rest (document/161). */
	Cascade,
	/** Walk a giant's foot across the band: partial damage, collapse once a building is more than half trampled. */
	Trample,
};

/**
 * Runtime side of the destruction plan (document/126 + 160 + 161 + 162): stage B, the gameplay layer and the trample
 * case with chunk physics + dust.
 *
 * The board's buildings are InstancedStaticMesh components, one instance per building module, so "a building" is
 * (component, instance index). The manager registers every instance inside the middle 4x8 band, gives each one a health
 * value from its module type and footprint, applies damage, shows two intermediate damage stages (debris at the foot),
 * and on death hides the instance and drops the pre-cut chunk set from Tools/destruction/build_chunk_meshes.py.
 *
 * Three ways a building can go down:
 *  - damage (ApplyDamageTo / ApplyAreaDamage): health based, with the load-bearing cascade for neighbours;
 *  - trample (ApplyTrample): a giant's foot covers part of the footprint; once more than
 *    TrampleCollapseFraction (default 0.5, i.e. "more than half") has been trampled, the building collapses as a whole;
 *  - DestroyBuilding / DestroyBand: the direct path used by the perf regression.
 *
 * Chunks can be simulated: with bPhysicsChunks the pieces spawn as rigid bodies, tumble for PhysicsSettleSeconds and are
 * then frozen into instanced static meshes (cheap long term). Every collapse also spawns a Niagara dust burst using an
 * engine template (DustSystemPath) - swap it for a proper VFX pack once one is imported.
 *
 * Console commands (usable in PIE and stand-alone):
 *   Tread.Trample <steps> [coverage]   step a 45 m foot across the band (default 0.35 coverage per step)
 *   Tread.HitBand <damage> <radiusM> [count]
 *   Tread.DestroyBand <count>
 *   Tread.RestoreBand
 *   Tread.DestructionStats
 */
UCLASS()
class TREAD_API ATreadBuildingDestructionManager : public AActor
{
	GENERATED_BODY()

public:
	ATreadBuildingDestructionManager();
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	// ---------------------------------------------------------------- chunks / look
	/** Chunk instances placed per destroyed building (the L sets have 6, the infill sets 8). */
	UPROPERTY(EditAnywhere, Category = "Destruction|Chunks")
	int32 MaxChunksPerBuilding = 8;

	/** Safety valve: at most this many buildings may be destroyed; 0 = unlimited (the band holds 254). */
	UPROPERTY(EditAnywhere, Category = "Destruction|Chunks")
	int32 MaxActiveBuildings = 0;

	/** Collapse look: random yaw per chunk (degrees), sink (metres) and vertical squash. */
	UPROPERTY(EditAnywhere, Category = "Destruction|Chunks")
	float ChunkYawJitterDeg = 3.0f;

	UPROPERTY(EditAnywhere, Category = "Destruction|Chunks")
	float ChunkSinkM = 0.6f;

	UPROPERTY(EditAnywhere, Category = "Destruction|Chunks")
	float ChunkSquashZ = 0.85f;

	// ---------------------------------------------------------------- chunk physics
	/** Spawn the chunks as rigid bodies that settle, then freeze them into instanced meshes. */
	UPROPERTY(EditAnywhere, Category = "Destruction|Physics")
	bool bPhysicsChunks = true;

	/** How long a chunk keeps simulating before it is frozen (seconds). */
	UPROPERTY(EditAnywhere, Category = "Destruction|Physics")
	float PhysicsSettleSeconds = 1.8f;

	/** How many chunks of one building may simulate (the rest are placed statically; complex collision is pricey). */
	UPROPERTY(EditAnywhere, Category = "Destruction|Physics")
	int32 MaxPhysicsChunksPerBuilding = 3;

	/** Hard cap on simultaneously simulating chunks (falls back to the static swap above it). */
	UPROPERTY(EditAnywhere, Category = "Destruction|Physics")
	int32 MaxPhysicsBodies = 24;

	/** Radial impulse applied to fresh chunks (per unit of building footprint, metres). */
	UPROPERTY(EditAnywhere, Category = "Destruction|Physics")
	float ChunkImpulseScale = 90.0f;

	// ---------------------------------------------------------------- dust
	/** Niagara system played when a building collapses; engine template by default. */
	UPROPERTY(EditAnywhere, Category = "Destruction|Dust")
	FString DustSystemPath = TEXT("/Niagara/DefaultAssets/Templates/Systems/SimpleExplosion.SimpleExplosion");

	UPROPERTY(EditAnywhere, Category = "Destruction|Dust")
	float DustLifetimeSeconds = 3.0f;

	/** Spawn dust only while the presenter shows the audience / kill camera - the board camera is 1.7 km away, where the
	 *  pack's near-field systems read as nothing anyway (document/162 section 4.3). */
	UPROPERTY(EditAnywhere, Category = "Destruction|Dust")
	bool bDustOnAudienceOnly = true;

	/** Authored radius of the dust system in cm: the spawned scale is footprint radius / this (so the cloud covers
	 *  the block). The board camera is ~1.7 km away, so systems authored at 1-2 m need ~50-100x. */
	UPROPERTY(EditAnywhere, Category = "Destruction|Dust")
	float DustSourceRadiusCm = 200.0f;

	// ---------------------------------------------------------------- health / cascade
	UPROPERTY(EditAnywhere, Category = "Destruction|Health")
	float HealthLargeModule = 120.0f;

	UPROPERTY(EditAnywhere, Category = "Destruction|Health")
	float HealthInfillModule = 60.0f;

	UPROPERTY(EditAnywhere, Category = "Destruction|Health")
	float HealthBurntModule = 70.0f;

	UPROPERTY(EditAnywhere, Category = "Destruction|Health")
	float HealthLibraryBlock = 200.0f;

	/** Footprint (metres) that maps to a health factor of 1; the factor is clamped to [0.5, 2]. */
	UPROPERTY(EditAnywhere, Category = "Destruction|Health")
	float ReferenceFootprintM = 40.0f;

	/** Whether losing a support damages the neighbours (the load-bearing cascade). */
	UPROPERTY(EditAnywhere, Category = "Destruction|Health")
	bool bLoadBearingCascade = true;

	/** Buildings closer than this (metres) support each other: one street façade holds together, not the whole block. */
	UPROPERTY(EditAnywhere, Category = "Destruction|Health")
	float SupportRadiusM = 90.0f;

	/** Share of its original supports a building needs to stay standing (0.8 = below 80% it starts to fold). */
	UPROPERTY(EditAnywhere, Category = "Destruction|Health")
	float SupportRequirementFraction = 0.8f;

	/** How hard the support deficit hits: deficit 1.0 (all supports gone) with scale 1.3 removes 130% of max health. */
	UPROPERTY(EditAnywhere, Category = "Destruction|Health")
	float CascadeDeficitScale = 1.3f;

	/** How far a collapse chain may travel from the building that was hit. */
	UPROPERTY(EditAnywhere, Category = "Destruction|Health")
	int32 CascadeMaxDepth = 3;

	/** How many cascade deaths one hit may cause in total (the chain stops there, so one blast cannot level the board). */
	UPROPERTY(EditAnywhere, Category = "Destruction|Health")
	int32 CascadeMaxBuildings = 12;

	/** Safety valve: how many cascade damage events one hit may schedule (deaths are capped separately). */
	UPROPERTY(EditAnywhere, Category = "Destruction|Health")
	int32 CascadeMaxEventsPerHit = 120;

	/** Delay between a support dying and the neighbour feeling it (seconds, jittered). */
	UPROPERTY(EditAnywhere, Category = "Destruction|Health")
	float CascadeDelaySeconds = 0.25f;

	/** Health fractions that switch to the two intermediate damage stages (debris at the foot). */
	UPROPERTY(EditAnywhere, Category = "Destruction|Health")
	float DamageStageOneFraction = 0.66f;

	UPROPERTY(EditAnywhere, Category = "Destruction|Health")
	float DamageStageTwoFraction = 0.33f;

	// ---------------------------------------------------------------- trample
	/** Share of the footprint that must be trampled before the building collapses as a whole (0.5 = more than half). */
	UPROPERTY(EditAnywhere, Category = "Destruction|Trample")
	float TrampleCollapseFraction = 0.5f;

	/** Damage a full-coverage step does (partial destruction below the collapse threshold). */
	UPROPERTY(EditAnywhere, Category = "Destruction|Trample")
	float TrampleStepDamage = 90.0f;

	/** Default footprint coverage of one step, when the caller does not pass one. */
	UPROPERTY(EditAnywhere, Category = "Destruction|Trample")
	float TrampleCoveragePerStep = 1.0f;

	/** Foot radius of the giant's step (metres). document/179: 30 m retest (was 45 m). */
	UPROPERTY(EditAnywhere, Category = "Destruction|Trample")
	float TrampleFootRadiusM = 30.0f;

	// ---------------------------------------------------------------- auto test
	UPROPERTY(EditAnywhere, Category = "Destruction|Auto")
	ETreadAutoTestMode AutoTestMode = ETreadAutoTestMode::DestroyBand;

	UPROPERTY(EditAnywhere, Category = "Destruction|Auto")
	int32 AutoTestHits = 4;

	UPROPERTY(EditAnywhere, Category = "Destruction|Auto")
	float AutoTestHitDamage = 200.0f;

	UPROPERTY(EditAnywhere, Category = "Destruction|Auto")
	float AutoTestHitRadiusM = 150.0f;

	/** Number of steps the Trample auto test walks across the band. */
	UPROPERTY(EditAnywhere, Category = "Destruction|Auto")
	int32 AutoTestTrampleSteps = 6;

	/** Run the automated stand-alone pass (also implied by -TreadDestructionTest). */
	UPROPERTY(EditAnywhere, Category = "Destruction|Auto")
	bool bAutoTest = false;

	// ---------------------------------------------------------------- API
	/** Applies damage to one building; returns the damage actually taken (0 if invalid or already dead). */
	UFUNCTION(BlueprintCallable, Category = "Destruction")
	float ApplyDamageTo(int32 Index, float Damage, int32 Depth = 0);

	/** Area damage inside the band; returns how many buildings died from the hit itself (cascade comes later). */
	UFUNCTION(BlueprintCallable, Category = "Destruction")
	int32 ApplyAreaDamage(const FVector& WorldLocation, float RadiusM, float Damage);

	/**
	 * One step of a giant's foot: every building under (or overlapping) the foot takes partial damage and accumulates
	 * trample coverage; anything pushed above TrampleCollapseFraction collapses whole. Returns the number that died.
	 */
	UFUNCTION(BlueprintCallable, Category = "Destruction")
	int32 ApplyTrample(const FVector& FootLocation, float FootRadiusM, float CoveragePerStep, float Damage);

	/** Destroys one registered building outright (no damage, no cascade); false if invalid or already dead. */
	UFUNCTION(BlueprintCallable, Category = "Destruction")
	bool DestroyBuilding(int32 Index);

	/** Destroys up to Limit registered buildings (Limit <= 0: all), no cascade. Returns how many died. */
	UFUNCTION(BlueprintCallable, Category = "Destruction")
	int32 DestroyBand(int32 Limit);

	/** Restores every destroyed instance, clears chunks/debris and resets health + trample. */
	UFUNCTION(BlueprintCallable, Category = "Destruction")
	void RestoreAll();

	/** Logs the current statistics and writes the JSON report. */
	UFUNCTION(BlueprintCallable, Category = "Destruction")
	void WriteStats(const FString& Reason) const;

	UFUNCTION(BlueprintCallable, Category = "Destruction")
	int32 GetRegisteredCount() const { return Buildings.Num(); }

	UFUNCTION(BlueprintCallable, Category = "Destruction")
	int32 GetDestroyedCount() const;

	/** Health fraction of one building in [0, 1]; -1 if the index is invalid. */
	UFUNCTION(BlueprintCallable, Category = "Destruction")
	float GetHealthFraction(int32 Index) const;

	/** Trampled share of one building in [0, 1]; -1 if the index is invalid. */
	UFUNCTION(BlueprintCallable, Category = "Destruction")
	float GetTrampledFraction(int32 Index) const;

	/** World location of one registered building (zero if the index is invalid); used by the console commands. */
	UFUNCTION(BlueprintCallable, Category = "Destruction")
	FVector GetBuildingLocation(int32 Index) const;

private:
	struct FChunkPiece
	{
		UStaticMesh* Mesh = nullptr;
		FVector OffsetM = FVector::ZeroVector;
	};

	struct FChunkSet
	{
		TArray<FChunkPiece> Pieces;
	};

	struct FBuildingRecord
	{
		TWeakObjectPtr<UInstancedStaticMeshComponent> Component;
		int32 InstanceIndex = 0;
		FTransform WorldTransform = FTransform::Identity;
		FString ModuleName;
		float MaxHealth = 100.0f;
		float Health = 100.0f;
		float FootprintRadiusCm = 2000.0f;
		float Trampled = 0.0f;
		int32 DamageStage = 0;
		bool bDestroyed = false;
		bool bUsedChunks = false;
		TArray<int32> Neighbours;
	};

	struct FPhysicsChunk
	{
		TObjectPtr<UStaticMeshComponent> Component;
		UStaticMesh* Mesh = nullptr;
		float Age = 0.0f;
	};

	void LoadManifest();
	void RegisterBuildings();
	void RegisterActor(class AActor* BoardActor);
	void BuildSupportGraph();
	float BaseHealthFor(const FBuildingRecord& Record) const;
	int32 CountAliveNeighbours(int32 Index) const;

	UHierarchicalInstancedStaticMeshComponent* ChunkComponentFor(UStaticMesh* Mesh);
	void PlaceRubble(const FBuildingRecord& Record);
	void SpawnDebris(FBuildingRecord& Record, int32 Count);
	void HideInstance(FBuildingRecord& Record);
	void ShowInstance(const FBuildingRecord& Record);
	void CascadeFrom(int32 Index, int32 Depth);
	/** document/179: decal material + budget for local damage marks. */
	UPROPERTY() TObjectPtr<UMaterialInterface> ScorchDecalMaterial;
	int32 MaxDamageDecals = 64;
	int32 DecalsSpawned = 0;

	void UpdateDamageStage(FBuildingRecord& Record);
	void OnCollapsed(FBuildingRecord& Record);   // chunks (physics or static) + dust

	void SpawnChunkBodies(FBuildingRecord& Record);
	bool IsAudienceCameraActive() const;
	void SpawnDust(const FBuildingRecord& Record);
	void SpawnDustAt(const FVector& WorldLocation, float Scale);
	/** document/179: scorch / crack decal left on the ground where a building was hit or collapsed. */
	void SpawnScorchDecal(const FVector& WorldLocation, float RadiusCm);
	void UpdatePhysicsChunks(float DeltaSeconds);
	void EnsureGroundCollision();
	float CircleOverlapFraction(const FVector& FootLocation, float FootRadiusCm, const FBuildingRecord& Record) const;

	void RunAutoTest(float DeltaSeconds);
	void FireAutoTestHit(int32 HitIndex);
	void FireAutoTestTrample(int32 StepIndex);

	UPROPERTY()
	TObjectPtr<USceneComponent> SceneRoot;

	TArray<FBuildingRecord> Buildings;
	TMap<FString, FChunkSet> ChunkSets;
	TArray<UStaticMesh*> RubbleMeshes;
	TMap<UStaticMesh*, TObjectPtr<UHierarchicalInstancedStaticMeshComponent>> ChunkComponents;
	/** Chunk instances added so far, kept so RestoreAll can clear them. */
	TArray<TObjectPtr<UHierarchicalInstancedStaticMeshComponent>> ChunkHosts;

	UPROPERTY()
	TObjectPtr<UNiagaraSystem> DustSystem;
	UPROPERTY()
	TObjectPtr<UStaticMesh> GroundFloorMesh;
	TArray<FPhysicsChunk> PhysicsChunks;
	TArray<TObjectPtr<UStaticMeshComponent>> GroundFloors;
	mutable int32 DustSpawned = 0;
	mutable int32 DustSkipped = 0;
	mutable int32 PhysicsChunksSpawned = 0;
	mutable int32 PhysicsChunksFrozen = 0;
	mutable int32 TrampleSteps = 0;
	mutable int32 TrampleCollapses = 0;

	// Cascade / statistics bookkeeping
	mutable int32 CascadeEvents = 0;
	mutable int32 CascadeDeaths = 0;
	mutable int32 CascadeMaxDepthSeen = 0;
	int32 CascadeDeathsThisHit = 0;
	int32 CascadeEventsThisHit = 0;
	mutable int32 RootHits = 0;

	// Auto test state
	float AutoSeconds = 0.0f;
	bool bAutoDestroyed = false;
	int32 AutoHitsFired = 0;
	int32 AutoDestroyedCount = 0;
	double AutoDestroyMs = 0.0;
	TArray<float> AutoBeforeMs;
	TArray<float> AutoAfterMs;
	bool bAutoFinished = false;
	bool bAutoShot = false;
	FString AutoScreenshotPath;
};
