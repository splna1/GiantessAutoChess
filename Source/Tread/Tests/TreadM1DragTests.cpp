#if WITH_DEV_AUTOMATION_TESTS

#include "Misc/AutomationTest.h"
#include "Misc/ScopeExit.h"
#include "Engine/World.h"
#include "../TreadDragController.h"
#include "../TreadM1MatchController.h"
#include "../TreadM1PlayerController.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTreadM1DragReleaseTest, "Tread.M1.Drag.ReleaseAndTargets",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FTreadM1DragReleaseTest::RunTest(const FString& Parameters)
{
	UWorld* World = UWorld::CreateWorld(EWorldType::Game, false);
	if (!TestNotNull(TEXT("Test world"), World)) return false;
	ON_SCOPE_EXIT { World->DestroyWorld(false); };
	ATreadM1MatchController* Match = World->SpawnActor<ATreadM1MatchController>();
	ATreadM1PlayerController* PC = World->SpawnActor<ATreadM1PlayerController>();
	if (!TestNotNull(TEXT("Match"), Match) || !TestNotNull(TEXT("Player controller"), PC)) return false;
	UTreadDragController* Drag = PC->DragController;
	Drag->MatchController = Match;
	Match->OnStateChanged.AddDynamic(Drag, &UTreadDragController::HandleMatchStateChanged);
	Match->OnPhaseChanged.AddDynamic(Drag, &UTreadDragController::HandlePhaseChanged);
	Match->MatchState.Phase = ETreadM1Phase::Preparation;
	Match->MatchState.Players.Reset();
	FTreadM1PlayerState& Player = Match->MatchState.Players.AddDefaulted_GetRef();
	Player.PlayerId = TEXT("P0");
	Player.bIsHuman = true;
	Player.BenchUnitInstanceIds.Init(FString(), 8);
	FTreadM1UnitInstance Unit;
	Unit.UnitInstanceId = TEXT("drag-test-unit");
	Unit.CharacterId = TEXT("test-character");
	Unit.OwnerPlayerId = Player.PlayerId;
	Unit.Cost = 3;
	Player.BenchUnits.Add(Unit);
	Player.BenchUnitInstanceIds[3] = Unit.UnitInstanceId;

	const auto CellCenter = [](int32 Column, int32 Row)
	{
		return FVector2D(535.0f + (Column + 0.5f) * 88.0f, 216.0f + (Row + 0.5f) * 88.0f);
	};
	// Inject only the initial press state because an unattended test has no
	// mouse viewport. All release routing, hit tests and commands are real.
	const auto PressBench = [&]()
	{
		Drag->ResetSession();
		Drag->SourceUnitInstanceId = Unit.UnitInstanceId;
		Drag->SourceBenchIndex = Player.BenchUnitInstanceIds.Find(Unit.UnitInstanceId);
		Drag->PressPosition = FVector2D(1006, 1019);
		Drag->CursorPosition = Drag->PressPosition;
		++Drag->DragSessionId;
		Drag->SetState(ETreadDragState::Pressed);
	};

	FIntPoint Hit;
	TestTrue(TEXT("Painted cell center resolves to own board"), Drag->TryGetBoardCell(CellCenter(2, 6), Hit));
	TestEqual(TEXT("Column matches the painted board"), Hit.X, 2);
	TestEqual(TEXT("Row matches the painted board"), Hit.Y, 6);
	TestFalse(TEXT("Enemy half is not deployable"), Drag->TryGetBoardCell(CellCenter(2, 1), Hit));
	TestFalse(TEXT("Right border is outside the board"), Drag->TryGetBoardCell(FVector2D(1239, 612), Hit));

	PressBench();
	TestTrue(TEXT("Release without an intervening tick is handled"), Drag->HandleLeftMouseReleasedAtScreenPosition(CellCenter(2, 6)));
	TestEqual(TEXT("Bench unit deployed once"), Player.BoardUnits.Num(), 1);
	TestTrue(TEXT("Synchronous state notification does not leave Resolving stuck"), Drag->GetDragState() == ETreadDragState::Idle);
	TestTrue(TEXT("Release is marked as a drag for click suppression"), Drag->WasLastReleaseDrag());
	TestFalse(TEXT("Duplicate release cannot settle again"), Drag->HandleLeftMouseReleasedAtScreenPosition(CellCenter(3, 6)));
	TestTrue(TEXT("Duplicate release did not move the unit"), Player.BoardUnits.Num() == 1 && Player.BoardUnits[0].BoardCell == FIntPoint(2, 6));

	TestTrue(TEXT("A second board drag can start immediately"), Drag->BeginBoardPressAtScreenPosition(CellCenter(2, 6)));
	Drag->HandleLeftMouseReleasedAtScreenPosition(CellCenter(3, 6));
	TestTrue(TEXT("Second drag moves to its release cell"), Player.BoardUnits.Num() == 1 && Player.BoardUnits[0].BoardCell == FIntPoint(3, 6));

	FTreadM1UnitInstance OtherUnit = Unit;
	OtherUnit.UnitInstanceId = TEXT("drag-test-other");
	OtherUnit.Location = ETreadM1UnitLocation::Board;
	OtherUnit.BoardCell = FIntPoint(4, 6);
	Player.BoardUnits.Add(OtherUnit);
	++Player.PopulationUsed;
	Drag->BeginBoardPressAtScreenPosition(CellCenter(3, 6));
	Drag->HandleLeftMouseReleasedAtScreenPosition(CellCenter(4, 6));
	TestTrue(TEXT("Dropping a board unit onto another swaps the two"), Player.BoardUnits[0].BoardCell == FIntPoint(4, 6) && Player.BoardUnits[1].BoardCell == FIntPoint(3, 6));

	Drag->BeginBoardPressAtScreenPosition(CellCenter(4, 6));
	Drag->HandleLeftMouseReleasedAtScreenPosition(FVector2D(682, 1019));
	TestEqual(TEXT("Board-to-bench releases population"), Player.PopulationUsed, 1);
	TestEqual(TEXT("Board-to-bench retains the unit"), Player.BenchUnits.Num(), 1);

	PressBench();
	Drag->HandleLeftMouseReleasedAtScreenPosition(CellCenter(1, 1));
	TestEqual(TEXT("Enemy-half release leaves the source on bench"), Player.BenchUnits.Num(), 1);
	TestTrue(TEXT("Invalid release resets to idle"), Drag->GetDragState() == ETreadDragState::Idle);

	Player.PopulationLimit = Player.PopulationUsed;
	PressBench();
	Drag->HandleLeftMouseReleasedAtScreenPosition(CellCenter(1, 7));
	TestEqual(TEXT("Population limit blocks bench deployment"), Player.BenchUnits.Num(), 1);
	Player.PopulationLimit = 3;

	PressBench();
	Drag->HandleLeftMouseReleasedAtScreenPosition(CellCenter(3, 6));
	TestEqual(TEXT("Bench cannot replace an occupied board cell"), Player.BenchUnits.Num(), 1);

	PressBench();
	Drag->SetInteractionBlocked(true);
	TestTrue(TEXT("Opening scout cancels the active gesture"), Drag->GetDragState() == ETreadDragState::Idle);
	TestFalse(TEXT("Scout blocks board press"), Drag->BeginBoardPressAtScreenPosition(CellCenter(3, 6)));
	Drag->SetInteractionBlocked(false);

	PressBench();
	Match->MatchState.Phase = ETreadM1Phase::Battle;
	Match->OnPhaseChanged.Broadcast(ETreadM1Phase::Preparation, ETreadM1Phase::Battle);
	TestTrue(TEXT("Phase change cancels active drag"), Drag->GetDragState() == ETreadDragState::Idle);
	TestFalse(TEXT("Stale release in battle cannot act"), Drag->HandleLeftMouseReleasedAtScreenPosition(CellCenter(1, 7)));
	TestEqual(TEXT("Phase cancellation preserves bench source"), Player.BenchUnits.Num(), 1);
	Match->MatchState.Phase = ETreadM1Phase::Preparation;

	const int32 FundsBeforeSale = Player.Funds;
	PressBench();
	Drag->HandleLeftMouseReleasedAtScreenPosition(FVector2D(150, 1019));
	TestEqual(TEXT("Sell release removes the source"), Player.BenchUnits.Num(), 0);
	TestEqual(TEXT("Sell release pays once"), Player.Funds, FundsBeforeSale + 3);
	Drag->HandleLeftMouseReleasedAtScreenPosition(FVector2D(150, 1019));
	TestEqual(TEXT("Duplicate sell release cannot pay again"), Player.Funds, FundsBeforeSale + 3);
	return true;
}

#endif
