// document/12 battle presentation: the units of the human's pairing replay MatchState.BattleEvents on the 3D board.
// They walk or run to their targets, stop, face them with their own anatomical front (Content/Data/Generated/
// ModelFacing.json), swing their profession's GP clips (BattlePresentation.json), fall with A_GP_Defeat and the
// winners play A_GP_Victory. Health bars, floating numbers and skill names are read by UTreadM1MatchWidget.
// Read-only towards the match: event times are a pure function of the event stream (same seed -> same timeline);
// the presenter only tells the controller when the replay is over (the 45 s battle cap still settles without it).

#include "TreadBuildingDestructionManager.h"
#include "TreadM3BoardPresenter.h"

#include "Animation/AnimSequence.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Misc/CommandLine.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "TreadAudioDirector.h"
#include "TreadM1MatchController.h"
#include "TreadM2PactData.h"

namespace
{
	/** document/162 §4.6: the battle presentation drives the destruction runtime (trample at each blow). */
	ATreadBuildingDestructionManager* FindDestructionManager(UWorld* World)
	{
		if (!World)
		{
			return nullptr;
		}
		for (TActorIterator<ATreadBuildingDestructionManager> It(World); It; ++It)
		{
			return *It;
		}
		return nullptr;
	}
}

namespace
{
	const TCHAR* HeroAnimFolder = TEXT("/Game/Tread/Characters/Clukay416/Anim/GP");
	const TCHAR* BoltMaterialPath = TEXT("/Game/Tread/City/Paris/Materials/M_Paris_Emissive.M_Paris_Emissive");
	const TCHAR* BoltMeshPath = TEXT("/Engine/BasicShapes/Cube.Cube");

	TSharedPtr<FJsonObject> LoadJsonFile(const FString& RelativeToContent)
	{
		FString Text;
		TSharedPtr<FJsonObject> Root;
		if (FFileHelper::LoadFileToString(Text, *FPaths::Combine(FPaths::ProjectContentDir(), RelativeToContent)))
		{
			FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root);
		}
		return Root;
	}

	double JsonNum(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Key, double Default)
	{
		double Value = Default;
		return Obj.IsValid() && Obj->TryGetNumberField(Key, Value) ? Value : Default;
	}

	TSharedPtr<FJsonObject> Child(const TSharedPtr<FJsonObject>& Obj, const FString& Key)
	{
		const TSharedPtr<FJsonObject>* Out = nullptr;
		return Obj.IsValid() && Obj->TryGetObjectField(Key, Out) && Out ? *Out : nullptr;
	}

	TArray<FName> Names(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Key)
	{
		TArray<FName> Out;
		const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
		if (Obj.IsValid() && Obj->TryGetArrayField(Key, Values) && Values)
		{
			for (const TSharedPtr<FJsonValue>& Value : *Values) Out.Add(FName(*Value->AsString()));
		}
		return Out;
	}

	FLinearColor ColorField(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Key, const FLinearColor& Default)
	{
		const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
		if (!Obj.IsValid() || !Obj->TryGetArrayField(Key, Values) || !Values || Values->Num() < 3) return Default;
		return FLinearColor((*Values)[0]->AsNumber(), (*Values)[1]->AsNumber(), (*Values)[2]->AsNumber());
	}

	float YawOf(const FVector& Direction) { return FMath::RadiansToDegrees(FMath::Atan2(Direction.Y, Direction.X)); }

	/** Facing table written by Tools/battle/ue_model_facing.py (component-space yaw of each model's front). */
	const TSharedPtr<FJsonObject>& FacingTable()
	{
		static TSharedPtr<FJsonObject> Facing = Child(LoadJsonFile(TEXT("Data/Generated/ModelFacing.json")), TEXT("facing"));
		return Facing;
	}
}

// ------------------------------------------------------------------------------------------------ data
void ATreadM3BoardPresenter::LoadPresentationTable()
{
	Table = LoadJsonFile(TEXT("Data/Generated/BattlePresentation.json"));
	if (!Table.IsValid()) UE_LOG(LogTemp, Warning, TEXT("Tread battle: BattlePresentation.json missing, using built-in timing"));
	BoltBase = LoadObject<UMaterialInterface>(nullptr, BoltMaterialPath);
	BoltMesh = LoadObject<UStaticMesh>(nullptr, BoltMeshPath);
	for (TActorIterator<ACameraActor> It(GetWorld()); It; ++It)
	{
		const bool bNamed = It->GetName().Contains(TEXT("Board_Camera"))
#if WITH_EDITOR
			|| It->GetActorLabel().Contains(TEXT("Board_Camera"))
#endif
			|| It->Tags.Contains(TEXT("Board_Camera"));
		if (bNamed) { BoardCamera = *It; break; }
	}
	// document/125 §4.1: Audience_Camera at the east end of the x = 0 street, looking west at the Eiffel Tower.
	const TSharedPtr<FJsonObject> Cam = Child(Table, TEXT("camera"));
	FVector LocationM(0.0, 940.0, 14.0);
	const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
	if (Cam.IsValid() && Cam->TryGetArrayField(TEXT("audienceLocationM"), Values) && Values && Values->Num() >= 3)
	{
		LocationM = FVector((*Values)[0]->AsNumber(), (*Values)[1]->AsNumber(), (*Values)[2]->AsNumber());
	}
	const FVector Location(LocationM.X * 100.0, LocationM.Y * 100.0, GroundZ + LocationM.Z * 100.0);
	const FRotator Rotation(JsonNum(Cam, TEXT("audiencePitchDeg"), 3.0), JsonNum(Cam, TEXT("audienceYawDeg"), -90.0), 0.0);
	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AudienceCamera = GetWorld()->SpawnActor<ACameraActor>(Location, Rotation, Params);
	if (AudienceCamera)
	{
		AudienceHomeLocation = AudienceCamera->GetActorLocation();
		AudienceHomeRotation = AudienceCamera->GetActorRotation();
		KillCamDistanceM = JsonNum(Cam, TEXT("killCamDistanceM"), 240.0);
		KillCamHeightM = JsonNum(Cam, TEXT("killCamHeightM"), 60.0);
		KillCamFovDeg = JsonNum(Cam, TEXT("killCamFovDeg"), 30.0);
#if WITH_EDITOR
		AudienceCamera->SetActorLabel(TEXT("Audience_Camera"));
#endif
		UCameraComponent* Camera = AudienceCamera->GetCameraComponent();
		// The table holds the vertical FOV (document/125); the camera component takes the horizontal one at 16:9.
		const float VerticalFov = JsonNum(Cam, TEXT("audienceFovDeg"), 18.0);
		AudienceHomeFov = VerticalFov;
		const float HorizontalFov = FMath::RadiansToDegrees(2.0f * FMath::Atan(FMath::Tan(FMath::DegreesToRadians(VerticalFov) * 0.5f) * 16.0f / 9.0f));
		Camera->SetFieldOfView(HorizontalFov);
		Camera->SetConstraintAspectRatio(false);
	}
}

