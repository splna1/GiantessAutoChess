"""Unity Humanoid muscle space -> UE bone-local rotations for the 416 VRM skeleton (pure Python, no `unreal`).

The muscle decoding here is DEPRECATED (doc 125 section 2, doc 127): the fitted IK-goal solution had
hand-tuned residuals, so the clip set moved to ActorX .psa data (anim_psa.py, doc 127), and the
A_Clukay_* assets were deleted in A2. Still in use by anim_psa.py / anim_body.py for the skeleton side:
Skeleton (rest pose, human bone map, fk), the quaternion helpers (qmul, qrot, IQ) and ROOT / GLB / STAGE.

Why the muscle path exists: the animation library we own is 354 Unity *Humanoid* clips. They contain no bone tracks,
only normalised muscle DoFs plus the body (hips) transform and IK goal curves. There is no FBX/Mixamo
source anywhere on disk, so the only way to get real motion onto the UE skeleton is to decode muscle space.

Two properties of the imported skeleton make this tractable (verified by 10_animations.py --dump-skel):
  1. Every bone rest rotation is identity, in local *and* component space. So a rotation expressed in
     component axes IS the bone local rotation - no pre/post-rotation conjugation.
  2. Component axes: up = +Z, character right = +X, character forward = -Y. Unity (x right, y up, z fwd)
     therefore maps as (x, y, z) -> (x, -z, y); the map has determinant +1, so quaternions map the same way.

Each muscle becomes a rotation of `scale * value + center` degrees about one component axis. The axis per
muscle is anatomy (see MUSCLES); scale/center are fitted against the IK goal curves stored in the clips
themselves (--fit), which resolves the sign ambiguities and the fact that muscle 0 is not the rest pose
for the hinge ("Stretch") DoFs. Mirroring to the right side follows M R M with M = diag(-1,1,1):
rotations about X keep their sign, rotations about Y and Z flip.

CLI:
  python Tools/paris/anim_retarget.py --fit                 # refit scale/center, writes muscle_fit.json
  python Tools/paris/anim_retarget.py --check <clip.anim>   # report IK goal error for one clip
  python Tools/paris/anim_retarget.py --convert <clip.anim> <out.json> [--in-place] [--no-ground]
"""
import io
import json
import math
import os
import re
import struct
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STAGE = os.path.join(ROOT, "Saved", "Staging", "Anim")
SKEL_JSON = os.path.join(STAGE, "skeleton.json")
FIT_JSON = os.path.join(STAGE, "muscle_fit.json")
GLB = os.path.join(ROOT, "Saved", "Staging", "vrm", "416.glb")
CLIP_DIR = "F:/AI/workbuddy/GiantessAutoChess/sizebox/Sizebox/ExportedProject/Assets/AnimationClip"
FPS = 30.0
D2R = math.pi / 180.0

# ---------------------------------------------------------------- quaternions (x, y, z, w)

IQ = (0.0, 0.0, 0.0, 1.0)


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def qaxis(axis, rad):
    h = rad * 0.5
    q = [0.0, 0.0, 0.0, math.cos(h)]
    q[axis] = math.sin(h)
    return tuple(q)


def qrot(q, v):
    x, y, z, w = q
    vx, vy, vz = v
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (vx + w * tx + y * tz - z * ty,
            vy + w * ty + z * tx - x * tz,
            vz + w * tz + x * ty - y * tx)


def qnorm(q):
    n = math.sqrt(sum(c * c for c in q)) or 1.0
    return tuple(c / n for c in q)


def unity_q(x, y, z, w):
    """Unity quaternion -> UE component-space quaternion, axes (x, y, z) -> (x, -z, y)."""
    return qnorm((x, -z, y, w))


def unity_v(x, y, z):
    return (x, -z, y)


