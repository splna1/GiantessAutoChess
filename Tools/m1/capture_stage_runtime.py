"""Launch the M1 map and save one deterministic native UMG evidence frame."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
import ctypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ue_mcp import UeMcp


ROOT = Path(__file__).resolve().parents[2]
UE = Path(r"G:\epicgame\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe")
PROJECT = ROOT / "Tread.uproject"
TOOLSET = "SlateInspectorToolset.SlateInspectorToolset"
EDITOR_TOOLSET = "EditorToolset.EditorAppToolset"


def text_payload(result: dict) -> str:
    for item in (result or {}).get("content", []):
        if item.get("type") == "text":
            return item.get("text", "")
    return ""


def call(client: UeMcp, name: str, args: dict, toolset: str):
    result = client.call(name, args, toolset=toolset, timeout=180)
    if result and result.get("isError"):
        raise RuntimeError(text_payload(result))
    return result


def new_client() -> UeMcp:
    last = None
    for _ in range(12):
        try:
            return UeMcp(timeout=180)
        except Exception as exc:  # editor's MCP endpoint may start after the window
            last = exc
            time.sleep(2)
    raise RuntimeError(f"Unreal MCP did not become available: {last}")


def maximize_process_window(process_id: int) -> None:
    """Maximize the editor before Slate captures its desktop window."""
    user32 = ctypes.windll.user32
    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    get_pid = user32.GetWindowThreadProcessId
    get_pid.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    get_pid.restype = ctypes.c_uint32
    show = user32.ShowWindow
    foreground = user32.SetForegroundWindow

    def visit(hwnd: int, _lparam: int) -> bool:
        owner = ctypes.c_uint32()
        get_pid(hwnd, ctypes.byref(owner))
        if owner.value == process_id and user32.IsWindowVisible(hwnd):
            show(hwnd, 3)  # SW_MAXIMIZE
            foreground(hwnd)
            return False
        return True

    user32.EnumWindows(enum_proc(visit), 0)


def window_index(client: UeMcp) -> int:
    raw = text_payload(call(client, "Windows", {"action": "list"}, TOOLSET))
    payload = json.loads(raw)
    windows = json.loads(payload["returnValue"])
    blank = [item["index"] for item in windows if not item.get("title")]
    return blank[0] if blank else windows[0]["index"]


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: capture_stage_runtime.py STAGE OUTPUT.png")
        return 2
    stage = sys.argv[1].upper()
    output = ROOT / "Saved" / "Screenshots" / sys.argv[2]
    if stage not in {"BP", "SCOUT", "PREPARE", "BATTLE", "RESULT"}:
        raise ValueError(stage)

    subprocess.run(["taskkill", "/F", "/IM", "UnrealEditor.exe"], capture_output=True, check=False)
    time.sleep(3)
    process = subprocess.Popen(
        [
            str(UE),
            str(PROJECT),
            "/Game/Tread/Maps/M1_Match_Graybox",
            "-TreadSeed=20260926",
            f"-TreadM1Capture={stage}",
            "-ResX=1920",
            "-ResY=1080",
        ],
        cwd=ROOT,
    )
    time.sleep(20)
    maximize_process_window(process.pid)
    time.sleep(2)

    client = new_client()
    call(
        client,
        "StartPIE",
        {"options": {"bSimulate": False, "playMode": "PlayMode_InViewPort", "warmupSeconds": 2}},
        EDITOR_TOOLSET,
    )
    time.sleep(4)
    client = new_client()
    index = window_index(client)
    call(client, "Windows", {"action": "select", "index": index}, TOOLSET)
    call(client, "Observe", {"ref": "w1", "maxDepth": 5}, TOOLSET)
    time.sleep(1)
    result = call(client, "Screenshot", {"ref": "w1"}, TOOLSET)
    raw = text_payload(result)
    payload = json.loads(raw)
    image = payload["returnValue"]
    if not image.get("data"):
        raise RuntimeError("Slate screenshot returned an empty image")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(base64.b64decode(image["data"]))
    print(json.dumps({"stage": stage, "path": str(output), "bytes": output.stat().st_size}, ensure_ascii=False))

    try:
        call(new_client(), "StopPIE", {}, EDITOR_TOOLSET)
    except Exception:
        pass
    subprocess.run(["taskkill", "/F", "/IM", "UnrealEditor.exe"], capture_output=True, check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
