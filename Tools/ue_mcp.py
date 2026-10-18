#!/usr/bin/env python3
"""Minimal Unreal Engine MCP client (ModelContextProtocol + AllToolsets plugins).

Usage:
    python Tools/ue_mcp.py toolsets
    python Tools/ue_mcp.py describe <toolset>
    python Tools/ue_mcp.py call <toolset|-> <tool> '<json args>'
    python Tools/ue_mcp.py pyfile <path/to/editor_script.py> [--timeout 600]

`pyfile` runs an editor-side Python script inside the running UE editor via the
MCP python execution tool, so every scene build step stays a replayable file on disk.
"""
import json
import os
import sys
import urllib.request

ENDPOINT = os.environ.get("UE_MCP_URL", "http://127.0.0.1:8000/mcp")


class UeMcp:
    def __init__(self, endpoint=ENDPOINT, timeout=600):
        self.endpoint = endpoint
        self.timeout = timeout
        self.session = None
        self._id = 0
        self._initialize()

    def _post(self, payload, timeout=None):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        req = urllib.request.Request(
            self.endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
            sid = resp.headers.get("Mcp-Session-Id")
            if sid:
                self.session = sid
            body = resp.read().decode("utf-8", errors="replace")
        if not body.strip():
            return None
        if body.lstrip().startswith("event:") or body.lstrip().startswith("data:"):
            # SSE framing: take the last data line
            data_lines = [l[5:].strip() for l in body.splitlines() if l.startswith("data:")]
            body = data_lines[-1] if data_lines else "{}"
        return json.loads(body)

    def _initialize(self):
        self._rpc("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "tread-tools", "version": "0.1"},
        })
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _rpc(self, method, params=None, timeout=None):
        self._id += 1
        resp = self._post({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}, timeout)
        if resp is None:
            return None
        if "error" in resp:
            raise RuntimeError(f"MCP error: {resp['error']}")
        return resp.get("result")

    def call(self, tool_name, arguments=None, toolset=None, timeout=None):
        args = {"tool_name": tool_name, "arguments": arguments or {}}
        if toolset:
            args["toolset_name"] = toolset
        result = self._rpc("tools/call", {"name": "call_tool", "arguments": args}, timeout)
        return result

    def top(self, name, arguments=None):
        return self._rpc("tools/call", {"name": name, "arguments": arguments or {}})


def text_of(result):
    if not result:
        return ""
    out = []
    for c in result.get("content", []):
        if c.get("type") == "text":
            out.append(c.get("text", ""))
        else:
            out.append(json.dumps(c)[:500])
    if result.get("structuredContent"):
        out.append(json.dumps(result["structuredContent"], ensure_ascii=False, indent=1))
    return "\n".join(out)


PY_TOOL = os.environ.get("UE_MCP_PY_TOOL", "")  # "toolset:tool" override


def run_pyfile(client, path, timeout=600):
    with open(path, "r", encoding="utf-8") as f:
        code = f.read()
    toolset, tool, argname = resolve_python_tool(client)
    res = client.call(tool, {argname: code}, toolset=toolset, timeout=timeout)
    return res


_py_cache = None


def resolve_python_tool(client):
    """Find the editor python-execution tool among the toolsets."""
    global _py_cache
    if _py_cache:
        return _py_cache
    if PY_TOOL:
        ts, tool, arg = (PY_TOOL.split(":") + ["code"])[:3]
        _py_cache = (ts, tool, arg)
        return _py_cache
    cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".ue_mcp_pytool.json")
    if os.path.exists(cache_file):
        _py_cache = tuple(json.load(open(cache_file)))
        return _py_cache
    raise RuntimeError("python tool not resolved; set UE_MCP_PY_TOOL=toolset:tool:argname")


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[1]
    c = UeMcp()
    if cmd == "toolsets":
        print(text_of(c.top("list_toolsets")))
    elif cmd == "describe":
        print(text_of(c.top("describe_toolset", {"toolset_name": argv[2]})))
    elif cmd == "call":
        ts = None if argv[2] == "-" else argv[2]
        args = json.loads(argv[4]) if len(argv) > 4 else {}
        print(text_of(c.call(argv[3], args, toolset=ts)))
    elif cmd == "pyfile":
        timeout = 600
        if "--timeout" in argv:
            timeout = int(argv[argv.index("--timeout") + 1])
        res = run_pyfile(c, argv[2], timeout)
        print(text_of(res))
        if res and res.get("isError"):
            return 2
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