# ---------------------------------------------------------------- muscle table
# (curve suffix, human bone key, component axis, scale deg, center deg, fit: 1 = scale, 2 = center)
# Only the two hinge DoFs get a fitted centre: Unity muscle 0 is the rest pose for every DoF *except*
# the knee and elbow, whose zero sits mid-range. A mean-centred metric cannot see a constant offset, so
# fitting the other centres would only bake in a crooked default posture.
X, Y, Z = 0, 1, 2
MUSCLES = [
    ("Spine Front-Back",            "spine",    X,  -40.0,  0.0, 0),
    ("Spine Left-Right",            "spine",    Y,   40.0,  0.0, 0),
    ("Spine Twist Left-Right",      "spine",    Z,   40.0,  0.0, 0),
    ("Chest Front-Back",            "chest",    X,  -40.0,  0.0, 0),
    ("Chest Left-Right",            "chest",    Y,   40.0,  0.0, 0),
    ("Chest Twist Left-Right",      "chest",    Z,   40.0,  0.0, 0),
    ("UpperChest Front-Back",       "chest",    X,  -20.0,  0.0, 0),
    ("UpperChest Left-Right",       "chest",    Y,   20.0,  0.0, 0),
    ("UpperChest Twist Left-Right", "chest",    Z,   20.0,  0.0, 0),
    ("Neck Nod Down-Up",            "neck",     X,  -40.0,  0.0, 0),
    ("Neck Tilt Left-Right",        "neck",     Y,   40.0,  0.0, 0),
    ("Neck Turn Left-Right",        "neck",     Z,   40.0,  0.0, 0),
    ("Head Nod Down-Up",            "head",     X,  -40.0,  0.0, 0),
    ("Head Tilt Left-Right",        "head",     Y,   40.0,  0.0, 0),
    ("Head Turn Left-Right",        "head",     Z,   40.0,  0.0, 0),
    # legs (bone axis -Z), fitted against the foot IK goals
    ("Upper Leg Front-Back",        "UpperLeg", X,   70.0,  0.0, 1),
    ("Upper Leg In-Out",            "UpperLeg", Y,   60.0,  0.0, 1),
    ("Upper Leg Twist In-Out",      "UpperLeg", Z,  -60.0,  0.0, 1),
    ("Lower Leg Stretch",           "LowerLeg", X,  -83.0, 67.0, 3),
    ("Lower Leg Twist In-Out",      "LowerLeg", Z,  -90.0,  0.0, 1),
    ("Foot Up-Down",                "Foot",     X,   50.0,  0.0, 1),
    ("Foot Twist In-Out",           "Foot",     Z,  -30.0,  0.0, 1),
    ("Toes Up-Down",                "Toes",     X,   50.0,  0.0, 0),
    # arms (bone axis -X on the left side), fitted against the hand IK goals
    ("Shoulder Down-Up",            "Shoulder", Y,   22.0,  0.0, 1),
    ("Shoulder Front-Back",         "Shoulder", Z,  -15.0,  0.0, 1),
    ("Arm Down-Up",                 "UpperArm", Y,   80.0,  0.0, 1),
    ("Arm Front-Back",              "UpperArm", Z, -100.0,  0.0, 1),
    ("Arm Twist In-Out",            "UpperArm", X,   90.0,  0.0, 1),
    ("Forearm Stretch",             "LowerArm", Z,  -83.0, 51.0, 3),
    ("Forearm Twist In-Out",        "LowerArm", X,   90.0,  0.0, 1),
    ("Hand Down-Up",                "Hand",     Y,   80.0,  0.0, 1),
    ("Hand In-Out",                 "Hand",     Z,   40.0,  0.0, 1),
]
# fingers: "<Side>Hand.<Finger>.<n> Stretched" and ".Spread"
FINGERS = ("Thumb", "Index", "Middle", "Ring", "Little")
FINGER_SEG = (("1", "Proximal"), ("2", "Intermediate"), ("3", "Distal"))
FINGER_STRETCH = (45.0, -18.0)   # scale, center in degrees; relaxed hands are slightly curled
FINGER_SPREAD = (10.0, 0.0)
# goal attachment point in the foot/hand bone frame (left side, cm) and goal unit -> cm; both fitted
GOAL_OFFSET = {"Foot": [-0.5, -3.0, -8.0], "Hand": [-6.0, 0.0, 0.0]}
# Goal curves are normalised by the *source* avatar human scale (~1 m for a ~1.7 m human), while our
# character is a 1.52 m stylised figure, so one normalised unit is worth fewer centimetres on us. Both
# scales are therefore derived from our own rest pose instead of being fitted: leaving them free makes
# the fit degenerate (it shrinks the target instead of scaling the muscles).
STANDING_HIPS = 0.96    # hips height above the sole in a standing humanoid clip, normalised units
HUMAN_ARM = 0.52        # shoulder -> wrist of the source avatar, normalised units
GOAL_SCALE = {"Foot": 100.0, "Hand": 100.0}
BODY_SCALE = 100.0   # RootT is normalised by the source human scale; 1.0 -> 100 cm puts our hips at rest height