float ATreadM3BoardPresenter::Timing(const TCHAR* Key, float Default) const { return JsonNum(Child(Table, TEXT("timing")), Key, Default); }
float ATreadM3BoardPresenter::Movement(const TCHAR* Key, float Default) const { return JsonNum(Child(Table, TEXT("movement")), Key, Default); }

TSharedPtr<FJsonObject> ATreadM3BoardPresenter::ProfessionRow(const FString& Profession) const
{
	const TSharedPtr<FJsonObject> Professions = Child(Table, TEXT("professions"));
	TSharedPtr<FJsonObject> Row = Child(Professions, Profession);
	if (!Row.IsValid() && Table.IsValid()) Row = Child(Professions, Table->GetStringField(TEXT("defaultProfession")));
	return Row;
}

FLinearColor ATreadM3BoardPresenter::ProfessionColor(const FString& Profession) const
{
	return ColorField(ProfessionRow(Profession), TEXT("color"), FLinearColor(1.0f, 0.85f, 0.3f));
}

UAnimSequence* ATreadM3BoardPresenter::Clip(const FString& CharacterId, FName Name)
{
	FTreadM3CharacterVisuals* Visuals = CharacterVisualCache.Find(CharacterId);
	if (!Visuals || Name.IsNone()) return nullptr;
	if (TObjectPtr<UAnimSequence>* Found = Visuals->Clips.Find(Name)) return *Found;
	// document/179: char_093's retargeted Idle makes the mesh vanish (document/154); play the hero's copy instead.
	const bool bBrokenIdle = CharacterId == TEXT("char_093") && Name == TEXT("Idle");
	// The clip must come from the same set as the mesh: the character's own retargeted copies or the hero's.
	const FString Folder = (bBrokenIdle || Visuals->AnimFolder.IsEmpty()) ? FString(HeroAnimFolder) : Visuals->AnimFolder;
	const FString Asset = TEXT("A_GP_") + Name.ToString();
	UAnimSequence* Sequence = LoadObject<UAnimSequence>(nullptr, *FString::Printf(TEXT("%s/%s.%s"), *Folder, *Asset, *Asset));
	Visuals->Clips.Add(Name, Sequence);
	return Sequence;
}

// ------------------------------------------------------------------------------------------------ helpers
float ATreadM3BoardPresenter::UnitHeight(const FUnitVisual& V) const
{
	const float K = V.Body ? V.Body->GetComponentScale().X / FMath::Max(BaseScale, KINDA_SMALL_NUMBER) : 1.0f;
	return UnitHeightCm * K;
}

FVector ATreadM3BoardPresenter::ChestOf(const FUnitVisual& V) const
{
	return V.Pos + FVector(0.0f, 0.0f, UnitHeight(V) * 0.62f);
}

void ATreadM3BoardPresenter::PlayClip(FUnitVisual& V, FName Name, bool bLoop, float Rate)
{
	UAnimSequence* Sequence = Clip(V.CharacterId, Name);
	if (!Sequence || !V.Body) return;
	V.Body->PlayAnimation(Sequence, bLoop);
	V.Body->SetPlayRate(Rate);
	V.Playing = Name;
	ClipPlays.FindOrAdd(Name)++;
}

void ATreadM3BoardPresenter::LaunchBolt(const FString& From, const FString& To, const FLinearColor& Color, float Delay, float Duration)
{
	FBolt* Bolt = Bolts.FindByPredicate([](const FBolt& B) { return !B.bActive; });
	if (!Bolt)
	{
		Bolt = &Bolts.AddDefaulted_GetRef();
		Bolt->Mesh = NewObject<UStaticMeshComponent>(this);
		Bolt->Mesh->SetStaticMesh(BoltMesh);
		Bolt->Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Bolt->Mesh->SetCastShadow(false);
		Bolt->Mesh->SetupAttachment(RootComponent);
		Bolt->Mesh->RegisterComponent();
		if (BoltBase)
		{
			Bolt->Material = UMaterialInstanceDynamic::Create(BoltBase, this);
			Bolt->Material->SetScalarParameterValue(TEXT("Intensity"), 9.0f);
			Bolt->Material->SetScalarParameterValue(TEXT("PulseAmount"), 0.0f);
			Bolt->Mesh->SetMaterial(0, Bolt->Material);
		}
		Owned.Add(Bolt->Mesh);
	}
	if (Bolt->Material) Bolt->Material->SetVectorParameterValue(TEXT("Color"), Color);
	Bolt->From = From;
	Bolt->To = To;
	Bolt->Start = BattleClock + FMath::Max(0.0f, Delay);
	Bolt->Duration = FMath::Max(0.1f, Duration);
	Bolt->bActive = true;
	Bolt->Mesh->SetVisibility(false);
	++BoltCount;
}

void ATreadM3BoardPresenter::SetViewCamera(bool bAudience, bool bManual)
{
	APlayerController* PC = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr;
	if (!PC) return;
	// The board camera is whatever the level put in view (its object name in PIE is not the editor label
	// "Board_Camera"), remembered the first time the presentation takes the view away from it.
	if (!BoardCamera && PC->GetViewTarget() != AudienceCamera.Get()) BoardCamera = Cast<ACameraActor>(PC->GetViewTarget());
	ACameraActor* Target = bAudience ? AudienceCamera.Get() : BoardCamera.Get();
	if (!Target) return;
	if (bManual) bManualCamera = true;
	if (bAudienceView == bAudience && PC->GetViewTarget() == Target) return;
	bAudienceView = bAudience;
	++CameraSwitches;
	PC->SetViewTargetWithBlend(Target, JsonNum(Child(Table, TEXT("camera")), TEXT("blendSec"), 0.6));
}

