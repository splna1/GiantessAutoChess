#include "TreadM1HUD.h"

#include "CanvasItem.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "EngineUtils.h"
#include "Engine/Texture2D.h"
#include "UObject/ConstructorHelpers.h"
#include "TreadM1MatchController.h"

ATreadM1MatchController* ATreadM1HUD::FindMatchController() const
{
	if (!GetWorld()) return nullptr;
	for (TActorIterator<ATreadM1MatchController> It(GetWorld()); It; ++It)
	{
		return *It;
	}
	return nullptr;
}

void ATreadM1HUD::DrawPanel(const FVector2D& Position, const FVector2D& Size, const FLinearColor& Color) const
{
	if (!Canvas) return;
	FCanvasTileItem Tile(Position, Size, Color);
	Tile.BlendMode = SE_BLEND_Translucent;
	Canvas->DrawItem(Tile);
}

void ATreadM1HUD::DrawLabel(const FString& Text, const FVector2D& Position, float Scale, const FLinearColor& Color) const
{
	if (!Canvas) return;
	FCanvasTextItem Item(Position, FText::FromString(Text), GEngine->GetLargeFont(), Color);
	Item.Scale = FVector2D(Scale, Scale);
	Item.EnableShadow(FLinearColor::Black, FVector2D(2.0f, 2.0f));
	Canvas->DrawItem(Item);
}

void ATreadM1HUD::DrawHUD()
{
	Super::DrawHUD();
	ATreadM1MatchController* Controller = FindMatchController();
	if (!Controller || !Canvas) return;
	const float Width = Canvas->SizeX;
	const float Height = Canvas->SizeY;
	const float Scale = FMath::Max(0.65f, FMath::Min(Width / 1920.0f, Height / 1080.0f));
	DrawMatchHeader(*Controller, Width, Scale);
	DrawBoard(*Controller, Width, Height, Scale);
	DrawBottomEconomy(*Controller, Width, Height, Scale);
	DrawRightRoster(*Controller, Width, Height, Scale);
	DrawSquadPanel(*Controller, Width, Height, Scale);
	DrawPhaseOverlay(*Controller, Width, Height, Scale);
}

void ATreadM1HUD::DrawMatchHeader(const ATreadM1MatchController& Controller, float Width, float Scale) const
{
	const FTreadM1MatchState& State = Controller.MatchState;
	DrawPanel(FVector2D(0, 0), FVector2D(Width, 92 * Scale), FLinearColor(0.025f, 0.035f, 0.06f, 0.94f));
	DrawLabel(TEXT("TREAD // M1 MATCH"), FVector2D(28 * Scale, 16 * Scale), 1.0f * Scale, FLinearColor(0.86f, 0.93f, 1.0f));
	DrawLabel(FString::Printf(TEXT("R%d  %s  |  %s"), State.RoundIndex, *UEnum::GetValueAsString(State.Phase).RightChop(13), *UEnum::GetValueAsString(State.RoundType).RightChop(16)), FVector2D(28 * Scale, 52 * Scale), 0.62f * Scale, FLinearColor(0.45f, 0.7f, 0.82f));
	if (State.Players.Num() > 0)
	{
		const FTreadM1PlayerState& Player = State.Players[0];
		DrawLabel(FString::Printf(TEXT("HP %d   ¤ %d   LV %d   POP %d/%d   +%d"), Player.Health, Player.Funds, Player.Level, Player.PopulationUsed, Player.PopulationLimit, Player.NextRoundIncome.Base + Player.NextRoundIncome.Interest + Player.NextRoundIncome.Streak + Player.NextRoundIncome.Other), FVector2D(610 * Scale, 28 * Scale), 0.72f * Scale, FLinearColor(1.0f, 0.86f, 0.56f));
	}
	DrawLabel(FString::Printf(TEXT("SEED %lld"), State.Seed), FVector2D(Width - 180 * Scale, 24 * Scale), 0.52f * Scale, FLinearColor(0.55f, 0.6f, 0.7f));
}

