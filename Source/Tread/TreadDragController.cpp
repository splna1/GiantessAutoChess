#include "TreadDragController.h"
#include "TreadM3BoardPresenter.h"

#include "Blueprint/SlateBlueprintLibrary.h"
#include "EngineUtils.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/PlayerController.h"
#include "TreadM1MatchController.h"

UTreadDragController::UTreadDragController()
{
	PrimaryComponentTick.bCanEverTick = true;
	SetComponentTickEnabled(true);
	RequestNamespace = FGuid::NewGuid().ToString(EGuidFormats::Digits);
}

void UTreadDragController::BeginPlay()
{
	Super::BeginPlay();
	MatchController = FindMatchController();
	if (MatchController)
	{
		MatchController->OnStateChanged.AddDynamic(this, &UTreadDragController::HandleMatchStateChanged);
		MatchController->OnPhaseChanged.AddDynamic(this, &UTreadDragController::HandlePhaseChanged);
		bMatchEventsBound = true;
	}
}

void UTreadDragController::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	CancelDrag();
	if (MatchController && bMatchEventsBound)
	{
		MatchController->OnStateChanged.RemoveDynamic(this, &UTreadDragController::HandleMatchStateChanged);
		MatchController->OnPhaseChanged.RemoveDynamic(this, &UTreadDragController::HandlePhaseChanged);
	}
	bMatchEventsBound = false;
	Super::EndPlay(EndPlayReason);
}

ATreadM1MatchController* UTreadDragController::FindMatchController() const
{
	if (!GetWorld()) return nullptr;
	for (TActorIterator<ATreadM1MatchController> It(GetWorld()); It; ++It) return *It;
	return nullptr;
}

bool UTreadDragController::IsPreparationPhase() const
{
	return MatchController && MatchController->MatchState.Phase == ETreadM1Phase::Preparation;
}

bool UTreadDragController::CanInteract() const
{
	return IsPreparationPhase() && !bInteractionBlocked && MatchController->MatchState.Players.Num() > 0 &&
		!MatchController->MatchState.Players[0].bIsEliminated;
}

void UTreadDragController::SetInteractionGeometry(const FGeometry& Geometry, float LayoutScale)
{
	InteractionGeometry = Geometry;
	InteractionLayoutScale = FMath::Max(LayoutScale, KINDA_SMALL_NUMBER);
	bHasInteractionGeometry = true;
}

void UTreadDragController::SetInteractionBlocked(bool bBlocked)
{
	bInteractionBlocked = bBlocked;
	if (bBlocked) CancelDrag();
}

bool UTreadDragController::SampleCursorPosition(FVector2D& OutScreenPosition) const
{
	// UMG may consume mouse movement before FSceneViewport updates its cached
	// cursor. Keep Slate's absolute desktop coordinate intact: ScreenToWidgetLocal
	// needs the same space as FPointerEvent::GetScreenSpacePosition.
	if (FSlateApplication::IsInitialized() && GetWorld() && GetWorld()->GetGameViewport())
	{
		OutScreenPosition = FSlateApplication::Get().GetCursorPos();
		return true;
	}
	const APlayerController* PC = Cast<APlayerController>(GetOwner());
	return PC && PC->GetMousePosition(OutScreenPosition.X, OutScreenPosition.Y);
}

float UTreadDragController::ReferenceScale() const
{
	if (bHasInteractionGeometry) return InteractionLayoutScale;
	const APlayerController* PC = Cast<APlayerController>(GetOwner());
	if (!PC || !PC->GetWorld()) return 1.0f;
	int32 Width = 0;
	int32 Height = 0;
	PC->GetViewportSize(Width, Height);
	const float Short = FMath::Min(static_cast<float>(Width), static_cast<float>(Height));
	if (Short <= 0.0f) return 1.0f;
	if (Short <= 900.0f) return 0.90f;
	if (Short <= 1080.0f) return FMath::Lerp(0.90f, 1.0f, (Short - 900.0f) / 180.0f);
	if (Short <= 1440.0f) return FMath::Lerp(1.0f, 1.3333f, (Short - 1080.0f) / 360.0f);
	return 1.3333f;
}

FVector2D UTreadDragController::ToReference(FVector2D ScreenPosition) const
{
	FVector2D LocalPosition = ScreenPosition;
	if (bHasInteractionGeometry)
	{
		USlateBlueprintLibrary::ScreenToWidgetLocal(this, InteractionGeometry, ScreenPosition, LocalPosition);
	}
	return LocalPosition / FMath::Max(ReferenceScale(), KINDA_SMALL_NUMBER);
}