void ATreadM3BoardPresenter::ToggleAudienceCamera()
{
	if (!bBattleActive) return;
	SetViewCamera(!bAudienceView, true);
}

void ATreadM3BoardPresenter::SetAudienceCameraForTest(bool bAudience)
{
	SetViewCamera(bAudience, true);
}

void ATreadM3BoardPresenter::ResolveKillCamUnit()
{
	if (!KillCamUnitId.IsEmpty())
	{
		return;
	}
	// Fallback when a caller asks for a unit before any kill: strongest own unit, deterministic.
	// One friendly character owns the kill camera for the whole battle: the strongest own unit (highest star, then id)
	// so the UI shows a consistent hero instead of cutting to whoever happened to land the kill.
	FString TopUnit;
	int32 TopStar = -1;
	for (const TPair<FString, FUnitVisual>& Pair : Units)
	{
		const FUnitVisual& V = Pair.Value;
		if (!V.bBattle || V.bEnemy)
		{
			continue;
		}
		if (V.Star > TopStar || (V.Star == TopStar && !TopUnit.IsEmpty() && Pair.Key < TopUnit))
		{
			TopStar = V.Star;
			TopUnit = Pair.Key;
		}
	}
	KillCamUnitId = TopUnit;
}

void ATreadM3BoardPresenter::MoveAudienceCameraToKill(const FVector& VictimLocation)
{
	if (!AudienceCamera)
	{
		return;
	}
	// Stand off on the audience side (+Y, the side the wide shot looks from) and above the roofs, then frame the victim.
	const FVector Standoff(0.0f, KillCamDistanceM * 100.0f, KillCamHeightM * 100.0f);
	const FVector CameraLocation = VictimLocation + Standoff;
	const FVector LookAt = VictimLocation + FVector(0.0f, 0.0f, 1500.0f);
	AudienceCamera->SetActorLocation(CameraLocation);
	AudienceCamera->SetActorRotation((LookAt - CameraLocation).Rotation());
	if (UCameraComponent* Camera = AudienceCamera->GetCameraComponent())
	{
		Camera->SetFieldOfView(KillCamFovDeg);
	}
	bAudienceMoved = true;
}

void ATreadM3BoardPresenter::RestoreAudienceCameraHome()
{
	if (!bAudienceMoved || !AudienceCamera)
	{
		return;
	}
	AudienceCamera->SetActorLocation(AudienceHomeLocation);
	AudienceCamera->SetActorRotation(AudienceHomeRotation);
	if (UCameraComponent* Camera = AudienceCamera->GetCameraComponent())
	{
		Camera->SetFieldOfView(AudienceHomeFov);
	}
	bAudienceMoved = false;
}

