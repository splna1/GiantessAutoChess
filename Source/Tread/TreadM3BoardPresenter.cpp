#include "TreadM3BoardPresenter.h"

#include "Animation/AnimSequence.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Animation/SkeletalMeshActor.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "TreadM1MatchController.h"

namespace
{
	const TCHAR* IdlePath = TEXT("/Game/Tread/Characters/Clukay416/Anim/GP/A_GP_Idle.A_GP_Idle");
	const TCHAR* GrowthPath = TEXT("/Game/Tread/Characters/Clukay416/Anim/GP/A_GP_Growth.A_GP_Growth");
	const TCHAR* RingMeshPath = TEXT("/Game/Tread/Characters/SM_SelectionRing.SM_SelectionRing");
	const TCHAR* RingBluePath = TEXT("/Game/Tread/City/Paris/Materials/Instances/MI_Ring_Blue.MI_Ring_Blue");
	const TCHAR* RingRedPath = TEXT("/Game/Tread/City/Paris/Materials/Instances/MI_Ring_Red.MI_Ring_Red");
	// document/159: the ring is the unit's health bar, so it needs a masked material the presenter can drive per unit.
	// Without the generated asset the plain M0 ring keeps the board readable (same colours, no gap).
	const TCHAR* UnitRingBluePath = TEXT("/Game/Tread/Characters/UnitRing/MI_UnitRing_Blue.MI_UnitRing_Blue");
	const TCHAR* UnitRingRedPath = TEXT("/Game/Tread/Characters/UnitRing/MI_UnitRing_Red.MI_UnitRing_Red");
	const TCHAR* UnitRingTrackPath = TEXT("/Game/Tread/Characters/UnitRing/MI_UnitRing_Track.MI_UnitRing_Track");
	/** Arc above the dark track: two coplanar rings at 1.7 km z-fight, 0.2 m of separation is invisible at 200 m cells. */
	constexpr float RingArcLift = 20.0f;
	const TCHAR* EmissivePath = TEXT("/Game/Tread/City/Paris/Materials/M_Paris_Emissive.M_Paris_Emissive");
	const TCHAR* CubePath = TEXT("/Engine/BasicShapes/Cube.Cube");
	constexpr float GrowSeconds = 1.4f;
}

ATreadM3BoardPresenter::ATreadM3BoardPresenter()
{
	PrimaryActorTick.bCanEverTick = true;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
}

FVector ATreadM3BoardPresenter::UiCellToWorld(FIntPoint UiCell, float Z)
{
	return FVector((3.5f - UiCell.Y) * CellCm, (UiCell.X - 3.5f) * CellCm, Z);
}

void ATreadM3BoardPresenter::BeginPlay()
{
	Super::BeginPlay();
	for (TActorIterator<ATreadM1MatchController> It(GetWorld()); It; ++It) { Controller = *It; break; }
	FindTemplates();
	// document/12: with a presenter on the board the controller resolves at battle start and keeps the Battle
	// phase until the replay below reports that it is over (or the battle cap runs out).
	LoadPresentationTable();
	if (Controller.IsValid()) Controller->SetBattlePresenterActive(true);
	IdleAnim = LoadObject<UAnimSequence>(nullptr, IdlePath);
	GrowthAnim = LoadObject<UAnimSequence>(nullptr, GrowthPath);
	if (!RingMesh) RingMesh = LoadObject<UStaticMesh>(nullptr, RingMeshPath);
	RingBlue = LoadObject<UMaterialInterface>(nullptr, UnitRingBluePath);
	RingRed = LoadObject<UMaterialInterface>(nullptr, UnitRingRedPath);
	RingTrackMaterial = LoadObject<UMaterialInterface>(nullptr, UnitRingTrackPath);
	if (!RingBlue) RingBlue = LoadObject<UMaterialInterface>(nullptr, RingBluePath);
	if (!RingRed) RingRed = LoadObject<UMaterialInterface>(nullptr, RingRedPath);
	// Drop target frame: four flat emissive bars around the hovered cell.
	UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, CubePath);
	if (UMaterialInterface* Emissive = LoadObject<UMaterialInterface>(nullptr, EmissivePath))
	{
		HoverMaterial = UMaterialInstanceDynamic::Create(Emissive, this);
		HoverMaterial->SetScalarParameterValue(TEXT("Intensity"), 6.0f);
		HoverMaterial->SetScalarParameterValue(TEXT("PulseAmount"), 0.45f);
		HoverMaterial->SetScalarParameterValue(TEXT("PulseSpeed"), 1.6f);
	}
	for (int32 Index = 0; Index < 4; ++Index)
	{
		UStaticMeshComponent* Bar = NewObject<UStaticMeshComponent>(this);
		Bar->SetStaticMesh(Cube);
		Bar->SetMaterial(0, HoverMaterial);
		Bar->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Bar->SetCastShadow(false);
		Bar->SetupAttachment(RootComponent);
		Bar->RegisterComponent();
		Bar->SetVisibility(false);
		HoverFrame.Add(Bar);
	}
}

