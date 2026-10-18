"""Freeze and verify the M0 baseline before M1 work starts.

Run inside the Unreal Editor with ``Tools/ue_run.py``.  The script is
idempotent: the first run duplicates the M0 map to the M1 graybox entry and
writes a manifest; subsequent ``--verify`` runs compare the recorded hashes
and editor evidence without modifying the M0 map.
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import unreal


PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CONTENT_DIR = os.path.join(PROJECT_DIR, "Content")
SAVED_REPORT_DIR = os.path.join(PROJECT_DIR, "Saved", "Reports")
M0_MAP = "/Game/Tread/Maps/M0_Paris_Board"
M1_MAP = "/Game/Tread/Maps/M1_Match_Graybox"
M0_MAP_FILE = os.path.join(CONTENT_DIR, "Tread", "Maps", "M0_Paris_Board.umap")
M1_MAP_FILE = os.path.join(CONTENT_DIR, "Tread", "Maps", "M1_Match_Graybox.umap")
BOARD_FREEZE = os.path.join(PROJECT_DIR, "Tools", "paris", "board_frozen.json")
REPORT = os.path.join(SAVED_REPORT_DIR, "M1_M0_Baseline_Freeze.json")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def json_load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def asset_exists(path):
    return bool(unreal.EditorAssetLibrary.does_asset_exist(path))


def duplicate_m1_map():
    """Create the M1 map through the editor asset API, never by editing a uasset/umap."""
    if asset_exists(M1_MAP):
        return {"created": False, "path": M1_MAP, "reason": "already_exists"}
    if not asset_exists(M0_MAP):
        raise RuntimeError("M0 map is missing: %s" % M0_MAP)
    duplicated = unreal.EditorAssetLibrary.duplicate_asset(M0_MAP, M1_MAP)
    if not duplicated:
        raise RuntimeError("failed to duplicate M0 map to %s" % M1_MAP)
    if not unreal.EditorAssetLibrary.save_asset(M1_MAP, only_if_is_dirty=False):
        raise RuntimeError("failed to save duplicated M1 map: %s" % M1_MAP)
    return {"created": True, "path": M1_MAP, "reason": "duplicated_from_m0"}


def editor_evidence():
    evidence = {
        "m0_map_exists": asset_exists(M0_MAP),
        "m1_graybox_map_exists": asset_exists(M1_MAP),
        "m0_technical_validation_exists": os.path.exists(
            os.path.join(SAVED_REPORT_DIR, "M0_Technical_Validation.json")
        ),
        "m0_camera_exists": os.path.exists(os.path.join(SAVED_REPORT_DIR, "M0_Camera.json")),
        "m0_render_baseline_exists": os.path.exists(
            os.path.join(SAVED_REPORT_DIR, "M0_Paris_Render_Baseline.json")
        ),
    }
    technical_path = os.path.join(SAVED_REPORT_DIR, "M0_Technical_Validation.json")
    if os.path.exists(technical_path):
        technical = json_load(technical_path)
        evidence["m0_technical_ok"] = bool(technical.get("ok"))
        evidence["frozen_board_sha256"] = technical.get("frozen_board_sha256")
        evidence["rendering"] = technical.get("rendering", {})
        evidence["actors"] = technical.get("actors", {})
    return evidence


def make_manifest(created):
    os.makedirs(SAVED_REPORT_DIR, exist_ok=True)
    technical_path = os.path.join(SAVED_REPORT_DIR, "M0_Technical_Validation.json")
    camera_path = os.path.join(SAVED_REPORT_DIR, "M0_Camera.json")
    render_path = os.path.join(SAVED_REPORT_DIR, "M0_Paris_Render_Baseline.json")
    files = {}
    for key, path in {
        "m0_map": M0_MAP_FILE,
        "frozen_board": BOARD_FREEZE,
        "m0_technical_validation": technical_path,
        "m0_camera": camera_path,
        "m0_render_baseline": render_path,
    }.items():
        files[key] = {"path": path, "exists": os.path.exists(path)}
        if os.path.exists(path):
            files[key]["sha256"] = sha256(path)
            files[key]["bytes"] = os.path.getsize(path)

    technical = json_load(technical_path) if os.path.exists(technical_path) else {}
    camera = json_load(camera_path) if os.path.exists(camera_path) else {}
    render = json_load(render_path) if os.path.exists(render_path) else {}
    return {
        "schema": "Tread.M1.M0BaselineFreeze.v1",
        "createdAtUtc": datetime.now(timezone.utc).isoformat(),
        "m0": {
            "mapAsset": M0_MAP,
            "mapFile": M0_MAP_FILE,
            "mapIsImmutable": True,
            "frozenBoardSha256": technical.get("frozen_board_sha256"),
            "camera": camera,
            "renderBaseline": {
                "resolution": render.get("resolution"),
                "rhi": render.get("rhi"),
                "averageFps": render.get("average_fps"),
                "onePercentLowFps": render.get("one_percent_low_fps"),
                "averageGpuMs": render.get("average_gpu_ms"),
                "dedicatedVideoMemoryMb": render.get("dedicated_video_memory_mb"),
            },
            "technicalValidation": {
                "ok": technical.get("ok"),
                "rendering": technical.get("rendering", {}),
                "actors": technical.get("actors", {}),
            },
        },
        "m1": {
            "grayboxMapAsset": M1_MAP,
            "grayboxMapFile": M1_MAP_FILE,
            "entryMode": "duplicate_of_frozen_m0",
            "defaultGameMapChanged": False,
            "gameplaySystemsAllowedToChange": [
                "M1 match state and deterministic seed",
                "shop and economy",
                "bench/board placement",
                "placeholder AI and auto battle",
                "BP and ScoutSnapshot UI/data bindings",
            ],
        },
        "files": files,
        "editorEvidence": editor_evidence(),
        "createdMap": created,
    }


def verify_manifest(manifest):
    mismatches = []
    for entry in manifest.get("files", {}).values():
        path = entry.get("path")
        if not entry.get("exists"):
            continue
        if not os.path.exists(path):
            mismatches.append({"path": path, "reason": "missing"})
            continue
        current = sha256(path)
        if current != entry.get("sha256"):
            mismatches.append({"path": path, "expected": entry.get("sha256"), "actual": current})
    if not asset_exists(M0_MAP):
        mismatches.append({"path": M0_MAP, "reason": "asset_missing"})
    if not asset_exists(M1_MAP):
        mismatches.append({"path": M1_MAP, "reason": "m1_entry_missing"})
    return mismatches


def main(argv):
    mode = "verify" if "--verify" in argv else "create"
    created = {"created": False, "path": M1_MAP, "reason": "verification_only"}
    if mode == "create":
        # A freeze is append-only.  Re-running the command must never refresh
        # hashes and silently move the baseline forward.
        if os.path.exists(REPORT):
            manifest = json_load(REPORT)
            mismatches = verify_manifest(manifest)
            if mismatches:
                raise RuntimeError(
                    "existing M0 baseline does not verify: %s"
                    % json.dumps(mismatches, ensure_ascii=False)
                )
            print("M1_M0_BASELINE_FREEZE=ALREADY_FROZEN")
            print("M1_M0_BASELINE_REPORT=" + REPORT)
            print("M1_GRAYBOX_MAP=" + M1_MAP)
            return
        created = duplicate_m1_map()
        manifest = make_manifest(created)
        with open(REPORT, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print("M1_M0_BASELINE_FREEZE=CREATED")
        print("M1_M0_BASELINE_REPORT=" + REPORT)
        print("M1_GRAYBOX_MAP=" + M1_MAP)
        return

    if not os.path.exists(REPORT):
        raise RuntimeError("baseline manifest missing; run without --verify first")
    manifest = json_load(REPORT)
    mismatches = verify_manifest(manifest)
    result = {
        "schema": "Tread.M1.M0BaselineFreeze.Verify.v1",
        "ok": not mismatches,
        "manifest": REPORT,
        "mismatches": mismatches,
        "checkedAtUtc": datetime.now(timezone.utc).isoformat(),
    }
    verify_report = os.path.join(SAVED_REPORT_DIR, "M1_M0_Baseline_Verify.json")
    with open(verify_report, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("M1_M0_BASELINE_VERIFY=" + ("PASS" if result["ok"] else "FAIL"))
    print("M1_M0_BASELINE_VERIFY_REPORT=" + verify_report)
    if mismatches:
        raise RuntimeError("M0 baseline changed: %s" % json.dumps(mismatches, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
