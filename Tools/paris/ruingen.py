"""B6 outer ruin ring generator (pure Python on geom.MeshBuilder, no `unreal` import; testable with CPython).

Block-local frame of haussmann.py (metres, pivot = block centre, street facades at +-81 m). Pieces:

    leaning_infill(seed, angle, damage)   the south mid-block building (haussmann.infill_lots) tipped 6-15 deg
                                          outward into the street about its courtyard-side base edge: the street
                                          side sinks below ground into a rubble mound, the top overhangs the
                                          sidewalk; ends are pulled in 0.35 m so the gap to the L arms stays open
    footprint(seed, side)                 "stamped block" centrepiece for the courtyard (radius <= 62 m): a 17 m
                                          barefoot print (115 m giant) pressed into a disc of flattened building
                                          debris, a pushed-up rim, floor slabs / zinc sheets / blocks on the disc
                                          and a ring of low-rise stubs toppled outward (<= 18 m, B2 low ceiling)
    cracked_road(seed)                    40 m x 16 m carriageway overlay: heaved, tilted asphalt plates over a
                                          dark crack bed (z >= 0.05 m, so it never shares a plane with the road)

Slots: haussmann.SLOTS + "asphalt" (MI_Ground_Asphalt) + "dust" (MI_Ground_Compacted, the pale floor of the print).
`python ruingen.py` prints sizes / heights / triangle counts and runs the coplanar-overlap audit of zfight_check.
"""
import math

import geom
import haussmann as hm
from geom import MeshBuilder, Z, norm, rng

SLOTS = hm.SLOTS + ["asphalt", "dust"]
SLOT_MATERIALS = dict(hm.SLOT_MATERIALS, asphalt="MI_Ground_Asphalt", dust="MI_Ground_Compacted")

FOOT_LEN = 17.0  # m, foot length of the 115 m giant (125 sec. 3.7)
LEAN_INSET = 0.35  # m pulled in at both ends of a leaning infill
LOW_MAX_H = hm.LOW_MAX_H

# name -> builder arguments (09_ruins.py builds exactly these)
LEANING = {"SM_Hsm_Leaning_%02d" % i: (4300 + 7 * i, a, d) for i, (a, d) in enumerate(((7.0, "burnt"), (10.0, None), (13.0, "burnt")))}
FOOTPRINTS = {"SM_Ruin_Footprint_%02d" % i: (9600 + 7 * i, 1 if i % 2 == 0 else -1) for i in range(4)}
CRACKS = {"SM_Ruin_CrackedRoad_%02d" % i: (9700 + 7 * i,) for i in range(3)}


# ---------------------------------------------------------------- helpers
def smoothstep(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3.0 - 2.0 * t)


def append_xformed(dst, src, fp, fn):
    """Append every slot of `src` to `dst` with points mapped by fp and normals by fn (proper rotations only)."""
    for s in src.used_slots():
        a, b = src.data[s], dst.data[s]
        base = len(b["p"])
        b["p"].extend(fp(p) for p in a["p"])
        b["n"].extend(norm(fn(n)) for n in a["n"])
        b["uv"].extend(a["uv"])
        b["c"].extend(a["c"])
        b["t"].extend((i + base, j + base, k + base) for i, j, k in a["t"])


def noise2(r, amp, waves=4, lo=0.15, hi=0.9):
    """Cheap deterministic 2D noise: sum of randomly oriented sine waves (wavelength 1/lo .. 1/hi m)."""
    terms = []
    for _ in range(waves):
        a = r.uniform(0, 2 * math.pi)
        f = r.uniform(lo, hi)
        terms.append((math.cos(a) * f, math.sin(a) * f, r.uniform(0, 2 * math.pi)))

    def fn(x, y):
        return amp * sum(math.sin(kx * x + ky * y + ph) for kx, ky, ph in terms) / waves
    return fn


