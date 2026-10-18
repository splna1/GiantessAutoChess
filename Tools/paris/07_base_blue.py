"""B5 blue faction base: Nanite meshes, staged GLB vehicles and lights."""
import math
import os
import sys
import time

import unreal

import bluegen
import geom
import gltf_io
import paris_common as pc
import ue_mesh

STEP = "BaseBlue"
OUT = pc.MESH + "/BaseBlue"
VEHICLE_OUT = OUT
VEHICLE_GLBS = {
    "SM_M1A2_Blue": (pc.STAGING_DIR + "/b5_vehicles/M1A2_Blue.glb", 8.2),
    "SM_ArmoredCar_Blue": (pc.STAGING_DIR + "/b5_vehicles/ArmoredCar_Blue.glb", 7.0),
}


def mats():
    return {slot: pc.MAT + "/Instances/" + name for slot, name in bluegen.SLOT_MATERIALS.items()}


def vehicle_builder(path, target_length):
    """Read a staged GLB, rotate its long horizontal axis to local +x and ground it."""
    g = gltf_io.Gltf(path)
    parts = list(g.triangles(uvs=True))
    if not parts:
        raise RuntimeError("vehicle GLB has no triangles: " + path)
    all_q = [gltf_io.to_geom(p) for _, _, P, _, _, _ in parts for p in P]
    lo = [min(p[k] for p in all_q) for k in range(3)]
    hi = [max(p[k] for p in all_q) for k in range(3)]
    rotate = (hi[1] - lo[1]) > (hi[0] - lo[0])

    def conv(p):
        q = gltf_io.to_geom(p)
        if rotate:
            q = (q[1], -q[0], q[2])
        return q

    Q = [[conv(p) for p in P] for _, _, P, _, _, _ in parts]
    lo = [min(q[k] for part in Q for q in part) for k in range(3)]
    hi = [max(q[k] for part in Q for q in part) for k in range(3)]
    gxs, gys, gzs = hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]
    gz0 = lo[2]
    kept = []
    filtered_parts = []
    for part, qpart in zip(parts, Q):
        xs = [p[0] for p in qpart]
        ys = [p[1] for p in qpart]
        zs = [p[2] for p in qpart]
        xs_span, ys_span, zs_span = max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)
        xy_span = max(xs_span, ys_span)
        is_ground = (zs_span <= 0.01 * xy_span and xs_span >= 0.5 * gxs and
                     ys_span >= 0.5 * gys and max(zs) <= gz0 + 0.1 * gzs)
        if is_ground:
            filtered_parts.append({"index": len(filtered_parts), "name": part[0], "material": part[1],
                                   "triangles": len(part[4]),
                                   "bounds_m": [[round(min(xs), 3), round(min(ys), 3), round(min(zs), 3)],
                                                 [round(max(xs), 3), round(max(ys), 3), round(max(zs), 3)]]})
        else:
            kept.append((part, qpart))
    fit_q = [p for _, qpart in kept for p in qpart]
    if not fit_q:
        raise RuntimeError("vehicle has no renderable triangles after ground-plane filtering: " + path)
    lo = [min(p[k] for p in fit_q) for k in range(3)]
    hi = [max(p[k] for p in fit_q) for k in range(3)]
    span = max(hi[0] - lo[0], hi[1] - lo[1]) or 1.0
    scale = target_length / span
    cx, cy = (lo[0] + hi[0]) * 0.5, (lo[1] + hi[1]) * 0.5
    mb = geom.MeshBuilder(["vehicle"])
    d = mb.data["vehicle"]
    tris = 0
    for (_, _, _P, N, T, UV), qpart in kept:
        base = len(d["p"])
        for i, q in enumerate(qpart):
            q = ((q[0] - cx) * scale, (q[1] - cy) * scale, (q[2] - lo[2]) * scale)
            if N:
                n = gltf_io.to_geom(N[i])
                if rotate:
                    n = (n[1], -n[0], n[2])
                n = geom.norm(n)
            else:
                n = Z = (0.0, 0.0, 1.0)
            uv = UV[i] if UV else geom.auto_uv(q, n)
            d["p"].append(q); d["n"].append(n); d["uv"].append(uv); d["c"].append((1, 1, 1, 1))
        d["t"].extend((base + a, base + b, base + c) for a, b, c in T)
        tris += len(T)
    meta = {"source": path.replace("\\", "/"), "source_parts": len(parts), "source_tris": sum(len(p[4]) for p in parts),
            "mesh_parts": len(kept), "mesh_tris": tris, "ground_plane_filtered": filtered_parts,
            "axis_rotated": rotate, "target_length_m": target_length, "scale": round(scale, 6),
            "bounds_m": [[round(v, 3) for v in b] for b in mb.bounds()]}
    return mb, meta


