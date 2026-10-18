"""Step 10: the skeleton dump and the AnimSequence authoring shared by the animation steps.

DEPRECATED as a clip builder (doc 125 section 2, doc 127). It used to retarget the Unity project's 354
AssetRipper humanoid clips (muscle space, hand-fitted IK goals) into A_Clukay_* sequences; those clips
carried hand-keyed fit errors and are superseded by the ActorX .psa set of 11_gp_animations.py, where
every key comes from source PSA data. A2 deleted the A_Clukay_* assets (--purge-unity, run by default).

What stays here, used by 11_gp_animations.py: dump_skeleton (the rest pose anim_retarget / anim_psa read),
make_sequence / write_sequence (the AnimationDataController authoring and its frame-rate rules) and
find_giant. The Unity reader itself is still in anim_unity.py / anim_retarget.py for reference.

Usage (through Tools/ue_run.py):
    10_animations.py                 delete the leftover A_Clukay_* clips (idempotent) and write the report
    10_animations.py --purge-unity   the same, explicitly
    10_animations.py --dump-skel     only rewrite Saved/Staging/Anim/skeleton.json
"""
import io
import json
import os
import sys
import time

import unreal

import paris_common as pc

STEP = "Anim"
ANIM_DIR = pc.CHAR + "/Clukay416/Anim"
SKEL_PATH = pc.CHAR + "/Clukay416/416/SkeletalMeshes/U_Char_0_Skeleton"
BODY_MESH = pc.CHAR + "/Clukay416/SK_Clukay416"
STAGE = pc.STAGING_DIR + "/Anim"
ACTOR_LABEL = "Char_Clukay416"
FPS = 30.0
FREEZE_RATE = 0.001  # --pose holds a frame; a true 0 rate leaves the pose unevaluated (reference pose)
UNITY_PREFIX = "A_Clukay_"  # the superseded Unity-derived clips (GP clips live in ANIM_DIR + "/GP")
REPORT = pc.REPORT_DIR + "/M0_Animations.json"


def _mkdir(path):
    """On-disk staging folder (pc.ensure_dir is for /Game content paths)."""
    if not os.path.isdir(path):
        os.makedirs(path)


# ---------------------------------------------------------------- skeleton dump


