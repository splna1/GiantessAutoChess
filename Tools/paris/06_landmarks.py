"""Step 06: landmarks -> /Game/Tread/City/Paris/Landmarks.

Eiffel Tower: the read-only source .glb (SDC PERFORMANCE, CC-BY-4.0, Sketchfab "( FREE ) La tour Eiffel") is
copied to Saved/Staging/eiffel, parsed by gltf_io.py and rebuilt as a Nanite StaticMesh through ue_mesh (same
path as the procedural city, so re-runs overwrite the asset in place). Scaled to EIFFEL_HEIGHT and placed on
the sanded square of the Champ de Mars laid out by 05_city_layout.py.

Notre-Dame (B2): the read-only scan .glb (mohamedhussien, CC-BY-4.0, Sketchfab "Notre Dame De Paris") is a
photogrammetry tile set of the whole east end of the Ile de la Cite at ~2.2x real size, cathedral axis on a diagonal,
no spire (post-2019). notre_dame_builder(): PCA of the upper structure -> rotate the nave axis onto +y with the towers
at -y (west facade), crop to the cathedral footprint + margin, drop the terrain below the parvis level, scale so the
towers are NOTRE_TOWER_H, keep the scan UVs (T_NotreDame_D atlas via MI_NotreDame). Placed on the paved close
(SM_CathedralClose, zones.CATHEDRAL_CELLS) laid out by 05_city_layout.py.

Usage (through Tools/ue_run.py):
    06_landmarks.py [--rebuild] [--only eiffel|notre]     (meshes are rebuilt when missing or with --rebuild;
                                                           both landmarks are re-placed on every run)
"""
import math
import sys
import time

import unreal

import geom
import gltf_io
import paris_common as pc
import ue_mesh

STEP = "Landmarks"
OUT = pc.LANDMARK
EIFFEL_MESH = OUT + "/SM_EiffelTower"
EIFFEL_Z = 0.17  # top of the sanded square (citygen: KERB_H + 0.02)
NOTRE_MESH = OUT + "/SM_NotreDame"
NOTRE_TOWER_H = 90.0  # west-tower height; real = 69 m, raised 1.3x so the skyline reads from Board_Camera (3.2 km away)
NOTRE_POS = (1300.0, -200.0)  # mesh origin = PCA centre of the upper structure; nave spans y -236..-110, parvis to the west
NOTRE_Z = 0.17  # top of the paved close (citygen.cathedral_close: KERB_H + 0.02)
NOTRE_MARGIN = (12.0, 14.0)  # crop margin in scan units (~5-6 m real) across / along the nave axis
NOTRE_MI = pc.MAT + "/Instances/MI_NotreDame"

stage = pc.stage


def eiffel_builder(path, height):
    g = gltf_io.Gltf(path)
    parts = list(g.triangles())
    top = max(p[1] for _, _, P, _, _ in parts for p in P)
    bot = min(p[1] for _, _, P, _, _ in parts for p in P)
    s = height / (top - bot)
    mb = geom.MeshBuilder(["eiffel"])
    d = mb.data["eiffel"]
    for _, _, P, N, T in parts:
        base = len(d["p"])
        if N is None:
            N = [(0.0, 1.0, 0.0)] * len(P)
        for p, n in zip(P, N):
            q = gltf_io.to_geom(p)
            q = (q[0] * s, q[1] * s, (q[2] - bot) * s)
            nn = gltf_io.to_geom(n)
            u = geom.auto_uv(q, nn)
            d["p"].append(q)
            d["n"].append(nn)
            d["uv"].append((u[0] * 0.25, u[1] * 0.25))
            d["c"].append((1.0, 1.0, 1.0, 1.0))
        d["t"].extend((base + a, base + b, base + c) for a, b, c in T)
    meta = {"source_tris": sum(len(t[4]) for t in parts), "source_height_units": round(top - bot, 3), "scale": round(s, 4)}
    return mb, meta


def pca_axis(pts):
    """Principal 2D axis (unit vector) and centroid of [(x, y)]."""
    n = float(len(pts))
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    sxx = sum((p[0] - cx) ** 2 for p in pts) / n
    syy = sum((p[1] - cy) ** 2 for p in pts) / n
    sxy = sum((p[0] - cx) * (p[1] - cy) for p in pts) / n
    tr, det = sxx + syy, sxx * syy - sxy * sxy
    lam = tr / 2.0 + math.sqrt(max(0.0, tr * tr / 4.0 - det))
    v = (lam - syy, sxy) if abs(sxy) > 1e-9 else ((1.0, 0.0) if sxx >= syy else (0.0, 1.0))
    ln = math.hypot(*v)
    return (v[0] / ln, v[1] / ln), (cx, cy)


