#include "TreadM1PlayerController.h"

#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Framework/Application/IInputProcessor.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/PlayerInput.h"
#include "Input/Events.h"
#include "InputCoreTypes.h"
#include "Kismet/KismetSystemLibrary.h"
#include "TreadDragController.h"
#include "TreadEscapeMenu.h"
#include "TreadM1UITest.h"

namespace
{
	/** Observe release before a capturing SButton consumes it. Gameplay and
	 * UMG still receive the event; the component consumes each drag only once. */
	class FTreadM1DragInputProcessor final : public IInputProcessor
	{
	public:
		explicit FTreadM1DragInputProcessor(ATreadM1PlayerController* InController) : Controller(InController) {}
		virtual void Tick(const float DeltaTime, FSlateApplication& SlateApp, TSharedRef<ICursor> Cursor) override {}
		virtual bool HandleMouseButtonDownEvent(FSlateApplication& SlateApp, const FPointerEvent& MouseEvent) override
		{
			if (MouseEvent.GetEffectingButton() == EKeys::LeftMouseButton && Controller.IsValid() && Controller->DragController)
			{
				Controller->DragController->ClearLastReleaseGesture();
			}
			return false;
		}
		virtual bool HandleMouseButtonUpEvent(FSlateApplication& SlateApp, const FPointerEvent& MouseEvent) override
		{
			if (MouseEvent.GetEffectingButton() != EKeys::LeftMouseButton || !Controller.IsValid() || !Controller->DragController) return false;
			Controller->DragController->HandleLeftMouseReleasedAtScreenPosition(MouseEvent.GetScreenSpacePosition());
			return false;
		}
		// document/185: catch Escape before the focused Slate widget (an editable login field) can swallow it.
		virtual bool HandleKeyDownEvent(FSlateApplication& SlateApp, const FKeyEvent& KeyEvent) override
		{
			if (KeyEvent.GetKey() != EKeys::Escape || !Controller.IsValid()) return false;
			if (!KeyEvent.IsRepeat())
			{
				Controller->ToggleEscapeMenu();
			}
			return true;
		}
		virtual const TCHAR* GetDebugName() const override { return TEXT("TreadM1DragInput"); }

	private:
		TWeakObjectPtr<ATreadM1PlayerController> Controller;
	};
}

ATreadM1PlayerController::ATreadM1PlayerController()
{
	DragController = CreateDefaultSubobject<UTreadDragController>(TEXT("M1DragController"));
	UITest = CreateDefaultSubobject<UTreadM1UITest>(TEXT("M1UITest"));
}

void ATreadM1PlayerController::BeginPlay()
{
	Super::BeginPlay();
	bShowMouseCursor = true;
	bEnableClickEvents = true;
	bEnableMouseOverEvents = true;
	FInputModeGameAndUI InputMode;
	InputMode.SetHideCursorDuringCapture(false);
	InputMode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
	SetInputMode(InputMode);
	if (IsLocalController() && FSlateApplication::IsInitialized())
	{
		DragInputProcessor = MakeShared<FTreadM1DragInputProcessor>(this);
		FSlateApplication::Get().RegisterInputPreProcessor(DragInputProcessor);
	}
	// document/185: Escape overlay, created once and hidden until the key is pressed.
	if (IsLocalController() && GEngine && GEngine->GameViewport)
	{
		EscapeMenu = SNew(STreadEscapeMenu)
			.OnQuit(FSimpleDelegate::CreateUObject(this, &ATreadM1PlayerController::QuitFromEscapeMenu))
			.OnCancel(FSimpleDelegate::CreateUObject(this, &ATreadM1PlayerController::CloseEscapeMenu));
		GEngine->GameViewport->AddViewportWidgetContent(EscapeMenu.ToSharedRef(), 1000);
		EscapeMenu->SetVisibility(EVisibility::Collapsed);
	}
}

void ATreadM1PlayerController::ToggleEscapeMenu()
{
	if (!EscapeMenu.IsValid()) return;
	bEscapeMenuOpen = !bEscapeMenuOpen;
	EscapeMenu->SetVisibility(bEscapeMenuOpen ? EVisibility::Visible : EVisibility::Collapsed);
	SetPause(bEscapeMenuOpen);
	bShowMouseCursor = true;
	FInputModeGameAndUI InputMode;
	InputMode.SetHideCursorDuringCapture(false);
	InputMode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
	SetInputMode(InputMode);
}

void ATreadM1PlayerController::CloseEscapeMenu()
{
	if (bEscapeMenuOpen) ToggleEscapeMenu();
}

void ATreadM1PlayerController::QuitFromEscapeMenu()
{
	CloseEscapeMenu();
	UKismetSystemLibrary::QuitGame(this, this, EQuitPreference::Quit, false);
}

void ATreadM1PlayerController::SetupInputComponent()
{
	Super::SetupInputComponent();
	if (!InputComponent) return;
	InputComponent->BindKey(EKeys::LeftMouseButton, IE_Pressed, this, &ATreadM1PlayerController::OnPrimaryPressed);
	InputComponent->BindKey(EKeys::LeftMouseButton, IE_Released, this, &ATreadM1PlayerController::OnPrimaryReleased);
}

void ATreadM1PlayerController::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (DragInputProcessor.IsValid() && FSlateApplication::IsInitialized())
	{
		FSlateApplication::Get().UnregisterInputPreProcessor(DragInputProcessor);
	}
	DragInputProcessor.Reset();
	if (DragController) DragController->CancelDrag();
	if (bEscapeMenuOpen) SetPause(false);
	if (EscapeMenu.IsValid() && GEngine && GEngine->GameViewport)
	{
		GEngine->GameViewport->RemoveViewportWidgetContent(EscapeMenu.ToSharedRef());
	}
	EscapeMenu.Reset();
	Super::EndPlay(EndPlayReason);
}

void ATreadM1PlayerController::OnPrimaryPressed()
{
	if (!DragController) return;
	FVector2D ScreenPosition;
	if (DragController->SampleCursorPosition(ScreenPosition)) DragController->BeginBoardPressAtScreenPosition(ScreenPosition);
}

void ATreadM1PlayerController::OnPrimaryReleased()
{
	if (DragController) DragController->HandleLeftMouseReleased();
}
