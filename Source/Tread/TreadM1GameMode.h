#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "TreadM1GameMode.generated.h"

UCLASS()
class TREAD_API ATreadM1GameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	ATreadM1GameMode();
	virtual void StartPlay() override;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "M1")
	TSubclassOf<class ATreadM1MatchController> MatchStateClass;

	UPROPERTY(BlueprintReadOnly, Category = "M1")
	class ATreadM1MatchController* MatchStateActor = nullptr;

	UPROPERTY(BlueprintReadOnly, Category = "M1|UI")
	class UUserWidget* MatchWidget = nullptr;

	/** doc 157 section 4: loading / login / campaign map / sortie, created on M3 maps in normal play (nullptr otherwise). */
	UPROPERTY(BlueprintReadOnly, Category = "M1|UI")
	class UTreadFrontEndWidget* FrontEndWidget = nullptr;
};