// ------------------------------------------------------------------------------------------------ timeline
void ATreadM3BoardPresenter::BeginBattle(const FTreadM1MatchState& State)
{
	bBattleActive = true;
	bBattleFinished = false;
	bBattleNotified = false;
	bManualCamera = false;
	BattleClock = 0.0f;
	Cues.Reset();
	Floats.Reset();
	KillShots = 0;
	KillShotUntil = -1.0f;
	BattleFrames = 0;
	BattleFrameSeconds = 0.0f;
	WorstFrameSeconds = 0.0f;
	FMemory::Memzero(CueCountsByKind);
	SwingCount = SkillSwingCount = BoltCount = VoiceCount = FootstepCount = CameraSwitches = 0;
	ClipPlays.Reset();
	// document/180: capture hook - defer the audience switch to the first battle tick (calling it inside BeginBattle
	// raced the camera spawn in -game runs and produced a black frame).
	bForceAudienceCapture = FParse::Param(FCommandLine::Get(), TEXT("TreadAudienceView"));
	for (FBolt& Bolt : Bolts) { Bolt.bActive = false; if (Bolt.Mesh) Bolt.Mesh->SetVisibility(false); }

	FString HumanId;
	for (const FTreadM1PlayerState& P : State.Players) if (P.bIsHuman) { HumanId = P.PlayerId; break; }
	// The resolver's left side (the pairing's PlayerId) strikes first in every exchange.
	FString LeftId = HumanId;
	for (const FTreadM1BattlePairing& Pair : State.LastBattleResult.Pairings)
	{
		if (Pair.PlayerId == HumanId || Pair.OpponentId == HumanId) { LeftId = Pair.PlayerId; break; }
	}
	const TSharedPtr<FJsonObject>& Facing = FacingTable();
	for (TPair<FString, FUnitVisual>& Pair : Units)
	{
		FUnitVisual& V = Pair.Value;
		V.bBattle = V.UiCell.X >= 0;
		V.Pos = UiCellToWorld(V.UiCell, GroundZ);
		V.Yaw = V.bEnemy ? 180.0f : 0.0f;
		V.ForwardYaw = static_cast<float>(JsonNum(Facing, *V.CharacterId, -90.0));
		V.bMoving = V.bRunning = V.bDead = V.bHidden = V.bWinner = false;
		V.TargetId.Reset();
		V.ActionEndsAt = V.DeadAt = V.HideAt = -1.0f;
		V.HealthMax = V.Health = 0;
		V.Swings = 0;
		V.SkillAt = -100.0f;
		V.QueuedClips.Reset();
		V.Travelled = 0.0f;
		const FTreadM2Card* Card = Controller.IsValid() ? Controller->FindCardData(V.CharacterId) : nullptr;
		V.Profession = Card ? Card->Profession : FString();
		V.bRanged = Card && (Card->AttackKind == TEXT("ranged") || Card->AttackKind == TEXT("heal"));
		V.SkillLabel = Card ? Card->SkillName : FString();
		V.SkillColor = ProfessionColor(V.Profession);
	}

	// Only the human's pairing is on the board; its unit events, in Sequence order, are the whole timeline.
	TArray<const FTreadM1BattleEvent*> Events;
	for (const FTreadM1BattleEvent& Event : State.BattleEvents)
	{
		if (Event.RoundIndex != State.RoundIndex || Event.SourceUnitInstanceId.IsEmpty()) continue;
		if (!Units.Contains(Event.SourceUnitInstanceId) || !Units.Contains(Event.TargetUnitInstanceId)) continue;
		Events.Add(&Event);
	}
	Events.Sort([](const FTreadM1BattleEvent& A, const FTreadM1BattleEvent& B) { return A.Sequence < B.Sequence; });
	int32 Exchanges = 0;
	{
		TMap<FString, int32> Count;
		for (const FTreadM1BattleEvent* Event : Events)
		{
			if (Event->EventType != ETreadM1BattleEventType::UnitDamaged) continue;
			Exchanges = FMath::Max(Exchanges, ++Count.FindOrAdd(Event->SourceUnitInstanceId));
		}
	}
	const float Approach = Timing(TEXT("approachSec"), 3.5f);
	const float Fight = FMath::Clamp(Exchanges * Timing(TEXT("secPerExchange"), 2.2f), Timing(TEXT("fightMinSec"), 8.0f), Timing(TEXT("fightMaxSec"), 27.0f));
	const float Step = Exchanges > 0 ? Fight / Exchanges : 0.0f;
	const float AttackRate = Timing(TEXT("attackPlayRate"), 1.6f);
	const float SkillRate = Timing(TEXT("skillPlayRate"), 1.35f);
	const float ProjectileSec = Timing(TEXT("projectileSec"), 0.55f);
	// When the blow lands after a swing starts: the clip's hit / release point, from the clip planned for that swing.
	auto HitDelay = [&](FUnitVisual& V, int32 SwingIndex, bool bSkill)
	{
		const TSharedPtr<FJsonObject> Row = ProfessionRow(V.Profession);
		TArray<FName> Chain = bSkill ? Names(Row, TEXT("skill")) : TArray<FName>();
		if (Chain.Num() == 0)
		{
			const TArray<FName> Attacks = V.bRanged ? Names(Child(Child(Table, TEXT("attackKinds")), TEXT("ranged")), TEXT("clips")) : Names(Row, TEXT("melee"));
			if (Attacks.Num() > 0) Chain.Add(Attacks[SwingIndex % Attacks.Num()]);
		}
		UAnimSequence* First = Chain.Num() > 0 ? Clip(V.CharacterId, Chain[0]) : nullptr;
		const float Length = First ? First->GetPlayLength() / (bSkill ? SkillRate : AttackRate) : 1.6f;
		if (V.bRanged) return FMath::Clamp(Length * Timing(TEXT("releaseFraction"), 0.5f), 0.3f, 1.4f) + ProjectileSec;
		return FMath::Clamp(Length * Timing(TEXT("hitFraction"), 0.42f), 0.45f, bSkill ? 2.0f : 1.7f);
	};
	TMap<FString, int32> SwingIndex;
	TMap<FString, int32> Slot;
	int32 SlotCount[2] = {0, 0};
	TMap<FString, int32> LastCue;
	for (const FTreadM1BattleEvent* Event : Events)
	{
		const FString& Source = Event->SourceUnitInstanceId;
		const FString& Target = Event->TargetUnitInstanceId;
		switch (Event->EventType)
		{
		case ETreadM1BattleEventType::UnitDamaged:
		{
			const bool bLeft = Event->SourcePlayerId == LeftId;
			int32* UnitSlot = Slot.Find(Source);
			if (!UnitSlot) UnitSlot = &Slot.Add(Source, SlotCount[bLeft ? 0 : 1]++);
			int32& K = SwingIndex.FindOrAdd(Source);
			FBattleCue Cue;
			Cue.Kind = FBattleCue::Attack;
			Cue.Unit = Source;
			Cue.Target = Target;
			Cue.Amount = Event->Amount;
			Cue.HealthAfter = Event->TargetHealthAfter;
			Cue.Sequence = Event->Sequence;
			Cue.Time = Approach + K * Step + (bLeft ? 0.0f : Step * 0.5f) + *UnitSlot * FMath::Min(0.09f, Step * 0.04f);
			Cue.HitDelay = HitDelay(Units[Source], K, false);
			++K;
			LastCue.Add(Source, Cues.Add(Cue));
			FUnitVisual& Victim = Units[Target];
			if (Victim.HealthMax == 0) Victim.HealthMax = Victim.Health = Event->TargetHealthAfter + Event->Amount;
			break;
		}
		case ETreadM1BattleEventType::SkillActivated:
			if (const int32* Index = LastCue.Find(Source))
			{
				Cues[*Index].bSkill = true;
				Cues[*Index].HitDelay = HitDelay(Units[Source], 0, true);
			}
			break;
		case ETreadM1BattleEventType::EnemyFrozen:
			if (const int32* Index = LastCue.Find(Source))
			{
				FBattleCue Cue;
				Cue.Kind = FBattleCue::Frozen;
				Cue.Unit = Target;
				Cue.Target = Source;
				Cue.Sequence = Event->Sequence;
				Cue.Time = Cues[*Index].Time + Cues[*Index].HitDelay + 0.05f;
				Cues.Add(Cue);
			}
			break;
		case ETreadM1BattleEventType::UnitDied:
		{
			FBattleCue Cue;
			Cue.Kind = FBattleCue::Died;
			Cue.Unit = Target;
			Cue.Target = Source;
			Cue.Sequence = Event->Sequence;
			const int32* Index = LastCue.Find(Source);
			Cue.Time = Index ? Cues[*Index].Time + Cues[*Index].HitDelay + 0.1f : Approach;
			Cues.Add(Cue);
			break;
		}
		default:
			break;
		}
	}
	float LastTime = Approach * 0.5f;
	for (const FBattleCue& Cue : Cues) LastTime = FMath::Max(LastTime, Cue.Time + (Cue.Kind == FBattleCue::Attack ? Cue.HitDelay : 0.0f));
	VictoryAt = LastTime + Timing(TEXT("victoryDelaySec"), 0.8f);
	BattleEndAt = VictoryAt + Timing(TEXT("victoryHoldSec"), 3.6f);
	FBattleCue Victory;
	Victory.Kind = FBattleCue::Victory;
	Victory.Time = VictoryAt;
	Cues.Add(Victory);
	Cues.StableSort([](const FBattleCue& A, const FBattleCue& B) { return A.Time < B.Time; });
	for (const FBattleCue& Cue : Cues) ++CueCountsByKind[Cue.Kind];

	// The winner is the resolver's verdict for the human (document/12 §5: never derived by the presentation).
	WinnerSide = TEXT("draw");
	for (const FTreadM1BattleOutcome& Outcome : State.LastBattleResult.Outcomes)
	{
		if (Outcome.PlayerId == HumanId) WinnerSide = Outcome.Outcome == TEXT("Win") ? TEXT("own") : TEXT("enemy");
	}
	for (TPair<FString, FUnitVisual>& Pair : Units)
	{
		Pair.Value.bWinner = (WinnerSide == TEXT("own")) != Pair.Value.bEnemy && WinnerSide != TEXT("draw");
	}
	// document/162 §4.5: one friendly unit owns the kill camera for the battle - the first of ours to land a kill.
	if (!bKillCamUnitPinned)
	{
		KillCamUnitId.Reset();
	}
	// Leader battles open on the audience camera; otherwise the first knockout gets a short close-up.
	if (State.RoundType == ETreadM1RoundType::Leader) SetViewCamera(true, false);
	if (UTreadAudioDirector* Audio = UTreadAudioDirector::Get(this)) Audio->StopVoice();
}

