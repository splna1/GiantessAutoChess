"""Freeze the 8x8 board interior of the B1 layout (pure CPython, no `unreal`).

Background: up to B1, 05_city_layout.py drew the board's module variants, ground yaws and street furniture from the
same random stream as the background city, so any change to the backfield (new zones, cleared rows, industrial belt)
reshuffled the board too. B2 makes the board immune: this script replays the exact random consumption of the B1 layout
loop (05_city_layout.py + zones.py as of doc 128, seed 20260927) and writes the board part of the result to

    Tools/paris/board_frozen.json   {"cells": {"c,r": {"ground": yaw_k, "modules": [[L, infill] x 4]}},
                                     "furniture": {"trees": [...], "cars": [...]}}   (|x|,|y| <= REGION m)

05_city_layout.py reads that file for the board cells and the board-region furniture instead of the random stream.
Re-running this script reproduces the same file bit for bit; it is kept as the provenance of the frozen table.

Usage: python Tools/paris/freeze_board_b1.py [--variant b1|b2] [--out path]
       --variant b2 replays the first B2 layout run (before freezing) - used once to validate the replay against
       the live level (Saved/Scratch/dump_live_board.py).
"""
import json
import os
import sys

import citygen as cg

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 20260927
N = 8
CELL = 200.0
CITY_ROWS = (-6, 18)
CITY_COLS = (-12, 18)
SEINE_COL = 9
PLAZA_CELLS = {(3, 3), (4, 3), (3, 4), (4, 4)}
DAMAGE_CELLS = {(5, 5), (6, 5), (5, 6), (6, 6), (1, 4), (2, 5)}
RUIN_CELL = (6, 6)
BRIDGE_ROWS_X = (-1200.0, -600.0, 0.0, 600.0, 1200.0, 1800.0, 2400.0, 3000.0)
EIFFEL_COL, CHAMP_ROWS = -2, (1, 4)
SOUTH_CLEAR_ROWS = (-7, -4)
BASE_RED_ROWS, BASE_RED_COLS = (8, 9), (1, 6)
CATHEDRAL_CELLS = ((2, 10), (3, 10))
REGION = 830.0

TREES = ["SM_Tree_%d" % i for i in range(4)]
CARS = ["SM_Car_%d" % i for i in range(5)]
CARS_BURNT = ["SM_Car_Burnt_%d" % i for i in range(2)]
L_OK = ["SM_Hsm_L_%02d" % i for i in range(8)]
L_BURNT = ["SM_Hsm_LBurnt_%02d" % i for i in range(3)]
L_RUIN = ["SM_Hsm_LRuin_%02d" % i for i in range(3)]
I_OK = ["SM_Hsm_Infill_%02d" % i for i in range(5)]
I_BURNT = ["SM_Hsm_InfillBurnt_00"]
I_RUIN = ["SM_Hsm_InfillRuin_%02d" % i for i in range(2)]
TREE_OFF = cg.ROAD_HALF + 1.8
LAMP_OFF = cg.ROAD_HALF + 0.55
CAR_OFF = cg.ROAD_HALF - 1.3


def cell_center(col, row):
    return ((row - (N - 1) / 2.0) * CELL, (col - (N - 1) / 2.0) * CELL)


def zone_b1(c, r):
    if c == SEINE_COL:
        return "riverbank"
    if c == EIFFEL_COL and CHAMP_ROWS[0] <= r <= CHAMP_ROWS[1]:
        return "champ"
    if SOUTH_CLEAR_ROWS[0] <= r <= SOUTH_CLEAR_ROWS[1]:
        return "south_clear"
    if c < -4:
        return "industrial"
    return "haussmann"


def zone_b2(c, r):
    if c == SEINE_COL:
        return "riverbank"
    if c == EIFFEL_COL and CHAMP_ROWS[0] <= r <= CHAMP_ROWS[1]:
        return "champ"
    if SOUTH_CLEAR_ROWS[0] <= r <= SOUTH_CLEAR_ROWS[1]:
        return "south_clear"
    if (c, r) in CATHEDRAL_CELLS:
        return "cathedral"
    if BASE_RED_ROWS[0] <= r <= BASE_RED_ROWS[1] and BASE_RED_COLS[0] <= c <= BASE_RED_COLS[1]:
        return "base_red"
    if c <= -3:
        return "industrial"
    if 8 <= r <= CITY_ROWS[1] and -2 <= c <= SEINE_COL - 1:
        return "low"
    return "haussmann"


