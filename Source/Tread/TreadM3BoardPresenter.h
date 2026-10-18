#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "TreadM1DataTypes.h"
#include "TreadM3BoardPresenter.generated.h"

class ATreadM1MatchController;
class USkeletalMesh;
class USkeletalMeshComponent;
class UStaticMesh;
class UStaticMeshComponent;
class UMaterialInterface;
class UMaterialInstanceDynamic;
class UAnimSequence;
class APlayerController;
class ACameraActor;
class FJsonObject;

/** One unit standing on the 3D board, as the HUD needs it for labels. */
struct FTreadM3UnitAnchor
{
	FString UnitInstanceId;
	FString CharacterId;
	bool bEnemy = false;
	FVector HeadWorld = FVector::ZeroVector;
	FIntPoint UiCell = FIntPoint(-1, -1);
	/** document/12 battle presentation: knocked-out state and the skill being cast. */
	bool bDead = false;
	FString SkillLabel;
	FLinearColor SkillColor = FLinearColor::White;
	float SkillAge01 = 1.0f;
};

/** A damage / status number rising above a unit during the battle presentation (document/12 §6). */
struct FTreadM3Floater
{
	FVector World = FVector::ZeroVector;
	FString Text;
	FLinearColor Color = FLinearColor::White;
	/** 0 when it appears, 1 when it is gone. */
	float Age01 = 0.0f;
	bool bBig = false;
};

/** The mesh and the two looping GP clips one character stands with. */
USTRUCT()
struct FTreadM3CharacterVisuals
{
	GENERATED_BODY()

	UPROPERTY() TObjectPtr<USkeletalMesh> Mesh;
	UPROPERTY() TObjectPtr<UAnimSequence> Idle;
	UPROPERTY() TObjectPtr<UAnimSequence> Growth;
	/** Battle clips by GP name ("Walk", "Kick", ...), loaded on first use from the same set as Idle. */
	UPROPERTY() TMap<FName, TObjectPtr<UAnimSequence>> Clips;
	/** Folder of the character's own retargeted clips, or "" for the hero set. */
	FString AnimFolder;
	/** Yaw (deg) of the model's anatomical front in component space, from its leg / shoulder bones. */
	float ForwardYaw = -90.0f;
};

/**
 * M3: puts the match onto the 3D Paris board. Spawned by ATreadM1GameMode on M3 maps only (M1 keeps its 2D grid).
 * UI cell (X = column west->east, Y = row from the top of the screen) maps to the board cell of
 * Tools/paris/paris_common.py: world X = (3.5 - Y) * 200 m (north up-screen), world Y = (X - 3.5) * 200 m.
 * Every unit stands as its own character model, scaled by star, on a blue (own) or red (opponent) ring: char_101..112
 * are the imported MMD meshes (Tools/m4/n2_build_retarget.py) and char_002..char_100 the roster VRMs
 * (Tools/m4/m4_build_retarget.py), each playing the GP clips retargeted onto it; char_001 and any character without
 * an import is the Clukay416 VRM body + face (leader pose) playing the original A_GP clips. A star-up plays A_GP_Growth while the
 * scale eases to the new size. The hovered drop cell gets a yellow (allowed) or red (blocked) frame. The template actors
 * placed by M0 are hidden.
 */
UCLASS()
class TREAD_API ATreadM3BoardPresenter : public AActor
{
	GENERATED_BODY()

public:
	ATreadM3BoardPresenter();
	virtual void Tick(float DeltaSeconds) override;

	static constexpr float CellCm = 20000.0f;

	static FVector UiCellToWorld(FIntPoint UiCell, float Z = 0.0f);
	/** Ray from the viewport pixel through the scene onto the ground plane; false when it misses the 8x8 board. */
	bool ViewportPixelToUiCell(const APlayerController* PC, FVector2D Pixel, FIntPoint& OutCell) const;
	/** Bounding rect of the projected board in viewport pixels (for the board press button). */
	bool ProjectBoardRect(const APlayerController* PC, FVector2D& OutMin, FVector2D& OutMax) const;

