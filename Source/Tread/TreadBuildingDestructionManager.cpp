#include "TreadBuildingDestructionManager.h"

#include "Components/DecalComponent.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/DecalActor.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Camera/PlayerCameraManager.h"
#include "GameFramework/Actor.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "NiagaraComponent.h"
#include "TreadM3BoardPresenter.h"
#include "NiagaraSystem.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "TimerManager.h"
#include "UnrealClient.h"

namespace
{
	constexpr float BandHalfXM = 300.0f;   // middle 4 rows of the 8x8 board: rows 2..5 -> |world X| <= 300 m
	constexpr float BandHalfYM = 700.0f;   // all 8 columns -> |world Y| <= 700 m
	constexpr float HideScale = 0.01f;

	const TCHAR* const BoardLabels[] = { TEXT("City_Board_Buildings"), TEXT("M3_Board_LibraryBlocks") };

	FString ManifestPath()
	{
		return FPaths::ProjectContentDir() / TEXT("Tread/Destruction/DestructionChunks.json");
	}

	bool ReadJson(const FString& Path, TSharedPtr<FJsonObject>& Out)
	{
		FString Text;
		if (!FFileHelper::LoadFileToString(Text, *Path))
		{
			return false;
		}
		const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Text);
		return FJsonSerializer::Deserialize(Reader, Out) && Out.IsValid();
	}

	struct FFramesStat
	{
		int32 Count = 0;
		float AvgMs = 0.0f;
		float WorstMs = 0.0f;
	};

	FFramesStat Summarise(const TArray<float>& Frames)
	{
		FFramesStat Stats;
		Stats.Count = Frames.Num();
		if (Frames.Num() == 0)
		{
			return Stats;
		}
		for (const float Ms : Frames)
		{
			Stats.AvgMs += Ms;
			Stats.WorstMs = FMath::Max(Stats.WorstMs, Ms);
		}
		Stats.AvgMs /= static_cast<float>(Frames.Num());
		return Stats;
	}
}

ATreadBuildingDestructionManager::ATreadBuildingDestructionManager()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PrePhysics;
	SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("SceneRoot"));
	SetRootComponent(SceneRoot);
}

void ATreadBuildingDestructionManager::BeginPlay()
{
	Super::BeginPlay();
	LoadManifest();
	RegisterBuildings();
	BuildSupportGraph();
	EnsureGroundCollision();

	// The dust system can be swapped without a rebuild: Content/Tread/Destruction/DestructionVFX.json
	// {"dust_system": "/Game/..."} wins over the property default (Tools/destruction/set_dust_system.py writes it).
	{
		TSharedPtr<FJsonObject> Vfx;
		const FString VfxPath = FPaths::ProjectContentDir() / TEXT("Tread/Destruction/DestructionVFX.json");
		FString Configured;
		if (ReadJson(VfxPath, Vfx) && Vfx->TryGetStringField(TEXT("dust_system"), Configured) && !Configured.IsEmpty())
		{
			DustSystemPath = Configured;
		}
	}
	DustSystem = LoadObject<UNiagaraSystem>(nullptr, *DustSystemPath);
#if WITH_EDITOR
	if (DustSystem)
	{
		// Editor / -game runs compile Niagara on demand; without this the first dust burst appears a second late.
		DustSystem->WaitForCompilationComplete();
	}
#endif
	UE_LOG(LogTemp, Display, TEXT("Tread destruction: %d buildings registered, %d chunk sets, %d rubble meshes, dust %s"),
		Buildings.Num(), ChunkSets.Num(), RubbleMeshes.Num(), DustSystem ? TEXT("loaded") : TEXT("MISSING"));
	if (Buildings.Num() > 0)
	{
		int32 MaxNeighbours = 0;
		int32 Isolated = 0;
		for (const FBuildingRecord& Record : Buildings)
		{
			MaxNeighbours = FMath::Max(MaxNeighbours, Record.Neighbours.Num());
			Isolated += Record.Neighbours.Num() == 0 ? 1 : 0;
		}
		UE_LOG(LogTemp, Display, TEXT("Tread destruction: support radius %.0f m, max neighbours %d, isolated %d"),
			SupportRadiusM, MaxNeighbours, Isolated);
	}

	if (bAutoTest || FParse::Param(FCommandLine::Get(), TEXT("TreadDestructionTest")))
	{
		bAutoTest = true;
		AutoScreenshotPath = FPaths::ProjectSavedDir() / TEXT("Screenshots/Destruction_Runtime.png");
		// Plain flags, not -Key=Value: Start-Process hands "-Key=Value" to the engine as tokens the map parser can
		// mistake for a map name (document/161 section 6).
		if (FParse::Param(FCommandLine::Get(), TEXT("TreadDestructionCascade")))
		{
			AutoTestMode = ETreadAutoTestMode::Cascade;
		}
		else if (FParse::Param(FCommandLine::Get(), TEXT("TreadDestructionTrample")))
		{
			AutoTestMode = ETreadAutoTestMode::Trample;
		}
		UE_LOG(LogTemp, Display, TEXT("Tread destruction: auto test armed (mode %d)"), static_cast<int32>(AutoTestMode));
	}
}

// ---------------------------------------------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------------------------------------------
void ATreadBuildingDestructionManager::LoadManifest()
{
	TSharedPtr<FJsonObject> Root;
	const FString Path = ManifestPath();
	if (!ReadJson(Path, Root))
	{
		UE_LOG(LogTemp, Warning, TEXT("Tread destruction: cannot read %s; every building will use rubble"), *Path);
		return;
	}

	const TArray<TSharedPtr<FJsonValue>>* Sets = nullptr;
	if (Root->TryGetArrayField(TEXT("sets"), Sets) && Sets)
	{
		for (const TSharedPtr<FJsonValue>& Value : *Sets)
		{
			const TSharedPtr<FJsonObject> SetObject = Value.IsValid() ? Value->AsObject() : nullptr;
			if (!SetObject.IsValid())
			{
				continue;
			}
			FString Module;
			SetObject->TryGetStringField(TEXT("module"), Module);
			const TArray<TSharedPtr<FJsonValue>>* Chunks = nullptr;
			if (Module.IsEmpty() || !SetObject->TryGetArrayField(TEXT("chunks"), Chunks) || !Chunks)
			{
				continue;
			}
			FChunkSet Set;
			for (const TSharedPtr<FJsonValue>& ChunkValue : *Chunks)
			{
				const TSharedPtr<FJsonObject> Chunk = ChunkValue.IsValid() ? ChunkValue->AsObject() : nullptr;
				if (!Chunk.IsValid())
				{
					continue;
				}
				FString Asset;
				Chunk->TryGetStringField(TEXT("asset"), Asset);
				const TArray<TSharedPtr<FJsonValue>>* Offset = nullptr;
				FChunkPiece Piece;
				Piece.Mesh = Asset.IsEmpty() ? nullptr : LoadObject<UStaticMesh>(nullptr, *Asset);
				if (!Piece.Mesh)
				{
					continue;
				}
				if (Chunk->TryGetArrayField(TEXT("offset_m"), Offset) && Offset && Offset->Num() >= 3)
				{
					Piece.OffsetM = FVector((*Offset)[0]->AsNumber(), (*Offset)[1]->AsNumber(), (*Offset)[2]->AsNumber());
				}
				Set.Pieces.Add(Piece);
			}
			if (Set.Pieces.Num() > 0)
			{
				ChunkSets.Add(Module, MoveTemp(Set));
			}
		}
	}

	const TArray<TSharedPtr<FJsonValue>>* Rubble = nullptr;
	if (Root->TryGetArrayField(TEXT("rubble_meshes"), Rubble) && Rubble)
	{
		for (const TSharedPtr<FJsonValue>& Value : *Rubble)
		{
			if (UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, *Value->AsString()))
			{
				RubbleMeshes.Add(Mesh);
			}
		}
	}
}