void ATreadM3BoardPresenter::EndPlay(const EEndPlayReason::Type Reason)
{
	if (Controller.IsValid()) Controller->SetBattlePresenterActive(false);
	Super::EndPlay(Reason);
}

void ATreadM3BoardPresenter::FindTemplates()
{
	// The M0 hero (Char_Clukay416 + face) and its two rings define size, height and look of every unit.
	// document/186: actor labels are editor-only, so in a packaged build GetActorNameOrLabel() returns the
	// object name (SkeletalMeshActor_N) and the label match found nothing. Identify the templates by their
	// mesh asset instead, and fall back to the known hero paths when the level has no template at all.
	for (TActorIterator<ASkeletalMeshActor> It(GetWorld()); It; ++It)
	{
		const FString Label = It->GetName() + TEXT(" ") + It->GetActorNameOrLabel();
		USkeletalMeshComponent* Comp = It->GetSkeletalMeshComponent();
		if (!Comp || !Comp->GetSkeletalMeshAsset()) continue;
		const FString MeshName = Comp->GetSkeletalMeshAsset()->GetName();
		const bool bFace = MeshName.Contains(TEXT("U_Char_1")) || Label.Contains(TEXT("Face"));
		const bool bHero = MeshName.Contains(TEXT("SK_Clukay416")) || MeshName.Contains(TEXT("U_Char_0"))
			|| Label.Contains(TEXT("Clukay416"));
		if (!bHero && !bFace) continue;
		TArray<TObjectPtr<UMaterialInterface>>& Mats = bFace ? FaceMaterials : BodyMaterials;
		for (int32 Slot = 0; Slot < Comp->GetNumMaterials(); ++Slot) Mats.Add(Comp->GetMaterial(Slot));
		if (bFace) FaceMesh = Comp->GetSkeletalMeshAsset();
		else
		{
			BodyMesh = Comp->GetSkeletalMeshAsset();
			BaseScale = It->GetActorScale3D().X;
			GroundZ = It->GetActorLocation().Z;
			const FBoxSphereBounds B = Comp->Bounds;
			UnitHeightCm = FMath::Max(1000.0f, B.Origin.Z + B.BoxExtent.Z - GroundZ);
		}
		It->SetActorHiddenInGame(true);
	}
	// Packaged fallback: the M3 level only carries the hero as a decoration; load the same assets by path.
	if (!BodyMesh)
	{
		BodyMesh = LoadObject<USkeletalMesh>(nullptr, TEXT("/Game/Tread/Characters/Clukay416/SK_Clukay416.SK_Clukay416"));
		if (BodyMesh)
		{
			const FBoxSphereBounds B = BodyMesh->GetBounds();
			const float MeshHeight = FMath::Max(1.0f, 2.0f * static_cast<float>(B.BoxExtent.Z));
			BaseScale = 11500.0f / MeshHeight;
			UnitHeightCm = 11500.0f;
			GroundZ = 0.0f;
		}
	}
	if (!FaceMesh)
	{
		FaceMesh = LoadObject<USkeletalMesh>(nullptr, TEXT("/Game/Tread/Characters/Clukay416/416/SkeletalMeshes/U_Char_1.U_Char_1"));
	}
	for (TActorIterator<AStaticMeshActor> It(GetWorld()); It; ++It)
	{
		if (!It->ActorHasTag(TEXT("M0SelectionRing"))) continue;
		if (UStaticMeshComponent* Comp = It->GetStaticMeshComponent())
		{
			RingMesh = Comp->GetStaticMesh();
			RingScale = It->GetActorScale3D().X;
			RingZ = It->GetActorLocation().Z;
		}
		It->SetActorHiddenInGame(true);
	}
	if (RingZ == 0.0f) RingZ = GroundZ + 30.0f;
	// document/186: packaged builds silently lost the unit meshes; log what the level templates resolved to.
	UE_LOG(LogTemp, Warning, TEXT("Tread board templates: body=%s face=%s idle=%s growth=%s baseScale=%.3f height=%.0f groundZ=%.0f"),
		BodyMesh ? *BodyMesh->GetName() : TEXT("NULL"),
		FaceMesh ? *FaceMesh->GetName() : TEXT("NULL"),
		IdleAnim ? *IdleAnim->GetName() : TEXT("NULL"),
		GrowthAnim ? *GrowthAnim->GetName() : TEXT("NULL"),
		BaseScale, UnitHeightCm, GroundZ);
}