def mound(mb, x0, x1, y0, y1, step, hf, slot_fn=None, keep=None):
    """Heightfield z = hf(x, y) over a rectangle, flat-shaded with true face normals; slot_fn(cx, cy) picks the slot
    per triangle (default rubble); keep(x, y) skips quads whose four corners are all outside."""
    nx = max(1, int(round((x1 - x0) / step)))
    ny = max(1, int(round((y1 - y0) / step)))
    xs = [x0 + (x1 - x0) * i / nx for i in range(nx + 1)]
    ys = [y0 + (y1 - y0) * j / ny for j in range(ny + 1)]
    hs = [[hf(x, y) for x in xs] for y in ys]
    for j in range(ny):
        for i in range(nx):
            if keep and not any(keep(xs[a], ys[b]) for a, b in ((i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1))):
                continue
            p00, p10 = (xs[i], ys[j], hs[j][i]), (xs[i + 1], ys[j], hs[j][i + 1])
            p11, p01 = (xs[i + 1], ys[j + 1], hs[j + 1][i + 1]), (xs[i], ys[j + 1], hs[j + 1][i])
            for tri in ((p00, p10, p11), (p00, p11, p01)):
                n = geom.newell(tri)
                if n[2] < 0:
                    n = geom.mul(n, -1)
                cx = (tri[0][0] + tri[1][0] + tri[2][0]) / 3.0
                cy = (tri[0][1] + tri[1][1] + tri[2][1]) / 3.0
                mb.poly(slot_fn(cx, cy) if slot_fn else "rubble", list(tri), n)


def chunk(mb, r, slot, c, size, flat=0.6, tilt=0.7):
    """One randomly oriented debris block centred at c (half size ~ size)."""
    ax = norm((r.uniform(-1, 1), r.uniform(-1, 1), r.uniform(-tilt, tilt)))
    ay = norm(geom.cross(Z, ax)) if abs(ax[2]) < 0.95 else (1.0, 0.0, 0.0)
    az = geom.cross(ax, ay)
    mb.obox(slot, c, ax, ay, az, size * r.uniform(0.9, 1.8), size, size * flat * r.uniform(0.6, 1.2))


def rot_y(theta):
    """Rotation about +y that tips +z towards +x."""
    c, s = math.cos(theta), math.sin(theta)
    return lambda p: (p[0] * c + p[2] * s, p[1], -p[0] * s + p[2] * c)


def rot_z(phi):
    c, s = math.cos(phi), math.sin(phi)
    return lambda p: (p[0] * c - p[1] * s, p[0] * s + p[1] * c, p[2])


# ---------------------------------------------------------------- leaning infill
def leaning_infill(seed, angle_deg, damage=None):
    """haussmann infill (south mid-block gap) tipped outward by angle_deg about its courtyard-side base edge."""
    r = rng(seed + 1)
    src = hm.piece_mesh(hm.infill_lots(seed, damage))
    th = math.radians(angle_deg)
    c, s = math.cos(th), math.sin(th)
    k = (hm.GAP - LEAN_INSET) / hm.GAP
    pivot = -hm.INNER

    def fp(p):
        y, z = p[1] - pivot, p[2]
        return (p[0] * k, pivot + y * c - z * s, y * s + z * c)

    def fn(n):
        return (n[0], n[1] * c - n[2] * s, n[1] * s + n[2] * c)

    mb = MeshBuilder(SLOTS)
    append_xformed(mb, src, fp, fn)
    # rubble mound burying the sunken street side (facade meets the ground at y ~ -INNER - DEPTH / cos(angle))
    y_f = pivot - hm.DEPTH / c
    nz = noise2(r, 0.35, lo=0.4, hi=1.2)
    peak = r.uniform(2.6, 3.6)

    def hf(x, y):
        a = smoothstep(y_f - 8.5, y_f - 1.5, y)
        b = 1.0 - smoothstep(hm.GAP - 1.5, hm.GAP + 2.5, abs(x))
        return -0.2 + a * b * (peak + nz(x, y))
    mound(mb, -hm.GAP - 2.5, hm.GAP + 2.5, y_f - 9.0, y_f + 2.0, 0.8, hf)
    for _ in range(46):
        x, y = r.uniform(-hm.GAP - 1.0, hm.GAP + 1.0), r.uniform(y_f - 9.0, y_f)
        chunk(mb, r, "stone" if r.random() < 0.45 else ("char" if r.random() < 0.3 else "rubble"), (x, y, max(0.1, hf(x, y))), r.uniform(0.25, 0.8))
    for _ in range(5):  # snapped joists / beams sticking out of the heap
        x, y = r.uniform(-hm.GAP, hm.GAP), r.uniform(y_f - 5.0, y_f)
        chunk(mb, r, "char", (x, y, hf(x, y) + 0.6), 0.12, flat=1.0, tilt=0.9)
    return mb