def dump_skeleton():
    """Write the rest pose (local transforms + hierarchy) that anim_retarget.py needs."""
    mesh = pc.load(BODY_MESH)
    tmp = pc.world().spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    try:
        comp = tmp.get_editor_property("skeletal_mesh_component")
        comp.set_skeletal_mesh(mesh)
        n = comp.get_num_bones()
        bones = []
        for i in range(n):
            name = str(comp.get_bone_name(i))
            t = comp.get_ref_pose_transform(i)
            loc = t.translation
            q = t.rotation
            s = t.scale3d
            parent = str(mesh.get_bone_parent(unreal.Name(name)))
            bones.append({"i": i, "name": name, "parent": parent,
                          "t": [loc.x, loc.y, loc.z], "q": [q.x, q.y, q.z, q.w], "s": [s.x, s.y, s.z]})
    finally:
        pc.actor_sub().destroy_actor(tmp)
    _mkdir(STAGE)
    out = {"mesh": pc.load(BODY_MESH).get_path_name(), "skeleton": pc.load(SKEL_PATH).get_path_name(), "bones": bones}
    with io.open(STAGE + "/skeleton.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(out, indent=1))
    pc.log("skeleton dumped: %d bones -> %s/skeleton.json" % (len(bones), STAGE))
    return out


# ---------------------------------------------------------------- authoring


def target_fps(seq):
    """The compression target rate (PlatformTargetFrameRate default) of an AnimSequence."""
    r = seq.get_editor_property("platform_target_frame_rate").get_editor_property("default")
    return r.numerator / float(r.denominator)


def make_sequence(path, skeleton, fps=FPS):
    """Load or create an AnimSequence at `path` whose compression target rate is `fps`.

    Compression resamples the keys to PlatformTargetFrameRate. Scripts cannot set it (VisibleAnywhere);
    the factory takes it from the project default (UAnimationSettings.DefaultFrameRate, 30 fps) when it
    populates the model. A 60 fps clip with an odd interval count leaves half a frame at 30 fps and
    asserts in AnimCompressionTypes on save (editor crash), so the default is switched to `fps` for the
    creation only. A matching asset is rebuilt in place (level / actor references survive), a
    mismatching one is recreated.
    """
    if pc.EAL.does_asset_exist(path):
        seq = pc.load(path)
        if seq and abs(target_fps(seq) - fps) < 1e-6:
            return seq
        seq = None
        if not pc.EAL.delete_asset(path) or pc.EAL.does_asset_exist(path):
            raise RuntimeError("%s: target rate differs from %g fps and the asset could not be deleted" % (path, fps))
        pc.log("%s: target rate differs from %g fps, recreated" % (path, fps))
    settings = unreal.get_default_object(unreal.AnimationSettings)
    r = settings.get_editor_property("default_frame_rate")  # a view into the CDO, not a copy
    old = (r.numerator, r.denominator)
    never = unreal.PropertyAccessChangeNotifyMode.NEVER  # no PostEditChange: nothing is written to the ini
    settings.set_editor_property("default_frame_rate", unreal.FrameRate(int(fps), 1), never)
    try:
        factory = unreal.AnimSequenceFactory()
        factory.set_editor_property("target_skeleton", skeleton)
        folder, name = path.rsplit("/", 1)
        seq = pc.ASSET_TOOLS.create_asset(name, folder, unreal.AnimSequence, factory)
    finally:
        settings.set_editor_property("default_frame_rate", unreal.FrameRate(*old), never)
    return seq


def write_sequence(seq, data, rest_t):
    """Push converted bone tracks into an AnimSequence through the animation data controller."""
    frames = data["frames"]
    fps = int(data.get("fps", FPS))  # 11_gp_animations writes 30 and 60 fps clips
    tfps = target_fps(seq)
    resampled = (frames - 1) * tfps / fps
    if abs(resampled - round(resampled)) > 1e-6:  # see make_sequence: saving this would crash the editor
        raise RuntimeError("%s: %d fps x %d frames cannot be resampled to the %g fps target (%.2f frames); "
                           "create it with make_sequence(path, skeleton, %d)" % (seq.get_name(), fps, frames,
                                                                                  tfps, resampled, fps))
    ctrl = seq.get_editor_property("controller")
    ctrl.open_bracket("Tread anim import", False)
    try:
        ctrl.remove_all_bone_tracks(False)
        ctrl.set_frame_rate(unreal.FrameRate(fps, 1), False)
        ctrl.set_number_of_frames(unreal.FrameNumber(max(1, frames - 1)), False)  # frames = intervals + 1
        scale = [unreal.Vector(1.0, 1.0, 1.0)] * frames
        written = 0
        for bone, track in sorted(data["tracks"].items()):
            if bone not in rest_t:
                continue
            name = unreal.Name(bone)
            ctrl.add_bone_track(name, False)
            ts = track.get("t") or [rest_t[bone]] * frames  # only the hips animate translation
            pos = [unreal.Vector(t[0], t[1], t[2]) for t in ts]
            rot = [unreal.Quat(q[0], q[1], q[2], q[3]) for q in track["q"]]
            ctrl.set_bone_track_keys(name, pos, rot, scale, False)
            written += 1
    finally:
        ctrl.close_bracket(False)
    seq.set_editor_property("enable_root_motion", False)
    pc.EAL.save_loaded_asset(seq, False)
    return {"tracks_written": written, "play_length": round(seq.get_play_length(), 4), "target_fps": target_fps(seq)}


# ---------------------------------------------------------------- playback on the giant


def find_giant():
    for a in pc.actor_sub().get_all_level_actors():
        if a.get_actor_label() == ACTOR_LABEL:
            return a
    return None


# ---------------------------------------------------------------- purge (A2)


def purge_unity():
    """Delete the superseded A_Clukay_* clips from ANIM_DIR. Idempotent, and never touches ANIM_DIR/GP
    (list_assets is non-recursive). An asset still referenced from outside the set (a level, a montage,
    an anim blueprint) aborts the purge instead of leaving a null reference behind."""
    found = []
    for path in pc.EAL.list_assets(ANIM_DIR, recursive=False):
        name = path.rsplit("/", 1)[-1].split(".")[0]
        if name.startswith(UNITY_PREFIX):
            found.append((name, path.split(".")[0]))
    inside = set(p for _n, p in found)
    blocked, deleted = [], []
    for name, path in found:
        refs = [str(r) for r in unreal.EditorAssetLibrary.find_package_referencers_for_asset(path, False)
                if str(r) not in inside]
        if refs:
            blocked.append({"asset": name, "referencers": refs})
    if blocked:
        raise RuntimeError("purge aborted: %s" % json.dumps(blocked))
    for name, path in found:
        if pc.EAL.delete_asset(path):
            deleted.append(name)
            pc.log("deleted %s" % name)
        else:
            blocked.append({"asset": name, "referencers": ["delete_asset returned False"]})
    remaining = sorted(p.rsplit("/", 1)[-1].split(".")[0] for p in pc.EAL.list_assets(ANIM_DIR, recursive=False))
    return {"deleted": deleted, "blocked": blocked, "remaining": remaining}


# ---------------------------------------------------------------- main


def main(argv):
    t0 = time.time()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    pc.ensure_map_loaded()
    if "--dump-skel" in argv:
        dump_skeleton()
        return
    res = purge_unity()
    report = {"step": STEP, "doc": "125 section 2 / A2 (127)", "folder": ANIM_DIR,
              "deprecated": "Unity clip builder removed; GP clips are built by 11_gp_animations.py",
              "gp_folder": ANIM_DIR + "/GP", "purged_prefix": UNITY_PREFIX,
              "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"), "seconds": round(time.time() - t0, 1)}
    report.update(res)
    pc.write_json(REPORT, report)
    pc.log("unity clips purged: %d deleted, %d left in %s -> %s" % (len(res["deleted"]), len(res["remaining"]),
                                                                    ANIM_DIR, REPORT))
    if res["blocked"]:
        raise RuntimeError("%d asset(s) could not be deleted, see %s" % (len(res["blocked"]), REPORT))


if __name__ == "__main__":
    main(sys.argv[1:])
