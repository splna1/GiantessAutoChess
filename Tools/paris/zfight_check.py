"""Z-fighting audit for Haussmann blocks (pure CPython, no `unreal`).

Assembles one full block (4 L-corners + 4 infills rotated 0/90/180/270, exactly like 05_city_layout.py) and
reports coplanar, same-facing triangles that overlap in area -- the surfaces that flicker in the viewport.
Also checks each piece against itself (overlapping bands / boxes inside one module).

Usage: python Tools/paris/zfight_check.py [--l SEED] [--i SEED] [--damage burnt|collapsed] [--low]
       --low audits the B2 low-rise modules (default seeds = first SM_Hsm_LowL / SM_Hsm_LowInfill)
"""
import math
import sys
from collections import defaultdict

import haussmann as hm

EPS_N = 1e-3  # normal tolerance
EPS_D = 0.004  # plane distance tolerance (m); the 1 cm infill lift is above this
CELL = 2.0  # spatial hash cell (m)


def rot(p, k):
    c, s = [(1, 0), (0, 1), (-1, 0), (0, -1)][k % 4]
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c, p[2])


def tris_of(mb, k, dz, src):
    out = []
    for slot, d in mb.data.items():
        P = d["p"]
        for a, b, c in d["t"]:
            A, B, C = (rot(P[i], k) for i in (a, b, c))
            A, B, C = (A[0], A[1], A[2] + dz), (B[0], B[1], B[2] + dz), (C[0], C[1], C[2] + dz)
            u = (B[0] - A[0], B[1] - A[1], B[2] - A[2])
            v = (C[0] - A[0], C[1] - A[1], C[2] - A[2])
            n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            ln = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
            if ln < 1e-6:
                continue
            n = (n[0] / ln, n[1] / ln, n[2] / ln)
            out.append((src, slot, (A, B, C), n, ln / 2.0))
    return out


def basis(n):
    a = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = (n[1] * a[2] - n[2] * a[1], n[2] * a[0] - n[0] * a[2], n[0] * a[1] - n[1] * a[0])
    lu = math.sqrt(sum(x * x for x in u))
    u = tuple(x / lu for x in u)
    v = (n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2], n[0] * u[1] - n[1] * u[0])
    return u, v


def inside(p, t):
    (ax, ay), (bx, by), (cx, cy) = t
    d1 = (p[0] - bx) * (ay - by) - (ax - bx) * (p[1] - by)
    d2 = (p[0] - cx) * (by - cy) - (bx - cx) * (p[1] - cy)
    d3 = (p[0] - ax) * (cy - ay) - (cx - ax) * (p[1] - ay)
    e = 1e-7
    return not ((d1 < -e or d2 < -e or d3 < -e) and (d1 > e or d2 > e or d3 > e))


def samples(t):
    (ax, ay), (bx, by), (cx, cy) = t
    out = []
    for w in ((1 / 3, 1 / 3, 1 / 3), (0.7, 0.15, 0.15), (0.15, 0.7, 0.15), (0.15, 0.15, 0.7)):
        out.append((ax * w[0] + bx * w[1] + cx * w[2], ay * w[0] + by * w[1] + cy * w[2]))
    return out


def audit(tris, min_area=0.02):
    planes = defaultdict(list)
    for t in tris:
        src, slot, (A, B, C), n, area = t
        if area < min_area:
            continue
        key = (round(n[0] / EPS_N / 5), round(n[1] / EPS_N / 5), round(n[2] / EPS_N / 5),
               round((n[0] * A[0] + n[1] * A[1] + n[2] * A[2]) / (EPS_D * 2)))
        planes[key].append(t)
    hits = defaultdict(float)
    where = {}
    for key, group in planes.items():
        if len(group) < 2:
            continue
        n = group[0][3]
        u, v = basis(n)
        proj = [tuple((p[0] * u[0] + p[1] * u[1] + p[2] * u[2], p[0] * v[0] + p[1] * v[1] + p[2] * v[2]) for p in g[2]) for g in group]
        grid = defaultdict(list)
        for i, t2 in enumerate(proj):
            xs, ys = [p[0] for p in t2], [p[1] for p in t2]
            for gx in range(int(math.floor(min(xs) / CELL)), int(math.floor(max(xs) / CELL)) + 1):
                for gy in range(int(math.floor(min(ys) / CELL)), int(math.floor(max(ys) / CELL)) + 1):
                    grid[(gx, gy)].append(i)
        for i, t2 in enumerate(proj):
            for s in samples(t2):
                cand = grid.get((int(math.floor(s[0] / CELL)), int(math.floor(s[1] / CELL))), ())
                hit = next((j for j in cand if j != i and inside(s, proj[j]) and not shares_edge_only(proj[i], proj[j])), None)
                if hit is not None:
                    a, b = group[i], group[hit]
                    pair = tuple(sorted((a[0] + ":" + a[1], b[0] + ":" + b[1])))
                    hits[pair] += a[4] / 4.0
                    where.setdefault(pair, a[2][0])
    return hits, where


def shares_edge_only(t1, t2):
    return False


def main(argv):
    low = "--low" in argv
    ls = int(argv[argv.index("--l") + 1]) if "--l" in argv else (hm.LOW_SEEDS["lowl"][0] if low else 1100)
    iseed = int(argv[argv.index("--i") + 1]) if "--i" in argv else (hm.LOW_SEEDS["lowinfill"][0] if low else 4100)
    dmg = argv[argv.index("--damage") + 1] if "--damage" in argv else None
    dz = 0.01 if "--lift" in argv else 0.0
    L = hm.l_piece(ls, dmg, low)
    I = hm.infill_piece(iseed, dmg, low)
    print("low-rise" if low else "standard", "L seed", ls, "infill seed", iseed, "max z %.2f m" % max(L.bounds()[1][2], I.bounds()[1][2]))
    tris = []
    for k in range(4):
        tris += tris_of(L, k, 0.0, "L%d" % k)
        tris += tris_of(I, k, dz, "I%d" % k)
    print("triangles", len(tris))
    hits, where = audit(tris)
    tot = 0.0
    for pair, area in sorted(hits.items(), key=lambda kv: -kv[1])[:40]:
        w = where[pair]
        print("  %-34s %8.2f m2  near (%.1f, %.1f, %.1f)" % (" vs ".join(pair), area, w[0], w[1], w[2]))
        tot += area
    print("overlapping coplanar area (approx) %.1f m2 in %d pairs" % (sum(hits.values()), len(hits)))


if __name__ == "__main__":
    main(sys.argv[1:])