void ATreadBuildingDestructionManager::RegisterBuildings()
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	for (TActorIterator<AActor> It(World); It; ++It)
	{
#if WITH_EDITOR
		const FString Label = It->GetActorLabel();
#else
		// Editor labels are stripped from a packaged build; the board actors keep their object names instead.
		const FString Label = It->GetName();
#endif
		for (const TCHAR* Wanted : BoardLabels)
		{
			if (Label == Wanted || Label.StartsWith(Wanted))
			{
				RegisterActor(*It);
				break;
			}
		}
	}
}

void ATreadBuildingDestructionManager::RegisterActor(AActor* BoardActor)
{
	if (!BoardActor)
	{
		return;
	}
	TArray<UInstancedStaticMeshComponent*> Components;
	BoardActor->GetComponents<UInstancedStaticMeshComponent>(Components);
	for (UInstancedStaticMeshComponent* Component : Components)
	{
		UStaticMesh* Mesh = Component ? Component->GetStaticMesh() : nullptr;
		if (!Mesh)
		{
			continue;
		}
		for (int32 Index = 0; Index < Component->GetInstanceCount(); ++Index)
		{
			FTransform Transform;
			if (!Component->GetInstanceTransform(Index, Transform, /*bWorldSpace*/ true))
			{
				continue;
			}
			const FVector Location = Transform.GetLocation();
			if (FMath::Abs(Location.X) > BandHalfXM * 100.0f || FMath::Abs(Location.Y) > BandHalfYM * 100.0f)
			{
				continue;
			}
			FBuildingRecord Record;
			Record.Component = Component;
			Record.InstanceIndex = Index;
			Record.WorldTransform = Transform;
			Record.ModuleName = Mesh->GetName();
			Record.MaxHealth = BaseHealthFor(Record);
			Record.Health = Record.MaxHealth;
			const FBoxSphereBounds MeshBounds = Mesh->GetBounds();
			Record.FootprintRadiusCm = FMath::Max(MeshBounds.BoxExtent.X, MeshBounds.BoxExtent.Y);
			Buildings.Add(Record);
		}
	}
}

float ATreadBuildingDestructionManager::BaseHealthFor(const FBuildingRecord& Record) const
{
	float Base = 80.0f;
	if (Record.ModuleName.StartsWith(TEXT("SM_M3_")))
	{
		Base = HealthLibraryBlock;  // imported hero blocks are the tough ones
	}
	else if (Record.ModuleName.Contains(TEXT("Burnt")))
	{
		Base = HealthBurntModule;
	}
	else if (Record.ModuleName.StartsWith(TEXT("SM_Hsm_L")))
	{
		Base = HealthLargeModule;
	}
	else if (Record.ModuleName.StartsWith(TEXT("SM_Hsm_Infill")))
	{
		Base = HealthInfillModule;
	}
	else if (Record.ModuleName.Contains(TEXT("Ruin")))
	{
		Base = HealthBurntModule * 0.5f;
	}

	float ExtentM = ReferenceFootprintM;
	if (const UInstancedStaticMeshComponent* Component = Record.Component.Get())
	{
		if (const UStaticMesh* Mesh = Component->GetStaticMesh())
		{
			const FBoxSphereBounds Bounds = Mesh->GetBounds();
			ExtentM = FMath::Max(Bounds.BoxExtent.X, Bounds.BoxExtent.Y) / 50.0f;  // cm -> m diameter
		}
	}
	const float Factor = FMath::Clamp(ExtentM / FMath::Max(ReferenceFootprintM, 1.0f), 0.5f, 2.0f);
	return Base * Factor;
}

void ATreadBuildingDestructionManager::BuildSupportGraph()
{
	const float RadiusCm = SupportRadiusM * 100.0f;
	const float RadiusSq = RadiusCm * RadiusCm;
	for (int32 A = 0; A < Buildings.Num(); ++A)
	{
		for (int32 B = A + 1; B < Buildings.Num(); ++B)
		{
			if (FVector::DistSquared2D(Buildings[A].WorldTransform.GetLocation(), Buildings[B].WorldTransform.GetLocation()) > RadiusSq)
			{
				continue;
			}
			Buildings[A].Neighbours.Add(B);
			Buildings[B].Neighbours.Add(A);
		}
	}
}

int32 ATreadBuildingDestructionManager::CountAliveNeighbours(int32 Index) const
{
	if (!Buildings.IsValidIndex(Index))
	{
		return 0;
	}
	int32 Alive = 0;
	for (const int32 Neighbour : Buildings[Index].Neighbours)
	{
		if (Buildings.IsValidIndex(Neighbour) && !Buildings[Neighbour].bDestroyed)
		{
			++Alive;
		}
	}
	return Alive;
}

// ---------------------------------------------------------------------------------------------------------------
// Chunks, debris, dust
// ---------------------------------------------------------------------------------------------------------------
UHierarchicalInstancedStaticMeshComponent* ATreadBuildingDestructionManager::ChunkComponentFor(UStaticMesh* Mesh)
{
	if (!Mesh)
	{
		return nullptr;
	}
	if (TObjectPtr<UHierarchicalInstancedStaticMeshComponent>* Existing = ChunkComponents.Find(Mesh))
	{
		return *Existing;
	}
	UHierarchicalInstancedStaticMeshComponent* Component = NewObject<UHierarchicalInstancedStaticMeshComponent>(this);
	Component->SetStaticMesh(Mesh);
	Component->SetMobility(EComponentMobility::Movable);
	Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Component->SetCastShadow(true);
	Component->bCastDynamicShadow = true;
	Component->SetGenerateOverlapEvents(false);
	Component->SetupAttachment(SceneRoot);
	Component->RegisterComponent();
	ChunkComponents.Add(Mesh, Component);
	ChunkHosts.Add(Component);
	return Component;
}

void ATreadBuildingDestructionManager::PlaceRubble(const FBuildingRecord& Record)
{
	if (RubbleMeshes.Num() == 0)
	{
		return;
	}
	UStaticMesh* Rubble = RubbleMeshes[Record.InstanceIndex % RubbleMeshes.Num()];
	UHierarchicalInstancedStaticMeshComponent* Host = ChunkComponentFor(Rubble);
	if (!Host)
	{
		return;
	}
	float Scale = 2.0f;
	const FBoxSphereBounds RubbleBounds = Rubble->GetBounds();
	const float Have = FMath::Max(RubbleBounds.BoxExtent.X, RubbleBounds.BoxExtent.Y);
	if (Have > 1.0f)
	{
		// Keep the ruin readable as a collapsed shell: modest scale and upright. Squashing it to 35% Z made the
		// library blocks read as a black plate lying at an angle (owner feedback, document/163).
		Scale = FMath::Clamp(Record.FootprintRadiusCm / Have, 1.2f, 2.4f);
	}
	FTransform Placement = Record.WorldTransform;
	FVector Scale3D = Placement.GetScale3D() * Scale;
	Scale3D.Z *= 0.8f;
	Placement.SetScale3D(Scale3D);
	Placement.AddToTranslation(FVector(0.0f, 0.0f, -150.0f));
	Host->AddInstance(Placement, /*bWorldSpace*/ true);
}

