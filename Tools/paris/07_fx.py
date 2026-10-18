"""Step 07: battlefield FX -> /Game/Tread/City/Paris/FX + level actors tagged FX.

Everything is anchored on the damaged Haussmann modules actually placed by 05_city_layout.py: the burnt / ruined
instances are read back from the "City_Board_Buildings" / "City_Back_Buildings" ISMs, so re-running 05 with a
different seed moves the fires with the buildings. Random streams are separate per stage (board fires + plumes 707,
backfield plumes 7071, scorch decals 7073, north plumes 7072) so a backfield change cannot move the board's FX.

    fire      crossed flame cards (M_FX_Fire, non-Nanite: translucent/additive) on the open roofs of burnt lots and
              on the rubble of collapsed lots, one warm point light per site (no shadows), glowing ember beds
              (MI_Ember) under the ruin fires
    smoke     Local Fog Volumes stacked into leaning plumes (volumetric, lit by the sun and the sky, cheap) - one
              plume per damaged board cell, a few taller ones in the backfield for depth, plus a thin ground haze
              over the two damage clusters. Wind blows north-east, away from the camera, so the board stays readable.
    scorch    deferred decals (M_Decal_Scorch) on the streets and sidewalks around the damaged cells
    north     (B2) 4 columns over the red base (burning supply dumps, small fire + light each) and 4 over the low-rise
              district roofs; all outside the cathedral's y band so the skyline stays readable, drifting north-east

LFV notes (measured in UE 5.8): the unit sphere is ~5 m in radius at actor scale 1, and a volume whose height-fog
extinction is exactly 0 is culled entirely -> keep it at a tiny positive value when only radial fog is wanted.

Usage (through Tools/ue_run.py):
    07_fx.py [--rebuild]        --rebuild regenerates the FX meshes
"""
import math
import json
import random
import sys
import time

import unreal

import geom
import paris_common as pc
import ue_mesh
import zones

STEP = "FX"
OUT = pc.FX
FLAME_MESH = OUT + "/SM_FX_FlameCards"
EMBER_MESH = OUT + "/SM_FX_EmberBed"
FIRE_MAT = pc.MAT + "/M_FX_Fire"
SCORCH_MAT = pc.MAT + "/M_Decal_Scorch"
EMBER_MI = pc.MAT + "/Instances/MI_Ember"

LFV_UNIT = 5.0  # m, LocalFogVolume unit-sphere radius at scale 1
WIND = (0.30, 0.22)  # plume drift (m) per metre of rise: north-east, away from the board camera
ROOF_Z = 18.5  # open roof of a burnt 5-storey lot (ground 5 m + 4-5 floors)
LOW_ROOF_Z = 13.0  # roof of a low-rise lot (B2 district, <= 18 m)
NORTH_KEEP_OUT_Y = (-450.0, 50.0)  # cathedral close + margin: no north plume starts in this band
RUBBLE_Z = 2.5
MAX_LIGHTS = 18

# fire sites in the block-local frame of a module placed at yaw 0 (haussmann.py: the L piece fills the SW corner,
# the infill closes the south side); the building band is 65..81 m from the block centre
L_SITES = [(-73.0, -73.0), (-73.0, -38.0), (-38.0, -73.0)]
I_SITES = [(-73.0, 0.0)]


# ---------------------------------------------------------------- meshes
def flame_cards():
    """3 crossed double-sided quads, 1 m tall (base at z 0), 0.55 m wide; V = 1 at the base (T_FlameTongue)."""
    mb = geom.MeshBuilder(["flame"])
    w = 0.275
    for k in range(3):
        a = math.radians(60.0 * k)
        dx, dy = math.cos(a) * w, math.sin(a) * w
        n = (-math.sin(a), math.cos(a), 0.0)
        pts = [(-dx, -dy, 0.0), (dx, dy, 0.0), (dx, dy, 1.0), (-dx, -dy, 1.0)]
        uvs = [(0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0)]
        mb.poly("flame", pts, n, uvs)
        mb.poly("flame", pts, geom.mul(n, -1.0), uvs)
    return mb