void ATreadM3BoardPresenter::EndBattle()
{
	bBattleActive = false;
	bBattleFinished = false;
	BattleRound = -1;
	Cues.Reset();
	Floats.Reset();
	for (FBolt& Bolt : Bolts) { Bolt.bActive = false; if (Bolt.Mesh) Bolt.Mesh->SetVisibility(false); }
	for (TPair<FString, FUnitVisual>& Pair : Units)
	{
		FUnitVisual& V = Pair.Value;
		V.bBattle = V.bDead = V.bHidden = V.bMoving = false;
		V.QueuedClips.Reset();
		V.ActionEndsAt = -1.0f;
		if (V.Body && V.Idle)
		{
			V.Body->PlayAnimation(V.Idle, true);
			V.Body->SetPlayRate(1.0f);
		}
	}
	SetViewCamera(false, false);
	bManualCamera = false;
}

// ------------------------------------------------------------------------------------------------ playback
void ATreadM3BoardPresenter::Swing(FUnitVisual& V, const FBattleCue& Cue)
{
	const float Now = BattleClock;
	// A one-shot still playing is not restarted (no snapping back to frame 0): the blow lands without a new swing.
	if (V.bDead || V.ActionEndsAt > Now) return;
	FUnitVisual* Target = Units.Find(Cue.Target);
	if (!Target) return;
	const float Scale = UnitHeight(V) / FMath::Max(UnitHeightCm, 1.0f);
	const float Range = (V.bRanged ? Movement(TEXT("rangedRangeCells"), 3.2f) : Movement(TEXT("meleeRangeCells"), 0.8f)) * CellCm * FMath::Max(1.0f, Scale);
	if (!V.bRanged && (Target->Pos - V.Pos).Size2D() > Range * 1.6f) return;
	const TSharedPtr<FJsonObject> Row = ProfessionRow(V.Profession);
	TArray<FName> Chain = Cue.bSkill ? Names(Row, TEXT("skill")) : TArray<FName>();
	if (Chain.Num() == 0)
	{
		const TArray<FName> Attacks = V.bRanged ? Names(Child(Child(Table, TEXT("attackKinds")), TEXT("ranged")), TEXT("clips")) : Names(Row, TEXT("melee"));
		if (Attacks.Num() > 0) Chain.Add(Attacks[V.Swings % Attacks.Num()]);
	}
	Chain.RemoveAll([this, &V](FName Name) { return Clip(V.CharacterId, Name) == nullptr; });
	if (Chain.Num() == 0) return;
	const float Rate = Cue.bSkill ? Timing(TEXT("skillPlayRate"), 1.35f) : Timing(TEXT("attackPlayRate"), 1.6f);
	V.bMoving = false;
	PlayClip(V, Chain[0], false, Rate);
	V.ActionEndsAt = Now + Clip(V.CharacterId, Chain[0])->GetPlayLength() / Rate;
	V.QueuedClips = Chain;
	V.QueuedClips.RemoveAt(0);
	++V.Swings;
	++SwingCount;
	if (V.bRanged)
	{
		const FLinearColor Color = Cue.bSkill ? V.SkillColor : FLinearColor(1.0f, 0.92f, 0.65f);
		const float ProjectileSec = Timing(TEXT("projectileSec"), 0.55f);
		LaunchBolt(Cue.Unit, Cue.Target, Color, Cue.HitDelay - ProjectileSec, ProjectileSec);
	}
	if (Cue.bSkill)
	{
		++SkillSwingCount;
		V.SkillAt = Now;
		if (UTreadAudioDirector* Audio = UTreadAudioDirector::Get(this))
		{
			Audio->PlaySfx(TEXT("skill_cast"));
			if (!V.bHidden && Audio->PlayVoice(V.CharacterId, 1)) ++VoiceCount;
		}
	}
}

