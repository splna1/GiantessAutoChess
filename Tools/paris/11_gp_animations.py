"""Step 11: GP action set (ActorX .psa, UE5 mannequin) -> A_GP_* AnimSequences on the 416 skeleton.

Doc 125 section 2: the Unity-derived A_Clukay_* clips of step 10 are superseded (hand-keyed errors) and were
deleted in A2 (10_animations.py --purge-unity); every key here comes from PSA data, nothing is keyed by hand.
A1 built the first ten clips of CLIPS, A2 (doc 127) completed the table to 33.

Pipeline: stage the categorized export into Saved/Staging/Anim/gp (the export folder stays read-only) ->
anim_psa.convert (PSA conventions, retarget, grounding, resampling: see anim_psa.py) -> the
AnimationDataController authoring of step 10 (make_sequence / write_sequence) -> checks -> report.

Frame rate rule (125 2.5): clips at <= 60 fps keep their rate, 90/120 fps clips are resampled to 60.

Sources in CLIPS: a staged .psa path; {"file", "trim": (t0, t1)} for one part of a longer take (defeat and
get-up are the two halves of laydown_Anim); IDLE's still + sway recipe. Grounding is anim_psa's "sole"
except for the FLOOR clips, which kneel, sit on or lie on the floor ("floor": the lowest body point per
frame, anim_body). In-place clips (locomotion) carry the per-frame root speed / distance curve in
root_motion.curve for gameplay; the others keep their own pelvis travel. CHAINS lists clips meant to play
one after the other; the report records how far each join is from seamless (for the M1 blend times).

Checks per clip (125 2.6); failures are listed under "errors" and the run raises after the report:
  mapped   every BONE_MAP bone exists in the source skeleton
  tpose    the upper arms leave their rest (T-pose) direction: mean angle >= TPOSE_MIN_DEG on both sides
  flip     largest frame-to-frame local rotation step <= the source's own largest step + FLIP_MARGIN_DEG
  feet     lowest heel / ball / toe tip >= FEET_MIN_CM (no ground penetration)
  body     lowest point of the body surface (anim_body: knees, buttocks, back, hands...) >= BODY_MIN_CM;
           looser than feet because the surface points are rigidly skinned (a few mm off near the joints)
  limbs    aimed bones (arms, legs, all fingers) follow the source bone direction within LIMB_MAX_DEG
  loop     clips played looped are seamless (first frame == last frame)
  ue       UE play length == converted length, every track written, compression target rate == clip rate

Usage (through Tools/ue_run.py):
    11_gp_animations.py                    rebuild every clip, then loop A_GP_Idle on the giant (map saved)
    11_gp_animations.py --only Idle,Kick   rebuild just these clips (exact suffixes)
    11_gp_animations.py --play Walk        loop another clip on the giant (map saved)
    11_gp_animations.py --pose Kick:5.1    freeze the giant at 5.1 s ("Kick:key" = the report's key frame);
                                           the map is not saved, --play restores the loop
    11_gp_animations.py --verify-reload    reload the map from disk, record what the giant plays in the report
"""
import importlib
import io
import json
import os
import shutil
import sys
import time

import unreal

import paris_common as pc

anim10 = importlib.import_module("10_animations")  # shared authoring: make_sequence / write_sequence / find_giant

STEP = "GPAnim"
GP_ANIM_DIR = anim10.ANIM_DIR + "/GP"
GP_SRC = pc.PROJECT_DIR + "/0614/gp_extract/action_animations_export_2026-09-28/categorized"  # read-only
STAGE_GP = anim10.STAGE + "/gp"
MANIFEST = "CATEGORIZED_ACTION_ANIMATION_MANIFEST.json"
REPORT = pc.REPORT_DIR + "/M0_GP_Animations.json"

TPOSE_MIN_DEG = 30.0
FLIP_MARGIN_DEG = 10.0
FEET_MIN_CM = -0.5
BODY_MIN_CM = -1.0
LIMB_MAX_DEG = 5.0

# 125 2.4: no GP clip is a plain standing idle. looking3 frame 0 is a natural symmetric stand; the
# torso / neck / head sway of `looking` (x0.25, faded out over the last second) keeps it alive and makes
# the loop seamless, while pelvis and legs stay on the base frame, so the feet never slide.
IDLE = {"base": "giantess_other/looking3.psa", "base_frame": 0, "sway": "giantess_other/looking.psa", "amp": 0.25}
# 125 2.4: the GP set has no hit / death clip. laydown_Anim goes down onto her back by 6.5 s (defeat) and
# gets up again after it (get-up); both halves meet at the same frame.
LAYDOWN = "giantess_other/laydown_Anim.psa"
LAY_SPLIT_S = 6.5

