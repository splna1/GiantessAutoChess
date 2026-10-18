#!/usr/bin/env python
"""Find animation and skeleton assets in the project."""

import unreal

def main():
    eal = unreal.EditorAssetLibrary()

    # Search for all skeletons
    print("=== Searching for Skeletons ===")
    char_dir = "/Game/Tread/Characters"
    all_assets = eal.list_assets(char_dir, recursive=True, include_folder=False)

    skeletons = []
    animations = []
    skeletal_meshes = []

    for asset_path in all_assets:
        try:
            asset = eal.load_asset(asset_path)
            if isinstance(asset, unreal.Skeleton):
                skeletons.append(asset_path)
            elif isinstance(asset, unreal.AnimSequence):
                animations.append(asset_path)
            elif isinstance(asset, unreal.SkeletalMesh):
                skeletal_meshes.append(asset_path)
        except:
            pass

    print(f"\nFound {len(skeletons)} skeletons:")
    for skel in sorted(skeletons):
        print(f"  {skel}")

    print(f"\nFound {len(skeletal_meshes)} skeletal meshes:")
    for mesh in sorted(skeletal_meshes):
        print(f"  {mesh}")

    print(f"\nFound {len(animations)} animations:")
    for anim in sorted(animations):
        print(f"  {anim}")

    return 0

if __name__ == '__main__':
    import sys
    sys.exit(main())