def make_cell_kind(zone):
    def cell_kind(c, r):
        if 0 <= c < N and 0 <= r < N:
            return "plaza" if (c, r) in PLAZA_CELLS else "board"
        if c == SEINE_COL:
            return "river"
        if c == EIFFEL_COL and CHAMP_ROWS[0] <= r <= CHAMP_ROWS[1]:
            return "champ"
        z = zone(c, r)
        if z == "south_clear":
            return "empty"
        if z in ("industrial", "cathedral", "base_red", "low"):
            return z
        return "back"
    return cell_kind


def neighbours_damage(c, r):
    return any((c + dc, r + dr) in DAMAGE_CELLS for dc in (-1, 0, 1) for dr in (-1, 0, 1))


def block_modules(c, r, rnd):
    out = []
    dmg = (c, r) in DAMAGE_CELLS
    ruin = (c, r) == RUIN_CELL
    near = not dmg and neighbours_damage(c, r) and 0 <= c < N and 0 <= r < N
    for k in range(4):
        x = rnd.random()
        if ruin:
            L, I = rnd.choice(L_RUIN if x < 0.7 else L_BURNT), rnd.choice(I_RUIN)
        elif dmg:
            L = rnd.choice(L_RUIN) if x < 0.3 else rnd.choice(L_BURNT) if x < 0.8 else rnd.choice(L_OK)
            I = rnd.choice(I_RUIN) if rnd.random() < 0.35 else rnd.choice(I_BURNT) if rnd.random() < 0.6 else rnd.choice(I_OK)
        elif near:
            L = rnd.choice(L_BURNT) if x < 0.25 else rnd.choice(L_OK)
            I = rnd.choice(I_BURNT) if rnd.random() < 0.2 else rnd.choice(I_OK)
        else:
            L = rnd.choice(L_BURNT) if x < 0.015 else rnd.choice(L_OK)
            I = rnd.choice(I_OK)
        out.append((L, I))
    return out


def industrial_modules(rnd):
    """Random consumption of 07_industrial.generate_industrial_modules (values discarded)."""
    t = rnd.choice(["chimney", "warehouse", "watertower", "mixed"])
    if t == "chimney":
        for _ in range(rnd.randint(1, 2)):
            rnd.randint(0, 2)
            rnd.uniform(-80, 80)
            rnd.uniform(-80, 80)
    elif t == "warehouse":
        rnd.randint(0, 1)
        rnd.uniform(-60, 60)
        rnd.uniform(-60, 60)
        rnd.choice([0, 90])
    elif t == "watertower":
        rnd.randint(0, 1)
        rnd.uniform(-70, 70)
        rnd.uniform(-70, 70)
    else:
        rnd.randint(0, 1)
        rnd.randint(0, 2)


def base_cell(rnd):
    rnd.randint(0, 3)  # ground yaw; basegen.cell_layout has its own seeded stream


def low_cell(rnd):
    rnd.random()
    rnd.randint(0, 3)
    rnd.randint(0, 3)  # court fill: choice(LOW_COURT 4) -> randbelow(4)
    rnd.randint(0, 3)
    for _ in range(4):
        rnd.randint(0, 5)  # choice(LOW_L 6)
        rnd.randint(0, 3)  # choice(LOW_I 4)


def replay(variant):
    zone = zone_b1 if variant == "b1" else zone_b2
    cell_kind = make_cell_kind(zone)
    rnd = cg.rng(SEED)
    board = {}
    for r in range(CITY_ROWS[0], CITY_ROWS[1] + 1):
        for c in range(CITY_COLS[0], CITY_COLS[1] + 1):
            kind = cell_kind(c, r)
            if kind in ("plaza", "river", "champ", "empty", "cathedral"):
                continue
            if kind == "industrial":
                rnd.randint(0, 3)
                industrial_modules(rnd)
                continue
            if kind == "base_red":
                base_cell(rnd)
                continue
            if kind == "low":
                low_cell(rnd)
                continue
            if kind == "board":
                yaw_k = rnd.randint(0, 3)
                mods = block_modules(c, r, rnd)
                board["%d,%d" % (c, r)] = {"ground": yaw_k, "modules": [list(m) for m in mods]}
                continue
            if rnd.random() < 0.045:
                for gx in range(-3, 4):
                    for gy in range(-3, 4):
                        if abs(gx) + abs(gy) > 1 and rnd.random() < 0.8:
                            rnd.choice(TREES)
                            rnd.uniform(-3, 3)
                            rnd.uniform(-3, 3)
                            rnd.uniform(0, 360)
                            rnd.uniform(0.95, 1.25)
                continue
            rnd.random()
            rnd.randint(0, 3)
            rnd.randint(0, 5)
            rnd.randint(0, 3)
            block_modules(c, r, rnd)
    trees, cars = furniture(rnd, cell_kind)
    return board, trees, cars