const FTreadM3CharacterVisuals& ATreadM3BoardPresenter::ResolveCharacterVisuals(const FString& CharacterId)
{
	if (FTreadM3CharacterVisuals* Cached = CharacterVisualCache.Find(CharacterId))
	{
		return *Cached;
	}
	FTreadM3CharacterVisuals Visuals;
	Visuals.Mesh = BodyMesh;
	Visuals.Idle = IdleAnim;
	Visuals.Growth = GrowthAnim;
	// Each character has its own imported mesh and a retargeted copy of the GP clips that lives with it,
	// because a clip only plays on the mesh it was baked for: char_101..112 are the MMD models (N2),
	// char_002..char_100 the roster VRMs (M4). char_100 is the 100th VRM despite its MMD-like number, and
	// char_001 is the M1 hero itself. Every other id (and any import that failed) falls back to the hero,
	// BodyMesh, which FindTemplates() resolved from the level.
	const bool bMmd = CharacterId.StartsWith(TEXT("char_1")) && CharacterId != TEXT("char_100");
	const bool bVrm = (CharacterId.StartsWith(TEXT("char_0")) || CharacterId == TEXT("char_100")) && CharacterId != TEXT("char_001");
	if (bMmd || bVrm)
	{
		const TCHAR* Set = bMmd ? TEXT("MMD") : TEXT("VRM");
		const FString Folder = FString::Printf(TEXT("/Game/Tread/Characters/%s/%s"), Set, *CharacterId);
		const FString MeshPath = FString::Printf(TEXT("%s/SK_%s_%s.SK_%s_%s"), *Folder, Set, *CharacterId, Set, *CharacterId);
		if (USkeletalMesh* Mesh = LoadObject<USkeletalMesh>(nullptr, *MeshPath))
		{
			Visuals.Mesh = Mesh;
			Visuals.AnimFolder = Folder + TEXT("/Anim");
			Visuals.Idle = LoadObject<UAnimSequence>(nullptr, *FString::Printf(TEXT("%s/Anim/A_GP_Idle.A_GP_Idle"), *Folder));
			Visuals.Growth = LoadObject<UAnimSequence>(nullptr, *FString::Printf(TEXT("%s/Anim/A_GP_Growth.A_GP_Growth"), *Folder));
			// A clip only plays on the mesh it was baked for, so a character whose clips are missing
			// would stand in the hero's clip and deform: take the whole hero set instead.
			if (!Visuals.Idle || !Visuals.Growth)
			{
				Visuals.Mesh = BodyMesh;
				Visuals.AnimFolder.Reset();
				Visuals.Idle = IdleAnim;
				Visuals.Growth = GrowthAnim;
			}
			UE_LOG(LogTemp, Warning, TEXT("Tread board visual %s: path=%s mesh=%s idle=%s folder=%s"),
				*CharacterId, *MeshPath, *Mesh->GetName(),
				Visuals.Idle ? *Visuals.Idle->GetName() : TEXT("NULL"), *Visuals.AnimFolder);
		}
		else
		{
			UE_LOG(LogTemp, Warning, TEXT("Tread board visual %s: path=%s MESH LOAD FAILED -> hero fallback body=%s"),
				*CharacterId, *MeshPath, BodyMesh ? *BodyMesh->GetName() : TEXT("NULL"));
		}
	}
	return CharacterVisualCache.Add(CharacterId, Visuals);
}

