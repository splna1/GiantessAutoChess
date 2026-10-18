"""Minimal pure-Python glTF 2.0 / GLB reader (no numpy): static triangle geometry with node transforms.

Used by 06_landmarks.py to turn the read-only Eiffel Tower / Notre-Dame .glb files (copied to Saved/Staging first)
into a geom.MeshBuilder, so the landmarks go through the same Nanite StaticMesh path as the procedural city.
triangles(uvs=True) also returns TEXCOORD_0 and extract_image() dumps an embedded texture (B2: Notre-Dame).
Coordinates are converted from glTF (right-handed, +Y up, metres) to the geom convention
(x north, y east, z up, metres): (x, y, z)_gltf -> (x, -z, y), a pure rotation, so winding is preserved.
"""
import array
import json
import math
import struct
import sys

_COMP = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
_NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


class Gltf:
    def __init__(self, path):
        with open(path, "rb") as f:
            data = f.read()
        if data[:4] == b"glTF":
            _, _, length = struct.unpack_from("<III", data, 0)
            off, self.bin = 12, b""
            while off < length:
                clen, ctype = struct.unpack_from("<II", data, off)
                chunk = data[off + 8:off + 8 + clen]
                if ctype == 0x4E4F534A:
                    self.js = json.loads(chunk.decode("utf-8"))
                elif ctype == 0x004E4942:
                    self.bin = chunk
                off += 8 + clen
            self.buffers = [self.bin]
        else:
            import os
            self.js = json.loads(data.decode("utf-8"))
            base = os.path.dirname(path)
            self.buffers = []
            for b in self.js.get("buffers", []):
                with open(os.path.join(base, b["uri"]), "rb") as f:
                    self.buffers.append(f.read())

    def accessor(self, idx):
        """Flat list of values of accessor idx and its component count."""
        a = self.js["accessors"][idx]
        bv = self.js["bufferViews"][a["bufferView"]]
        fmt, size = _COMP[a["componentType"]]
        nc = _NCOMP[a["type"]]
        buf = self.buffers[bv.get("buffer", 0)]
        start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = bv.get("byteStride", 0) or size * nc
        count = a["count"]
        if stride == size * nc:
            arr = array.array(fmt)
            arr.frombytes(buf[start:start + count * stride])
            if sys.byteorder != "little":
                arr.byteswap()
            return arr, nc
        out = array.array(fmt)
        for i in range(count):
            out.extend(struct.unpack_from("<" + fmt * nc, buf, start + i * stride))
        return out, nc

    # ---------------------------------------------------------------- scene graph
    def node_matrices(self):
        """{node index: 4x4 world matrix (column-major flat list)}."""
        nodes = self.js["nodes"]
        world = {}
        scene = self.js.get("scenes", [{}])[self.js.get("scene", 0)]
        roots = scene.get("nodes") or [i for i in range(len(nodes)) if not any(i in n.get("children", []) for n in nodes)]
        stack = [(r, _identity()) for r in roots]
        while stack:
            i, parent = stack.pop()
            m = _mat_mul(parent, _local_matrix(nodes[i]))
            world[i] = m
            for c in nodes[i].get("children", []):
                stack.append((c, m))
        return world

    def triangles(self, uvs=False):
        """Yield (mesh_name, material_index, positions[(x,y,z)], normals[(x,y,z)] or None, tris[(a,b,c)]) in glTF world
        space; with uvs=True a sixth element holds TEXCOORD_0 [(u, v)] (or None)."""
        mats = self.node_matrices()
        for ni, m in mats.items():
            node = self.js["nodes"][ni]
            if "mesh" not in node:
                continue
            mesh = self.js["meshes"][node["mesh"]]
            nm = _normal_matrix(m)
            for prim in mesh["primitives"]:
                if prim.get("mode", 4) != 4:
                    continue
                pos, _ = self.accessor(prim["attributes"]["POSITION"])
                P = [_xform(m, pos[i], pos[i + 1], pos[i + 2]) for i in range(0, len(pos), 3)]
                N = None
                if "NORMAL" in prim["attributes"]:
                    nrm, _ = self.accessor(prim["attributes"]["NORMAL"])
                    N = [_norm(_xform3(nm, nrm[i], nrm[i + 1], nrm[i + 2])) for i in range(0, len(nrm), 3)]
                if "indices" in prim:
                    idx, _ = self.accessor(prim["indices"])
                else:
                    idx = list(range(len(P)))
                T = [(idx[i], idx[i + 1], idx[i + 2]) for i in range(0, len(idx) - 2, 3)]
                if _det3(m) < 0:  # mirrored node: keep front faces front
                    T = [(a, c, b) for a, b, c in T]
                if not uvs:
                    yield mesh.get("name", ""), prim.get("material"), P, N, T
                    continue
                UV = None
                if "TEXCOORD_0" in prim["attributes"]:
                    tc, nc = self.accessor(prim["attributes"]["TEXCOORD_0"])
                    UV = [(float(tc[i]), float(tc[i + 1])) for i in range(0, len(tc), nc)]
                yield mesh.get("name", ""), prim.get("material"), P, N, T, UV

    def image_bytes(self, index=0):
        """Raw bytes + mime type of image `index` (embedded bufferView images only)."""
        im = self.js["images"][index]
        if "bufferView" not in im:
            raise ValueError("image %d is external (%s)" % (index, im.get("uri")))
        bv = self.js["bufferViews"][im["bufferView"]]
        buf = self.buffers[bv.get("buffer", 0)]
        start = bv.get("byteOffset", 0)
        return buf[start:start + bv["byteLength"]], im.get("mimeType", "")

    def extract_image(self, out_path, index=0):
        """Write embedded image `index` to out_path (the extension should match the mime type)."""
        data, mime = self.image_bytes(index)
        with open(out_path, "wb") as f:
            f.write(data)
        return mime


