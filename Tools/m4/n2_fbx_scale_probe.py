"""N2 (host-side, Pillow-free): export one staged MMD model three ways and let UE measure them.

The board's MMD units never draw because the FBX carries the metre->centimetre factor on the armature
object, which arrives in UE as a scale-100 root bone; the retargeted clips then write scale 1 on that
bone and shrink the mesh to about 1 %.  Three ways of writing the factor are compared here, all of
them through blender_mmd_to_fbx.py:

    local    --scale 0.08, FBX_SCALE_NONE      (what the project did until now)
    fbxall   --scale 0.08, FBX_SCALE_ALL       (factor goes to the FBX header instead of the nodes)
    cmetre   --scale 8.0, unit scale 0.01, FBX_SCALE_NONE
                                               (geometry is authored in centimetres, no factor at all)

Writes Saved/Staging/n2_scaleprobe/<variant>/SK_MMD_<id>.fbx and a JSON record of what Blender
exported.  The UE side (Tools/m4/ue_n2_scale_probe.py) imports each variant and measures the mesh
bounds and the reference-pose root bone scale -- the two things that must come out right.

    python Tools/m4/n2_fbx_scale_probe.py [--id char_101]
"""
import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLENDER = "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
SCRIPT = os.path.join(ROOT, "Tools", "m4", "blender_mmd_to_fbx.py")
OUT = os.path.join(ROOT, "Saved", "Staging", "n2_scaleprobe")

VARIANTS = {
    "local": ["--scale", "0.08", "--scale-mode", "none"],
    "fbxall": ["--scale", "0.08", "--scale-mode", "all"],
    "cmetre": ["--scale", "8.0", "--scale-mode", "none", "--unit-scale", "0.01"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", default="char_101")
    a = ap.parse_args()
    staged = json.load(open(os.path.join(ROOT, "Saved", "Staging", "mmd", "staged.json"), encoding="utf-8"))
    row = next(m for m in staged["models"] if m["characterId"] == a.id)
    pmx = os.path.join(ROOT, "Saved", "Staging", "mmd", row["mainPmx"])
    if not os.path.isfile(pmx):
        raise SystemExit("missing pmx: " + pmx)
    results = {}
    for name, extra in VARIANTS.items():
        out = os.path.join(OUT, name)
        cmd = [BLENDER, "--background", "--python", SCRIPT, "--",
               "--pmx", pmx, "--out", out, "--name", "SK_MMD_" + a.id] + extra
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        info_path = os.path.join(out, "SK_MMD_%s.json" % a.id)
        info = json.load(open(info_path, encoding="utf-8")) if os.path.isfile(info_path) else None
        fbx = os.path.join(out, "SK_MMD_%s.fbx" % a.id)
        results[name] = {
            "args": extra,
            "ok": proc.returncode == 0 and info is not None,
            "fbxBytes": os.path.getsize(fbx) if os.path.isfile(fbx) else None,
            "heightCm": info and info["height_cm"],
            "boundsCm": info and info["bounds_cm"],
            "rootBones": info and info["rootBones"],
        }
        print("SCALEPROBE", name, json.dumps(results[name], ensure_ascii=False))
        if not results[name]["ok"]:
            print(proc.stdout[-2000:])
            print(proc.stderr[-2000:])
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "probe.json"), "w", encoding="utf-8") as f:
        json.dump({"schema": "Tread.N2.FbxScaleProbe.v1", "characterId": a.id, "variants": results},
                  f, ensure_ascii=False, indent=1)
    return 0 if all(r["ok"] for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