ATreadM3BoardPresenter::FUnitVisual& ATreadM3BoardPresenter::Spawn(const FString& Id, const FTreadM1UnitInstance& Unit, bool bEnemy)
{
	FUnitVisual& V = Units.Add(Id);
	V.CharacterId = Unit.CharacterId;
	V.Tier = Unit.OperatorTier;
	V.OwnerId = Unit.OwnerPlayerId;
	V.Star = Unit.UnitStar;
	V.bEnemy = bEnemy;
	V.Body = NewObject<USkeletalMeshComponent>(this);
	const FTreadM3CharacterVisuals& Visuals = ResolveCharacterVisuals(Unit.CharacterId);
	USkeletalMesh* CharMesh = Visuals.Mesh;
	V.Idle = Visuals.Idle;
	V.Growth = Visuals.Growth;
	V.Body->SetSkeletalMeshAsset(CharMesh);
	// BodyMaterials are the M1 hero's own slots, and the hero is a body mesh plus a face mesh that
	// shares its pose. An MMD or roster VRM mesh is single-mesh and carries its own per-slot toon
	// instances from its import step (slot counts differ from the hero's 23), so it must keep them.
	const bool bHeroMesh = (CharMesh == BodyMesh.Get());
	if (bHeroMesh)
	{
		for (int32 Slot = 0; Slot < BodyMaterials.Num(); ++Slot) V.Body->SetMaterial(Slot, BodyMaterials[Slot]);
	}
	V.Body->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	V.Body->SetupAttachment(RootComponent);
	V.Body->RegisterComponent();
	UE_LOG(LogTemp, Warning, TEXT("Tread board spawn %s char=%s mesh=%s starScale=%.2f anim=%d"),
		*Id, *Unit.CharacterId,
		V.Body->GetSkeletalMeshAsset() ? *V.Body->GetSkeletalMeshAsset()->GetName() : TEXT("NULL"),
		StarScale(Unit.UnitStar), V.Body->GetAnimInstance() ? 1 : 0);
	if (V.Idle) V.Body->PlayAnimation(V.Idle, true);
	// Desynchronise the idle loops so a full board does not breathe in lockstep.
	V.Body->SetPosition(FMath::Fmod(static_cast<float>(GetTypeHash(Id) % 997) * 0.37f, V.Idle ? V.Idle->GetPlayLength() : 1.0f));
	// The M1 hero is a body mesh plus a face mesh sharing its pose; MMD and roster VRM models are single-mesh.
	if (FaceMesh && bHeroMesh)
	{
		V.Face = NewObject<USkeletalMeshComponent>(this);
		V.Face->SetSkeletalMeshAsset(FaceMesh);
		for (int32 Slot = 0; Slot < FaceMaterials.Num(); ++Slot) V.Face->SetMaterial(Slot, FaceMaterials[Slot]);
		V.Face->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		V.Face->SetupAttachment(V.Body);
		V.Face->RegisterComponent();
		V.Face->SetLeaderPoseComponent(V.Body);
		Owned.Add(V.Face);
	}
	// document/159: the ring under the unit is its health bar. A dark full ring (the track) sits on the ground and the
	// coloured arc on top of it is cut open at 6 o'clock; the gap widens as the unit loses health.
	V.RingTrack = NewObject<UStaticMeshComponent>(this);
	V.RingTrack->SetStaticMesh(RingMesh);
	if (RingTrackMaterial) V.RingTrack->SetMaterial(0, RingTrackMaterial);
	V.RingTrack->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	V.RingTrack->SetCastShadow(false);
	V.RingTrack->SetupAttachment(RootComponent);
	V.RingTrack->RegisterComponent();
	V.Ring = NewObject<UStaticMeshComponent>(this);
	V.Ring->SetStaticMesh(RingMesh);
	// One dynamic instance per unit: HealthFraction has to differ per unit, and the shared MI_Ring_* is a constant.
	UMaterialInterface* ArcMaterial = bEnemy ? RingRed.Get() : RingBlue.Get();
	if (ArcMaterial)
	{
		V.RingMaterial = UMaterialInstanceDynamic::Create(ArcMaterial, this);
		ArcMaterial = V.RingMaterial;
	}
	V.Ring->SetMaterial(0, ArcMaterial);
	V.Ring->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	V.Ring->SetCastShadow(false);
	V.Ring->SetupAttachment(RootComponent);
	V.Ring->RegisterComponent();
	Owned.Add(V.Body);
	Owned.Add(V.Ring);
	if (V.RingTrack) Owned.Add(V.RingTrack);
	V.Scale = V.FromScale = StarScale(V.Star);
	return V;
}

