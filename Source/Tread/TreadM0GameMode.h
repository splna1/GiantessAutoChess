#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "TreadM0GameMode.generated.h"

UCLASS()
class TREAD_API ATreadM0GameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	ATreadM0GameMode();
	virtual void StartPlay() override;
};
