#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "TreadM0PlayerController.generated.h"

UCLASS()
class TREAD_API ATreadM0PlayerController : public APlayerController
{
	GENERATED_BODY()

protected:
	virtual void BeginPlay() override;
	virtual void SetupInputComponent() override;

private:
	void OnPrimaryClick();
	void RunSelectionSmoke();
	AActor* FindSelectable() const;
	void SetSelection(bool bSelected);
	bool IsClickInsideProjectedBounds(const FVector2D& ScreenPosition, AActor* Actor) const;

	UPROPERTY()
	AActor* SelectedActor = nullptr;
};