void ATreadBuildingDestructionManager::SpawnDebris(FBuildingRecord& Record, int32 Count)
{
	const FChunkSet* Set = ChunkSets.Find(Record.ModuleName);
	if (!Set || Set->Pieces.Num() == 0 || Count <= 0)
	{
		return;
	}
	FRandomStream Rnd(Record.InstanceIndex * 104729 + Record.DamageStage * 31 + 7);
	for (int32 Piece = 0; Piece < Count; ++Piece)
	{
		const FChunkPiece& Chosen = Set->Pieces[Rnd.RandRange(0, Set->Pieces.Num() - 1)];
		UHierarchicalInstancedStaticMeshComponent* Host = ChunkComponentFor(Chosen.Mesh);
		if (!Host)
		{
			continue;
		}
		const FVector Offset(Rnd.FRandRange(-2500.0f, 2500.0f), Rnd.FRandRange(-2500.0f, 2500.0f), 0.0f);
		const FTransform Local(FRotator(Rnd.FRandRange(-8.0f, 8.0f), Rnd.FRandRange(0.0f, 360.0f),
			Rnd.FRandRange(-8.0f, 8.0f)), Offset, FVector(1.0f, 1.0f, 0.55f));
		FTransform Placement = Local * Record.WorldTransform;
		Placement.AddToTranslation(FVector(0.0f, 0.0f, -Rnd.FRandRange(50.0f, 150.0f)));
		Host->AddInstance(Placement, /*bWorldSpace*/ true);
	}
}

void ATreadBuildingDestructionManager::HideInstance(FBuildingRecord& Record)
{
	UInstancedStaticMeshComponent* Component = Record.Component.Get();
	if (!Component)
	{
		return;
	}
	FTransform Hidden = Record.WorldTransform;
	Hidden.SetScale3D(Hidden.GetScale3D() * HideScale);
	Component->UpdateInstanceTransform(Record.InstanceIndex, Hidden, /*bWorldSpace*/ true,
		/*bMarkRenderStateDirty*/ true, /*bTeleport*/ true);
}

void ATreadBuildingDestructionManager::ShowInstance(const FBuildingRecord& Record)
{
	if (UInstancedStaticMeshComponent* Component = Record.Component.Get())
	{
		Component->UpdateInstanceTransform(Record.InstanceIndex, Record.WorldTransform, /*bWorldSpace*/ true,
			/*bMarkRenderStateDirty*/ true, /*bTeleport*/ true);
	}
}

void ATreadBuildingDestructionManager::EnsureGroundCollision()
{
	// Chunks are rigid bodies now, so they need a floor. The board's plaza is a Nanite mesh with no collision in places;
	// if a downward trace over the band does not hit, drop an invisible collision slab under the band.
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	const FVector Probes[] = { FVector(0.0f, 0.0f, 5000.0f), FVector(-20000.0f, 0.0f, 5000.0f),
		FVector(20000.0f, 40000.0f, 5000.0f), FVector(0.0f, -40000.0f, 5000.0f) };
	int32 Hits = 0;
	for (const FVector& Start : Probes)
	{
		FHitResult Hit;
		FCollisionQueryParams Params(SCENE_QUERY_STAT(TreadGroundProbe), false, this);
		if (World->LineTraceSingleByChannel(Hit, Start, Start - FVector(0.0f, 0.0f, 10000.0f), ECC_WorldStatic, Params))
		{
			++Hits;
		}
	}
	if (Hits == UE_ARRAY_COUNT(Probes))
	{
		UE_LOG(LogTemp, Display, TEXT("Tread destruction: ground collision present under the band"));
		return;
	}

	GroundFloorMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
	if (!GroundFloorMesh)
	{
		UE_LOG(LogTemp, Warning, TEXT("Tread destruction: no ground collision and no cube to build a floor from"));
		return;
	}
	UStaticMeshComponent* Floor = NewObject<UStaticMeshComponent>(this);
	Floor->SetStaticMesh(GroundFloorMesh);
	Floor->SetWorldLocation(FVector(0.0f, 0.0f, -30.0f));
	Floor->SetWorldScale3D(FVector(8.0f, 18.0f, 0.6f));  // 800 x 1800 x 60 m under the whole band
	Floor->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	Floor->SetCollisionObjectType(ECC_WorldStatic);
	Floor->SetCollisionResponseToAllChannels(ECR_Block);
	Floor->SetMobility(EComponentMobility::Movable);
	Floor->SetVisibility(false);
	Floor->SetupAttachment(SceneRoot);
	Floor->RegisterComponent();
	GroundFloors.Add(Floor);
	UE_LOG(LogTemp, Display, TEXT("Tread destruction: ground collision missing (%d/%d probes) - added an invisible floor"),
		Hits, static_cast<int32>(UE_ARRAY_COUNT(Probes)));
}

void ATreadBuildingDestructionManager::SpawnChunkBodies(FBuildingRecord& Record)
{
	const FChunkSet* Set = ChunkSets.Find(Record.ModuleName);
	if (!Set || Set->Pieces.Num() == 0)
	{
		PlaceRubble(Record);
		return;
	}
	FRandomStream Rnd(Record.InstanceIndex * 7919 + 13);
	const int32 Count = FMath::Min3(Set->Pieces.Num(), MaxChunksPerBuilding, FMath::Max(1, MaxPhysicsChunksPerBuilding));
	const FVector Centre = Record.WorldTransform.GetLocation();
	// document/179: stack by floor - the sink amount grows with the piece's height inside the building instead of
	// the old flat 45%, so lower floors keep their volume and the top folds down furthest.
	float MinZ = MAX_flt;
	float MaxZ = -MAX_flt;
	for (const FChunkPiece& Piece : Set->Pieces)
	{
		MinZ = FMath::Min(MinZ, Piece.OffsetM.Z);
		MaxZ = FMath::Max(MaxZ, Piece.OffsetM.Z);
	}
	const float HeightZ = FMath::Max(MaxZ - MinZ, 1.0f);
	int32 Spawned = 0;
	for (int32 PieceIndex = 0; PieceIndex < Count; ++PieceIndex)
	{
		const FChunkPiece& Piece = Set->Pieces[PieceIndex];
		if (!Piece.Mesh || PhysicsChunks.Num() >= MaxPhysicsBodies)
		{
			continue;
		}
		UStaticMeshComponent* Body = NewObject<UStaticMeshComponent>(this);
		Body->SetStaticMesh(Piece.Mesh);
		Body->SetMobility(EComponentMobility::Movable);
		Body->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
		Body->SetCollisionProfileName(TEXT("PhysicsActor"));
		Body->SetCastShadow(true);
		Body->SetupAttachment(SceneRoot);

		// Pieces keep their place in the building: the upper half folds down onto the base and leans out a little,
		// instead of being thrown off at a random yaw (owner feedback: "just randomly rotated debris", document/163).
		const bool bUpper = Piece.OffsetM.Z > 0.0f;
		FVector OffsetCm = Piece.OffsetM * 100.0f;
		// Per-floor sink: base pieces stay put, the top folds down most (linear between 15% and 65% of height).
		const float Norm = FMath::Clamp((Piece.OffsetM.Z - MinZ) / HeightZ, 0.0f, 1.0f);
		const float SinkFraction = FMath::Lerp(0.15f, 0.65f, Norm);
		OffsetCm.Z -= (Piece.OffsetM.Z - MinZ) * 100.0f * SinkFraction;
		if (bUpper)
		{
			const FVector Out = FVector(Piece.OffsetM.X, Piece.OffsetM.Y, 0.0f).GetSafeNormal();
			OffsetCm += Out * Rnd.FRandRange(150.0f, 600.0f);
		}
		const FTransform Local(FRotator(Rnd.FRandRange(-2.0f, 2.0f), Rnd.FRandRange(-3.0f, 3.0f), Rnd.FRandRange(-2.0f, 2.0f)),
			OffsetCm, FVector(0.62f, 0.62f, bUpper ? 0.55f : 0.62f));
		Body->SetWorldTransform(Local * Record.WorldTransform);
		Body->RegisterComponent();
		Body->SetSimulatePhysics(true);

		FVector Out = (Body->GetComponentLocation() - Centre).GetSafeNormal2D();
		if (Out.IsNearlyZero())
		{
			Out = FVector(Rnd.FRandRange(-1.0f, 1.0f), Rnd.FRandRange(-1.0f, 1.0f), 0.0f).GetSafeNormal();
		}
		const float Mass = FMath::Max(Body->GetMass(), 1.0f);
		const FVector Impulse = (Out * ChunkImpulseScale + FVector(0.0f, 0.0f, ChunkImpulseScale * 0.25f)) * Mass;
		Body->AddImpulse(Impulse, NAME_None, /*bVelChange*/ false);

		FPhysicsChunk Chunk;
		Chunk.Component = Body;
		Chunk.Mesh = Piece.Mesh;
		Chunk.Age = 0.0f;
		PhysicsChunks.Add(Chunk);
		++PhysicsChunksSpawned;
		++Spawned;
	}
	if (Spawned == 0)
	{
		PlaceRubble(Record);  // body budget spent or the mesh cannot simulate: keep the cheap swap
	}
}