def in_near(c, r):
    return -3 <= c <= 12 and -3 <= r <= 12


def ns_street_open(cell_kind, j, r):
    kw, ke = cell_kind(j + 3, r), cell_kind(j + 4, r)
    if kw == "plaza" and ke == "plaza":
        return False
    if kw == "cathedral" and ke == "cathedral":
        return False
    return True


def ew_street_open(cell_kind, i, c):
    ks, kn = cell_kind(c, i + 3), cell_kind(c, i + 4)
    if ks == "plaza" and kn == "plaza":
        return False
    if ks == "champ" and kn == "champ":
        return False
    if ks == "river" or kn == "river":
        return (200.0 * i) in BRIDGE_ROWS_X
    return True


def furniture(rnd, cell_kind):
    """Same random consumption as 05_city_layout.furniture(); returns board-region trees and cars."""
    rows, cols = CITY_ROWS, CITY_COLS
    trees, cars = [], []
    for j in range(cols[0] - 4, cols[1] - 2):
        y = 200.0 * j
        board_line = -4 <= j <= 4
        boulevard = board_line or j % 2 == 0
        for r in range(rows[0], rows[1] + 1):
            if not ns_street_open(cell_kind, j, r):
                continue
            xc = (r - 3.5) * CELL
            near = in_near(j + 3, r) or in_near(j + 4, r)
            for side in (-1.0, 1.0):
                cell = (j + 3 if side < 0 else j + 4, r)
                kind = cell_kind(*cell)
                if boulevard and (near or rnd.random() < 0.8):
                    for t in range(13):
                        if rnd.random() < 0.06:
                            continue
                        x = xc - 75.0 + 12.5 * t + rnd.uniform(-0.6, 0.6)
                        mesh = rnd.choice(TREES)
                        yaw = rnd.uniform(0, 360)
                        s = rnd.uniform(0.82, 1.0)
                        trees.append([mesh, x, y + side * TREE_OFF, cg.KERB_H, yaw, s])
                if near:
                    burnt = cell in DAMAGE_CELLS
                    for _ in range(rnd.randint(0, 3)):
                        x = xc + rnd.uniform(-70.0, 70.0)
                        yaw = (0.0 if side > 0 else 180.0) + (rnd.uniform(-35, 35) if burnt else rnd.uniform(-2, 2))
                        mesh = rnd.choice(CARS_BURNT) if burnt and rnd.random() < 0.7 else rnd.choice(CARS)
                        cars.append([mesh, x, y + side * CAR_OFF, 0.0, yaw, 1.0])
    for i in range(rows[0] - 4, rows[1] - 2):
        x = 200.0 * i
        for c in range(cols[0], cols[1] + 1):
            if not ew_street_open(cell_kind, i, c) or not (in_near(c, i + 3) or in_near(c, i + 4)):
                continue
            yc = (c - 3.5) * CELL
            if cell_kind(c, i + 3) == "river" or cell_kind(c, i + 4) == "river":
                continue
            for side in (-1.0, 1.0):
                cell = (c, i + 3 if side < 0 else i + 4)
                burnt = cell in DAMAGE_CELLS
                for _ in range(rnd.randint(0, 2)):
                    y = yc + rnd.uniform(-70.0, 70.0)
                    yaw = (90.0 if side < 0 else -90.0) + (rnd.uniform(-35, 35) if burnt else rnd.uniform(-2, 2))
                    mesh = rnd.choice(CARS_BURNT) if burnt and rnd.random() < 0.7 else rnd.choice(CARS)
                    cars.append([mesh, x + side * CAR_OFF, y, 0.0, yaw, 1.0])
    inside = lambda e: abs(e[1]) <= REGION and abs(e[2]) <= REGION  # noqa: E731
    rnd6 = lambda e: [e[0]] + [round(v, 6) for v in e[1:]]  # noqa: E731
    return [rnd6(e) for e in trees if inside(e)], [rnd6(e) for e in cars if inside(e)]


def main(argv):
    variant = argv[argv.index("--variant") + 1] if "--variant" in argv else "b1"
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(HERE, "board_frozen.json")
    board, trees, cars = replay(variant)
    data = {"source": "replay of the %s 05_city_layout.py random stream (freeze_board_b1.py), seed %d" % (variant.upper(), SEED),
            "region_m": REGION, "cells": board, "furniture": {"trees": trees, "cars": cars}}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("wrote", out, ":", len(board), "board cells,", len(trees), "trees,", len(cars), "cars")


if __name__ == "__main__":
    main(sys.argv[1:])
