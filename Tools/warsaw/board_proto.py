# -*- coding: utf-8 -*-
"""Warsaw board v2 — prototype data transcribed from
Saved/UIPrototype/Tread_Warsaw_Board_Prototype.html (the layout's single source of truth).

Pure python (no bpy / no shapely) so both the layout generator and Blender can import it.

Scale decision (document/184): the prototype is schematic at 120 px = 800 m, which spreads the
24 cells over 4.1 x 5.3 km; the board camera of document/122 only frames ~1.5 km of depth.
The board is therefore compressed to 1 px = 2.0 m (old town <-> castle 296 m, real ~260 m) while
every landmark stays 1:1.

Frame: metres, +X east, +Y north, Z up (same as spec.py).  UE import rotates yaw +90 so that
north becomes UE +X like the Paris board.
"""
import math

PX = 2.0                    # metres per prototype pixel
OX, OY = 680.0, 520.0       # prototype pixel that becomes the world origin (board centre)
CELL_SCALE = 0.8            # cells are shrunk to a Paris-pad sized plaza (~100 x 85 m)


def w(px, py):
    return ((px - OX) * PX, -(py - OY) * PX)


def wpts(pts):
    return [w(x, y) for x, y in pts]


def wang(svg_deg):
    """SVG rotate() is clockwise on a y-down screen -> counter-clockwise world angle is negative."""
    return -float(svg_deg)


# ------------------------------------------------------------------ city regions
# pal: old / city / south / praga ; ang: SVG degrees ; step: px (unused for v2 block size)
REGIONS = [
    {"name": "old_muranow",   "pts": [[592, 110], [884, 104], [896, 268], [872, 336], [600, 340], [580, 220]], "pal": "city",  "ang": 4},
    {"name": "srodmiescie_n", "pts": [[150, 150], [586, 116], [584, 424], [380, 436], [150, 392]],             "pal": "city",  "ang": 0},
    {"name": "wola",          "pts": [[-10, 140], [150, 146], [150, 552], [-10, 566]],                         "pal": "wola",  "ang": 0},
    {"name": "srodmiescie_sw","pts": [[384, 438], [586, 428], [586, 616], [384, 646]],                         "pal": "city",  "ang": 0},
    {"name": "nowy_swiat",    "pts": [[612, 346], [836, 338], [862, 416], [788, 392], [612, 420]],             "pal": "city",  "ang": -6},
    {"name": "ochota",        "pts": [[-10, 572], [376, 560], [376, 764], [-10, 770]],                         "pal": "south", "ang": 0},
    {"name": "mokotow",       "pts": [[382, 650], [664, 622], [660, 864], [382, 864]],                         "pal": "south", "ang": 0},
    {"name": "se_bank",       "pts": [[906, 612], [1040, 620], [1050, 900], [990, 896], [990, 930], [906, 930]], "pal": "south", "ang": 0},
    {"name": "praga_n",       "pts": [[1266, 140], [1424, 140], [1424, 540], [1266, 540]],                     "pal": "praga", "ang": 2},
    {"name": "praga_s",       "pts": [[1272, 696], [1424, 690], [1424, 930], [1278, 930]],                     "pal": "praga", "ang": 2},
]

# ------------------------------------------------------------------ parks
PARKS = [
    {"name": "ogrod_saski",     "pts": [[636, 246], [762, 240], [772, 318], [648, 330]], "kind": "garden"},
    {"name": "lazienki",        "pts": [[668, 650], [886, 636], [902, 810], [756, 852], [664, 792]], "kind": "forest"},
    {"name": "ogrod_botaniczny","pts": [[872, 822], [968, 806], [986, 886], [896, 904]], "kind": "garden"},
    {"name": "pole_mokotowskie","pts": [[150, 846], [330, 830], [356, 930], [168, 948]], "kind": "field"},
    {"name": "park_praski",     "pts": [[1272, 560], [1418, 548], [1424, 672], [1278, 690]], "kind": "forest"},
]
PONDS = [  # (cx, cy, rx, ry) px — the Łazienki lake belongs to the landmark itself
    (260, 888, 38, 20),
]

# ------------------------------------------------------------------ Vistula (cubic Bezier banks)
RIVER_LEFT = [(1090, -20), [(1055, 120), (1090, 250), (1075, 340)], [(1060, 430), (1045, 470), (1065, 560)],
              [(1085, 650), (1105, 760), (1130, 860)], [(1145, 920), (1150, 970), (1155, 1020)]]