bool ATreadBuildingDestructionManager::IsAudienceCameraActive() const
{
	if (const UWorld* World = GetWorld())
	{
		for (TActorIterator<ATreadM3BoardPresenter> It(const_cast<UWorld*>(World)); It; ++It)
		{
			return It->IsAudienceCamera();
		}
	}
	return false;
}

void ATreadBuildingDestructionManager::SpawnDust(const FBuildingRecord& Record)
{
	if (bDustOnAudienceOnly && !IsAudienceCameraActive())
	{
		++DustSkipped;  // board camera: 1.7 km away, the dust would be a few pixels of haze
		return;
	}
	// One puff at the centre plus one at the footprint edge: at board distance a single small system reads as nothing.
	// document/179: 1.5x larger so the audience / kill camera can read the plume at 1-2 km.
	const float Scale = FMath::Clamp(Record.FootprintRadiusCm / FMath::Max(DustSourceRadiusCm, 10.0f), 5.0f, 150.0f) * 1.5f;
	SpawnDustAt(Record.WorldTransform.GetLocation() + FVector(0.0f, 0.0f, 200.0f), Scale);
	const float Radius = FMath::Clamp(Record.FootprintRadiusCm * 0.5f, 500.0f, 6000.0f);
	const float Angle = FMath::FRandRange(0.0f, 2.0f * PI);
	SpawnDustAt(Record.WorldTransform.GetLocation() +
		FVector(FMath::Cos(Angle) * Radius, FMath::Sin(Angle) * Radius, 200.0f), Scale * 0.8f);
	SpawnScorchDecal(Record.WorldTransform.GetLocation(), FMath::Clamp(Record.FootprintRadiusCm * 0.7f, 600.0f, 4500.0f));
}

void ATreadBuildingDestructionManager::SpawnScorchDecal(const FVector& WorldLocation, float RadiusCm)
{
	if (DecalsSpawned >= MaxDamageDecals) return;
	UWorld* World = GetWorld();
	if (!World) return;
	if (!ScorchDecalMaterial)
	{
		ScorchDecalMaterial = LoadObject<UMaterialInterface>(nullptr,
			TEXT("/Game/Tread/City/Paris/Materials/M_Decal_Scorch.M_Decal_Scorch"));
	}
	if (!ScorchDecalMaterial) return;
	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	ADecalActor* Decal = World->SpawnActor<ADecalActor>(WorldLocation, FRotator(-90.0f, 0.0f, 0.0f), Params);
	if (!Decal) return;
	Decal->SetDecalMaterial(ScorchDecalMaterial);
	if (UDecalComponent* Component = Decal->GetDecal())
	{
		const float R = FMath::Max(RadiusCm, 100.0f);
		Component->DecalSize = FVector(R * 0.4f, R, R);
		Component->SetFadeOut(8.0f, 2.0f, false);
	}
	Decal->SetLifeSpan(60.0f);
	++DecalsSpawned;
}

void ATreadBuildingDestructionManager::SpawnDustAt(const FVector& WorldLocation, float Scale)
{
	if (!DustSystem)
	{
		return;
	}
	UNiagaraComponent* Effect = NewObject<UNiagaraComponent>(this);
	Effect->SetAsset(DustSystem);
	Effect->SetupAttachment(SceneRoot);
	Effect->SetMobility(EComponentMobility::Movable);
	Effect->RegisterComponent();
	Effect->SetWorldLocation(WorldLocation);
	Effect->SetWorldScale3D(FVector(Scale));
	Effect->SetAllowScalability(false);  // the effect type's distance culling would drop it at board distance
	Effect->Activate(/*bReset*/ true);
	++DustSpawned;
	if (DustSpawned <= 3)
	{
		const FBoxSphereBounds Bounds(Effect->Bounds.GetBox(), Effect->Bounds.GetSphere());
		UE_LOG(LogTemp, Display, TEXT("Tread dust: active=%d scale=%.1f bounds=%.0f cm at (%.0f, %.0f) asset=%s"),
			Effect->IsActive() ? 1 : 0, Scale, Bounds.SphereRadius, WorldLocation.X / 100.0f, WorldLocation.Y / 100.0f,
			*DustSystem->GetName());
	}

	FTimerHandle Handle;
	GetWorldTimerManager().SetTimer(Handle, FTimerDelegate::CreateWeakLambda(this, [this, Effect]()
	{
		if (IsValid(Effect))
		{
			Effect->Deactivate();
			Effect->DestroyComponent();
		}
	}), FMath::Max(0.2f, DustLifetimeSeconds), false);


}

void ATreadBuildingDestructionManager::UpdatePhysicsChunks(float DeltaSeconds)
{
	for (int32 Index = PhysicsChunks.Num() - 1; Index >= 0; --Index)
	{
		FPhysicsChunk& Chunk = PhysicsChunks[Index];
		UStaticMeshComponent* Body = Chunk.Component.Get();
		if (!Body)
		{
			PhysicsChunks.RemoveAtSwap(Index, EAllowShrinking::No);
			continue;
		}
		Chunk.Age += DeltaSeconds;
		const bool bSettled = Chunk.Age >= PhysicsSettleSeconds || Body->GetComponentLocation().Z < -2000.0f;
		if (!bSettled)
		{
			continue;
		}
		// Freeze: bake the resting pose into the instanced mesh that carries the debris from now on.
		const FTransform Frozen = Body->GetComponentTransform();
		if (UHierarchicalInstancedStaticMeshComponent* Host = ChunkComponentFor(Chunk.Mesh))
		{
			Host->AddInstance(Frozen, /*bWorldSpace*/ true);
			++PhysicsChunksFrozen;
		}
		Body->SetSimulatePhysics(false);
		Body->DestroyComponent();
		PhysicsChunks.RemoveAtSwap(Index, EAllowShrinking::No);
	}
}

void ATreadBuildingDestructionManager::OnCollapsed(FBuildingRecord& Record)
{
	if (bPhysicsChunks && PhysicsChunks.Num() < MaxPhysicsBodies)
	{
		SpawnChunkBodies(Record);
	}
	else
	{
		const FChunkSet* Set = ChunkSets.Find(Record.ModuleName);
		if (Set && Set->Pieces.Num() > 0)
		{
			Record.bUsedChunks = true;
			FRandomStream Jitter(Record.InstanceIndex * 7919 + 13);
			const int32 Count = FMath::Min(Set->Pieces.Num(), MaxChunksPerBuilding);
			for (int32 PieceIndex = 0; PieceIndex < Count; ++PieceIndex)
			{
				const FChunkPiece& Piece = Set->Pieces[PieceIndex];
				UHierarchicalInstancedStaticMeshComponent* Host = ChunkComponentFor(Piece.Mesh);
				if (!Host)
				{
					continue;
				}
				const bool bUpperPiece = Piece.OffsetM.Z > 0.0f;
				FVector PieceOffset = Piece.OffsetM * 100.0f;
				float PieceSquash = 1.0f;
				if (bUpperPiece)
				{
					const FVector Out = FVector(Piece.OffsetM.X, Piece.OffsetM.Y, 0.0f).GetSafeNormal();
					PieceOffset.Z -= FMath::Abs(Piece.OffsetM.Z) * 45.0f;
					PieceOffset += Out * Jitter.FRandRange(150.0f, 600.0f);
					PieceSquash = 0.9f;
				}
				const FTransform Local(FRotator(0.0f, Jitter.FRandRange(-ChunkYawJitterDeg, ChunkYawJitterDeg), 0.0f),
					PieceOffset, FVector(0.62f, 0.62f, PieceSquash * 0.62f));
				FTransform Placement = Local * Record.WorldTransform;
				Placement.AddToTranslation(FVector(0.0f, 0.0f, -60.0f * Jitter.FRandRange(0.3f, 1.0f)));
				Host->AddInstance(Placement, /*bWorldSpace*/ true);
			}
		}
		else
		{
			PlaceRubble(Record);
		}
	}
	SpawnDust(Record);
}

