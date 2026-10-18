#include "TreadDestructionPerfActor.h"

#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/DateTime.h"
#include "RenderCore.h"
#include "RHI.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "TimerManager.h"

namespace
{
	constexpr float CellM = 200.0f;
	constexpr int32 GridX = 12;   // 12 columns over the middle 4 rows' width
	constexpr int32 GridY = 8;    // 8 rows over the board

	FRandomStream& Stream()
	{
		static FRandomStream Random(20261018);
		return Random;
	}

	struct FPhaseStats
	{
		int32 Frames = 0;
		float AvgMs = 0.0f;
		float WorstMs = 0.0f;
		float P95Ms = 0.0f;
		float AvgGameMs = 0.0f;
		float AvgRenderMs = 0.0f;
		float AvgGpuMs = 0.0f;
		int32 Over33Ms = 0;
		int32 Over50Ms = 0;
	};

	FPhaseStats Summarise(const TArray<ATreadDestructionPerfActor::FSample>& Samples)
	{
		FPhaseStats Stats;
		Stats.Frames = Samples.Num();
		if (Samples.Num() == 0)
		{
			return Stats;
		}
		TArray<float> Frames;
		Frames.Reserve(Samples.Num());
		for (const ATreadDestructionPerfActor::FSample& Sample : Samples)
		{
			Frames.Add(Sample.FrameMs);
			Stats.AvgMs += Sample.FrameMs;
			Stats.AvgGameMs += Sample.GameMs;
			Stats.AvgRenderMs += Sample.RenderMs;
			Stats.AvgGpuMs += Sample.GpuMs;
			Stats.WorstMs = FMath::Max(Stats.WorstMs, Sample.FrameMs);
			Stats.Over33Ms += Sample.FrameMs > 33.3f ? 1 : 0;
			Stats.Over50Ms += Sample.FrameMs > 50.0f ? 1 : 0;
		}
		const float Count = static_cast<float>(Samples.Num());
		Stats.AvgMs /= Count;
		Stats.AvgGameMs /= Count;
		Stats.AvgRenderMs /= Count;
		Stats.AvgGpuMs /= Count;
		Frames.Sort();
		Stats.P95Ms = Frames[FMath::Clamp(FMath::RoundToInt(0.95f * (Frames.Num() - 1)), 0, Frames.Num() - 1)];
		return Stats;
	}

	void WriteStats(const TSharedRef<FJsonObject>& Root, const TCHAR* Key, const FPhaseStats& Stats)
	{
		const TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
		Out->SetNumberField(TEXT("frames"), Stats.Frames);
		Out->SetNumberField(TEXT("avg_ms"), Stats.AvgMs);
		Out->SetNumberField(TEXT("avg_fps"), Stats.AvgMs > 0.0f ? 1000.0f / Stats.AvgMs : 0.0f);
		Out->SetNumberField(TEXT("p95_ms"), Stats.P95Ms);
		Out->SetNumberField(TEXT("worst_ms"), Stats.WorstMs);
		Out->SetNumberField(TEXT("avg_game_ms"), Stats.AvgGameMs);
		Out->SetNumberField(TEXT("avg_render_ms"), Stats.AvgRenderMs);
		Out->SetNumberField(TEXT("avg_gpu_ms"), Stats.AvgGpuMs);
		Out->SetNumberField(TEXT("frames_over_33ms"), Stats.Over33Ms);
		Out->SetNumberField(TEXT("frames_over_50ms"), Stats.Over50Ms);
		Root->SetObjectField(Key, Out);
	}
}

ATreadDestructionPerfActor::ATreadDestructionPerfActor()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostUpdateWork;
}

void ATreadDestructionPerfActor::BeginPlay()
{
	Super::BeginPlay();
	// Optional override so the runner can sweep the body count without a rebuild: -TreadDestructionPerfBodies=N
	int32 Requested = 0;
	if (FParse::Value(FCommandLine::Get(), TEXT("TreadDestructionPerfBodies="), Requested) && Requested > 0)
	{
		BodyCount = Requested;
		FirstBurstBodies = FMath::Max(1, Requested / 2);
	}
	SpawnFloor();
	UE_LOG(LogTemp, Display, TEXT("Tread destruction perf: %d bodies (%d first burst), warmup %.1fs burst %.1fs settle %.1fs"),
		BodyCount, FirstBurstBodies, WarmupSeconds, BurstSeconds, SettleSeconds);
}

