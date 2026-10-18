"""Build the single-file Tread UI prototype.

Inputs : Tools/ui_proto/tread_ui.src.html (template)
         Saved/UIPrototype/fonts/*.ttf      (make_fonts.py)
         Saved/UIPrototype/textures/*.png   (make_textures.py)
         Content/Data/Generated/Campaign16.json + LeaderRounds.json
Output : Saved/UIPrototype/Tread_UI_Prototype.html (fonts subset to the glyphs used, woff2 + textures inlined)

Usage: python Tools/ui_proto/build_ui_proto.py
"""
import base64
import io
import json
import os

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "Tools", "ui_proto", "tread_ui.src.html")
FONTS = os.path.join(ROOT, "Saved", "UIPrototype", "fonts")
TEX = os.path.join(ROOT, "Saved", "UIPrototype", "textures")
DATA = os.path.join(ROOT, "Content", "Data", "Generated")
OUT = os.path.join(ROOT, "Saved", "UIPrototype", "Tread_UI_Prototype.html")

# css family, weight, file, add Latin+Cyrillic ranges
FACES = [
    ("TSans", 900, "TreadSans-Black.ttf", True),
    ("TSans", 700, "TreadSans-Bold.ttf", True),
    ("TSans", 500, "TreadSans-Medium.ttf", True),
    ("TSerif", 900, "TreadSerif-Black.ttf", False),
    ("TCond", 600, "TreadCond-SemiBold.ttf", True),
    ("TMono", 500, "TreadMono-Medium.ttf", True),
    ("TMono", 800, "TreadMono-ExtraBold.ttf", True),
    ("TStencil", 900, "TreadStencil-Black.ttf", True),
    ("TRusso", 400, "TreadRusso-Regular.ttf", True),
]

TEXTURES = ["T_UI_Paper", "T_UI_Grain", "T_UI_Vignette", "T_UI_Logo", "T_UI_Disc", "T_UI_DiscShade",
            "T_UI_Stamp_Approved", "T_UI_Stamp_Cleared", "T_UI_Stamp_Ready", "T_UI_Stamp_Sortie",
            "T_UI_InkSplat", "T_UI_Giantess", "T_UI_GiantessInDisc", "T_UI_Hatch", "T_UI_Halftone", "T_UI_Scanlines"]

BASE_RANGES = set(range(0x20, 0x7F)) | set(range(0x400, 0x460)) | {0xB0, 0xB7, 0xD7, 0x2014, 0x2026, 0x2116}


def stages():
    camp = json.load(open(os.path.join(DATA, "Campaign16.json"), encoding="utf-8"))
    lead = json.load(open(os.path.join(DATA, "LeaderRounds.json"), encoding="utf-8"))
    leaders = {l["opponentId"]: l for l in lead["leaders"]}
    keep = ["index", "country", "landmark", "rule", "effect", "aiLevel", "garrisonBonus", "enemyHpBonus",
            "startGoldBonus", "incomeBonus", "damageTakenPercent", "prepareSecondsDelta"]
    out = []
    for s in camp["stages"]:
        row = {k: s[k] for k in keep}
        row["city"] = s["rule"].split("：")[0]
        l = leaders.get(s["leaderId"], {})
        row["leader"] = l.get("displayName", "").replace("（占位）", "")
        row["leaderSize"] = len(l.get("lineup", []))
        row["leaderHp"] = l.get("health", 0)
        out.append(row)
    return out


def subset_woff2(path, codepoints):
    font = TTFont(path)
    cmap = font.getBestCmap()
    cps = sorted(c for c in codepoints if c in cmap)
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    sub = subset.Subsetter(options=opts)
    sub.populate(unicodes=cps)
    sub.subset(font)
    buf = io.BytesIO()
    font.flavor = "woff2"
    font.save(buf)
    return buf.getvalue(), len(cps)


def data_uri(path, mime):
    with open(path, "rb") as fp:
        return "data:%s;base64,%s" % (mime, base64.b64encode(fp.read()).decode("ascii"))


def main():
    html = open(SRC, encoding="utf-8").read()
    html = html.replace("/*@STAGES@*/[]", json.dumps(stages(), ensure_ascii=False))
    used = {ord(ch) for ch in html if ord(ch) >= 0x20}

    faces = []
    report = []
    for fam, weight, fname, latin in FACES:
        cps = used | BASE_RANGES if latin else used
        blob, n = subset_woff2(os.path.join(FONTS, fname), cps)
        faces.append("@font-face{font-family:%s;font-weight:%d;font-style:normal;font-display:block;"
                     "src:url(data:font/woff2;base64,%s) format('woff2')}"
                     % (fam, weight, base64.b64encode(blob).decode("ascii")))
        report.append("%s %d: %d glyphs, %d KB" % (fam, weight, n, len(blob) // 1024))

    texvars = []
    for name in TEXTURES:
        if name == "T_UI_Paper":
            uri = data_uri(os.path.join(TEX, "T_UI_Paper.web.jpg"), "image/jpeg")
        else:
            uri = data_uri(os.path.join(TEX, name + ".png"), "image/png")
        texvars.append("--%s:url(%s);" % (name, uri))

    html = html.replace("/*@FONTFACES@*/", "\n".join(faces))
    html = html.replace("/*@TEXVARS@*/", "".join(texvars))
    with open(OUT, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(html)
    for r in report:
        print(r)
    print("wrote", OUT, os.path.getsize(OUT) // 1024, "KB")


if __name__ == "__main__":
    main()
