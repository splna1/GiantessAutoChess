#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Layout/Geometry.h"
#include "TreadM1DataTypes.h"
#include "TreadDragController.generated.h"

class ATreadM1MatchController;
class ATreadM3BoardPresenter;

/** The single owner of an M1 mouse drag session.  It intentionally does not
 * use UDragDropOperation: a release may land on the world board as well as
 * on UMG, so the PlayerController is the only release authority. */
UENUM(BlueprintType)
enum class ETreadDragState : uint8
{
	Idle,
	Pressed,
	Dragging,
	Resolving,
	Cancelled
};

UENUM(BlueprintType)
enum class ETreadDragTarget : uint8
{
	None,
	Board,
	Bench,
	Sell
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_FourParams(FTreadDragStateChanged,
	ETreadDragState, State, int32, DragSessionId, ETreadDragTarget, Target, bool, bAllowed);

UCLASS(ClassGroup=(M1), BlueprintType, meta=(BlueprintSpawnableComponent))
class TREAD_API UTreadDragController : public UActorComponent
{
	GENERATED_BODY()

public:
	UTreadDragController();

	/** Emitted for previews and accessibility/toast UI. */
	UPROPERTY(BlueprintAssignable, Category="M1|Drag")
	FTreadDragStateChanged OnDragStateChanged;

	UFUNCTION(BlueprintPure, Category="M1|Drag")
	ETreadDragState GetDragState() const { return DragState; }

	UFUNCTION(BlueprintPure, Category="M1|Drag")
	ETreadDragTarget GetHoverTarget() const { return HoverTarget; }

	UFUNCTION(BlueprintPure, Category="M1|Drag")
	bool IsDragging() const { return DragState == ETreadDragState::Dragging; }

	UFUNCTION(BlueprintPure, Category="M1|Drag")
	int32 GetDragSessionId() const { return DragSessionId; }

	UFUNCTION(BlueprintPure, Category="M1|Drag")
	FVector2D GetCursorPosition() const { return CursorPosition; }

	UFUNCTION(BlueprintPure, Category="M1|Drag")
	FVector2D GetCursorReferencePosition() const { return ToReference(CursorPosition); }

	UFUNCTION(BlueprintPure, Category="M1|Drag")
	FIntPoint GetHoverBoardCell() const { return HoverBoardCell; }

	UFUNCTION(BlueprintPure, Category="M1|Drag")
	int32 GetHoverBenchIndex() const { return HoverBenchIndex; }

	UFUNCTION(BlueprintPure, Category="M1|Drag")
	bool IsHoverAllowed() const { return bHoverAllowed; }

	UFUNCTION(BlueprintPure, Category="M1|Drag")
	FString GetSourceUnitInstanceId() const { return SourceUnitInstanceId; }

	UFUNCTION(BlueprintPure, Category="M1|Drag")
	bool WasLastReleaseDrag() const { return bLastReleaseWasDrag; }

	/** Use the same geometry and reference scale as the HUD's paint pass. */
	void SetInteractionGeometry(const FGeometry& Geometry, float LayoutScale);

	UFUNCTION(BlueprintCallable, Category="M1|Drag")
	void SetInteractionBlocked(bool bBlocked);

	/** Called by the PlayerController's Slate preprocessor before UMG consumes release. */
	bool HandleLeftMouseReleasedAtScreenPosition(FVector2D ScreenPosition);

	void ClearLastReleaseGesture() { bLastReleaseWasDrag = false; }
	bool SampleCursorPosition(FVector2D& OutScreenPosition) const;

	/** Called by a bench slot's OnMouseButtonDown/Pressed handler. */
	UFUNCTION(BlueprintCallable, Category="M1|Drag")
	bool BeginBenchPress(int32 BenchIndex, const FString& UnitInstanceId);

	/** Called by PlayerController after a world click misses UMG. */
	UFUNCTION(BlueprintCallable, Category="M1|Drag")
	bool BeginBoardPressAtScreenPosition(FVector2D ScreenPosition);

	/** The PlayerController's sole LeftMouseButton release entry point. */
	UFUNCTION(BlueprintCallable, Category="M1|Drag")
	bool HandleLeftMouseReleased();

	UFUNCTION(BlueprintCallable, Category="M1|Drag")
	void CancelDrag();

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

private:
	UFUNCTION()
	void HandleMatchStateChanged();

	UFUNCTION()
	void HandlePhaseChanged(ETreadM1Phase PreviousPhase, ETreadM1Phase NewPhase);

	void SetState(ETreadDragState NewState, ETreadDragTarget NewTarget = ETreadDragTarget::None, bool bAllowed = false);
	void UpdateHoverTarget();
	void ResolveRelease();
	void ResetSession();
	ATreadM1MatchController* FindMatchController() const;
	bool IsPreparationPhase() const;
	float ReferenceScale() const;
	FVector2D ToReference(FVector2D ScreenPosition) const;
	bool IsInRect(FVector2D RefPosition, FVector2D Position, FVector2D Size) const;
	bool TryGetBoardCell(FVector2D RefPosition, FIntPoint& OutCell) const;
	bool TryGetBenchIndex(FVector2D RefPosition, int32& OutIndex) const;
	bool CanInteract() const;

	UPROPERTY()
	TObjectPtr<ATreadM1MatchController> MatchController;

	ETreadDragState DragState = ETreadDragState::Idle;
	ETreadDragTarget HoverTarget = ETreadDragTarget::None;
	FVector2D CursorPosition = FVector2D::ZeroVector;
	FVector2D PressPosition = FVector2D::ZeroVector;
	FString SourceUnitInstanceId;
	int32 SourceBenchIndex = INDEX_NONE;
	FIntPoint SourceBoardCell = FIntPoint(-1, -1);
	FIntPoint HoverBoardCell = FIntPoint(-1, -1);
	int32 HoverBenchIndex = INDEX_NONE;
	int32 DragSessionId = 0;
	bool bReleaseConsumed = false;
	bool bMatchEventsBound = false;
	bool bHoverAllowed = false;
	bool bInteractionBlocked = false;
	bool bHasInteractionGeometry = false;
	bool bLastReleaseWasDrag = false;
	FGeometry InteractionGeometry;
	float InteractionLayoutScale = 1.0f;
	FString RequestNamespace;
	float DragThresholdReference = 6.0f;

	/** M3 maps: the 3D board presenter (looked up once); board cells then come from a ray onto the ground. */
	mutable TWeakObjectPtr<ATreadM3BoardPresenter> BoardPresenter;
	mutable bool bPresenterSearched = false;
	ATreadM3BoardPresenter* FindBoardPresenter() const;

	friend class FTreadM1DragReleaseTest;

	// Reference-space geometry shared by the native graybox and the WBP spec.
	static constexpr float SellX = 16.0f;
	static constexpr float SellY = 968.0f;
	static constexpr float SellW = 300.0f;
	static constexpr float SellH = 100.0f;
	static constexpr float BenchX = 632.0f;
	static constexpr float BenchY = 978.0f;
	static constexpr float BenchStep = 108.0f;
	static constexpr float BenchW = 100.0f;
	static constexpr float BenchH = 82.0f;
	static constexpr float BoardX = 535.0f;
	static constexpr float BoardY = 216.0f;
	static constexpr float BoardCell = 88.0f;
};
