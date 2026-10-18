"""Host-side (CPython + Pillow) texture preparation for the M3 imported buildings and aircraft.

Reads Saved/Staging/m3_models/<set>/manifest.json (written by blender_prepare_models.py) and produces
Saved/Staging/m3_models/<set>/ue/:
  * <slot>_D.png  base colour, longest side <= 1024 (aircraft insignia scrubbed, see SCRUB)
  * <slot>_N.png  normal map, <= 512
  * manifest_ue.json: per slot {base, normal, roughness (1 - mean gloss), metallic, glass}
Deterministic: same inputs -> same bytes.
Usage: python Tools/m3/prepare_textures.py [set ...]
"""
import json
import os
import re
import sys

from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODELS = os.path.join(ROOT, "Saved", "Staging", "m3_models")
SETS = ["AM229_025", "AM229_030", "AM229_037", "AM229_042", "Oushi", "Stuka", "SE5"]
MAX_BASE, MAX_NORMAL = 1024, 512

# Extremist insignia painted on the Stuka atlas (Body.dds, 2048^2) are painted over with the surrounding
# camouflage before the texture can reach UE. Boxes are in source pixels (x0, y0, x1, y1).
SCRUB = {
    ("Stuka", "Body"): [(170, 380, 290, 540), (1715, 100, 1855, 240), (575, 225, 700, 345), (1330, 515, 1455, 640)],
}
# Slot overrides where the source material does not reference its texture through a node we can follow.
OVERRIDE_BASE = {
    ("SE5", "DefaultWhite"): "texture.png", ("SE5", "transparent"): "texture.png", ("SE5", "transparentExt"): "texture.png",
}
SE5_TEX = "F:/AI/workbuddy/GiantessAutoChess/model/英国双翼战斗机_爱给网_aigei_com/WkMRB15NzSVOB8w3pKMpxqJ7p/RAF-S-E-5/textures"


def clean(name):
    return re.sub(r"[^A-Za-z0-9]", "_", name).strip("_")


def fit(im, limit):
    w, h = im.size
    s = min(1.0, float(limit) / max(w, h))
    return im if s >= 1.0 else im.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)


def scrub(im, boxes, src_size):
    sx, sy = im.size[0] / float(src_size[0]), im.size[1] / float(src_size[1])
    d = ImageDraw.Draw(im)
    for x0, y0, x1, y1 in boxes:
        # sample the camouflage just outside the box (left edge, mid height) and fill
        px = im.getpixel((max(0, int(x0 * sx) - 6), int((y0 + y1) / 2 * sy)))
        d.rectangle([int(x0 * sx), int(y0 * sy), int(x1 * sx), int(y1 * sy)], fill=px)
    return im


def run(name):
    base_dir = os.path.join(MODELS, name)
    man = json.load(open(os.path.join(base_dir, "manifest.json"), encoding="utf-8"))
    out = os.path.join(base_dir, "ue")
    os.makedirs(out, exist_ok=True)
    slots = {}
    for slot, rec in man["materials"].items():
        key = clean(slot)
        entry = {"slot": slot, "base": None, "normal": None, "roughness": 0.75, "metallic": 0.0,
                 "glass": bool(rec.get("glass")), "color": rec.get("color")}
        src_base = OVERRIDE_BASE.get((name, slot)) or rec.get("base")
        if src_base:
            p = os.path.join(base_dir, "tex", src_base)
            if not os.path.isfile(p) and name == "SE5":
                p = os.path.join(SE5_TEX, src_base)
            im = Image.open(p)
            src_size = im.size
            im = im.convert("RGB")
            if (name, slot) in SCRUB:
                im = scrub(im, SCRUB[(name, slot)], src_size)
            fit(im, MAX_BASE).save(os.path.join(out, key + "_D.png"), optimize=False)
            entry["base"] = key + "_D.png"
        if rec.get("normal"):
            im = Image.open(os.path.join(base_dir, "tex", rec["normal"])).convert("RGB")
            fit(im, MAX_NORMAL).save(os.path.join(out, key + "_N.png"), optimize=False)
            entry["normal"] = key + "_N.png"
        if rec.get("gloss"):
            g = Image.open(os.path.join(base_dir, "tex", rec["gloss"])).convert("L").resize((64, 64))
            mean = sum(g.getdata()) / (64.0 * 64.0 * 255.0)
            entry["roughness"] = round(min(0.95, max(0.08, 1.0 - mean)), 3)
        if entry["glass"]:
            entry["roughness"] = 0.06
        if name in ("Stuka", "SE5"):
            entry["roughness"] = 0.55
        slots[key] = entry
    json.dump({"set": name, "pieces": man["pieces"], "slots": slots}, open(os.path.join(out, "manifest_ue.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, sort_keys=True)
    print("TEX_OK", name, len(slots))


if __name__ == "__main__":
    for n in (sys.argv[1:] or SETS):
        run(n)