def to_geom(p):
    """glTF Y-up -> geom Z-up (rotation +90 deg about X)."""
    return (p[0], -p[2], p[1])


# ---------------------------------------------------------------- small matrix helpers (column-major)
def _identity():
    return [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]


def _mat_mul(a, b):
    r = [0.0] * 16
    for c in range(4):
        for rr in range(4):
            r[c * 4 + rr] = sum(a[k * 4 + rr] * b[c * 4 + k] for k in range(4))
    return r


def _local_matrix(n):
    if "matrix" in n:
        return [float(x) for x in n["matrix"]]
    tx, ty, tz = n.get("translation", (0, 0, 0))
    qx, qy, qz, qw = n.get("rotation", (0, 0, 0, 1))
    sx, sy, sz = n.get("scale", (1, 1, 1))
    xx, yy, zz = qx * qx, qy * qy, qz * qz
    xy, xz, yz, wx, wy, wz = qx * qy, qx * qz, qy * qz, qw * qx, qw * qy, qw * qz
    r = [1 - 2 * (yy + zz), 2 * (xy + wz), 2 * (xz - wy),
         2 * (xy - wz), 1 - 2 * (xx + zz), 2 * (yz + wx),
         2 * (xz + wy), 2 * (yz - wx), 1 - 2 * (xx + yy)]
    return [r[0] * sx, r[1] * sx, r[2] * sx, 0, r[3] * sy, r[4] * sy, r[5] * sy, 0, r[6] * sz, r[7] * sz, r[8] * sz, 0, tx, ty, tz, 1.0]


def _xform(m, x, y, z):
    return (m[0] * x + m[4] * y + m[8] * z + m[12], m[1] * x + m[5] * y + m[9] * z + m[13], m[2] * x + m[6] * y + m[10] * z + m[14])


def _xform3(m3, x, y, z):
    return (m3[0] * x + m3[3] * y + m3[6] * z, m3[1] * x + m3[4] * y + m3[7] * z, m3[2] * x + m3[5] * y + m3[8] * z)


def _det3(m):
    a, b, c, d, e, f, g, h, i = m[0], m[4], m[8], m[1], m[5], m[9], m[2], m[6], m[10]
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)


def _normal_matrix(m):
    """Inverse-transpose of the upper 3x3 (column-major 3x3 list)."""
    a, b, c, d, e, f, g, h, i = m[0], m[4], m[8], m[1], m[5], m[9], m[2], m[6], m[10]
    det = _det3(m) or 1.0
    inv = [(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det,
           (f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det,
           (d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]  # row-major inverse
    return inv  # read as column-major == transpose of the inverse


def _norm(v):
    l = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / l, v[1] / l, v[2] / l)


if __name__ == "__main__":
    g = Gltf(sys.argv[1])
    tot, lo, hi = 0, [1e9] * 3, [-1e9] * 3
    for name, mat, P, N, T in g.triangles():
        tot += len(T)
        for p in P:
            q = to_geom(p)
            for k in range(3):
                lo[k], hi[k] = min(lo[k], q[k]), max(hi[k], q[k])
        print(name, mat, len(P), len(T), N is not None)
    print("tris", tot, "bounds(geom)", [round(x, 3) for x in lo], [round(x, 3) for x in hi])