void ATreadM1HUD::DrawBoard(const ATreadM1MatchController& Controller, float Width, float Height, float Scale) const
{
	const float Left = 150 * Scale;
	const float Top = 150 * Scale;
	const float Cell = 76 * Scale;
	DrawLabel(TEXT("BOARD // PLAYER 0"), FVector2D(Left, Top - 38 * Scale), 0.65f * Scale, FLinearColor(0.76f, 0.87f, 0.92f));
	for (int32 Y = 0; Y < 8; ++Y)
	{
		for (int32 X = 0; X < 8; ++X)
		{
			const bool bHome = Y >= 4;
			const FLinearColor CellColor = bHome ? FLinearColor(0.09f, 0.2f, 0.24f, 0.78f) : FLinearColor(0.12f, 0.15f, 0.2f, 0.65f);
			DrawPanel(FVector2D(Left + X * Cell, Top + Y * Cell), FVector2D(Cell - 3 * Scale, Cell - 3 * Scale), CellColor);
		}
	}
	if (Controller.MatchState.Players.Num() == 0) return;
	const FTreadM1PlayerState& Player = Controller.MatchState.Players[0];
	for (const FTreadM1UnitInstance& Unit : Player.BoardUnits)
	{
		if (Unit.BoardCell.X < 0 || Unit.BoardCell.Y < 0) continue;
		const float X = Left + Unit.BoardCell.X * Cell + 10 * Scale;
		const float Y = Top + Unit.BoardCell.Y * Cell + 10 * Scale;
		DrawPanel(FVector2D(X, Y), FVector2D(Cell - 23 * Scale, Cell - 23 * Scale), FLinearColor(0.18f, 0.52f, 0.64f, 0.92f));
		DrawLabel(FString::Printf(TEXT("%s\n★%d"), *Unit.CharacterId, Unit.UnitStar), FVector2D(X + 5 * Scale, Y + 8 * Scale), 0.43f * Scale, FLinearColor::White);
	}
}

void ATreadM1HUD::DrawBottomEconomy(const ATreadM1MatchController& Controller, float Width, float Height, float Scale) const
{
	if (Controller.MatchState.Players.Num() == 0) return;
	const FTreadM1PlayerState& Player = Controller.MatchState.Players[0];
	const float BenchTop = Height - 180 * Scale;
	DrawPanel(FVector2D(108 * Scale, BenchTop - 8 * Scale), FVector2D(1040 * Scale, 86 * Scale), FLinearColor(0.035f, 0.06f, 0.09f, 0.9f));
	DrawLabel(TEXT("BENCH // 8"), FVector2D(120 * Scale, BenchTop + 10 * Scale), 0.54f * Scale, FLinearColor(0.63f, 0.76f, 0.82f));
	for (int32 Slot = 0; Slot < 8; ++Slot)
	{
		const float X = (220 + Slot * 112) * Scale;
		DrawPanel(FVector2D(X, BenchTop + 4 * Scale), FVector2D(100 * Scale, 58 * Scale), FLinearColor(0.1f, 0.14f, 0.18f, 0.95f));
		if (Player.BenchUnits.IsValidIndex(Slot))
		{
			const FTreadM1UnitInstance& Unit = Player.BenchUnits[Slot];
			DrawLabel(Unit.CharacterId, FVector2D(X + 8 * Scale, BenchTop + 13 * Scale), 0.42f * Scale, FLinearColor(0.9f, 0.94f, 1.0f));
			DrawLabel(FString::Printf(TEXT("★%d  %s"), Unit.UnitStar, *Unit.OperatorTier), FVector2D(X + 8 * Scale, BenchTop + 38 * Scale), 0.34f * Scale, FLinearColor(0.55f, 0.78f, 0.86f));
		}
	}
	const float ShopTop = Height - 94 * Scale;
	DrawPanel(FVector2D(108 * Scale, ShopTop - 8 * Scale), FVector2D(1440 * Scale, 82 * Scale), FLinearColor(0.035f, 0.06f, 0.09f, 0.94f));
	DrawLabel(TEXT("SHOP"), FVector2D(120 * Scale, ShopTop + 16 * Scale), 0.55f * Scale, FLinearColor(0.63f, 0.76f, 0.82f));
	for (int32 Slot = 0; Slot < Player.Shop.Slots.Num(); ++Slot)
	{
		const FTreadM1ShopSlot& ShopSlot = Player.Shop.Slots[Slot];
		const float X = (220 + Slot * 210) * Scale;
		DrawPanel(FVector2D(X, ShopTop + 4 * Scale), FVector2D(190 * Scale, 56 * Scale), ShopSlot.bIsSold ? FLinearColor(0.08f, 0.09f, 0.11f, 0.75f) : FLinearColor(0.12f, 0.22f, 0.25f, 0.96f));
		DrawLabel(ShopSlot.bIsSold ? TEXT("SOLD") : FString::Printf(TEXT("%s  %s"), *ShopSlot.CharacterId, *ShopSlot.OperatorTier), FVector2D(X + 10 * Scale, ShopTop + 15 * Scale), 0.42f * Scale, FLinearColor::White);
		DrawLabel(ShopSlot.bIsSold ? TEXT("") : FString::Printf(TEXT("¤ %d"), ShopSlot.Cost), FVector2D(X + 10 * Scale, ShopTop + 39 * Scale), 0.38f * Scale, FLinearColor(1.0f, 0.82f, 0.48f));
	}
}

