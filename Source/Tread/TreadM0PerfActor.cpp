#include "TreadM0PerfActor.h"

#include "Algo/MaxElement.h"
#include "Engine/Engine.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/DateTime.h"
#include "ProfilingDebugging/RealtimeGPUProfiler.h"
#include "RenderCore.h"
#include "RenderTimer.h"
#include "RHI.h"
#include "RHIStats.h"
#include "RHIGlobals.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Kismet/KismetSystemLibrary.h"

namespace
{
	float Average(const TArray<float>& Values)
	{
		if (Values.Num() == 0)
		{
			return 0.0f;
		}
		float Sum = 0.0f;
		for (const float Value : Values)
		{
			Sum += Value;
		}
		return Sum / Values.Num();
	}

	float Percentile(TArray<float> Values, float Fraction)
	{
		if (Values.Num() == 0)
		{
			return 0.0f;
		}
		Values.Sort();
		const int32 Index = FMath::Clamp(FMath::RoundToInt(Fraction * (Values.Num() - 1)), 0, Values.Num() - 1);
		return Values[Index];
	}
}

ATreadM0PerfActor::ATreadM0PerfActor()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostUpdateWork;
}

void ATreadM0PerfActor::BeginPlay()
{
	Super::BeginPlay();
	if (GEngine && GetWorld())
	{
		GEngine->Exec(GetWorld(), TEXT("StartFPSChart M0_Paris_1080p"));
	}
}

void ATreadM0PerfActor::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	ElapsedSeconds += DeltaSeconds;
	if (ElapsedSeconds > WarmupSeconds)
	{
		FrameTimesMs.Add(DeltaSeconds * 1000.0f);
		GameTimesMs.Add(FPlatformTime::ToMilliseconds(GGameThreadTime));
		RenderTimesMs.Add(FPlatformTime::ToMilliseconds(GRenderThreadTime));
		GpuTimesMs.Add(FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles()));
		DrawCalls.Add(GNumDrawCallsRHI[0]);
		Primitives.Add(GNumPrimitivesDrawnRHI[0]);
		FrameNumbers.Add(GFrameCounter);
	}
	if (ElapsedSeconds >= WarmupSeconds + SampleSeconds)
	{
		if (GEngine && GetWorld())
		{
			GEngine->Exec(GetWorld(), TEXT("StopFPSChart"));
		}
		WriteReport();
		UKismetSystemLibrary::QuitGame(this, nullptr, EQuitPreference::Quit, false);
		SetActorTickEnabled(false);
	}
}

