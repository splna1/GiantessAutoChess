#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "TreadM1PlayerController.generated.h"

class UTreadDragController;
class IInputProcessor;
class UTreadM1UITest;
class STreadEscapeMenu;

/** M1 input boundary.  It owns the only global mouse-release binding and
 * delegates drag state to the component so UMG and world board releases
 * cannot both settle the same gesture. */
UCLASS()
class TREAD_API ATreadM1PlayerController : public APlayerController
{
	GENERATED_BODY()

public:
	ATreadM1PlayerController();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="M1|Drag")
	TObjectPtr<UTreadDragController> DragController;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="M1|Validation")
	TObjectPtr<UTreadM1UITest> UITest;

protected:
	virtual void BeginPlay() override;
	virtual void SetupInputComponent() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

public:
	/** document/185: Escape overlay (quit / cancel). The input preprocessor calls this before Slate sees the key. */
	void ToggleEscapeMenu();
	void CloseEscapeMenu();
	void QuitFromEscapeMenu();
	bool IsEscapeMenuOpen() const { return bEscapeMenuOpen; }

private:
	void OnPrimaryPressed();
	void OnPrimaryReleased();
	TSharedPtr<IInputProcessor> DragInputProcessor;
	TSharedPtr<STreadEscapeMenu> EscapeMenu;
	bool bEscapeMenuOpen = false;
};
