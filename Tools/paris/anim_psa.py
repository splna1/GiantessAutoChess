"""GP ActorX .psa (UE5 Manny/Quinn skeleton) -> bone-local keys for the 416 VRM skeleton (pure Python).

The GP action set was ripped by CUE4Parse from a UE5 project whose characters use the Epic mannequin
skeleton (294 bones: root, pelvis, spine_01..05, neck_01/02, head, clavicle/upperarm/lowerarm/hand, thigh/
calf/foot/ball, 15 finger bones per hand plus twist/corrective/IK helpers). psa_io.py reads the file
unchanged; everything about handedness is decided here and was verified on the data, not assumed:

  BONENAMES reference pose   raw values are UE-native local transforms. FK gives head z 163, feet z 8,
                             A-pose hands at (+-48, 16, 104); character left = +X, forward = +Y.
  ANIMKEYS, non-root bones   PSA stores the Y mirror of the UE value, conjugated (ActorX convention):
                             q_ue = (x, -y, z, w), t_ue = (x, -y, z). spine_01 / calf_l keys then agree in
                             sign with the reference, the pelvis key (0, 2.47, 95.72) with the reference
                             (0, 2.28, 95.9).
  ANIMKEYS, root bone        mirror only, no conjugation: q_ue = (-x, y, -z, w), t_ue = (x, -y, z).
                             Checked on FP_WalkStart_F_90L/90R: the root travels the way the body faces
                             only with this rule.
  AnimRate                   NumKeys / length (see psa_io.Sequence.length); real fps = (keys - 1) / length.

Target: U_Char_0_Skeleton, all 252 rest rotations identity, character left = -X, forward = -Y. The source
therefore maps into target space with C = 180 deg about Z: v -> (-x, -y, z), q -> (-x, -y, z, w).

Retarget, per mapped bone j (BONE_MAP):
  D_j(t) = C Rs_j(t) Rs_j(ref)^-1 C^-1          world-space delta of the source bone from its ref pose
  R_j(t) = D_j(t) W_j                           target world rotation
  local  = R_parent^-1 R_j                      unmapped target bones keep local identity
W_j aligns the target rest pose with the source reference pose (the source ref is an A-pose, ours a T-pose):
  rest     W = identity. Torso, neck, head, clavicles: keeps our own posture instead of baking in the
           source's, and the face does not tilt down.
  aim      W maps the target bone direction (bone -> child) onto the source one; with the hand lateral
           axis (index_01 -> pinky_01) as secondary it also fixes the roll (arms, hands, fingers). Without a
           secondary it is the minimal swing (legs, thumbs). Source directions use the reference rotations
           with the clip's own key offsets (Source.kref), not the file's reference offsets.
  flat     yaw only (foot): our ankle sits higher above the toes than the source's, a full aim would
           pitch the toe up and push the heel through the ground.
  inherit  reuse another bone's W (ball -> Foot, finger distals -> intermediate).

Hips translation = rest + k_leg * C (pelvis(t) - pelvis(ref)) + dz, k_leg = our leg / the clip's leg
(from the clip's own key translations: Quinn clips carry Quinn bone lengths). In-place clips zero the root
XY and yaw before FK, remove the linear pelvis drift and report the root motion instead. Grounding:
  sole    (default) one constant for the whole clip, so its lowest heel / ball / toe tip touches z = 0.
          Right while the feet carry her: the constant absorbs our taller ankle (rest hips 94.4 cm against
          0.87 x 95.9 for the source).
  floor   per frame, so the lowest point of the body surface (anim_body: knees, buttocks, back, hands, and
          the sole contacts) touches z = 0. For clips that kneel, sit on or lie on the floor: there the
          support moves off the feet, the sole constant no longer holds and the body floats 5-14 cm or
          sinks through (knee.psa / laydown_Anim). Only for clips without airborne moments, which it would
          flatten. The shift depends on the pose only, so clips cut from one take (Source.trim) and a hold
          that continues another clip (knee -> kneeidle) meet at the same height.
  source  keep the source height (hips follow the pelvis offset only).

CLI:
  python Tools/paris/anim_psa.py <file.psa> [--in-place] [--ground sole|floor|source] [--seq N] [--out f.json]
  python Tools/paris/anim_psa.py --analyze <file.psa> [...]      source-only motion summary
"""
import io
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import psa_io  # noqa: E402
from anim_retarget import IQ, ROOT, Skeleton, qmul, qnorm, qrot  # noqa: E402

GP_DIR = os.path.join(ROOT, "0614", "gp_extract", "action_animations_export_2026-09-28", "categorized")
MAX_FPS = 60.0
LOOP_DEG = 2.0
FLOOR_SMOOTH_S = 0.1

# contact points (cm) in the target Foot / Toes bone frames; all at z = 0 in the rest pose
HEEL = (0.0, 3.5, -11.3)
BALL = (0.0, 0.0, -3.8)
TOE_TIP = (0.0, -3.0, -3.8)

REST, AIM, FLAT, INHERIT = "rest", "aim", "flat", "inherit"


# ---------------------------------------------------------------- math (quats x, y, z, w)

