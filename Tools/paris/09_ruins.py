"""B6 assets and deterministic placement. Run through Tools/ue_run.py; --rebuild regenerates geometry.

Ruin kit (2026-10-03): 13_blender_ruin_kit.py (Blender, via blender-mcp or headless) cuts the BldgLG_J scan into
SM_KB_* pieces under Saved/Staging/ruin_kit; this step imports them like the scan (0.85, MI_KB_*, Nanite) and
placements() dresses ruined courtyards and spills rubble into their streets from a separate random stream, so the
B6 records drawn before the kit keep their exact transforms. --rebuild-kit re-imports the kit FBX files."""
import importlib.util
import json
import math
import os
import random
import sys
import time

import unreal
import paris_common as pc
import ruingen
import ue_mesh
import zones

OUT = pc.MESH + "/Ruins"
SCAN = "SM_CollapsedBuilding_Scan"
REVISION = 2
KIT_DIR = pc.STAGING_DIR + "/ruin_kit"
KIT = ("KB_WingEast", "KB_WingWest", "KB_FacadeFall", "KB_Stub", "KB_RubbleField", "KB_CornerStack")
KIT_Z = 0.1  # m above the court / street surface; the kit keeps the scan's ground at local z = 0
PROTECTED_HALF = 830.0  # m, frozen board furniture margin (11_audit_b6.protected_state uses 830 m)
SCAN_MATERIALS = dict(zip(
    ("assetA", "bricksA", "bricksAdamage", "concreteA", "concreteB", "damageA", "floorA", "floorB",
     "metalFrameA", "metalRustA", "plasterA", "plasterB", "plasterC", "rubbleA", "woodA"),
    ("AssetsA", "BricksA", "BricksADamage", "ConcreteA", "ConcreteB", "DamageA", "FloorA", "FloorB",
     "MetalFrameA", "MetalRustA", "PlasterA", "PlasterB", "PlasterC", "RubbleA", "WoodA")))


def mesh_info(mesh):
    bounds = mesh.get_bounding_box()
    materials = mesh.get_editor_property("static_materials")
    return {"asset": mesh.get_path_name().split(".")[0], "tris": mesh.get_num_triangles(0),
            "bounds_m": [[component / 100.0 for component in (point.x, point.y, point.z)]
                         for point in (bounds.min, bounds.max)],
            "nanite": bool(mesh.get_editor_property("nanite_settings").enabled),
            "materials": [{"slot": str(slot.material_slot_name),
                           "material": slot.material_interface.get_path_name() if slot.material_interface else None}
                          for slot in materials]}


def import_scan(name=SCAN, source=None, reimport=False):
    path = OUT + "/" + name
    if reimport and pc.EAL.does_asset_exist(path):
        pc.EAL.delete_asset(path)
    if not pc.EAL.does_asset_exist(path):
        task = unreal.AssetImportTask()
        task.filename = source or pc.stage(pc.SRC["ruin"], "ruins")
        task.destination_path = OUT
        task.destination_name = name
        task.automated = True
        task.replace_existing = True
        task.save = True
        options = unreal.FbxImportUI()
        options.import_mesh = True
        options.import_as_skeletal = False
        options.import_materials = False
        options.import_textures = False
        options.static_mesh_import_data.import_uniform_scale = 0.85
        options.static_mesh_import_data.combine_meshes = True
        task.options = options
        pc.ASSET_TOOLS.import_asset_tasks([task])
    mesh = pc.load(path)
    for index, slot in enumerate(mesh.get_editor_property("static_materials")):
        suffix = SCAN_MATERIALS[str(slot.material_slot_name)]
        mesh.set_material(index, pc.load(pc.MAT + "/Instances/MI_KB_" + suffix))
    subsystem = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    subsystem.set_nanite_settings(mesh, ue_mesh.nanite_settings(True), True)
    pc.EAL.save_asset(path, only_if_is_dirty=False)
    return mesh