SIDES = (("Left ", "left", 1.0), ("Right ", "right", -1.0))


def mirror(axis, side):
    """M R M with M = diag(-1,1,1): X keeps its sign, Y and Z flip."""
    return 1.0 if (side > 0 or axis == X) else -1.0


# ---------------------------------------------------------------- skeleton + human bone map


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def read_glb_humanoid(path=GLB):
    """{vrm bone name: glTF node name} from the VRM extension of a .glb."""
    with io.open(path, "rb") as f:
        f.read(12)
        clen, _ = struct.unpack("<II", f.read(8))
        j = json.loads(f.read(clen).decode("utf-8"))
    nodes = j["nodes"]
    return dict((e["bone"], nodes[e["node"]].get("name", ""))
                for e in j["extensions"]["VRM"]["humanoid"]["humanBones"])


class Skeleton(object):
    def __init__(self, path=SKEL_JSON, glb=GLB):
        d = json.load(io.open(path, encoding="utf-8"))
        self.mesh = d["mesh"]
        self.skeleton = d["skeleton"]
        self.bones = d["bones"]
        self.index = dict((b["name"], b["i"]) for b in self.bones)
        self.parent = [self.index.get(b["parent"], -1) for b in self.bones]
        self.local_t = [tuple(b["t"]) for b in self.bones]
        by_norm = dict((_norm(b["name"]), b["name"]) for b in self.bones)
        self.human = {}
        for vrm, node in read_glb_humanoid(glb).items():
            n = by_norm.get(_norm(node))
            if n:
                self.human[vrm] = n
        self.ref = self.fk({})
        hips_z = self.ref[self.index[self.human["hips"]]][0][2]
        sh = self.ref[self.index[self.key("UpperArm", "left")]][0]
        wr = self.ref[self.index[self.key("Hand", "left")]][0]
        arm = math.sqrt(sum((sh[k] - wr[k]) ** 2 for k in range(3)))
        self.goal_scale = {"Foot": hips_z / STANDING_HIPS, "Hand": arm / HUMAN_ARM}

    def key(self, bone_key, side=None):
        """Resolve a MUSCLES bone key (plus side) to a UE bone name, or None."""
        vrm = bone_key if side is None else (side + bone_key[0].upper() + bone_key[1:])
        return self.human.get(vrm)

    def fk(self, local_q):
        """local rotations {bone name: quat} (plus optional "@hips_t") -> [(pos, quat)] per bone index."""
        out = [None] * len(self.bones)
        hips_t = local_q.get("@hips_t")
        hips = self.human.get("hips")
        for b in self.bones:
            i = b["i"]
            p = self.parent[i]
            t = self.local_t[i]
            if hips_t is not None and b["name"] == hips:
                t = hips_t
            q = local_q.get(b["name"], IQ)
            if p < 0:
                out[i] = (t, q)
            else:
                pp, pq = out[p]
                r = qrot(pq, t)
                out[i] = ((pp[0] + r[0], pp[1] + r[1], pp[2] + r[2]), qmul(pq, q))
        return out