void ATreadM3BoardPresenter::Place(FUnitVisual& V)
{
	const FVector Ground = UiCellToWorld(V.UiCell, GroundZ);
	float Scale = V.Scale;
	if (V.GrowT < 1.0f)
	{
		// Ease-out with a small overshoot so the growth reads as a pulse, then settle on the new star size.
		const float T = V.GrowT;
		const float Ease = 1.0f - FMath::Pow(1.0f - T, 3.0f);
		const float Overshoot = FMath::Sin(T * PI) * 0.06f;
		Scale = FMath::Lerp(V.FromScale, V.Scale, Ease) * (1.0f + Overshoot);
	}
	// During the battle presentation the unit walks off its cell and turns to its target (document/12).
	const FVector Feet = V.bBattle ? FVector(V.Pos.X, V.Pos.Y, GroundZ) : Ground;
	V.Body->SetWorldLocationAndRotation(Feet, FRotator(0.0f, V.bBattle ? V.Yaw : (V.bEnemy ? 180.0f : 0.0f), 0.0f));
	V.Body->SetWorldScale3D(FVector(Scale));
	const float RingK = RingScale * Scale / FMath::Max(BaseScale, KINDA_SMALL_NUMBER);
	const FVector RingBase(V.Body->GetComponentLocation().X, V.Body->GetComponentLocation().Y, RingZ);
	V.Ring->SetWorldLocation(RingBase + FVector(0.0f, 0.0f, RingArcLift));
	V.Ring->SetWorldScale3D(FVector(RingK, RingK, RingScale));
	if (V.RingTrack)
	{
		V.RingTrack->SetWorldLocation(RingBase);
		V.RingTrack->SetWorldScale3D(FVector(RingK, RingK, RingScale));
	}
	// document/159: full ring outside the battle and for a unit that was never hit; otherwise the health fraction.
	if (V.RingMaterial)
	{
		const float Fraction = (V.bBattle && V.HealthMax > 0)
			? FMath::Clamp(static_cast<float>(V.Health) / static_cast<float>(V.HealthMax), 0.0f, 1.0f) : 1.0f;
		V.RingMaterial->SetScalarParameterValue(TEXT("HealthFraction"), Fraction);
	}
	const bool bVisible = V.UiCell.X >= 0 && !V.bHidden;
	V.Body->SetVisibility(bVisible, true);
	V.Ring->SetVisibility(bVisible && !V.bDead);
	if (V.RingTrack) V.RingTrack->SetVisibility(bVisible && !V.bDead);
}

