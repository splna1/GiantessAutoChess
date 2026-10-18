"""Generate every bitmap used by the Tread UI prototype (Ursus constructivist style).

All outputs are deterministic (fixed seeds). The same PNGs are embedded into the HTML
prototype by build_ui_proto.py and imported into UE as UI textures during the port, so
the browser and the engine draw identical pixels.

Mask-style textures (logo, stamps, hatch, halftone, splat) are white RGB + alpha and are
tinted at draw time (CSS mask + background colour / Slate brush tint).

Usage: python Tools/ui_proto/make_textures.py
"""
import json
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "Saved", "UIPrototype", "textures")
FONTS = os.path.join(ROOT, "Saved", "UIPrototype", "fonts")

PAPER = (227, 213, 184)
PAPER_LIGHT = (239, 230, 211)
PAPER_DARK = (196, 177, 141)
INK = (22, 18, 15)
BURN = (150, 116, 78)


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def pnoise(h, w, sigma, rng):
    """Tileable gaussian-filtered white noise with unit standard deviation."""
    n = rng.standard_normal((h, w))
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    g = np.exp(-2.0 * (math.pi ** 2) * (sigma ** 2) * (fx ** 2 + fy ** 2))
    out = np.real(np.fft.ifft2(np.fft.fft2(n) * g))
    return out / (out.std() + 1e-9)


def blur(a, radius):
    im = Image.fromarray(np.clip(a * 255.0, 0, 255).astype(np.uint8), "L")
    return np.asarray(im.filter(ImageFilter.GaussianBlur(radius)), dtype=np.float64) / 255.0


