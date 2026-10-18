#!/usr/bin/env python3
"""Host-side (Pillow): annotate every MMD slot with "cutout" when its base texture has real transparency.

Overlay layers (表情 expression decals, 目影, lashes, hair strands) carry their shape in the texture alpha; rendering them
opaque paints solid quads over the face. A texture is a cutout when >= 0.5 % of its pixels have alpha < 128.
Updates Saved/Staging/mmd_fbx/<id>/SK_MMD_<id>.json in place (slot["cutout"], slot["alphaFraction"]).

    python Tools/m4/mmd_texture_alpha.py
"""
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "Saved/Staging/mmd_fbx"


def alpha_fraction(path, cache={}):
    if path not in cache:
        im = Image.open(path)
        if im.mode not in ("RGBA", "LA", "PA") and "transparency" not in im.info:
            cache[path] = 0.0
        else:
            a = im.convert("RGBA").getchannel("A").resize((256, 256))
            cache[path] = sum(1 for v in a.getdata() if v < 128) / (256.0 * 256.0)
    return cache[path]


def main():
    for info_path in sorted(SRC.glob("char_*/SK_MMD_char_*.json")):
        info = json.loads(info_path.read_text(encoding="utf-8"))
        cut = 0
        for slot in info["slots"]:
            frac = alpha_fraction(info_path.parent / "tex" / slot["texture"]) if slot.get("texture") else 0.0
            slot["alphaFraction"] = round(frac, 4)
            slot["cutout"] = frac >= 0.005 or slot.get("alpha", 1.0) < 0.99
            cut += slot["cutout"]
        info_path.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
        print(info["name"], "slots", len(info["slots"]), "cutout", cut)


if __name__ == "__main__":
    main()