// ---------------------------------------------------------------------------------------------------------------
// Damage, trample, cascade
// ---------------------------------------------------------------------------------------------------------------
void ATreadBuildingDestructionManager::UpdateDamageStage(FBuildingRecord& Record)
{
	if (Record.bDestroyed || Record.MaxHealth <= 0.0f)
	{
		return;
	}
	const float Fraction = Record.Health / Record.MaxHealth;
	int32 Stage = 0;
	if (Fraction <= DamageStageTwoFraction)
	{
		Stage = 2;
	}
	else if (Fraction <= DamageStageOneFraction)
	{
		Stage = 1;
	}
	if (Stage <= Record.DamageStage)
	{
		return;
	}
	const int32 Added = Stage - Record.DamageStage;
	Record.DamageStage = Stage;
	SpawnDebris(Record, Added + 1);
}

float ATreadBuildingDestructionManager::ApplyDamageTo(int32 Index, float Damage, int32 Depth)
{
	if (!Buildings.IsValidIndex(Index) || Damage <= 0.0f)
	{
		return 0.0f;
	}
	FBuildingRecord& Record = Buildings[Index];
	if (Record.bDestroyed)
	{
		return 0.0f;
	}
	if (Record.Health <= 0.0f)
	{
		if (DestroyBuilding(Index))
		{
			CascadeMaxDepthSeen = FMath::Max(CascadeMaxDepthSeen, Depth);
			CascadeFrom(Index, Depth + 1);
		}
		return 0.0f;
	}
	const float Applied = FMath::Max(0.0f, FMath::Min(Damage, Record.Health));
	Record.Health -= Applied;
	UpdateDamageStage(Record);
	if (Record.Health <= 0.0f && DestroyBuilding(Index))
	{
		CascadeMaxDepthSeen = FMath::Max(CascadeMaxDepthSeen, Depth);
		CascadeFrom(Index, Depth + 1);
	}
	return Applied;
}

void ATreadBuildingDestructionManager::CascadeFrom(int32 Index, int32 Depth)
{
	if (!bLoadBearingCascade || Depth > CascadeMaxDepth || !Buildings.IsValidIndex(Index))
	{
		return;
	}
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	const TArray<int32> Neighbours = Buildings[Index].Neighbours;  // copy: a cascade can re-enter this function
	for (const int32 Neighbour : Neighbours)
	{
		if (CascadeDeathsThisHit >= FMath::Max(1, CascadeMaxBuildings) ||
			CascadeEventsThisHit >= FMath::Max(1, CascadeMaxEventsPerHit) ||
			!Buildings.IsValidIndex(Neighbour) || Buildings[Neighbour].bDestroyed)
		{
			continue;
		}
		// Load-bearing rule: a building stays up while it keeps SupportRequirementFraction of its original supports.
		// Below that it folds, and the further below, the harder - which is what makes a block collapse in a chain.
		const int32 OriginalSupports = Buildings[Neighbour].Neighbours.Num();
		if (OriginalSupports <= 0)
		{
			continue;
		}
		const int32 RequiredSupports = FMath::Max(1, FMath::CeilToInt(OriginalSupports * SupportRequirementFraction));
		const int32 AliveSupports = CountAliveNeighbours(Neighbour);
		if (AliveSupports >= RequiredSupports)
		{
			continue;  // still braced
		}
		const float Deficit = (RequiredSupports - AliveSupports) / static_cast<float>(RequiredSupports);
		const float Damage = Buildings[Neighbour].MaxHealth * Deficit * CascadeDeficitScale;
		++CascadeEvents;
		++CascadeEventsThisHit;
		const float Delay = CascadeDelaySeconds * FMath::FRandRange(0.7f, 1.3f);
		FTimerHandle Handle;
		const FTimerDelegate Delegate = FTimerDelegate::CreateWeakLambda(this, [this, Neighbour, Damage, Depth]()
		{
			if (Buildings.IsValidIndex(Neighbour) && !Buildings[Neighbour].bDestroyed)
			{
				if (ApplyDamageTo(Neighbour, Damage, Depth) > 0.0f && Buildings[Neighbour].bDestroyed)
				{
					++CascadeDeaths;
					++CascadeDeathsThisHit;
				}
			}
		});
		World->GetTimerManager().SetTimer(Handle, Delegate, FMath::Max(0.05f, Delay), false);
	}
}

float ATreadBuildingDestructionManager::CircleOverlapFraction(const FVector& FootLocation, float FootRadiusCm,
	const FBuildingRecord& Record) const
{
	// How much of the building's roof footprint the foot circle covers: circle-vs-circle intersection area.
	const FVector Delta = Record.WorldTransform.GetLocation() - FootLocation;
	const float Distance = FVector2D(Delta.X, Delta.Y).Size();
	const float R = FMath::Max(FootRadiusCm, 1.0f);
	const float r = FMath::Max(Record.FootprintRadiusCm, 1.0f);
	if (Distance >= R + r)
	{
		return 0.0f;
	}
	const float BuildingArea = PI * r * r;
	if (Distance <= FMath::Abs(R - r))
	{
		const float Smaller = FMath::Min(R, r);
		return FMath::Clamp(PI * Smaller * Smaller / BuildingArea, 0.0f, 1.0f);
	}
	const float D2 = Distance * Distance;
	const float R2 = R * R;
	const float r2 = r * r;
	const float Alpha = FMath::Acos(FMath::Clamp((D2 + r2 - R2) / (2.0f * Distance * r), -1.0f, 1.0f));
	const float Beta = FMath::Acos(FMath::Clamp((D2 + R2 - r2) / (2.0f * Distance * R), -1.0f, 1.0f));
	const float Height = 0.5f * FMath::Sqrt(FMath::Max(0.0f,
		(-Distance + r + R) * (Distance + r - R) * (Distance - r + R) * (Distance + r + R)));
	const float Overlap = r2 * Alpha + R2 * Beta - Height;
	return FMath::Clamp(Overlap / BuildingArea, 0.0f, 1.0f);
}

int32 ATreadBuildingDestructionManager::ApplyTrample(const FVector& FootLocation, float FootRadiusM, float CoveragePerStep,
	float Damage)
{
	const float FootRadiusCm = FMath::Max(FootRadiusM, 1.0f) * 100.0f;
	const float Coverage = FMath::Max(CoveragePerStep, 0.0f);
	++TrampleSteps;
	CascadeDeathsThisHit = 0;
	CascadeEventsThisHit = 0;
	int32 Killed = 0;
	for (int32 Index = 0; Index < Buildings.Num(); ++Index)
	{
		FBuildingRecord& Record = Buildings[Index];
		if (Record.bDestroyed)
		{
			continue;
		}
		const float Cover = CircleOverlapFraction(FootLocation, FootRadiusCm, Record);
		if (Cover <= 0.001f)
		{
			continue;
		}
		Record.Trampled = FMath::Min(1.0f, Record.Trampled + Cover * Coverage);
		if (Damage > 0.0f)
		{
			ApplyDamageTo(Index, Damage * Cover, 0);  // partial destruction under the foot
		}
		if (!Record.bDestroyed && Record.Trampled >= TrampleCollapseFraction)
		{
			if (DestroyBuilding(Index))
			{
				++Killed;
				++TrampleCollapses;
				CascadeFrom(Index, 1);
			}
		}
	}
	// document/179: leave a scorch mark under the foot (every third step, budgeted).
	if (TrampleSteps % 3 == 0)
	{
		SpawnScorchDecal(FootLocation, FootRadiusCm * 0.85f);
	}
	UE_LOG(LogTemp, Display, TEXT("Tread destruction: trample at (%.0f, %.0f) r=%.0f cover=%.2f -> %d collapsed "
		"(%d collapses so far)"), FootLocation.X / 100.0f, FootLocation.Y / 100.0f, FootRadiusM, Coverage,
		Killed, TrampleCollapses);
	return Killed;
}

