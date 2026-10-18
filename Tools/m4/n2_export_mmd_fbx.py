"""N2 (host-side): re-export every staged MMD model to FBX with the centimetre export settings.

Wraps Tools/m4/blender_mmd_to_fbx.py over Saved/Staging/mmd/staged.json, one Blender process per
model.  Until 2026-10-11 the 12 models were exported by hand as a one-off loop at scale 0.08, which
put the metre->centimetre factor on the armature node and cost the board its MMD units; this makes
that stage repeatable with the settings the scale probe measured.

    python Tools/m4/n2_export_mmd_fbx.py [--only char_1xx] [--force]

Skips a model whose FBX and sidecar already exist unless --force.  Writes
Saved/Reports/N2_MmdFbxExport.json.  Afterwards re-run mmd_texture_alpha.py (it annotates the sidecar
the export just rewrote), then ue_import_mmd.py --rebuild, ue_mmd_materials.py and n2_build_retarget.py.
"""
import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLENDER = "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
SCRIPT = os.path.join(ROOT, "Tools", "m4", "blender_mmd_to_fbx.py")
STAGING = os.path.join(ROOT, "Saved", "Staging", "mmd")
OUT = os.path.join(ROOT, "Saved", "Staging", "mmd_fbx")
REPORT = os.path.join(ROOT, "Saved", "Reports", "N2_MmdFbxExport.json")
LOG = os.path.join(ROOT, "Saved", "Logs", "n2_mmd_fbx_export.log")


def export_one(row):
    cid = row["characterId"]
    dest = os.path.join(OUT, cid)
    fbx = os.path.join(dest, "SK_MMD_%s.fbx" % cid)
    side = os.path.join(dest, "SK_MMD_%s.json" % cid)
    cmd = [BLENDER, "--background", "--python", SCRIPT, "--",
           "--pmx", os.path.join(STAGING, row["mainPmx"]), "--out", dest, "--name", "SK_MMD_" + cid]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    info = json.load(open(side, encoding="utf-8")) if os.path.isfile(side) else None
    ok = proc.returncode == 0 and info is not None and os.path.isfile(fbx)
    result = {"characterId": cid, "ok": ok, "fbx": fbx if ok else None,
              "heightCm": info and info.get("height_cm"), "bones": info and info.get("bones"),
              "slots": info and len(info.get("slots", [])), "units": info and info.get("units"),
              "yawDeg": info and info.get("yawDeg")}
    print("MMD_FBX", json.dumps(result, ensure_ascii=False))
    if not ok:
        print(proc.stdout[-1500:])
        print(proc.stderr[-1500:])
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    rows = json.load(open(os.path.join(STAGING, "staged.json"), encoding="utf-8"))["models"]
    rows = [r for r in rows if not a.only or r["characterId"] == a.only]
    if not rows:
        raise SystemExit("no staged model matched --only %s" % a.only)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    previous = {}
    if os.path.isfile(REPORT):
        previous = {r["characterId"]: r for r in json.load(open(REPORT, encoding="utf-8")).get("models", [])}
    done = []
    for row in rows:
        cid = row["characterId"]
        fbx = os.path.join(OUT, cid, "SK_MMD_%s.fbx" % cid)
        side = os.path.join(OUT, cid, "SK_MMD_%s.json" % cid)
        if not a.force and os.path.isfile(fbx) and os.path.isfile(side) and not a.only:
            print("MMD_FBX", cid, "kept (exists; --force to redo)")
            done.append(previous.get(cid, {"characterId": cid, "ok": True}))
            continue
        done.append(export_one(row))
    merged = dict(previous)
    merged.update({r["characterId"]: r for r in done})
    report = {"schema": "Tread.N2.MmdFbxExport.v1",
              "ok": all(r.get("ok") for r in merged.values()) and len(merged) == 12,
              "models": [merged[k] for k in sorted(merged)]}
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("N2_MMD_FBX", "PASS" if report["ok"] else "PARTIAL", len(merged))
    return 0 if all(r.get("ok") for r in done) else 1


if __name__ == "__main__":
    sys.exit(main())
