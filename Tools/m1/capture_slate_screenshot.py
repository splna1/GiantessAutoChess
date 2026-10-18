import base64, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ue_mcp import UeMcp
out = os.path.abspath(sys.argv[1])
ref = sys.argv[2] if len(sys.argv) > 2 else "w1"
client = UeMcp(timeout=120)
result = client.call("Screenshot", {"ref": ref}, toolset="SlateInspectorToolset.SlateInspectorToolset", timeout=120)
image = None
for part in (result or {}).get("content", []):
    if part.get("type") == "text":
        payload = json.loads(part["text"])
        image = payload.get("returnValue") or payload.get("structuredContent", {}).get("returnValue")
        break
if not image or not image.get("data"):
    raise RuntimeError("Slate screenshot returned no image: " + json.dumps(result)[:1000])
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "wb") as f:
    f.write(base64.b64decode(image["data"]))
print(json.dumps({"path": out, "mimeType": image.get("mimeType"), "bytes": os.path.getsize(out)}))
