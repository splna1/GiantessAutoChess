"""M4 step 0 (host-side, read-only): inventory the 100 roster VRMs before importing any of them.

For each char_001..char_100 row of Content/Data/Generated/Roster112.json, resolve its legacy Unity path under
the read-only source tree and parse the .vrm as glTF (VRM 0.x and 1.0 are both glTF 2.0 + an extension).
Nothing is copied or written outside Saved/Reports.

What it measures, and why (each item is a defect N2 hit on the MMD models; see document/151):
  * VRM version and the humanoid bone map (hips, spine, chest, neck, head, arms, legs);
  * skinned vertices per humanoid bone -- a retarget chain on bones that carry no skin moves nothing
    (memory: tread-mmd-dbone-skin); where a humanoid limb bone is unskinned, the skinned sibling bone
    under the same parent is reported as the candidate;
  * scale / rotation on the scene root nodes and the skeleton root -- a non-identity node transform ends
    up as a root-bone transform a retargeted clip overwrites (memory: tread-mmd-root-scale);
  * upper-arm angle away from straight down in the bind pose: T-pose ~90, A-pose ~45 (the retarget pose
    must be aligned when it differs from the hero's, memory: tread-retarget-pose-align);
  * facing from the foot -> toe vectors, in glTF axes (+Y up, the VRM 0.x convention faces -Z, VRM 1.0 +Z)
    (memory: tread-mmd-facing);
  * height, meshes, materials, MToon use, morph targets, file size and a content hash for duplicates.

    python Tools/m4/vrm_inventory.py [--only char_001]

Report: Saved/Reports/M4_VRM_Inventory.json
"""
import argparse
import hashlib
import json
import math
import os
import struct
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROSTER = os.path.join(ROOT, "Content", "Data", "Generated", "Roster112.json")
UNITY_PROJECT = "F:/AI/workbuddy/GiantessAutoChess/MyProject"  # read-only
REPORT = os.path.join(ROOT, "Saved", "Reports", "M4_VRM_Inventory.json")

HUMANOID = ["hips", "spine", "chest", "upperChest", "neck", "head",
            "leftShoulder", "leftUpperArm", "leftLowerArm", "leftHand",
            "rightShoulder", "rightUpperArm", "rightLowerArm", "rightHand",
            "leftUpperLeg", "leftLowerLeg", "leftFoot", "leftToes",
            "rightUpperLeg", "rightLowerLeg", "rightFoot", "rightToes"]
LIMBS = ["leftUpperArm", "leftLowerArm", "leftHand", "rightUpperArm", "rightLowerArm", "rightHand",
         "leftUpperLeg", "leftLowerLeg", "leftFoot", "rightUpperLeg", "rightLowerLeg", "rightFoot"]
COMPONENT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_glb(path):
    with open(path, "rb") as f:
        blob = f.read()
    magic, _, _ = struct.unpack_from("<4sII", blob, 0)
    if magic != b"glTF":
        raise ValueError("not a GLB")
    offset, doc, binary = 12, None, b""
    while offset < len(blob):
        length, kind = struct.unpack_from("<I4s", blob, offset)
        chunk = blob[offset + 8:offset + 8 + length]
        if kind == b"JSON":
            doc = json.loads(chunk.decode("utf-8"))
        elif kind == b"BIN\x00":
            binary = chunk
        offset += 8 + length
    return blob, doc, binary


def accessor(doc, binary, index):
    acc = doc["accessors"][index]
    view = doc["bufferViews"][acc["bufferView"]]
    dtype = np.dtype(COMPONENT[acc["componentType"]])
    width = WIDTH[acc["type"]]
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = view.get("byteStride", 0) or dtype.itemsize * width
    count = acc["count"]
    if stride == dtype.itemsize * width:
        data = np.frombuffer(binary, dtype, count * width, start).reshape(count, width)
    else:
        rows = [np.frombuffer(binary, dtype, width, start + i * stride) for i in range(count)]
        data = np.stack(rows)
    if acc.get("normalized") and dtype.kind in "iu":
        data = data.astype(np.float32) / np.iinfo(dtype).max
    return data