# ---------------------------------------------------------------- muscle -> local rotations


class Retargeter(object):
    def __init__(self, skel, params=None):
        self.skel = skel
        self.params = {}
        for name, _bone, _axis, sc, ce, _fit in MUSCLES:
            self.params[name] = [sc, ce]
        self.params["@FingerStretch"] = list(FINGER_STRETCH)
        self.params["@FingerSpread"] = list(FINGER_SPREAD)
        for k in GOAL_OFFSET:
            self.params["@Offset" + k] = list(GOAL_OFFSET[k])
            self.params["@Scale" + k] = [skel.goal_scale[k]]
        for k, v in (params or {}).items():
            if k in self.params:
                self.params[k] = list(v)
        self._plan = self._build_plan()

    def _build_plan(self):
        """Pre-resolve (curve name, bone name, axis, param key, mirror sign) once."""
        plan = []
        for name, bone, axis, _sc, _ce, _fit in MUSCLES:
            if bone in ("spine", "chest", "neck", "head"):
                n = self.skel.key(bone)
                if n:
                    plan.append((name, n, axis, name, 1.0))
                continue
            for prefix, side_key, sign in SIDES:
                n = self.skel.key(bone, side_key)
                if n:
                    plan.append((prefix + name, n, axis, name, mirror(axis, sign)))
        for prefix, side_key, sign in SIDES:
            hand = prefix.strip() + "Hand"
            for f in FINGERS:
                for seg, seg_name in FINGER_SEG:
                    n = self.skel.key(f + seg_name, side_key)
                    if n:
                        plan.append(("%s.%s.%s Stretched" % (hand, f, seg), n, Y,
                                     "@FingerStretch", mirror(Y, sign)))
                n = self.skel.key(f + "Proximal", side_key)
                if n:
                    plan.append(("%s.%s.Spread" % (hand, f), n, Z, "@FingerSpread", mirror(Z, sign)))
        return plan

    def pose(self, values, i):
        """Local rotations for frame i; a bone with several DoFs gets the product of its rotations."""
        acc = {}
        P = self.params
        for curve, bone, axis, pkey, sign in self._plan:
            v = values.get(curve)
            if v is None:
                continue
            sc, ce = P[pkey]
            ang = (sc * v[i] + ce) * sign * D2R
            if abs(ang) < 1e-7:
                continue
            q = qaxis(axis, ang)
            acc[bone] = qmul(acc[bone], q) if bone in acc else q
        return acc

    def body(self, values, i):
        """Hips local rotation and translation (cm) for frame i."""
        s = BODY_SCALE
        q = unity_q(values["RootQ.x"][i], values["RootQ.y"][i], values["RootQ.z"][i], values["RootQ.w"][i])
        t = unity_v(values["RootT.x"][i] * s, values["RootT.y"][i] * s, values["RootT.z"][i] * s)
        return q, t

    def full_pose(self, values, i):
        """pose() with the body transform folded into the hips bone."""
        local = self.pose(values, i)
        hips = self.skel.human["hips"]
        hq, ht = self.body(values, i)
        local[hips] = qmul(hq, local.get(hips, IQ))
        local["@hips_t"] = ht
        return local


# ---------------------------------------------------------------- goal error (fitting objective)


