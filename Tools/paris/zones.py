"""Environment zoning configuration for the Paris battlefield (125 B1+).

Single source of truth for background area types. 05_city_layout.py calls cell_zone(c, r) to decide what to place in
each background cell; 07_fx.py / 07_base_red.py use cells_of(zone) to find their anchor cells. The 8x8 board interior
is never routed through this module (05_city_layout.cell_kind handles it first), so the board cannot be changed here.

Zones:
  - "haussmann":   normal Haussmann blocks (default background)
  - "south_clear": southern strip x in [-1400, -800] m, cleared for the B5 blue base (currently empty)
  - "champ":       Champ de Mars park under the Eiffel tower (west side, spans the dividing line)
  - "industrial":  western industrial belt, every column west of the tower column (B1, refined in B3)
  - "base_red":    B2 red faction base, the two cell rows north of the board (x 800..1200 m, y -600..600 m)
  - "cathedral":   B2 Notre-Dame close, two cells north of the base on the axis (x 1200..1400, y -400..0 m)
  - "low":         B2 low-rise district (2-3 upper floors, <= 18 m) filling the rest of the north side
  - "riverbank":   Seine column (unchanged)
  - "base_blue":   B5 south command area (x -1300..-900 m, three rows directly south of the board)
  - "ruins":       B6 overlay on outer "haussmann" cells: collapsed scan / leaning infills / ruined L-corners
  - "ruins_low":   B6 overlay on outer "low" cells: ruined / burnt low-rise modules (still <= 18 m)
  - "footprint":   B6 stamped blocks, one per outer direction (FOOTPRINT_CELLS): giant footprint centrepiece

Cell convention: (col, row); col grows east (+y), row grows north (+x); cell centre = paris_common.cell_center.
"""
import math

import paris_common as pc

# Eiffel tower / Champ de Mars: the tower cell lives in paris_common (EIFFEL_CELL / CHAMP_ROWS) so that 05_city_layout
# and 06_landmarks agree; these names mirror it so the zoning cannot drift from the placed tower.
EIFFEL_NEW_COL = pc.EIFFEL_CELL[0]  # -2 -> y = -1100 m (tower at (-100, -1100) m, one cell south of the dividing line)
EIFFEL_NEW_Y = pc.EIFFEL_POS[1]
CHAMP_NEW_ROWS = pc.CHAMP_ROWS  # (1, 4): rows 1..4 = x in [-500, 300] m, centred on the dividing line x = 0

# B1: south clear strip beyond the B5 base, retained as empty ground.
SOUTH_CLEAR_ROWS = (-7, -4)
# B1 (revised in B2): the industrial belt starts right west of the tower column (no Haussmann columns in between)
INDUSTRIAL_MAX_COL = EIFFEL_NEW_COL - 1  # -3

# B2: north side
BASE_RED_ROWS = (8, 9)  # x in [800, 1200] m, directly north of the board edge
BASE_RED_COLS = (1, 6)  # y in [-600, 600] m
CATHEDRAL_CELLS = ((2, 10), (3, 10))  # Notre-Dame close: x in [1200, 1400], y in [-400, 0] m
CATHEDRAL_ANCHOR = (2, 10)  # the close mesh is one 2-cell strip placed from this cell
LOW_ROWS = (8, pc.CITY_ROWS[1])  # everything north of the board edge ...
LOW_COLS = (EIFFEL_NEW_COL, pc.SEINE_COL - 1)  # ... between the tower column and the Seine

# B5: three 200 m rows immediately south of the board.  Their centres are
# x = -1300, -1100, -900 m, matching the documented blue-base band.  The
# western edge starts at the industrial boundary and the eastern edge stops
# before the Seine column; 05_city_layout handles these cells as low ground
# and 07_base_blue supplies the actual command centre props.
BASE_BLUE_ROWS = (-3, -1)
BASE_BLUE_COLS = (INDUSTRIAL_MAX_COL, pc.SEINE_COL - 1)

# B6 (125 sec. 3.7): outer ruin ring. Cells whose base zone is "haussmann" or "low" and whose centre lies more than
# RUINS_MIN_RADIUS from the board centre are ruined with probability RUINS_RATIO (seeded per cell, so the ring does
# not depend on the layout's random stream). The B5 base strip, the cathedral close, the red base, the river and the
# industrial belt (already war-damaged in B3) are never ruined, so nothing tall lands in front of the board.
RUINS_MIN_RADIUS = 1000.0
RUINS_RATIO = 0.30
RUINS_SEED = 2026100306
RUINS_BASES = {"haussmann": "ruins", "low": "ruins_low"}
# One stamped block per outer direction (base zone in brackets). Each is visible from the board camera except the
# southern one, which sits behind the blue base (x = -1500 m), well clear of its sight line.
FOOTPRINT_CELLS = {"north": (5, 12),   # low district, x 1700 / y 300 m (east of the cathedral band)
                   "east": (12, 5),    # haussmann, east bank, x 300 / y 1700 m
                   "west": (-5, 6),    # industrial belt, x 500 / y -1700 m (north-west of the tower)
                   "south": (12, -4)}  # south_clear, x -1500 / y 1700 m (beyond the base, east bank)
