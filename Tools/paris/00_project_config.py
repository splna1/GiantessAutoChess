"""Step 00: project-level render budget for the M0 Paris board (8 GB laptop GPU shared with desktop apps).

Idempotently writes the cvars below into Config/DefaultEngine.ini [SystemSettings] (read at editor start) and
applies them to the running editor through the console. Without these the default VSM physical page pool
(4096 pages) + 512 MB Nanite streaming pool push the editor ~300 MB over the DXGI budget and UE prints
"Video memory has been exhausted".

Usage (through Tools/ue_run.py, or plain `python` to only patch the ini):
    00_project_config.py
"""
import os
import re

CVARS = {
    "r.Shadow.Virtual.MaxPhysicalPages": "2048",
    "r.Nanite.Streaming.StreamingPoolSize": "320",
    "r.LocalFogVolume.TileMaxInstanceCount": "64",  # smoke plumes (07_fx.py) overlap on screen: 32 drops volumes
}
INI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "Config", "DefaultEngine.ini")
SECTION = "[SystemSettings]"


def patch_ini(path=INI, cvars=CVARS):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    lines = text.splitlines()
    if SECTION not in [l.strip() for l in lines]:
        lines += ["", SECTION]
    start = [l.strip() for l in lines].index(SECTION)
    end = start + 1
    while end < len(lines) and not lines[end].strip().startswith("["):
        end += 1
    body = lines[start + 1:end]
    for k, val in cvars.items():
        pat = re.compile(r"^\s*" + re.escape(k) + r"\s*=")
        body = [l for l in body if not pat.match(l)]
        body.append("%s=%s" % (k, val))
    while body and not body[-1].strip():
        body.pop()
    tail = lines[end:]
    new = lines[:start + 1] + body + ([""] if tail else []) + tail
    out = "\n".join(new).rstrip("\n") + "\n"
    changed = out != text
    if changed:
        with open(path, "w", encoding="utf-8") as f:
            f.write(out)
    return changed


def main():
    changed = patch_ini()
    print("[paris] DefaultEngine.ini [SystemSettings]", "updated" if changed else "unchanged", CVARS)
    try:
        import unreal
    except ImportError:
        return
    for k, val in CVARS.items():
        unreal.SystemLibrary.execute_console_command(None, "%s %s" % (k, val))
    print("[paris] cvars applied to the running editor")


main()
