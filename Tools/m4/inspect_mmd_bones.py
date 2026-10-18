"""Quick check: read MMD bone names from the first staged PMX."""
import json
import subprocess
import sys

# Use Blender 5.2 with mmd_tools
BLENDER = "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
PMX = "E:/AI/Tread/Tread/Saved/Staging/mmd/char_101/src/OTs14原皮/GirlsFrontline OTs14Default.pmx"
OUT = "E:/AI/Tread/Tread/Saved/Reports/MMD_Bones_Sample.json"

script = """
import bpy, json
bpy.ops.mmd_tools.import_model(filepath=r'%s', scale=0.08)
arm = next((o for o in bpy.data.objects if o.type == 'ARMATURE'), None)
bones = [b.name for b in arm.data.bones] if arm else []
with open(r'%s', 'w', encoding='utf-8') as f:
    json.dump({'armature': arm.name if arm else None, 'bones': bones, 'count': len(bones)}, f, ensure_ascii=False, indent=1)
""" % (PMX, OUT)

subprocess.run([BLENDER, "--background", "--python-expr", script], check=True)
print(json.dumps(json.load(open(OUT, encoding='utf-8')), indent=1, ensure_ascii=False))
