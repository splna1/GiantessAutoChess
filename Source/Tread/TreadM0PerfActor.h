#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "TreadM0PerfActor.generated.h"

UCLASS()
class TREAD_API ATreadM0PerfActor : public AActor
{
	GENERATED_BODY()

public:
	ATreadM0PerfActor();
	virtual void Tick(float DeltaSeconds) override;
	virtual void BeginPlay() override;

	UPROPERTY(EditAnywhere, Category = "M0 Performance")
	float WarmupSeconds = 3.0f;

	UPROPERTY(EditAnywhere, Category = "M0 Performance")
	float SampleSeconds = 20.0f;

private:
	void WriteReport();
	float ElapsedSeconds = 0.0f;
	TArray<float> FrameTimesMs;
	TArray<float> GameTimesMs;
	TArray<float> RenderTimesMs;
	TArray<float> GpuTimesMs;
	// document/181: per-frame draw-call / primitive counts and a slow-frame table, so a 1% low regression can be
	// attributed to the CPU, the GPU or a specific burst of geometry instead of only an average.
	TArray<int32> DrawCalls;
	TArray<int32> Primitives;
	TArray<uint64> FrameNumbers;
};