def goal_error(rt, values, frames, detail=False):
    """Motion-shape error (cm) between FK-ed foot/hand points and the IK goal curves stored in the clip.

    The source avatar has different proportions from ours, so absolute positions can never match. Each
    goal track is therefore **mean-centred** over the sampled frames before comparing: what is scored is
    how the limb *moves*, not where it sits. That is exactly what decides the muscle axes, signs, scales
    and hinge centres, and it keeps the fit from distorting muscles to chase a constant offset.
    """
    skel = rt.skel
    P = rt.params
    hips_i = skel.index[skel.human["hips"]]
    pred = {}
    tgt = {}
    for i in frames:
        world = skel.fk(rt.full_pose(values, i))
        hp = world[hips_i][0]
        for kind in ("Foot", "Hand"):
            gs = P["@Scale" + kind][0]
            for prefix, side_key, _sign in SIDES:
                bone = skel.key(kind, side_key)
                gp = prefix.strip() + kind
                if bone is None or (gp + "T.x") not in values:
                    continue
                wp = world[skel.index[bone]][0]
                pred.setdefault(gp, []).append((wp[0] - hp[0], wp[1] - hp[1], wp[2] - hp[2]))
                tgt.setdefault(gp, []).append(unity_v(values[gp + "T.x"][i] * gs,
                                                      values[gp + "T.y"][i] * gs,
                                                      values[gp + "T.z"][i] * gs))
    tot = 0.0
    n = 0
    per = {}
    for gp, ps in pred.items():
        ts = tgt[gp]
        m = len(ps)
        pm = [sum(p[k] for p in ps) / m for k in range(3)]
        tm = [sum(t[k] for t in ts) / m for k in range(3)]
        s = 0.0
        for p, t in zip(ps, ts):
            s += math.sqrt(sum((p[k] - pm[k] - t[k] + tm[k]) ** 2 for k in range(3)))
        per[gp] = s / m
        tot += s
        n += m
    if detail:
        return tot / max(1, n), per
    return tot / max(1, n)


# ---------------------------------------------------------------- conversion


def load_fit():
    if os.path.exists(FIT_JSON):
        return json.load(io.open(FIT_JSON, encoding="utf-8"))
    return {}


def convert(clip_path, skel=None, rt=None, fps=FPS, in_place=False, ground=True):
    """Unity .anim -> {bone: {q, t}} of UE bone-local keys, plus clip meta."""
    import anim_unity
    skel = skel or Skeleton()
    rt = rt or Retargeter(skel, load_fit())
    raw = anim_unity.read_clip(clip_path)
    if raw["generic"]:
        raise ValueError("%s is a generic clip (hashed bone paths), cannot retarget" % raw["name"])
    if "RootT.y" not in raw["curves"]:
        raise ValueError("%s has no humanoid curves" % raw["name"])
    clip = anim_unity.resample(raw, fps)
    values = clip["values"]
    hips = skel.human["hips"]
    poses = [rt.full_pose(values, i) for i in range(clip["frames"])]
    if in_place:  # strip horizontal travel of the hips, keep the vertical bob
        rest = skel.local_t[skel.index[hips]]
        for p in poses:
            p["@hips_t"] = (rest[0], rest[1], p["@hips_t"][2])
    if ground:  # one constant Z shift so the lowest toe of the clip sits at its rest height
        toes = [skel.index[t] for t in (skel.key("Toes", s[1]) for s in SIDES) if t]
        if toes:
            ref = min(skel.ref[t][0][2] for t in toes)
            low = min(min(skel.fk(p)[t][0][2] for t in toes) for p in poses)
            dz = ref - low
            for p in poses:
                t = p["@hips_t"]
                p["@hips_t"] = (t[0], t[1], t[2] + dz)
    names = set()
    for p in poses:
        names.update(k for k in p if k != "@hips_t")
    names.add(hips)
    tracks = {}
    for b in sorted(names):
        tracks[b] = {"q": [[round(c, 6) for c in qnorm(p.get(b, IQ))] for p in poses], "t": None}
    tracks[hips]["t"] = [[round(c, 4) for c in p["@hips_t"]] for p in poses]
    return {"name": clip["name"], "source": os.path.basename(clip_path), "fps": fps,
            "frames": clip["frames"], "length": clip["length"], "loop": clip["loop"],
            "skeleton": skel.skeleton, "in_place": bool(in_place), "grounded": bool(ground),
            "tracks": tracks}