bool UTreadDragController::IsInRect(FVector2D RefPosition, FVector2D Position, FVector2D Size) const
{
	return RefPosition.X >= Position.X && RefPosition.Y >= Position.Y &&
		RefPosition.X < Position.X + Size.X && RefPosition.Y < Position.Y + Size.Y;
}

bool UTreadDragController::TryGetBenchIndex(FVector2D RefPosition, int32& OutIndex) const
{
	for (int32 Index = 0; Index < 8; ++Index)
	{
		if (IsInRect(RefPosition, FVector2D(BenchX + Index * BenchStep, BenchY), FVector2D(BenchW, BenchH)))
		{
			OutIndex = Index;
			return true;
		}
	}
	return false;
}

ATreadM3BoardPresenter* UTreadDragController::FindBoardPresenter() const
{
	if (!bPresenterSearched && GetWorld())
	{
		bPresenterSearched = true;
		for (TActorIterator<ATreadM3BoardPresenter> It(GetWorld()); It; ++It) { BoardPresenter = *It; break; }
	}
	return BoardPresenter.Get();
}

bool UTreadDragController::TryGetBoardCell(FVector2D RefPosition, FIntPoint& OutCell) const
{
	if (ATreadM3BoardPresenter* Presenter = FindBoardPresenter())
	{
		// Reference -> widget local -> absolute desktop -> viewport pixel, then a ray onto the 3D board.
		const APlayerController* PC = Cast<APlayerController>(GetOwner());
		FVector2D Pixel;
		if (bHasInteractionGeometry)
		{
			const FVector2D Absolute = InteractionGeometry.LocalToAbsolute(RefPosition * ReferenceScale());
			FVector2D ViewportPosition;
			USlateBlueprintLibrary::AbsoluteToViewport(GetWorld(), Absolute, Pixel, ViewportPosition);
		}
		else if (!PC || !PC->GetMousePosition(Pixel.X, Pixel.Y)) return false;
		FIntPoint Cell;
		if (!Presenter->ViewportPixelToUiCell(PC, Pixel, Cell) || Cell.Y < 4) return false;
		OutCell = Cell;
		return true;
	}
	if (!IsInRect(RefPosition, FVector2D(BoardX, BoardY), FVector2D(BoardCell * 8.0f, BoardCell * 8.0f))) return false;
	const int32 X = FMath::FloorToInt((RefPosition.X - BoardX) / BoardCell);
	const int32 Y = FMath::FloorToInt((RefPosition.Y - BoardY) / BoardCell);
	if (X < 0 || X > 7 || Y < 4 || Y > 7) return false;
	OutCell = FIntPoint(X, Y);
	return true;
}

void UTreadDragController::SetState(ETreadDragState NewState, ETreadDragTarget NewTarget, bool bAllowed)
{
	DragState = NewState;
	HoverTarget = NewTarget;
	bHoverAllowed = bAllowed;
	OnDragStateChanged.Broadcast(DragState, DragSessionId, HoverTarget, bHoverAllowed);
}

bool UTreadDragController::BeginBenchPress(int32 BenchIndex, const FString& UnitInstanceId)
{
	if (!CanInteract() || BenchIndex < 0 || BenchIndex >= 8 || UnitInstanceId.IsEmpty()) return false;
	if (DragState != ETreadDragState::Idle) return false;
	const FTreadM1PlayerState& Player = MatchController->MatchState.Players[0];
	if (!Player.BenchUnitInstanceIds.IsValidIndex(BenchIndex) || Player.BenchUnitInstanceIds[BenchIndex] != UnitInstanceId) return false;
	if (!Player.BenchUnits.ContainsByPredicate([&UnitInstanceId](const FTreadM1UnitInstance& Unit) { return Unit.UnitInstanceId == UnitInstanceId; })) return false;
	if (!SampleCursorPosition(CursorPosition)) return false;
	PressPosition = CursorPosition;
	SourceUnitInstanceId = UnitInstanceId;
	SourceBenchIndex = BenchIndex;
	SourceBoardCell = FIntPoint(-1, -1);
	HoverBoardCell = FIntPoint(-1, -1);
	HoverBenchIndex = INDEX_NONE;
	bReleaseConsumed = false;
	bLastReleaseWasDrag = false;
	++DragSessionId;
	SetState(ETreadDragState::Pressed);
	return true;
}

