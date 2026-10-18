"""Step 07_fx_industrial: Western industrial zone battle effects (B3).

Adds fire, explosions, thick smoke and impact marks to the western industrial belt to show active combat.
Anchored on the industrial buildings placed by 05_city_layout.py (read back from City_Industrial_Buildings ISM).

FX types:
- Factory fires: flame cards + point lights on damaged/collapsed buildings
- Explosion sites: Niagara burst particles (or flipbook fallback) + scorch decals
- Industrial smoke: thick black columns from chimneys and burning buildings (Local Fog Volume)
- Sparks/embers: Niagara particle systems at fire sites

Usage (through Tools/ue_run.py):
    07_fx_industrial.py [--seed N]     (default seed = 20261002)
"""
import math
import random
import sys
import time

import unreal

import paris_common as pc
import citygen as cg

SEED = 20261002
STEP = "FX_Industrial"
FLAME_MESH = pc.FX + "/SM_FX_FlameCards"


def find_actor(label):
    for a in pc.actor_sub().get_all_level_actors():
        if a.get_actor_label() == label:
            return a
    return None


def read_industrial_instances():
    """Read back industrial building instances from City_Industrial_Buildings actor."""
    a = find_actor("City_Industrial_Buildings")
    if a is None:
        return []
    instances = []
    for comp in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = comp.get_editor_property("static_mesh")
        name = sm.get_name() if sm else ""
        for i in range(comp.get_instance_count()):
            t = comp.get_instance_transform(i, True)
            if isinstance(t, tuple):
                t = t[-1]
            p = t.translation
            instances.append((name, p.x / 100.0, p.y / 100.0, p.z / 100.0, t.rotation.rotator().yaw))
    return instances


def fire_sites(instances, rnd):
    """Select industrial buildings for fire FX (damaged, collapsed, or random tall structures)."""
    sites = []
    for name, x, y, z, yaw in instances:
        if "Damaged" in name or "Collapsed" in name:
            sites.append(("damaged", x, y, z + 5.0))
        elif "Chimney" in name and rnd.random() < 0.15:
            sites.append(("chimney", x, y, z + 40.0))
        elif "FactoryHall" in name and rnd.random() < 0.25:
            sites.append(("factory", x, y, z + 15.0))
        elif "StorageTank" in name and rnd.random() < 0.2:
            sites.append(("tank", x, y, z + 8.0))
    return sites


def place_flames(sites, rnd):
    """Place flame cards and lights at fire sites. Returns {mesh: [xforms]}, lights."""
    flames = {}
    lights = []
    for tag, x, y, z in sites:
        n_flames = {"damaged": 6, "chimney": 3, "factory": 8, "tank": 5}.get(tag, 4)
        spread = {"damaged": 15.0, "chimney": 8.0, "factory": 25.0, "tank": 10.0}.get(tag, 12.0)
        for _ in range(n_flames):
            h = rnd.uniform(4.0, 9.0) if tag != "chimney" else rnd.uniform(6.0, 12.0)
            loc = (x + rnd.uniform(-spread, spread), y + rnd.uniform(-spread, spread), z + rnd.uniform(-2.0, 1.0))
            flames.setdefault(FLAME_MESH, []).append(pc.xform(loc, rnd.uniform(0, 360), (h * 0.9, h * 0.9, h)))
        # Point light
        light_z = z + 2.0
        lights.append(("point", (x, y, light_z), (1.0, 0.5, 0.2), 2500.0 if tag == "factory" else 1800.0))
    return flames, lights


def smoke_plumes(sites, rnd):
    """Generate thick black smoke columns (Local Fog Volume) at fire sites. Returns volume specs."""
    volumes = []
    for i, (tag, x, y, z) in enumerate(sites):
        if tag == "chimney":
            continue  # chimneys already have smoke from 07_fx.py
        n = {"damaged": 5, "factory": 7, "tank": 4}.get(tag, 5)
        h = {"damaged": 280.0, "factory": 320.0, "tank": 250.0}.get(tag, 300.0)
        r0 = {"damaged": 18.0, "factory": 22.0, "tank": 15.0}.get(tag, 20.0)
        r1 = {"damaged": 90.0, "factory": 110.0, "tank": 80.0}.get(tag, 100.0)
        for j in range(n):
            dz = (j / n) * h
            r = r0 + (r1 - r0) * (j / n) ** 0.6
            em = 1.0 * (1.0 - j / n) ** 1.5
            glow = 0.6 if j < 2 else 0.3
            loc = (x + rnd.uniform(-r0 * 0.3, r0 * 0.3), y + rnd.uniform(-r0 * 0.3, r0 * 0.3), z + dz)
            volumes.append({"label": f"FX_SmokeIndustrial_{i}_{j}", "location": loc, "extent": (r, r, h / n * 0.6),
                           "density": 0.35, "albedo": (0.08, 0.08, 0.08), "emissive": (em * glow, em * glow * 0.5, em * glow * 0.3)})
    return volumes


