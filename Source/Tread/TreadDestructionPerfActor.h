#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "TreadDestructionPerfActor.generated.h"

/**
 * Physics stress probe for plan 126 (document/160): drops a burst of rigid bodies onto a temporary floor over the
 * middle 4x8 band of the board and records frame times per phase, so the "shatter spike" can be compared with the
 * render-only cost measured in Tools/destruction/destruction_trial.py.
 *
 * Spawned by ATreadM1GameMode when the command line has -TreadDestructionPerf:
 *
 *   UnrealEditor.exe Tread.uproject -game /Game/Tread/Maps/M3_Paris_Match -TreadSkipFrontEnd -TreadDestructionPerf
 *   (Tools/destruction/run_physics_trial.ps1 wraps that call and reads Saved/Reports/Destruction_Physics_Trial.json)
 *
 * Bodies are cubes, not the pre-cut chunks: the probe measures the physics side (body count, contacts, solver cost);
 * the render side was measured separately with the real chunk meshes.
 */
UCLASS()
class TREAD_API ATreadDestructionPerfActor : public AActor
{
	GENERATED_BODY()

public:
	ATreadDestructionPerfActor();
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	/** Total bodies dropped over the two bursts. */
	UPROPERTY(EditAnywhere, Category = "Destruction|Perf")
	int32 BodyCount = 96;

	/** Bodies dropped in the first burst; the rest lands one burst-length later. */
	UPROPERTY(EditAnywhere, Category = "Destruction|Perf")
	int32 FirstBurstBodies = 48;

	UPROPERTY(EditAnywhere, Category = "Destruction|Perf")
	float WarmupSeconds = 3.0f;

	UPROPERTY(EditAnywhere, Category = "Destruction|Perf")
	float BurstSeconds = 4.0f;

	UPROPERTY(EditAnywhere, Category = "Destruction|Perf")
	float SettleSeconds = 3.0f;

	/** Cube edge x/y and height in metres: debris scale for a 24 m Haussmann module. */
	UPROPERTY(EditAnywhere, Category = "Destruction|Perf")
	FVector BodySizeM = FVector(8.0f, 8.0f, 5.0f);

	/** One sampled frame; public so the report helpers can summarise it. */
	struct FSample
	{
		float FrameMs = 0.0f;
		float GameMs = 0.0f;
		float RenderMs = 0.0f;
		float GpuMs = 0.0f;
	};

private:
	enum class EPhase : uint8 { Warmup, Burst, Settle, Done };

	void SpawnFloor();
	void SpawnBodies(int32 Count, int32 FirstIndex);
	FVector SpotFor(int32 Index) const;
	void WriteReport();

	EPhase Phase = EPhase::Warmup;
	float PhaseSeconds = 0.0f;
	bool bSecondBurstDone = false;
	int32 Spawned = 0;
	TArray<FSample> WarmupSamples;
	TArray<FSample> BurstSamples;
	TArray<FSample> SettleSamples;
	TArray<TObjectPtr<UStaticMeshComponent>> BodyComponents;
};