void ATreadM1HUD::DrawRightRoster(const ATreadM1MatchController& Controller, float Width, float Height, float Scale) const
{
	const float X = Width - 360 * Scale;
	DrawPanel(FVector2D(X, 126 * Scale), FVector2D(330 * Scale, Height - 330 * Scale), FLinearColor(0.035f, 0.05f, 0.08f, 0.87f));
	DrawLabel(TEXT("SCOUT SNAPSHOT // READ ONLY"), FVector2D(X + 18 * Scale, 148 * Scale), 0.48f * Scale, FLinearColor(0.64f, 0.83f, 0.88f));
	for (int32 Index = 0; Index < Controller.MatchState.Players.Num(); ++Index)
	{
		const FTreadM1PlayerState& Player = Controller.MatchState.Players[Index];
		const float Y = 194 * Scale + Index * 70 * Scale;
		const FLinearColor Row = Player.bIsEliminated ? FLinearColor(0.2f, 0.08f, 0.1f, 0.9f) : FLinearColor(0.08f, 0.12f, 0.16f, 0.9f);
		DrawPanel(FVector2D(X + 12 * Scale, Y), FVector2D(306 * Scale, 58 * Scale), Row);
		DrawLabel(FString::Printf(TEXT("%d  %s"), Player.Rank > 0 ? Player.Rank : Index + 1, *Player.DisplayName), FVector2D(X + 22 * Scale, Y + 8 * Scale), 0.45f * Scale, FLinearColor::White);
		DrawLabel(FString::Printf(TEXT("HP %d   LV %d   %d/%d   BOARD %d"), Player.Health, Player.Level, Player.PopulationUsed, Player.PopulationLimit, Player.BoardUnits.Num()), FVector2D(X + 22 * Scale, Y + 32 * Scale), 0.34f * Scale, Player.bIsEliminated ? FLinearColor(1.0f, 0.35f, 0.4f) : FLinearColor(0.55f, 0.75f, 0.8f));
	}
}

UTexture2D* ATreadM1HUD::PortraitFor(const FString& CharacterId) const
{
	// Portraits come from the M4 avatar pass (one texture per character).
	static TMap<FString, UTexture2D*> Cache;
	if (const UTexture2D* const* Found = Cache.Find(CharacterId))
	{
		return const_cast<UTexture2D*>(*Found);
	}
	const FString Path = FString::Printf(TEXT("/Game/Tread/UI/Avatars/T_Avatar_%s.T_Avatar_%s"), *CharacterId, *CharacterId);
	UTexture2D* Texture = LoadObject<UTexture2D>(nullptr, *Path);
	Cache.Add(CharacterId, Texture);
	return Texture;
}