# ---------------------------------------------------------------- giant footprint
# Sole parts / toes in units of the foot length: heel at -x, toes at +x, big toe on +y (right foot).
SOLE = ((-0.34, -0.010, 0.150, 0.125), (-0.07, -0.075, 0.220, 0.075), (0.17, 0.0, 0.120, 0.190), (0.18, 0.08, 0.090, 0.110))
TOES = ((0.405, 0.105, 0.085, 0.072), (0.400, 0.012, 0.048, 0.039), (0.375, -0.055, 0.040, 0.033),
        (0.345, -0.115, 0.036, 0.030), (0.305, -0.165, 0.032, 0.027))


def ellipse_d(x, y, cx, cy, rx, ry):
    return (math.hypot((x - cx) / rx, (y - cy) / ry) - 1.0) * min(rx, ry)


def smin(a, b, k):
    h = max(k - abs(a - b), 0.0) / k
    return min(a, b) - h * h * k * 0.25


def foot_d(x, y, side=1, length=FOOT_LEN):
    """(sole distance, toe distance) in metres, negative inside; side=-1 mirrors to a left foot."""
    u, v = x / length, side * y / length
    ds = 1e9
    for cx, cy, rx, ry in SOLE:
        ds = smin(ds, ellipse_d(u, v, cx, cy, rx, ry), 0.05)
    dt = min(ellipse_d(u, v, cx, cy, rx, ry) for cx, cy, rx, ry in TOES)
    return ds * length, dt * length


