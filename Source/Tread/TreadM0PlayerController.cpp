#include "TreadM0PlayerController.h"

#include "EngineUtils.h"
#include "GameFramework/Actor.h"
#include "InputCoreTypes.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "GenericPlatform/GenericPlatformMisc.h"

void ATreadM0PlayerController::BeginPlay()
{
	Super::BeginPlay();
	bShowMouseCursor = true;
	bEnableClickEvents = true;
	bEnableMouseOverEvents = true;
	SetInputMode(FInputModeGameOnly());
	SetSelection(false);
	if (FParse::Param(FCommandLine::Get(), TEXT("TreadM0SelectionSmoke")))
	{
		GetWorldTimerManager().SetTimerForNextTick(this, &ATreadM0PlayerController::RunSelectionSmoke);
	}
}

void ATreadM0PlayerController::RunSelectionSmoke()


{
	if (FParse::Param(FCommandLine::Get(), TEXT("TreadM0SelectionSmoke")))
	{
		AActor* Candidate = FindSelectable();
		FVector2D Center;
		const bool bProjected = Candidate && ProjectWorldLocationToScreen(Candidate->GetActorLocation(), Center);
		const bool bInside = bProjected && IsClickInsideProjectedBounds(Center, Candidate);
		const bool bOutside = Candidate && !IsClickInsideProjectedBounds(FVector2D(-100.0f, -100.0f), Candidate);
		SetSelection(true);
		bool bBlueVisible = false;
		bool bRedHidden = false;
		for (TActorIterator<AActor> It(GetWorld()); It; ++It)
		{
			if (It->ActorHasTag(TEXT("M0SelectionRing")))
			{
				if (It->ActorHasTag(TEXT("M0EnemyRing")))
				{
					bRedHidden |= It->IsHidden();
				}
				else
				{
					bBlueVisible |= !It->IsHidden();
				}
			}
		}
		const bool bSelectedState = Candidate && SelectedActor == Candidate && bBlueVisible && bRedHidden;
		SetSelection(false);
		const FString Json = FString::Printf(TEXT("{\"ok\":%s,\"projected\":%s,\"center_inside\":%s,\"outside_rejected\":%s,\"selected_ring_state\":%s}"),
			bInside && bOutside && bSelectedState ? TEXT("true") : TEXT("false"), bProjected ? TEXT("true") : TEXT("false"),
			bInside ? TEXT("true") : TEXT("false"), bOutside ? TEXT("true") : TEXT("false"), bSelectedState ? TEXT("true") : TEXT("false"));
		FFileHelper::SaveStringToFile(Json, *(FPaths::ProjectSavedDir() / TEXT("Reports/M0_Selection_Smoke.json")));
		FPlatformMisc::RequestExit(false);
	}
}

void ATreadM0PlayerController::SetupInputComponent()
{
	Super::SetupInputComponent();
	if (InputComponent)
	{
		InputComponent->BindKey(EKeys::LeftMouseButton, IE_Pressed, this, &ATreadM0PlayerController::OnPrimaryClick);
	}
}

AActor* ATreadM0PlayerController::FindSelectable() const
{
	if (!GetWorld())
	{
		return nullptr;
	}
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		if (It->ActorHasTag(TEXT("M0Selectable")))
		{
			return *It;
		}
	}
	return nullptr;
}

bool ATreadM0PlayerController::IsClickInsideProjectedBounds(const FVector2D& ScreenPosition, AActor* Actor) const
{
	if (!Actor)
	{
		return false;
	}
	const FBox Bounds = Actor->GetComponentsBoundingBox(true);
	FVector2D MinScreen;
	FVector2D MaxScreen;
	if (!ProjectWorldLocationToScreen(Bounds.Min, MinScreen) || !ProjectWorldLocationToScreen(Bounds.Max, MaxScreen))
	{
		return false;
	}
	const float MinX = FMath::Min(MinScreen.X, MaxScreen.X) - 24.0f;
	const float MaxX = FMath::Max(MinScreen.X, MaxScreen.X) + 24.0f;
	const float MinY = FMath::Min(MinScreen.Y, MaxScreen.Y) - 24.0f;
	const float MaxY = FMath::Max(MinScreen.Y, MaxScreen.Y) + 24.0f;
	return ScreenPosition.X >= MinX && ScreenPosition.X <= MaxX && ScreenPosition.Y >= MinY && ScreenPosition.Y <= MaxY;
}

void ATreadM0PlayerController::SetSelection(bool bSelected)
{
	SelectedActor = bSelected ? FindSelectable() : nullptr;
	if (!GetWorld())
	{
		return;
	}
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		if (It->ActorHasTag(TEXT("M0SelectionRing")))
		{
			It->SetActorHiddenInGame(!bSelected || It->ActorHasTag(TEXT("M0EnemyRing")));
		}
	}
}

void ATreadM0PlayerController::OnPrimaryClick()
{
	FVector2D MousePosition;
	if (!GetMousePosition(MousePosition.X, MousePosition.Y))
	{
		return;
	}
	AActor* Candidate = FindSelectable();
	SetSelection(Candidate && IsClickInsideProjectedBounds(MousePosition, Candidate));
}
