# -*- coding: utf-8 -*-
"""Warsaw landmark spec — single source of truth.

Units: metres, Z up, +X east, +Y north.
Each landmark is modelled with its own local origin at (0,0) on the ground plane;
`PLACE` gives where that origin goes on the level-2 board.

Board mapping (from Saved/UIPrototype/Tread_Warsaw_Board_Prototype.html):
  the prototype SVG is 1400x1000 px, scale bar 120 px = 800 m  ->  1 px = 6.6667 m
  world_x = (px - 700) * 6.6667 ; world_y = -(py - 500) * 6.6667
The prototype is explicitly schematic ("示意比例，非精确测绘"); these placements
follow it so the 3D set lines up with the board art.
"""

PX = 800.0 / 120.0          # metres per prototype pixel
MAP_W, MAP_H = 700.0, 500.0  # prototype map centre in px


def board(px, py):
    return (round((px - MAP_W) * PX, 1), round(-(py - MAP_H) * PX, 1))


# ---------------------------------------------------------------- 01 老城集市
RYNEK = {
    "name": "GEO-RYNEK",
    "label": "老城集市 Rynek Starego Miasta",
    # market square inside the house rows
    "square": (90.0, 73.0),          # X (E-W) x Y (N-S)
    "house_depth": 13.0,
    "house_w": (9.5, 13.5),          # per-house frontage range
    "eaves": 13.6,                   # 3 storeys to the eaves
    "storey": (4.3, 3.35, 3.15),     # ground / 1st / 2nd
    "roof_h": (5.8, 7.2),            # steep gable roofs
    "gable_styles": ("step", "tri", "volute", "step", "tri"),
    "gap_corners": 7.0,              # street openings at the four corners
    "well_r": 2.6,
    "place": board(724, 158),
}

# ---------------------------------------------------------------- 02 皇家城堡
ZAMEK = {
    "name": "GEO-ZAMEK",
    "label": "皇家城堡 Zamek Królewski",
    # quadrangle: east wing faces Castle Square (the long public facade)
    "east_len": 92.0, "east_depth": 18.0,
    "north_len": 54.0, "south_len": 54.0, "west_len": 40.0, "wing_depth": 16.0,
    "courtyard": (40.0, 36.0),
    "storeys": (5.2, 4.6, 4.2, 3.6),   # 4 storeys
    "cornice": 18.6,
    "roof_h": 7.4,
    "sig_tower": {"x": 34.0, "y": 0.0, "w": 11.0, "h": 44.0, "helmet": 13.0},
    "wlad_tower": {"x": -38.0, "y": 0.0, "w": 9.0, "h": 30.0, "helmet": 8.0},
    "place": board(872, 150),
}

# ---------------------------------------------------------------- 03 巴比肯
BARBAKAN = {
    "name": "GEO-BARBAKAN",
    "label": "巴比肯 Barbakan",
    "r_out": 15.5, "r_in": 9.6,
    "levels": (4.6, 3.9, 3.6),
    "parapet": 1.9,
    "crenel": 1.1,
    "nowomiejska": {"dx": 0.0, "dy": 0.0, "w": 8.4, "body": 18.5, "roof": 8.5},
    "prochowa": {"dx": -30.0, "dy": 0.0, "r": 4.6, "body": 20.0, "roof": 9.0},
    "wall": {"len": 26.0, "h": 8.6, "t": 3.2},
    "bridge": 9.0,
    "place": board(962, 190),
}

# ---------------------------------------------------------------- 04 瓦津基宫
LAZIENKI = {
    "name": "GEO-LAZIENKI",
    "label": "瓦津基宫 Pałac na Wyspie",
    "main": (34.0, 13.0),            # central block
    "main_h": 12.2,                  # to the balustrade
    "dome_r": 6.2, "dome_h": 4.6,
    "wing": (11.0, 10.5), "wing_h": 10.4,
    "gallery": (11.0, 5.4), "gallery_h": 6.2,
    "island_r": 46.0, "water_r": 64.0,
    "bridge": (13.0, 4.4),
    "place": board(782, 742),
}