bool UTreadDragController::BeginBoardPressAtScreenPosition(FVector2D ScreenPosition)
{
	if (!CanInteract() || DragState != ETreadDragState::Idle) return false;
	FIntPoint Cell(-1, -1);
	// The M1 board is drawn in UMG. A world-plane hit here would select a
	// different cell, or deploy through a panel covering the world.
	if (!TryGetBoardCell(ToReference(ScreenPosition), Cell)) return false;
	const FTreadM1PlayerState& Player = MatchController->MatchState.Players[0];
	const FTreadM1UnitInstance* Unit = Player.BoardUnits.FindByPredicate([&Cell](const FTreadM1UnitInstance& Candidate) { return Candidate.BoardCell == Cell; });
	if (!Unit) return false;
	CursorPosition = PressPosition = ScreenPosition;
	SourceUnitInstanceId = Unit->UnitInstanceId;
	SourceBenchIndex = INDEX_NONE;
	SourceBoardCell = Cell;
	HoverBoardCell = FIntPoint(-1, -1);
	HoverBenchIndex = INDEX_NONE;
	bReleaseConsumed = false;
	bLastReleaseWasDrag = false;
	++DragSessionId;
	SetState(ETreadDragState::Pressed);
	return true;
}

void UTreadDragController::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	if (!MatchController)
	{
		MatchController = FindMatchController();
		if (MatchController && !bMatchEventsBound)
		{
			MatchController->OnStateChanged.AddDynamic(this, &UTreadDragController::HandleMatchStateChanged);
			MatchController->OnPhaseChanged.AddDynamic(this, &UTreadDragController::HandlePhaseChanged);
			bMatchEventsBound = true;
		}
	}
	if (!CanInteract())
	{
		CancelDrag();
		return;
	}
	if (DragState != ETreadDragState::Pressed && DragState != ETreadDragState::Dragging) return;
	if (!SampleCursorPosition(CursorPosition)) { CancelDrag(); return; }
	if (DragState == ETreadDragState::Pressed && FVector2D::Distance(ToReference(CursorPosition), ToReference(PressPosition)) >= DragThresholdReference)
	{
		SetState(ETreadDragState::Dragging);
	}
	if (DragState == ETreadDragState::Dragging) UpdateHoverTarget();
}

void UTreadDragController::UpdateHoverTarget()
{
	const FVector2D RefPosition = ToReference(CursorPosition);
	HoverTarget = ETreadDragTarget::None;
	HoverBoardCell = FIntPoint(-1, -1);
	HoverBenchIndex = INDEX_NONE;
	bHoverAllowed = false;
	if (!CanInteract()) return;
	const FTreadM1PlayerState& Player = MatchController->MatchState.Players[0];
	if (IsInRect(RefPosition, FVector2D(SellX, SellY), FVector2D(SellW, SellH)))
	{
		HoverTarget = ETreadDragTarget::Sell;
		bHoverAllowed = true;
	}
	else if (TryGetBenchIndex(RefPosition, HoverBenchIndex))
	{
		HoverTarget = ETreadDragTarget::Bench;
		// MoveUnitToBench returns a deployed unit to the first vacant slot.
		// Bench-to-bench reordering is not a supported M1 command.
		bHoverAllowed = SourceBoardCell.X >= 0 && Player.BenchUnits.Num() < MatchController->MatchState.Rules.MaxBenchSlots;
	}
	else if (TryGetBoardCell(RefPosition, HoverBoardCell))
	{
		HoverTarget = ETreadDragTarget::Board;
		const bool bOccupied = Player.BoardUnits.ContainsByPredicate([this](const FTreadM1UnitInstance& Unit)
		{
			return Unit.BoardCell == HoverBoardCell && Unit.UnitInstanceId != SourceUnitInstanceId;
		});
		bHoverAllowed = SourceBoardCell.X >= 0
			? SourceBoardCell != HoverBoardCell
			: !bOccupied && Player.PopulationUsed < Player.PopulationLimit;
	}
	OnDragStateChanged.Broadcast(DragState, DragSessionId, HoverTarget, bHoverAllowed);
}

bool UTreadDragController::HandleLeftMouseReleased()
{
	if (DragState == ETreadDragState::Idle || DragState == ETreadDragState::Cancelled) return false;
	FVector2D ReleasePosition;
	if (!SampleCursorPosition(ReleasePosition))
	{
		CancelDrag();
		return true;
	}
	return HandleLeftMouseReleasedAtScreenPosition(ReleasePosition);
}