RIVER_RIGHT = [(1200, -20), [(1165, 120), (1200, 250), (1185, 340)], [(1170, 430), (1155, 470), (1175, 560)],
               [(1195, 650), (1215, 760), (1240, 860)], [(1255, 920), (1260, 970), (1265, 1020)]]
# continuation outside the prototype frame (centre line, px) so the camera never sees the river end
RIVER_NORTH = [(1145, -20), (1172, -300), (1240, -700), (1300, -1100)]
RIVER_SOUTH = [(1210, 1020), (1236, 1300), (1290, 1600)]
RIVER_W_PX = 110.0


def bezier_bank(spec, steps=24):
    p0 = spec[0]
    out = [p0]
    for c1, c2, p3 in spec[1:]:
        for i in range(1, steps + 1):
            t = i / float(steps)
            a = (1 - t) ** 3
            b = 3 * (1 - t) ** 2 * t
            c = 3 * (1 - t) * t * t
            d = t ** 3
            out.append((a * p0[0] + b * c1[0] + c * c2[0] + d * p3[0],
                        a * p0[1] + b * c1[1] + c * c2[1] + d * p3[1]))
        p0 = p3
    return out


# ------------------------------------------------------------------ streets
# (name, pts px, real width m, tree rows)
STREETS = [
    ("Marszalkowska",      [[600, 110], [600, 880]],                                             34.0, False),
    ("Al_Jerozolimskie",   [[-10, 512], [1046, 500]],                                            44.0, True),
    ("Al_Solidarnosci",    [[292, 300], [1046, 296]],                                            40.0, False),
    ("Swietokrzyska",      [[180, 392], [1050, 386]],                                            30.0, False),
    ("Trakt_Krolewski",    [[938, 290], [906, 318], [826, 398], [796, 470], [820, 560], [786, 636], [768, 676]], 26.0, False),
    ("Al_Ujazdowskie",     [[768, 676], [742, 762], [726, 838]],                                 40.0, True),
    ("Mokotowska",         [[380, 640], [900, 610]],                                             26.0, False),
    ("Grojecka",           [[60, 660], [380, 650]],                                              26.0, False),
    ("Waszyngtona",        [[1052, 502], [1280, 512], [1424, 520]],                              40.0, True),
    ("Targowa",            [[1292, 140], [1300, 540]],                                           32.0, False),
]

# ------------------------------------------------------------------ bridges (row py, centre px)
BRIDGES = [
    {"name": "Most_Kierbedzia",      "x": 1112, "y": 296, "w": 24.0, "kind": "truss"},
    {"name": "Most_Swietokrzyski",   "x": 1112, "y": 386, "w": 22.0, "kind": "girder"},
    {"name": "Most_Poniatowskiego",  "x": 1110, "y": 500, "w": 30.0, "kind": "towers"},
    {"name": "Most_Lazienkowski",    "x": 1140, "y": 648, "w": 28.0, "kind": "girder"},
]

# ------------------------------------------------------------------ landmarks (1:1)
# hx/hy: half extents of the local bbox (probed from the .blend), rot: world degrees
LANDMARKS = [
    {"key": "RYNEK",    "blend": "Warsaw_01_Rynek.blend",    "coll": "COL_LM_RYNEK",    "root": "LM_RYNEK",
     "px": (724, 158), "rot": -4.0,  "bbox": (-59.4, -50.9, 59.4, 50.9)},
    {"key": "ZAMEK",    "blend": "Warsaw_02_Zamek.blend",    "coll": "COL_LM_ZAMEK",    "root": "LM_ZAMEK",
     "px": (958, 262), "rot": -90.0, "bbox": (-47.4, -54.4, 47.4, 29.4)},
    {"key": "BARBAKAN", "blend": "Warsaw_03_Barbakan.blend", "coll": "COL_LM_BARBAKAN", "root": "LM_BARBAKAN",
     "px": (948, 108), "rot": 0.0,   "bbox": (-44.0, -30.0, 44.0, 26.0)},
    {"key": "LAZIENKI", "blend": "Warsaw_04_Lazienki.blend", "coll": "COL_LM_LAZIENKI", "root": "LM_LAZIENKI",
     "px": (782, 742), "rot": 0.0,   "bbox": (-64.0, -65.0, 64.0, 64.0)},
    {"key": "STADION",  "blend": "Warsaw_05_Stadion.blend",  "coll": "COL_LM_STADION",  "root": "LM_STADION",
     "px": (1316, 470), "rot": 0.0,  "bbox": (-161.6, -161.6, 161.7, 161.6)},
    {"key": "PKIN",     "blend": "Warsaw_06_PKin.blend",     "coll": "COL_LM_PKIN",     "root": "LM_PKIN",
     "px": (660, 450), "rot": 0.0,   "bbox": (-85.0, -85.0, 85.0, 85.0)},
]
SIGISMUND_COLUMN_PX = (918, 262)   # in front of the castle's public (west) facade

