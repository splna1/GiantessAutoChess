#pragma once

#include "CoreMinimal.h"
#include "Engine/Texture2D.h"
#include "GameFramework/HUD.h"
#include "TreadM1HUD.generated.h"

class ATreadM1MatchController;

/**
 * Native M1 graybox HUD. It is intentionally canvas based so the prototype
 * can be run from a clean checkout without hand-authored UMG assets. The
 * canvas contains no hit proxies, so 3D board clicks remain available to the
 * eventual drag/drop layer.
 */
UCLASS()
class TREAD_API ATreadM1HUD : public AHUD
{
	GENERATED_BODY()

public:
	virtual void DrawHUD() override;

private:
	ATreadM1MatchController* FindMatchController() const;
	void DrawPanel(const FVector2D& Position, const FVector2D& Size, const FLinearColor& Color) const;
	void DrawLabel(const FString& Text, const FVector2D& Position, float Scale, const FLinearColor& Color) const;
	void DrawMatchHeader(const ATreadM1MatchController& Controller, float Width, float Scale) const;
	void DrawBoard(const ATreadM1MatchController& Controller, float Width, float Height, float Scale) const;
	void DrawBottomEconomy(const ATreadM1MatchController& Controller, float Width, float Height, float Scale) const;
	void DrawRightRoster(const ATreadM1MatchController& Controller, float Width, float Height, float Scale) const;
	void DrawPhaseOverlay(const ATreadM1MatchController& Controller, float Width, float Height, float Scale) const;

	/** document/168: squad panel - portrait, health bar and the green 技力 bar for every fielded unit. */
	void DrawSquadPanel(const ATreadM1MatchController& Controller, float Width, float Height, float Scale) const;
	UTexture2D* PortraitFor(const FString& CharacterId) const;
};