def build_meshes(rebuild=False):
    report_path = pc.REPORT_DIR + "/M0_Ruins.json"
    previous = {}
    if os.path.exists(report_path):
        with open(report_path, encoding="utf-8") as stream:
            previous = json.load(stream)
    rebuild = rebuild or previous.get("revision") != REVISION
    materials = {slot: pc.MAT + "/Instances/" + name for slot, name in ruingen.SLOT_MATERIALS.items()}
    for path in materials.values():
        pc.load(path)
    started = time.time()
    stats = {SCAN: dict(mesh_info(import_scan()), source="BldgLG_J_grp.fbx", import_scale=0.85)}
    kit_report = {}
    if os.path.exists(KIT_DIR + "/ruin_kit.json"):
        with open(KIT_DIR + "/ruin_kit.json", encoding="utf-8") as stream:
            kit_report = json.load(stream)["pieces"]
    for piece in KIT:
        source = KIT_DIR + "/" + piece + ".fbx"
        if not os.path.exists(source):
            raise RuntimeError("missing %s: run 13_blender_ruin_kit.py in Blender first" % source)
        mesh = import_scan("SM_" + piece, source, reimport="--rebuild-kit" in sys.argv)
        stats["SM_" + piece] = dict(mesh_info(mesh), kind="kb_kit", source=piece + ".fbx", import_scale=0.85,
                                    source_tris=kit_report.get(piece, {}).get("tris"))
    for catalog, builder, kind in ((ruingen.LEANING, ruingen.leaning_infill, "leaning"),
                                   (ruingen.FOOTPRINTS, ruingen.footprint, "footprint"),
                                   (ruingen.CRACKS, ruingen.cracked_road, "cracked_road")):
        for name, arguments in catalog.items():
            path = OUT + "/" + name
            if rebuild or not pc.EAL.does_asset_exist(path):
                mesh, unused = ue_mesh.build_static_mesh(path, builder(*arguments), materials, nanite=True)
            else:
                mesh = pc.load(path)
            stats[name] = dict(mesh_info(mesh), kind=kind, arguments=list(arguments))
    spec = importlib.util.spec_from_file_location("b6_hsm", os.path.join(os.path.dirname(__file__), "04_haussmann_modules.py"))
    modules = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modules)
    for name in modules.LOW_MODULES:
        if "Ruin" not in name and "Burnt" not in name:
            continue
        path = modules.OUT + "/" + name
        if rebuild or not pc.EAL.does_asset_exist(path):
            modules.build_module(name, modules.slot_materials())
        stats[name] = dict(mesh_info(pc.load(path)), kind="low_damage")
    report = {"step": "B6", "revision": REVISION, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
              "meshes": stats, "mesh_count": len(stats), "zones": zones.ruin_stats(),
              "elapsed_s": round(time.time() - started, 2)}
    pc.write_json(report_path, report)
    return report


def world_box(bounds, location, yaw, scale):
    """World AABB (m) of a mesh with local `bounds` placed at location / yaw (deg) / uniform scale."""
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    points = [(location[0] + scale * (x * c - y * s), location[1] + scale * (x * s + y * c), location[2] + scale * z)
              for x in (bounds[0][0], bounds[1][0]) for y in (bounds[0][1], bounds[1][1])
              for z in (bounds[0][2], bounds[1][2])]
    return [min(p[i] for p in points) for i in range(3)], [max(p[i] for p in points) for i in range(3)]


def kit_allowed(box):
    """Outside the frozen furniture square and under the B5 south sight ceiling (same formula as 11_audit_b6)."""
    low, high = box
    if not (high[0] < -PROTECTED_HALF or low[0] > PROTECTED_HALF or high[1] < -PROTECTED_HALF or low[1] > PROTECTED_HALF):
        return False
    if high[0] < -800:
        return high[2] <= min(25.0, 0.8 * 1202 * (-800 - high[0]) / 929) - 0.5
    return True