def footprint(seed, side=1, disc_r=30.0):
    """Stamped-block centrepiece: footprint pressed into a flattened debris disc, ring of toppled low-rise stubs."""
    r = rng(seed)
    mb = MeshBuilder(SLOTS)
    nz = noise2(r, 0.32, waves=5, lo=0.25, hi=1.1)
    nz_big = noise2(r, 0.5, waves=3, lo=0.05, hi=0.12)
    sole_z, toe_z = 0.32, 0.75

    def h_out(x, y):
        rho = math.hypot(x, y)
        dome = 0.6 + 1.9 * math.sqrt(max(0.0, 1.0 - (rho / disc_r) ** 2))
        w = smoothstep(disc_r, disc_r - 5.0, rho)
        return -0.25 + w * (dome + 0.25 + nz(x, y) + nz_big(x, y))

    def hf(x, y):
        ds, dt = foot_d(x, y, side)
        h = h_out(x, y)
        d = min(ds, dt)
        h += 0.95 * math.exp(-((d - 0.9) / 1.5) ** 2) * smoothstep(-0.5, 0.4, d)  # rim pushed up around the print
        h = sole_z + (h - sole_z) * smoothstep(-0.35, 0.55, ds) if ds < 0.55 else h
        if dt < 0.55:
            h = min(h, toe_z + (h - toe_z) * smoothstep(-0.3, 0.5, dt))
        return h

    def slot(x, y):
        ds, dt = foot_d(x, y, side)
        return "dust" if min(ds, dt) < 0.1 else "rubble"

    mound(mb, -disc_r - 0.5, disc_r + 0.5, -disc_r - 0.5, disc_r + 0.5, 0.5, hf, slot,
          keep=lambda x, y: math.hypot(x, y) <= disc_r)
    # flattened building: floor slabs, zinc roof sheets and blocks lying on the disc (never in the print)
    def clear(x, y, m):
        return min(foot_d(x, y, side)) > m

    for _ in range(9):
        for _try in range(20):
            a, d = r.uniform(0, 2 * math.pi), r.uniform(12.0, disc_r - 4.0)
            x, y = d * math.cos(a), d * math.sin(a)
            if clear(x, y, 6.0):
                break
        ax = norm((math.cos(a + 1.3), math.sin(a + 1.3), r.uniform(-0.35, 0.35)))
        ay = norm(geom.cross(Z, ax))
        ay = norm((ay[0], ay[1], r.uniform(-0.3, 0.3)))
        az = norm(geom.cross(ax, ay))
        mb.obox("zinc" if r.random() < 0.3 else "court", (x, y, hf(x, y) + 0.35), ax, ay, az, r.uniform(2.5, 5.0), r.uniform(1.8, 3.2), 0.16)
    for _ in range(150):
        a, d = r.uniform(0, 2 * math.pi), disc_r * math.sqrt(r.uniform(0.02, 0.9))
        x, y = d * math.cos(a), d * math.sin(a)
        if not clear(x, y, 1.2):
            continue
        sl = r.random()
        chunk(mb, r, "stone" if sl < 0.4 else "court" if sl < 0.6 else "char" if sl < 0.75 else "rubble",
              (x, y, hf(x, y) + 0.1), r.uniform(0.3, 1.3))
    # ring of low-rise stubs toppled away from the print
    n = r.choice((7, 8, 9))
    phi0 = r.uniform(0, 2 * math.pi)
    for i in range(n):
        if r.random() < 0.15:
            continue  # gap in the ring
        phi = phi0 + 2 * math.pi * i / n + r.uniform(-0.15, 0.15)
        d, w = r.uniform(9.5, 12.0), r.uniform(12.0, 17.0)
        poly = [(-d / 2, -w / 2), (d / 2, -w / 2), (d / 2, w / 2), (-d / 2, w / 2)]
        x = r.random()
        dmg = "collapsed" if x < 0.35 else "burnt" if x < 0.8 else None
        lot = hm.Lot(poly, ["court"] * 4, r, 3 if r.random() < 0.7 else 2, damage=dmg, low=True)
        tmp = MeshBuilder(hm.SLOTS)
        hm.build_lot(tmp, lot)
        tilt = math.radians(r.uniform(12.0, 30.0) if dmg != "collapsed" else r.uniform(4.0, 12.0))
        ry, rz = rot_y(tilt), rot_z(phi)
        rho = disc_r + r.uniform(6.5, 12.0)
        ox, oy = rho * math.cos(phi), rho * math.sin(phi)

        def fp(p, ry=ry, rz=rz, ox=ox, oy=oy, d=d):
            q = ry((p[0] + d / 2, p[1], p[2]))
            q = rz((q[0] - d / 2, q[1], q[2]))
            return (q[0] + ox, q[1] + oy, q[2])

        append_xformed(mb, tmp, fp, lambda nn, ry=ry, rz=rz: rz(ry(nn)))
        # debris skirt in front of the fallen stub
        for _ in range(14):
            t = r.uniform(-w / 2, w / 2)
            s = r.uniform(d / 2, d / 2 + 7.0)
            q = rz((s - d / 2, t, 0.0))
            chunk(mb, r, "rubble" if r.random() < 0.6 else "stone", (q[0] + ox, q[1] + oy, r.uniform(0.0, 0.5)), r.uniform(0.4, 1.2))
    return mb