def explosion_decals(instances, rnd):
    """Place scorch decals at explosion impact sites (ground near industrial buildings). Returns decal specs."""
    decals = []
    candidates = [(x, y, z, yaw) for name, x, y, z, yaw in instances if "Factory" in name or "Warehouse" in name]
    for x, y, z, yaw in rnd.sample(candidates, min(15, len(candidates))):
        dx, dy = rnd.uniform(-40, 40), rnd.uniform(-40, 40)
        s = rnd.uniform(8.0, 18.0)
        decals.append({"location": (x + dx, y + dy, 0.5), "rotation": (90, rnd.uniform(0, 360), 0), "scale": (s, s, s)})
    return decals


def place_fx(seed):
    """Place industrial zone battle FX: fires, smoke, explosions."""
    rnd = random.Random(seed)
    pc.clear_step(STEP)

    instances = read_industrial_instances()
    pc.log("read %d industrial instances" % len(instances))

    sites = fire_sites(instances, rnd)
    flames_dict, lights = place_flames(sites, rnd)
    volumes = smoke_plumes(sites, rnd)
    decals = explosion_decals(instances, rnd)

    # Spawn flame cards
    if flames_dict:
        pc.spawn_instances(flames_dict, STEP, "City_Industrial_Flames", "City")

    # Spawn lights
    for kind, loc, color, intensity in lights:
        light = pc.spawn(unreal.PointLight, loc, (0, 0, 0), step_tag=STEP, label=f"IndustrialFire_{len(lights)}", folder="FX")
        lc = light.point_light_component
        lc.set_intensity(intensity)
        lc.set_light_color(unreal.LinearColor(*color, 1.0))
        lc.set_attenuation_radius(2500.0)
        lc.set_source_radius(80.0)

    # Spawn fog volumes
    for spec in volumes:
        vol = pc.spawn(unreal.LocalFogVolume, spec["location"], (0, 0, 0), step_tag=STEP, label=spec["label"], folder="FX")
        vol.set_actor_scale3d(unreal.Vector(*[s / 5.0 for s in spec["extent"]]))  # LFV_UNIT = 5.0 m
        comp = vol.get_component_by_class(unreal.LocalFogVolumeComponent)
        comp.set_radial_fog_extinction(spec["density"])
        comp.set_height_fog_extinction(0.01)
        comp.set_fog_albedo(unreal.LinearColor(*spec["albedo"], 1.0))
        comp.set_fog_emissive(unreal.LinearColor(*spec["emissive"], 1.0))
        comp.set_fog_phase_g(0.6)

    # Spawn scorch decals (using charred paint material as placeholder)
    scorch_mat = pc.MAT + "/Instances/MI_Paint_Charred"
    for spec in decals:
        dec = pc.spawn(unreal.DecalActor, spec["location"], spec["rotation"], step_tag=STEP, label="ScorchIndustrial", folder="FX")
        dec.set_decal_material(pc.load(scorch_mat))
        comp = dec.decal
        comp.set_editor_property("decal_size", unreal.Vector(*[s * 100.0 for s in spec["scale"]]))  # convert to cm half-extents
        comp.set_editor_property("fade_screen_size", 0.001)

    pc.save_map()
    return {"fire_sites": len(sites), "flame_cards": sum(len(v) for v in flames_dict.values()), "fire_lights": len(lights),
            "smoke_columns": len(volumes), "scorch_decals": len(decals)}


def main(argv):
    seed = SEED
    if "--seed" in argv:
        seed = int(argv[argv.index("--seed") + 1])

    pc.ensure_map_loaded()
    t0 = time.time()
    stats = place_fx(seed)
    stats["seconds"] = round(time.time() - t0, 1)

    pc.write_json(pc.REPORT_DIR + "/M0_FX_Industrial.json", stats)
    pc.log("industrial FX:", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