def kit_records(col, row, zone, low, has_scan, kit_bounds):
    """Ruin-kit dressing of one B6 cell: a courtyard piece (unless the scan is there), a frame corner in tall
    cells and rubble / a toppled facade spilling into 1-2 of the cell's streets."""
    generator = random.Random(zones.RUINS_SEED + col * 1009 + row * 7919 + 457)
    center_x, center_y = pc.cell_center(col, row)
    out = []

    def add(piece, local, yaw, scale, role):
        location = [center_x + local[0], center_y + local[1], KIT_Z]
        if kit_allowed(world_box(kit_bounds["SM_" + piece], location, yaw, scale)):
            out.append({"cell": [col, row], "zone": zone, "mesh": "SM_" + piece, "asset": OUT + "/SM_" + piece,
                        "location_m": location, "yaw": yaw, "scale": scale, "role": role})

    if not has_scan:
        piece = generator.choice(("KB_Stub", "KB_RubbleField") if low else ("KB_WingEast", "KB_WingWest", "KB_Stub"))
        add(piece, (generator.uniform(-12, 12), generator.uniform(-12, 12)), 90.0 * generator.randrange(4), 1.0,
            "kit_court")
    if not low and (has_scan or generator.random() < 0.5):
        sx, sy = generator.choice(((1, 1), (1, -1), (-1, 1), (-1, -1)))
        add("KB_CornerStack", (48.0 * sx, 48.0 * sy), 90.0 * generator.randrange(4), 1.0, "kit_corner")
    # streets: +x / -x run along y (long axis yaw 90), +y / -y along x; tall cells keep -y for the leaning infill
    sides = [(1, 0), (-1, 0), (0, 1)] + ([(0, -1)] if low else [])
    for nx, ny in generator.sample(sides, generator.choice((1, 1, 2))):
        along = generator.uniform(-35.0, 35.0)
        local = (88.0 * nx + along * abs(ny), 88.0 * ny + along * abs(nx))
        yaw = (90.0 if nx else 0.0) + 180.0 * generator.randrange(2)
        if generator.random() < 0.5:
            add("KB_FacadeFall", local, yaw, 1.0, "kit_street")
        else:
            add("KB_RubbleField", local, yaw, 0.45, "kit_street")
    return out