void ATreadM3BoardPresenter::SteerUnit(const FString& Id, FUnitVisual& V, float DeltaSeconds)
{
	const float Now = BattleClock;
	const float TurnRate = Timing(TEXT("turnDegPerSec"), 240.0f);
	auto Face = [&](const FVector& Direction)
	{
		if (Direction.SizeSquared2D() < 1.0f) return;
		V.Yaw = FMath::FixedTurn(V.Yaw, YawOf(Direction) - V.ForwardYaw, TurnRate * DeltaSeconds);
	};
	auto Stop = [&]()
	{
		if (V.bMoving && V.ActionEndsAt <= Now) PlayClip(V, TEXT("Idle"), true, 1.0f);
		V.bMoving = false;
	};
	if (V.bDead || !V.bBattle || Now >= VictoryAt) { Stop(); return; }
	// Heading for the target of the unit's next swing (its current one until then).
	float NextCueTime = BattleEndAt;
	FString NextTarget = V.TargetId;
	for (const FBattleCue& Cue : Cues)
	{
		if (Cue.Kind == FBattleCue::Attack && !Cue.bDone && Cue.Unit == Id) { NextCueTime = Cue.Time; NextTarget = Cue.Target; break; }
	}
	FUnitVisual* Target = NextTarget.IsEmpty() ? nullptr : Units.Find(NextTarget);
	if (!Target)
	{
		// No events for this unit (it never attacks): advance towards the nearest living enemy anyway.
		float Best = TNumericLimits<float>::Max();
		for (TPair<FString, FUnitVisual>& Other : Units)
		{
			if (Other.Value.bEnemy == V.bEnemy || Other.Value.bDead || !Other.Value.bBattle) continue;
			const float D = (Other.Value.Pos - V.Pos).SizeSquared2D();
			if (D < Best) { Best = D; Target = &Other.Value; }
		}
		NextCueTime = FMath::Max(NextCueTime, Timing(TEXT("approachSec"), 3.5f));
	}
	if (!Target || (Target->bDead && NextTarget.IsEmpty())) { Stop(); return; }
	const FVector ToTarget = Target->Pos - V.Pos;
	const float Scale = UnitHeight(V) / FMath::Max(UnitHeightCm, 1.0f);
	const float Range = (V.bRanged ? Movement(TEXT("rangedRangeCells"), 3.2f) : Movement(TEXT("meleeRangeCells"), 0.8f)) * CellCm * FMath::Max(1.0f, Scale);
	if (V.ActionEndsAt > Now || ToTarget.Size2D() <= Range * 1.05f)
	{
		Stop();
		Face(ToTarget);
		return;
	}
	const FVector Goal = Target->Pos - ToTarget.GetSafeNormal2D() * Range;
	const FVector ToGoal = Goal - V.Pos;
	const float GoalDistance = ToGoal.Size2D();
	const float Walk = Movement(TEXT("walkCellsPerSec"), 0.98f) * CellCm * Scale;
	const float Run = Movement(TEXT("runCellsPerSec"), 1.96f) * CellCm * Scale;
	const float TimeLeft = FMath::Max(Movement(TEXT("minMoveSec"), 0.8f), NextCueTime - Now - 0.1f);
	const float Speed = FMath::Clamp(GoalDistance / TimeLeft, Walk * 0.7f, Run * 1.25f);
	const bool bRun = Speed > Walk * 1.35f;
	if (!V.bMoving || bRun != V.bRunning)
	{
		// Play rate follows the ground speed so the feet roughly keep up (in-place GP walk / run loops).
		PlayClip(V, bRun ? TEXT("Run") : TEXT("Walk"), true, FMath::Clamp(Speed / (bRun ? Run : Walk), 0.6f, 1.5f));
	}
	V.bMoving = true;
	V.bRunning = bRun;
	const float StepLength = FMath::Min(GoalDistance, Speed * DeltaSeconds);
	V.Pos += ToGoal.GetSafeNormal2D() * StepLength;
	V.Travelled += StepLength;
	Face(ToGoal);
}