	void SetHoverCell(FIntPoint UiCell, bool bAllowed);
	void SetDraggedUnit(const FString& UnitInstanceId) { DraggedUnitId = UnitInstanceId; }
	void GetAnchors(TArray<FTreadM3UnitAnchor>& Out) const;
	const FString& GetOpponentId() const { return OpponentId; }
	int32 GetStarUpCount() const { return StarUpCount; }

	/** document/12: floating numbers of the running battle presentation. */
	void GetFloaters(TArray<FTreadM3Floater>& Out) const;
	bool IsBattlePresenting() const { return bBattleActive && !bBattleFinished; }
	/** Board_Camera <-> Audience_Camera (document/125 §4): mouse toggle during the battle, never a hotkey. */
	void ToggleAudienceCamera();
	bool IsAudienceCamera() const { return bAudienceView; }

	/** document/162 §4.5: the one friendly character the kill camera follows (empty = pick the strongest own unit).
	 *  The UI shows a single own character's kill shots instead of cutting to a different unit every fight. */
	void SetKillCamUnit(const FString& UnitId) { KillCamUnitId = UnitId; bKillCamUnitPinned = !UnitId.IsEmpty(); }
	/** Evidence hook: put the kill camera on a world location without a real kill (stand-alone destruction test). */
	void MoveAudienceCameraForTest(const FVector& VictimLocation) { MoveAudienceCameraToKill(VictimLocation); }
	const FString& GetKillCamUnit() const { return KillCamUnitId; }

	/** Test/evidence hooks (Tools/battle/battle_presentation_check.py). */
	UFUNCTION(BlueprintPure, Category = "Battle|Test")
	FString GetBattleTimelineDigest() const;
	UFUNCTION(BlueprintPure, Category = "Battle|Test")
	FString GetBattlePresentationReport() const;
	UFUNCTION(BlueprintPure, Category = "Battle|Test")
	float GetBattleClock() const { return bBattleActive ? BattleClock : -1.0f; }
	UFUNCTION(BlueprintCallable, Category = "Battle|Test")
	void SetAudienceCameraForTest(bool bAudience);

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;

private:
	struct FUnitVisual
	{
		TObjectPtr<USkeletalMeshComponent> Body;
		TObjectPtr<USkeletalMeshComponent> Face;
		/** Health arc (document/159): a per-unit dynamic instance of MI_UnitRing_Blue / _Red whose HealthFraction
		 *  cuts the ring open at 6 o'clock; the gap grows as the unit loses health. */
		TObjectPtr<UStaticMeshComponent> Ring;
		/** Dark base ring under the arc, so the gap reads as a track instead of a hole in the ground. */
		TObjectPtr<UStaticMeshComponent> RingTrack;
		TObjectPtr<UMaterialInstanceDynamic> RingMaterial;
		/** This unit's own clips: the hero's, or the retargeted copy that matches its own mesh. */
		TObjectPtr<UAnimSequence> Idle;
		TObjectPtr<UAnimSequence> Growth;
		FString CharacterId;
		FString Tier;
		FString OwnerId;
		int32 Star = 1;
		bool bEnemy = false;
		FIntPoint UiCell = FIntPoint(-1, -1);
		float Scale = 1.0f;
		float FromScale = 1.0f;
		float GrowT = 1.0f;  // 0..1 while a star-up plays
		bool bSeen = false;
		// --- battle presentation (document/12) ---
		FVector Pos = FVector::ZeroVector;   // ground position while the battle moves the unit off its cell
		float Yaw = 0.0f;                    // world yaw of the component
		float ForwardYaw = -90.0f;
		bool bBattle = false;
		bool bMoving = false;
		bool bRunning = false;
		bool bDead = false;
		bool bHidden = false;
		bool bRanged = false;
		bool bWinner = false;
		FString Profession;
		FString TargetId;
		float ActionEndsAt = -1.0f;
		float DeadAt = -1.0f;
		float HideAt = -1.0f;
		int32 HealthMax = 0;
		int32 Health = 0;
		int32 Swings = 0;
		FString SkillLabel;
		FLinearColor SkillColor = FLinearColor::White;
		float SkillAt = -100.0f;
		TArray<FName> QueuedClips;
		FName Playing;
		float Travelled = 0.0f;
	};