FVector ATreadDestructionPerfActor::SpotFor(int32 Index) const
{
	// Uniform spread over the middle 4x8 band: world X is the board's row axis (rows 2..5 -> |X| <= 300 m),
	// world Y the column axis (8 columns -> |Y| <= 700 m). Spots sit inside the cells, clear of the ring buildings.
	const int32 Column = Index % GridX;
	const int32 Row = (Index / GridX) % GridY;
	const float X = FMath::Lerp(-260.0f, 260.0f, (Row + 0.5f) / GridY) * 100.0f;
	const float Y = FMath::Lerp(-660.0f, 660.0f, (Column + 0.5f) / GridX) * 100.0f;
	return FVector(X, Y, 3000.0f);
}

void ATreadDestructionPerfActor::SpawnFloor()
{
	UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
	if (!Cube)
	{
		UE_LOG(LogTemp, Error, TEXT("Tread destruction perf: /Engine/BasicShapes/Cube missing"));
		return;
	}
	UStaticMeshComponent* Floor = NewObject<UStaticMeshComponent>(this);
	Floor->SetStaticMesh(Cube);
	Floor->SetWorldLocation(FVector(0.0f, 0.0f, -50.0f));
	Floor->SetWorldScale3D(FVector(8.0f, 18.0f, 0.2f));  // 800 x 1800 x 20 m, enough for the whole band
	Floor->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	Floor->SetCollisionObjectType(ECC_WorldStatic);
	Floor->SetCollisionResponseToAllChannels(ECR_Block);
	Floor->SetMobility(EComponentMobility::Movable);
	Floor->SetVisibility(false);
	Floor->SetupAttachment(RootComponent);
	Floor->RegisterComponent();
	BodyComponents.Add(Floor);
}

void ATreadDestructionPerfActor::SpawnBodies(int32 Count, int32 FirstIndex)
{
	UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
	if (!Cube)
	{
		return;
	}
	const FVector Scale = BodySizeM;  // the engine cube is 100 cm, so scale in metres = size in metres
	for (int32 Offset = 0; Offset < Count; ++Offset)
	{
		const int32 Index = FirstIndex + Offset;
		UStaticMeshComponent* Body = NewObject<UStaticMeshComponent>(this);
		Body->SetStaticMesh(Cube);
		Body->SetWorldLocation(SpotFor(Index) + FVector(0.0f, 0.0f, Offset * 400.0f));
		Body->SetWorldRotation(FRotator(Stream().FRandRange(-20.0f, 20.0f), Stream().FRandRange(0.0f, 360.0f),
			Stream().FRandRange(-20.0f, 20.0f)));
		Body->SetWorldScale3D(Scale);
		Body->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
		Body->SetCollisionObjectType(ECC_PhysicsBody);
		Body->SetCollisionResponseToAllChannels(ECR_Block);
		Body->SetMobility(EComponentMobility::Movable);
		Body->SetSimulatePhysics(true);
		Body->SetPhysicsLinearVelocity(FVector(Stream().FRandRange(-600.0f, 600.0f), Stream().FRandRange(-600.0f, 600.0f),
			Stream().FRandRange(-400.0f, 100.0f)));
		Body->SetupAttachment(RootComponent);
		Body->RegisterComponent();
		Body->SetSimulatePhysics(true);
		BodyComponents.Add(Body);
		++Spawned;
	}
	UE_LOG(LogTemp, Display, TEXT("Tread destruction perf: burst spawned, %d bodies live"), Spawned);
}