void ATreadM3BoardPresenter::TickBattle(float DeltaSeconds)
{
	BattleClock += DeltaSeconds;
	if (bForceAudienceCapture && BattleClock > 0.2f)
	{
		bForceAudienceCapture = false;
		SetViewCamera(true, false);
	}
	const float Now = BattleClock;
	if (!bBattleFinished && DeltaSeconds > 0.0f)
	{
		++BattleFrames;
		BattleFrameSeconds += DeltaSeconds;
		// The first frames load clips synchronously; they are not what the battle runs at.
		if (BattleFrames > 10) WorstFrameSeconds = FMath::Max(WorstFrameSeconds, DeltaSeconds);
	}
	const float FloaterSec = Timing(TEXT("floaterSec"), 1.4f);
	for (FBattleCue& Cue : Cues)
	{
		if (Cue.Time > Now) break;
		if (!Cue.bDone)
		{
			Cue.bDone = true;
			FUnitVisual* V = Cue.Unit.IsEmpty() ? nullptr : Units.Find(Cue.Unit);
			switch (Cue.Kind)
			{
			case FBattleCue::Attack:
				if (V && !V->bDead)
				{
					V->TargetId = Cue.Target;
					Swing(*V, Cue);
				}
				break;
			case FBattleCue::Frozen:
				if (V && !V->bDead) Floats.Add({Cue.Unit, TEXT("冻结"), FLinearColor(0.45f, 0.85f, 1.0f), Now, false});
				break;
			case FBattleCue::Died:
				if (V && !V->bDead)
				{
					V->bDead = true;
					V->bMoving = false;
					V->Health = 0;
					V->QueuedClips.Reset();
					const float Rate = Timing(TEXT("defeatPlayRate"), 1.7f);
					PlayClip(*V, TEXT("Defeat"), false, Rate);
					UAnimSequence* Defeat = Clip(V->CharacterId, TEXT("Defeat"));
					V->DeadAt = Now;
					V->HideAt = Now + (Defeat ? Defeat->GetPlayLength() / Rate : 1.0f) + Timing(TEXT("defeatHoldSec"), 1.0f);
					Floats.Add({Cue.Unit, TEXT("击倒"), FLinearColor(1.0f, 0.35f, 0.25f), Now, true});
					// document/163: the body itself comes down - crush the buildings it lands on.
					if (ATreadBuildingDestructionManager* Destruction = FindDestructionManager(GetWorld()))
					{
						Destruction->ApplyTrample(V->Pos, FMath::Clamp(V->Scale, 0.6f, 2.5f) * 18.0f, 1.0f, 400.0f);
					}
					// The UI features exactly one of our characters on the kill camera: the first one of ours to land a
					// kill claims it, and every later shot stays on that unit (doc 162 §4.5).
					if (KillCamUnitId.IsEmpty() && !Cue.Target.IsEmpty())
					{
						if (const FUnitVisual* Killer = Units.Find(Cue.Target))
						{
							if (!Killer->bEnemy && Killer->bBattle)
							{
								KillCamUnitId = Cue.Target;
							}
						}
					}
					const bool bOurKill = !KillCamUnitId.IsEmpty() && Cue.Target == KillCamUnitId;
					// document/187: kill shots belong to the audience camera only. In the top-down board view the
					// cut-away hid the board for 2.6 s, which the owner does not want.
					if (!bManualCamera && KillShots == 0 && bAudienceView && bOurKill)
					{
						++KillShots;
						MoveAudienceCameraToKill(V->Pos);
						SetViewCamera(true, false);
						KillShotUntil = Now + JsonNum(Child(Table, TEXT("camera")), TEXT("killShotSec"), 2.6);
					}
				}
				break;
			case FBattleCue::Victory:
			{
				bool bVoiced = false;
				for (TPair<FString, FUnitVisual>& Pair : Units)
				{
					FUnitVisual& U = Pair.Value;
					if (!U.bBattle || U.bDead) continue;
					U.bMoving = false;
					U.QueuedClips.Reset();
					U.ActionEndsAt = -1.0f;
					PlayClip(U, U.bWinner ? FName(TEXT("Victory")) : FName(TEXT("Idle")), !U.bWinner, 1.0f);
					if (U.bWinner && !U.bEnemy && !bVoiced)
					{
						if (UTreadAudioDirector* Audio = UTreadAudioDirector::Get(this)) bVoiced = Audio->PlayVoice(U.CharacterId, 0);
						VoiceCount += bVoiced ? 1 : 0;
					}
				}
				break;
			}
			}
		}
		if (Cue.Kind == FBattleCue::Attack && !Cue.bHitDone && Now >= Cue.Time + Cue.HitDelay)
		{
			Cue.bHitDone = true;
			// document/162 §4.6: the blow lands -> the ground under the attacker is trampled. 45 m foot radius scaled by
			// the unit's growth; skill blows (Stomp / Crush / KneelSmash) cover more and hit harder. The destruction
			// manager then damages/collapses the buildings there and spawns the dust on the audience/kill camera.
			if (FUnitVisual* Attacker = Units.Find(Cue.Unit))
			{
				if (ATreadBuildingDestructionManager* Destruction = FindDestructionManager(GetWorld()))
				{
					// A real footprint, not a cell: 12 m per unit of scale (max 30 m). The whole-block look came from
					// the old 45 m per scale, which covered the entire ring (document/163).
					const float FootRadius = FMath::Clamp(Attacker->Scale, 0.6f, 2.5f) * 12.0f;
					Destruction->ApplyTrample(Attacker->Pos, FootRadius, Cue.bSkill ? 0.6f : 0.35f,
						Cue.bSkill ? 200.0f : 80.0f);
				}
			}
			if (FUnitVisual* Victim = Units.Find(Cue.Target))
			{
				Victim->Health = FMath::Min(Victim->Health, Cue.HealthAfter);
				Floats.Add({Cue.Target, FString::Printf(TEXT("-%d"), Cue.Amount),
					Victim->bEnemy ? FLinearColor(1.0f, 0.93f, 0.55f) : FLinearColor(1.0f, 0.45f, 0.38f), Now, Cue.bSkill});
			}
		}
	}
	for (TPair<FString, FUnitVisual>& Pair : Units)
	{
		FUnitVisual& V = Pair.Value;
		if (!V.bBattle) continue;
		if (!V.bDead && V.ActionEndsAt > 0.0f && Now >= V.ActionEndsAt)
		{
			V.ActionEndsAt = -1.0f;
			if (V.QueuedClips.Num() > 0)
			{
				// Skill chains such as Grab -> Hold -> Throw continue clip by clip.
				const FName Next = V.QueuedClips[0];
				V.QueuedClips.RemoveAt(0);
				const float Rate = Timing(TEXT("skillPlayRate"), 1.35f);
				PlayClip(V, Next, false, Rate);
				if (UAnimSequence* Sequence = Clip(V.CharacterId, Next)) V.ActionEndsAt = Now + Sequence->GetPlayLength() / Rate;
			}
			else if (Now < VictoryAt)
			{
				PlayClip(V, TEXT("Idle"), true, 1.0f);
			}
		}
		if (V.HideAt > 0.0f && Now >= V.HideAt) V.bHidden = true;
		SteerUnit(Pair.Key, V, DeltaSeconds);
	}
	// Keep bodies from sinking into each other where several attackers converge on one target.
	TArray<FUnitVisual*> Living;
	for (TPair<FString, FUnitVisual>& Pair : Units) if (Pair.Value.bBattle && !Pair.Value.bDead) Living.Add(&Pair.Value);
	const float MinGap = 0.42f * CellCm;
	for (int32 A = 0; A < Living.Num(); ++A)
	{
		for (int32 B = A + 1; B < Living.Num(); ++B)
		{
			FVector Delta = Living[B]->Pos - Living[A]->Pos;
			Delta.Z = 0.0f;
			const float Distance = Delta.Size();
			if (Distance >= MinGap) continue;
			const FVector Push = (Distance > 1.0f ? Delta / Distance : FVector(0.0f, A < B ? 1.0f : -1.0f, 0.0f)) * (MinGap - Distance) * 0.5f;
			Living[A]->Pos -= Push;
			Living[B]->Pos += Push;
		}
	}
	// Projectiles fly chest to chest; their arrival is the cue's hit time.
	for (FBolt& Bolt : Bolts)
	{
		if (!Bolt.bActive) continue;
		const FUnitVisual* From = Units.Find(Bolt.From);
		const FUnitVisual* To = Units.Find(Bolt.To);
		const float Alpha = (Now - Bolt.Start) / Bolt.Duration;
		if (!From || !To || Alpha >= 1.0f) { Bolt.bActive = false; Bolt.Mesh->SetVisibility(false); continue; }
		if (Alpha < 0.0f) continue;
		const FVector A = ChestOf(*From);
		const FVector B = ChestOf(*To);
		const FVector Direction = (B - A).GetSafeNormal();
		Bolt.Mesh->SetWorldLocationAndRotation(FMath::Lerp(A, B, Alpha), Direction.Rotation());
		Bolt.Mesh->SetWorldScale3D(FVector(28.0f, 3.5f, 3.5f));
		Bolt.Mesh->SetVisibility(true);
	}
	Floats.RemoveAll([Now, FloaterSec](const FFloat& F) { return Now - F.Born >= FloaterSec; });
	// Footsteps: one shared, throttled step while anything visible walks (no stacked stomps).
	bool bAnyMoving = false;
	for (const TPair<FString, FUnitVisual>& Pair : Units) bAnyMoving |= Pair.Value.bMoving && !Pair.Value.bHidden;
	if (bAnyMoving && Now - LastFootstep >= 0.42f)
	{
		LastFootstep = Now;
		if (UTreadAudioDirector* Audio = UTreadAudioDirector::Get(this)) { if (Audio->PlayFootstep()) ++FootstepCount; }
	}
	if (KillShotUntil > 0.0f && Now >= KillShotUntil)
	{
		KillShotUntil = -1.0f;
		RestoreAudienceCameraHome();
		const bool bLeader = Controller.IsValid() && Controller->MatchState.RoundType == ETreadM1RoundType::Leader;
		if (!bManualCamera && !bLeader) SetViewCamera(false, false);
	}
	if (!bBattleFinished && Now >= BattleEndAt)
	{
		bBattleFinished = true;
		if (!bManualCamera) SetViewCamera(false, false);
		if (Controller.IsValid() && !bBattleNotified)
		{
			bBattleNotified = true;
			Controller->NotifyBattlePresentationFinished();
		}
	}
}