def placements(scan_bounds, kit_bounds=None):
    """Mesh records in world metres, using an independent random stream per B6 cell."""
    records = []
    corners_low = (["SM_Hsm_LowLRuin_%02d" % index for index in range(3)] +
                   ["SM_Hsm_LowLBurnt_%02d" % index for index in range(2)])
    corners_tall = ["SM_Hsm_LRuin_%02d" % index for index in range(3)]
    footprint_cells = list(zones.FOOTPRINT_CELLS.values())
    for row in range(pc.CITY_ROWS[0], pc.CITY_ROWS[1] + 1):
        for col in range(pc.CITY_COLS[0], pc.CITY_COLS[1] + 1):
            if 0 <= col < 8 and 0 <= row < 8:
                continue
            zone = zones.cell_zone(col, row)
            if zone not in ("ruins", "ruins_low", "footprint"):
                continue
            center_x, center_y = pc.cell_center(col, row)
            low = zone == "ruins_low" or center_x < -800.0
            generator = random.Random(zones.RUINS_SEED + col * 1009 + row * 7919 + 123)

            def add(name, local=(0.0, 0.0, 0.0), yaw=0.0, scale=1.0, library="Ruins", role=None):
                setback = 15.0 if center_x == -900.0 and library == "Haussmann" else 0.0
                records.append({"cell": [col, row], "zone": zone, "mesh": name,
                                "asset": pc.MESH + "/" + library + "/" + name,
                                "location_m": [center_x + local[0] - setback, center_y + local[1], local[2]],
                                "yaw": yaw, "scale": scale, "role": role or library})

            if zone == "footprint":
                index = footprint_cells.index((col, row))
                add(list(ruingen.FOOTPRINTS)[index], yaw=90.0 * index, role="footprint")
            else:
                for quarter in range(4):
                    yaw = 90.0 * quarter
                    add(generator.choice(corners_low if low else corners_tall), yaw=yaw, library="Haussmann")
                    if low:
                        add("SM_Hsm_LowInfillRuin_%02d" % generator.randrange(2), yaw=yaw, library="Haussmann")
                    elif quarter == 0:
                        add(generator.choice(list(ruingen.LEANING)), yaw=yaw, role="leaning")
                    else:
                        add("SM_Hsm_InfillRuin_%02d" % generator.randrange(2), yaw=yaw, library="Haussmann")
                if generator.random() < 0.4:
                    scale = 0.6 if low else 1.0
                    yaw = 90.0 * generator.randrange(4)
                    offset_x = -(scan_bounds[0][0] + scan_bounds[1][0]) * 0.5 * scale
                    offset_y = -(scan_bounds[0][1] + scan_bounds[1][1]) * 0.5 * scale
                    angle = math.radians(yaw)
                    local = (offset_x * math.cos(angle) - offset_y * math.sin(angle),
                             offset_x * math.sin(angle) + offset_y * math.cos(angle), -scan_bounds[0][2] * scale + 0.2)
                    add(SCAN, local, yaw, scale, role="scan")
            street_y = -100.0 if center_y < -800.0 else 100.0
            add(generator.choice(list(ruingen.CRACKS)), (25.0, street_y, 0.0), role="cracked_road")
            if kit_bounds and zone != "footprint":
                has_scan = any(record["role"] == "scan" and record["cell"] == [col, row] for record in records)
                records.extend(kit_records(col, row, zone, low, has_scan, kit_bounds))
    return records


def apply_layout(ground, back_buildings, low_buildings, industrial_buildings, squares):
    """Replace B6 cells after the original random draws to preserve unaffected blocks."""
    selected = {tuple(cell) for zone in ("ruins", "ruins_low", "footprint") for cell in zones.cells_of(zone)}
    for groups in (ground, back_buildings, low_buildings, industrial_buildings, squares):
        for path, transforms in groups.items():
            groups[path] = [transform for transform in transforms if (
                int(math.floor(transform.translation.y / 20000.0 + 4)),
                int(math.floor(transform.translation.x / 20000.0 + 4))) not in selected]
    for col, row in sorted(selected):
        center_x, center_y = pc.cell_center(col, row)
        ground.setdefault(pc.MESH + "/City/SM_Cell_Court", []).append(pc.xform((center_x, center_y, 0.0)))
    bounds = mesh_info(pc.load(OUT + "/" + SCAN))["bounds_m"]
    kit_bounds = {"SM_" + piece: mesh_info(pc.load(OUT + "/SM_" + piece))["bounds_m"] for piece in KIT}
    records = placements(bounds, kit_bounds)
    groups = {}
    for record in records:
        groups.setdefault(record["asset"], []).append(pc.xform(record["location_m"], record["yaw"], record["scale"]))
    pc.write_json(pc.REPORT_DIR + "/M0_B6_Layout.json", {"zones": zones.ruin_stats(), "instances": records})
    return groups


def clear_furniture(*collections):
    """Clear ruined sidewalks while preserving the frozen board furniture margin."""
    for groups in collections:
        for path, transforms in groups.items():
            keep = []
            for transform in transforms:
                position = transform.translation
                col = int(math.floor(position.y / 20000.0 + 4))
                row = int(math.floor(position.x / 20000.0 + 4))
                protected = abs(position.x) <= 83000 and abs(position.y) <= 83000
                if protected or zones.cell_zone(col, row) not in ("ruins", "ruins_low", "footprint"):
                    keep.append(transform)
            groups[path] = keep


if __name__ == "__main__":
    pc.ensure_map_loaded()
    build_meshes("--rebuild" in sys.argv)
