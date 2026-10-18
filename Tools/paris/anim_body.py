"""Body surface of the 416 VRM as a few thousand bone-rigid points, for floor contact (pure Python).

The sole contacts in anim_psa (heel, ball, toe tip) only tell where the feet are. Kneeling, sitting on the
floor and lying need the rest of the body: knees, buttocks, back, head. This module reads the skinned
meshes of Saved/Staging/vrm/416.glb (read-only copy) and keeps, per skin bone, the vertices that are
extreme in one of DIRS directions, as offsets from the bone's rest position in UE component space.

  coordinates  glTF (x, y, z) m -> UE (100 x, 100 z, 100 y) cm, checked on the hips / head / wrist / foot
               joints against skeleton.json; the inverse bind matrices are identity at the node pose, so the
               vertex positions are already the bind pose.
  skinning     rigid, dominant weight only: good to a few mm near the joints, which is enough to put the
               lowest point on the floor.
  soft parts   the hair chains (VRM spring bones under the head) are left out: they hang down the back in
               the rest pose and would lift her off the floor when she lies on her back. The other spring
               bones (breasts, backpack, pendants) are not simulated, so they stay rigid with the torso and
               count, like the solid gear (thigh holster, hat).

A pose from Skeleton.fk gives each bone's world rotation R and position P; the height of an offset o is
P.z + o . (third row of R).

CLI: python Tools/paris/anim_body.py      rebuild the cache Saved/Staging/Anim/body_points.json
"""
import io
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gltf_io  # noqa: E402
from anim_retarget import GLB, STAGE, Skeleton, _norm  # noqa: E402

BODY_JSON = os.path.join(STAGE, "body_points.json")
DIRS = 96
VERSION = 2


def _fib_dirs(n):
    out = []
    ga = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(n):
        z = 1.0 - 2.0 * (i + 0.5) / n
        r = math.sqrt(max(0.0, 1.0 - z * z))
        out.append((r * math.cos(ga * i), r * math.sin(ga * i), z))
    return out


def build(skel, glb=GLB, dirs=DIRS):
    g = gltf_io.Gltf(glb)
    js = g.js
    nodes = js["nodes"]
    vrm = js["extensions"]["VRM"]
    spring = set()
    for grp in vrm.get("secondaryAnimation", {}).get("boneGroups", []):
        stack = list(grp.get("bones", []))
        while stack:
            n = stack.pop()
            spring.add(n)
            stack.extend(nodes[n].get("children", []))
    # only the hair chains (spring bones under the head) are soft: nothing simulates the spring bones yet,
    # so breasts, backpack and pendants move rigidly with the torso and must rest on the floor like it
    head = [h["node"] for h in vrm["humanoid"]["humanBones"] if h["bone"] == "head"]
    soft = set()
    stack = list(head)
    while stack:
        n = stack.pop()
        if n in spring:
            soft.add(n)
        stack.extend(nodes[n].get("children", []))
    by_norm = dict((_norm(b["name"]), b["name"]) for b in skel.bones)
    ref = skel.ref
    verts = {}
    counts = {"vertices": 0, "soft": 0, "unmapped": 0}
    for n in nodes:
        if "mesh" not in n or "skin" not in n:
            continue
        joints = js["skins"][n["skin"]]["joints"]
        for prim in js["meshes"][n["mesh"]]["primitives"]:
            pos, _ = g.accessor(prim["attributes"]["POSITION"])
            J, _ = g.accessor(prim["attributes"]["JOINTS_0"])
            W, _ = g.accessor(prim["attributes"]["WEIGHTS_0"])
            for v in range(len(pos) // 3):
                counts["vertices"] += 1
                w = W[v * 4:v * 4 + 4]
                k = max(range(4), key=lambda c: w[c])
                node = joints[J[v * 4 + k]]
                if node in soft:
                    counts["soft"] += 1
                    continue
                bone = by_norm.get(_norm(nodes[node].get("name", "")))
                if bone is None:
                    counts["unmapped"] += 1
                    continue
                x, y, z = pos[v * 3:v * 3 + 3]
                verts.setdefault(bone, []).append((100.0 * x, 100.0 * z, 100.0 * y))
    D = _fib_dirs(dirs)
    bones = {}
    lowest = 1e9
    for bone, vs in verts.items():
        p = ref[skel.index[bone]][0]
        keep = set()
        for d in D:
            keep.add(max(range(len(vs)), key=lambda i: vs[i][0] * d[0] + vs[i][1] * d[1] + vs[i][2] * d[2]))
        bones[bone] = [[round(vs[i][c] - p[c], 3) for c in range(3)] for i in sorted(keep)]
        lowest = min(lowest, min(v[2] for v in vs))
    st = os.stat(glb)
    return {"version": VERSION, "glb": os.path.basename(glb), "glb_size": st.st_size, "dirs": dirs,
            "skeleton": skel.skeleton, "counts": counts, "rest_lowest_cm": round(lowest, 3),
            "points": sum(len(v) for v in bones.values()), "bones": bones}


def load(skel, glb=GLB, path=BODY_JSON):
    """Cached build(); rebuilt when the glb, the direction count or the format changes."""
    size = os.stat(glb).st_size
    if os.path.exists(path):
        d = json.load(io.open(path, encoding="utf-8"))
        if d.get("version") == VERSION and d.get("glb_size") == size and d.get("dirs") == DIRS \
                and d.get("skeleton") == skel.skeleton:
            return d
    d = build(skel, glb)
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(d, f)
    return d


class Body(object):
    def __init__(self, skel, glb=GLB):
        self.skel = skel
        self.data = load(skel, glb)
        self.items = [(skel.index[b], pts) for b, pts in self.data["bones"].items() if b in skel.index]
        # humanoid owner of each bone, to name the part that touches
        human = dict((v, k) for k, v in skel.human.items())
        self.part = {}
        for i, _pts in self.items:
            j = i
            while j >= 0 and skel.bones[j]["name"] not in human:
                j = skel.parent[j]
            self.part[i] = human.get(skel.bones[j]["name"], "?") if j >= 0 else "?"

    def lowest(self, pose):
        """(height, humanoid part) of the lowest body point of a target FK pose."""
        best = (1e9, -1)
        for i, pts in self.items:
            (px, py, pz), (x, y, z, w) = pose[i]
            r0, r1, r2 = 2.0 * (x * z - w * y), 2.0 * (y * z + w * x), 1.0 - 2.0 * (x * x + y * y)
            m = min(o[0] * r0 + o[1] * r1 + o[2] * r2 for o in pts) + pz
            if m < best[0]:
                best = (m, i)
        return best[0], self.part.get(best[1], "?")

    def lowest_by_part(self, pose):
        """{humanoid part: lowest height} of a target FK pose."""
        out = {}
        for i, pts in self.items:
            (px, py, pz), (x, y, z, w) = pose[i]
            r0, r1, r2 = 2.0 * (x * z - w * y), 2.0 * (y * z + w * x), 1.0 - 2.0 * (x * x + y * y)
            m = min(o[0] * r0 + o[1] * r1 + o[2] * r2 for o in pts) + pz
            p = self.part[i]
            if m < out.get(p, 1e9):
                out[p] = m
        return out


if __name__ == "__main__":
    sk = Skeleton()
    d = build(sk)
    with io.open(BODY_JSON, "w", encoding="utf-8") as f:
        json.dump(d, f)
    print(json.dumps(dict((k, v) for k, v in d.items() if k != "bones"), ensure_ascii=False))