def notre_dame_builder(path, tower_h, margin=NOTRE_MARGIN):
    """Scan .glb -> cropped, axis-aligned, real-scale cathedral (see module doc). Returns (MeshBuilder, meta)."""
    g = gltf_io.Gltf(path)
    parts = [(P, N, T, UV) for _, _, P, N, T, UV in g.triangles(uvs=True)]
    Q = [[gltf_io.to_geom(p) for p in P] for P, _, _, _ in parts]
    NQ = [[gltf_io.to_geom(n) for n in N] if N else None for _, N, _, _ in parts]
    zmax = max(q[2] for part in Q for q in part)
    zmin = min(q[2] for part in Q for q in part)
    z_upper = zmax - 0.45 * (zmax - zmin)  # everything above the surrounding roofs = the cathedral proper
    upper = [(q[0], q[1]) for part in Q for q in part if q[2] > z_upper]
    axis, (cx, cy) = pca_axis(upper)
    rot = math.pi / 2.0 - math.atan2(axis[1], axis[0])  # nave axis -> +y
    cr, sr = math.cos(rot), math.sin(rot)

    def R(q):
        x, y = q[0] - cx, q[1] - cy
        return (x * cr - y * sr, x * sr + y * cr, q[2])

    def Rn(n):
        return (n[0] * cr - n[1] * sr, n[0] * sr + n[1] * cr, n[2])

    Q = [[R(q) for q in part] for part in Q]
    NQ = [[Rn(n) for n in part] if part else None for part in NQ]
    up = [q for part in Q for q in part if q[2] > z_upper]
    ys = [q[1] for q in up]
    ya, yb = min(ys), max(ys)
    span = yb - ya
    top_s = max(q[2] for q in up if q[1] < ya + 0.3 * span)
    top_n = max(q[2] for q in up if q[1] > yb - 0.3 * span)
    flipped = top_n > top_s  # towers must end up at -y (west facade)
    if flipped:
        Q = [[(-q[0], -q[1], q[2]) for q in part] for part in Q]
        NQ = [[(-n[0], -n[1], n[2]) for n in part] if part else None for part in NQ]
        ya, yb = -yb, -ya
    xs = [q[0] if not flipped else -q[0] for q in up]
    xa, xb = min(xs), max(xs)
    mx, my = margin
    box = (xa - mx, xb + mx, ya - my, yb + my)
    zs_in = sorted(q[2] for part in Q for q in part if xa <= q[0] <= xb and ya <= q[1] <= yb)
    ground = zs_in[int(len(zs_in) * 0.05)]  # parvis level: 5th percentile inside the tight footprint
    s = tower_h / (zmax - ground)
    mb = geom.MeshBuilder(["nd"])
    d = mb.data["nd"]
    kept = src = 0
    for (P, N, T, UV), q, nq in zip(parts, Q, NQ):
        src += len(T)
        keep = []
        for a, b, c in T:
            gx = (q[a][0] + q[b][0] + q[c][0]) / 3.0
            gy = (q[a][1] + q[b][1] + q[c][1]) / 3.0
            gz = (q[a][2] + q[b][2] + q[c][2]) / 3.0
            if box[0] <= gx <= box[1] and box[2] <= gy <= box[3] and gz > ground - 3.0:
                keep.append((a, b, c))
        if not keep:
            continue
        used = sorted({i for t in keep for i in t})
        remap = {i: k for k, i in enumerate(used)}
        base = len(d["p"])
        for i in used:
            x, y, z = q[i]
            d["p"].append((x * s, y * s, (z - ground) * s))
            d["n"].append(nq[i] if nq else (0.0, 0.0, 1.0))
            d["uv"].append(UV[i] if UV else (0.0, 0.0))
            d["c"].append((1.0, 1.0, 1.0, 1.0))
        d["t"].extend((base + remap[a], base + remap[b], base + remap[c]) for a, b, c in keep)
        kept += len(keep)
    meta = {"source_tris": src, "kept_tris": kept, "scale": round(s, 4), "axis_rotation_deg": round(math.degrees(rot) + (180.0 if flipped else 0.0), 2),
            "ground_source_z": round(ground, 2), "source_top_z": round(zmax, 2),
            "footprint_m": [round((xb - xa) * s, 1), round((yb - ya) * s, 1)], "crop_box_m": [round(v * s, 1) for v in box]}
    return mb, meta


