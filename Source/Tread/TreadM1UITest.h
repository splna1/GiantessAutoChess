#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "TreadM1UITest.generated.h"

class ATreadM1MatchController;
class UTreadM1MatchWidget;
class FJsonObject;

/** Opt-in smoke runner: sends actual Slate input to the live M1 widget.
 * Enable with -TreadM1UITest, or call StartTest on this component in PIE.
 * Add -TreadM1UIFullTest to play from the menu through natural GameOver.
 * Add -TreadM1UIFull12 as well for the R1-R12 high-health UI fixture. */
UCLASS(ClassGroup=(M1), BlueprintType, meta=(BlueprintSpawnableComponent))
class TREAD_API UTreadM1UITest : public UActorComponent
{
	GENERATED_BODY()

public:
	UTreadM1UITest();

	UFUNCTION(BlueprintCallable, Category="M1|Validation")
	void StartTest();

	UPROPERTY(BlueprintReadOnly, Category="M1|Validation")
	bool bRunning = false;

	UPROPERTY(BlueprintReadOnly, Category="M1|Validation")
	bool bLastRunPassed = false;

protected:
	virtual void BeginPlay() override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

private:
	bool Check(const FString& Name, bool bPassed, const FString& Detail = FString());
	void Click(FVector2D ReferencePosition);
	void Drag(FVector2D SourceReference, FVector2D TargetReference);
	void SendPointer(FVector2D ReferencePosition, int32 Action);
	void Capture(const FString& Stage);
	void Finish(bool bPassed);
	void AdvanceStep();
	FVector2D BenchPosition(const FString& UnitId) const;
	FIntPoint UnitCell(const FString& UnitId) const;
	FString HumanRosterSignature() const;
	FString HumanShopSignature() const;
	bool RecordRoundResult(int32 ExpectedRound);
	bool RecordRoundHud(int32 ExpectedRound);
	bool CheckGameOver();

	TWeakObjectPtr<ATreadM1MatchController> Match;
	TWeakObjectPtr<UTreadM1MatchWidget> Widget;
	TArray<TSharedPtr<FJsonObject>> Checks;
	TArray<TSharedPtr<FJsonObject>> Inputs;
	TArray<TSharedPtr<FJsonObject>> Rounds;
	TArray<TSharedPtr<FJsonObject>> RoundHuds;
	TSharedPtr<FJsonObject> FinalRanking;
	TArray<FString> Screenshots;
	FString ScreenshotDirectory;
	FString DraggedUnitId;
	FString SwappedUnitId;
	FString FirstStrategyId;
	FString RevisedStrategyId;
	FString BattleRosterBefore;
	FString BattleShopBefore;
	int32 Step = 0;
	int32 FundsBefore = 0;
	int32 ExpectedCost = 0;
	int32 RefreshBefore = 0;
	int32 ExperienceBefore = 0;
	int32 ShopSlot = 0;
	int32 LastDragSession = 0;
	int32 RoundBefore = 0;
	int32 FullRoundIndex = 0;
	int32 BattleFundsBefore = 0;
	int32 ScoutPoolRevisionBefore = 0;
	int32 ScoutPoolEntriesBefore = 0;
	int32 ScoutFundsBefore = 0;
	int32 ScoutIndex = 0;
	double StartedAt = 0;
	double NextActionAt = 0;
	double RoundTwoPreparationAt = 0;
	double RoundTwoAutoTransitionSeconds = 0;
	double BattleStartedAt = 0;
	bool bLeftPressed = false;
	bool bExitOnComplete = false;
	bool bFullGameMode = false;
	bool bFull12Mode = false;
	bool bFull12FixtureApplied = false;
	bool bRevisedStrategy = false;
	bool bSettlementReadyForClick = false;
	bool bHudReadyForDeploy = false;
};
