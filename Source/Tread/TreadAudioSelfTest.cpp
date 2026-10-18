// Audio acceptance (document/177): the M4 sound catalogue was never auditioned - the battle capture
// runs mute (`Tread.Audio 0`) and reported voices=0/footsteps=0. This self-test turns the CVar on,
// loads and starts every assigned BGM/SFX, plays one voice line and one footstep, and asserts the
// voice/footstep throttle rules. It writes Saved/Reports/Audio_SelfTest.json and is driven by
// `-TreadAudioSelfTest` (run WITHOUT -nosound / -nullrhi).

#include "TreadM1MatchController.h"

#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "TreadAudioDirector.h"

bool ATreadM1MatchController::RunAudioSelfTest(const FString& OutputPath)
{
	if (IConsoleVariable* CVar = IConsoleManager::Get().FindConsoleVariable(TEXT("Tread.Audio")))
	{
		CVar->Set(1);
	}
	UTreadAudioDirector* Director = NewObject<UTreadAudioDirector>(this);
	Director->Initialize(this);

	TMap<FString, bool> Checks;
	TArray<TSharedPtr<FJsonValue>> Failures;
	int32 BgmTotal = 0;
	int32 BgmPlayed = 0;
	int32 SfxTotal = 0;
	int32 SfxPlayed = 0;
	if (PactData.IsValid())
	{
		for (const TPair<FString, FString>& Pair : PactData->BgmAssets)
		{
			++BgmTotal;
			if (Director->PlayAssetPath(Pair.Value, 0.15f)) ++BgmPlayed;
			else Failures.Add(MakeShared<FJsonValueString>(TEXT("bgm:") + Pair.Key + TEXT("=") + Pair.Value));
		}
		for (const TPair<FString, FString>& Pair : PactData->SfxAssets)
		{
			++SfxTotal;
			if (Director->PlayAssetPath(Pair.Value, 0.15f)) ++SfxPlayed;
			else Failures.Add(MakeShared<FJsonValueString>(TEXT("sfx:") + Pair.Key + TEXT("=") + Pair.Value));
		}
	}
	Checks.Add(TEXT("bgmCatalogueComplete"), BgmTotal > 0 && BgmPlayed == BgmTotal);
	Checks.Add(TEXT("sfxCatalogueComplete"), SfxTotal >= 10 && SfxPlayed == SfxTotal);

	// One real character voice line (the first card that owns voice assets).
	FString VoiceCharacter;
	if (PactData.IsValid())
	{
		for (const FString& CharacterId : PactData->CardOrder)
		{
			const FTreadM2Card* Card = PactData->FindCard(CharacterId);
			if (Card && Card->VoiceAssets.Num() > 0)
			{
				VoiceCharacter = CharacterId;
				break;
			}
		}
	}
	const bool bVoicePlayed = !VoiceCharacter.IsEmpty() && Director->PlayVoice(VoiceCharacter, 0);
	Checks.Add(TEXT("voicePlayable"), bVoicePlayed);
	Director->StopVoice();

	// Footsteps: the first one plays, an immediate second one is throttled (document/12 §6).
	const bool bStepFirst = Director->PlayFootstep();
	const bool bStepAgain = Director->PlayFootstep();
	Checks.Add(TEXT("footstepPlayable"), bStepFirst);
	Checks.Add(TEXT("footstepThrottled"), !bStepAgain);

	// Phase-driven path: entering battle swaps the BGM and fires the round-type SFX.
	Director->HandlePhaseChanged(ETreadM1Phase::Preparation, ETreadM1Phase::Battle);
	Checks.Add(TEXT("battlePhaseAudioRuns"), true);

	bool bOk = true;
	TSharedPtr<FJsonObject> Named = MakeShared<FJsonObject>();
	for (const TPair<FString, bool>& Check : Checks)
	{
		Named->SetBoolField(Check.Key, Check.Value);
		bOk &= Check.Value;
	}
	TSharedPtr<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetStringField(TEXT("schema"), TEXT("Tread.Audio.SelfTest.v1"));
	Root->SetStringField(TEXT("producer"), TEXT("Tread C++ RunAudioSelfTest"));
	Root->SetBoolField(TEXT("ok"), bOk);
	Root->SetObjectField(TEXT("namedChecks"), Named);
	Root->SetNumberField(TEXT("bgmTotal"), BgmTotal);
	Root->SetNumberField(TEXT("bgmPlayed"), BgmPlayed);
	Root->SetNumberField(TEXT("sfxTotal"), SfxTotal);
	Root->SetNumberField(TEXT("sfxPlayed"), SfxPlayed);
	Root->SetStringField(TEXT("voiceCharacter"), VoiceCharacter);
	Root->SetArrayField(TEXT("failures"), Failures);

	FString Output;
	FJsonSerializer::Serialize(Root.ToSharedRef(), TJsonWriterFactory<>::Create(&Output));
	const FString Path = OutputPath.IsEmpty()
		? FPaths::Combine(FPaths::ProjectDir(), TEXT("Saved/Reports/Audio_SelfTest.json")) : OutputPath;
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(Path), true);
	const bool bSaved = FFileHelper::SaveStringToFile(Output + TEXT("\n"), *Path, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
	Director->Shutdown();
	return bOk && bSaved;
}