	/** One step of the battle timeline, all derived from MatchState.BattleEvents (Sequence order). */
	struct FBattleCue
	{
		enum EKind : uint8 { Attack, Died, Frozen, Victory };
		float Time = 0.0f;
		EKind Kind = Attack;
		FString Unit;
		FString Target;
		int32 Amount = 0;
		int32 HealthAfter = 0;
		int32 Sequence = 0;
		bool bSkill = false;
		float HitDelay = 0.8f;
		bool bDone = false;
		bool bHitDone = false;
	};

	struct FBolt
	{
		TObjectPtr<UStaticMeshComponent> Mesh;
		TObjectPtr<UMaterialInstanceDynamic> Material;
		FString From;
		FString To;
		float Start = 0.0f;
		float Duration = 0.5f;
		bool bActive = false;
	};

	struct FFloat
	{
		FString Unit;
		FString Text;
		FLinearColor Color = FLinearColor::White;
		float Born = 0.0f;
		bool bBig = false;
	};

	void FindTemplates();
	void Sync();
	/** Mesh and clips for one character; a character without its own model resolves to the M1 hero. */
	const FTreadM3CharacterVisuals& ResolveCharacterVisuals(const FString& CharacterId);

	FUnitVisual& Spawn(const FString& Id, const FTreadM1UnitInstance& Unit, bool bEnemy);
	void Place(FUnitVisual& V);

	// --- battle presentation (TreadM3BattlePresentation.cpp) ---
	void LoadPresentationTable();
	UAnimSequence* Clip(const FString& CharacterId, FName Name);
	void BeginBattle(const FTreadM1MatchState& State);
	void TickBattle(float DeltaSeconds);
	void EndBattle();
	void Swing(FUnitVisual& V, const FBattleCue& Cue);
	void PlayClip(FUnitVisual& V, FName Name, bool bLoop, float Rate);
	void SteerUnit(const FString& Id, FUnitVisual& V, float DeltaSeconds);
	void LaunchBolt(const FString& From, const FString& To, const FLinearColor& Color, float Delay, float Duration);
	FVector ChestOf(const FUnitVisual& V) const;
	float UnitHeight(const FUnitVisual& V) const;
	void SetViewCamera(bool bAudience, bool bManual);
	/** Picks the friendly unit the kill camera follows: highest star, then id (deterministic). */
	void ResolveKillCamUnit();
	/** Moves the audience camera next to a victim and widens it for the close-up; RestoreAudienceCameraHome undoes it. */
	void MoveAudienceCameraToKill(const FVector& VictimLocation);
	void RestoreAudienceCameraHome();
	TSharedPtr<FJsonObject> ProfessionRow(const FString& Profession) const;
	FLinearColor ProfessionColor(const FString& Profession) const;
	float Timing(const TCHAR* Key, float Default) const;
	float Movement(const TCHAR* Key, float Default) const;
	// document/179: +20% visual scale so the giants read at the 1.7 km board camera (owner feedback "too small").
	float StarScale(int32 Star) const { return BaseScale * 1.2f * (1.0f + 0.18f * (FMath::Clamp(Star, 1, 3) - 1)); }