void ATreadM1HUD::DrawSquadPanel(const ATreadM1MatchController& Controller, float Width, float Height, float Scale) const
{
	const FTreadM1MatchState& State = Controller.MatchState;
	if (State.Players.Num() == 0)
	{
		return;
	}
	const FTreadM1PlayerState& Player = State.Players[0];
	const TArray<FTreadM1UnitInstance>& Units = Player.BoardUnits;
	const float PanelW = 268 * Scale;
	const float RowH = 62 * Scale;
	const float PanelH = (Units.Num() > 0 ? Units.Num() : 1) * RowH + 46 * Scale;
	const float X = 24 * Scale;
	const float Y = Height - PanelH - 118 * Scale;
	DrawPanel(FVector2D(X, Y), FVector2D(PanelW, PanelH), FLinearColor(0.02f, 0.05f, 0.08f, 0.9f));
	DrawLabel(TEXT("SQUAD // 技力"), FVector2D(X + 12 * Scale, Y + 10 * Scale), 0.5f * Scale, FLinearColor(0.55f, 0.82f, 0.7f));

	for (int32 Index = 0; Index < Units.Num(); ++Index)
	{
		const FTreadM1UnitInstance& Unit = Units[Index];
		const float RowY = Y + 38 * Scale + Index * RowH;
		const float PortraitSize = 46 * Scale;
		const FVector2D PortraitPos(X + 10 * Scale, RowY);
		if (UTexture2D* Portrait = PortraitFor(Unit.CharacterId))
		{
			FCanvasTileItem Tile(PortraitPos, Portrait->GetResource(), FVector2D(PortraitSize, PortraitSize), FLinearColor::White);
			Tile.BlendMode = SE_BLEND_Translucent;
			Canvas->DrawItem(Tile);
		}
		else
		{
			DrawPanel(PortraitPos, FVector2D(PortraitSize, PortraitSize), FLinearColor(0.1f, 0.16f, 0.2f, 1.0f));
			DrawLabel(Unit.CharacterId.Right(3), PortraitPos + FVector2D(6 * Scale, 14 * Scale), 0.4f * Scale, FLinearColor(0.7f, 0.8f, 0.85f));
		}

		const float BarX = PortraitPos.X + PortraitSize + 10 * Scale;
		const float BarW = PanelW - (BarX - X) - 14 * Scale;
		const float HpFraction = State.Phase == ETreadM1Phase::Battle || State.Phase == ETreadM1Phase::Settlement
			? Controller.GetUnitHealthFraction(Player.PlayerId, Unit.UnitInstanceId) : 1.0f;
		const float SpFraction = Controller.GetUnitSpFraction(Player.PlayerId, Unit.UnitInstanceId);

		// health: player blue, drained from the right
		DrawPanel(FVector2D(BarX, RowY + 16 * Scale), FVector2D(BarW, 9 * Scale), FLinearColor(0.05f, 0.09f, 0.12f, 0.95f));
		DrawPanel(FVector2D(BarX, RowY + 16 * Scale), FVector2D(BarW * FMath::Clamp(HpFraction, 0.0f, 1.0f), 9 * Scale),
			FLinearColor(0.22f, 0.55f, 0.95f, 1.0f));

		// 技力: green, the panel's whole reason to exist
		DrawPanel(FVector2D(BarX, RowY + 30 * Scale), FVector2D(BarW, 7 * Scale), FLinearColor(0.04f, 0.1f, 0.07f, 0.95f));
		DrawPanel(FVector2D(BarX, RowY + 30 * Scale), FVector2D(BarW * FMath::Clamp(SpFraction, 0.0f, 1.0f), 7 * Scale),
			FLinearColor(0.28f, 0.92f, 0.46f, 1.0f));

		DrawLabel(FString::Printf(TEXT("%s  ★%d%s"), *Unit.CharacterId, Unit.UnitStar,
			Controller.GetUnitAmmo(Player.PlayerId, Unit.UnitInstanceId) > 0
				? *FString::Printf(TEXT("  ▮%d"), Controller.GetUnitAmmo(Player.PlayerId, Unit.UnitInstanceId)) : TEXT("")),
			FVector2D(BarX, RowY - 2 * Scale), 0.4f * Scale, FLinearColor(0.82f, 0.9f, 0.96f));
	}
}