def qconj(q):
    return (-q[0], -q[1], -q[2], q[3])


def qdot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]


def qangle(a, b):
    """Angle between two rotations in degrees (atan2 form: exact near 0, unlike acos of the dot)."""
    d = qmul(qconj(a), b)
    return math.degrees(2.0 * math.atan2(math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]), abs(d[3])))


def qslerp(a, b, u):
    d = qdot(a, b)
    if d < 0.0:
        b = (-b[0], -b[1], -b[2], -b[3])
        d = -d
    if d > 0.9995:
        return qnorm(tuple(a[k] + (b[k] - a[k]) * u for k in range(4)))
    th = math.acos(d)
    s = math.sin(th)
    wa, wb = math.sin((1.0 - u) * th) / s, math.sin(u * th) / s
    return tuple(wa * a[k] + wb * b[k] for k in range(4))


def vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vscale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def vdot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vcross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def vlen(a):
    return math.sqrt(vdot(a, a))


def vunit(a):
    n = vlen(a) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


def vangle(a, b):
    return math.degrees(math.acos(max(-1.0, min(1.0, vdot(vunit(a), vunit(b))))))


def qfrom_m(m):
    """Rotation matrix (rows) -> quat, for qrot(q, v) == m v."""
    tr = m[0][0] + m[1][1] + m[2][2]
    if tr > 0.0:
        s = math.sqrt(tr + 1.0) * 2.0
        q = ((m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s, 0.25 * s)
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2.0
        q = (0.25 * s, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s, (m[2][1] - m[1][2]) / s)
    elif m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2.0
        q = ((m[0][1] + m[1][0]) / s, 0.25 * s, (m[1][2] + m[2][1]) / s, (m[0][2] - m[2][0]) / s)
    else:
        s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2.0
        q = ((m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, 0.25 * s, (m[1][0] - m[0][1]) / s)
    return qnorm(q)


def qbetween(u, v):
    """Minimal rotation taking direction u onto direction v."""
    u, v = vunit(u), vunit(v)
    d = vdot(u, v)
    if d < -0.999999:
        axis = vcross((1.0, 0.0, 0.0), u)
        if vlen(axis) < 1e-6:
            axis = vcross((0.0, 1.0, 0.0), u)
        a = vunit(axis)
        return (a[0], a[1], a[2], 0.0)
    c = vcross(u, v)
    return qnorm((c[0], c[1], c[2], 1.0 + d))


def frame(aim, sec):
    """Orthonormal basis (aim, sec', aim x sec') as three column vectors."""
    a = vunit(aim)
    b = vunit(vsub(sec, vscale(a, vdot(sec, a))))
    return a, b, vcross(a, b)


def qalign(src_cols, dst_cols):
    """Rotation taking basis src (columns) onto basis dst: M = dst src^T."""
    m = [[sum(dst_cols[k][r] * src_cols[k][c] for k in range(3)) for c in range(3)] for r in range(3)]
    return qfrom_m(m)


def qyaw(u, v):
    """Rotation about Z taking the horizontal projection of u onto that of v."""
    h = math.atan2(v[1], v[0]) - math.atan2(u[1], u[0])
    return (0.0, 0.0, math.sin(h * 0.5), math.cos(h * 0.5))


# ---------------------------------------------------------------- conventions

def key_q(q, root):
    x, y, z, w = q
    return qnorm((-x, y, -z, w)) if root else qnorm((x, -y, z, w))


def key_t(t):
    return (t[0], -t[1], t[2])


def cq(q):
    """C q C^-1, C = 180 deg about Z (source facing +Y -> target facing -Y)."""
    return (-q[0], -q[1], q[2], q[3])


def cv(v):
    return (-v[0], -v[1], v[2])


def fk(parent, local):
    out = [None] * len(local)
    for i, (t, q) in enumerate(local):
        p = parent[i]
        if p < 0:
            out[i] = (t, q)
        else:
            pp, pq = out[p]
            r = qrot(pq, t)
            out[i] = ((pp[0] + r[0], pp[1] + r[1], pp[2] + r[2]), qmul(pq, q))
    return out


# ---------------------------------------------------------------- bone map (vrm humanoid <- mannequin)

FINGERS = (("Thumb", "thumb"), ("Index", "index"), ("Middle", "middle"), ("Ring", "ring"), ("Little", "pinky"))


def bone_map():
    """[(vrm bone, source bone, mode, aim (vrm child, source child) | inherit vrm, use lateral secondary)]"""
    m = [("hips", "pelvis", REST, None, False),
         ("spine", "spine_02", REST, None, False),
         ("chest", "spine_05", REST, None, False),
         ("neck", "neck_01", REST, None, False),
         ("head", "head", REST, None, False)]
    for side, s in (("left", "_l"), ("right", "_r")):
        m += [(side + "Shoulder", "clavicle" + s, REST, None, False),
              (side + "UpperArm", "upperarm" + s, AIM, (side + "LowerArm", "lowerarm" + s), True),
              (side + "LowerArm", "lowerarm" + s, AIM, (side + "Hand", "hand" + s), True),
              (side + "Hand", "hand" + s, AIM, (side + "MiddleProximal", "middle_01" + s), True),
              (side + "UpperLeg", "thigh" + s, AIM, (side + "LowerLeg", "calf" + s), False),
              (side + "LowerLeg", "calf" + s, AIM, (side + "Foot", "foot" + s), False),
              (side + "Foot", "foot" + s, FLAT, (side + "Toes", "ball" + s), False),
              (side + "Toes", "ball" + s, INHERIT, side + "Foot", False)]
        for fin, src in FINGERS:
            lat = fin != "Thumb"
            v = side + fin
            m += [(v + "Proximal", src + "_01" + s, AIM, (v + "Intermediate", src + "_02" + s), lat),
                  (v + "Intermediate", src + "_02" + s, AIM, (v + "Distal", src + "_03" + s), lat),
                  (v + "Distal", src + "_03" + s, INHERIT, v + "Intermediate", False)]
    return m


def _side(vrm):
    return "left" if vrm.startswith("left") else ("right" if vrm.startswith("right") else None)


# ---------------------------------------------------------------- source clip

class Source(object):
    """One PSA sequence as UE-convention local keys at an integer rate <= max_fps.

    UE's FrameRate is a ratio of integers, so clips above max_fps (the 120 fps grab/throw set) or at a
    non-integer rate are resampled at exact times i / fps; the tail shorter than one output frame is
    dropped (throw007: 272 keys at 120 fps, 2.2583 s -> 136 frames at 60 fps, 2.25 s). The length comes
    from a float32 AnimRate, so a tail within 1e-3 frame of a whole frame counts as one (rampage: 346 keys
    at 75 fps, 4.6 s -> 277 frames at 60 fps, not 276).
    """

    def __init__(self, path, seq=0, max_fps=MAX_FPS):
        self.path = path
        self.psa = psa_io.Psa(path)
        s = self.psa.sequences[seq]
        self.seq = s
        self.label = os.path.basename(path) if seq == 0 else "%s#%d" % (os.path.basename(path), seq)
        self.hash = self.psa.content_hash()
        bones = self.psa.bones
        self.names = [b.name for b in bones]
        self.index = self.psa.index
        self.parent = [-1 if i == 0 else b.parent for i, b in enumerate(bones)]
        for i, p in enumerate(self.parent):
            if p >= i:
                raise ValueError("%s: bone %s parent %d is not before it" % (path, self.names[i], p))
        self.ref = fk(self.parent, [(b.t, qnorm(b.q)) for b in bones])
        self.src_fps, self.src_frames, self.length = s.fps, s.frames, s.length
        local = [[(key_t(t), key_q(q, i == 0)) for i, (t, q) in enumerate(row)] for row in s.keys]
        integer = abs(s.fps - round(s.fps)) < 1e-3
        self.fps = float(round(s.fps)) if integer else s.fps
        if s.frames > 1 and (self.fps > max_fps + 1e-6 or not integer):
            fps = float(min(int(max_fps), int(round(s.fps))))
            key_rate = (s.frames - 1) / self.length
            n = int(math.floor(self.length * fps + 1e-3)) + 1
            out = []
            for i in range(n):
                u = min(i / fps * key_rate, s.frames - 1.0)
                i0 = min(int(math.floor(u)), s.frames - 2)
                f = u - i0
                a, b = local[i0], local[i0 + 1]
                out.append([(vadd(ta, vscale(vsub(tb, ta), f)), qslerp(qa, qb, f))
                            for (ta, qa), (tb, qb) in zip(a, b)])
            local = out
            self.fps = fps
            self.length = (n - 1) / fps
        self.local = local
        self.frames = len(local)
        self.trim_range = None
        # reference rotations with the clip's own bone offsets: clips keyed on Quinn proportions point
        # the thumb / index metacarpals 10-15 deg away from the Manny reference in the file
        # (walkstomp, kneeDownCrush), so aim directions are taken from here, rotation deltas from `ref`
        self.kref = fk(self.parent, [(b.t if i == 0 else local[0][i][0], qnorm(b.q)) for i, b in enumerate(bones)])

    def trim(self, t0=0.0, t1=None):
        """Keep only t0..t1 seconds (inclusive, snapped to frames): one part of a longer clip, e.g. the
        defeat is the first half of laydown_Anim (125 section 2.4)."""
        f0 = max(0, int(round(t0 * self.fps)))
        f1 = self.frames - 1 if t1 is None else min(self.frames - 1, int(round(t1 * self.fps)))
        if f1 - f0 < 1:
            raise ValueError("%s: trim %s..%s s leaves no interval" % (self.label, t0, t1))
        self.local = self.local[f0:f1 + 1]
        self.frames = len(self.local)
        self.length = (self.frames - 1) / self.fps
        self.trim_range = [round(f0 / self.fps, 4), round(f1 / self.fps, 4)]
        self.label = "%s[%.2f-%.2fs]" % (self.label, self.trim_range[0], self.trim_range[1])
        return self

    def bone_len(self, name, frame=0):
        i = self.index.get(name)
        return vlen(self.local[frame][i][0]) if i is not None else 0.0

    def world(self, in_place=False):
        out = []
        for row in self.local:
            if in_place:
                t, _q = row[0]
                row = [((0.0, 0.0, t[2]), IQ)] + row[1:]
            out.append(fk(self.parent, row))
        return out


# ---------------------------------------------------------------- retarget

class Retarget(object):
    def __init__(self, skel, src):
        self.skel = skel
        self.src = src
        sref = src.kref
        tref = skel.ref
        self.entries = []   # (target index, source index, W)
        self.missing = []
        W = {}
        lateral = {}
        for side, s in (("left", "_l"), ("right", "_r")):
            ti = [skel.human.get(side + f + "Proximal") for f in ("Index", "Little")]
            si = [src.index.get(n + s) for n in ("index_01", "pinky_01")]
            if all(ti) and all(i is not None for i in si):
                lateral[side] = (vsub(tref[skel.index[ti[1]]][0], tref[skel.index[ti[0]]][0]),
                                 cv(vsub(sref[si[1]][0], sref[si[0]][0])))
        for vrm, sname, mode, aim, lat in bone_map():
            tname = skel.human.get(vrm)
            si = src.index.get(sname)
            if tname is None or si is None:
                self.missing.append(vrm + "<-" + sname)
                continue
            ti = skel.index[tname]
            w = IQ
            if mode in (AIM, FLAT):
                tc, sc = skel.human.get(aim[0]), src.index.get(aim[1])
                if tc is None or sc is None:
                    self.missing.append(vrm + " aim " + aim[1])
                    continue
                at = vsub(tref[skel.index[tc]][0], tref[ti][0])
                as_ = cv(vsub(sref[sc][0], sref[si][0]))
                if mode == FLAT:
                    w = qyaw(at, as_)
                elif lat and _side(vrm) in lateral:
                    lt, ls = lateral[_side(vrm)]
                    w = qalign(frame(at, lt), frame(as_, ls))
                else:
                    w = qbetween(at, as_)
            elif mode == INHERIT:
                w = W.get(aim, IQ)
            W[vrm] = w
            self.entries.append((ti, si, w, vrm, mode, aim))
        self.mapped = dict((e[0], e) for e in self.entries)
        # leg / arm scale from the clip's own bone lengths
        tl = self._chain(("leftUpperLeg", "leftLowerLeg", "leftFoot"))
        ta = self._chain(("leftUpperArm", "leftLowerArm", "leftHand"))
        sl = 0.5 * sum(src.bone_len("calf" + s) + src.bone_len("foot" + s) for s in ("_l", "_r"))
        sa = 0.5 * sum(src.bone_len("lowerarm" + s) + src.bone_len("hand" + s) for s in ("_l", "_r"))
        self.k_leg = tl / sl if sl > 0 else 1.0
        self.k_arm = ta / sa if sa > 0 else 1.0

    def _chain(self, vrms):
        p = [self.skel.ref[self.skel.index[self.skel.human[v]]][0] for v in vrms]
        return sum(vlen(vsub(p[i + 1], p[i])) for i in range(len(p) - 1))

    def rotations(self, sworld):
        """Source world pose of one frame -> {target bone name: local quat} for the mapped bones."""
        skel = self.skel
        sref = self.src.ref
        world = [None] * len(skel.bones)
        local = {}
        for b in skel.bones:
            i = b["i"]
            p = skel.parent[i]
            pw = world[p] if p >= 0 else IQ
            e = self.mapped.get(i)
            if e is None:
                world[i] = pw
                continue
            _ti, si, w, _v, _m, _a = e
            d = cq(qmul(sworld[si][1], qconj(sref[si][1])))
            r = qnorm(qmul(d, w))
            world[i] = r
            local[b["name"]] = qnorm(qmul(qconj(pw), r))
        return local


def _contacts(skel, pose):
    """World contact points (heel, ball, toe tip of both feet) of a target FK pose."""
    pts = []
    for side in ("left", "right"):
        f = pose[skel.index[skel.human[side + "Foot"]]]
        t = pose[skel.index[skel.human[side + "Toes"]]]
        pts.append(vadd(f[0], qrot(f[1], HEEL)))
        pts.append(vadd(t[0], qrot(t[1], BALL)))
        pts.append(vadd(t[0], qrot(t[1], TOE_TIP)))
    return pts


def _envelope(vals, w, cyclic=False):
    """Smooth upper envelope: running max over +-w frames, then a triangle filter of half-width w.

    Every output value is >= the input at the same frame (each filter tap is a max over a window that
    contains it), so a floor shift built from it never pushes the body through the floor, while the kinks
    where the support moves from one body part to another (toes -> knee) are spread over 2 w frames.
    `cyclic` wraps the windows (the last frame repeats the first), so a looping clip stays closed.
    """
    n = len(vals)
    if n < 3 or w < 1:
        return list(vals)
    m = n - 1 if cyclic else n

    def at(i):
        if cyclic:
            return vals[i % m]
        return vals[max(0, min(n - 1, i))]

    mx = [max(at(i + k) for k in range(-w, w + 1)) for i in range(n)]

    def mat(i):
        if cyclic:
            return mx[i % m]
        return mx[max(0, min(n - 1, i))]

    wt = [w + 1 - abs(k) for k in range(-w, w + 1)]
    s = float(sum(wt))
    return [sum(wt[k + w] * mat(i + k) for k in range(-w, w + 1)) / s for i in range(n)]


def _cyclic(src):
    """The source's last frame repeats its first (a loop): same local rotations, pelvis within 1 cm."""
    a, b = src.local[0], src.local[-1]
    pel = src.index["pelvis"]
    return src.frames > 2 and max(qangle(x[1], y[1]) for x, y in zip(a, b)) < LOOP_DEG \
        and vlen(vsub(a[pel][0], b[pel][0])) < 1.0


def _detrend(vals):
    """Remove the linear drift from the first to the last frame, pivoting on the middle frame.

    The endpoint slope (not a least-squares fit) makes the first and last value equal, so an in-place
    locomotion cycle closes exactly.
    """
    n = len(vals)
    if n < 2:
        return list(vals)
    xm = (n - 1) / 2.0
    b = (vals[-1] - vals[0]) / (n - 1)
    return [v - b * (i - xm) for i, v in enumerate(vals)]


# ---------------------------------------------------------------- composite: still stance + torso sway

SWAY_BONES = ("spine_01", "spine_02", "spine_03", "spine_04", "spine_05", "neck_01", "neck_02", "head")


def qpow(q, a):
    """Rotation q with its angle scaled by a (shortest arc)."""
    if q[3] < 0.0:
        q = (-q[0], -q[1], -q[2], -q[3])
    th = math.acos(min(1.0, q[3]))
    s = math.sin(th)
    if s < 1e-9:
        return IQ
    k = math.sin(a * th) / s
    return (q[0] * k, q[1] * k, q[2] * k, math.cos(a * th))


def still_sway(base_path, sway_path, base_frame=0, amp=0.25, fade=1.0, max_fps=MAX_FPS):
    """Idle built only from PSA data (125 section 2.4): one frame of `base` held still, plus the spine / neck
    / head motion of `sway` relative to its first frame, angle-scaled by `amp`.

    Pelvis and legs stay on the base frame, so the feet are planted exactly. The sway weight eases to 0
    over the last `fade` seconds, so the last frame equals the first and the clip loops seamlessly.
    """
    base = Source(base_path, max_fps=max_fps)
    sway = Source(sway_path, max_fps=max_fps)
    row = base.local[base_frame]
    ids = [(base.index[n], sway.index[n]) for n in SWAY_BONES if n in base.index and n in sway.index]
    q0 = dict((si, sway.local[0][si][1]) for _bi, si in ids)
    n = sway.frames
    nf = max(1, int(round(fade * sway.fps)))
    out = []
    for f in range(n):
        u = min(1.0, (n - 1 - f) / float(nf))
        w = amp * u * u * (3.0 - 2.0 * u)
        r = list(row)
        for bi, si in ids:
            d = qpow(qnorm(qmul(sway.local[f][si][1], qconj(q0[si]))), w)
            r[bi] = (row[bi][0], qnorm(qmul(d, row[bi][1])))
        out.append(r)
    base.local = out
    base.frames = n
    base.fps = sway.fps
    base.length = (n - 1) / sway.fps
    base.label = "%s@%d + %s torso x%.2f" % (os.path.basename(base_path), base_frame,
                                            os.path.basename(sway_path), amp)
    base.hash = base.hash + "+" + sway.hash
    base.src_frames = sway.src_frames
    base.src_fps = sway.src_fps
    return base


def convert(psa, skel=None, in_place=False, ground="sole", seq=0, max_fps=MAX_FPS, name=None, key_time=None):
    """PSA path (or a prepared Source) -> {name, source, fps, frames, length, loop, skeleton, in_place,
    grounded, tracks, report}. `key_time` pins the report's verification still (default: see metrics)."""
    skel = skel or Skeleton()
    src = psa if isinstance(psa, Source) else Source(psa, seq, max_fps)
    rt = Retarget(skel, src)
    sw = src.world(in_place)
    hips = skel.human["hips"]
    hi = skel.index[hips]
    rest_t = skel.local_t[hi]
    pelvis = src.index["pelvis"]
    p_ref = src.ref[pelvis][0]

    delta = [vscale(cv(vsub(w[pelvis][0], p_ref)), rt.k_leg) for w in sw]
    if in_place:
        xs, ys = _detrend([d[0] for d in delta]), _detrend([d[1] for d in delta])
        delta = [(xs[i], ys[i], d[2]) for i, d in enumerate(delta)]
    poses = []
    for f, w in enumerate(sw):
        p = rt.rotations(w)
        p["@hips_t"] = vadd(rest_t, delta[f])
        poses.append(p)

    fkp = [skel.fk(p) for p in poses]
    body = body_of(skel)
    if ground == "floor":
        raw = [-min(body.lowest(q)[0], min(c[2] for c in _contacts(skel, q))) for q in fkp]
        shift = _envelope(raw, int(round(FLOOR_SMOOTH_S * src.fps)), _cyclic(src))
    elif ground == "sole":
        shift = [-min(min(c[2] for c in _contacts(skel, q)) for q in fkp)] * len(fkp)
    else:
        shift = [0.0] * len(fkp)
    if any(shift):
        for p, dz in zip(poses, shift):
            t = p["@hips_t"]
            p["@hips_t"] = (t[0], t[1], t[2] + dz)
        fkp = [[(vadd(pos, (0.0, 0.0, dz)), q) for pos, q in fr] for fr, dz in zip(fkp, shift)]

    names = sorted(k for k in poses[0] if k != "@hips_t")
    tracks = {}
    for b in names:
        qs = []
        prev = None
        for p in poses:
            q = p[b]
            if prev is not None and qdot(prev, q) < 0.0:
                q = (-q[0], -q[1], -q[2], -q[3])
            qs.append(q)
            prev = q
        tracks[b] = {"q": [[round(c, 6) for c in q] for q in qs], "t": None}
    tracks[hips]["t"] = [[round(c, 4) for c in p["@hips_t"]] for p in poses]

    loop_deg = max(qangle(tuple(tr["q"][0]), tuple(tr["q"][-1])) for tr in tracks.values())
    ht = tracks[hips]["t"]
    loop_cm = vlen(vsub(ht[0], ht[-1]))
    loop = src.frames > 2 and loop_deg < LOOP_DEG and loop_cm < 1.0

    report = {"source": src.label, "sequence": src.seq.name, "hash": src.hash,
              "src_bones": len(src.names), "src_fps": round(src.src_fps, 4), "src_frames": src.src_frames,
              "trim_s": src.trim_range,
              "fps": src.fps, "frames": src.frames, "length": round(src.length, 4),
              "in_place": bool(in_place), "ground": ground, "dz": round(shift[0], 3),
              "dz_range": [round(min(shift), 3), round(max(shift), 3)],
              "k_leg": round(rt.k_leg, 4), "k_arm": round(rt.k_arm, 4),
              "mapped": len(rt.entries), "missing": rt.missing, "tracks": len(tracks),
              "loop": loop, "loop_deg": round(loop_deg, 2), "loop_cm": round(loop_cm, 2)}
    # in-place clips (locomotion) hand their travel to gameplay, so they carry the per-frame speed curve
    report["root_motion"] = root_motion(src, rt, sw_full=src.world(False), curve=bool(in_place))
    report.update(metrics(skel, src, rt, sw, fkp, tracks, key_time))
    return {"name": name or src.seq.name, "source": src.label, "fps": src.fps,
            "frames": src.frames, "length": src.length, "loop": loop, "skeleton": skel.skeleton,
            "in_place": bool(in_place), "grounded": ground in ("sole", "floor"), "tracks": tracks, "report": report}


_BODY = {}


def body_of(skel):
    """anim_body.Body for this skeleton, built once per process."""
    b = _BODY.get(id(skel))
    if b is None:
        import anim_body
        b = _BODY[id(skel)] = anim_body.Body(skel)
    return b


def root_motion(src, rt, sw_full, curve=False):
    """Net travel of the source root and pelvis in target cm (x k_leg), and the root yaw change.

    `curve` adds the per-frame horizontal root speed and the distance travelled so far (skeleton cm, one
    value per clip frame; x the actor scale in the world). Gameplay moves an in-place clip's actor with it:
    speed for stride matching, distance for distance matching of the start / stop clips.
    """
    root = [w[0] for w in sw_full]
    pel = [w[src.index["pelvis"]][0] for w in sw_full]
    d_root = vscale(cv(vsub(root[-1][0], root[0][0])), rt.k_leg)
    d_pel = vscale(cv(vsub(pel[-1], pel[0])), rt.k_leg)
    fwd = (0.0, 1.0, 0.0)
    y0, y1 = qrot(root[0][1], fwd), qrot(root[-1][1], fwd)
    yaw = math.degrees(math.atan2(y1[1], y1[0]) - math.atan2(y0[1], y0[0]))
    yaw = (yaw + 180.0) % 360.0 - 180.0
    L = src.length or 1.0
    out = {"root_cm": [round(c, 2) for c in d_root], "pelvis_cm": [round(c, 2) for c in d_pel],
           "root_speed_cm_s": round(math.hypot(d_root[0], d_root[1]) / L, 2),
           "pelvis_speed_cm_s": round(math.hypot(d_pel[0], d_pel[1]) / L, 2),
           "root_yaw_deg": round(yaw, 2), "root_z0": round(root[0][0][2], 2)}
    if curve and len(root) > 1:
        xy = [vscale(cv(r[0]), rt.k_leg)[:2] for r in root]
        n = len(xy)
        speed = []
        for f in range(n):
            a, b = max(0, f - 1), min(n - 1, f + 1)
            speed.append(math.hypot(xy[b][0] - xy[a][0], xy[b][1] - xy[a][1]) * src.fps / (b - a))
        dist = [0.0]
        for f in range(1, n):
            dist.append(dist[-1] + math.hypot(xy[f][0] - xy[f - 1][0], xy[f][1] - xy[f - 1][1]))
        out["curve"] = {"fps": src.fps, "speed_cm_s": [round(v, 1) for v in speed],
                        "dist_cm": [round(v, 1) for v in dist],
                        "speed_min_max": [round(min(speed), 1), round(max(speed), 1)]}
    return out


def metrics(skel, src, rt, sw, fkp, tracks, key_time=None):
    """Quality checks: end-effector shape error, limb direction, contact heights, flips, arm elevation."""
    hips = skel.index[skel.human["hips"]]
    pel = src.index["pelvis"]
    out = {}
    # end effectors relative to hips / pelvis, mean-centred, source scaled by k
    eff = []
    for side, s in (("left", "_l"), ("right", "_r")):
        eff.append((side + "Hand", "hand" + s, rt.k_arm))
        eff.append((side + "Foot", "foot" + s, rt.k_leg))
    err = {}
    for vrm, sname, k in eff:
        ti, si = skel.index[skel.human[vrm]], src.index[sname]
        a = [vsub(fr[ti][0], fr[hips][0]) for fr in fkp]
        b = [vscale(cv(vsub(w[si][0], w[pel][0])), k) for w in sw]
        n = len(a)
        am = vscale(tuple(sum(v[c] for v in a) for c in range(3)), 1.0 / n)
        bm = vscale(tuple(sum(v[c] for v in b) for c in range(3)), 1.0 / n)
        e = [vlen(vsub(vsub(a[i], am), vsub(b[i], bm))) for i in range(n)]
        err[vrm] = (sum(e) / n, max(e))
    out["effector_err_cm"] = dict((k, [round(v[0], 2), round(v[1], 2)]) for k, v in err.items())
    out["effector_err_mean_cm"] = round(sum(v[0] for v in err.values()) / len(err), 2)
    # limb directions: target bone -> child vs source bone -> child (aim bones, actual key lengths)
    worst = (0.0, "")
    for ti, si, _w, vrm, mode, aim in rt.entries:
        if mode != AIM:
            continue
        tc = skel.index[skel.human[aim[0]]]
        sc = src.index[aim[1]]
        for f, fr in enumerate(fkp):
            ang = vangle(vsub(fr[tc][0], fr[ti][0]), cv(vsub(sw[f][sc][0], sw[f][si][0])))
            if ang > worst[0]:
                worst = (ang, "%s@%d" % (vrm, f))
    out["limb_dir_max_deg"] = [round(worst[0], 2), worst[1]]
    # contacts / penetration
    per = [min(c[2] for c in _contacts(skel, fr)) for fr in fkp]
    out["sole_min_cm"] = round(min(per), 2)
    out["sole_float_max_cm"] = round(max(per), 2)
    out["sole_float_mean_cm"] = round(sum(per) / len(per), 2)
    for vrm in ("leftLowerLeg", "rightLowerLeg", "leftHand", "rightHand"):
        ti = skel.index[skel.human[vrm]]
        out[vrm + "_min_z"] = round(min(fr[ti][0][2] for fr in fkp), 2)
    out["hips_z"] = [round(min(fr[hips][0][2] for fr in fkp), 2), round(max(fr[hips][0][2] for fr in fkp), 2)]
    # horizontal area the hips cover (min x, min y, max x, max y): framing for clips that travel
    hx, hy = [fr[hips][0][0] for fr in fkp], [fr[hips][0][1] for fr in fkp]
    out["hips_xy_box_cm"] = [round(min(hx), 1), round(min(hy), 1), round(max(hx), 1), round(max(hy), 1)]
    # whole body surface (anim_body): penetration anywhere, and the gap under the lowest point per frame
    low = [body_of(skel).lowest(fr) for fr in fkp]
    lf = min(range(len(low)), key=lambda f: low[f][0])
    out["body_min_cm"] = [round(low[lf][0], 2), "%s@%d" % (low[lf][1], lf)]
    out["body_float_max_cm"] = round(max(v[0] for v in low), 2)
    # flips: largest frame-to-frame local rotation step
    step = (0.0, "")
    for b, tr in tracks.items():
        qs = tr["q"]
        for f in range(1, len(qs)):
            a = qangle(tuple(qs[f - 1]), tuple(qs[f]))
            if a > step[0]:
                step = (a, "%s@%d" % (b, f))
    out["max_step_deg"] = [round(step[0], 2), step[1]]
    # the same on the mapped source bones: a target step well above this one is a flip, not fast motion
    sstep = (0.0, "")
    for _ti, si, _w, _vrm, _mode, _aim in rt.entries:
        for f in range(1, src.frames):
            a = qangle(src.local[f - 1][si][1], src.local[f][si][1])
            if a > sstep[0]:
                sstep = (a, "%s@%d" % (src.names[si], f))
    out["src_max_step_deg"] = [round(sstep[0], 2), sstep[1]]
    # T-pose guard: upper arm elevation below horizontal (deg), mean over the clip
    for side in ("left", "right"):
        ua, la = skel.index[skel.human[side + "UpperArm"]], skel.index[skel.human[side + "LowerArm"]]
        el = [math.degrees(math.asin(max(-1.0, min(1.0, -vunit(vsub(fr[la][0], fr[ua][0]))[2])))) for fr in fkp]
        out[side + "_arm_down_deg"] = [round(sum(el) / len(el), 1), round(min(el), 1), round(max(el), 1)]
        # angle of the upper arm from its rest (T-pose) direction: ~0 all clip long = the retarget did nothing
        r0 = vsub(skel.ref[la][0], skel.ref[ua][0])
        dv = [vangle(vsub(fr[la][0], fr[ua][0]), r0) for fr in fkp]
        out[side + "_arm_from_tpose_deg"] = [round(sum(dv) / len(dv), 1), round(min(dv), 1)]
    # verification still for the contact sheet: the frame whose pose (hands, feet, head relative to the
    # hips, so a clip that travels, like the kick stepping forward, is judged by its shape) is farthest
    # from the first frame, unless the caller pins `key_time`
    pts = dict((v, skel.index[skel.human[v]]) for v in ("hips", "head", "leftHand", "rightHand", "leftFoot", "rightFoot",
                                                         "leftMiddleProximal", "rightMiddleProximal") if v in skel.human)
    ends = [pts[v] for v in ("leftHand", "rightHand", "leftFoot", "rightFoot", "head")]
    hp = pts["hips"]

    def rel(fr, i):
        return vsub(fr[i][0], fr[hp][0])

    dev = [sum(vlen(vsub(rel(fr, i), rel(fkp[0], i))) for i in ends) for fr in fkp]
    kf = max(range(len(dev)), key=lambda f: dev[f])
    if key_time is not None:
        kf = max(0, min(len(fkp) - 1, int(round(key_time * src.fps))))
    out["key_frame"] = kf
    out["key_pinned"] = key_time is not None
    out["key_time"] = round(kf / src.fps, 4)
    out["key_points_cm"] = dict((v, [round(c, 1) for c in fkp[kf][i][0]]) for v, i in pts.items())
    hand_dev = dict((v, vlen(vsub(rel(fkp[kf], pts[v]), rel(fkp[0], pts[v])))) for v in ("leftHand", "rightHand"))
    out["key_hand"] = "leftHand" if hand_dev["leftHand"] > hand_dev["rightHand"] + 1.0 else "rightHand"
    return out


# ---------------------------------------------------------------- source-only analysis

def analyze(path, seq=0):
    src = Source(path, seq)
    sw = src.world(False)
    ix = src.index

    def z(name):
        i = ix[name]
        return [w[i][0][2] for w in sw]

    ref_z = dict((n, src.ref[ix[n]][0][2]) for n in ("ball_l", "ball_r", "foot_l", "foot_r", "pelvis"))
    feet = [min(w[ix["ball_l"]][0][2] - ref_z["ball_l"], w[ix["ball_r"]][0][2] - ref_z["ball_r"],
                w[ix["foot_l"]][0][2] - ref_z["foot_l"], w[ix["foot_r"]][0][2] - ref_z["foot_r"]) for w in sw]
    pel = z("pelvis")
    root = [w[0][0] for w in sw]
    energy = 0.0
    for n in ("upperarm_l", "upperarm_r", "thigh_l", "thigh_r", "spine_05", "head"):
        i = ix[n]
        energy += sum(qangle(sw[f - 1][i][1], sw[f][i][1]) for f in range(1, len(sw))) / max(1.0, src.length)
    hands = [min(w[ix["hand_l"]][0][2], w[ix["hand_r"]][0][2]) for w in sw]
    fwd = []
    for w in sw:  # body facing from the pelvis: source forward is +Y
        f = qrot(w[ix["pelvis"]][1], (0.0, 1.0, 0.0))
        fwd.append(math.degrees(math.atan2(f[1], f[0])))
    return {"file": os.path.basename(path), "seq": src.seq.name, "fps": src.src_fps, "frames": src.src_frames,
            "length": round(src.length, 3), "hash": src.psa.content_hash(),
            "root_disp": [round(c, 1) for c in vsub(root[-1], root[0])], "root_z": round(root[0][2], 2),
            "pelvis_z": [round(min(pel), 1), round(max(pel), 1), round(ref_z["pelvis"], 1)],
            "pelvis_xy_disp": [round(sw[-1][ix["pelvis"]][0][c] - sw[0][ix["pelvis"]][0][c], 1) for c in (0, 1)],
            "feet_above_flat": [round(min(feet), 1), round(max(feet), 1)],
            "hand_min_z": round(min(hands), 1), "head_z": [round(min(z("head")), 1), round(max(z("head")), 1)],
            "facing_deg": [round(min(fwd), 1), round(max(fwd), 1)],
            "energy_deg_s": round(energy, 1)}


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    if argv[0] == "--analyze":
        for p in argv[1:]:
            print(json.dumps(analyze(p), ensure_ascii=False))
        return 0
    path = argv[0]
    in_place = "--in-place" in argv
    ground = argv[argv.index("--ground") + 1] if "--ground" in argv else "sole"
    seq = int(argv[argv.index("--seq") + 1]) if "--seq" in argv else 0
    data = convert(path, in_place=in_place, ground=ground, seq=seq)
    print(json.dumps(data["report"], ensure_ascii=False, indent=1))
    if "--out" in argv:
        with io.open(argv[argv.index("--out") + 1], "w", encoding="utf-8") as f:
            json.dump(data, f)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