void ATreadDestructionPerfActor::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	PhaseSeconds += DeltaSeconds;

	FSample Sample;
	Sample.FrameMs = DeltaSeconds * 1000.0f;
	Sample.GameMs = FPlatformTime::ToMilliseconds(GGameThreadTime);
	Sample.RenderMs = FPlatformTime::ToMilliseconds(GRenderThreadTime);
	Sample.GpuMs = FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles());

	switch (Phase)
	{
	case EPhase::Warmup:
		if (PhaseSeconds >= WarmupSeconds)
		{
			WarmupSamples.Empty();  // the warmup is not reported, it only lets shaders/Lumen settle
			Phase = EPhase::Burst;
			PhaseSeconds = 0.0f;
			SpawnBodies(FirstBurstBodies, 0);
		}
		break;
	case EPhase::Burst:
		BurstSamples.Add(Sample);
		if (!bSecondBurstDone && PhaseSeconds >= BurstSeconds * 0.5f)
		{
			bSecondBurstDone = true;
			SpawnBodies(BodyCount - FirstBurstBodies, FirstBurstBodies);
		}
		if (PhaseSeconds >= BurstSeconds)
		{
			Phase = EPhase::Settle;
			PhaseSeconds = 0.0f;
		}
		break;
	case EPhase::Settle:
		SettleSamples.Add(Sample);
		if (PhaseSeconds >= SettleSeconds)
		{
			Phase = EPhase::Done;
			WriteReport();
			UKismetSystemLibrary::QuitGame(this, nullptr, EQuitPreference::Quit, false);
			SetActorTickEnabled(false);
		}
		break;
	default:
		break;
	}
}

void ATreadDestructionPerfActor::WriteReport()
{
	const FPhaseStats Burst = Summarise(BurstSamples);
	const FPhaseStats Settle = Summarise(SettleSamples);
	// Sanity: bodies that reached the floor and are still awake tell "physics really ran" from "they fell through".
	int32 Landed = 0;
	int32 Awake = 0;
	for (const TObjectPtr<UStaticMeshComponent>& Body : BodyComponents)
	{
		if (!Body || !Body->IsSimulatingPhysics()) continue;
		if (Body->GetComponentLocation().Z < 200.0) ++Landed;
		if (Body->IsAnyRigidBodyAwake()) ++Awake;
	}
	const TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetStringField(TEXT("schema"), TEXT("Tread.Destruction.PhysicsTrial.v1"));
	Root->SetStringField(TEXT("date"), FDateTime::Now().ToString());
	Root->SetStringField(TEXT("map"), GetWorld() ? GetWorld()->GetMapName() : TEXT("unknown"));
	Root->SetNumberField(TEXT("bodies"), Spawned);
	Root->SetNumberField(TEXT("landed_bodies"), Landed);
	Root->SetNumberField(TEXT("awake_bodies"), Awake);
	Root->SetNumberField(TEXT("first_burst_bodies"), FirstBurstBodies);
	Root->SetNumberField(TEXT("body_size_m"), BodySizeM.X);
	Root->SetNumberField(TEXT("warmup_seconds"), WarmupSeconds);
	Root->SetNumberField(TEXT("burst_seconds"), BurstSeconds);
	Root->SetNumberField(TEXT("settle_seconds"), SettleSeconds);
	Root->SetStringField(TEXT("note"),
		TEXT("cubes, not the pre-cut chunks: this measures the physics side (bodies, contacts, solver). The render side "
			 "was measured separately with the real chunk meshes (Saved/Reports/Destruction_Trial.json)."));
	WriteStats(Root, TEXT("burst"), Burst);
	WriteStats(Root, TEXT("settle"), Settle);
	FString Output;
	const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Output);
	FJsonSerializer::Serialize(Root, Writer);
	const FString Path = FPaths::ProjectSavedDir() / TEXT("Reports/Destruction_Physics_Trial.json");
	FFileHelper::SaveStringToFile(Output, *Path);
	UE_LOG(LogTemp, Display, TEXT("Tread destruction perf report: %s (burst avg %.1f ms / worst %.1f ms / %d frames over 33 ms)"),
		*Path, Burst.AvgMs, Burst.WorstMs, Burst.Over33Ms);
}
