#pragma once

#include "CoreMinimal.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"

/**
 * document/185: the Escape overlay. One paper panel with two actions: quit the game or go back.
 * Built in code (like the rest of the Tread UI) so it works in the packaged build without a UMG asset.
 */
class STreadEscapeMenu : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(STreadEscapeMenu) {}
		SLATE_EVENT(FSimpleDelegate, OnQuit)
		SLATE_EVENT(FSimpleDelegate, OnCancel)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	FSimpleDelegate OnQuit;
	FSimpleDelegate OnCancel;
};