def downsample(a, factor):
    im = Image.fromarray(np.clip(a * 255.0, 0, 255).astype(np.uint8), "L")
    im = im.resize((a.shape[1] // factor, a.shape[0] // factor), Image.LANCZOS)
    return np.asarray(im, dtype=np.float64) / 255.0


def save_mask(alpha, name, manifest, usage, tiling="None"):
    a = np.clip(alpha * 255.0 + 0.5, 0, 255).astype(np.uint8)
    rgba = np.dstack([np.full_like(a, 255)] * 3 + [a])
    path = os.path.join(OUT, name + ".png")
    Image.fromarray(rgba, "RGBA").save(path, optimize=True)
    manifest[name] = {"size": [a.shape[1], a.shape[0]], "kind": "mask(white+alpha, tint at draw)",
                      "tiling": tiling, "usage": usage}
    print("wrote", name, a.shape[1], a.shape[0], os.path.getsize(path))


def save_rgba(rgb, alpha, name, manifest, usage, tiling="None"):
    a = np.clip(alpha * 255.0 + 0.5, 0, 255).astype(np.uint8)
    c = np.clip(rgb + 0.5, 0, 255).astype(np.uint8)
    path = os.path.join(OUT, name + ".png")
    Image.fromarray(np.dstack([c, a]), "RGBA").save(path, optimize=True)
    manifest[name] = {"size": [a.shape[1], a.shape[0]], "kind": "rgba", "tiling": tiling, "usage": usage}
    print("wrote", name, a.shape[1], a.shape[0], os.path.getsize(path))


def roughen(mask, rng, amp=0.2, sigma=2.0, edge_radius=5.0, voids=0.0, pressure=0.0, pressure_sigma=60.0,
            bleed=0.0):
    """Ink-print edges: multi-scale noise displaces the 0.5 iso-line near edges; low-pressure areas
    break up into noisy voids (never smooth fades), plus optional coarse bleed wobble."""
    h, w = mask.shape
    m = blur(mask, 1.4)
    e = blur(mask, edge_radius)
    edge = np.clip(e * (1.0 - e) * 6.0, 0.0, 1.0)
    n = 0.55 * pnoise(h, w, sigma, rng) + 0.3 * pnoise(h, w, 0.8, rng)
    if bleed > 0:
        n = n + bleed * pnoise(h, w, sigma * 4.0, rng)
    out = smoothstep(0.45, 0.55, m + n * amp * edge)
    fine = pnoise(h, w, 1.0, rng)
    hole = np.zeros_like(out)
    if voids > 0:
        hole = np.maximum(hole, smoothstep(3.3 - voids, 3.7 - voids, fine))
    if pressure > 0:
        p = pnoise(h, w, pressure_sigma, rng)
        lack = np.clip((p - (1.6 - 2.2 * pressure)) / 1.2, 0.0, 1.0)  # 0 = full pressure
        hole = np.maximum(hole, smoothstep(1.1 - 2.4 * lack, 1.5 - 2.4 * lack, fine) * (lack > 0.02))
        out *= 1.0 - 0.10 * lack
    return out * (1.0 - 0.96 * hole)


def text_tile(ch, fnt, box):
    """Render one glyph centred (by ink bbox) in a box x box L-image."""
    im = Image.new("L", (box, box), 0)
    d = ImageDraw.Draw(im)
    l, t, r, b = d.textbbox((0, 0), ch, font=fnt)
    d.text(((box - (r - l)) / 2 - l, (box - (b - t)) / 2 - t), ch, font=fnt, fill=255)
    return im


def draw_text_centered(canvas, text, fnt, cx, cy, tracking=0.0):
    """Draw a run of glyphs centred on (cx, cy); tracking is extra advance in px per glyph."""
    d = ImageDraw.Draw(canvas)
    widths = [fnt.getlength(ch) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    l, t, r, b = d.textbbox((0, 0), text, font=fnt)
    x = cx - total / 2
    y = cy - (b + t) / 2
    for ch, wch in zip(text, widths):
        d.text((x, y), ch, font=fnt, fill=255)
        x += wch + tracking


def arc_text(canvas, cx, cy, radius, text, fnt, center_deg, span_deg, bottom=False, size_box=120):
    """Glyphs evenly spread over an arc. Angles: 0 = top, clockwise. Top arcs keep glyph tops outward;
    bottom arcs keep glyph tops toward the centre so both read left-to-right."""
    arr = np.asarray(canvas, dtype=np.float64)
    adv = [fnt.getlength(ch) if ch != " " else fnt.size * 0.3 for ch in text]
    total = sum(adv)
    gap = (math.radians(span_deg) * radius - total) / max(1, len(text) - 1)
    span_used = (total + gap * (len(text) - 1)) / radius
    pos = 0.0
    for ch, a in zip(text, adv):
        mid = (pos + a / 2) / radius - span_used / 2
        pos += a + gap
        if ch == " ":
            continue
        ang = math.radians(center_deg) + (-mid if bottom else mid)
        rot = math.degrees(ang) + (180.0 if bottom else 0.0)
        tile = text_tile(ch, fnt, size_box).rotate(-rot, resample=Image.BICUBIC)
        x = int(round(cx + radius * math.sin(ang) - size_box / 2))
        y = int(round(cy - radius * math.cos(ang) - size_box / 2))
        t = np.asarray(tile, dtype=np.float64)
        arr[y:y + size_box, x:x + size_box] = np.maximum(arr[y:y + size_box, x:x + size_box], t)
    return Image.fromarray(arr.astype(np.uint8), "L")


def star_points(cx, cy, r_out, r_in, rot_deg=-90.0):
    pts = []
    for i in range(10):
        r = r_out if i % 2 == 0 else r_in
        a = math.radians(rot_deg + i * 36)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


# --------------------------------------------------------------------------------------
def make_paper(manifest):
    rng = np.random.default_rng(1917)
    h, w = 1080, 1920
    low = pnoise(h, w, 170, rng)
    mid = pnoise(h, w, 26, rng)
    fine = pnoise(h, w, 1.1, rng)
    stain = pnoise(h, w, 80, rng)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)

    img = np.ones((h, w, 3)) * np.array(PAPER, dtype=np.float64)
    lum = 5.0 * low + 3.2 * mid + 3.4 * fine
    img += lum[..., None] * np.array([1.0, 0.97, 0.9])

    s = smoothstep(1.3, 2.6, stain) * 0.30
    img = img * (1 - s[..., None]) + np.array(PAPER_DARK) * s[..., None]

    # Fold creases: a bright ridge beside a soft dark valley, one side slightly shaded.
    def crease(dist, strength):
        light = np.exp(-((dist + 1.3) ** 2) / 1.0) * 24.0
        dark = -np.exp(-((dist - 1.6) ** 2) / 2.6) * 20.0
        shade = np.where(dist > 0, -5.0 * np.exp(-dist / 90.0), 2.5 * np.exp(dist / 140.0))
        return (light + dark + shade) * strength

    sv = np.clip(0.72 + 0.32 * pnoise(h, w, 50, rng), 0.15, 1.0)
    dv = xx - (1112 + (yy - 540) * 0.011)
    dh = yy - (812 - (xx - 960) * 0.005)
    img += crease(dv, sv)[..., None]
    img += crease(dh, sv * 0.8)[..., None]

    # Paper fibres.
    fib = Image.new("L", (w, h), 128)
    d = ImageDraw.Draw(fib)
    for _ in range(4200):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        seg = rng.uniform(5, 26) / 3
        a = rng.uniform(0, math.pi)
        pts = [(x, y)]
        for _k in range(3):
            a += rng.normal(0, 0.35)
            x += math.cos(a) * seg
            y += math.sin(a) * seg
            pts.append((x, y))
        d.line(pts, fill=int(128 + rng.choice([-1, 1]) * rng.uniform(9, 22)), width=1)
    fib = fib.filter(ImageFilter.GaussianBlur(0.5))
    img += ((np.asarray(fib, dtype=np.float64) - 128.0) * 0.85)[..., None]

    # Burnt, handled edges.
    nx = (xx / (w - 1) - 0.5) * 2
    ny = (yy / (h - 1) - 0.5) * 2
    r = np.sqrt((nx * 0.94) ** 2 + ny ** 2)
    burn = smoothstep(0.9, 1.5, r + 0.07 * low) * 0.24
    img = img * (1 - burn[..., None]) + np.array(BURN) * burn[..., None]

    c = np.clip(img + 0.5, 0, 255).astype(np.uint8)
    Image.fromarray(c, "RGB").save(os.path.join(OUT, "T_UI_Paper.png"), optimize=True)
    Image.fromarray(c, "RGB").save(os.path.join(OUT, "T_UI_Paper.web.jpg"), quality=84, optimize=True)
    manifest["T_UI_Paper"] = {"size": [w, h], "kind": "rgb", "tiling": "None",
                              "usage": "full-screen paper base, every screen"}
    print("wrote T_UI_Paper")


def make_grain(manifest):
    rng = np.random.default_rng(2604)
    n = 1024

    def specks(sig, lo, hi, density):
        f = pnoise(n, n, sig, rng)
        return smoothstep(lo, hi, f) * (pnoise(n, n, 30, rng) > (1.0 - density))

    dark = np.maximum(specks(0.7, 2.9, 3.5, 1.6) * 0.75, specks(1.3, 2.9, 3.4, 0.9) * 0.5)
    light = np.maximum(specks(0.8, 2.8, 3.4, 1.6) * 0.85, specks(1.4, 2.8, 3.3, 0.9) * 0.55)
    mottle = smoothstep(0.4, 2.0, pnoise(n, n, 16, rng)) * 0.045
    # Composite: mottle (paper-light) first, specks over it.
    use_light = light > dark
    sp_a = np.where(use_light, light, dark)
    sp_rgb = np.where(use_light[..., None], np.array(PAPER_LIGHT, dtype=np.float64), np.array(INK, dtype=np.float64))
    out_a = sp_a + mottle * (1.0 - sp_a)
    rgb = sp_rgb * sp_a[..., None] + np.array(PAPER_LIGHT, dtype=np.float64) * (mottle * (1.0 - sp_a))[..., None]
    rgb = rgb / np.maximum(out_a, 1e-6)[..., None]
    save_rgba(rgb, out_a, "T_UI_Grain", manifest, "screen-wide print grain + ink mottle overlay above all content",
              "Both")


def make_disc(manifest):
    rng = np.random.default_rng(1918)
    s = 2
    D = 1024 * s
    yy, xx = (np.mgrid[0:D, 0:D].astype(np.float64) + 0.5)
    c = D / 2
    r = np.sqrt((xx - c) ** 2 + (yy - c) ** 2)
    disc = (r < D * 0.495).astype(np.float64)
    a = roughen(disc, rng, amp=0.12, sigma=2.5 * s, edge_radius=4 * s, bleed=0.8)
    save_mask(downsample(a, s), "T_UI_Disc", manifest, "solid disc (sun / white circle), tinted")

    # Halftone shading crescent: dot radius grows toward the lower-right rim, dots stay inside the disc.
    n = 1024
    cell = 22.0
    yy, xx = (np.mgrid[0:n * s, 0:n * s].astype(np.float64) + 0.5) / s
    u = (xx + yy) / math.sqrt(2) / cell
    v = (xx - yy) / math.sqrt(2) / cell
    du = (u - np.round(u)) * cell
    dv = (v - np.round(v)) * cell
    cu = np.round(u) * cell
    cv = np.round(v) * cell
    gx = (cu + cv) / math.sqrt(2)
    gy = (cu - cv) / math.sqrt(2)
    cc = n / 2
    rr = np.sqrt((gx - cc) ** 2 + (gy - cc) ** 2) / (n * 0.495)
    along = ((gx - cc) * 0.6 + (gy - cc) * 0.8) / (n * 0.495)
    k = np.clip((along - 0.05) / 0.8, 0, 1) * np.clip((1.0 - rr) / 0.12, 0, 1) * (rr < 0.97)
    dots = (np.sqrt(du ** 2 + dv ** 2) < k * cell * 0.46).astype(np.float64)
    save_mask(downsample(dots, s), "T_UI_DiscShade", manifest, "halftone crescent shading over T_UI_Disc, tinted")


def make_halftone(manifest):
    n, s = 24, 8
    N = n * s
    yy, xx = (np.mgrid[0:N, 0:N].astype(np.float64) + 0.5) / s

    def dist(cx, cy):
        dx = (xx - cx + n / 2) % n - n / 2
        dy = (yy - cy + n / 2) % n - n / 2
        return np.sqrt(dx * dx + dy * dy)

    a = (np.minimum(dist(0, 0), dist(12, 12)) < 3.6).astype(np.float64)
    a = a.reshape(n, s, n, s).mean(axis=(1, 3))
    save_mask(a, "T_UI_Halftone", manifest, "halftone shading inside colour blocks", "Both")


def make_hatch(manifest):
    n, s = 24, 8
    N = n * s
    yy, xx = (np.mgrid[0:N, 0:N].astype(np.float64) + 0.5) / s
    a = (((xx + yy) % 12.0) < 3.4).astype(np.float64)
    a = a.reshape(n, s, n, s).mean(axis=(1, 3))
    save_mask(a, "T_UI_Hatch", manifest, "45-degree hatch for locked / disabled states", "Both")


def make_scanlines(manifest):
    a = np.zeros((4, 4))
    a[0, :] = 0.55
    a[1, :] = 0.12
    save_mask(a, "T_UI_Scanlines", manifest, "scan band texture used by screen transitions", "Both")


def make_vignette(manifest):
    h, w = 270, 480
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    nx = (xx / (w - 1) - 0.5) * 2
    ny = (yy / (h - 1) - 0.5) * 2
    r = np.sqrt((nx * 0.9) ** 2 + ny ** 2)
    a = smoothstep(0.55, 1.4, r) * 0.42
    rgb = np.ones((h, w, 3)) * np.array((40, 24, 12), dtype=np.float64)
    save_rgba(rgb, a, "T_UI_Vignette", manifest, "stretched full-screen edge darkening")


def make_logo(manifest):
    rng = np.random.default_rng(1924)
    s = 2
    size = 600 * s
    f = font("TreadSans-Black.ttf", size)
    pad = 40 * s
    tracking = -0.05 * size
    text = "踏国"
    widths = [f.getlength(ch) for ch in text]
    probe = ImageDraw.Draw(Image.new("L", (10, 10)))
    l, t, r, b = probe.textbbox((0, 0), text, font=f)
    w = int(sum(widths) + tracking * (len(text) - 1) + 2 * pad)
    h = int((b - t) + 2 * pad)
    im = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(im)
    x = pad
    for ch, wch in zip(text, widths):
        d.text((x, pad - t), ch, font=f, fill=255)
        x += wch + tracking
    mask = np.asarray(im, dtype=np.float64) / 255.0

    # Stencil slit: one horizontal through-cut, placed on the row band (40-62% height) where the
    # thinner of the two glyphs carries the most ink, so the cut reads as deliberate, not as a gap.
    ys, xs = np.nonzero(mask > 0.5)
    top, bot = ys.min(), ys.max()
    th = int((bot - top) * 0.032)
    mid = w // 2
    best, y0 = -1.0, int(top + (bot - top) * 0.5)
    for y in range(int(top + (bot - top) * 0.40), int(top + (bot - top) * 0.62)):
        band = mask[y:y + th]
        cov = min(band[:, :mid].mean(), band[:, mid:].mean())
        if cov > best:
            best, y0 = cov, y
    mask[y0:y0 + th, :] = 0.0

    a = roughen(mask, rng, amp=0.16, sigma=2.2 * s, edge_radius=5 * s, voids=0.18, pressure=0.16,
                pressure_sigma=90 * s, bleed=0.9)
    a = downsample(a, s)
    save_mask(a, "T_UI_Logo", manifest, "title logo 踏国, stencil slit, tinted ink (+ red misregistration copy)")
    manifest["T_UI_Logo"]["slitY"] = round((y0 / s) / a.shape[0], 4)


def make_stamp_round(manifest, name, diameter, top_text, top_font, bottom_text, bottom_font, center_text,
                     center_font, center_size, seed, ring_size, star=True, top_span=150, bottom_span=96,
                     rough=1.0):
    rng = np.random.default_rng(seed)
    s = 2
    D = diameter * s
    c = D / 2
    im = Image.new("L", (D, D), 0)
    d = ImageDraw.Draw(im)
    R = D * 0.47
    d.ellipse([c - R, c - R, c + R, c + R], outline=255, width=int(D * 0.034))
    Ri = D * 0.335
    d.ellipse([c - Ri, c - Ri, c + Ri, c + Ri], outline=255, width=int(D * 0.014))
    rt = (R + Ri) / 2
    box = int(ring_size * s * 1.9)
    im = arc_text(im, c, c, rt, top_text, font(top_font, int(ring_size * s)), 0, top_span, size_box=box)
    im = arc_text(im, c, c, rt, bottom_text, font(bottom_font, int(ring_size * s * 0.92)), 180, bottom_span,
                  bottom=True, size_box=box)
    d = ImageDraw.Draw(im)
    for side in (-1, 1):  # separator stars between the arcs
        a = math.radians(100 * side)
        sx, sy = c + rt * math.sin(a), c - rt * math.cos(a)
        d.polygon(star_points(sx, sy, ring_size * s * 0.42, ring_size * s * 0.17), fill=255)
    if star:
        d.polygon(star_points(c, c - D * 0.19, D * 0.052, D * 0.021), fill=255)
    draw_text_centered(im, center_text, font(center_font, int(center_size * s)), c, c + D * 0.035,
                       tracking=-center_size * s * 0.02)
    d.rectangle([c - D * 0.17, c + D * 0.155, c + D * 0.17, c + D * 0.155 + D * 0.012], fill=255)
    mask = np.asarray(im, dtype=np.float64) / 255.0
    a = roughen(mask, rng, amp=0.16 * rough, sigma=1.6 * s, edge_radius=2.5 * s, voids=0.35 * rough,
                pressure=0.42 * rough, pressure_sigma=45 * s, bleed=0.5)
    save_mask(downsample(a, s), name, manifest, "red rubber stamp, tinted")


def make_badge_stamp(manifest, name, diameter, cn, ru, seed):
    """Small round stamp that must stay legible at ~100 px: no ring text, star dots on the ring band,
    bold centre text with a cyrillic line underneath."""
    rng = np.random.default_rng(seed)
    s = 2
    D = diameter * s
    c = D / 2
    im = Image.new("L", (D, D), 0)
    d = ImageDraw.Draw(im)
    R = D * 0.47
    d.ellipse([c - R, c - R, c + R, c + R], outline=255, width=int(D * 0.05))
    Ri = D * 0.36
    d.ellipse([c - Ri, c - Ri, c + Ri, c + Ri], outline=255, width=int(D * 0.022))
    rt = (R + Ri) / 2
    for k in range(10):
        a = math.radians(k * 36)
        d.polygon(star_points(c + rt * math.sin(a), c - rt * math.cos(a), D * 0.03, D * 0.012), fill=255)
    draw_text_centered(im, cn, font("TreadSans-Black.ttf", int(D * 0.2)), c, c - D * 0.04, tracking=-D * 0.004)
    draw_text_centered(im, ru, font("TreadRusso-Regular.ttf", int(D * 0.1)), c, c + D * 0.15, tracking=D * 0.01)
    mask = np.asarray(im, dtype=np.float64) / 255.0
    a = roughen(mask, rng, amp=0.12, sigma=1.4 * s, edge_radius=2 * s, voids=0.2, pressure=0.3,
                pressure_sigma=30 * s, bleed=0.4)
    save_mask(downsample(a, s), name, manifest, "small legible round stamp for cards, tinted")


def make_giantess(manifest):
    """Owner-supplied giantess-over-Tokyo silhouette (Saved/UIPrototype/source/giantess_silhouette_src.png).
    Its alpha already holds the ink; keep it as a white+alpha mask so each screen can tint it."""
    src = os.path.join(ROOT, "Saved", "UIPrototype", "source", "giantess_silhouette_src.png")
    a = np.asarray(Image.open(src).convert("RGBA"), dtype=np.float64)[..., 3] / 255.0
    h, w = a.shape
    rng = np.random.default_rng(1957)
    # Ragged ink break-up on the left/right 110 px so the skyline never ends in a straight cut.
    x = np.arange(w, dtype=np.float64)[None, :]
    ramp = np.minimum(np.clip(x / 110.0, 0, 1), np.clip((w - 1 - x) / 110.0, 0, 1))
    noise = smoothstep(-2.0, 2.0, pnoise(h, w, 1.6, rng) + 0.6 * pnoise(h, w, 12, rng))
    edged = a * (ramp > noise * 0.92)
    save_mask(edged, "T_UI_Giantess", manifest, "giantess over city silhouette (owner art), ragged sides, tinted")

    # Disc-cropped variant for the sortie sun: same 1024 frame as T_UI_Disc, figure scaled 0.95 * 0.84 of
    # the disc size and placed so the head sits inside the top of the circle; everything outside r=0.49 cut.
    N, s = 1024, 2
    D = N * s
    k = D / 860.0
    fw, fh = int(655 * k), int(817 * k)
    fig = Image.fromarray((edged * 255).astype(np.uint8), "L").resize((fw, fh), Image.LANCZOS)
    canvas = Image.new("L", (D, D), 0)
    canvas.paste(fig, (int(22 * k), int(40 * k)))
    yy, xx = np.mgrid[0:D, 0:D].astype(np.float64) + 0.5
    r = np.sqrt((xx - D / 2) ** 2 + (yy - D / 2) ** 2) / D
    disc = smoothstep(0.492, 0.488, r)
    out = np.asarray(canvas, dtype=np.float64) / 255.0 * disc
    save_mask(downsample(out, s), "T_UI_GiantessInDisc", manifest, "giantess cropped to the T_UI_Disc circle, tinted")


def make_stamp_rect(manifest, name, w, h, cn, ru, seed):
    rng = np.random.default_rng(seed)
    s = 2
    W, H = w * s, h * s
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    o = int(H * 0.06)
    d.rectangle([o, o, W - o, H - o], outline=255, width=int(H * 0.06))
    o2 = int(H * 0.16)
    d.rectangle([o2, o2, W - o2, H - o2], outline=255, width=int(H * 0.022))
    fcn = font("TreadSans-Black.ttf", int(H * 0.46))
    fru = font("TreadRusso-Regular.ttf", int(H * 0.31))
    cn_w = sum(fcn.getlength(ch) for ch in cn) - H * 0.02 * (len(cn) - 1)
    ru_w = fru.getlength(ru)
    gap = H * 0.12
    x0 = W / 2 - (cn_w + gap + ru_w) / 2
    draw_text_centered(im, cn, fcn, x0 + cn_w / 2, H / 2, tracking=-H * 0.02)
    draw_text_centered(im, ru, fru, x0 + cn_w + gap + ru_w / 2, H / 2)
    mask = np.asarray(im, dtype=np.float64) / 255.0
    a = roughen(mask, rng, amp=0.2, sigma=1.8 * s, edge_radius=3 * s, voids=0.4, pressure=0.45,
                pressure_sigma=50 * s, bleed=0.5)
    save_mask(downsample(a, s), name, manifest, "rectangular rubber stamp, tinted")


def make_splat(manifest):
    rng = np.random.default_rng(1941)
    s = 2
    D = 320 * s
    im = Image.new("L", (D, D), 0)
    d = ImageDraw.Draw(im)
    c = D / 2
    # Ink squeezed out at the rim of a slammed round stamp: a few small droplets just outside
    # radius ~0.47 D, clustered on two arcs, plus fine mist.
    for arc in (rng.uniform(0, 2 * math.pi), rng.uniform(0, 2 * math.pi)):
        for _ in range(5):
            ang = arc + rng.normal(0, 0.28)
            dist = D * (0.475 + abs(rng.normal(0, 0.025)))
            r = rng.uniform(2.0, 6.5) * s
            x, y = c + math.cos(ang) * dist, c + math.sin(ang) * dist
            d.ellipse([x - r, y - r, x + r, y + r], fill=255)
    for _ in range(16):
        ang = rng.uniform(0, 2 * math.pi)
        dist = D * rng.uniform(0.46, 0.5)
        r = rng.uniform(0.8, 1.8) * s
        x, y = c + math.cos(ang) * dist, c + math.sin(ang) * dist
        d.ellipse([x - r, y - r, x + r, y + r], fill=255)
    mask = np.asarray(im, dtype=np.float64) / 255.0
    a = roughen(mask, rng, amp=0.35, sigma=2.0 * s, edge_radius=4 * s, voids=0.2)
    save_mask(downsample(a, s), "T_UI_InkSplat", manifest, "ink droplets around a slammed stamp, tinted")


def main():
    os.makedirs(OUT, exist_ok=True)
    manifest = {}
    make_paper(manifest)
    make_grain(manifest)
    make_halftone(manifest)
    make_hatch(manifest)
    make_scanlines(manifest)
    make_vignette(manifest)
    make_disc(manifest)
    make_logo(manifest)
    make_stamp_round(manifest, "T_UI_Stamp_Approved", 520, "踏国行军档案终端", "TreadSans-Black.ttf",
                     "ОДОБРЕНО", "TreadRusso-Regular.ttf", "核准", "TreadSerif-Black.ttf", 132, 4170,
                     ring_size=40, top_span=150, bottom_span=92)
    make_badge_stamp(manifest, "T_UI_Stamp_Cleared", 300, "已攻克", "ВЗЯТО", 1945)
    make_stamp_rect(manifest, "T_UI_Stamp_Ready", 600, 200, "就绪", "ГОТОВО", 1961)
    make_stamp_rect(manifest, "T_UI_Stamp_Sortie", 600, 200, "出征", "В БОЙ", 1943)
    make_splat(manifest)
    make_giantess(manifest)
    with open(os.path.join(OUT, "textures_manifest.json"), "w", encoding="utf-8") as fp:
        json.dump(manifest, fp, ensure_ascii=False, indent=2)
    print("manifest", len(manifest))


if __name__ == "__main__":
    main()