# (suffix, use, source (see the module doc), loop, in_place, note)
# in_place strips the horizontal travel (walk / run cycles and their starts / stops, the walking stomp:
# gameplay moves the actor, the report keeps the root speed curve); everything else keeps its own pelvis
# motion. loop = played looped (the loop check applies).
CLIPS = [
    ("Idle",       u"待机", IDLE, True, False, "looking3@0 + looking torso sway x0.25, see IDLE"),
    ("Walk",       u"走", "walk/MF_Unarmed_Walk_Fwd.psa", True, True, ""),
    ("WalkStart",  u"走·起步", "walk/MF_Unarmed_Walk_Fwd_Start.psa", False, True, "from the stand into Walk"),
    ("WalkStop",   u"走·停步", "walk/MF_Unarmed_Walk_Fwd_Stop.psa", False, True, "from Walk to the stand"),
    ("Run",        u"跑", "run/MF_Unarmed_Jog_Fwd.psa", True, True, "jog; flight phase lifts both feet up to 14.5 cm"),
    ("RunStart",   u"跑·起步", "run/MF_Unarmed_Jog_Fwd_Start.psa", False, True, "from the stand into Run"),
    ("RunStop",    u"跑·停步", "run/MF_Unarmed_Jog_Fwd_Stop.psa", False, True, "from Run to the stand"),
    ("Stomp",      u"踩", "stomp/rightStomp.psa", False, False, "right foot"),
    ("WalkStomp",  u"行进踩踏", "stomp/walkstomp_UNREAL.psa", False, True,
     "stomps while stepping forward; 111 cm of source travel over 8 s handed to gameplay (root_motion.curve)"),
    ("Grind",      u"碾", "stomp/rightGrind.psa", True, False, "right sole grinds on the spot, seamless loop"),
    ("Crush",      u"踩碎", "stomp/leftregularcrush.psa", False, False, "left foot"),
    ("Kick",       u"踢", "kick/kick003_animation_UNREAL.psa", False, False,
     "same keys as kickForward_segment1; steps 81 cm forward (source root motion, see root_motion)"),
    ("KickRight",  u"右踢", "kick/kick007_animation_UNREAL.psa", False, False, "same keys as kickRight_segment1"),
    ("Smash",      u"重击", "punch/handSmash009_animation_UNREAL.psa", False, False,
     "standing hammer blows: right hand up to 1.3 m and down in front (1.25 s), then the left (2.25 s); "
     "the hands stop at chest height, no ground contact"),
    ("SmashLow",   u"低位重击", "punch/handSmash003_animation_UNREAL.psa", False, False, "same keys as handLow_segment1"),
    ("Thigh",      u"大腿攻击", "stomp/thighattack010_animation_UNREAL.psa", False, False, "special-skill candidate"),
    ("Grab",       u"抓", "grab/grabBeforeIdle.psa", False, False, "crouch and pick up; same keys as grabTinies_segment1"),
    ("Hold",       u"持", "grab/holdidle.psa", True, False, "right hand holds the grabbed unit at chest height"),
    ("Throw",      u"扔", "grab/throw007_animation_UNREAL.psa", False, False, "120 fps source resampled to 60 fps"),
    ("Release",    u"放下", "grab/release.psa", False, False, "Hold -> set the unit down"),
    ("SitDown",    u"坐下", "giantess_other/sitdown.psa", False, False, "stand -> Sit"),
    ("Sit",        u"坐", "giantess_other/sitidle.psa", True, False,
     "chair-height seat (hips ~57 cm): needs a seat prop of that height (a 24 m building is too high)"),
    ("StandUp",    u"起身（坐）", "giantess_other/standUp.psa", False, False, "Sit -> stand"),
    ("SitCrush",   u"坐压", "stomp/sitcrush1.psa", False, False, "drops onto the ground seat first; floor grounding"),
    ("Kneel",      u"跪下", "giantess_other/knee.psa", False, False, "stand -> KneelIdle; floor grounding"),
    ("KneelIdle",  u"跪姿", "giantess_other/kneeidle.psa", True, False, "on both knees; floor grounding"),
    ("KneelSmash", u"跪压", "stomp/kneeDownCrush_UNREAL.psa", False, False,
     "deep crouch, both hands down; the source body has a longer torso, hence the larger hand error"),
    ("Growth",     u"成长", "giantess_other/growth.psa", False, False, "star-up / height growth (05_HEIGHT_SYSTEM)"),
    ("Jump",       u"跳", "giantess_other/jump_Anim.psa", False, False, "vertical jump, feet up to 18 cm"),
    # 125 2.4 had no victory clip: of the three candidates shot with gp_contact_sheet.py --strip
    # (rampage / jump_Anim / leftJumpRotate) this one is the celebration - a full turn in the air that
    # ends exactly where it began (loop 0.01 cm), so it loops on the spot inside the board cell.
    ("Victory",    u"胜利", "giantess_other/leftJumpRotate.psa", True, False,
     "leftJumpRotate: jump with a full turn in place, seamless; doubles as the turning jump"),
    ("Rampage",    u"暴走", "giantess_other/rampage.psa", False, True,
     "arm-swinging march; 103 cm of source travel handed to gameplay (root_motion.curve)"),
    ("Defeat",     u"战败", {"file": LAYDOWN, "trim": (0.0, LAY_SPLIT_S)}, False, False,
     "laydown_Anim 0-6.5 s: goes down onto her back; floor grounding"),
    ("GetUp",      u"起身", {"file": LAYDOWN, "trim": (LAY_SPLIT_S, None)}, False, False,
     "laydown_Anim 6.5 s-end: gets up from the back; floor grounding"),
]
DEFAULT_PLAY = "Idle"