def ember_bed(seed=3):
    """Glowing coals: ~70 small tilted blocks scattered over a 1 m radius disc (scaled per site)."""
    mb = geom.MeshBuilder(["ember"])
    r = random.Random(seed)
    for _ in range(70):
        d = math.sqrt(r.random()) * 1.0
        a = r.uniform(0, 2 * math.pi)
        c = (d * math.cos(a), d * math.sin(a), r.uniform(0.0, 0.05))
        yaw, tilt = r.uniform(0, 2 * math.pi), r.uniform(-0.5, 0.5)
        ax = (math.cos(yaw), math.sin(yaw), 0.0)
        ay = geom.norm((-math.sin(yaw), math.cos(yaw), tilt))
        az = geom.norm(geom.cross(ax, ay))
        s = r.uniform(0.02, 0.07) * (1.3 - 0.6 * d)
        mb.obox("ember", c, ax, ay, az, s * r.uniform(0.8, 1.6), s, s * r.uniform(0.5, 1.0), skip=("nz",))
    return mb


def build_meshes(rebuild):
    pc.ensure_dir(OUT)
    fire = pc.load(FIRE_MAT)
    # flame cards are drawn as instanced static meshes
    unreal.MaterialEditingLibrary.set_base_material_usage(fire, unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
    pc.EAL.save_asset(FIRE_MAT, only_if_is_dirty=True)
    stats = {}
    if rebuild or not pc.EAL.does_asset_exist(FLAME_MESH):
        _, stats["flame"] = ue_mesh.build_static_mesh(FLAME_MESH, flame_cards(), {"flame": FIRE_MAT}, nanite=False)
    if rebuild or not pc.EAL.does_asset_exist(EMBER_MESH):
        _, stats["ember"] = ue_mesh.build_static_mesh(EMBER_MESH, ember_bed(), {"ember": EMBER_MI}, nanite=True)
    return stats


# ---------------------------------------------------------------- damaged modules -> fire sites
def find_actor(label):
    for a in pc.actor_sub().get_all_level_actors():
        if a.get_actor_label() == label:
            return a
    return None


def damaged_instances(label):
    """[(kind 'burnt'|'ruin', piece 'l'|'infill', loc (m), yaw deg)] of the damaged modules held by actor `label`."""
    a = find_actor(label)
    out = []
    if a is None:
        return out
    for comp in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = comp.get_editor_property("static_mesh")
        name = sm.get_name() if sm else ""
        kind = "ruin" if "Ruin" in name else "burnt" if "Burnt" in name else None
        if kind is None:
            continue
        piece = "infill" if "Infill" in name else "l"
        for i in range(comp.get_instance_count()):
            t = comp.get_instance_transform(i, True)
            if isinstance(t, tuple):
                t = t[-1]
            if t is None:
                continue
            p = t.translation
            out.append((kind, piece, (p.x / pc.M, p.y / pc.M, p.z / pc.M), t.rotation.rotator().yaw))
    return out


def to_world(loc, yaw, local):
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    return (loc[0] + local[0] * c - local[1] * s, loc[1] + local[0] * s + local[1] * c)


def cell_of(x, y):
    return (int(math.floor(y / pc.CELL + pc.N / 2.0)), int(math.floor(x / pc.CELL + pc.N / 2.0)))


def fire_sites(rnd):
    """Board fires on every damaged module of the damage cells (ruins: ground fires, burnt: roof fires)."""
    sites = []
    for kind, piece, loc, yaw in damaged_instances("City_Board_Buildings"):
        cell = cell_of(loc[0], loc[1])
        if cell not in pc.DAMAGE_CELLS:
            continue  # a lone burnt-out shell next to the battle: soot only, no live fire
        cand = L_SITES if piece == "l" else I_SITES
        n = 1 if piece == "infill" else (2 if kind == "ruin" and rnd.random() < 0.5 else 1)
        if kind == "burnt" and rnd.random() < 0.35:
            continue  # burnt out, already cold
        for local in rnd.sample(cand, min(n, len(cand))):
            x, y = to_world(loc, yaw, local)
            x += rnd.uniform(-4, 4)
            y += rnd.uniform(-4, 4)
            ruin = kind == "ruin"
            sites.append({"cell": cell, "kind": kind, "x": x, "y": y, "z": RUBBLE_Z if ruin else ROOF_Z,
                          "size": rnd.uniform(1.1, 1.5) if ruin else rnd.uniform(0.7, 1.1)})
    return sites


def back_plume_sites(rnd, count=3):
    """Distant burning blocks in the backfield (depth cue beyond the board), spread across the view."""
    cands = []
    for kind, piece, loc, yaw in damaged_instances("City_Back_Buildings"):
        if 1300.0 < loc[0] < 2700.0 and -1300.0 < loc[1] < 2600.0 and abs(loc[1] - 1100.0) > 150.0:
            x, y = to_world(loc, yaw, L_SITES[0] if piece == "l" else I_SITES[0])
            cands.append((x, y))
    rnd.shuffle(cands)
    picked = []
    for c in cands:
        if all(math.hypot(c[0] - p[0], c[1] - p[1]) > 900.0 for p in picked):
            picked.append(c)
        if len(picked) >= count:
            break
    return picked


def north_plume_sites(rnd, n_base=4, n_low=4):
    """B2: [(tag 'base'|'low', x, y)] plume anchors over the red base and the low-rise district (x 1500..2300 m),
    spread out and clear of the cathedral band so the Notre-Dame skyline stays readable from the board camera."""
    picks = []
    for tag, cells, n, spread in (("base", zones.cells_of("base_red"), n_base, 300.0),
                                  ("low", [c for c in zones.cells_of("low") if 1500.0 <= pc.cell_center(*c)[0] <= 2300.0], n_low, 450.0)):
        cands = [c for c in cells if not (NORTH_KEEP_OUT_Y[0] < pc.cell_center(*c)[1] < NORTH_KEEP_OUT_Y[1])]
        rnd.shuffle(cands)
        chosen = []
        for c in cands:
            x, y = pc.cell_center(*c)
            if all(math.hypot(x - px, y - py) > spread for _, px, py in chosen):
                chosen.append((tag, x + rnd.uniform(-45.0, 45.0), y + rnd.uniform(-45.0, 45.0)))
            if len(chosen) >= n:
                break
        picks += chosen
    return picks


# ---------------------------------------------------------------- smoke (Local Fog Volumes)
def fog_volume(label, loc, scale, radial, albedo, emissive=None, yaw=0.0, phase=0.35):
    a = pc.spawn(unreal.LocalFogVolume, loc, (0.0, yaw, 0.0), step_tag=STEP, label=label, folder="FX/Smoke")
    a.set_actor_scale3d(unreal.Vector(*[s / LFV_UNIT for s in scale]))
    c = a.get_component_by_class(unreal.LocalFogVolumeComponent)
    c.set_radial_fog_extinction(radial)
    c.set_height_fog_extinction(0.01)  # 0 would cull the volume (see module doc)
    c.set_fog_albedo(unreal.LinearColor(albedo[0], albedo[1], albedo[2], 1.0))
    if emissive:
        c.set_fog_emissive(unreal.LinearColor(emissive[0], emissive[1], emissive[2], 1.0))
    c.set_fog_phase_g(phase)
    return a


def plume(name, x, y, z0, rnd, n=8, h=240.0, r0=14.0, r1=70.0, e0=1.3, e1=0.3, glow=1.0):
    """A leaning smoke column: n stacked, jittered ellipsoids, denser/darker/narrower at the base."""
    for i in range(n):
        t = i / (n - 1.0)
        hz = z0 + (t ** 1.15) * h
        r = r0 + (t ** 0.9) * (r1 - r0)
        px = x + WIND[0] * (hz - z0) + rnd.uniform(-0.25, 0.25) * r
        py = y + WIND[1] * (hz - z0) + rnd.uniform(-0.25, 0.25) * r
        g = 0.10 + 0.22 * t
        emi = None
        if i < 2 and glow > 0.0:  # fire-lit underside of the column
            k = glow * (0.5 if i == 0 else 0.15)
            emi = (0.9 * k, 0.28 * k, 0.05 * k)
        fog_volume("%s_%02d" % (name, i), (px, py, hz), (r * rnd.uniform(0.9, 1.15), r * rnd.uniform(0.9, 1.15), r * 0.75),
                   e0 + (e1 - e0) * t, (g, g * 0.96, g * 0.92), emi, yaw=rnd.uniform(0, 360))
    return n


# ---------------------------------------------------------------- fire, embers, lights, decals
def place_fires(sites, rnd):
    flames, embers = {}, {}
    for s in sites:
        k = 5 if s["kind"] == "ruin" else 3
        for j in range(k):
            h = s["size"] * rnd.uniform(9.0, 17.0) * (1.0 if j else 1.3)
            loc = (s["x"] + rnd.uniform(-5, 5) * s["size"], s["y"] + rnd.uniform(-5, 5) * s["size"], s["z"] - 0.5)
            w = h * rnd.uniform(0.8, 1.2)
            flames.setdefault(FLAME_MESH, []).append(pc.xform(loc, rnd.uniform(0, 360), (w, w, h)))
        if s["kind"] == "ruin":
            embers.setdefault(EMBER_MESH, []).append(pc.xform((s["x"], s["y"], 0.2), rnd.uniform(0, 360), rnd.uniform(9.0, 13.0)))
    if flames:
        pc.spawn_instances(flames, STEP, "FX_Flames", "FX/Fire", shadows=False)
    if embers:
        pc.spawn_instances(embers, STEP, "FX_Embers", "FX/Fire", shadows=False)
    # one light per site, strongest sites first
    lights = 0
    for i, s in enumerate(sorted(sites, key=lambda q: -q["size"])[:MAX_LIGHTS]):
        l = pc.spawn(unreal.PointLight, (s["x"], s["y"], s["z"] + 6.0), step_tag=STEP, label="FX_FireLight_%02d" % i, folder="FX/Fire")
        lc = l.point_light_component
        lc.set_editor_property("intensity_units", unreal.LightUnits.CANDELAS)
        lc.set_intensity(9000.0 * s["size"])
        lc.set_light_color(unreal.LinearColor(1.0, 0.42, 0.12, 1.0))
        lc.set_attenuation_radius(12000.0)
        lc.set_source_radius(300.0)
        lc.set_cast_shadows(False)
        lights += 1
    return sum(len(t) for t in flames.values()), sum(len(t) for t in embers.values()), lights


def place_scorch(rnd):
    mat = pc.load(SCORCH_MAT)
    n = 0
    for (c, r) in sorted(pc.DAMAGE_CELLS):
        x, y = pc.cell_center(c, r)
        spots = [(x + 100.0, y + rnd.uniform(-60, 60)), (x - 100.0, y + rnd.uniform(-60, 60)),
                 (x + rnd.uniform(-60, 60), y + 100.0), (x + rnd.uniform(-60, 60), y - 100.0),
                 (x + rnd.uniform(-40, 40), y + rnd.uniform(-40, 40))]  # 4 street edges + the courtyard
        for sx, sy in spots:
            size = rnd.uniform(30.0, 55.0)
            d = pc.spawn(unreal.DecalActor, (sx, sy, 0.0), (-90.0, rnd.uniform(0, 360), 0.0), step_tag=STEP,
                         label="FX_Scorch_%02d" % n, folder="FX/Scorch")
            d.set_decal_material(mat)
            dc = d.decal
            dc.set_editor_property("decal_size", unreal.Vector(600.0, size * 50.0, size * 50.0))  # half extents (cm)
            dc.set_editor_property("sort_order", 1)
            n += 1
    return n


def place_ruins_fx():
    """Read placed ruined corners and add a small, independently seeded outer-ring fire pass."""
    global STEP
    original_step = STEP
    STEP = "RuinsFX"
    try:
        pc.clear_step(STEP)
        build_meshes(False)
        generator = random.Random(7076)
        candidates = []
        for kind, piece, location, yaw in damaged_instances("City_Ruins"):
            if kind != "ruin" or piece != "l" or location[0] < 800:
                continue
            anchor_x, anchor_y = to_world(location, yaw, L_SITES[0])
            if -450 < anchor_y < 50:
                continue
            candidates.append((anchor_x, anchor_y))
        generator.shuffle(candidates)
        sites = []
        for anchor_x, anchor_y in candidates:
            if all(math.hypot(anchor_x - site[0], anchor_y - site[1]) > 500 for site in sites):
                sites.append((anchor_x, anchor_y))
            if len(sites) == 8:
                break
        flames = {}
        volumes = 0
        for index, (anchor_x, anchor_y) in enumerate(sites):
            for unused in range(3):
                height = generator.uniform(4.0, 7.0)
                flames.setdefault(FLAME_MESH, []).append(pc.xform(
                    (anchor_x + generator.uniform(-2, 2), anchor_y + generator.uniform(-2, 2), 2.0),
                    generator.uniform(0, 360), (height, height, height)))
            volumes += plume("FX_B6_Smoke_%d" % index, anchor_x, anchor_y, 4.0, generator,
                             n=5, h=90.0, r0=5.0, r1=25.0, e0=0.7, e1=0.12, glow=0.5)
        if flames:
            pc.spawn_instances(flames, STEP, "FX_B6_Flames", "FX/Fire", shadows=False)
        report = {"source_actor": "City_Ruins", "sites_m": sites, "smoke_plumes": len(sites),
                  "local_fog_volumes": volumes, "flame_instances": sum(len(items) for items in flames.values())}
        pc.write_json(pc.REPORT_DIR + "/M0_B6_FX.json", report)
        return report
    finally:
        STEP = original_step


# ---------------------------------------------------------------- main
def main(argv):
    rebuild = "--rebuild" in argv
    pc.ensure_map_loaded()
    t0 = time.time()
    mesh_stats = build_meshes(rebuild)
    pc.clear_step(STEP)
    rnd = random.Random(707)

    sites = fire_sites(rnd)
    n_flames, n_embers, n_lights = place_fires(sites, rnd)

    # one plume per burning cell, rising from its biggest fire; the ruin cell gets the tallest column
    volumes, plumes = 0, []
    by_cell = {}
    for s in sites:
        if s["cell"] not in by_cell or s["size"] > by_cell[s["cell"]]["size"]:
            by_cell[s["cell"]] = s
    for cell, s in sorted(by_cell.items()):
        big = cell == pc.RUIN_CELL
        volumes += plume("FX_Smoke_%d_%d" % cell, s["x"], s["y"], s["z"] + 3.0, rnd,
                         n=10 if big else 7, h=430.0 if big else 260.0, r0=18.0 if big else 12.0,
                         r1=125.0 if big else 75.0, e0=1.4 if big else 1.1, e1=0.22)
        plumes.append({"cell": list(cell), "base_m": [round(s["x"], 1), round(s["y"], 1)], "big": big})
    rnd_back = random.Random(7071)
    for i, (x, y) in enumerate(back_plume_sites(rnd_back)):
        volumes += plume("FX_SmokeFar_%d" % i, x, y, ROOF_Z, rnd_back, n=8, h=540.0, r0=25.0, r1=170.0, e0=1.0, e1=0.2, glow=1.4)
        l = pc.spawn(unreal.PointLight, (x, y, ROOF_Z + 8.0), step_tag=STEP, label="FX_FarFireLight_%d" % i, folder="FX/Fire")
        l.point_light_component.set_editor_property("intensity_units", unreal.LightUnits.CANDELAS)
        l.point_light_component.set_intensity(6000.0)
        l.point_light_component.set_light_color(unreal.LinearColor(1.0, 0.42, 0.12, 1.0))
        l.point_light_component.set_attenuation_radius(12000.0)
        l.point_light_component.set_cast_shadows(False)
        plumes.append({"backfield": True, "base_m": [round(x, 1), round(y, 1)]})
    # B2 north: red base supply-dump fires + low-rise district roof fires, one column each (own stream)
    rnd_n = random.Random(7072)
    north_flames = {}
    for i, (tag, x, y) in enumerate(north_plume_sites(rnd_n)):
        base = tag == "base"
        z0 = 1.5 if base else LOW_ROOF_Z
        volumes += plume("FX_SmokeNorth_%s_%d" % (tag, i), x, y, z0 + 2.0, rnd_n, n=7, h=300.0 if base else 340.0,
                         r0=11.0 if base else 14.0, r1=80.0 if base else 95.0, e0=1.15, e1=0.22, glow=0.9)
        for j in range(4 if base else 3):
            h = rnd_n.uniform(6.0, 11.0) * (1.3 if j == 0 else 1.0)
            loc = (x + rnd_n.uniform(-4, 4), y + rnd_n.uniform(-4, 4), z0 - 0.5)
            north_flames.setdefault(FLAME_MESH, []).append(pc.xform(loc, rnd_n.uniform(0, 360), (h * 0.9, h * 0.9, h)))
        l = pc.spawn(unreal.PointLight, (x, y, z0 + 6.0), step_tag=STEP, label="FX_NorthFireLight_%d" % i, folder="FX/Fire")
        l.point_light_component.set_editor_property("intensity_units", unreal.LightUnits.CANDELAS)
        l.point_light_component.set_intensity(5000.0)
        l.point_light_component.set_light_color(unreal.LinearColor(1.0, 0.42, 0.12, 1.0))
        l.point_light_component.set_attenuation_radius(9000.0)
        l.point_light_component.set_cast_shadows(False)
        plumes.append({"north": tag, "base_m": [round(x, 1), round(y, 1)]})
    if north_flames:
        pc.spawn_instances(north_flames, STEP, "FX_Flames_North", "FX/Fire", shadows=False)
        n_flames += sum(len(t) for t in north_flames.values())
    # thin brown ground haze over the two damage clusters (dust + low smoke), kept faint for legibility
    haze = [((600.0, 600.0), 300.0), ((200.0, -400.0), 210.0)]
    for i, ((hx, hy), hr) in enumerate(haze):
        fog_volume("FX_Haze_%d" % i, (hx + 40.0, hy + 30.0, 0.0), (hr, hr, 38.0), 0.12, (0.42, 0.38, 0.33), phase=0.5)
        volumes += 1

    n_decals = place_scorch(random.Random(7073))
    place_ruins_fx()
    pc.save_map()
    report = {"step": STEP, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "fire_sites": len(sites), "flame_cards": n_flames,
              "ember_beds": n_embers, "fire_lights": n_lights, "smoke_plumes": plumes, "local_fog_volumes": volumes,
              "scorch_decals": n_decals, "meshes": mesh_stats, "seconds": round(time.time() - t0, 1)}
    pc.write_json(pc.REPORT_DIR + "/M0_FX.json", report)
    pc.log("fx: %d fire sites, %d flame cards, %d lights, %d fog volumes, %d decals" % (len(sites), n_flames, n_lights, volumes, n_decals))


if "--b6" in sys.argv:
    pc.ensure_map_loaded()
    place_ruins_fx()
    pc.save_map()
else:
    main(sys.argv[1:])