FOOTPRINT_SET = set(FOOTPRINT_CELLS.values())


def ruin_roll(c, r):
    """Seeded per-cell draw in [0, 1) used for the ruin decision and the ruin variant."""
    import random

    return random.Random(RUINS_SEED + c * 1009 + r * 7919).random()


def base_zone(c, r):
    """Zone of background cell (c, r) before the B6 ruin overlay. Board interior is never passed in (see module doc)."""
    if c == pc.SEINE_COL:
        return "riverbank"
    if c == EIFFEL_NEW_COL and CHAMP_NEW_ROWS[0] <= r <= CHAMP_NEW_ROWS[1]:
        return "champ"
    if SOUTH_CLEAR_ROWS[0] <= r <= SOUTH_CLEAR_ROWS[1]:
        return "south_clear"
    if BASE_BLUE_ROWS[0] <= r <= BASE_BLUE_ROWS[1] and BASE_BLUE_COLS[0] <= c <= BASE_BLUE_COLS[1]:
        return "base_blue"
    if (c, r) in CATHEDRAL_CELLS:
        return "cathedral"
    if BASE_RED_ROWS[0] <= r <= BASE_RED_ROWS[1] and BASE_RED_COLS[0] <= c <= BASE_RED_COLS[1]:
        return "base_red"
    if c <= INDUSTRIAL_MAX_COL:
        return "industrial"
    if LOW_ROWS[0] <= r <= LOW_ROWS[1] and LOW_COLS[0] <= c <= LOW_COLS[1]:
        return "low"
    return "haussmann"


def cell_zone(c, r):
    """Zone of background cell (c, r) including the B6 overlay ("footprint", "ruins", "ruins_low")."""
    z = base_zone(c, r)
    if (c, r) in FOOTPRINT_SET:
        return "footprint"
    if z in RUINS_BASES:
        x, y = pc.cell_center(c, r)
        if math.hypot(x, y) > RUINS_MIN_RADIUS and ruin_roll(c, r) < RUINS_RATIO:
            return RUINS_BASES[z]
    return z


def cells_of(zone, rows=None, cols=None, base=False):
    """All background cells of `zone` inside the city extents (board interior excluded), sorted.
    base=True matches the zone before the B6 ruin overlay (keeps B2-B5 anchors stable)."""
    fn = base_zone if base else cell_zone
    rows = rows or pc.CITY_ROWS
    cols = cols or pc.CITY_COLS
    out = []
    for r in range(rows[0], rows[1] + 1):
        for c in range(cols[0], cols[1] + 1):
            if 0 <= c < pc.N and 0 <= r < pc.N:
                continue
            if fn(c, r) == zone:
                out.append((c, r))
    return out


def ruin_stats():
    """Counts of the B6 overlay (for M0_Ruins.json): eligible outer cells, ruined cells, ratio, footprint bases."""
    elig = ruined = 0
    for r in range(pc.CITY_ROWS[0], pc.CITY_ROWS[1] + 1):
        for c in range(pc.CITY_COLS[0], pc.CITY_COLS[1] + 1):
            if (0 <= c < pc.N and 0 <= r < pc.N) or (c, r) in FOOTPRINT_SET:
                continue
            x, y = pc.cell_center(c, r)
            if base_zone(c, r) in RUINS_BASES and math.hypot(x, y) > RUINS_MIN_RADIUS:
                elig += 1
                ruined += cell_zone(c, r) in ("ruins", "ruins_low")
    return {"eligible_outer_cells": elig, "ruined_cells": ruined, "ratio": round(ruined / max(1, elig), 3),
            "target_ratio": RUINS_RATIO, "min_radius_m": RUINS_MIN_RADIUS,
            "footprints": {k: {"cell": list(v), "base_zone": base_zone(*v), "center_m": list(pc.cell_center(*v))}
                           for k, v in FOOTPRINT_CELLS.items()}}


if __name__ == "__main__":
    from collections import Counter

    cnt = Counter()
    for r in range(pc.CITY_ROWS[0], pc.CITY_ROWS[1] + 1):
        for c in range(pc.CITY_COLS[0], pc.CITY_COLS[1] + 1):
            if not (0 <= c < pc.N and 0 <= r < pc.N):
                cnt[cell_zone(c, r)] += 1
    print(dict(cnt))
    print(ruin_stats())
