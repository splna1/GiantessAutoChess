# -*- coding: utf-8 -*-
"""M6 Bureau — near-future military base kit.  FROZEN SPEC / single source of truth.

Units: metres, Z up, +X east, +Y north.
Every module is built with its local origin at (0,0,0) on the ground plane and
its FRONT facing local -Y (south).  `SITE["place"]` puts that origin in the
compound.  Nothing outside this file may invent dimensions: builders read MODS,
the assembler reads SITE.

Design language (near-future, "特勤处"):
  * cast concrete plinths + painted steel/composite panels with real seams
  * chamfered volumes, exposed ribs, gasketed panel joints
  * LED light lines, sensor pods, drone infrastructure, solar arrays
  * safety orange / signal amber only on hazard edges and signage
  * cool grey-green palette, dusty ground, no sci-fi glow everywhere
"""

VERSION = "m6-base-1.0"
GRID = 4.0                      # structural planning grid

# ---------------------------------------------------------------- materials
# key: (hex, roughness, metallic, pattern, pattern_scale)
MAT = {
    # concrete family
    "conc":         ("#7b7d78", 0.88, 0.00, "concrete", 0.28),
    "conc_dark":    ("#5f625e", 0.90, 0.00, "concrete", 0.24),
    "conc_light":   ("#8d8e87", 0.86, 0.00, "concrete", 0.32),
    "conc_stain":   ("#6e6d64", 0.92, 0.00, "plaster", 0.55),
    # steel / panels
    "steel":        ("#4d555b", 0.42, 0.85, "metal", 0.70),
    "steel_dark":   ("#23282d", 0.46, 0.88, "metal", 0.85),
    "steel_light":  ("#7f878d", 0.38, 0.80, "metal", 0.65),
    "galv":         ("#8f969a", 0.34, 0.72, "metal", 1.05),
    "panel":        ("#5b636b", 0.52, 0.45, "metal", 0.55),
    "panel_dark":   ("#3a4148", 0.54, 0.40, "metal", 0.60),
    "panel_sand":   ("#8b866f", 0.58, 0.25, "metal", 0.50),
    # glass
    "glass":        ("#0a1216", 0.10, 0.72, None, 1.0),
    "glass_green":  ("#0c171b", 0.12, 0.65, None, 1.0),
    "glass_warm":   ("#221d16", 0.14, 0.55, None, 1.0),
    # rubber / paint / cloth
    "rubber":       ("#17181a", 0.88, 0.00, None, 1.0),
    "orange":       ("#c2531f", 0.55, 0.10, None, 1.0),
    "yellow":       ("#c9a22a", 0.52, 0.10, None, 1.0),
    "red":          ("#a32a20", 0.55, 0.00, None, 1.0),
    "white":        ("#d9d9d1", 0.62, 0.00, None, 1.0),
    "black":        ("#131415", 0.70, 0.10, None, 1.0),
    "canvas":       ("#6d6a58", 0.92, 0.00, "plaster", 0.60),
    "rust":         ("#7d4a30", 0.86, 0.15, "metal", 1.40),
    "copper":       ("#7b5a3a", 0.36, 0.90, "metal", 1.20),
    # ground
    "asphalt":      ("#33353a", 0.92, 0.00, "concrete", 0.30),
    "concrete_rd":  ("#7a7a73", 0.90, 0.00, "concrete", 0.20),
    "gravel":       ("#6f675b", 0.95, 0.00, "stone", 0.40),
    "dust":         ("#6b6355", 0.96, 0.00, "plaster", 0.45),
    "grass_dry":    ("#63633f", 0.95, 0.00, None, 1.0),
    "stone_scatter": ("#6b6357", 0.95, 0.00, "stone", 1.8),
    # technical
    "solar":        ("#101a28", 0.16, 0.55, None, 1.0),
    "radome":       ("#b9b7ab", 0.55, 0.00, "plaster", 0.35),
    "lens":         ("#c9d4d6", 0.08, 0.20, None, 1.0),
    "mirror":       ("#d5dade", 0.05, 1.00, None, 1.0),
    # heavy machinery / construction site
    "steel_plate":  ("#4a4f54", 0.54, 0.80, "brushed", 0.55),
    "steel_matte":  ("#6a7076", 0.64, 0.42, "brushed", 0.80),
    "track_steel":  ("#3a3c3e", 0.74, 0.72, "metal", 1.30),
    "rubber_dark":  ("#191a1b", 0.92, 0.00, None, 1.0),
    "concrete_raw": ("#9a9992", 0.92, 0.00, "concrete", 0.35),
    "rebar":        ("#6b4a35", 0.78, 0.55, "metal", 2.20),
    "timber":       ("#8a6a42", 0.86, 0.00, "plaster", 1.30),
    "dirt_pile":    ("#7a6d58", 0.97, 0.00, "plaster", 0.80),
    "gravel_pile":  ("#8b8478", 0.95, 0.00, "stone", 1.20),
    "panel_grey":   ("#8c8c86", 0.88, 0.00, "concrete", 0.30),
}

