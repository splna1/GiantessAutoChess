// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;

public class Tread : ModuleRules
{
	public Tread(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
	
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "EnhancedInput", "Json", "RHI", "RenderCore", "UMG", "Slate", "SlateCore" });

		// Niagara: the destruction manager spawns the dust burst with an engine Niagara template (document/162).
		PrivateDependencyModuleNames.AddRange(new string[] { "Niagara" });

		// TreadEditorThumbnails.cpp (editor builds only): the thumbnail manager lives in UnrealEd.
		if (Target.bBuildEditor)
		{
			PrivateDependencyModuleNames.Add("UnrealEd");
		}

		// Uncomment if you are using Slate UI
		// PrivateDependencyModuleNames.AddRange(new string[] { "Slate", "SlateCore" });
		
		// Uncomment if you are using online features
		// PrivateDependencyModuleNames.Add("OnlineSubsystem");

		// To include OnlineSubsystemSteam, add it to the plugins section in your uproject file with the Enabled attribute set to true
	}
}