void ATreadM3BoardPresenter::Sync()
{
	if (!Controller.IsValid() || !BodyMesh) return;
	const FTreadM1MatchState& State = Controller->MatchState;
	const FTreadM1PlayerState* Human = nullptr;
	for (const FTreadM1PlayerState& P : State.Players) if (P.bIsHuman) { Human = &P; break; }
	if (!Human && State.Players.Num() > 0) Human = &State.Players[0];
	if (!Human) return;
	OpponentId = TEXT("P1");
	for (const FTreadM1BattlePairing& Pair : State.LastBattleResult.Pairings)
	{
		if (Pair.PlayerId == Human->PlayerId) OpponentId = Pair.OpponentId;
		else if (Pair.OpponentId == Human->PlayerId) OpponentId = Pair.PlayerId;
	}
	const FTreadM1PlayerState* Opponent = State.Players.FindByPredicate([this](const FTreadM1PlayerState& P) { return P.PlayerId == OpponentId; });
	const bool bShowBoard = State.Phase == ETreadM1Phase::Preparation || State.Phase == ETreadM1Phase::Battle || State.Phase == ETreadM1Phase::Settlement;
	for (TPair<FString, FUnitVisual>& Pair : Units) Pair.Value.bSeen = false;
	auto Visit = [&](const FTreadM1PlayerState& Side, bool bEnemy)
	{
		for (const FTreadM1UnitInstance& Unit : Side.BoardUnits)
		{
			FIntPoint Cell = Unit.BoardCell;
			if (Cell.X < 0 || Cell.X > 7 || Cell.Y < 0 || Cell.Y > 7) continue;
			if (bEnemy) Cell.Y = FMath::Clamp(Cell.Y, 0, 3);  // AI rosters stand on rows 0-3 (as in the M1 2D board)
			FUnitVisual* V = Units.Find(Unit.UnitInstanceId);
			const FString StarKey = Side.PlayerId + TEXT("|") + Unit.CharacterId;
			const int32 Before = BestStar.FindRef(StarKey);
			if (!V)
			{
				V = &Spawn(Unit.UnitInstanceId, Unit, bEnemy);
				if (Before > 0 && Unit.UnitStar > Before)
				{
					// Combine result: grow from the previous star size and play the growth clip once.
					V->FromScale = StarScale(Before);
					V->GrowT = 0.0f;
					++StarUpCount;
					if (V->Growth) V->Body->PlayAnimation(V->Growth, false);
				}
			}
			else if (Unit.UnitStar > V->Star)
			{
				V->FromScale = V->Scale;
				V->GrowT = 0.0f;
				++StarUpCount;
				if (V->Growth) V->Body->PlayAnimation(V->Growth, false);
			}
			BestStar.FindOrAdd(StarKey) = FMath::Max(Before, Unit.UnitStar);
			V->Star = Unit.UnitStar;
			V->Scale = StarScale(Unit.UnitStar);
			V->UiCell = Cell;
			V->bSeen = bShowBoard;
		}
		// Bench units count for star-up detection too (a 2-star made on the bench grows when it is deployed).
		// Only 1-star bench copies are recorded, so a 2-star combined on the bench still grows when deployed.
		for (const FTreadM1UnitInstance& Unit : Side.BenchUnits)
		{
			if (Unit.UnitStar != 1) continue;
			int32& Best = BestStar.FindOrAdd(Side.PlayerId + TEXT("|") + Unit.CharacterId);
			Best = FMath::Max(Best, 1);
		}
	};
	Visit(*Human, false);
	if (Opponent) Visit(*Opponent, true);
	else if (!State.ScriptedOpponentId.IsEmpty() && State.ScriptedOpponentUnits.Num() > 0)
	{
		// M4 campaign: the R1-R2 garrison / R12 leader is not a match player; its lineup lives in the match state.
		FTreadM1PlayerState Scripted;
		Scripted.PlayerId = TEXT("SCRIPTED");
		Scripted.BoardUnits = State.ScriptedOpponentUnits;
		Visit(Scripted, true);
	}
	TArray<FString> Gone;
	for (TPair<FString, FUnitVisual>& Pair : Units)
	{
		if (Pair.Value.bSeen) continue;
		Gone.Add(Pair.Key);
		for (USceneComponent* C : {static_cast<USceneComponent*>(Pair.Value.Face), static_cast<USceneComponent*>(Pair.Value.Body), static_cast<USceneComponent*>(Pair.Value.Ring)})
		{
			if (!C) continue;
			Owned.Remove(C);
			C->DestroyComponent();
		}
	}
	for (const FString& Id : Gone) Units.Remove(Id);
}

