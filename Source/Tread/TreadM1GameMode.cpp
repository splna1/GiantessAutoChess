#include "TreadM1GameMode.h"

#include "TreadBuildingDestructionManager.h"
#include "TreadDestructionPerfActor.h"
#include "TreadFrontEndWidget.h"
#include "TreadM1MatchController.h"
#include "TreadM1MatchWidget.h"
#include "TreadM1PlayerController.h"
#include "TreadM3BoardPresenter.h"
#include "Blueprint/UserWidget.h"
#include "Engine/World.h"
#include "Camera/CameraActor.h"
#include "EngineUtils.h"
#include "GameFramework/SpectatorPawn.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

namespace
{
	/** The front end (doc 157 section 4.1) covers the R0 briefing in normal play only: self-tests, UI tests, captures and
	 * the campaign developer entry run without it. */
	bool ShouldCreateFrontEnd()
	{
		const TCHAR* CommandLine = FCommandLine::Get();
		static const TCHAR* const Flags[] = { TEXT("TreadM1SelfTest"), TEXT("TreadM2SelfTest"), TEXT("TreadM1UITest"), TEXT("TreadSkipFrontEnd") };
		for (const TCHAR* Flag : Flags)
		{
			if (FParse::Param(CommandLine, Flag)) return false;
		}
		static const TCHAR* const Values[] = { TEXT("TreadM1Capture="), TEXT("TreadM2Capture="), TEXT("TreadCampaign=") };
		for (const TCHAR* Key : Values)
		{
			FString Ignored;
			if (FParse::Value(CommandLine, Key, Ignored)) return false;
		}
		return true;
	}
}

ATreadM1GameMode::ATreadM1GameMode()
{
	DefaultPawnClass = ASpectatorPawn::StaticClass();
	PlayerControllerClass = ATreadM1PlayerController::StaticClass();
	MatchStateClass = ATreadM1MatchController::StaticClass();
	// M1 is rendered by the native UMG match widget.  Keeping the legacy
	// Canvas HUD alive would draw a second, stale layer underneath the M1 UI.
	HUDClass = nullptr;
}

void ATreadM1GameMode::StartPlay()
{
	Super::StartPlay();
	if (GetWorld() && MatchStateClass)
	{
		MatchStateActor = GetWorld()->SpawnActor<ATreadM1MatchController>(MatchStateClass);
		// M3 maps put the match on the 3D Paris board; the M1 graybox map keeps its 2D grid (regression baseline).
		if (GetWorld()->GetMapName().Contains(TEXT("M3_Paris")))
		{
			GetWorld()->SpawnActor<ATreadM3BoardPresenter>();
		}
		UClass* WidgetClass = LoadClass<UTreadM1MatchWidget>(nullptr, TEXT("/Game/Tread/UI/M1/WBP_M1Match.WBP_M1Match_C"));
		MatchWidget = CreateWidget<UTreadM1MatchWidget>(GetWorld()->GetFirstPlayerController(), WidgetClass ? WidgetClass : UTreadM1MatchWidget::StaticClass());
		if (MatchWidget)
		{
			MatchWidget->AddToViewport(10);
		}
		// document/126 + 160: destruction runtime. Registers the middle 4x8 band and swaps intact instances to the
		// pre-cut chunk sets; harmless until something calls ApplyAreaDamage / Tread.DestroyBand.
		GetWorld()->SpawnActor<ATreadBuildingDestructionManager>();
		// document/160: physics stress probe for the destruction plan; stand-alone runs only, never in normal play.
		if (FParse::Param(FCommandLine::Get(), TEXT("TreadDestructionPerf")))
		{
			GetWorld()->SpawnActor<ATreadDestructionPerfActor>();
		}
		// Front end (loading / login / campaign map / sortie) over the match UI, M3 maps in normal play only.
		if (GetWorld()->GetMapName().Contains(TEXT("M3_Paris")) && ShouldCreateFrontEnd())
		{
			FrontEndWidget = CreateWidget<UTreadFrontEndWidget>(GetWorld()->GetFirstPlayerController(), UTreadFrontEndWidget::StaticClass());
			if (FrontEndWidget)
			{
				FrontEndWidget->AddToViewport(20);
				// The legacy campaign map and its buttons stay hidden underneath.
				if (UTreadM1MatchWidget* Match = Cast<UTreadM1MatchWidget>(MatchWidget))
				{
					Match->SetCampaignMapSuppressed(true);
				}
			}
		}
		for (TActorIterator<ACameraActor> It(GetWorld()); It; ++It)
		{
			if (It->GetName().Contains(TEXT("Board_Camera")))
			{
				GetWorld()->GetFirstPlayerController()->SetViewTarget(*It);
				break;
			}
		}
	}
}