# ---------------------------------------------------------------- fitting

FIT_CLIPS = ("Breathing Idle", "Female Walk", "Running", "Stomping", "Kicking Out", "Combo Punch",
             "Neutral Idle", "Dismissing Gesture")


def fit(argv):
    import anim_unity
    skel = Skeleton()
    clips = []
    for n in FIT_CLIPS:
        p = os.path.join(CLIP_DIR, n + ".anim")
        if not os.path.exists(p):
            print("missing", p)
            continue
        c = anim_unity.resample(anim_unity.read_clip(p), FPS)
        step = max(1, c["frames"] // 12)
        clips.append((c["values"], list(range(0, c["frames"], step))))
    print("fitting on %d clips, %d sample frames" % (len(clips), sum(len(f) for _v, f in clips)))
    rt = Retargeter(skel)

    def err():
        return sum(goal_error(rt, v, f) for v, f in clips) / len(clips)

    knobs = []   # (param key, index, coarse grid multipliers or None, span)
    grid = [-1.9, -1.5, -1.2, -1.0, -0.85, -0.7, -0.5, 0.5, 0.7, 0.85, 1.0, 1.2, 1.5, 1.9]
    for name, _bone, _axis, sc, _ce, fitted in MUSCLES:
        if fitted & 1:
            knobs.append((name, 0, grid, abs(sc)))
        if fitted & 2:
            knobs.append((name, 1, None, 0.0))
    e = err()
    print("start error %.3f cm" % e)
    for it in range(4):
        for key, idx, g, span in knobs:
            cur = rt.params[key][idx]
            best, bv = e, cur
            if g:
                cand = [m * span for m in g] if it == 0 else \
                       [cur * m for m in (0.8, 0.9, 1.1, 1.25)] + [cur + d for d in (-8, 8)]
            else:
                w = max(6.0, abs(cur) * 0.5) * 3.0 / (it + 1)
                cand = [cur + w * s for s in (-1.0, -0.6, -0.3, 0.3, 0.6, 1.0)]
            for c in cand:
                rt.params[key][idx] = c
                v = err()
                if v < best - 1e-6:
                    best, bv = v, c
            rt.params[key][idx] = bv
            e = best
        print("pass %d error %.3f cm" % (it + 1, e))
    out = dict((k, [round(x, 4) for x in v]) for k, v in rt.params.items())
    if not os.path.isdir(STAGE):
        os.makedirs(STAGE)
    json.dump(out, io.open(FIT_JSON, "w", encoding="utf-8"), indent=1, sort_keys=True)
    print("wrote", FIT_JSON)
    for name, (v, f) in zip(FIT_CLIPS, clips):
        m, per = goal_error(rt, v, f, detail=True)
        print("  %-20s %5.2f cm  %s" % (name, m, " ".join("%s %.1f" % (k, x) for k, x in sorted(per.items()))))


def check(path):
    import anim_unity
    skel = Skeleton()
    rt = Retargeter(skel, load_fit())
    c = anim_unity.resample(anim_unity.read_clip(path), FPS)
    frames = list(range(0, c["frames"], max(1, c["frames"] // 20)))
    m, per = goal_error(rt, c["values"], frames, detail=True)
    print("%s: mean goal error %.2f cm  %s" % (c["name"], m,
          " ".join("%s %.1f" % (k, v) for k, v in sorted(per.items()))))


def main(argv):
    if not argv:
        print(__doc__)
    elif argv[0] == "--fit":
        fit(argv[1:])
    elif argv[0] == "--check":
        check(argv[1])
    elif argv[0] == "--convert":
        d = convert(argv[1], in_place="--in-place" in argv, ground="--no-ground" not in argv)
        json.dump(d, io.open(argv[2], "w", encoding="utf-8"))
        print("%s -> %s (%d frames, %d bones)" % (d["name"], argv[2], d["frames"], len(d["tracks"])))
    else:
        print(__doc__)


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main(sys.argv[1:])
