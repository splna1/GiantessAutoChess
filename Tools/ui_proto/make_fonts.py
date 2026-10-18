"""Instantiate the OFL variable fonts used by the Tread UI prototype into static TTFs.

Output (Saved/UIPrototype/fonts/) is the full-glyph set that the UE port imports as
UFontFace assets; build_ui_proto.py subsets these same files for the HTML prototype.

Usage: python Tools/ui_proto/make_fonts.py
"""
import os
import sys
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "Saved", "UIPrototype", "fonts_src")
OUT = os.path.join(ROOT, "Saved", "UIPrototype", "fonts")

# (source file, weight or None for static, output name)
FACES = [
    ("NotoSansSC-VF.ttf", 900, "TreadSans-Black.ttf"),
    ("NotoSansSC-VF.ttf", 700, "TreadSans-Bold.ttf"),
    ("NotoSansSC-VF.ttf", 500, "TreadSans-Medium.ttf"),
    ("NotoSerifSC-VF.ttf", 900, "TreadSerif-Black.ttf"),
    ("Oswald-VF.ttf", 600, "TreadCond-SemiBold.ttf"),
    ("JetBrainsMono-VF.ttf", 500, "TreadMono-Medium.ttf"),
    ("JetBrainsMono-VF.ttf", 800, "TreadMono-ExtraBold.ttf"),
    ("BigShouldersStencilDisplay-VF.ttf", 900, "TreadStencil-Black.ttf"),
    ("RussoOne-Regular.ttf", None, "TreadRusso-Regular.ttf"),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    only = set(sys.argv[1:])
    for src, weight, out in FACES:
        if only and out not in only:
            continue
        dst = os.path.join(OUT, out)
        font = TTFont(os.path.join(SRC, src))
        if weight is not None:
            font = instancer.instantiateVariableFont(font, {"wght": weight})
        font.save(dst)
        print("wrote", out, os.path.getsize(dst))


if __name__ == "__main__":
    main()
