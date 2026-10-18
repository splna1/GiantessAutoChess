"""Destruction perf trial (editor-side, PIE): implements the 126 plan's state swap for the middle 4x8 cells of the board
and lets the battle presenter measure the frame rate (Tools/destruction/README.md has the numbers).

The trial only uses what the map already has: the board's InstancedStaticMesh components and the ruin / burnt variants
that ship with the Paris kit. It hides the intact instance (scale -> 0.01, the cheapest per-instance "remove" an ISM
allows), puts a ruin variant of the same family in its place, and can scatter extra ruin instances as debris stand-ins.
No assets, no map edits: every change lives in the PIE world and dies with the session.

    python Tools/ue_run.py Tools/destruction/destruction_trial.py band
    python Tools/ue_run.py Tools/destruction/destruction_trial.py destroy ruins
    python Tools/ue_run.py Tools/destruction/destruction_trial.py destroy ruins_debris

Phases are separate remote calls (memory: tread-editor-python-map-switch).
"""
import json
import os
import random
import sys

import unreal

BAND_X_M = 300.0   # middle 4 rows of the 8x8 board: rows 2..5 -> |world X| <= 300 m
BAND_Y_M = 700.0   # all 8 columns -> |world Y| <= 700 m
HIDE_SCALE = 0.01
SEED = 20261017

# Intact family -> ruin / burnt family already in the level (same Paris kit, similar footprint).
RUIN_FOR = {
    "SM_Hsm_L_": ["SM_Hsm_LRuin_00", "SM_Hsm_LRuin_01", "SM_Hsm_LRuin_02"],
    "SM_Hsm_LBurnt_": ["SM_Hsm_LRuin_00", "SM_Hsm_LRuin_01"],
    "SM_Hsm_Infill_": ["SM_Hsm_InfillRuin_00", "SM_Hsm_InfillRuin_01"],
    "SM_Hsm_InfillBurnt_": ["SM_Hsm_InfillRuin_00", "SM_Hsm_InfillRuin_01"],
}
LIBRARY_RUIN = ["SM_Hsm_LRuin_00", "SM_Hsm_LRuin_01"]

_state = {"hidden": [], "added": []}


def pie_world():
    sub = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world = sub.get_game_world() if sub else None
    if not world:
        for candidate in unreal.EditorLevelLibrary.get_pie_worlds(False) or []:
            if candidate:
                return candidate
    return world


def scene():
    """The PIE copies of the board actors. Never the editor world: this trial must not touch the saved map."""
    world = pie_world()
    if not world:
        raise RuntimeError("no PIE world; start PIE first (this trial must never run on the saved map)")
    books, libraries = None, None
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor):
        label = actor.get_actor_label()
        if label == "City_Board_Buildings":
            books = actor
        elif label == "M3_Board_LibraryBlocks":
            libraries = actor
    if not books:
        raise RuntimeError("City_Board_Buildings missing in the PIE world")
    return world, books, libraries


def in_band(translation):
    return abs(translation.x / 100.0) <= BAND_X_M and abs(translation.y / 100.0) <= BAND_Y_M


def components(actor):
    if not actor:
        return []
    return list(actor.get_components_by_class(unreal.InstancedStaticMeshComponent))


def mesh_name(comp):
    mesh = comp.get_editor_property("static_mesh")
    return mesh.get_name() if mesh else ""


def band_instances(books, libraries):
    """[(component, index, world transform, mesh name)] for every board building inside the middle 4x8 band."""
    rows = []
    for actor in (books, libraries):
        for comp in components(actor):
            name = mesh_name(comp)
            for index in range(comp.get_instance_count()):
                transform = comp.get_instance_transform(index, True)
                if in_band(transform.translation):
                    rows.append((comp, index, transform, name))
    rows.sort(key=lambda r: (round(r[2].translation.x, 1), round(r[2].translation.y, 1), r[3]))
    return rows


def ruin_component(books, mesh):
    for comp in components(books):
        if mesh_name(comp) == mesh:
            return comp
    return None


def ruin_mesh_for(name):
    for prefix, options in RUIN_FOR.items():
        if name.startswith(prefix):
            return options
    return LIBRARY_RUIN


def phase_band():
    world, books, libraries = scene()
    rows = band_instances(books, libraries)
    by_mesh = {}
    for _, _, _, name in rows:
        by_mesh[name] = by_mesh.get(name, 0) + 1
    print("BAND instances=%d meshes=%s" % (len(rows), json.dumps(by_mesh, ensure_ascii=False, sort_keys=True)))


def fit_scale(intact, ruin):
    """Scale factor that gives the small ruin chunk the footprint of the building it replaces.

    The kit's ruin meshes are fragments (a 24 m Haussmann module dropped in as-is is a few metres of rubble), so the
    stand-in is scaled up to the intact footprint. Without this the trial quietly renders a fraction of the geometry a
    real destroyed state has and the frame rate would flatter the plan.
    """
    if not intact or not ruin:
        return 1.0
    a = intact.get_bounds().box_extent
    b = ruin.get_bounds().box_extent
    have = max(b.x, b.y)
    if have <= 1.0:
        return 1.0
    return float(min(max(max(a.x, a.y) / have, 1.0), 12.0))