# per-frame floor grounding (anim_psa "floor"): the support moves off the feet onto knees, buttocks or back
FLOOR = {"SitCrush", "Kneel", "KneelIdle", "KneelSmash", "Defeat", "GetUp"}

# clips played back to back (M1 state machine); the report measures each join
CHAINS = [("WalkStart", "Walk"), ("Walk", "WalkStop"), ("RunStart", "Run"), ("Run", "RunStop"),
          ("Grab", "Hold"), ("Hold", "Throw"), ("Hold", "Release"),
          ("SitDown", "Sit"), ("Sit", "StandUp"), ("Kneel", "KneelIdle"), ("Defeat", "GetUp")]

# verification still (report key_time, --pose <S>:key, contact sheet) where the automatic pick (the pose
# farthest from the first frame) is not the frame worth checking: the kick's wind-up bends the right leg
# more than the left front kick extends, so the extension is pinned; GetUp ends standing (farthest from the
# lying first frame, but a still that reads like Idle), so the half-risen pose is pinned instead.
KEY_TIME = {"Kick": 3.35, "GetUp": 4.05}


def asset_name(suffix):
    return "A_GP_" + suffix


def _loop_of(suffix):
    for c in CLIPS:
        if c[0] == suffix:
            return c[3]
    return True


# ---------------------------------------------------------------- staging


def stage_export():
    """Copy the categorized export into STAGE_GP (new or changed files only). Returns the number copied."""
    if not os.path.isdir(GP_SRC):
        raise RuntimeError("GP export missing: " + GP_SRC)
    n = 0
    for d, _dirs, files in os.walk(GP_SRC):
        out = os.path.normpath(os.path.join(STAGE_GP, os.path.relpath(d, GP_SRC)))
        for f in files:
            s, t = os.path.join(d, f), os.path.join(out, f)
            if not os.path.exists(t) or os.path.getsize(t) != os.path.getsize(s):
                anim10._mkdir(out)
                shutil.copy2(s, t)  # read-only source: copy out, never touch in place
                n += 1
    return n


def load_manifest():
    """{'cat/name.psa': original GP asset path} from the export manifest."""
    path = os.path.join(STAGE_GP, MANIFEST)
    if not os.path.exists(path):
        return {}
    with io.open(path, encoding="utf-8") as f:
        d = json.load(f)
    out = {}
    for c in d.get("clips", []):
        rel = c.get("copiedFile", "").replace("\\", "/").split("/categorized/", 1)[-1]
        out[rel] = c.get("sourceAsset")
    return out


# ---------------------------------------------------------------- checks