# ---------------------------------------------------------------- cracked carriageway
def cracked_road(seed, length=40.0, hw=8.0, z0=0.05):
    """Heaved asphalt plates (two rows split by a wandering longitudinal crack) over a dark crack bed, local x along
    the street. Plates at the segment ends stay nearly flat so they meet the intact road."""
    r = rng(seed)
    mb = MeshBuilder(SLOTS)
    mb.poly("char", [(-length / 2, -hw, z0), (length / 2, -hw, z0), (length / 2, hw, z0), (-length / 2, hw, z0)], Z)
    n = r.randint(4, 6)
    cuts = []
    for i in range(n + 1):
        x = -length / 2 + length * i / n
        if 0 < i < n:
            x += r.uniform(-0.25, 0.25) * length / n
            cuts.append((x + r.uniform(-2.5, 2.5), x + r.uniform(-1.5, 1.5), x + r.uniform(-2.5, 2.5), r.uniform(-1.8, 1.8)))
        else:
            cuts.append((x, x, x, 0.0))
    for i in range(n):
        a, b = cuts[i], cuts[i + 1]
        end = i == 0 or i == n - 1
        for row in (-1, 1):
            if row < 0:
                pts = [(a[0], -hw), (b[0], -hw), (b[1], b[3]), (a[1], a[3])]
            else:
                pts = [(a[1], a[3]), (b[1], b[3]), (b[2], hw), (a[2], hw)]
            gap = [r.uniform(0.12, 0.3) for _ in range(4)]
            # outer edges (kerb side, segment ends) stay closed
            if row < 0:
                gap[0] = 0.0
            else:
                gap[2] = 0.0
            if i == 0:
                gap[3] = 0.0
            if i == n - 1:
                gap[1] = 0.0
            pts = geom.inset_polygon(pts, gap)
            cx = sum(p[0] for p in pts) / 4.0
            cy = sum(p[1] for p in pts) / 4.0
            heave = not end and r.random() < 0.45
            sl = r.uniform(0.03, 0.085) if heave else r.uniform(0.0, 0.008)
            ua = r.uniform(0, 2 * math.pi)
            u = (math.cos(ua), math.sin(ua))
            lift = [sl * ((p[0] - cx) * u[0] + (p[1] - cy) * u[1]) for p in pts]
            t0 = max(r.uniform(0.06, 0.16) if not end else 0.06, 0.05 - min(lift))
            top = [(p[0], p[1], z0 + t0 + l) for p, l in zip(pts, lift)]
            mb.poly("asphalt", top, norm((-sl * u[0], -sl * u[1], 1.0)))
            for k in range(4):
                p, q = top[k], top[(k + 1) % 4]
                sn = geom.seg_normal(p, q)
                mb.poly("asphalt", [(p[0], p[1], z0), (q[0], q[1], z0), q, p], (sn[0], sn[1], 0.0))
    for _ in range(r.randint(10, 18)):
        c = cuts[r.randint(1, n - 1)]
        x = r.uniform(min(c[:3]), max(c[:3])) + r.uniform(-1.5, 1.5)
        y = r.uniform(-hw + 0.5, hw - 0.5)
        chunk(mb, r, "asphalt" if r.random() < 0.7 else "rubble", (x, y, z0 + 0.15), r.uniform(0.18, 0.55), flat=0.45)
    return mb


# ---------------------------------------------------------------- CPython audit
def build_all():
    out = {}
    for name, (seed, ang, dmg) in LEANING.items():
        out[name] = leaning_infill(seed, ang, dmg)
    for name, (seed, side) in FOOTPRINTS.items():
        out[name] = footprint(seed, side)
    for name, (seed,) in CRACKS.items():
        out[name] = cracked_road(seed)
    return out


def audit():
    """Sizes / heights / triangle counts and the zfight_check coplanar audit of every piece (and of each leaning
    infill assembled with a standard L pair, as 05_city_layout places it). Returns a JSON-able dict."""
    import zfight_check as zf
    rep = {}
    meshes = build_all()
    l_left = hm.l_piece(1100)
    for name, mb in meshes.items():
        lo, hi = mb.bounds()
        tris = zf.tris_of(mb, 0, 0.0, "P")
        if name in LEANING:
            tris += zf.tris_of(l_left, 0, 0.0, "L0") + zf.tris_of(l_left, 3, 0.0, "L3")
        hits, _ = zf.audit(tris)
        rep[name] = {"tris": mb.tri_count(), "slots": mb.used_slots(), "min": [round(v, 2) for v in lo],
                     "max": [round(v, 2) for v in hi], "zfight_m2": round(sum(hits.values()), 2), "zfight_pairs": len(hits)}
    return rep


if __name__ == "__main__":
    import json
    import time

    t0 = time.time()
    rep = audit()
    for k, v in rep.items():
        print("%-26s tris %6d  z %.2f..%.2f  x %.1f..%.1f  y %.1f..%.1f  zfight %.2f m2 / %d" % (
            k, v["tris"], v["min"][2], v["max"][2], v["min"][0], v["max"][0], v["min"][1], v["max"][1], v["zfight_m2"], v["zfight_pairs"]))
    print("%.1fs" % (time.time() - t0))