void ATreadM3BoardPresenter::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	Sync();
	if (Controller.IsValid())
	{
		const FTreadM1MatchState& State = Controller->MatchState;
		const bool bBattleView = State.Phase == ETreadM1Phase::Battle || State.Phase == ETreadM1Phase::Settlement;
		// A battle is keyed by its round and the last event sequence, so a fresh match never reuses an old replay.
		const int32 Key = State.RoundIndex * 100000 + (State.BattleEvents.Num() > 0 ? State.BattleEvents.Last().Sequence : 0);
		if (State.Phase == ETreadM1Phase::Battle && State.bBattleAwaitingPresentation && BattleRound != Key)
		{
			BattleRound = Key;
			BeginBattle(State);
		}
		if (bBattleActive && !bBattleView) EndBattle();
		if (bBattleActive) TickBattle(DeltaSeconds);
	}
	for (TPair<FString, FUnitVisual>& Pair : Units)
	{
		FUnitVisual& V = Pair.Value;
		if (V.GrowT < 1.0f)
		{
			V.GrowT = FMath::Min(1.0f, V.GrowT + DeltaSeconds / GrowSeconds);
			if (V.GrowT >= 1.0f && V.Idle) V.Body->PlayAnimation(V.Idle, true);
		}
		const bool bDragged = !DraggedUnitId.IsEmpty() && Pair.Key == DraggedUnitId;
		Place(V);
		if (bDragged) V.Body->SetVisibility(false, true);
		if (V.bBattle && V.Face) V.Face->SetVisibility(!V.bHidden && V.UiCell.X >= 0);
	}
}

void ATreadM3BoardPresenter::SetHoverCell(FIntPoint UiCell, bool bAllowed)
{
	const bool bShow = UiCell.X >= 0 && UiCell.X <= 7 && UiCell.Y >= 0 && UiCell.Y <= 7;
	for (UStaticMeshComponent* Bar : HoverFrame) if (Bar) Bar->SetVisibility(bShow);
	if (!bShow || HoverFrame.Num() < 4) return;
	if (HoverMaterial) HoverMaterial->SetVectorParameterValue(TEXT("Color"), bAllowed ? FLinearColor(1.0f, 0.78f, 0.12f) : FLinearColor(1.0f, 0.12f, 0.08f));
	const FVector C = UiCellToWorld(UiCell, GroundZ + 120.0f);
	// Cube is 100 cm: a bar of 168 m x 3 m x 1.2 m on each side of the 162 m courtyard block.
	const float Half = 0.43f * CellCm;
	const FVector Long(Half * 2.0f / 100.0f, 3.0f, 1.2f);
	const FVector Wide(3.0f, Half * 2.0f / 100.0f, 1.2f);
	HoverFrame[0]->SetWorldLocation(C + FVector(Half, 0, 0)); HoverFrame[0]->SetWorldScale3D(Wide);
	HoverFrame[1]->SetWorldLocation(C - FVector(Half, 0, 0)); HoverFrame[1]->SetWorldScale3D(Wide);
	HoverFrame[2]->SetWorldLocation(C + FVector(0, Half, 0)); HoverFrame[2]->SetWorldScale3D(Long);
	HoverFrame[3]->SetWorldLocation(C - FVector(0, Half, 0)); HoverFrame[3]->SetWorldScale3D(Long);
}