def phase_destroy(mode):
    """mode 'ruins': swap every band building to a ruin instance. 'ruins_debris': also scatter 3 debris instances each."""
    world, books, libraries = scene()
    rows = band_instances(books, libraries)
    rnd = random.Random(SEED)
    debris = 3 if mode == "ruins_debris" else 0
    swapped = 0
    scattered = 0
    for comp, index, transform, name in rows:
        options = ruin_mesh_for(name)
        ruin = ruin_component(books, options[swapped % len(options)])
        if not ruin:
            continue
        # Hide the intact instance: keep its pose, shrink it out of sight (ISM has no per-instance visibility).
        hidden = transform.copy()  # struct wrapper aliases: mutating it would scale the source transform too
        hidden.scale3d = transform.scale3d * HIDE_SCALE
        comp.update_instance_transform(index, hidden, True)
        _state["hidden"].append((comp, index, transform))
        # Stand-in ruin at the same pose, scaled up to the building footprint.
        factor = fit_scale(comp.get_editor_property("static_mesh"), ruin.get_editor_property("static_mesh"))
        pose = transform.copy()
        pose.scale3d = transform.scale3d * factor
        ruin.add_instance_world_space(pose)
        _state["added"].append(ruin)
        swapped += 1
        for _ in range(debris):
            piece = ruin_component(books, rnd.choice(options))
            if not piece:
                continue
            offset = unreal.Vector(rnd.uniform(-25.0, 25.0) * 100.0, rnd.uniform(-25.0, 25.0) * 100.0, 0.0)
            yaw = unreal.Rotator(roll=0.0, pitch=0.0, yaw=rnd.uniform(0.0, 360.0))
            pose = unreal.Transform(transform.translation + offset, yaw,
                                    transform.scale3d * factor * rnd.uniform(0.25, 0.55))
            piece.add_instance_world_space(pose)
            _state["added"].append(piece)
            scattered += 1
    print("DESTROY mode=%s swapped=%d debris=%d" % (mode, swapped, scattered))


def phase_chunks():
    """Real chunk meshes (Tools/destruction/build_chunk_meshes.py): every band building becomes its pre-cut pieces.

    An ISM component cannot be created from Python at runtime, so the trial reuses existing ones as chunk hosts: their
    mesh is swapped for a chunk mesh and their instances cleared. Hosts are picked from the already-damaged families
    first (their few instances are rubble / burnt variants), then from the library block actor.
    """
    world, books, libraries = scene()
    path = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()), "Saved", "Reports",
                        "Destruction_Chunks.json")
    if not os.path.exists(path):
        raise RuntimeError("missing %s; run Tools/destruction/build_chunk_meshes.py first" % path)
    doc = json.load(open(path, encoding="utf-8"))
    chunks = []
    for record in doc["chunks"]:
        mesh = unreal.load_asset(record["asset"])
        if mesh:
            chunks.append((record["asset"], mesh, record["offset_m"]))
    if not chunks:
        raise RuntimeError("no chunk assets in %s" % path)

    # Scan the band BEFORE the hosts are cleared: some of the target buildings live on the host components.
    rows = band_instances(books, libraries)
    damaged = ("SM_Hsm_LRuin_", "SM_Hsm_InfillRuin_", "SM_Hsm_LBurnt_", "SM_Hsm_InfillBurnt_")
    pool = [c for c in components(books) if mesh_name(c).startswith(damaged)]
    pool += [c for c in components(libraries)]
    if len(pool) < len(chunks):
        raise RuntimeError("need %d host components, have %d" % (len(chunks), len(pool)))
    hosts = pool[:len(chunks)]
    for host, (asset, mesh, _) in zip(hosts, chunks):
        host.clear_instances()
        host.set_static_mesh(mesh)

    for comp, index, transform, name in rows:
        hidden = transform.copy()  # struct wrapper aliases: mutating it would scale the source transform too
        hidden.scale3d = transform.scale3d * HIDE_SCALE
        comp.update_instance_transform(index, hidden, True)
        _state["hidden"].append((comp, index, transform))
        for host, (_, _, offset) in zip(hosts, chunks):
            local = unreal.Transform(unreal.Vector(offset[0] * 100.0, offset[1] * 100.0, offset[2] * 100.0),
                                     unreal.Rotator(), unreal.Vector(1.0, 1.0, 1.0))
            host.add_instance_world_space(transform.multiply(local))
            _state["added"].append(host)
    print("CHUNKS buildings=%d chunks_per_building=%d instances=%d tris_per_building=%d" %
          (len(rows), len(chunks), len(rows) * len(chunks), doc.get("source_triangles", 0)))


def main():
    args = sys.argv[1:]
    name = args[0] if args else "band"
    if name == "band":
        phase_band()
    elif name == "chunks":
        phase_chunks()
    elif name == "destroy":
        phase_destroy(args[1] if len(args) > 1 else "ruins")
    else:
        raise RuntimeError("phase must be band|chunks|destroy")


main()