def check(r, info, loop):
    errs = []
    if r["missing"]:
        errs.append("mapped: source lacks %s" % ", ".join(r["missing"]))
    arm = min(r["left_arm_from_tpose_deg"][0], r["right_arm_from_tpose_deg"][0])
    if arm < TPOSE_MIN_DEG:
        errs.append("tpose: upper arms stay within %.1f deg of the rest pose" % arm)
    if r["max_step_deg"][0] > r["src_max_step_deg"][0] + FLIP_MARGIN_DEG:
        errs.append("flip: step %.1f deg at %s, source max %.1f deg" % (r["max_step_deg"][0], r["max_step_deg"][1],
                                                                        r["src_max_step_deg"][0]))
    if r["sole_min_cm"] < FEET_MIN_CM:
        errs.append("feet: sole %.2f cm below the ground" % -r["sole_min_cm"])
    if r["body_min_cm"][0] < BODY_MIN_CM:
        errs.append("body: %s %.2f cm below the ground" % (r["body_min_cm"][1], -r["body_min_cm"][0]))
    if r["limb_dir_max_deg"][0] > LIMB_MAX_DEG:
        errs.append("limbs: %.1f deg off at %s" % tuple(r["limb_dir_max_deg"]))
    if loop and not r["loop"]:
        errs.append("loop: not seamless (%.2f deg, %.2f cm)" % (r["loop_deg"], r["loop_cm"]))
    if abs(info["play_length"] - r["length"]) > 0.5 / r["fps"]:
        errs.append("ue: play length %.4f s, converted %.4f s" % (info["play_length"], r["length"]))
    if info["tracks_written"] != r["tracks"]:
        errs.append("ue: %d of %d tracks written" % (info["tracks_written"], r["tracks"]))
    if abs(info["target_fps"] - r["fps"]) > 1e-6:
        errs.append("ue: compression target %g fps, clip %g fps" % (info["target_fps"], r["fps"]))
    return errs


# ---------------------------------------------------------------- playback on the giant


def giant_info():
    a = anim10.find_giant()
    if a is None:
        return None
    t = a.get_editor_property("skeletal_mesh_component").get_world_transform()
    loc, rot = t.translation, t.rotation.rotator()
    return {"actor": anim10.ACTOR_LABEL, "location_m": [round(loc.x / pc.M, 3), round(loc.y / pc.M, 3), round(loc.z / pc.M, 3)],
            "rotation": [round(rot.pitch, 3), round(rot.yaw, 3), round(rot.roll, 3)],
            "scale": round(t.scale3d.x, 4)}


def play(suffix, at_time=None, save=True):
    """Loop (or freeze at `at_time`) a GP clip on the giant through the serialised AnimationData."""
    a = anim10.find_giant()
    if a is None:
        raise RuntimeError("giant actor %r not found - run 08_vrm.py first" % anim10.ACTOR_LABEL)
    path = GP_ANIM_DIR + "/" + asset_name(suffix)
    if not pc.EAL.does_asset_exist(path):
        raise RuntimeError("clip %s not built yet" % asset_name(suffix))
    seq = pc.load(path)
    loop = _loop_of(suffix) if at_time is None else True
    rate = 1.0 if at_time is None else anim10.FREEZE_RATE
    pos = 0.0 if at_time is None else float(at_time)
    comp = a.get_editor_property("skeletal_mesh_component")
    comp.set_update_animation_in_editor(True)
    comp.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
    comp.set_editor_property("animation_data", unreal.SingleAnimationPlayData(
        anim_to_play=seq, saved_looping=loop, saved_playing=True, saved_position=pos, saved_play_rate=rate))
    comp.set_animation(seq)
    comp.set_play_rate(rate)
    comp.play(loop)
    if at_time is not None:
        comp.set_position(pos, False)
    if save:
        pc.save_map()
    pc.log("giant plays %s%s" % (asset_name(suffix), "" if at_time is None else " frozen at %.3fs" % pos))
    return asset_name(suffix)


def playing_state():
    a = anim10.find_giant()
    comp = a.get_editor_property("skeletal_mesh_component")
    ad = comp.get_editor_property("animation_data")
    anim = ad.get_editor_property("anim_to_play")
    return {"anim_to_play": anim.get_path_name() if anim else None,
            "saved_looping": ad.get_editor_property("saved_looping"),
            "saved_playing": ad.get_editor_property("saved_playing"),
            "saved_play_rate": ad.get_editor_property("saved_play_rate"),
            "animation_mode": str(comp.get_animation_mode())}