bool ATreadM3BoardPresenter::ViewportPixelToUiCell(const APlayerController* PC, FVector2D Pixel, FIntPoint& OutCell) const
{
	FVector Origin, Dir;
	if (!PC || !UGameplayStatics::DeprojectScreenToWorld(PC, Pixel, Origin, Dir) || FMath::Abs(Dir.Z) < KINDA_SMALL_NUMBER) return false;
	const float T = (GroundZ - Origin.Z) / Dir.Z;
	if (T <= 0.0f) return false;
	const FVector Hit = Origin + Dir * T;
	const int32 Col = FMath::FloorToInt(Hit.Y / CellCm + 4.0f);
	const int32 RowFromTop = FMath::FloorToInt(4.0f - Hit.X / CellCm);
	if (Col < 0 || Col > 7 || RowFromTop < 0 || RowFromTop > 7) return false;
	OutCell = FIntPoint(Col, RowFromTop);
	return true;
}

bool ATreadM3BoardPresenter::ProjectBoardRect(const APlayerController* PC, FVector2D& OutMin, FVector2D& OutMax) const
{
	if (!PC) return false;
	OutMin = FVector2D(1e9f, 1e9f);
	OutMax = FVector2D(-1e9f, -1e9f);
	const float H = 4.0f * CellCm;
	for (const FVector& Corner : {FVector(-H, -H, GroundZ), FVector(-H, H, GroundZ), FVector(H, -H, GroundZ), FVector(H, H, GroundZ)})
	{
		FVector2D P;
		if (!UGameplayStatics::ProjectWorldToScreen(PC, Corner, P)) return false;
		OutMin = FVector2D(FMath::Min(OutMin.X, P.X), FMath::Min(OutMin.Y, P.Y));
		OutMax = FVector2D(FMath::Max(OutMax.X, P.X), FMath::Max(OutMax.Y, P.Y));
	}
	return true;
}

void ATreadM3BoardPresenter::GetAnchors(TArray<FTreadM3UnitAnchor>& Out) const
{
	Out.Reset();
	for (const TPair<FString, FUnitVisual>& Pair : Units)
	{
		const FUnitVisual& V = Pair.Value;
		if (V.UiCell.X < 0 || V.bHidden) continue;
		FTreadM3UnitAnchor A;
		A.UnitInstanceId = Pair.Key;
		A.CharacterId = V.CharacterId;
		A.bEnemy = V.bEnemy;
		A.UiCell = V.UiCell;
		const float K = V.Body ? V.Body->GetComponentScale().X / FMath::Max(BaseScale, KINDA_SMALL_NUMBER) : 1.0f;
		A.HeadWorld = UiCellToWorld(V.UiCell, GroundZ + UnitHeightCm * K * 1.04f);
		if (V.bBattle)
		{
			A.HeadWorld = FVector(V.Pos.X, V.Pos.Y, GroundZ + UnitHeightCm * K * 1.04f);
			A.bDead = V.bDead;
			const float SkillSec = Timing(TEXT("skillLabelSec"), 2.4f);
			A.SkillAge01 = FMath::Clamp((BattleClock - V.SkillAt) / SkillSec, 0.0f, 1.0f);
			if (A.SkillAge01 < 1.0f)
			{
				A.SkillLabel = V.SkillLabel;
				A.SkillColor = V.SkillColor;
			}
		}
		Out.Add(A);
	}
}
