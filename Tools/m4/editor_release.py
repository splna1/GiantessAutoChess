"""Release what a long editor batch holds on to (editor-side, Tools/ue_run.py), as two separate remote calls:

    python Tools/ue_run.py Tools/m4/editor_release.py reload   # reload the current map: resets the undo buffer
    python Tools/ue_run.py Tools/m4/editor_release.py gc       # unload the VRM packages, collect garbage

The IK Rig / Retargeter controllers record undo transactions, and the editor's TransBuffer keeps every object they
touched alive (obj refs: UUnrealEdEngine::Trans -> TransBuffer -> SkeletalMesh), with its GPU skinning resources:
about 200 MB of VRAM per VRM character, which crashed the 8 GB GPU twice (memory: tread-editor-vram-batch).  Python
has no ResetTransaction, but loading a map runs it (EditorDestroyWorld -> Cleanse).  The map switch is its own call
(memory: tread-editor-python-map-switch); the batch tools save their packages, so nothing is dirty here.
"""
import sys

import unreal

ROOT = "/Game/Tread/Characters/VRM/"


def reload_map():
    dirty = (unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
             + unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    if dirty:
        raise RuntimeError("dirty packages, not reloading: %s" % [p.get_name() for p in dirty][:10])
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    path = world.get_path_name().split(".")[0]
    world = None
    if not unreal.EditorLoadingAndSavingUtils.load_map(path):
        raise RuntimeError("failed to reload " + path)
    print("EDITOR_RELEASE reload %s" % path)


def collect():
    # With the undo buffer reset only RF_Standalone keeps the loaded VRM assets alive; unload their packages so
    # their render resources go too.  Dirty packages are left alone (they would lose their changes).
    dirty = {p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}
    packages = {}
    for cls in (unreal.AnimSequence, unreal.IKRetargeter, unreal.IKRigDefinition, unreal.SkeletalMesh,
                unreal.PhysicsAsset, unreal.Skeleton):
        for obj in unreal.ObjectIterator(cls):
            package = obj.get_outermost()
            name = package.get_name()
            if name.startswith(ROOT) and name not in dirty:
                packages[name] = package
    if packages:
        unreal.EditorLoadingAndSavingUtils.unload_packages(list(packages.values()))
    packages = None
    # The thumbnail preview scenes outlive the assets; only replacing their renderers frees them.
    unreal.SystemLibrary.execute_console_command(None, "Tread.FlushThumbnailScenes")
    unreal.SystemLibrary.collect_garbage()
    meshes = [o.get_name() for o in unreal.ObjectIterator(unreal.SkeletalMesh) if o.get_name().startswith("SK_VRM")]
    print("EDITOR_RELEASE gc vrm_meshes_loaded=%d %s" % (len(meshes), sorted(meshes)[:8]))


{"reload": reload_map, "gc": collect}[sys.argv[1]]()