// ---------------------------------------------------------------------------------------------------------------
// Collapse entry points
// ---------------------------------------------------------------------------------------------------------------
bool ATreadBuildingDestructionManager::DestroyBuilding(int32 Index)
{
	if (!Buildings.IsValidIndex(Index))
	{
		return false;
	}
	FBuildingRecord& Record = Buildings[Index];
	if (Record.bDestroyed)
	{
		return false;
	}
	if (MaxActiveBuildings > 0 && GetDestroyedCount() >= MaxActiveBuildings)
	{
		return false;
	}

	HideInstance(Record);
	Record.bDestroyed = true;
	Record.Health = 0.0f;
	OnCollapsed(Record);
	return true;
}

int32 ATreadBuildingDestructionManager::DestroyBand(int32 Limit)
{
	int32 Destroyed = 0;
	for (int32 Index = 0; Index < Buildings.Num(); ++Index)
	{
		if (Limit > 0 && Destroyed >= Limit)
		{
			break;
		}
		if (DestroyBuilding(Index))
		{
			++Destroyed;
		}
	}
	UE_LOG(LogTemp, Display, TEXT("Tread destruction: destroyed %d buildings (%d total, %d chunk hosts)"),
		Destroyed, GetDestroyedCount(), ChunkHosts.Num());
	return Destroyed;
}

int32 ATreadBuildingDestructionManager::ApplyAreaDamage(const FVector& WorldLocation, float RadiusM, float Damage)
{
	const float RadiusCm = RadiusM * 100.0f;
	const float RadiusSq = RadiusCm * RadiusCm;
	++RootHits;
	CascadeDeathsThisHit = 0;   // one hit may only cascade this far
	CascadeEventsThisHit = 0;
	int32 Killed = 0;
	for (int32 Index = 0; Index < Buildings.Num(); ++Index)
	{
		FBuildingRecord& Record = Buildings[Index];
		if (Record.bDestroyed)
		{
			continue;
		}
		if (FVector::DistSquared(Record.WorldTransform.GetLocation(), WorldLocation) > RadiusSq)
		{
			continue;
		}
		ApplyDamageTo(Index, Damage, 0);
		Killed += Record.bDestroyed ? 1 : 0;
	}
	UE_LOG(LogTemp, Display, TEXT("Tread destruction: hit at (%.0f, %.0f) r=%.0f dmg=%.0f -> %d destroyed outright, "
		"%d cascade events / %d cascade deaths so far"), WorldLocation.X / 100.0f, WorldLocation.Y / 100.0f, RadiusM,
		Damage, Killed, CascadeEventsThisHit, CascadeDeathsThisHit);
	return Killed;
}

void ATreadBuildingDestructionManager::RestoreAll()
{
	for (FPhysicsChunk& Chunk : PhysicsChunks)
	{
		if (UStaticMeshComponent* Body = Chunk.Component.Get())
		{
			Body->SetSimulatePhysics(false);
			Body->DestroyComponent();
		}
	}
	PhysicsChunks.Reset();

	for (int32 Index = 0; Index < Buildings.Num(); ++Index)
	{
		FBuildingRecord& Record = Buildings[Index];
		if (Record.bDestroyed)
		{
			ShowInstance(Record);
			Record.bDestroyed = false;
			Record.bUsedChunks = false;
		}
		Record.Health = Record.MaxHealth;
		Record.DamageStage = 0;
		Record.Trampled = 0.0f;
	}
	for (const TObjectPtr<UHierarchicalInstancedStaticMeshComponent>& Host : ChunkHosts)
	{
		if (Host)
		{
			Host->ClearInstances();
		}
	}
	UE_LOG(LogTemp, Display, TEXT("Tread destruction: restored %d buildings"), Buildings.Num());
}

int32 ATreadBuildingDestructionManager::GetDestroyedCount() const
{
	int32 Count = 0;
	for (const FBuildingRecord& Record : Buildings)
	{
		Count += Record.bDestroyed ? 1 : 0;
	}
	return Count;
}

FVector ATreadBuildingDestructionManager::GetBuildingLocation(int32 Index) const
{
	return Buildings.IsValidIndex(Index) ? Buildings[Index].WorldTransform.GetLocation() : FVector::ZeroVector;
}

float ATreadBuildingDestructionManager::GetHealthFraction(int32 Index) const
{
	if (!Buildings.IsValidIndex(Index) || Buildings[Index].MaxHealth <= 0.0f)
	{
		return -1.0f;
	}
	return FMath::Clamp(Buildings[Index].Health / Buildings[Index].MaxHealth, 0.0f, 1.0f);
}

float ATreadBuildingDestructionManager::GetTrampledFraction(int32 Index) const
{
	return Buildings.IsValidIndex(Index) ? FMath::Clamp(Buildings[Index].Trampled, 0.0f, 1.0f) : -1.0f;
}