def verify_reload():
    """Drop the loaded map, load it again from disk and record what the giant plays."""
    unreal.EditorLoadingAndSavingUtils.new_blank_map(False)
    pc.ensure_map_loaded()
    state = playing_state()
    state["expected"] = pc.load(GP_ANIM_DIR + "/" + asset_name(DEFAULT_PLAY)).get_path_name()
    state["ok"] = state["anim_to_play"] == state["expected"] and state["saved_playing"] and state["saved_play_rate"] == 1.0
    state["checked_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    report = _read_report() or {}
    report["reload_check"] = state
    pc.write_json(REPORT, report)
    pc.log("reload check: %s" % json.dumps(state, ensure_ascii=False))
    if not state["ok"]:
        raise RuntimeError("after reload the giant does not loop %s" % asset_name(DEFAULT_PLAY))


def _read_report():
    if not os.path.exists(REPORT):
        return None
    with io.open(REPORT, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- build


def convert_clip(ap, src, in_place, skel, key_time=None, ground="sole"):
    """One CLIPS source entry -> (converted data, the staged files it came from)."""
    if isinstance(src, dict) and "base" in src:  # still + sway recipe (IDLE)
        s = ap.still_sway(STAGE_GP + "/" + src["base"], STAGE_GP + "/" + src["sway"], src.get("base_frame", 0),
                          src.get("amp", 0.25))
        files = [src["base"], src["sway"]]
    else:
        f = src["file"] if isinstance(src, dict) else src
        s = ap.Source(STAGE_GP + "/" + f)
        if isinstance(src, dict) and "trim" in src:
            s.trim(*src["trim"])  # one part of a longer take (defeat / get-up)
        files = [f]
    return ap.convert(s, skel, in_place=in_place, ground=ground, key_time=key_time), files


def edge_of(data):
    """First / last frame of a converted clip, for the CHAINS join measurement."""
    q = dict((b, (tuple(tr["q"][0]), tuple(tr["q"][-1]))) for b, tr in data["tracks"].items())
    t = [tr["t"] for tr in data["tracks"].values() if tr["t"]][0]
    return {"q": q, "t": (tuple(t[0]), tuple(t[-1]))}


def chain_joins(ap, edges):
    """How far each CHAINS hand-over is from seamless: hips gap (cm) and worst bone rotation gap (deg).
    Not a check (a blend covers it); it sizes the M1 blend times."""
    out = []
    for a, b in CHAINS:
        ea, eb = edges.get(a), edges.get(b)
        if not ea or not eb:
            continue
        worst = (0.0, "")
        for bone, (_f, last) in ea["q"].items():
            if bone not in eb["q"]:
                continue
            d = ap.qangle(last, eb["q"][bone][0])
            if d > worst[0]:
                worst = (d, bone)
        out.append({"from": a, "to": b, "hips_cm": round(ap.vlen(ap.vsub(ea["t"][1], eb["t"][0])), 2),
                    "rot_deg": round(worst[0], 2), "rot_bone": worst[1]})
    return out


def build(only):
    import anim_psa as ap
    import psa_io
    from anim_retarget import Skeleton

    t0 = time.time()
    copied = stage_export()
    index = psa_io.hash_index(STAGE_GP)
    by_path = dict((p, h) for h, ps in index.items() for p in ps)
    manifest = load_manifest()
    if not os.path.exists(anim10.STAGE + "/skeleton.json"):
        anim10.dump_skeleton()
    skel = Skeleton(anim10.STAGE + "/skeleton.json")
    rest = dict((b["name"], tuple(b["t"])) for b in skel.bones)
    skeleton = pc.load(anim10.SKEL_PATH)
    pc.ensure_dir(GP_ANIM_DIR)

    old = (_read_report() or {}) if only else {}
    old_clips = dict((c["asset"], c) for c in old.get("clips", []))
    report = {"step": STEP, "doc": "125 section 2 / A2 (127)", "skeleton": skeleton.get_path_name(),
              "folder": GP_ANIM_DIR, "export": GP_SRC, "staged": STAGE_GP, "staged_copied": copied,
              "psa_files": sum(len(v) for v in index.values()), "psa_unique": len(index),
              "fps_rule": "<= 60 fps kept, faster sources resampled to 60 fps",
              "checks": {"tpose_min_deg": TPOSE_MIN_DEG, "flip_margin_deg": FLIP_MARGIN_DEG,
                         "feet_min_cm": FEET_MIN_CM, "body_min_cm": BODY_MIN_CM, "limb_max_deg": LIMB_MAX_DEG},
              "clips": [], "errors": []}
    edges = {}
    for suffix, use, src, loop, in_place, note in CLIPS:
        name = asset_name(suffix)
        if only and suffix.lower() not in only:
            if name in old_clips:
                report["clips"].append(old_clips[name])
            continue
        t = time.time()
        try:
            data, files = convert_clip(ap, src, in_place, skel, KEY_TIME.get(suffix),
                                       "floor" if suffix in FLOOR else "sole")
        except (ValueError, KeyError, IOError) as e:
            report["errors"].append({"clip": name, "error": "convert: %s" % e})
            pc.log("%s: convert failed: %s" % (name, e))
            continue
        edges[suffix] = edge_of(data)
        path = GP_ANIM_DIR + "/" + name
        seq = anim10.make_sequence(path, skeleton, data["fps"])  # target rate = clip rate (see make_sequence)
        info = anim10.write_sequence(seq, data, rest)
        r = data["report"]
        errs = check(r, info, loop)
        entry = {"asset": name, "path": path, "use": use, "files": files,
                 "source_asset": [manifest.get(f) for f in files],
                 "aliases": dict((f, [p for p in index.get(by_path.get(f), []) if p != f]) for f in files),
                 "note": note}
        entry.update(r)
        entry["loop_detected"] = r["loop"]
        entry["loop"] = loop
        entry.update(info)
        entry["errors"] = errs
        entry["seconds"] = round(time.time() - t, 2)
        report["clips"].append(entry)
        for e in errs:
            report["errors"].append({"clip": name, "error": e})
        pc.log("%-12s <- %-38s %2d fps %4d fr %6.3fs %2d tracks  err %.2f cm  step %.1f/%.1f  %s" % (
            name, r["source"], r["fps"], r["frames"], r["length"], info["tracks_written"], r["effector_err_mean_cm"],
            r["max_step_deg"][0], r["src_max_step_deg"][0], "OK" if not errs else "; ".join(errs)))
    joins = chain_joins(ap, edges)  # only the pairs whose both clips were rebuilt in this run
    done = set((j["from"], j["to"]) for j in joins)
    joins += [j for j in old.get("chains", []) if (j["from"], j["to"]) not in done]
    report["chains"] = [j for p in CHAINS for j in joins if (j["from"], j["to"]) == p]
    for j in report["chains"]:
        pc.log("join %-10s -> %-10s  hips %5.2f cm  rot %5.2f deg (%s)" % (
            j["from"], j["to"], j["hips_cm"], j["rot_deg"], j["rot_bone"]))
    if only is None:  # full rebuild: drop clips renamed or removed from the table
        keep = set(asset_name(c[0]) for c in CLIPS)
        for p in pc.EAL.list_assets(GP_ANIM_DIR, recursive=False):
            n = p.rsplit("/", 1)[-1].split(".")[0]
            if n.startswith("A_GP_") and n not in keep:
                pc.EAL.delete_asset(p.split(".")[0])
                report.setdefault("deleted", []).append(n)
                pc.log("deleted stale %s" % n)
    report["giant"] = giant_info()
    report["playing"] = play(DEFAULT_PLAY) if (only is None or DEFAULT_PLAY.lower() in only) else old.get("playing")
    if old.get("reload_check"):
        report["reload_check_previous"] = old["reload_check"]
    report["seconds"] = round(time.time() - t0, 1)
    pc.write_json(REPORT, report)
    pc.log("GP animations: %d clips, %d errors, %d files staged, %.1fs -> %s" % (
        len(report["clips"]), len(report["errors"]), copied, report["seconds"], REPORT))
    if report["errors"]:
        raise RuntimeError("%d clip check(s) failed, see %s" % (len(report["errors"]), REPORT))


# ---------------------------------------------------------------- main


def main(argv):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    pc.ensure_map_loaded()
    if "--verify-reload" in argv:
        verify_reload()
        return
    if "--play" in argv:
        play(argv[argv.index("--play") + 1])
        return
    if "--pose" in argv:
        s, _, t = argv[argv.index("--pose") + 1].partition(":")
        if t == "key":
            clip = [c for c in (_read_report() or {}).get("clips", []) if c["asset"] == asset_name(s)]
            if not clip:
                raise RuntimeError("no report entry for %s" % asset_name(s))
            t = clip[0]["key_time"]
        play(s, float(t or 0.0), save=False)
        return
    only = None
    if "--only" in argv:
        only = set(s.strip().lower() for s in argv[argv.index("--only") + 1].split(","))
    build(only)


if __name__ == "__main__":
    main(sys.argv[1:])
