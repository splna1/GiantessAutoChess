#include "TreadAudioDirector.h"

#include "Components/AudioComponent.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"
#include "Sound/SoundBase.h"
#include "TreadM1MatchController.h"

namespace
{
	TAutoConsoleVariable<int32> CVarTreadAudio(
		TEXT("Tread.Audio"), 1,
		TEXT("1: play Tread BGM, SFX and voice lines; 0: mute them (automated captures)."));

	constexpr float MusicVolume = 0.35f;
	constexpr float SfxVolume = 0.8f;
	constexpr float VoiceVolume = 1.0f;

	FString ObjectPath(const FString& PackagePath)
	{
		// "/Game/A/B" -> "/Game/A/B.B" so LoadObject does not have to guess the object name.
		return PackagePath.Contains(TEXT(".")) ? PackagePath : PackagePath + TEXT(".") + FPaths::GetBaseFilename(PackagePath);
	}

	const FTreadM1PlayerState* Human(const ATreadM1MatchController* Controller)
	{
		if (!Controller) return nullptr;
		for (const FTreadM1PlayerState& Player : Controller->MatchState.Players)
		{
			if (Player.bIsHuman) return &Player;
		}
		return nullptr;
	}
}

TWeakObjectPtr<UTreadAudioDirector> UTreadAudioDirector::Active;

UTreadAudioDirector* UTreadAudioDirector::Get(const UObject* WorldContext)
{
	UTreadAudioDirector* Director = Active.Get();
	return Director && WorldContext && Director->GetAudioWorld() == WorldContext->GetWorld() ? Director : nullptr;
}

void UTreadAudioDirector::Initialize(ATreadM1MatchController* InController)
{
	Controller = InController;
	Active = this;
	bPrimed = false;
	KnownUnits.Reset();
	if (Controller.IsValid())
	{
		HandlePhaseChanged(Controller->GetPhase(), Controller->GetPhase());
	}
}

void UTreadAudioDirector::Shutdown()
{
	if (Music) Music->Stop();
	if (Voice) Voice->Stop();
	Music = nullptr;
	Voice = nullptr;
}

bool UTreadAudioDirector::IsEnabled() const
{
	return CVarTreadAudio.GetValueOnGameThread() != 0 && GetAudioWorld() != nullptr;
}

UWorld* UTreadAudioDirector::GetAudioWorld() const
{
	return Controller.IsValid() ? Controller->GetWorld() : nullptr;
}

USoundBase* UTreadAudioDirector::LoadSound(const FString& Path)
{
	if (Path.IsEmpty()) return nullptr;
	if (TObjectPtr<USoundBase>* Cached = SoundCache.Find(Path)) return *Cached;
	USoundBase* Sound = LoadObject<USoundBase>(nullptr, *ObjectPath(Path));
	if (!Sound) UE_LOG(LogTemp, Warning, TEXT("Tread audio: missing sound %s"), *Path);
	SoundCache.Add(Path, Sound);
	return Sound;
}

void UTreadAudioDirector::SetMusic(const FString& Key)
{
	if (Key == MusicKey) return;
	MusicKey = Key;
	if (Music)
	{
		Music->FadeOut(1.0f, 0.0f);
		Music = nullptr;
	}
	if (!IsEnabled() || Key.IsEmpty()) return;
	USoundBase* Sound = LoadSound(Controller->GetBgmAssetPath(Key));
	if (!Sound) return;
	Music = UGameplayStatics::CreateSound2D(GetAudioWorld(), Sound, MusicVolume, 1.0f, 0.0f, nullptr, false, false);
	if (Music) Music->FadeIn(1.5f, MusicVolume);
}

void UTreadAudioDirector::PlaySfx(const FString& Key)
{
	if (!IsEnabled()) return;
	if (USoundBase* Sound = LoadSound(Controller->GetSfxAssetPath(Key)))
	{
		UGameplayStatics::PlaySound2D(GetAudioWorld(), Sound, SfxVolume);
	}
}

bool UTreadAudioDirector::PlayVoice(const FString& CharacterId, int32 LineIndex)
{
	if (!IsEnabled()) return false;
	const FTreadM2Card* Card = Controller->FindCardData(CharacterId);
	if (!Card || Card->VoiceAssets.Num() == 0) return false;
	const double Now = GetAudioWorld()->GetRealTimeSeconds();
	if (Now - LastVoiceTime < VoiceMinIntervalSeconds) return false;
	if (Voice && Voice->IsPlaying()) return false;
	USoundBase* Sound = LoadSound(Card->VoiceAssets[FMath::Abs(LineIndex) % Card->VoiceAssets.Num()]);
	if (!Sound) return false;
	if (Voice) Voice->Stop();
	Voice = UGameplayStatics::SpawnSound2D(GetAudioWorld(), Sound, VoiceVolume);
	LastVoiceTime = Now;
	return Voice != nullptr;
}