def quat_matrix(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def local_matrix(node):
    m = np.eye(4)
    if "matrix" in node:
        return np.array(node["matrix"], dtype=float).reshape(4, 4).T
    t = node.get("translation", [0, 0, 0])
    r = node.get("rotation", [0, 0, 0, 1])
    s = node.get("scale", [1, 1, 1])
    m[:3, :3] = quat_matrix(r) @ np.diag(s)
    m[:3, 3] = t
    return m


def world_matrices(doc):
    nodes = doc["nodes"]
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i
    cache = {}

    def world(i):
        if i not in cache:
            m = local_matrix(nodes[i])
            cache[i] = world(parent[i]) @ m if i in parent else m
        return cache[i]

    return [world(i) for i in range(len(nodes))], parent


def humanoid_map(doc):
    ext = doc.get("extensions", {})
    if "VRMC_vrm" in ext:
        bones = ext["VRMC_vrm"].get("humanoid", {}).get("humanBones", {})
        return "1.0", {k: v["node"] for k, v in bones.items() if "node" in v}
    if "VRM" in ext:
        bones = ext["VRM"].get("humanoid", {}).get("humanBones", [])
        return "0.x", {b["bone"]: b["node"] for b in bones if "node" in b and b.get("node", -1) >= 0}
    return None, {}


def skinned_counts(doc, binary):
    """node index -> vertices with weight > 0.01 on it, over every skinned primitive."""
    counts = {}
    for node in doc["nodes"]:
        if "mesh" not in node or "skin" not in node:
            continue
        joints = doc["skins"][node["skin"]]["joints"]
        for prim in doc["meshes"][node["mesh"]]["primitives"]:
            attrs = prim["attributes"]
            for set_index in range(4):
                jk, wk = "JOINTS_%d" % set_index, "WEIGHTS_%d" % set_index
                if jk not in attrs or wk not in attrs:
                    break
                j = accessor(doc, binary, attrs[jk]).astype(np.int64)
                w = accessor(doc, binary, attrs[wk]).astype(np.float32)
                for col in range(j.shape[1]):
                    hit = j[w[:, col] > 0.01, col]
                    for local, n in zip(*np.unique(hit, return_counts=True)):
                        node_index = joints[int(local)]
                        counts[node_index] = counts.get(node_index, 0) + int(n)
    return counts


def vertex_bounds(doc, binary, worlds):
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    for i, node in enumerate(doc["nodes"]):
        if "mesh" not in node:
            continue
        for prim in doc["meshes"][node["mesh"]]["primitives"]:
            acc = doc["accessors"][prim["attributes"]["POSITION"]]
            if "min" in acc and "max" in acc:
                p = np.array([acc["min"], acc["max"]], dtype=float)
            else:
                p = accessor(doc, binary, prim["attributes"]["POSITION"]).astype(float)
            # Skinned meshes are bound in their own space; glTF says to ignore the mesh node's transform.
            if "skin" not in node:
                p = (worlds[i][:3, :3] @ p.T).T + worlds[i][:3, 3]
            lo, hi = np.minimum(lo, p.min(0)), np.maximum(hi, p.max(0))
    return lo, hi


def subtree(doc, i):
    out, stack = [], [i]
    while stack:
        n = stack.pop()
        out.append(n)
        stack.extend(doc["nodes"][n].get("children", []))
    return out


def d_variant(name):
    """The MMD deform twin of a leg bone name: 足.L -> 足D.L, ひざ_R -> ひざD_R, 足首 -> 足首D."""
    for sep in (".", "_"):
        for side in ("L", "R"):
            tail = sep + side
            if name.endswith(tail):
                return name[:-len(tail)] + "D" + tail
    return name + "D"


def chain_bones(doc, hmap, skin, keys):
    """Humanoid bones of one limb, or their skinned MMD D twins when the limb's skin lives in a parallel
    hierarchy (the D twins carry more weights than the humanoid bones)."""
    nodes = doc["nodes"]
    by_name = {n.get("name"): i for i, n in enumerate(nodes)}
    first = hmap[keys[0]]
    under = sum(skin.get(n, 0) for n in subtree(doc, first))
    names = [nodes[hmap[k]].get("name") for k in keys]
    twins = [by_name.get(d_variant(n)) for n in names]
    own = sum(skin.get(hmap[k], 0) for k in keys)
    # Prefer the D twins when they carry more skin than the humanoid bones themselves.  Testing the
    # humanoid bone's whole subtree missed char_004/012/029/030: an accessory under 足.L, or 123 stray
    # vertices on 足.L itself, made the plain chain look skinned while the leg itself sat on the D set.
    if all(t is not None for t in twins) and sum(skin.get(t, 0) for t in twins) > own:
        return {"bones": [nodes[t].get("name") for t in twins], "via": "D",
                "skin": [skin.get(t, 0) for t in twins]}
    return {"bones": names, "via": "humanoid" if under else "UNSKINNED", "skin": [skin.get(hmap[k], 0) for k in keys],
            "subtreeSkin": under}


def meta(doc):
    ext = doc.get("extensions", {})
    if "VRMC_vrm" in ext:
        m = ext["VRMC_vrm"].get("meta", {})
        return {"title": m.get("name"), "author": ", ".join(m.get("authors", [])), "license": m.get("licenseUrl"),
                "avatarPermission": m.get("avatarPermission"), "violent": m.get("allowExcessivelyViolentUsage"),
                "commercial": m.get("commercialUsage"), "credit": m.get("creditNotation")}
    m = ext.get("VRM", {}).get("meta", {})
    return {"title": m.get("title"), "author": m.get("author"), "license": m.get("licenseName"),
            "avatarPermission": m.get("allowedUserName"), "violent": m.get("violentUssageName"),
            "commercial": m.get("commercialUssageName"), "otherPermission": m.get("otherPermissionUrl")}


def angle_from_down(v):
    n = np.linalg.norm(v) or 1.0
    return round(math.degrees(math.acos(max(-1.0, min(1.0, -v[1] / n)))), 1)


def probe(path):
    blob, doc, binary = read_glb(path)
    version, hmap = humanoid_map(doc)
    worlds, parent = world_matrices(doc)
    nodes = doc["nodes"]
    pos = lambda i: worlds[i][:3, 3]  # noqa: E731
    skin = skinned_counts(doc, binary)
    out = {"bytes": len(blob), "sha1": hashlib.sha1(blob).hexdigest(), "vrm": version,
           "extensionsUsed": doc.get("extensionsUsed", []), "nodes": len(nodes),
           "meshes": len(doc.get("meshes", [])), "skins": len(doc.get("skins", [])),
           "materials": len(doc.get("materials", [])),
           "mtoon": any(e in doc.get("extensionsUsed", []) for e in ("VRMC_materials_mtoon",)) or (
               version == "0.x" and any(m.get("shader") == "VRM/MToon"
                                        for m in doc["extensions"]["VRM"].get("materialProperties", []))),
           "morphTargets": sum(len(p.get("targets", [])) for m in doc.get("meshes", []) for p in m["primitives"]),
           "jointCount": len({j for s in doc.get("skins", []) for j in s["joints"]})}
    out["humanoid"] = {k: nodes[v].get("name") for k, v in hmap.items() if k in HUMANOID}
    out["missingHumanoid"] = [k for k in HUMANOID if k not in hmap and k not in ("upperChest", "leftToes", "rightToes",
                                                                                   "leftShoulder", "rightShoulder")]
    # Scene roots and the skeleton root: every non-identity transform here is a future root-bone transform.
    roots = doc["scenes"][doc.get("scene", 0)]["nodes"]
    odd = []
    for r in roots:
        n = nodes[r]
        s, q = n.get("scale", [1, 1, 1]), n.get("rotation", [0, 0, 0, 1])
        if "matrix" in n or max(abs(v - 1) for v in s) > 1e-4 or max(abs(v) for v in q[:3]) > 1e-4:
            odd.append({"node": n.get("name"), "scale": s, "rotation": q, "matrix": "matrix" in n})
    out["rootTransforms"] = odd
    scales = [np.linalg.norm(worlds[j][:3, :3], axis=0) for s in doc.get("skins", []) for j in s["joints"]]
    out["jointWorldScale"] = [round(float(np.min(scales)), 4), round(float(np.max(scales)), 4)] if scales else None
    # Skin on the humanoid limb bones, and an unskinned limb's skinned sibling (the MMD "D" bone pattern).
    unskinned = {}
    for key in LIMBS:
        if key not in hmap:
            continue
        i = hmap[key]
        if skin.get(i, 0) == 0:
            p = parent.get(i)
            siblings = [c for c in (nodes[p].get("children", []) if p is not None else []) if c != i]
            alt = max(siblings, key=lambda c: skin.get(c, 0), default=None)
            unskinned[key] = {"bone": nodes[i].get("name"),
                              "skinnedSibling": nodes[alt].get("name") if alt is not None and skin.get(alt, 0) else None,
                              "siblingVerts": skin.get(alt, 0) if alt is not None else 0}
    out["limbSkin"] = {k: skin.get(hmap[k], 0) for k in LIMBS if k in hmap}
    out["unskinnedLimbs"] = unskinned
    out["meta"] = meta(doc)
    # Retarget chain candidates per limb: the humanoid bones, or the MMD D twins when needed.
    limbs = {"LeftArm": ["leftUpperArm", "leftHand"], "RightArm": ["rightUpperArm", "rightHand"],
             "LeftLeg": ["leftUpperLeg", "leftLowerLeg", "leftFoot"],
             "RightLeg": ["rightUpperLeg", "rightLowerLeg", "rightFoot"]}
    out["chains"] = {c: chain_bones(doc, hmap, skin, k) for c, k in limbs.items() if all(x in hmap for x in k)}
    lo, hi = vertex_bounds(doc, binary, worlds)
    out["boundsMin"], out["boundsMax"] = [round(float(v), 3) for v in lo], [round(float(v), 3) for v in hi]
    out["heightM"] = round(float(hi[1] - lo[1]), 3)
    if all(k in hmap for k in ("leftUpperArm", "leftHand", "rightUpperArm", "rightHand")):
        out["armDeg"] = {"L": angle_from_down(pos(hmap["leftHand"]) - pos(hmap["leftUpperArm"])),
                         "R": angle_from_down(pos(hmap["rightHand"]) - pos(hmap["rightUpperArm"]))}
        mean = (out["armDeg"]["L"] + out["armDeg"]["R"]) / 2
        out["bindPose"] = "T" if mean > 70 else ("A" if mean > 25 else "down")
    # Facing in glTF axes: the horizontal direction the toes point, else left x up for the chest.
    toe = []
    for foot, toes in (("leftFoot", "leftToes"), ("rightFoot", "rightToes")):
        if foot in hmap and toes in hmap:
            toe.append(pos(hmap[toes]) - pos(hmap[foot]))
    if toe:
        v = np.mean(toe, axis=0)
    elif "leftUpperLeg" in hmap and "rightUpperLeg" in hmap:
        side = pos(hmap["leftUpperLeg"]) - pos(hmap["rightUpperLeg"])
        v = np.cross(side, [0, 1, 0]) * -1  # left x up = backward for a right-handed +Y-up frame
    else:
        v = None
    if v is not None:
        out["facingGltf"] = "+Z" if v[2] > abs(v[0]) else "-Z" if -v[2] > abs(v[0]) else "+X" if v[0] > 0 else "-X"
    return out


def count_meta(rows, key):
    out = {}
    for r in rows:
        v = str(r["meta"].get(key))
        out[v] = out.get(v, 0) + 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    roster = json.load(open(ROSTER, encoding="utf-8"))["characters"]
    rows = []
    for r in roster:
        cid = r["characterId"]
        if r.get("modelSource") != "legacy-vrm" or (a.only and cid != a.only):
            continue
        path = os.path.join(UNITY_PROJECT, r["modelAssetPath"])
        row = {"characterId": cid, "modelName": r["modelName"], "source": path.replace("\\", "/")}
        if not os.path.isfile(path):
            row["error"] = "missing"
        else:
            try:
                row.update(probe(path))
            except Exception as error:  # noqa: BLE001 - one bad file must not hide the other 99
                row["error"] = "%s: %s" % (type(error).__name__, error)
        rows.append(row)
        print("VRM %s %-4s %s pose=%s face=%s h=%s unskinned=%d roots=%d %s" % (
            cid, row.get("vrm"), "ok " if "error" not in row else "ERR", row.get("bindPose"), row.get("facingGltf"),
            row.get("heightM"), len(row.get("unskinnedLimbs", {})), len(row.get("rootTransforms", [])),
            row.get("error", "")))
    hashes = {}
    for row in rows:
        if "sha1" in row:
            hashes.setdefault(row["sha1"], []).append(row["characterId"])
    good = [r for r in rows if "error" not in r]
    count = lambda key: {str(k): sum(1 for r in good if r.get(key) == k) for k in sorted({str(r.get(key)) for r in good})}  # noqa: E731
    summary = {"rows": len(rows), "ok": len(good), "errors": [r["characterId"] for r in rows if "error" in r],
               "vrm": count("vrm"), "bindPose": count("bindPose"), "facingGltf": count("facingGltf"),
               "withUnskinnedLimbs": [r["characterId"] for r in good if r["unskinnedLimbs"]],
               "chainsViaD": [r["characterId"] for r in good if any(c["via"] == "D" for c in r["chains"].values())],
               "chainsUnskinned": {r["characterId"]: [k for k, c in r["chains"].items() if c["via"] == "UNSKINNED"]
                                   for r in good if any(c["via"] == "UNSKINNED" for c in r["chains"].values())},
               "violent": count_meta(good, "violent"), "commercial": count_meta(good, "commercial"),
               "withRootTransforms": [r["characterId"] for r in good if r["rootTransforms"]],
               "missingHumanoid": {r["characterId"]: r["missingHumanoid"] for r in good if r["missingHumanoid"]},
               "duplicateFiles": [v for v in hashes.values() if len(v) > 1],
               "heightM": [min(r["heightM"] for r in good), max(r["heightM"] for r in good)] if good else None,
               "totalMB": round(sum(r.get("bytes", 0) for r in rows) / 1e6, 1)}
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump({"schema": "Tread.M4.VrmInventory.v1", "summary": summary, "rows": rows}, f, ensure_ascii=False, indent=1)
    print("VRM_INVENTORY", json.dumps(summary, ensure_ascii=True)[:1500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
