#!/usr/bin/env python3
"""Run an on-disk editor Python script inside the running Unreal Editor (Python remote execution).

Usage:
    python Tools/ue_run.py <script.py> [script args...]
    python Tools/ue_run.py -c "<python code>"

Requirements (set once, see Tools/paris/00_enable_remote_exec.md):
    Project Settings > Plugins > Python > Enable Remote Execution = true
    Multicast bind address 127.0.0.1, group 239.0.0.1:6766

The script runs with sys.argv set, its folder on sys.path and every module previously
imported from Tools/ purged, so edits to helper modules are always picked up.
stdout/stderr of the script is tee'd into Saved/Logs/ue_run_last.log (the socket
protocol of remote_execution.py truncates large payloads, so the runner reads the log file).
Exit code 0 = script finished without exception, 2 = script raised, 3 = connection failure.
"""
import os
import sys
import time

ENGINE_PY = os.environ.get(
    "UE_REMOTE_EXEC_PY",
    "G:/epicgame/UE_5.8/Engine/Plugins/Experimental/PythonScriptPlugin/Content/Python",
)
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TOOLS_DIR)
LOG_PATH = os.path.join(PROJECT_DIR, "Saved", "Logs", "ue_run_last.log")

WRAPPER = r'''
def _ue_run_main():
    import sys, os, gc, traceback, runpy, time
    tools = {tools!r}

    def purge():
        for m in [k for k, v in list(sys.modules.items()) if getattr(v, "__file__", None) and os.path.abspath(v.__file__).startswith(tools)]:
            del sys.modules[m]

    class Tee(object):
        def __init__(self, f):
            self.f = f
        def write(self, t):
            self.f.write(t); self.f.flush(); return len(t)
        def flush(self):
            self.f.flush()

    purge()
    log = open({log!r}, "w", encoding="utf-8")
    old = (sys.stdout, sys.stderr)
    sys.stdout = sys.stderr = Tee(log)
    ok = True
    t0 = time.time()
    try:
        {body}
    except SystemExit as e:
        ok = e.code in (0, None)
    except BaseException:
        traceback.print_exc()
        ok = False
    finally:
        sys.stdout, sys.stderr = old
        # Collect every Python cycle (script namespaces, purged modules, wrapped UObjects) here, in a safe
        # context: cyclic garbage left for the engine's pre-GC hook (PyGC_Collect inside CollectGarbage)
        # crashed the 5.8 editor (EXCEPTION_ACCESS_VIOLATION in python311.dll).
        purge()
        gc.collect()
        gc.collect()
        log.write("\n[ue_run] status=%s elapsed=%.1fs\n" % ("OK" if ok else "FAIL", time.time() - t0))
        log.close()
    print("UE_RUN_STATUS=" + ("OK" if ok else "FAIL"))

_ue_run_main()
del _ue_run_main
import gc as _gc
_gc.collect()
del _gc
'''

RUN_FILE = (
    "sys.argv = [{script!r}] + {argv!r}\n"
    "        sys.path.insert(0, os.path.dirname({script!r})) if os.path.dirname({script!r}) not in sys.path else None\n"
    "        ns = runpy.run_path({script!r}, run_name='__main__')\n"
    "        ns.clear()\n"
    "        del ns"
)
RUN_CODE = "ns = {{'__name__': '__main__'}}\n        exec(compile({code!r}, '<ue_run -c>', 'exec'), ns)\n        ns.clear()\n        del ns"


def connect(timeout=10.0):
    sys.path.insert(0, ENGINE_PY)
    import remote_execution as rex

    cfg = rex.RemoteExecutionConfig()
    cfg.multicast_bind_address = "127.0.0.1"
    r = rex.RemoteExecution(cfg)
    r.start()
    t0 = time.time()
    while not r.remote_nodes and time.time() - t0 < timeout:
        time.sleep(0.2)
    if not r.remote_nodes:
        r.stop()
        raise RuntimeError("no Unreal Editor node answered (is Remote Execution enabled?)")
    nodes = [n for n in r.remote_nodes if "Tread" in str(n.get("project_name", "")) or "Tread" in str(n)] or r.remote_nodes
    r.open_command_connection(nodes[0]["node_id"])
    return r, rex


def run(body):
    code = WRAPPER.format(tools=TOOLS_DIR, log=LOG_PATH, body=body)
    try:
        r, rex = connect()
    except Exception as e:  # noqa: BLE001
        print("[ue_run] connection failed:", e)
        return 3
    try:
        res = r.run_command(code, unattended=True, exec_mode=rex.MODE_EXEC_FILE)
    except Exception as e:  # noqa: BLE001  (large replies may fail to parse; the log still exists)
        res = {"success": False, "result": str(e), "output": []}
    finally:
        r.stop()
    try:
        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            sys.stdout.write(f.read())
    except OSError:
        pass
    status = "".join(o.get("output", "") for o in res.get("output", []) if "UE_RUN_STATUS" in o.get("output", ""))
    if "UE_RUN_STATUS=OK" in status:
        return 0
    if not res.get("success"):
        print("[ue_run] remote result:", str(res.get("result"))[:2000])
    return 2


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    if len(argv) < 2:
        print(__doc__)
        return 1
    if argv[1] == "-c":
        return run(RUN_CODE.format(code=argv[2]))
    script = os.path.abspath(argv[1])
    if not os.path.exists(script):
        print("script not found:", script)
        return 1
    return run(RUN_FILE.format(script=script, argv=list(argv[2:])))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
