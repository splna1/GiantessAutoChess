"""Replayable source patch: adds the M2 pact panel to the native M1 HUD widget."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
h = ROOT / "Source/Tread/TreadM1MatchWidget.h"
c = ROOT / "Source/Tread/TreadM1MatchWidget.cpp"

hs = h.read_text(encoding="utf-8")
if "DrawPacts" in hs:
    raise SystemExit("already patched")
anchor = "\tvoid DrawResult(const FGeometry& Geometry, FSlateWindowElementList& OutDrawElements, int32 LayerId) const;"
assert hs.count(anchor) == 1
hs = hs.replace(anchor, anchor + """
	/** M2 pact tiers, stacks, trait X/Y values and event-bus log. bCompact = battle-phase summary. */
	void DrawPacts(const FGeometry& Geometry, FSlateWindowElementList& OutDrawElements, int32 LayerId,
		const FVector2D& Origin, const FVector2D& Size, const FTreadM1PlayerState& PlayerState, bool bCompact) const;""")

s = c.read_text(encoding="utf-8")


def rep(a, b):
    global s
    assert s.count(a) == 1, a[:100]
    s = s.replace(a, b)


rep("""		DrawText(Out, Geometry, Layer + 2, FString::Printf(TEXT("下轮收入：基础 %d + 利息 %d + 连胜/败 %d"), P->NextRoundIncome.Base, P->NextRoundIncome.Interest, P->NextRoundIncome.Streak), RefVec(1320, 640), 17, Funds);""",
    """		// Income breakdown sits on its own panel so it never draws straight over the 3D city.
		DrawPanel(Out, Geometry, Layer + 1, RefVec(1592, 606), RefVec(312, 40), BgPanel);
		DrawPanel(Out, Geometry, Layer + 1, RefVec(1252, 650), RefVec(652, 38), BgPanel);
		DrawText(Out, Geometry, Layer + 2, FString::Printf(TEXT("下轮收入：基础 %d + 利息 %d + 连胜/败 %d + 特质 %d"), P->NextRoundIncome.Base, P->NextRoundIncome.Interest, P->NextRoundIncome.Streak, P->NextRoundIncome.Other), RefVec(1266, 657), 17, Funds);
		DrawPacts(Geometry, Out, Layer + 4, FVector2D(16, 196), FVector2D(504, 744), *P, false);""")
rep("""	DrawPanel(Out, Geometry, Layer + 1, RefVec(750, 118), RefVec(420, 54), FLinearColor(0.08f, 0.24f, 0.34f, 0.92f), true);""",
    """	if (const FTreadM1PlayerState* P = GetHumanPlayer()) DrawPacts(Geometry, Out, Layer + 4, FVector2D(16, 548), FVector2D(504, 400), *P, true);
	DrawPanel(Out, Geometry, Layer + 1, RefVec(750, 118), RefVec(420, 54), FLinearColor(0.08f, 0.24f, 0.34f, 0.92f), true);""")
rep("""		DrawText(Out, Geometry, Layer + 3, FString::Printf(TEXT("备战席 %d / 8    装备 %d    盟约层数 %d"), Snapshot->BenchUnits.Num(), Snapshot->EquipmentIds.Num(), Snapshot->PactStacks.Num()), RefVec(676, 442), 15, TextSecondary);""",
    """		DrawText(Out, Geometry, Layer + 3, FString::Printf(TEXT("备战席 %d / 8    装备 %d    盟约层数 %d"), Snapshot->BenchUnits.Num(), Snapshot->EquipmentIds.Num(), Snapshot->PactStacks.Num()), RefVec(676, 442), 15, TextSecondary);
		DrawText(Out, Geometry, Layer + 3, TEXT("盟约 · 人数 / 层数"), RefVec(1124, 196), 16, PlayerText, true);
		int32 ScoutRow = 0;
		for (const FTreadM2PactProgress& Pact : Snapshot->Pacts)
		{
			if ((Pact.Count <= 0 && Pact.Stacks <= 0) || ScoutRow >= 11) continue;
			const float Y = 224 + ScoutRow++ * 22;
			DrawText(Out, Geometry, Layer + 4, FString::Printf(TEXT("%s%s  %d/%d  层 %d"), Pact.bActive ? TEXT("● ") : TEXT("○ "), *Pact.PactId, Pact.Count,
				Pact.NextThreshold > 0 ? Pact.NextThreshold : (Pact.Thresholds.Num() > 0 ? Pact.Thresholds.Last() : 0), Pact.Stacks),
				RefVec(1124, Y), 14, Pact.bActive ? Funds : TextSecondary, Pact.bActive, FVector2D(410, 22));
		}""")

s += r'''
void UTreadM1MatchWidget::DrawPacts(const FGeometry& Geometry, FSlateWindowElementList& Out, int32 Layer,
	const FVector2D& Origin, const FVector2D& Size, const FTreadM1PlayerState& P, bool bCompact) const
{
	if (!Controller.IsValid()) return;
	const FLinearColor CoreActive(0.46f, 0.30f, 0.06f, 0.94f);
	const FLinearColor AdjunctActive(0.05f, 0.30f, 0.36f, 0.94f);
	const FLinearColor PipOff(0.20f, 0.25f, 0.33f, 0.90f);
	const int32 LatestSequence = Controller->MatchState.TraitLog.Num();
	const float Pulse = GetWorld() ? 0.5f + 0.5f * FMath::Sin(GetWorld()->GetTimeSeconds() * 5.0f) : 1.0f;
	DrawPanel(Out, Geometry, Layer, RefVec(Origin.X, Origin.Y), RefVec(Size.X, Size.Y), BgPanel, true);
	int32 ActiveCount = 0;
	int32 TotalStacks = 0;
	TArray<const FTreadM2PactProgress*> Rows;
	for (const FTreadM2PactProgress& Pact : P.Pacts)
	{
		ActiveCount += Pact.bActive ? 1 : 0;
		TotalStacks += Pact.Stacks;
		if ((Pact.Count > 0 || Pact.Stacks > 0) && (!bCompact || Pact.bActive || Pact.Stacks > 0)) Rows.Add(&Pact);
	}
	Rows.StableSort([](const FTreadM2PactProgress& A, const FTreadM2PactProgress& B)
	{
		if (A.ActiveTier != B.ActiveTier) return A.ActiveTier > B.ActiveTier;
		if (A.Count != B.Count) return A.Count > B.Count;
		return A.Stacks > B.Stacks;
	});
	DrawText(Out, Geometry, Layer + 2, bCompact ? TEXT("盟约层数 · 战斗快照") : TEXT("盟约 · 人数档位 / 层数"), RefVec(Origin.X + 18, Origin.Y + 12), 20, TextPrimary, true);
	DrawText(Out, Geometry, Layer + 2, FString::Printf(TEXT("已激活 %d  ·  层数合计 %d  ·  待结算特质资金 ¤%d"), ActiveCount, TotalStacks, P.PendingTraitIncome),
		RefVec(Origin.X + 18, Origin.Y + 42), 14, TextSecondary, false, FVector2D(Size.X - 30, 24));
	const int32 MaxRows = bCompact ? 6 : 9;
	const float RowHeight = 40.0f;
	float Y = Origin.Y + 70;
	if (Rows.Num() == 0)
	{
		DrawText(Out, Geometry, Layer + 2, TEXT("尚无盟约成员：上阵单位后显示人数与层数"), RefVec(Origin.X + 18, Y + 8), 15, TextSecondary);
	}
	for (int32 Index = 0; Index < Rows.Num() && Index < MaxRows; ++Index, Y += RowHeight)
	{
		const FTreadM2PactProgress& Pact = *Rows[Index];
		const bool bCore = Pact.Kind == TEXT("Core");
		const bool bRecent = Pact.LastChangeSequence > 0 && Pact.LastChangeSequence > LatestSequence - 8;
		FLinearColor RowColor = Pact.bActive ? (bCore ? CoreActive : AdjunctActive) : BgInset;
		if (bRecent) RowColor = FMath::Lerp(RowColor, FLinearColor(0.95f, 0.75f, 0.25f, 0.95f), 0.35f * Pulse);
		DrawPanel(Out, Geometry, Layer + 1, RefVec(Origin.X + 12, Y), RefVec(Size.X - 24, RowHeight - 4), RowColor, Pact.bActive);
		if (Pact.bActive) DrawDivider(Out, Geometry, Layer + 2, RefVec(Origin.X + 12, Y), RefVec(4, RowHeight - 4), bCore ? Funds : Info);
		DrawText(Out, Geometry, Layer + 3, Pact.PactId, RefVec(Origin.X + 24, Y + 8), 17, Pact.bActive ? TextPrimary : TextSecondary, true, FVector2D(110, 26));
		DrawText(Out, Geometry, Layer + 3, bCore ? TEXT("核心") : TEXT("加盟"), RefVec(Origin.X + 132, Y + 11), 12, bCore ? Funds : Info);
		// One pip per threshold: filled when reached, labelled with the member count it needs.
		for (int32 Tier = 0; Tier < Pact.Thresholds.Num(); ++Tier)
		{
			const bool bReached = Tier < Pact.ActiveTier;
			const float PipX = Origin.X + 172 + Tier * 34;
			DrawPanel(Out, Geometry, Layer + 2, RefVec(PipX, Y + 7), RefVec(28, 22), bReached ? (bCore ? Funds : Success) : PipOff, bReached);
			DrawText(Out, Geometry, Layer + 3, FString::FromInt(Pact.Thresholds[Tier]), RefVec(PipX + 8, Y + 9), 13, bReached ? BgInset : TextSecondary, true, FVector2D(24, 20));
		}
		FString CountText = FString::Printf(TEXT("%d 人"), Pact.Count);
		if (Pact.HarmonyBonus > 0) CountText += FString::Printf(TEXT(" (调和+%d)"), Pact.HarmonyBonus);
		if (Pact.BenchCount > 0) CountText += FString::Printf(TEXT(" 备战+%d"), Pact.BenchCount);
		DrawText(Out, Geometry, Layer + 3, CountText, RefVec(Origin.X + 248, Y + 10), 14, TextPrimary, false, FVector2D(150, 22));
		DrawText(Out, Geometry, Layer + 3, FString::Printf(TEXT("层 %d"), Pact.Stacks), RefVec(Origin.X + Size.X - 110, Y + 8), 17, Pact.Stacks > 0 ? Funds : TextSecondary, true, FVector2D(80, 24));
		if (bRecent && Pact.LastStackDelta > 0)
		{
			DrawText(Out, Geometry, Layer + 3, FString::Printf(TEXT("+%d"), Pact.LastStackDelta), RefVec(Origin.X + Size.X - 48, Y + 10), 14, Success, true, FVector2D(40, 22));
		}
	}
	if (bCompact) Y = Origin.Y + 70 + MaxRows * RowHeight;
	else
	{
		// Trait values of the participant's units: [current] is base for 1-star, elite for 2-star and above.
		Y = Origin.Y + 70 + MaxRows * RowHeight + 6;
		DrawText(Out, Geometry, Layer + 2, TEXT("单位特质  数值 X/Y（[ ] 为当前生效，精锐取后值）"), RefVec(Origin.X + 18, Y), 14, PlayerText, true, FVector2D(Size.X - 30, 22));
		Y += 24;
		TArray<FTreadM1UnitInstance> Units = P.BoardUnits;
		Units.Append(P.BenchUnits);
		for (int32 Index = 0; Index < Units.Num() && Index < 4; ++Index)
		{
			const FTreadM1UnitInstance& Unit = Units[Index];
			FString Summary = Controller->GetTraitSummary(Unit.CharacterId);
			if (Summary.Len() > 22) Summary = Summary.Left(21) + TEXT("…");
			DrawText(Out, Geometry, Layer + 2, FString::Printf(TEXT("%s ★%d  %s  %s"), *Unit.CharacterId.RightChop(5), Unit.UnitStar,
				*Controller->GetTraitValueText(Unit.CharacterId, Unit.UnitStar), *Summary), RefVec(Origin.X + 18, Y + Index * 22), 13,
				Unit.UnitStar >= 2 ? Funds : TextSecondary, false, FVector2D(Size.X - 30, 22));
		}
		Y += 4 * 22 + 6;
	}
	DrawText(Out, Geometry, Layer + 2, TEXT("触发日志"), RefVec(Origin.X + 18, Y), 14, PlayerText, true);
	Y += 24;
	int32 Lines = 0;
	const int32 MaxLines = bCompact ? 3 : 5;
	for (int32 Index = Controller->MatchState.TraitLog.Num() - 1; Index >= 0 && Lines < MaxLines; --Index)
	{
		const FTreadM2TraitLogEntry& Entry = Controller->MatchState.TraitLog[Index];
		if (Entry.PlayerId != P.PlayerId || Entry.Status == TEXT("event")) continue;
		const bool bApplied = Entry.Status.StartsWith(TEXT("applied"));
		FString Line = FString::Printf(TEXT("R%d %s·%s %s %s"), Entry.RoundIndex, *Entry.Trigger, *Entry.Event, *Entry.Op, *Entry.PactId);
		if (Entry.Op == TEXT("AddStacks")) Line += FString::Printf(TEXT(" +%d→%d"), Entry.Amount, Entry.StacksAfter);
		else if (Entry.Amount != 0) Line += FString::Printf(TEXT(" %d"), Entry.Amount);
		if (!bApplied) Line += TEXT("  ") + Entry.Status;
		// Keep every log line inside the panel; long statuses would otherwise spill over the 3D board.
		const int32 MaxChars = FMath::Max(16, FMath::FloorToInt((Size.X - 30) / 9.5f));
		if (Line.Len() > MaxChars) Line = Line.Left(MaxChars - 1) + TEXT("…");
		DrawText(Out, Geometry, Layer + 2, Line, RefVec(Origin.X + 18, Y + Lines * 22), 13, bApplied ? Success : TextSecondary, false, FVector2D(Size.X - 30, 22));
		++Lines;
	}
}
'''
h.write_text(hs, encoding="utf-8")
c.write_text(s, encoding="utf-8")
print("patched widget")