# ---------------------------------------------------------------- 05 国家体育场
STADION = {
    "name": "GEO-STADION",
    "label": "国家体育场 Stadion Narodowy",
    "outer": (310.0, 280.0),
    "inner": (182.0, 152.0),
    "pitch": (105.0, 68.0),
    "plinth_h": 3.4,
    "bowl_h": 26.0,
    "mast_h": 70.0, "masts": 8,
    "roof_outer": (300.0, 270.0),
    "roof_inner": (176.0, 146.0),
    "weave_bands": 26,
    "place": board(1316, 470),
}

LANDMARKS = [RYNEK, ZAMEK, BARBAKAN, LAZIENKI, STADION]

# ---------------------------------------------------------------- 06 文化科学宫
PKIN = {
    "name": "GEO-PKIN",
    "label": "文化科学宫 Pałac Kultury i Nauki",
    # 1955 Stalinist tower: 84 m podium, 46 m shaft, stepped crown, 237 m tip
    "podium": (88.0, 88.0), "podium_h": 22.0,
    "pavilion": (20.0, 20.0), "pavilion_h": 34.0,
    "tier2": (62.0, 62.0), "tier2_h": 44.0,
    "shaft": (40.0, 40.0), "shaft_top": 114.0,
    "crown": (34.0, 34.0), "crown_top": 126.0,
    "steps": [(28.0, 142.0), (20.0, 156.0), (13.0, 168.0)],
    "spire_top": 192.0, "tip": 237.0,
    "plaza": 170.0,
    "place": board(660, 480),
}

# ---------------------------------------------------------------- materials
MAT = {
    "stucco_ochre":  ("#c6a468", 0.72, 0.0),
    "stucco_cream":  ("#ded4bc", 0.74, 0.0),
    "stucco_white":  ("#eae4d6", 0.70, 0.0),
    "stucco_pink":   ("#bf8b74", 0.72, 0.0),
    "stucco_olive":  ("#a8a06b", 0.72, 0.0),
    "stucco_blue":   ("#8d9aa8", 0.72, 0.0),
    "brick_red":     ("#8d3d30", 0.86, 0.0),
    "brick_dark":    ("#6c2f26", 0.88, 0.0),
    "stone_grey":    ("#b5ae9f", 0.78, 0.0),
    "stone_light":   ("#cfc7b4", 0.76, 0.0),
    "copper_green":  ("#5c8c74", 0.55, 0.35),
    "copper_dark":   ("#3d6a57", 0.60, 0.30),
    "tile_red":      ("#9d4530", 0.80, 0.0),
    "roof_grey":     ("#565b5f", 0.72, 0.15),
    "glass_dark":    ("#1d2429", 0.16, 0.55),
    "glass_warm":    ("#3a2f24", 0.20, 0.30),
    "gold":          ("#c9a23c", 0.30, 1.0),
    "iron_dark":     ("#2f2c28", 0.55, 0.85),
    "bronze":        ("#6f5733", 0.42, 0.85),
    "concrete":      ("#a8a294", 0.82, 0.0),
    "conc_dark":     ("#7d786d", 0.84, 0.0),
    "grass":         ("#6d8a4b", 0.90, 0.0),
    "water":         ("#35566a", 0.12, 0.35),
    "asphalt":       ("#464644", 0.90, 0.0),
    "cobble":        ("#8b857a", 0.88, 0.0),
    "steel":         ("#b9bec4", 0.35, 1.0),
    "stad_red":      ("#ad2a24", 0.45, 0.55),
    "stad_white":    ("#e6e2d9", 0.45, 0.45),
    "stad_silver":   ("#9aa3ab", 0.38, 0.75),
    "membrane":      ("#d8d2c4", 0.55, 0.0),
}