def main(argv):
    rebuild = "--rebuild" in argv
    only = [argv[i + 1] for i, a in enumerate(argv) if a == "--only"]
    want = lambda k: not only or k in only  # noqa: E731
    pc.ensure_map_loaded()
    pc.ensure_dir(OUT)
    report = {"step": STEP, "time": time.strftime("%Y-%m-%d %H:%M:%S")}

    # ---------------------------------------------------------------- Eiffel Tower
    staged = stage(pc.SRC["eiffel"], "eiffel")
    info = {"source": pc.SRC["eiffel"], "staged": staged.replace("\\", "/"), "asset": EIFFEL_MESH,
            "credit": "( FREE ) La tour Eiffel by SDC PERFORMANCE (https://sketchfab.com/Lambo_SC04), CC-BY-4.0",
            "height_m": pc.EIFFEL_HEIGHT, "position_m": [pc.EIFFEL_POS[0], pc.EIFFEL_POS[1], EIFFEL_Z]}
    if want("eiffel") and (rebuild or not pc.EAL.does_asset_exist(EIFFEL_MESH)):
        mb, meta = eiffel_builder(staged, pc.EIFFEL_HEIGHT)
        _, stats = ue_mesh.build_static_mesh(EIFFEL_MESH, mb, {"eiffel": pc.MAT + "/Instances/MI_Paint_Eiffel"}, nanite=True)
        info.update(meta)
        info["mesh"] = stats
        unreal.SystemLibrary.execute_console_command(None, "obj gc")
    sm = pc.load(EIFFEL_MESH)
    info["nanite_enabled"] = bool(sm.get_editor_property("nanite_settings").get_editor_property("enabled"))
    b = sm.get_bounding_box()
    info["bounds_m"] = [[round(b.min.x / 100, 2), round(b.min.y / 100, 2), round(b.min.z / 100, 2)],
                        [round(b.max.x / 100, 2), round(b.max.y / 100, 2), round(b.max.z / 100, 2)]]
    report["eiffel"] = info

    # ---------------------------------------------------------------- Notre-Dame (B2)
    staged_nd = stage(pc.SRC["notre_dame"], "notre_dame")
    nd = {"source": pc.SRC["notre_dame"], "staged": staged_nd, "asset": NOTRE_MESH,
          "credit": "Notre Dame De Paris by mohamedhussien (https://sketchfab.com/mohamedhussien), CC-BY-4.0",
          "tower_height_m": NOTRE_TOWER_H, "position_m": [NOTRE_POS[0], NOTRE_POS[1], NOTRE_Z], "material": NOTRE_MI,
          "texture": pc.TEX + "/T_NotreDame_D"}
    if want("notre") and (rebuild or not pc.EAL.does_asset_exist(NOTRE_MESH)):
        t0 = time.time()
        mb, meta = notre_dame_builder(staged_nd, NOTRE_TOWER_H)
        meta["convert_seconds"] = round(time.time() - t0, 1)
        _, stats = ue_mesh.build_static_mesh(NOTRE_MESH, mb, {"nd": NOTRE_MI}, nanite=True)
        nd.update(meta)
        nd["mesh"] = stats
        unreal.SystemLibrary.execute_console_command(None, "obj gc")
    smn = pc.load(NOTRE_MESH)
    nd["nanite_enabled"] = bool(smn.get_editor_property("nanite_settings").get_editor_property("enabled"))
    b = smn.get_bounding_box()
    nd["bounds_m"] = [[round(b.min.x / 100, 2), round(b.min.y / 100, 2), round(b.min.z / 100, 2)],
                      [round(b.max.x / 100, 2), round(b.max.y / 100, 2), round(b.max.z / 100, 2)]]
    report["notre_dame"] = nd

    pc.clear_step(STEP)
    n = pc.spawn_mesh(smn, (NOTRE_POS[0], NOTRE_POS[1], NOTRE_Z), step_tag=STEP, label="Notre_Dame", folder="Landmarks")
    n.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    t = pc.spawn_mesh(sm, (pc.EIFFEL_POS[0], pc.EIFFEL_POS[1], EIFFEL_Z), step_tag=STEP, label="Eiffel_Tower", folder="Landmarks")
    t.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    # aviation beacon on the antenna + warm floodlight at the base so the lattice reads through the haze
    top = info["bounds_m"][1][2]
    beacon = pc.spawn(unreal.PointLight, (pc.EIFFEL_POS[0], pc.EIFFEL_POS[1], EIFFEL_Z + top + 1.5), step_tag=STEP, label="Eiffel_Beacon", folder="Landmarks")
    lc = beacon.point_light_component
    lc.set_intensity(80.0)
    lc.set_editor_property("intensity_units", unreal.LightUnits.CANDELAS)
    lc.set_light_color(unreal.LinearColor(1.0, 0.12, 0.05, 1.0))
    lc.set_attenuation_radius(6000.0)
    lc.set_cast_shadows(False)

    pc.save_map()
    pc.write_json(pc.REPORT_DIR + "/M0_Landmarks.json", report)
    pc.log("landmarks placed:", EIFFEL_MESH, info["bounds_m"], NOTRE_MESH, nd["bounds_m"])


main(sys.argv[1:])