# emissive materials: key -> (hex, strength)
EMAT = {
    "em_white":  ("#dfe9ee", 7.0),
    "em_amber":  ("#ff9a2e", 12.0),
    "em_red":    ("#ff2d20", 10.0),
    "em_cyan":   ("#4fd6e6", 8.0),
    "em_green":  ("#57e07a", 6.0),
    "em_blue":   ("#3f7dff", 6.0),
}

# ---------------------------------------------------------------- modules
# footprints are (X, Y) metres; heights are absolute Z unless named _h.
MODS = {
    # ------------------------------------------------------------ C2
    "C2": {
        "name": "GEO-C2",
        "label": "指挥中心 Command & Control",
        "plinth": (40.0, 32.0, 0.9),        # hardened apron slab (w, d, h)
        "body": (24.0, 16.0),               # main hardened block
        "podium_h": 5.2,                    # blast podium
        "floors": (4.2, 4.0, 3.8),          # three upper storeys
        "annex": (8.0, 8.0, 5.6),           # west annex (w, d, h)
        "deck": (18.0, 11.0, 1.1),          # roof plant deck (w, d, h)
        "mast_h": 18.0, "mast_at": (7.0, -4.0),
        "shield": {"len": 13.0, "h": 6.2, "t": 1.1, "offset": 5.2},
        "entry": {"w": 5.4, "h": 3.4, "steps": 4},
    },
    # ------------------------------------------------------------ HGR
    "HGR": {
        "name": "GEO-HGR",
        "label": "机库 · 维修坞 Hangar / Maintenance",
        "body": (48.0, 34.0),               # clear-span hangar
        "eave": 14.6, "ridge": 18.8,
        "door": (28.0, 11.2),               # clear opening (w, h)
        "leaves": 4,
        "annex": (14.0, 10.0, 6.4),         # maintenance annex (east side)
        "apron": (60.0, 38.0, 0.18),        # apron in front (south)
        "extractors": 6,
        "fuel_farm": {"tanks": 2, "r": 2.3, "h": 6.2, "at": (26.0, -22.0)},
    },
    # ------------------------------------------------------------ BRK
    "BRK": {
        "name": "GEO-BRK",
        "label": "兵营 Barracks",
        "body": (40.0, 12.0),
        "storeys": 4, "storey_h": 3.15,
        "parapet": 1.1,
        "stair": (6.0, 5.0, 14.4),          # stair tower (w, d, h)
        "arcade": 3.4,                      # ground-floor arcade depth
        "solar": (13.0, 6.5),               # roof solar array (w, d)
        "containers": 3,
    },
    # ------------------------------------------------------------ RDR
    "RDR": {
        "name": "GEO-RDR",
        "label": "雷达 · 近防塔 Radar / CIWS tower",
        "shelter": (14.0, 11.0, 5.2),
        "tower_h": 38.0,
        "base_w": 5.2, "top_w": 2.4,
        "aesa": (6.6, 5.0),                 # phased-array panel
        "ciws_at": 26.0,
        "launcher_at": 12.0,
        "dish_r": 1.6,
    },
    # ------------------------------------------------------------ GTE
    "GTE": {
        "name": "GEO-GTE",
        "label": "门禁 · 围墙 Gate complex / perimeter",
        "house": (12.0, 8.0, 4.6),
        "canopy": (16.0, 7.0, 0.45),
        "tower": (4.2, 4.2, 9.2),
        "tower_gap": 16.0,
        "barrier": 8.0,                      # drop-arm length
        "wall": {"len": 40.0, "h": 3.3, "t": 0.35, "pier": 4.0},
        "lane": (30.0, 12.0),
    },
    # ------------------------------------------------------------ UAV
    "UAV": {
        "name": "GEO-UAV",
        "label": "无人机坪 Drone nest / VTOL pad",
        "pad": (30.0, 26.0, 0.22),
        "circles": [(0.0, 0.0, 4.6), (-8.0, 7.0, 3.2), (8.0, 7.0, 3.2),
                    (-8.0, -7.0, 3.2), (8.0, -7.0, 3.2)],
        "shed": (15.0, 7.5, 4.6),
        "cab": (6.0, 4.2, 3.2),
        "gantries": 3,
    },
    # ------------------------------------------------------------ CON (site)
    "CON": {
        "name": "GEO-CON",
        "label": "施工场 Construction site",
        "plot": (64.0, 52.0),
        "pit": (34.0, 24.0, 4.2),            # w, d, depth
        "frame": (26.0, 20.0, 3),            # partial concrete frame: w, d, bays
        "frame_bh": 8.6,                     # two slabs / three levels
        "office": (12.0, 3.0, 2.9),
        "laydown": (26.0, 18.0),             # material laydown yard (w, d)
        "beams": {"n": 7, "len": 20.0, "d": 1.10, "b": 0.42},
        "panels": {"n": 5, "w": 12.0, "h": 4.2, "t": 0.55},
        "containers": 5,
        "rebar_bundles": 4,
        "pallets": 8,
    },
    # ------------------------------------------------------------ SIT (seat)
    "SIT": {
        "name": "GEO-SIT",
        "label": "巨人座 · 观礼台 Giant's seat / review stand",
        "seat": (64.0, 46.0, 26.0),          # w, d, h  (the low block she sits on)
        "pan": (56.0, 39.0, 2.4),            # recessed seat pan w, d, depth
        "back": (64.0, 18.0, 78.0),          # w, d, total height (the tall block)
        "spine": (3.0, 0.8),                 # spine channel width / depth
        "gallery": (48.0, 10.0, 56.0),       # glazed band w, h, z base (side faces)
        "mast": 12.0,
        "stair": (7.0, 9.0, 28.5),
        "elev": (8.0, 8.0, 30.0),
        "cushions": (6, 4),                  # seat cushion grid
    },
    # ------------------------------------------------------------ CCR (crane)
    "CCR": {
        "name": "GEO-CCR",
        "label": "履带式集装箱吊车 Crawler container crane",
        "track_len": 10.6, "track_w": 1.90, "gauge": 4.8,
        "carbody": (5.4, 2.8, 1.9),
        "house": (11.0, 4.3, 3.9),           # superstructure (L, W, H)
        "counterweight": (4.6, 4.3, 2.9),
        "cab": (2.5, 2.3, 2.7),
        "boom_len": 44.0, "boom_angle": 58.0,
        "boom_w0": 2.6, "boom_w1": 1.5,
        "spreader": (12.6, 2.7, 1.1),
        "container": (12.19, 2.44, 2.59),
    },
}

