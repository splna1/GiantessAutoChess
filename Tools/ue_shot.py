#!/usr/bin/env python3
"""Capture the level viewport through the UE MCP server and save it as PNG.

Usage:
    python Tools/ue_shot.py <out.png> [x_m y_m z_m pitch yaw roll] [--annotate] [--warm N]

--warm N renders N throw-away captures at the same pose first (default 2) so Lumen, VSM pages and TSR
history converge after the camera jump; without it the first frame shows missing shadow pages.

Location is given in METRES (converted to cm for UE). Without a pose the current
viewport camera is used. Prints the saved path and the capture camera pose.
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ue_mcp import UeMcp  # noqa: E402


def capture(out_path, pose=None, annotate=False, timeout=180):
    c = UeMcp(timeout=timeout)
    args = {"bShowUI": False}
    if pose:
        x, y, z, p, yw, r = pose
        args["captureTransform"] = {
            "location": {"x": x * 100.0, "y": y * 100.0, "z": z * 100.0},
            "rotation": {"pitch": p, "yaw": yw, "roll": r},
        }
    # the tool requires an annotations block; spacing 0 / label distance 0 disables the overlay
    args["annotations"] = {
        "gridSpacing": 20000 if annotate else 0, "gridExtent": 100000, "gridHeight": 0,
        "maxLabelDistance": 0, "classFilter": {"refPath": ""}, "maxLabels": 0,
    }
    res = c.call("CaptureViewport", args, toolset="EditorToolset.EditorAppToolset")
    sc = (res or {}).get("structuredContent") or {}
    rv = sc.get("returnValue") or {}
    img = (rv.get("image") or {}).get("data")
    if not img:
        # some servers only return text content
        for part in (res or {}).get("content", []):
            if part.get("type") == "text":
                try:
                    rv = json.loads(part["text"]).get("returnValue", {})
                    img = rv.get("image", {}).get("data")
                except Exception:  # noqa: BLE001
                    pass
            elif part.get("type") == "image":
                img = part.get("data")
    if not img:
        raise RuntimeError("capture failed: %s" % json.dumps(res)[:1500])
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(img))
    return rv


def main(argv):
    annotate = "--annotate" in argv
    argv = [a for a in argv if a != "--annotate"]
    warm = 2
    if "--warm" in argv:
        i = argv.index("--warm")
        warm = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    if len(argv) < 2:
        print(__doc__)
        return 1
    pose = [float(a) for a in argv[2:8]] if len(argv) >= 8 else None
    for _ in range(warm):
        capture(argv[1], pose, annotate)
    rv = capture(argv[1], pose, annotate)
    print("saved", os.path.abspath(argv[1]))
    print("camera", json.dumps({k: rv.get(k) for k in ("cameraLocation", "cameraRotation", "cameraFOV")}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