// ---------------------------------------------------------------------------------------------------------------
// Reporting
// ---------------------------------------------------------------------------------------------------------------
void ATreadBuildingDestructionManager::WriteStats(const FString& Reason) const
{
	int32 ChunkBuildings = 0;
	int32 RubbleBuildings = 0;
	int32 Instances = 0;
	int32 StageOne = 0;
	int32 StageTwo = 0;
	int32 HalfTrampled = 0;
	float HealthSum = 0.0f;
	float TrampledSum = 0.0f;
	for (const FBuildingRecord& Record : Buildings)
	{
		HealthSum += Record.bDestroyed ? 0.0f : Record.Health / FMath::Max(Record.MaxHealth, 1.0f);
		TrampledSum += Record.Trampled;
		StageOne += Record.DamageStage == 1 ? 1 : 0;
		StageTwo += Record.DamageStage == 2 ? 1 : 0;
		HalfTrampled += Record.Trampled >= TrampleCollapseFraction ? 1 : 0;
		if (Record.bDestroyed)
		{
			ChunkBuildings += Record.bUsedChunks ? 1 : 0;
			RubbleBuildings += Record.bUsedChunks ? 0 : 1;
		}
	}
	for (const TPair<UStaticMesh*, TObjectPtr<UHierarchicalInstancedStaticMeshComponent>>& Pair : ChunkComponents)
	{
		Instances += Pair.Value ? Pair.Value->GetInstanceCount() : 0;
	}

	const FFramesStat Before = Summarise(AutoBeforeMs);
	const FFramesStat After = Summarise(AutoAfterMs);

	const TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetStringField(TEXT("schema"), TEXT("Tread.Destruction.Runtime.v3"));
	Root->SetStringField(TEXT("reason"), Reason);
	Root->SetStringField(TEXT("map"), GetWorld() ? GetWorld()->GetMapName() : TEXT("unknown"));
	Root->SetStringField(TEXT("date"), FDateTime::Now().ToString());
	const TCHAR* ModeName = AutoTestMode == ETreadAutoTestMode::Cascade ? TEXT("cascade")
		: (AutoTestMode == ETreadAutoTestMode::Trample ? TEXT("trample") : TEXT("destroy-band"));
	Root->SetStringField(TEXT("auto_mode"), ModeName);
	Root->SetNumberField(TEXT("registered"), Buildings.Num());
	Root->SetNumberField(TEXT("destroyed"), GetDestroyedCount());
	Root->SetNumberField(TEXT("chunk_buildings"), ChunkBuildings);
	Root->SetNumberField(TEXT("rubble_buildings"), RubbleBuildings);
	Root->SetNumberField(TEXT("chunk_hosts"), ChunkHosts.Num());
	Root->SetNumberField(TEXT("chunk_instances"), Instances);
	Root->SetNumberField(TEXT("avg_health_fraction"), Buildings.Num() > 0 ? HealthSum / Buildings.Num() : 0.0f);
	Root->SetNumberField(TEXT("avg_trampled"), Buildings.Num() > 0 ? TrampledSum / Buildings.Num() : 0.0f);

	const TSharedRef<FJsonObject> Health = MakeShared<FJsonObject>();
	Health->SetNumberField(TEXT("stage1_damaged"), StageOne);
	Health->SetNumberField(TEXT("stage2_heavy"), StageTwo);
	Health->SetNumberField(TEXT("half_trampled"), HalfTrampled);
	Health->SetNumberField(TEXT("root_hits"), RootHits);
	Health->SetNumberField(TEXT("cascade_events"), CascadeEvents);
	Health->SetNumberField(TEXT("cascade_deaths"), CascadeDeaths);
	Health->SetNumberField(TEXT("cascade_max_depth"), CascadeMaxDepthSeen);
	Health->SetNumberField(TEXT("support_radius_m"), SupportRadiusM);
	Health->SetNumberField(TEXT("support_requirement_fraction"), SupportRequirementFraction);
	Health->SetNumberField(TEXT("cascade_deficit_scale"), CascadeDeficitScale);
	Root->SetObjectField(TEXT("health"), Health);

	const TSharedRef<FJsonObject> Trample = MakeShared<FJsonObject>();
	Trample->SetNumberField(TEXT("steps"), TrampleSteps);
	Trample->SetNumberField(TEXT("collapses"), TrampleCollapses);
	Trample->SetNumberField(TEXT("collapse_fraction"), TrampleCollapseFraction);
	Trample->SetNumberField(TEXT("foot_radius_m"), TrampleFootRadiusM);
	Root->SetObjectField(TEXT("trample"), Trample);

	const TSharedRef<FJsonObject> Physics = MakeShared<FJsonObject>();
	Physics->SetNumberField(TEXT("chunk_bodies_spawned"), PhysicsChunksSpawned);
	Physics->SetNumberField(TEXT("chunk_bodies_frozen"), PhysicsChunksFrozen);
	Physics->SetNumberField(TEXT("chunk_bodies_live"), PhysicsChunks.Num());
	Physics->SetNumberField(TEXT("decals_spawned"), DecalsSpawned);
	Physics->SetNumberField(TEXT("settle_seconds"), PhysicsSettleSeconds);
	Physics->SetNumberField(TEXT("max_bodies"), MaxPhysicsBodies);
	Physics->SetNumberField(TEXT("dust_spawned"), DustSpawned);
	Physics->SetNumberField(TEXT("dust_skipped"), DustSkipped);
	Physics->SetBoolField(TEXT("dust_audience_only"), bDustOnAudienceOnly);
	Physics->SetBoolField(TEXT("dust_system_loaded"), DustSystem != nullptr);
	Root->SetObjectField(TEXT("physics"), Physics);

	if (AutoDestroyMs > 0.0)
	{
		Root->SetNumberField(TEXT("destroy_pass_ms"), AutoDestroyMs);
	}
	const TSharedRef<FJsonObject> BeforeObject = MakeShared<FJsonObject>();
	BeforeObject->SetNumberField(TEXT("frames"), Before.Count);
	BeforeObject->SetNumberField(TEXT("avg_ms"), Before.AvgMs);
	BeforeObject->SetNumberField(TEXT("worst_ms"), Before.WorstMs);
	BeforeObject->SetNumberField(TEXT("avg_fps"), Before.AvgMs > 0.0f ? 1000.0f / Before.AvgMs : 0.0f);
	Root->SetObjectField(TEXT("intact"), BeforeObject);
	const TSharedRef<FJsonObject> AfterObject = MakeShared<FJsonObject>();
	AfterObject->SetNumberField(TEXT("frames"), After.Count);
	AfterObject->SetNumberField(TEXT("avg_ms"), After.AvgMs);
	AfterObject->SetNumberField(TEXT("worst_ms"), After.WorstMs);
	AfterObject->SetNumberField(TEXT("avg_fps"), After.AvgMs > 0.0f ? 1000.0f / After.AvgMs : 0.0f);
	Root->SetObjectField(TEXT("destroyed_frame_times"), AfterObject);

	FString Output;
	const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Output);
	FJsonSerializer::Serialize(Root, Writer);
	const FString Path = FPaths::ProjectSavedDir() / TEXT("Reports/Destruction_Runtime.json");
	FFileHelper::SaveStringToFile(Output, *Path);
	UE_LOG(LogTemp, Display, TEXT("Tread destruction stats (%s): registered=%d destroyed=%d chunks=%d rubble=%d "
		"stage1=%d stage2=%d trample steps=%d collapses=%d bodies=%d/%d dust=%d -> %s"), *Reason, Buildings.Num(),
		GetDestroyedCount(), ChunkBuildings, RubbleBuildings, StageOne, StageTwo, TrampleSteps, TrampleCollapses,
		PhysicsChunksSpawned, PhysicsChunksFrozen, DustSpawned, *Path);
}

// ---------------------------------------------------------------------------------------------------------------
// Auto test (stand-alone validation)
// ---------------------------------------------------------------------------------------------------------------
void ATreadBuildingDestructionManager::FireAutoTestHit(int32 HitIndex)
{
	const int32 Count = FMath::Max(AutoTestHits, 1);
	const int32 Stride = FMath::Max(1, Buildings.Num() / (Count + 1));
	const int32 Index = FMath::Clamp(Stride * (HitIndex + 1), 0, FMath::Max(0, Buildings.Num() - 1));
	const FVector Origin = Buildings.IsValidIndex(Index) ? Buildings[Index].WorldTransform.GetLocation() : FVector::ZeroVector;
	// The first hit is deliberately light so the test exercises damage stage 1 (cracked, still standing) as well as
	// the lethal ones - a single 200-damage blast skips straight past it on the 240 hp large modules.
	const float Scale = HitIndex == 0 ? 0.4f : 1.0f;
	ApplyAreaDamage(Origin, AutoTestHitRadiusM, AutoTestHitDamage * Scale);
}

void ATreadBuildingDestructionManager::FireAutoTestTrample(int32 StepIndex)
{
	// Walk the foot across the band; partial damage first, collapse once a building is past half trampled.
	const int32 Steps = FMath::Max(AutoTestTrampleSteps, 1);
	const float Y = FMath::Lerp(-620.0f, 620.0f, (StepIndex + 0.5f) / Steps);
	const float X = (StepIndex % 2 == 0) ? -12000.0f : 12000.0f;  // zig-zag over two rows
	ApplyTrample(FVector(X, Y * 100.0f, 0.0f), TrampleFootRadiusM, TrampleCoveragePerStep, TrampleStepDamage);
}