# ---------------------------------------------------------------- site
SITE = {
    "size": (220.0, 170.0),                 # compound inside the perimeter
    "fence_h": 3.3,
    "fence_inset": 4.0,
    "place": {
        "C2":  {"pos": (0.0, 46.0), "rz": 0.0},
        "HGR": {"pos": (66.0, 8.0), "rz": -90.0},
        "BRK": {"pos": (-66.0, 34.0), "rz": 0.0},
        "RDR": {"pos": (86.0, 60.0), "rz": -18.0},
        "GTE": {"pos": (0.0, -70.0), "rz": 0.0},
        "UAV": {"pos": (-52.0, 60.0), "rz": 0.0},
        "CON": {"pos": (-70.0, -14.0), "rz": 0.0},
        "SIT": {"pos": (0.0, -152.0), "rz": 0.0},
        "CCR": {"pos": (-60.0, -26.0), "rz": 118.0},
    },
    # asphalt / concrete rectangles: (x0, y0, x1, y1, material_key, z)
    "paving": [
        (-9.0, -62.0, 9.0, 30.0, "asphalt", 0.02),        # main approach
        (-46.0, -6.0, 52.0, 6.0, "asphalt", 0.02),        # east-west spine
        (-46.0, 6.0, -14.0, 34.0, "asphalt", 0.02),       # barracks spur
        (13.0, -11.0, 49.0, 23.0, "concrete_rd", 0.03),   # hangar apron approach
        (-24.0, 8.0, 24.0, 32.0, "concrete_rd", 0.03),    # command plaza
        (-22.0, -62.0, 22.0, -50.0, "concrete_rd", 0.03), # gate inspection
        (-70.0, 44.0, -34.0, 74.0, "concrete_rd", 0.03),  # drone pad
        (70.0, 40.0, 100.0, 74.0, "gravel", 0.02),        # radar pad
        (-46.0, 14.0, -34.0, 30.0, "concrete_rd", 0.03),  # barracks yard
    ],
    # container / equipment yard filler: (x0, y0, x1, y1)
    "yards": [(-96.0, -30.0, -50.0, 8.0), (30.0, -46.0, 84.0, -18.0)],
    # reserved expansion plots: gravel pad + painted outline + corner stakes.
    # adding a module = append one entry here and one row in assemble.MODULES.
    "expansion": [
        {"id": "P-01", "pos": (-72.0, -14.0), "size": (56.0, 46.0), "use": "施工场 CON（已用）"},
        {"id": "P-02", "pos": (34.0, -58.0), "size": (44.0, 34.0), "use": "预留 / 车辆场二期"},
        {"id": "P-03", "pos": (-96.0, 44.0), "size": (38.0, 38.0), "use": "预留 / 仓储"},
        {"id": "P-04", "pos": (66.0, 40.0), "size": (36.0, 36.0), "use": "预留 / 能源站"},
        {"id": "S-01", "pos": (0.0, -152.0), "size": (96.0, 84.0), "use": "巨人座广场（外场）"},
    ],
    "light_masts": [(-104.0, -76.0), (104.0, -76.0), (-104.0, 76.0), (104.0, 76.0),
                    (-30.0, -40.0), (36.0, 30.0)],
    "berms": [  # earth revetments around the hangar and fuel farm
        {"x0": 38.0, "y0": -24.0, "x1": 94.0, "y1": -14.0, "h": 3.2},
        {"x0": 38.0, "y0": 26.0, "x1": 94.0, "y1": 36.0, "h": 3.2},
    ],
}