def build_meshes(rebuild=False):
    m = mats()
    paths = {}
    meta = {}
    n = 0
    t0 = time.time()
    for name, fn in bluegen.MESHES.items():
        if name in bluegen.RUIN_MESHES:
            continue  # built below with the haussmann slot materials
        path = OUT + "/" + name
        if rebuild or not pc.EAL.does_asset_exist(path):
            ue_mesh.build_static_mesh(path, fn(), m, nanite=name not in bluegen.NON_NANITE)
            n += 1
        paths[name] = path

    # B5 ruin meshes (haussmann SLOTS/SLOT_MATERIALS, low=True)
    import haussmann as hm
    ruin_mats = {s: pc.MAT + "/Instances/" + mat for s, mat in hm.SLOT_MATERIALS.items()}
    for name in bluegen.RUIN_MESHES:
        path = OUT + "/" + name
        if rebuild or not pc.EAL.does_asset_exist(path):
            ue_mesh.build_static_mesh(path, bluegen.MESHES[name](), ruin_mats, nanite=True)
            n += 1
        paths[name] = path

    for name, (src, target) in VEHICLE_GLBS.items():
        if not os.path.exists(src):
            raise RuntimeError("staged vehicle missing; run Blender exporter first: " + src)
        path = OUT + "/" + name
        if rebuild or not pc.EAL.does_asset_exist(path):
            mb, info = vehicle_builder(src, target)
            ue_mesh.build_static_mesh(path, mb, {"vehicle": pc.MAT + "/Instances/MI_Paint_BlueBright"}, nanite=True)
            meta[name] = info
            n += 1
        paths[name] = path
    if n:
        unreal.SystemLibrary.execute_console_command(None, "obj gc")
    pc.log("blue meshes built: %d in %.1fs" % (n, time.time() - t0))
    return paths, meta


def path_of(name, extra, paths):
    """Resolve mesh path: lib meshes from pc.MESH/<lib>/<name>, else from paths or OUT."""
    lib = extra.get("lib")
    # B5 ruins are generated into the BaseBlue package, although their
    # layout tag is kept as Blue to distinguish them from City library meshes.
    if lib == "Blue":
        return paths.get(name, OUT + "/" + name)
    if lib:
        return pc.MESH + "/" + lib + "/" + name
    return paths.get(name, OUT + "/" + name)

def groups(paths):
    out = {}
    for name, loc, rot, extra in bluegen.prop_layout():
        path = path_of(name, extra, paths)
        scale = extra.get("scale", 1.0)
        out.setdefault(path, []).append(pc.xform_rot(loc, rot, scale))
    return out


def point_light(loc, label, color=(0.05, 0.22, 1.0), intensity=3200.0, radius=4200.0):
    a = pc.spawn(unreal.PointLight, loc, step_tag=STEP, label=label, folder="BaseBlue/Lights")
    lc = a.point_light_component
    lc.set_editor_property("intensity_units", unreal.LightUnits.CANDELAS)
    lc.set_intensity(intensity)
    lc.set_light_color(unreal.LinearColor(color[0], color[1], color[2], 1.0))
    lc.set_attenuation_radius(radius)
    lc.set_source_radius(20.0)
    lc.set_cast_shadows(False)
    return a


def build_lights():
    pc.clear_step(STEP)
    points = signals = 0
    for _, loc, _rot, extra in bluegen.light_layout():
        lz = extra.get("light_z")
        if extra.get("light") == "signal":
            z = loc[2] + (lz if lz is not None else 5.1)
            point_light((loc[0], loc[1], z), "BaseBlue_Signal_%d_%d" % (loc[0], loc[1]), intensity=2200.0, radius=2400.0)
            signals += 1
        elif extra.get("light") == "point":
            z = loc[2] + (lz if lz is not None else 12.7)
            point_light((loc[0], loc[1], z), "BaseBlue_Tower_%d_%d" % (loc[0], loc[1]), intensity=6500.0, radius=5200.0)
            points += 1
    pc.save_map()
    return {"point_lights": points, "signal_lights": signals}


def main(argv):
    rebuild = "--rebuild" in argv
    pc.ensure_map_loaded()
    paths, meta = build_meshes(rebuild)
    pc.clear_step("CityBaseBlue")
    pc.spawn_instances(groups(paths), "CityBaseBlue", "City_Base_Blue", "City")
    lights = build_lights()
    report = {"step": STEP, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "props": len(bluegen.prop_layout()),
              "defense_line": {"x_m": [-862.0, -838.0], "y_m": [-888.0, 968.0]}, "vehicles": meta, **lights,
              "meshes": sorted(paths.values())}
    pc.write_json(pc.REPORT_DIR + "/M0_Base_Blue.json", report)
    pc.log("base blue: %d props, %d point lights, %d signal lights" % (report["props"], lights["point_lights"], lights["signal_lights"]))


if __name__ == "__main__":
    main(sys.argv[1:])
