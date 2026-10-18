import base64,json,os,sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ue_mcp import UeMcp
out=os.path.abspath(sys.argv[1])
c=UeMcp(timeout=120)
r=c.call('CaptureEditorImage',{},toolset='EditorToolset.EditorAppToolset',timeout=120)
img=None
for p in (r or {}).get('content',[]):
 if p.get('type')=='text':
  x=json.loads(p['text']); img=x.get('returnValue') or x.get('structuredContent',{}).get('returnValue'); break
if not img or not img.get('data'): raise RuntimeError(str(r)[:1000])
os.makedirs(os.path.dirname(out),exist_ok=True)
open(out,'wb').write(base64.b64decode(img['data']))
print(out,os.path.getsize(out),img.get('mimeType'))
