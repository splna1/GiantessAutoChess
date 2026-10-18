# -*- coding: utf-8 -*-
"""Rename the collided doc 163 -> 164 (shell channel is down)."""
import os
import json

D = r"E:\AI\Tread\Tread\document"
src = os.path.join(D, "163_华沙五地标_Blender程序化建模_2026-10-18.md")
dst = os.path.join(D, "164_华沙五地标_Blender程序化建模_2026-10-18.md")
if os.path.exists(src) and not os.path.exists(dst):
    os.rename(src, dst)
print("HEADLESS " + json.dumps({"src_exists": os.path.exists(src),
                                "dst_exists": os.path.exists(dst),
                                "dst": dst}, ensure_ascii=False))