void ATreadM1HUD::DrawPhaseOverlay(const ATreadM1MatchController& Controller, float Width, float Height, float Scale) const
{
	const FTreadM1MatchState& State = Controller.MatchState;
	const float X = Width - 520 * Scale;
	if (State.Phase == ETreadM1Phase::PreMatchBP)
	{
		DrawPanel(FVector2D(X, 760 * Scale), FVector2D(500 * Scale, 220 * Scale), FLinearColor(0.05f, 0.08f, 0.14f, 0.96f));
		DrawLabel(TEXT("PRE-MATCH BP // 32 CANDIDATES / 4 BAN"), FVector2D(X + 20 * Scale, 780 * Scale), 0.5f * Scale, FLinearColor(0.86f, 0.76f, 0.46f));
		DrawLabel(FString::Printf(TEXT("PLAYER  %s"), State.BP.PlayerStrategyId.IsEmpty() ? TEXT("SELECTING") : *State.BP.PlayerStrategyId), FVector2D(X + 20 * Scale, 818 * Scale), 0.42f * Scale, FLinearColor::White);
		for (int32 Index = 0; Index < State.BP.AiPickStates.Num(); ++Index)
		{
			const FString Status = State.BP.AiPickStates[Index] == ETreadM1AIPickState::Confirmed ? TEXT("CONFIRMED") : State.BP.AiPickStates[Index] == ETreadM1AIPickState::Thinking ? TEXT("THINKING") : TEXT("WAITING");
			DrawLabel(FString::Printf(TEXT("AI-%d  %s  %s"), Index + 1, *Status, *State.BP.AiStrategyIds[Index]), FVector2D(X + 20 * Scale, (850 + Index * 28) * Scale), 0.38f * Scale, FLinearColor(0.65f, 0.82f, 0.88f));
		}
	}
	else if (State.Phase == ETreadM1Phase::Settlement || State.Phase == ETreadM1Phase::GameOver)
	{
		DrawPanel(FVector2D(X, 760 * Scale), FVector2D(500 * Scale, 220 * Scale), FLinearColor(0.06f, 0.09f, 0.14f, 0.96f));
		DrawLabel(TEXT("BATTLE RESULT // SETTLEMENT"), FVector2D(X + 20 * Scale, 780 * Scale), 0.52f * Scale, FLinearColor(0.9f, 0.78f, 0.46f));
		for (int32 Index = 0; Index < State.LastBattleResult.Outcomes.Num(); ++Index)
		{
			const FTreadM1BattleOutcome& Outcome = State.LastBattleResult.Outcomes[Index];
			DrawLabel(FString::Printf(TEXT("%s  %s  HP %d -> %d  SURV %d"), *Outcome.PlayerId, *Outcome.Outcome, Outcome.HealthBefore, Outcome.HealthAfter, Outcome.SurvivingUnitCount), FVector2D(X + 20 * Scale, (820 + Index * 28) * Scale), 0.35f * Scale, Outcome.Outcome == TEXT("Win") ? FLinearColor(0.45f, 1.0f, 0.65f) : FLinearColor(1.0f, 0.45f, 0.5f));
		}
		DrawLabel(FString::Printf(TEXT("EVENTS %d  |  PAIRS %d  |  AUTO BATTLE ON"), State.BattleEvents.Num(), State.LastBattleResult.Pairings.Num()), FVector2D(X + 20 * Scale, 946 * Scale), 0.36f * Scale, FLinearColor(0.58f, 0.72f, 0.82f));
	}
	else
	{
		DrawLabel(State.Phase == ETreadM1Phase::Battle ? TEXT("AUTO BATTLE  //  TARGETING ACTIVE") : TEXT("DEPLOY COMPLETE  //  AUTO BATTLE ENABLED"), FVector2D(Width - 660 * Scale, Height - 256 * Scale), 0.48f * Scale, FLinearColor(0.85f, 0.9f, 0.74f));
	}
}
