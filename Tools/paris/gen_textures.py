#!/usr/bin/env python3
"""Host-side (plain CPython + Pillow) generator for the procedural textures of the Paris board.

Writes deterministic PNGs to Saved/Staging/Textures (seeded RNG, re-running gives identical files):
    T_Water_N.png      512^2 tileable tangent-space normal map (sum of integer-wavevector sines)
    T_SmokePuff.png    256^2 RGBA soft smoke puff (fractal noise inside a radial falloff)
    T_FlameTongue.png  128x256 RGBA flame tongue (distorted teardrop, hot core)
    T_Scorch.png       512^2 RGBA burnt-ground decal (radial soot + noise, alpha in A)
    T_StoneGrunge.png  512^2 tileable greyscale grunge (value noise fbm) for facade variation

Usage: python Tools/paris/gen_textures.py
"""
import math
import os
import random

from PIL import Image

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Saved", "Staging", "Textures")


class TileNoise:
    """Tileable value noise with period `per` lattice cells."""

    def __init__(self, per, seed):
        rnd = random.Random(seed)
        self.per = per
        self.g = [[rnd.random() for _ in range(per)] for _ in range(per)]

    def __call__(self, x, y):
        p = self.per
        xi, yi = math.floor(x), math.floor(y)
        fx, fy = x - xi, y - yi
        fx = fx * fx * (3 - 2 * fx)
        fy = fy * fy * (3 - 2 * fy)
        x0, y0 = xi % p, yi % p
        x1, y1 = (x0 + 1) % p, (y0 + 1) % p
        g = self.g
        a = g[y0][x0] + (g[y0][x1] - g[y0][x0]) * fx
        b = g[y1][x0] + (g[y1][x1] - g[y1][x0]) * fx
        return a + (b - a) * fy


def fbm(noises, u, v):
    """u,v in [0,1) -> fbm in ~[0,1]; noises = list of TileNoise with doubling periods."""
    s, amp, tot = 0.0, 1.0, 0.0
    for n in noises:
        s += amp * n(u * n.per, v * n.per)
        tot += amp
        amp *= 0.5
    return s / tot


def water_normal(size=512):
    rnd = random.Random(11)
    waves = []
    for _ in range(14):
        kx, ky = rnd.randint(-9, 9), rnd.randint(-9, 9)
        if kx == 0 and ky == 0:
            kx = 3
        amp = 1.0 / (math.hypot(kx, ky) ** 1.3)
        waves.append((kx, ky, amp, rnd.random() * 6.283))
    img = Image.new("RGB", (size, size))
    px = img.load()
    strength = 0.9
    for j in range(size):
        v = j / size
        for i in range(size):
            u = i / size
            dx = dy = 0.0
            for kx, ky, a, ph in waves:
                c = math.cos(6.283185 * (kx * u + ky * v) + ph) * a * 6.283185
                dx += c * kx
                dy += c * ky
            nx, ny, nz = -dx * strength / 40.0, -dy * strength / 40.0, 1.0
            ln = math.sqrt(nx * nx + ny * ny + nz * nz)
            px[i, j] = (int((nx / ln * 0.5 + 0.5) * 255), int((ny / ln * 0.5 + 0.5) * 255), int((nz / ln * 0.5 + 0.5) * 255))
    return img


def smoke_puff(size=256):
    ns = [TileNoise(p, 20 + p) for p in (4, 8, 16, 32)]
    img = Image.new("RGBA", (size, size))
    px = img.load()
    for j in range(size):
        for i in range(size):
            u, v = i / size, j / size
            r = math.hypot(u - 0.5, v - 0.5) * 2.0
            n = fbm(ns, u, v)
            fall = max(0.0, 1.0 - r) ** 1.4
            a = max(0.0, min(1.0, (fall * 1.6) * (0.35 + 0.9 * n) - 0.12))
            shade = 0.55 + 0.45 * n
            c = int(255 * shade)
            px[i, j] = (c, c, c, int(255 * a))
    return img


def flame_tongue(w=128, h=256):
    ns = [TileNoise(p, 40 + p) for p in (4, 8, 16)]
    img = Image.new("RGBA", (w, h))
    px = img.load()
    for j in range(h):
        t = 1.0 - j / (h - 1)  # 0 bottom -> 1 top
        for i in range(w):
            u = i / (w - 1) - 0.5
            n = fbm(ns, i / w, j / h)
            width = 0.42 * (1.0 - t) ** 0.7 * (0.35 + 0.65 * math.sin(min(1.0, t * 3.5) * 1.5708)) + 1e-3
            d = abs(u + (n - 0.5) * 0.25 * t) / width
            core = max(0.0, 1.0 - d)
            a = max(0.0, min(1.0, core ** 0.8 * (0.7 + 0.6 * n) * (1.0 - t ** 3)))
            heat = max(0.0, min(1.0, core * (1.2 - t)))
            r = 255
            g = int(255 * (0.35 + 0.6 * heat))
            b = int(255 * (0.08 + 0.55 * heat ** 3))
            px[i, j] = (r, g, b, int(255 * a))
    return img


def scorch(size=512):
    ns = [TileNoise(p, 60 + p) for p in (4, 8, 16, 32, 64)]
    img = Image.new("RGBA", (size, size))
    px = img.load()
    for j in range(size):
        for i in range(size):
            u, v = i / size, j / size
            n = fbm(ns, u, v)
            r = math.hypot(u - 0.5, v - 0.5) * 2.0 + (n - 0.5) * 0.55
            a = max(0.0, min(1.0, (1.0 - r) * 2.2))
            c = int(255 * (0.05 + 0.10 * n))
            px[i, j] = (c, int(c * 0.93), int(c * 0.85), int(255 * a * (0.55 + 0.45 * n)))
    return img


def stone_grunge(size=512):
    ns = [TileNoise(p, 80 + p) for p in (4, 8, 16, 32, 64, 128)]
    img = Image.new("L", (size, size))
    px = img.load()
    for j in range(size):
        for i in range(size):
            n = fbm(ns, i / size, j / size)
            px[i, j] = int(255 * max(0.0, min(1.0, (n - 0.5) * 1.8 + 0.5)))
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    jobs = [
        ("T_Water_N.png", water_normal),
        ("T_SmokePuff.png", smoke_puff),
        ("T_FlameTongue.png", flame_tongue),
        ("T_Scorch.png", scorch),
        ("T_StoneGrunge.png", stone_grunge),
    ]
    for name, fn in jobs:
        path = os.path.join(OUT, name)
        fn().save(path)
        print("wrote", path)


if __name__ == "__main__":
    main()
