#!/usr/bin/env python3
"""Stage the owner's 12 MMD models (mmd_12/, read-only) into Saved/Staging/mmd/<characterId>/ with 7-Zip.

Reads Content/Data/Source/Roster112_Models.json (char_101..112, archivePrefix) and for each model:
  * extracts the archive whose name starts with archivePrefix into Saved/Staging/mmd/<id>/src/
  * picks the main PMX (largest .pmx; weapon/prop PMX files are listed separately)
  * copies the matching portrait PNG (mmd_12/<short name>.png) to Saved/Staging/mmd/<id>/portrait.png
Writes Saved/Staging/mmd/staged.json. Re-running skips archives already extracted.

    python Tools/m4/stage_mmd_models.py
"""
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "mmd_12"
OUT = ROOT / "Saved/Staging/mmd"
SEVEN = Path("C:/Program Files/7-Zip/7z.exe")
# portrait file stem per archive prefix (the owner's PNG names)
PORTRAIT = {"OTs14原皮": "OTS14", "_Agent_代理人原皮": "代理人", "克莱妲衣装濯浪焦点": "克莱妲", "莱娅女仆": "莱娅",
            "【异环】伊洛伊": "伊洛伊", "【异环】明音凛": "明音凛", "【异环】真红": "真红", "【异环】黑羽": "黑羽",
            "哈索尔": "哈索尔", "小吱": "小吱", "残虹": "残虹", "【异环】浔": "浔"}


def main():
    models = json.loads((ROOT / "Content/Data/Source/Roster112_Models.json").read_text(encoding="utf-8"))["models"]
    archives = sorted(p for p in SRC.iterdir() if p.suffix.lower() in (".zip", ".rar", ".7z"))
    staged = []
    for m in models:
        cid, prefix = m["characterId"], m["archivePrefix"]
        match = [a for a in archives if a.name.startswith(prefix + "_by_")]
        if len(match) != 1:
            raise SystemExit("%s: expected one archive for %s, found %s" % (cid, prefix, [a.name for a in match]))
        dest = OUT / cid / "src"
        if not dest.exists() or not any(dest.rglob("*.pmx")):
            dest.mkdir(parents=True, exist_ok=True)
            subprocess.run([str(SEVEN), "x", "-y", "-o" + str(dest), str(match[0])], check=True, capture_output=True)
        pmx = sorted(dest.rglob("*.pmx"), key=lambda p: (-p.stat().st_size, str(p)))
        portrait_src = SRC / (PORTRAIT[prefix] + ".png")
        if portrait_src.exists():
            shutil.copy2(portrait_src, OUT / cid / "portrait.png")
        staged.append({"characterId": cid, "modelName": m["modelName"], "archive": match[0].name,
                       "mainPmx": str(pmx[0].relative_to(OUT)).replace("\\", "/"),
                       "extraPmx": [str(p.relative_to(OUT)).replace("\\", "/") for p in pmx[1:]],
                       "portrait": "%s/portrait.png" % cid if portrait_src.exists() else None})
    (OUT / "staged.json").write_text(json.dumps({"models": staged}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for s in staged:
        print(s["characterId"], s["modelName"], s["mainPmx"], "portrait" if s["portrait"] else "-")


if __name__ == "__main__":
    main()
