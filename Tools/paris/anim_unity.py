"""Unity AnimationClip (.anim, AssetRipper YAML) reader for humanoid clips (pure Python, no `unreal`).

DEPRECATED (doc 125 section 2, doc 127): the clips this reads are superseded by the ActorX .psa set
(anim_psa.py + 11_gp_animations.py), and the A_Clukay_* assets built from them were deleted in A2. Kept
for reference and for anything that still needs to inspect the Unity library; no build step calls it.

The sizebox animation library (453 clips, read-only Unity project) is exported as YAML AnimationClips.
354 of them are Unity **Humanoid** clips: instead of bone tracks they store
    * `RootT.x/y/z`, `RootQ.x/y/z/w`  - the body (hips) transform, normalised by the avatar's human scale
    * muscle curves like `Left Upper Leg Front-Back` - one normalised [-1, 1] DoF per human bone axis
    * IK goal curves `LeftFootT/Q`, `RightHandT/Q`, ... - only used as ground truth by anim_retarget.py
The remaining 99 clips are generic clips whose bone paths were exported as hashes
(`path_0xDD3D365E_IRhlIWL`), so they cannot be retargeted and are rejected here.

Curves are Hermite (`inSlope` / `outSlope`, unweighted) and are resampled to a fixed frame rate.

Usage: python Tools/paris/anim_unity.py <clip.anim> [--fps 30]
"""
import io
import math
import os
import sys

FPS = 30.0

# ---------------------------------------------------------------- parsing


def _f(s):
    s = s.strip()
    if s in ("Infinity", ".inf"):
        return math.inf
    if s in ("-Infinity", "-.inf"):
        return -math.inf
    if s in ("NaN", ".nan"):
        return math.nan
    return float(s)


def read_clip(path):
    """Parse one .anim file. Returns dict(name, stop, loop, curves={attribute: [(t, v, in, out), ...]}, generic=bool)."""
    name = os.path.splitext(os.path.basename(path))[0]
    curves = {}
    generic = False
    section = None
    keys = None
    key = None
    stop = 0.0
    loop = False
    settings = False
    with io.open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.rstrip("\n")
            if s.startswith("  m_"):
                head = s[4:].split(":")[0]
                empty = s.rstrip().endswith("[]")
                if head in ("RotationCurves", "PositionCurves", "ScaleCurves", "EulerCurves") and not empty:
                    generic = True
                section = head
                settings = head == "AnimationClipSettings"
                if head == "Name":
                    name = s.split(": ", 1)[1] if ": " in s else name
                continue
            if settings:
                t = s.strip()
                if t.startswith("m_StopTime:"):
                    stop = _f(t.split(":")[1])
                elif t.startswith("m_LoopTime:"):
                    loop = t.split(":")[1].strip() == "1"
                continue
            if section != "FloatCurves":
                continue
            if s.startswith("  - "):  # new curve entry
                keys = []
                key = None
            elif keys is not None:
                t = s.strip()
                if t.startswith("attribute: "):  # last line of the entry names the curve
                    curves[t[11:]] = keys
                    keys = None
                    key = None
                elif t.startswith("time: "):
                    key = [_f(t[6:]), 0.0, 0.0, 0.0]
                    keys.append(key)
                elif key is not None:
                    if t.startswith("value: "):
                        key[1] = _f(t[7:])
                    elif t.startswith("inSlope: "):
                        key[2] = _f(t[9:])
                    elif t.startswith("outSlope: "):
                        key[3] = _f(t[10:])
    return {"name": name, "stop": stop, "loop": loop, "curves": curves, "generic": generic}


# ---------------------------------------------------------------- evaluation


def eval_curve(keys, t):
    """Unity AnimationCurve evaluation (unweighted Hermite, clamped ends)."""
    n = len(keys)
    if n == 0:
        return 0.0
    if t <= keys[0][0]:
        return keys[0][1]
    if t >= keys[-1][0]:
        return keys[-1][1]
    lo, hi = 0, n - 1
    while hi - lo > 1:  # keys are sorted by time
        mid = (lo + hi) // 2
        if keys[mid][0] <= t:
            lo = mid
        else:
            hi = mid
    t0, v0, _, m0 = keys[lo]
    t1, v1, m1, _ = keys[hi]
    dt = t1 - t0
    if dt <= 1e-9:
        return v1
    s = (t - t0) / dt
    if not (math.isfinite(m0) and math.isfinite(m1)):  # stepped key
        return v0
    m0 *= dt
    m1 *= dt
    s2 = s * s
    s3 = s2 * s
    return (2 * s3 - 3 * s2 + 1) * v0 + (s3 - 2 * s2 + s) * m0 + (-2 * s3 + 3 * s2) * v1 + (s3 - s2) * m1


def resample(clip, fps=FPS):
    """Resample every curve to `frames` evenly spaced samples. Returns dict(frames, fps, values={attr: [..]}, ...)."""
    stop = clip["stop"]
    if stop <= 0:
        for keys in clip["curves"].values():
            if keys:
                stop = max(stop, keys[-1][0])
    frames = max(1, int(round(stop * fps)) + 1)
    times = [i / fps for i in range(frames)]
    values = {a: [eval_curve(k, t) for t in times] for a, k in clip["curves"].items()}
    return {"name": clip["name"], "frames": frames, "fps": fps, "length": (frames - 1) / fps,
            "loop": clip["loop"], "values": values}


def main(argv):
    path = argv[0]
    fps = float(argv[argv.index("--fps") + 1]) if "--fps" in argv else FPS
    clip = read_clip(path)
    print("clip %r generic=%s stop=%.3f loop=%s curves=%d" % (clip["name"], clip["generic"], clip["stop"], clip["loop"], len(clip["curves"])))
    r = resample(clip, fps)
    print("frames", r["frames"], "length %.3f" % r["length"])
    for a in ("RootT.x", "RootT.y", "RootT.z", "RootQ.w", "Left Upper Leg Front-Back", "Left Lower Leg Stretch",
              "Left Forearm Stretch", "Left Arm Down-Up", "Spine Front-Back"):
        v = r["values"].get(a)
        if v:
            print("  %-26s min %7.3f max %7.3f  head %s" % (a, min(v), max(v), ["%.3f" % x for x in v[:5]]))


if __name__ == "__main__":
    main(sys.argv[1:])
