#pragma once

#include "CoreMinimal.h"
#include "GameFramework/SaveGame.h"
#include "TreadCampaignSave.generated.h"

/** M4 campaign progress (slot "TreadCampaign"): stages conquered so far; stage N+1 unlocks when N is conquered. */
UCLASS()
class TREAD_API UTreadCampaignSave : public USaveGame
{
	GENERATED_BODY()

public:
	static constexpr const TCHAR* SlotName = TEXT("TreadCampaign");

	UPROPERTY() TArray<int32> ConqueredStages;
	UPROPERTY() int32 LastStage = 1;
	UPROPERTY() int32 Attempts = 0;
};