# ------------------------------------------------------------------ cells (24 deployment plazas)
# moved from the prototype (old -> new px) only where a landmark footprint overlapped:
#   E8 (986,300)->(1000,316)  castle;  M2 (700,398)->(740,385)  PKiN plaza
CELLS = [
    ("E1", "老城集市 Rynek",          "enemy", (724, 158), 74, 56, 6),
    ("E2", "城堡广场 Pl.Zamkowy",     "enemy", (872, 150), 70, 54, -8),
    ("E3", "巴比肯 Barbakan",         "enemy", (962, 190), 60, 50, 12),
    ("E4", "新城广场 Rynek Nowego",   "enemy", (806, 212), 68, 52, -4),
    ("E5", "克拉辛斯基宫",            "enemy", (668, 238), 66, 54, 10),
    ("E6", "大剧院 Teatr Wielki",     "enemy", (620, 300), 64, 50, -6),
    ("E7", "穆里亚诺夫 Muranów",      "enemy", (748, 296), 70, 52, 4),
    ("E8", "河岸哨所",                "enemy", (1000, 316), 58, 48, -10),
    ("E9", "萨克森北缘",              "enemy", (890, 254), 62, 48, 8),
    ("M1", "阅兵广场 Pl.Defilad",     "mid",   (548, 418), 78, 58, -6),
    ("M2", "文化宫前庭",              "mid",   (740, 385), 72, 54, 5),
    ("M3", "金色露台 Złote Tarasy",   "mid",   (806, 430), 66, 52, -10),
    ("M4", "耶路撒冷大道",            "mid",   (556, 548), 74, 54, 8),
    ("M5", "中央站 Dw.Centralny",     "mid",   (706, 562), 70, 52, -4),
    ("M6", "宪法广场 Pl.Konstytucji", "mid",   (816, 534), 68, 50, 6),
    ("P1", "莫科托夫街 Mokotowska",   "player", (452, 688), 72, 54, -6),
    ("P2", "乌亚兹多夫大道",          "player", (600, 700), 70, 52, 4),
    ("P3", "瓦津基湖北岸",            "player", (724, 662), 64, 50, -8),
    ("P4", "救世主广场 Pl.Zbawiciela","player", (470, 792), 70, 54, 8),
    ("P5", "莫科托夫街区",            "player", (610, 806), 72, 54, -4),
    ("P6", "瓦津基宫前庭",            "player", (782, 868), 66, 50, 6),
    ("P7", "植物园南门",              "player", (930, 872), 62, 50, -6),
    ("P8", "肖邦公园南",              "player", (552, 884), 66, 50, 10),
    ("P9", "南郊哨位",                "player", (376, 862), 62, 50, -8),
]
# E1 is the Rynek square itself: fit the cell inside the 90 x 73 m house ring
CELL_OVERRIDE = {"E1": (84.0, 66.0)}

ZONE_COLOR = {"enemy": (0.75, 0.22, 0.17), "mid": (0.72, 0.53, 0.04), "player": (0.12, 0.44, 0.84)}

# ------------------------------------------------------------------ named buildings (real 1939 Warsaw)
# placed on the street edge of the block nearest to the anchor point
SPECIALS = [
    ("church_twin",   "Kosciol_sw_Krzyza",      (842, 372)),   # Holy Cross, Krakowskie Przedmiescie
    ("church_single", "Kosciol_sw_Anny",        (906, 300)),   # St Anne, by Castle Square
    ("rotunda",       "Kosciol_sw_Aleksandra",  (812, 476)),   # Pl. Trzech Krzyzy
    ("church_twin",   "Kosciol_Zbawiciela",     (506, 776)),   # Pl. Zbawiciela
    ("church_twin",   "Katedra_sw_Floriana",    (1322, 236)),  # Praga
    ("tower",         "Prudential",             (626, 368)),   # Pl. Napoleona, 66 m (1933)
    ("theatre",       "Teatr_Wielki",           (640, 266)),
    ("palace",        "Palac_Krasinskich",      (672, 200)),
    ("gasworks",      "Gazownia_Wola",          (70, 330)),
]

# map frame of the prototype and the background extent (px)
PROTO_FRAME = (-10, 0, 1424, 1000)
WORLD_BOUNDS = (-3200.0, -1600.0, 3400.0, 3600.0)   # metres: x0, y0, x1, y1