void ATreadBuildingDestructionManager::RunAutoTest(float DeltaSeconds)
{
	// Timeline: 0-2 s warm up, 2-4 s sample "intact", run the pass, 4-9 s sample, screenshot + report, quit at 10 s.
	AutoSeconds += DeltaSeconds;
	if (AutoSeconds < 2.0f)
	{
		return;
	}
	if (!bAutoDestroyed)
	{
		if (AutoSeconds < 4.0f)
		{
			AutoBeforeMs.Add(DeltaSeconds * 1000.0f);
			return;
		}
		bAutoDestroyed = true;
		const double Start = FPlatformTime::Seconds();
		if (AutoTestMode == ETreadAutoTestMode::Cascade)
		{
			for (int32 Hit = 0; Hit < FMath::Max(AutoTestHits, 1); ++Hit)
			{
				FireAutoTestHit(Hit);
			}
			AutoDestroyedCount = GetDestroyedCount();
		}
		else if (AutoTestMode == ETreadAutoTestMode::Trample)
		{
			// Trample steps are spread over time so the partial damage and the final collapses are both visible.
			// Switch to the audience camera for the pass: dust only spawns there, and it is the shot that matters.
			if (UWorld* World = GetWorld())
			{
				for (TActorIterator<ATreadM3BoardPresenter> It(World); It; ++It)
				{
					// Frame the middle band with the close-up kill camera: that is where dust is allowed to spawn and
					// the only view in which the destruction reads (document/162 §4.3-4.5).
					It->MoveAudienceCameraForTest(FVector(0.0f, 0.0f, 0.0f) + FVector(0.0f, -12000.0f, 0.0f));
					It->SetAudienceCameraForTest(true);
					break;
				}
			}
			const int32 Steps = FMath::Max(AutoTestTrampleSteps, 1);
			if (UWorld* World = GetWorld())
			{
				for (int32 Step = 0; Step < Steps; ++Step)
				{
					FTimerHandle Handle;
					const FTimerDelegate Delegate = FTimerDelegate::CreateWeakLambda(this, [this, Step]()
					{
						FireAutoTestTrample(Step);
					});
					World->GetTimerManager().SetTimer(Handle, Delegate, 0.3f * (Step + 1), false);
				}
			}
			AutoDestroyedCount = 0;
		}
		else
		{
			AutoDestroyedCount = DestroyBand(0);
		}
		AutoDestroyMs = (FPlatformTime::Seconds() - Start) * 1000.0;
		UE_LOG(LogTemp, Display, TEXT("Tread destruction: auto pass queued/destroyed %d in %.2f ms"),
			AutoDestroyedCount, AutoDestroyMs);
		return;
	}
	AutoAfterMs.Add(DeltaSeconds * 1000.0f);
	// Trample: grab the picture while the dust is still alive (the last step lands around 6 s).
	if (AutoTestMode == ETreadAutoTestMode::Trample && !bAutoShot && AutoSeconds >= 5.8f && !AutoScreenshotPath.IsEmpty())
	{
		bAutoShot = true;
		FScreenshotRequest::RequestScreenshot(AutoScreenshotPath, /*bShowUI*/ false, /*bAddFilenameSuffix*/ false);
	}
	if (AutoSeconds >= 9.0f && !bAutoFinished)
	{
		bAutoFinished = true;
		if (!bAutoShot && !AutoScreenshotPath.IsEmpty())
		{
			FScreenshotRequest::RequestScreenshot(AutoScreenshotPath, /*bShowUI*/ false, /*bAddFilenameSuffix*/ false);
		}
		WriteStats(TEXT("auto-settle"));
	}
	if (bAutoFinished && AutoSeconds >= 10.0f)
	{
		UKismetSystemLibrary::QuitGame(this, nullptr, EQuitPreference::Quit, false);
		SetActorTickEnabled(false);
	}
}

void ATreadBuildingDestructionManager::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	UpdatePhysicsChunks(DeltaSeconds);
	if (bAutoTest && !bAutoFinished)
	{
		RunAutoTest(DeltaSeconds);
	}
}

// ---------------------------------------------------------------------------------------------------------------
// Console commands (PIE / stand-alone). They act on the first manager in the current PIE or game world.
// ---------------------------------------------------------------------------------------------------------------
namespace
{
	ATreadBuildingDestructionManager* FindManager()
	{
		if (!GEngine)
		{
			return nullptr;
		}
		for (const FWorldContext& Context : GEngine->GetWorldContexts())
		{
			UWorld* World = Context.World();
			if (!World || (Context.WorldType != EWorldType::PIE && Context.WorldType != EWorldType::Game))
			{
				continue;
			}
			for (TActorIterator<ATreadBuildingDestructionManager> It(World); It; ++It)
			{
				return *It;
			}
		}
		return nullptr;
	}

	FAutoConsoleCommandWithWorldAndArgs GTrample(
		TEXT("Tread.Trample"),
		TEXT("Tread.Trample <steps> [coverage] [damage]: walk a foot across the band (partial damage + collapse past half)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(
			[](const TArray<FString>& Args, UWorld*)
			{
				ATreadBuildingDestructionManager* Manager = FindManager();
				if (!Manager)
				{
					return;
				}
				const int32 Steps = Args.Num() > 0 ? FCString::Atoi(*Args[0]) : 3;
				const float Coverage = Args.Num() > 1 ? FCString::Atof(*Args[1]) : 0.35f;
				const float Damage = Args.Num() > 2 ? FCString::Atof(*Args[2]) : 90.0f;
				for (int32 Step = 0; Step < FMath::Max(Steps, 1); ++Step)
				{
					const float Y = FMath::Lerp(-620.0f, 620.0f, (Step + 0.5f) / FMath::Max(Steps, 1));
					Manager->ApplyTrample(FVector(0.0f, Y * 100.0f, 0.0f), 45.0f, Coverage, Damage);
				}
			}));

	FAutoConsoleCommandWithWorldAndArgs GHitBand(
		TEXT("Tread.HitBand"),
		TEXT("Tread.HitBand <damage> <radiusM> [count]: area hits inside the band, cascade included"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(
			[](const TArray<FString>& Args, UWorld*)
			{
				ATreadBuildingDestructionManager* Manager = FindManager();
				if (!Manager)
				{
					return;
				}
				const float Damage = Args.Num() > 0 ? FCString::Atof(*Args[0]) : 200.0f;
				const float RadiusM = Args.Num() > 1 ? FCString::Atof(*Args[1]) : 120.0f;
				const int32 Count = Args.Num() > 2 ? FCString::Atoi(*Args[2]) : 1;
				for (int32 Hit = 0; Hit < FMath::Max(Count, 1); ++Hit)
				{
					Manager->ApplyAreaDamage(Manager->GetBuildingLocation(Hit), RadiusM, Damage);
				}
			}));

	FAutoConsoleCommandWithWorldAndArgs GDestroyBand(
		TEXT("Tread.DestroyBand"),
		TEXT("Tread.DestroyBand <count>: destroy up to <count> buildings of the middle 4x8 band (0 = all)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(
			[](const TArray<FString>& Args, UWorld*)
			{
				if (ATreadBuildingDestructionManager* Manager = FindManager())
				{
					const int32 Limit = Args.Num() > 0 ? FCString::Atoi(*Args[0]) : 0;
					Manager->DestroyBand(Limit);
				}
			}));

	FAutoConsoleCommandWithWorld GRestoreBand(
		TEXT("Tread.RestoreBand"),
		TEXT("Tread.RestoreBand: undo every destruction this session"),
		FConsoleCommandWithWorldDelegate::CreateStatic(
			[](UWorld*)
			{
				if (ATreadBuildingDestructionManager* Manager = FindManager())
				{
					Manager->RestoreAll();
				}
			}));

	FAutoConsoleCommandWithWorld GDestructionStats(
		TEXT("Tread.DestructionStats"),
		TEXT("Tread.DestructionStats: log + write Saved/Reports/Destruction_Runtime.json"),
		FConsoleCommandWithWorldDelegate::CreateStatic(
			[](UWorld*)
			{
				if (ATreadBuildingDestructionManager* Manager = FindManager())
				{
					Manager->WriteStats(TEXT("console"));
				}
			}));
}