void UTreadAudioDirector::StopVoice()
{
	if (Voice) Voice->Stop();
}

bool UTreadAudioDirector::PlayAssetPath(const FString& Path, float Volume)
{
	if (!IsEnabled()) return false;
	USoundBase* Sound = LoadSound(Path);
	if (!Sound) return false;
	return UGameplayStatics::SpawnSound2D(GetAudioWorld(), Sound, Volume) != nullptr;
}

bool UTreadAudioDirector::PlayFootstep()
{
	if (!IsEnabled()) return false;
	const double Now = GetAudioWorld()->GetRealTimeSeconds();
	if (Now - LastFootstepTime < FootstepMinIntervalSeconds) return false;
	USoundBase* Sound = LoadSound(Controller->GetSfxAssetPath(TEXT("tread_footstep")));
	if (!Sound) return false;
	LastFootstepTime = Now;
	UGameplayStatics::PlaySound2D(GetAudioWorld(), Sound, SfxVolume * 0.45f);
	return true;
}

void UTreadAudioDirector::Snapshot(TMap<FString, bool>& Out, TMap<FString, FString>& OutCharacters) const
{
	if (const FTreadM1PlayerState* Player = Human(Controller.Get()))
	{
		for (const FTreadM1UnitInstance& Unit : Player->BenchUnits)
		{
			Out.Add(Unit.UnitInstanceId, false);
			OutCharacters.Add(Unit.UnitInstanceId, Unit.CharacterId);
		}
		for (const FTreadM1UnitInstance& Unit : Player->BoardUnits)
		{
			Out.Add(Unit.UnitInstanceId, true);
			OutCharacters.Add(Unit.UnitInstanceId, Unit.CharacterId);
		}
	}
}

void UTreadAudioDirector::HandleStateChanged()
{
	if (!Controller.IsValid()) return;
	TMap<FString, bool> Units;
	TMap<FString, FString> Characters;
	Snapshot(Units, Characters);
	if (bPrimed && Controller->GetPhase() == ETreadM1Phase::Preparation)
	{
		FString NewCharacter;
		bool bDeployed = false;
		for (const TPair<FString, bool>& Pair : Units)
		{
			const bool* Before = KnownUnits.Find(Pair.Key);
			if (!Before && NewCharacter.IsEmpty()) NewCharacter = Characters[Pair.Key];
			if (Before && !*Before && Pair.Value) bDeployed = true;
		}
		if (!NewCharacter.IsEmpty())
		{
			PlaySfx(TEXT("purchase"));
			PlayVoice(NewCharacter, VoiceCounter++);
		}
		if (bDeployed) PlaySfx(TEXT("giantess_deploy"));
	}
	KnownUnits = MoveTemp(Units);
	bPrimed = true;
}

void UTreadAudioDirector::HandlePhaseChanged(ETreadM1Phase PreviousPhase, ETreadM1Phase NewPhase)
{
	if (!Controller.IsValid()) return;
	switch (NewPhase)
	{
	case ETreadM1Phase::Battle:
	{
		// Entering battle clears whatever the preparation phase left playing (document/12 §6).
		if (Voice) Voice->Stop();
		SetMusic(TEXT("battle"));
		if (PreviousPhase != NewPhase)
		{
			PlaySfx(Controller->MatchState.RoundType == ETreadM1RoundType::PvE ? TEXT("pve_raid") : TEXT("pvp_battle"));
		}
		break;
	}
	case ETreadM1Phase::Settlement:
	{
		const FTreadM1PlayerState* Player = Human(Controller.Get());
		for (const FTreadM1BattleOutcome& Outcome : Controller->MatchState.LastBattleResult.Outcomes)
		{
			if (Player && Outcome.PlayerId == Player->PlayerId && PreviousPhase != NewPhase)
			{
				PlaySfx(Outcome.Outcome == TEXT("Win") ? TEXT("victory") : TEXT("defeat"));
			}
		}
		break;
	}
	case ETreadM1Phase::GameOver:
	{
		SetMusic(TEXT("menu"));
		const FTreadM1PlayerState* Player = Human(Controller.Get());
		if (PreviousPhase != NewPhase) PlaySfx(Player && Player->Rank == 1 ? TEXT("victory") : TEXT("eliminated"));
		break;
	}
	case ETreadM1Phase::Preparation:
		SetMusic(TEXT("menu"));
		if (PreviousPhase != NewPhase) PlaySfx(TEXT("round_start"));
		break;
	default:
		SetMusic(TEXT("menu"));
		break;
	}
	// Units granted by the phase change itself (round rewards) are not purchases.
	KnownUnits.Reset();
	TMap<FString, FString> Characters;
	Snapshot(KnownUnits, Characters);
}