// ------------------------------------------------------------------------------------------------ HUD / tests
void ATreadM3BoardPresenter::GetFloaters(TArray<FTreadM3Floater>& Out) const
{
	Out.Reset();
	if (!bBattleActive) return;
	const float FloaterSec = Timing(TEXT("floaterSec"), 1.4f);
	for (const FFloat& F : Floats)
	{
		const FUnitVisual* V = Units.Find(F.Unit);
		if (!V) continue;
		FTreadM3Floater Floater;
		Floater.Age01 = FMath::Clamp((BattleClock - F.Born) / FloaterSec, 0.0f, 1.0f);
		const float Height = UnitHeight(*V);
		Floater.World = V->Pos + FVector(0.0f, 0.0f, Height * (1.12f + 0.22f * Floater.Age01));
		Floater.Text = F.Text;
		Floater.Color = F.Color;
		Floater.bBig = F.bBig;
		Out.Add(Floater);
	}
}

FString ATreadM3BoardPresenter::GetBattleTimelineDigest() const
{
	FString Out = FString::Printf(TEXT("winner=%s victory=%.2f end=%.2f;"), *WinnerSide, VictoryAt, BattleEndAt);
	for (const FBattleCue& Cue : Cues)
	{
		Out += FString::Printf(TEXT("%d:%s>%s@%.2f/%d/%d%s;"), static_cast<int32>(Cue.Kind), *Cue.Unit, *Cue.Target, Cue.Time,
			Cue.Amount, Cue.HealthAfter, Cue.bSkill ? TEXT("S") : TEXT(""));
	}
	return Out;
}

FString ATreadM3BoardPresenter::GetBattlePresentationReport() const
{
	const TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetBoolField(TEXT("active"), bBattleActive);
	Root->SetBoolField(TEXT("finished"), bBattleFinished);
	Root->SetNumberField(TEXT("clock"), BattleClock);
	Root->SetNumberField(TEXT("victoryAt"), VictoryAt);
	Root->SetNumberField(TEXT("endAt"), BattleEndAt);
	Root->SetStringField(TEXT("winner"), WinnerSide);
	Root->SetNumberField(TEXT("attackCues"), CueCountsByKind[FBattleCue::Attack]);
	Root->SetNumberField(TEXT("diedCues"), CueCountsByKind[FBattleCue::Died]);
	Root->SetNumberField(TEXT("frozenCues"), CueCountsByKind[FBattleCue::Frozen]);
	Root->SetNumberField(TEXT("swings"), SwingCount);
	Root->SetNumberField(TEXT("skillSwings"), SkillSwingCount);
	Root->SetNumberField(TEXT("bolts"), BoltCount);
	Root->SetNumberField(TEXT("voices"), VoiceCount);
	Root->SetNumberField(TEXT("footsteps"), FootstepCount);
	Root->SetNumberField(TEXT("cameraSwitches"), CameraSwitches);
	Root->SetBoolField(TEXT("audienceView"), bAudienceView);
	Root->SetNumberField(TEXT("floaters"), Floats.Num());
	Root->SetNumberField(TEXT("frames"), BattleFrames);
	Root->SetNumberField(TEXT("avgFps"), BattleFrameSeconds > 0.0f ? BattleFrames / BattleFrameSeconds : 0.0f);
	Root->SetNumberField(TEXT("worstFrameMs"), WorstFrameSeconds * 1000.0f);
	const TSharedRef<FJsonObject> Clips = MakeShared<FJsonObject>();
	for (const TPair<FName, int32>& Pair : ClipPlays) Clips->SetNumberField(Pair.Key.ToString(), Pair.Value);
	Root->SetObjectField(TEXT("clipPlays"), Clips);
	TArray<TSharedPtr<FJsonValue>> UnitRows;
	for (const TPair<FString, FUnitVisual>& Pair : Units)
	{
		const FUnitVisual& V = Pair.Value;
		if (!V.bBattle) continue;
		const TSharedRef<FJsonObject> Row = MakeShared<FJsonObject>();
		Row->SetStringField(TEXT("unit"), Pair.Key);
		Row->SetStringField(TEXT("characterId"), V.CharacterId);
		Row->SetBoolField(TEXT("enemy"), V.bEnemy);
		Row->SetBoolField(TEXT("ranged"), V.bRanged);
		Row->SetBoolField(TEXT("dead"), V.bDead);
		Row->SetBoolField(TEXT("hidden"), V.bHidden);
		Row->SetBoolField(TEXT("winner"), V.bWinner);
		Row->SetNumberField(TEXT("swings"), V.Swings);
		Row->SetNumberField(TEXT("travelledCells"), V.Travelled / CellCm);
		Row->SetNumberField(TEXT("health"), V.Health);
		Row->SetNumberField(TEXT("healthMax"), V.HealthMax);
		Row->SetNumberField(TEXT("forwardYaw"), V.ForwardYaw);
		Row->SetStringField(TEXT("playing"), V.Playing.ToString());
		UnitRows.Add(MakeShared<FJsonValueObject>(Row));
	}
	Root->SetArrayField(TEXT("units"), UnitRows);
	FString Out;
	FJsonSerializer::Serialize(Root, TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Out));
	return Out;
}
