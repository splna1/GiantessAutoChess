#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "TreadM1DataTypes.h"
#include "TreadAudioDirector.generated.h"

class ATreadM1MatchController;
class UAudioComponent;
class USoundBase;

/**
 * M4 presentation-only audio: BGM, phase SFX and character voice lines, driven by watching the match state.
 * It never issues commands; it compares the human player's units between state broadcasts (new unit -> purchase
 * cue and that character's voice, unit moved to the board -> deploy cue) and reacts to phase changes.
 *
 * Voice rule (document/12 §6): one voice at a time, at least VoiceMinIntervalSeconds between lines, a line is
 * skipped while another plays, and entering Battle stops whatever the preparation phase left playing.
 * Console variable Tread.Audio (1 on, 0 muted) silences everything, e.g. for automated captures.
 */
UCLASS()
class TREAD_API UTreadAudioDirector : public UObject
{
	GENERATED_BODY()

public:
	void Initialize(ATreadM1MatchController* InController);
	void HandlePhaseChanged(ETreadM1Phase PreviousPhase, ETreadM1Phase NewPhase);
	void HandleStateChanged();
	void Shutdown();

	/** Plays a character's voice line (index 0/1) under the voice rule; returns false when skipped. */
	bool PlayVoice(const FString& CharacterId, int32 LineIndex);
	void PlaySfx(const FString& Key);
	void StopVoice();
	/** One shared, throttled footstep for the battle presentation (document/12 §6: no stacked stomps). */
	bool PlayFootstep();

	/** The director of the match HUD in this world (the battle presenter plays through it), or nullptr. */
	static UTreadAudioDirector* Get(const UObject* WorldContext);

	/** document/177: load one sound by asset path and start it; true when the asset exists and playback began. */
	bool PlayAssetPath(const FString& Path, float Volume = 1.0f);

	static constexpr float FootstepMinIntervalSeconds = 0.4f;

	static constexpr float VoiceMinIntervalSeconds = 5.5f;

private:
	TWeakObjectPtr<ATreadM1MatchController> Controller;
	UPROPERTY() TObjectPtr<UAudioComponent> Music;
	UPROPERTY() TObjectPtr<UAudioComponent> Voice;
	UPROPERTY() TMap<FString, TObjectPtr<USoundBase>> SoundCache;
	FString MusicKey;
	double LastVoiceTime = -1000.0;
	double LastFootstepTime = -1000.0;
	static TWeakObjectPtr<UTreadAudioDirector> Active;
	int32 VoiceCounter = 0;
	/** Unit instance id -> on board, for the human player at the last broadcast. */
	TMap<FString, bool> KnownUnits;
	bool bPrimed = false;

	USoundBase* LoadSound(const FString& Path);
	void SetMusic(const FString& Key);
	void Snapshot(TMap<FString, bool>& Out, TMap<FString, FString>& OutCharacters) const;
	bool IsEnabled() const;
	UWorld* GetAudioWorld() const;
};
