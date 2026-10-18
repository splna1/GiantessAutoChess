// Editor-only console command for the batch asset tools under Tools/m4 (document/152).
//
// Every package save renders a thumbnail, and the skeletal mesh, skeleton, IK Rig, IK Retargeter and cloth asset
// thumbnail renderers each keep one preview FScene per rendered asset (TObjectInstanceThumbnailScene<..., 128>),
// about 90 MB of GPU memory per scene (GPU particle state, GPUScene, distance field and physics field buffers).
// A batch over the 100-character roster saves hundreds of such assets and took the 8 GB GPU down twice
// (CreateReservedResource failed).  Unloading the assets does not free the scenes: only the renderer's
// BeginDestroy clears its cache.  Tread.FlushThumbnailScenes swaps those renderers for fresh instances and collects
// garbage, so the old renderers and every scene they cached are destroyed.

#if WITH_EDITOR

#include "HAL/IConsoleManager.h"
#include "ThumbnailRendering/ThumbnailManager.h"
#include "ThumbnailRendering/ThumbnailRenderer.h"
#include "UObject/UnrealType.h"
#include "UObject/UObjectGlobals.h"

namespace
{
	// Renderer classes (and their subclasses, e.g. the IK Rig renderer derives from the skeletal mesh one) that
	// cache one preview scene per asset.
	bool CachesScenePerAsset(const UClass* RendererClass)
	{
		static const FName Names[] = {
			TEXT("SkeletalMeshThumbnailRenderer"), TEXT("SkeletonThumbnailRenderer"),
			TEXT("IKRetargeterThumbnailRenderer"), TEXT("ClothAssetThumbnailRenderer"),
			TEXT("ChaosClothAssetThumbnailRenderer")};
		for (const UClass* Class = RendererClass; Class; Class = Class->GetSuperClass())
		{
			for (const FName& Name : Names)
			{
				if (Class->GetFName() == Name)
				{
					return true;
				}
			}
		}
		return false;
	}

	void FlushThumbnailScenes()
	{
		UThumbnailManager* Manager = UThumbnailManager::TryGet();
		// RenderableThumbnailTypes is protected; it is a reflected property, so reach it through reflection.
		const FArrayProperty* Property = FindFProperty<FArrayProperty>(UThumbnailManager::StaticClass(), TEXT("RenderableThumbnailTypes"));
		if (!Manager || !Property)
		{
			UE_LOG(LogTemp, Warning, TEXT("Tread.FlushThumbnailScenes: no thumbnail manager or renderer list"));
			return;
		}
		TArray<FThumbnailRenderingInfo>& Types = *Property->ContainerPtrToValuePtr<TArray<FThumbnailRenderingInfo>>(Manager);
		int32 Replaced = 0;
		for (FThumbnailRenderingInfo& Info : Types)
		{
			if (Info.Renderer && CachesScenePerAsset(Info.Renderer->GetClass()))
			{
				Info.Renderer = NewObject<UThumbnailRenderer>(GetTransientPackage(), Info.Renderer->GetClass());
				++Replaced;
			}
		}
		CollectGarbage(GARBAGE_COLLECTION_KEEPFLAGS);
		UE_LOG(LogTemp, Display, TEXT("Tread.FlushThumbnailScenes: replaced %d thumbnail renderers"), Replaced);
	}

	FAutoConsoleCommand GFlushThumbnailScenes(
		TEXT("Tread.FlushThumbnailScenes"),
		TEXT("Release the per-asset thumbnail preview scenes (GPU memory) cached by the mesh, skeleton, IK and cloth thumbnail renderers."),
		FConsoleCommandDelegate::CreateStatic(&FlushThumbnailScenes));
}

#endif // WITH_EDITOR