bool UTreadDragController::HandleLeftMouseReleasedAtScreenPosition(FVector2D ScreenPosition)
{
	if (DragState == ETreadDragState::Idle || DragState == ETreadDragState::Cancelled) return false;
	if (bReleaseConsumed) return true;
	bReleaseConsumed = true;
	CursorPosition = ScreenPosition;
	// A complete gesture can arrive between ticks (including MCP input).
	if (DragState == ETreadDragState::Pressed && FVector2D::Distance(ToReference(CursorPosition), ToReference(PressPosition)) >= DragThresholdReference)
	{
		SetState(ETreadDragState::Dragging);
	}
	bLastReleaseWasDrag = DragState == ETreadDragState::Dragging;
	if (DragState != ETreadDragState::Dragging || !CanInteract())
	{
		CancelDrag();
		return true;
	}
	UpdateHoverTarget();
	if (!bHoverAllowed) { CancelDrag(); return true; }
	ResolveRelease();
	return true;
}

void UTreadDragController::ResolveRelease()
{
	if (!CanInteract() || SourceUnitInstanceId.IsEmpty() || !bHoverAllowed) { CancelDrag(); return; }
	const FString RequestId = FString::Printf(TEXT("m1-drag-%s-%d"), *RequestNamespace, DragSessionId);
	const ETreadDragTarget Target = HoverTarget;
	// Commands broadcast OnStateChanged synchronously. Enter Resolving first,
	// then always finish from the command result, including cached responses
	// which need not broadcast another state event.
	SetState(ETreadDragState::Resolving, Target, true);
	FTreadM1CommandResult Result;
	switch (Target)
	{
	case ETreadDragTarget::Sell:
		Result = MatchController->SellUnit(TEXT("P0"), SourceUnitInstanceId, RequestId);
		break;
	case ETreadDragTarget::Board:
		{
			const FTreadM1PlayerState& Player = MatchController->MatchState.Players[0];
			const FTreadM1UnitInstance* TargetUnit = Player.BoardUnits.FindByPredicate([this](const FTreadM1UnitInstance& Candidate)
			{
				return Candidate.BoardCell == HoverBoardCell && Candidate.UnitInstanceId != SourceUnitInstanceId;
			});
			Result = SourceBoardCell.X >= 0 && TargetUnit
				? MatchController->SwapBoardUnits(TEXT("P0"), SourceUnitInstanceId, TargetUnit->UnitInstanceId, RequestId)
				: MatchController->MoveUnitToBoard(TEXT("P0"), SourceUnitInstanceId, HoverBoardCell, RequestId);
		}
		break;
	case ETreadDragTarget::Bench:
		Result = MatchController->MoveUnitToBench(TEXT("P0"), SourceUnitInstanceId, RequestId);
		break;
	default:
		CancelDrag();
		return;
	}
	if (!Result.bAccepted) SetState(ETreadDragState::Cancelled, Target, false);
	ResetSession();
}

void UTreadDragController::CancelDrag()
{
	if (DragState == ETreadDragState::Idle) return;
	bLastReleaseWasDrag |= DragState == ETreadDragState::Dragging;
	SetState(ETreadDragState::Cancelled);
	ResetSession();
}

void UTreadDragController::ResetSession()
{
	SourceUnitInstanceId.Empty();
	SourceBenchIndex = INDEX_NONE;
	SourceBoardCell = FIntPoint(-1, -1);
	HoverBoardCell = FIntPoint(-1, -1);
	HoverBenchIndex = INDEX_NONE;
	bReleaseConsumed = false;
	SetState(ETreadDragState::Idle);
}

void UTreadDragController::HandleMatchStateChanged()
{
	// ResolveRelease owns the synchronous completion. An unrelated state
	// change during a gesture must still cancel a removed source unit.
	if (DragState != ETreadDragState::Pressed && DragState != ETreadDragState::Dragging) return;
	if (!CanInteract()) { CancelDrag(); return; }
	const FTreadM1PlayerState& Player = MatchController->MatchState.Players[0];
	const auto IsSource = [this](const FTreadM1UnitInstance& Unit) { return Unit.UnitInstanceId == SourceUnitInstanceId; };
	if (!Player.BenchUnits.ContainsByPredicate(IsSource) && !Player.BoardUnits.ContainsByPredicate(IsSource)) CancelDrag();
}

void UTreadDragController::HandlePhaseChanged(ETreadM1Phase PreviousPhase, ETreadM1Phase NewPhase)
{
	if (NewPhase != ETreadM1Phase::Preparation) CancelDrag();
}