	TWeakObjectPtr<ATreadM1MatchController> Controller;
	TMap<FString, FUnitVisual> Units;
	/** Highest star seen per owner + character (detects combines / star-ups). */
	TMap<FString, int32> BestStar;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> HoverFrame;
	UPROPERTY() TObjectPtr<USkeletalMesh> BodyMesh;
	/** CharacterId -> mesh and clips; a character without its own model resolves to the M1 hero. */
	UPROPERTY() TMap<FString, FTreadM3CharacterVisuals> CharacterVisualCache;
	UPROPERTY() TObjectPtr<USkeletalMesh> FaceMesh;
	UPROPERTY() TArray<TObjectPtr<UMaterialInterface>> BodyMaterials;
	UPROPERTY() TArray<TObjectPtr<UMaterialInterface>> FaceMaterials;
	UPROPERTY() TObjectPtr<UStaticMesh> RingMesh;
	UPROPERTY() TObjectPtr<UMaterialInterface> RingBlue;
	UPROPERTY() TObjectPtr<UMaterialInterface> RingRed;
	UPROPERTY() TObjectPtr<UMaterialInterface> RingTrackMaterial;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> HoverMaterial;
	UPROPERTY() TObjectPtr<UAnimSequence> IdleAnim;
	UPROPERTY() TObjectPtr<UAnimSequence> GrowthAnim;
	/** Components are created at runtime; keep them referenced. */
	UPROPERTY() TArray<TObjectPtr<UActorComponent>> Owned;
	float BaseScale = 1.0f;
	float RingScale = 1.0f;
	float GroundZ = 0.0f;
	float RingZ = 0.0f;
	float UnitHeightCm = 11500.0f;
	FString DraggedUnitId;
	FString OpponentId;
	int32 StarUpCount = 0;

	// --- battle presentation state ---
	TSharedPtr<FJsonObject> Table;
	TArray<FBattleCue> Cues;
	TArray<FBolt> Bolts;
	TArray<FFloat> Floats;
	int32 BattleRound = -1;
	bool bBattleActive = false;
	bool bBattleFinished = false;
	bool bBattleNotified = false;
	float BattleClock = 0.0f;
	float VictoryAt = 0.0f;
	float BattleEndAt = 0.0f;
	float LastFootstep = -10.0f;
	int32 KillShots = 0;
	float KillShotUntil = -1.0f;
	FString WinnerSide;  // "own", "enemy" or "draw"
	// Frame statistics while the battle presentation runs (document/12 §8: >= 45 fps at 1080p).
	int32 BattleFrames = 0;
	float BattleFrameSeconds = 0.0f;
	float WorstFrameSeconds = 0.0f;
	int32 CueCountsByKind[4] = {0, 0, 0, 0};
	int32 SwingCount = 0;
	int32 SkillSwingCount = 0;
	int32 BoltCount = 0;
	int32 VoiceCount = 0;
	int32 FootstepCount = 0;
	int32 CameraSwitches = 0;
	TMap<FName, int32> ClipPlays;
	UPROPERTY() TObjectPtr<ACameraActor> BoardCamera;
	UPROPERTY() TObjectPtr<ACameraActor> AudienceCamera;
	UPROPERTY() TObjectPtr<UMaterialInterface> BoltBase;
	UPROPERTY() TObjectPtr<UStaticMesh> BoltMesh;
	bool bAudienceView = false;

	// document/162 §4.5: close-up kill camera
	FString KillCamUnitId;
	/** true when a caller pinned the kill-cam unit; otherwise the first friendly killer is featured. */
	bool bKillCamUnitPinned = false;
	FVector AudienceHomeLocation = FVector::ZeroVector;
	FRotator AudienceHomeRotation = FRotator::ZeroRotator;
	float AudienceHomeFov = 18.0f;
	bool bAudienceMoved = false;
	float KillCamDistanceM = 240.0f;
	float KillCamHeightM = 60.0f;
	float KillCamFovDeg = 30.0f;
	bool bManualCamera = false;
	/** document/180: -TreadAudienceView defers the camera switch to the first battle tick. */
	bool bForceAudienceCapture = false;
};
