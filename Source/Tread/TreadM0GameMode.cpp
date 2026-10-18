#include "TreadM0GameMode.h"

#include "TreadM0PerfActor.h"
#include "TreadM0PlayerController.h"
#include "Engine/World.h"
#include "Misc/Parse.h"

ATreadM0GameMode::ATreadM0GameMode()
{
	PlayerControllerClass = ATreadM0PlayerController::StaticClass();
	DefaultPawnClass = nullptr;
}

void ATreadM0GameMode::StartPlay()
{
	Super::StartPlay();
	if (FParse::Param(FCommandLine::Get(), TEXT("TreadM0Perf")) && GetWorld())
	{
		GetWorld()->SpawnActor<ATreadM0PerfActor>();
	}
}
