"""ActorX .psa reader (pure Python, no `unreal`, no addon).

The GP action set (0614/gp_extract/action_animations_export_2026-09-28) was exported by CUE4Parse as
ActorX PSA files. Layout, all little-endian:

  chunk header (32 B): char id[20], int typeflag, int datasize, int datacount
  ANIMHEAD   no payload
  BONENAMES  datacount x 120 B: char name[64], int flags, int numChildren, int parent,
             quat orientation (x, y, z, w), vec3 position, float length, vec3 size
  ANIMINFO   datacount x 168 B: char name[64], char group[64], int totalBones, int rootInclude,
             int keyCompression, int keyQuotum, float keyReduction, float trackTime, float animRate,
             int startBone, int firstRawFrame, int numRawFrames
  ANIMKEYS   datacount x 32 B: vec3 position, quat orientation, float time   (frame-major, bone-minor)
  SCALEKEYS  optional, datacount x 16 B: vec3 scale, float time

BONENAMES carries the reference pose, so no .psk is needed to know the source rest skeleton.
Values are returned exactly as stored; the handedness/conjugation convention is decided in
anim_psa.py (it is verified there against anatomy, not assumed).

CLI:
  python Tools/paris/psa_io.py <file.psa> [...]     print header, skeleton size, rate, frames, hash
"""
import hashlib
import io
import os
import struct
import sys

HEADER = struct.Struct("<20siii")
BONE = struct.Struct("<64siii4f3f4f")
INFO = struct.Struct("<64s64siiiifffiii")
KEY = struct.Struct("<3f4ff")
SCALE = struct.Struct("<3ff")


def _cstr(b):
    return b.split(b"\0", 1)[0].decode("latin-1")


def read_chunks(path):
    """{chunk id: (typeflag, datasize, datacount, payload bytes)} in file order."""
    with io.open(path, "rb") as f:
        data = f.read()
    out = {}
    pos = 0
    while pos + HEADER.size <= len(data):
        cid, flag, size, count = HEADER.unpack_from(data, pos)
        pos += HEADER.size
        n = size * count
        out[_cstr(cid)] = (flag, size, count, data[pos:pos + n])
        pos += n
    return out


class Bone(object):
    __slots__ = ("name", "flags", "children", "parent", "q", "t")

    def __init__(self, name, flags, children, parent, q, t):
        self.name = name
        self.flags = flags
        self.children = children
        self.parent = parent
        self.q = q
        self.t = t


class Sequence(object):
    """One ANIMINFO entry with its keys: keys[frame][bone] = (t, q)."""

    def __init__(self, name, group, rate, frames, keys, track_time, scales=None):
        self.name = name
        self.group = group
        self.rate = rate
        self.frames = frames
        self.keys = keys
        self.track_time = track_time
        self.scales = scales

    @property
    def length(self):
        """Play length in seconds.

        CUE4Parse (like UModel) stores AnimRate = NumKeys / SequenceLength, so a 30 fps clip with 144
        keys is written as 30.2098. The real length is keys / AnimRate, the real rate is
        (keys - 1) / length.
        """
        return self.frames / self.rate if self.rate > 0 else 0.0

    @property
    def fps(self):
        """Sampling rate of the keys, snapped to an integer when it is one within float noise."""
        if self.frames < 2 or self.rate <= 0:
            return 30.0
        r = (self.frames - 1) / self.length
        return float(round(r)) if abs(r - round(r)) < 1e-3 else r


class Psa(object):
    def __init__(self, path):
        self.path = path
        self.name = os.path.splitext(os.path.basename(path))[0]
        ch = read_chunks(path)
        for need in ("BONENAMES", "ANIMINFO", "ANIMKEYS"):
            if need not in ch:
                raise ValueError("%s: missing %s chunk" % (path, need))
        _f, size, count, raw = ch["BONENAMES"]
        if size != BONE.size:
            raise ValueError("%s: BONENAMES record is %d bytes, expected %d" % (path, size, BONE.size))
        self.bones = []
        for i in range(count):
            v = BONE.unpack_from(raw, i * size)
            self.bones.append(Bone(_cstr(v[0]), v[1], v[2], v[3], tuple(v[4:8]), tuple(v[8:11])))
        self.index = dict((b.name, i) for i, b in enumerate(self.bones))

        _f, size, count, info_raw = ch["ANIMINFO"]
        _f, ksize, kcount, key_raw = ch["ANIMKEYS"]
        if ksize != KEY.size:
            raise ValueError("%s: ANIMKEYS record is %d bytes, expected %d" % (path, ksize, KEY.size))
        scale_raw = ch.get("SCALEKEYS")
        nb = len(self.bones)
        self.sequences = []
        for s in range(count):
            v = INFO.unpack_from(info_raw, s * size)
            name, group = _cstr(v[0]), _cstr(v[1])
            total_bones, track_time, rate = v[2], v[7], v[8]
            first, frames = v[10], v[11]
            if total_bones != nb:
                raise ValueError("%s: sequence %s has %d bones, skeleton %d" % (path, name, total_bones, nb))
            keys = []
            for fr in range(frames):
                row = []
                base = (first + fr) * nb
                for b in range(nb):
                    k = KEY.unpack_from(key_raw, (base + b) * ksize)
                    row.append((tuple(k[0:3]), tuple(k[3:7])))
                keys.append(row)
            scales = None
            if scale_raw and scale_raw[1] == SCALE.size and scale_raw[2] >= (first + frames) * nb:
                sr = scale_raw[3]
                scales = [[SCALE.unpack_from(sr, ((first + fr) * nb + b) * SCALE.size)[0:3] for b in range(nb)]
                          for fr in range(frames)]
            self.sequences.append(Sequence(name, group, rate, frames, keys, track_time, scales))
        self._key_bytes = key_raw

    def content_hash(self):
        """Hash of the skeleton names + raw keys: identical montage segments and direct sequences collide."""
        h = hashlib.sha1()
        for b in self.bones:
            h.update(b.name.encode("latin-1"))
        h.update(self._key_bytes)
        return h.hexdigest()[:16]

    def summary(self):
        s = self.sequences[0]
        return {"file": os.path.basename(self.path), "bones": len(self.bones), "sequences": len(self.sequences),
                "name": s.name, "rate": s.rate, "fps": s.fps, "frames": s.frames, "length": round(s.length, 4),
                "track_time": s.track_time, "hash": self.content_hash()}


def file_hash(path):
    """Psa(path).content_hash() without unpacking the keys (fast enough to index a whole export)."""
    ch = read_chunks(path)
    if "BONENAMES" not in ch or "ANIMKEYS" not in ch:
        return None
    _f, size, count, raw = ch["BONENAMES"]
    h = hashlib.sha1()
    for i in range(count):
        h.update(_cstr(raw[i * size:i * size + 64]).encode("latin-1"))
    h.update(ch["ANIMKEYS"][3])
    return h.hexdigest()[:16]


def hash_index(root):
    """{content hash: [paths relative to root, '/'-separated, sorted]} for every .psa under root."""
    out = {}
    for d, _dirs, files in os.walk(root):
        for f in files:
            if f.lower().endswith(".psa"):
                p = os.path.join(d, f)
                h = file_hash(p)
                if h:
                    out.setdefault(h, []).append(os.path.relpath(p, root).replace("\\", "/"))
    for v in out.values():
        v.sort()
    return out


def main(argv):
    for p in argv:
        try:
            print(Psa(p).summary())
        except ValueError as e:
            print("ERROR", e)


if __name__ == "__main__":
    main(sys.argv[1:])
