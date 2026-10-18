"""M4 step 1 (host-side): stage and convert the roster VRMs into centimetre FBX + sidecar, several Blender processes at once.

For every char_0xx row of Saved/Reports/M4_VRM_Inventory.json (run Tools/m4/vrm_inventory.py first):
  * copy the read-only source .vrm to Saved/Staging/vrm100/<char_0xx>.vrm (never written back);
  * run Tools/m4/blender_vrm_to_fbx.py into Saved/Staging/vrm_fbx/<char_0xx>/.

char_001 is skipped: it is 416.vrm, the M1 hero Clukay416 itself, already imported by Tools/paris/08_vrm.py and
the source of every retarget.

    python Tools/m4/m4_export_vrm_fbx.py [--only char_002,char_003] [--force] [--jobs 4]

Skips a model whose FBX and sidecar already exist unless --force.  Report: Saved/Reports/M4_VrmFbxExport.json.
Next: ue_import_vrm.py, ue_vrm_materials.py, m4_build_retarget.py.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLENDER = "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
SCRIPT = os.path.join(ROOT, "Tools", "m4", "blender_vrm_to_fbx.py")
INVENTORY = os.path.join(ROOT, "Saved", "Reports", "M4_VRM_Inventory.json")
STAGING = os.path.join(ROOT, "Saved", "Staging", "vrm100")
OUT = os.path.join(ROOT, "Saved", "Staging", "vrm_fbx")
REPORT = os.path.join(ROOT, "Saved", "Reports", "M4_VrmFbxExport.json")
LOGS = os.path.join(ROOT, "Saved", "Logs", "m4_vrm_export")
HERO = "char_001"


def export_one(row):
    cid = row["characterId"]
    staged = os.path.join(STAGING, cid + ".vrm")
    if not os.path.isfile(staged) or os.path.getsize(staged) != os.path.getsize(row["source"]):
        shutil.copyfile(row["source"], staged)
    dest = os.path.join(OUT, cid)
    cmd = [BLENDER, "--background", "--python", SCRIPT, "--", "--vrm", staged, "--out", dest, "--name", "SK_VRM_" + cid]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    with open(os.path.join(LOGS, cid + ".log"), "w", encoding="utf-8") as f:
        f.write(proc.stdout + "\n----\n" + proc.stderr)
    side = os.path.join(dest, "SK_VRM_%s.json" % cid)
    info = json.load(open(side, encoding="utf-8")) if os.path.isfile(side) else None
    ok = "VRM_OK" in proc.stdout and info is not None and os.path.isfile(os.path.join(dest, "SK_VRM_%s.fbx" % cid))
    # The yaw must leave the left hip on Blender -X (model facing +Y there, -Y in UE); see blender_vrm_to_fbx.py.
    facing_ok = bool(info) and (info.get("leftHipMinusRightHipX_cm") or 0) < 0
    result = {"characterId": cid, "ok": ok and facing_ok, "facingOk": facing_ok,
              "heightCm": info and info.get("height_cm"), "bones": info and info.get("bones"),
              "slots": info and len(info.get("slots", [])), "spec": info and info.get("specVersion")}
    if not ok:
        tail = [l for l in (proc.stdout + proc.stderr).splitlines() if l.strip()][-6:]
        result["error"] = " | ".join(tail)[-600:]
    print("VRM_FBX", json.dumps(result, ensure_ascii=True), flush=True)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    only = set(filter(None, a.only.split(",")))
    rows = [r for r in json.load(open(INVENTORY, encoding="utf-8"))["rows"]
            if r["characterId"] != HERO and "error" not in r and (not only or r["characterId"] in only)]
    os.makedirs(STAGING, exist_ok=True)
    os.makedirs(LOGS, exist_ok=True)
    previous = {}
    if os.path.isfile(REPORT):
        previous = {r["characterId"]: r for r in json.load(open(REPORT, encoding="utf-8")).get("models", [])}
    todo = []
    for r in rows:
        cid = r["characterId"]
        done = all(os.path.isfile(os.path.join(OUT, cid, "SK_VRM_%s.%s" % (cid, e))) for e in ("fbx", "json"))
        if done and not a.force and previous.get(cid, {}).get("ok", True):
            continue
        todo.append(r)
    print("VRM_FBX todo=%d of %d, jobs=%d" % (len(todo), len(rows), a.jobs), flush=True)
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        results = list(pool.map(export_one, todo))
    merged = dict(previous)
    merged.update({r["characterId"]: r for r in results})
    models = [merged[k] for k in sorted(merged)]
    report = {"schema": "Tread.M4.VrmFbxExport.v1", "ok": len(models) == 99 and all(m.get("ok") for m in models),
              "count": len(models), "failed": [m["characterId"] for m in models if not m.get("ok")], "models": models}
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("M4_VRM_FBX", "PASS" if report["ok"] else "PARTIAL", len(models), "failed=%s" % report["failed"])
    return 0 if not report["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