void ATreadM0PerfActor::WriteReport()
{
	const float AverageFrameMs = Average(FrameTimesMs);
	const float OnePercentLowFrameMs = Percentile(FrameTimesMs, 0.99f);
	const FPlatformMemoryStats Memory = FPlatformMemory::GetStats();
	FTextureMemoryStats TextureMemory;
	RHIGetTextureMemoryStats(TextureMemory);
	TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetStringField(TEXT("date"), FDateTime::Now().ToString());
	Root->SetStringField(TEXT("map"), GetWorld() ? GetWorld()->GetMapName() : TEXT("unknown"));
	Root->SetStringField(TEXT("resolution"), TEXT("1920x1080"));
	Root->SetStringField(TEXT("rhi"), GDynamicRHI ? GDynamicRHI->GetName() : TEXT("unknown"));
	Root->SetNumberField(TEXT("warmup_seconds"), WarmupSeconds);
	Root->SetNumberField(TEXT("sample_seconds"), SampleSeconds);
	Root->SetNumberField(TEXT("frames"), FrameTimesMs.Num());
	Root->SetNumberField(TEXT("average_fps"), AverageFrameMs > 0.0f ? 1000.0f / AverageFrameMs : 0.0f);
	Root->SetNumberField(TEXT("one_percent_low_fps"), OnePercentLowFrameMs > 0.0f ? 1000.0f / OnePercentLowFrameMs : 0.0f);
	Root->SetNumberField(TEXT("average_frame_ms"), AverageFrameMs);
	Root->SetNumberField(TEXT("average_game_ms"), Average(GameTimesMs));
	Root->SetNumberField(TEXT("average_render_ms"), Average(RenderTimesMs));
	Root->SetNumberField(TEXT("average_gpu_ms"), Average(GpuTimesMs));
	Root->SetNumberField(TEXT("peak_gpu_ms"), GpuTimesMs.Num() ? *Algo::MaxElement(GpuTimesMs) : 0.0f);
	Root->SetNumberField(TEXT("p50_frame_ms"), Percentile(FrameTimesMs, 0.50f));
	Root->SetNumberField(TEXT("p95_frame_ms"), Percentile(FrameTimesMs, 0.95f));
	Root->SetNumberField(TEXT("p99_frame_ms"), Percentile(FrameTimesMs, 0.99f));
	int32 Over20 = 0;
	int32 Over25 = 0;
	for (const float FrameMs : FrameTimesMs)
	{
		if (FrameMs > 20.0f) ++Over20;
		if (FrameMs > 25.0f) ++Over25;
	}
	Root->SetNumberField(TEXT("frames_over_20ms"), Over20);
	Root->SetNumberField(TEXT("frames_over_25ms"), Over25);
	double DrawSum = 0.0;
	double PrimSum = 0.0;
	for (int32 Index = 0; Index < DrawCalls.Num(); ++Index) DrawSum += DrawCalls[Index];
	for (int32 Index = 0; Index < Primitives.Num(); ++Index) PrimSum += Primitives[Index];
	Root->SetNumberField(TEXT("average_draw_calls"), DrawCalls.Num() ? DrawSum / DrawCalls.Num() : 0.0);
	Root->SetNumberField(TEXT("average_primitives"), Primitives.Num() ? PrimSum / Primitives.Num() : 0.0);
	// Slow-frame table: the ten worst frames with their thread/GPU split, so the 1% low can be attributed.
	TArray<int32> Order;
	for (int32 Index = 0; Index < FrameTimesMs.Num(); ++Index) Order.Add(Index);
	Order.Sort([this](int32 A, int32 B) { return FrameTimesMs[A] > FrameTimesMs[B]; });
	TArray<TSharedPtr<FJsonValue>> SlowFrames;
	for (int32 Rank = 0; Rank < FMath::Min(10, Order.Num()); ++Rank)
	{
		const int32 Index = Order[Rank];
		const TSharedRef<FJsonObject> Entry = MakeShared<FJsonObject>();
		Entry->SetNumberField(TEXT("frame"), static_cast<double>(FrameNumbers.IsValidIndex(Index) ? FrameNumbers[Index] : Index));
		Entry->SetNumberField(TEXT("frame_ms"), FrameTimesMs[Index]);
		Entry->SetNumberField(TEXT("game_ms"), GameTimesMs.IsValidIndex(Index) ? GameTimesMs[Index] : 0.0f);
		Entry->SetNumberField(TEXT("render_ms"), RenderTimesMs.IsValidIndex(Index) ? RenderTimesMs[Index] : 0.0f);
		Entry->SetNumberField(TEXT("gpu_ms"), GpuTimesMs.IsValidIndex(Index) ? GpuTimesMs[Index] : 0.0f);
		Entry->SetNumberField(TEXT("draw_calls"), DrawCalls.IsValidIndex(Index) ? DrawCalls[Index] : 0);
		Entry->SetNumberField(TEXT("primitives"), Primitives.IsValidIndex(Index) ? Primitives[Index] : 0);
		SlowFrames.Add(MakeShared<FJsonValueObject>(Entry));
	}
	Root->SetArrayField(TEXT("slow_frames"), SlowFrames);
	Root->SetNumberField(TEXT("physical_memory_used_mb"), static_cast<double>(Memory.UsedPhysical) / 1048576.0);
	Root->SetNumberField(TEXT("physical_memory_peak_mb"), static_cast<double>(Memory.PeakUsedPhysical) / 1048576.0);
	Root->SetNumberField(TEXT("physical_memory_total_mb"), static_cast<double>(Memory.TotalPhysical) / 1048576.0);
	Root->SetNumberField(TEXT("dedicated_video_memory_mb"), static_cast<double>(GRHIGlobals.GpuInfo.DedicatedVideoMemory) / 1048576.0);
	Root->SetNumberField(TEXT("total_graphics_memory_mb"), static_cast<double>(TextureMemory.TotalGraphicsMemory) / 1048576.0);
	Root->SetBoolField(TEXT("target_prepare_average_fps_pass"), AverageFrameMs > 0.0f && 1000.0f / AverageFrameMs >= 60.0f);
	Root->SetBoolField(TEXT("target_prepare_one_percent_low_pass"), OnePercentLowFrameMs > 0.0f && 1000.0f / OnePercentLowFrameMs >= 60.0f);
	Root->SetBoolField(TEXT("target_battle_average_fps_pass"), AverageFrameMs > 0.0f && 1000.0f / AverageFrameMs >= 45.0f);
	FString Output;
	const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Output);
	FJsonSerializer::Serialize(Root, Writer);
	FFileHelper::SaveStringToFile(Output, *(FPaths::ProjectSavedDir() / TEXT("Reports/M0_Paris_Render_Baseline.json")));
}
