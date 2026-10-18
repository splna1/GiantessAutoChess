#!/usr/bin/env python3
"""Host side: contact sheet of the GP clips (doc 125 section 2, A1 / A2 doc 127), captured from the editor.

For every clip in Saved/Reports/M0_GP_Animations.json the giant is frozen at the clip's key frame
(11_gp_animations.py --pose <S>:key: the frame farthest from the first one, map not saved), then a body
shot and a close-up of the key hand are captured through the MCP viewport capture (Tools/ue_shot.py).
The cameras are placed from the report: key points are skeleton-space cm, the actor transform comes from
report["giant"], so the framing follows the giant wherever 08_vrm.py puts her.
Afterwards A_GP_Idle loops again (saved), the map is reloaded from disk (--verify-reload) and the giant
is captured once more.

--strip takes one clip through evenly spaced times from a single camera instead, framed on its whole
travel (report hips_xy_box_cm): for judging a motion the single key frame cannot show (which clip becomes
the victory animation, 125 section 2.4). --speed plots the root speed curves of the in-place clips.

Usage:
    python Tools/paris/gp_contact_sheet.py [--only Idle,Kick] [--warm N] [--no-reload]
    python Tools/paris/gp_contact_sheet.py --strip Rampage,Jump [--frames 6] [--warm N]
    python Tools/paris/gp_contact_sheet.py --speed          (no capture, reads the report)
    python Tools/paris/gp_contact_sheet.py --tile           (no capture: re-tile the sheets from gp/,
                                                            after re-shooting a single clip with --only)
Outputs:
    Saved/Screenshots/M0_GP_Anim_Contact_Sheet.png   body shots, 6 per row
    Saved/Screenshots/M0_GP_Anim_Hands.png           key-hand close-ups, 6 per row
    Saved/Screenshots/M0_GP_Root_Speed.png           root speed curves (in-place clips)
    Saved/Screenshots/gp/<Clip>_body.png, <Clip>_hand.png, strip_<Clip>.png, after_reload.png
"""
import json
import math
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
PROJECT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import ue_shot  # noqa: E402

REPORT = os.path.join(PROJECT, "Saved", "Reports", "M0_GP_Animations.json")
SHOTS = os.path.join(PROJECT, "Saved", "Screenshots")
SINGLE = os.path.join(SHOTS, "gp")
SHEET = os.path.join(SHOTS, "M0_GP_Anim_Contact_Sheet.png")
HANDS = os.path.join(SHOTS, "M0_GP_Anim_Hands.png")
SPEED = os.path.join(SHOTS, "M0_GP_Root_Speed.png")
FONT = "C:/Windows/Fonts/msyh.ttc"

BODY_AZIMUTH = (1.0, -1.0)  # skeleton space: +X = character right, -Y = forward -> front 3/4 view (X mirrored
                            # to the key hand's side)
BODY_PITCH_DEG = -22.0      # looking down: the view to the feet clears the 24 m courtyard blocks
BODY_FILL = 0.78            # body height / frame height
HAND_DIST_M = 20.0
HEAD_TOP_CM = 16.0          # head joint -> top of the hair
COLS = 6
STRIP_COLS = 6
STRIP_FILL = 0.62           # body height / frame height in a strip cell (leaves room for the travel)


def ue(*args):
    cmd = [sys.executable, os.path.join(TOOLS, "ue_run.py"), os.path.join(HERE, "11_gp_animations.py")] + list(args)
    r = subprocess.run(cmd, cwd=PROJECT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        raise RuntimeError("ue_run %s failed (%d): %s" % (" ".join(args), r.returncode, r.stderr[-800:]))


# ---------------------------------------------------------------- camera placement


def to_world(g, p):
    """Skeleton-space cm -> world metres (actor yaw only; the giant stands upright)."""
    s, yaw = g["scale"], math.radians(g["rotation"][1])
    c, sn = math.cos(yaw), math.sin(yaw)
    loc = g["location_m"]
    return (loc[0] + (p[0] * c - p[1] * sn) * s / 100.0,
            loc[1] + (p[0] * sn + p[1] * c) * s / 100.0,
            loc[2] + p[2] * s / 100.0)


def look_at(cam, tgt):
    d = [tgt[i] - cam[i] for i in range(3)]
    yaw = math.degrees(math.atan2(d[1], d[0]))
    pitch = math.degrees(math.atan2(d[2], math.hypot(d[0], d[1])))
    return (round(cam[0], 2), round(cam[1], 2), round(cam[2], 2), round(pitch, 2), round(yaw, 2), 0.0)


def _unit(v):
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return [c / n for c in v]


def clip_top(clip):
    return max(p[2] for p in clip["key_points_cm"].values()) + HEAD_TOP_CM


def body_pose(g, clip, vfov_deg, top):
    """3/4 front view on the key hand's side (the other side hides it behind the body).

    `top` is shared by all clips (the tallest key pose), so every cell has the same scale and ground line
    and a crouch reads as a crouch instead of being zoomed in.
    """
    kp = clip["key_points_cm"]
    hips = kp["hips"]
    centre = (hips[0], hips[1], top * 0.5)
    h_m = top * g["scale"] / 100.0
    dist_m = (h_m / BODY_FILL) * 0.5 / math.tan(math.radians(vfov_deg) * 0.5)
    side = -1.0 if clip["key_hand"] == "leftHand" else 1.0
    az = _unit([side * BODY_AZIMUTH[0], BODY_AZIMUTH[1], 0.0])
    el = math.radians(-BODY_PITCH_DEG)
    d_cm = dist_m * 100.0 / g["scale"]
    cam = (centre[0] + az[0] * math.cos(el) * d_cm, centre[1] + az[1] * math.cos(el) * d_cm,
           centre[2] + math.sin(el) * d_cm)
    return look_at(to_world(g, cam), to_world(g, centre))


def hand_pose(g, clip):
    kp = clip["key_points_cm"]
    side = "left" if clip["key_hand"] == "leftHand" else "right"
    hand = kp.get(side + "MiddleProximal") or kp[clip["key_hand"]]
    hips = kp["hips"]
    out = _unit([hand[0] - hips[0], hand[1] - hips[1], 0.0])  # away from the body axis
    d = _unit([out[0] + 0.0, out[1] - 1.0, 0.45])               # ... blended with the front, from above
    d_cm = HAND_DIST_M * 100.0 / g["scale"]
    cam = [hand[i] + d[i] * d_cm for i in range(3)]
    cam[2] = max(cam[2], 4.0 * 100.0 / g["scale"])              # never below 4 m (street furniture)
    return look_at(to_world(g, cam), to_world(g, hand))


# ---------------------------------------------------------------- capture + tiling


def shoot(path, pose, warm):
    for _ in range(warm):
        ue_shot.capture(path, pose)
    return ue_shot.capture(path, pose)


def probe_vfov():
    """Vertical FOV of the capture: the shot reports the horizontal FOV, the frame gives the aspect."""
    p = os.path.join(SINGLE, "_probe.png")
    probe = shoot(p, look_at((0, 0, 100), (1, 0, 100)), 0)
    w, h = Image.open(p).size
    hfov = float(probe.get("cameraFOV") or 90.0)
    os.remove(p)
    return math.degrees(2 * math.atan(math.tan(math.radians(hfov) * 0.5) * h / float(w)))


def crop_centre(path, aspect):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    cw, ch = (int(h * aspect), h) if w / float(h) > aspect else (w, int(w / aspect))
    x0, y0 = (w - cw) // 2, (h - ch) // 2
    return im.crop((x0, y0, x0 + cw, y0 + ch))


def tile(cells, out, cell_w, aspect, title, cols=COLS):
    rows = (len(cells) + cols - 1) // cols
    cell_h = int(cell_w / aspect)
    bar, pad, head = 58, 8, 64
    W = cols * (cell_w + pad) + pad
    H = head + rows * (cell_h + bar + pad) + pad
    sheet = Image.new("RGB", (W, H), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    f_title, f_big, f_small = ImageFont.truetype(FONT, 28), ImageFont.truetype(FONT, 22), ImageFont.truetype(FONT, 15)
    d.text((pad + 4, 16), title, font=f_title, fill=(235, 235, 235))
    for i, (im, big, small) in enumerate(cells):
        r, c = divmod(i, cols)
        x = pad + c * (cell_w + pad)
        y = head + r * (cell_h + bar + pad)
        d.text((x + 6, y + 2), big, font=f_big, fill=(255, 255, 255))
        d.text((x + 6, y + 34), small, font=f_small, fill=(170, 175, 185))
        sheet.paste(im.resize((cell_w, cell_h), Image.LANCZOS), (x, y + bar))
    sheet.save(out)
    return out


def strip_pose(g, clip, vfov_deg, top):
    """One fixed camera for a whole clip: centred on the middle of the travel (hips_xy_box_cm) and pulled
    back far enough that the body and the box both fit, so the frames can be read as one motion."""
    bx = clip.get("hips_xy_box_cm") or [0, 0, 0, 0]
    cx, cy = (bx[0] + bx[2]) * 0.5, (bx[1] + bx[3]) * 0.5
    span = max(bx[2] - bx[0], bx[3] - bx[1])
    centre = (cx, cy, top * 0.5)
    # frame height: the body at STRIP_FILL, or - if the clip travels further than that leaves room for -
    # the travel plus a body width, converted through the cell aspect (0.75 w/h)
    frame_cm = max(top / STRIP_FILL, (span + 0.5 * top) / 0.75)
    dist_m = (frame_cm * g["scale"] / 100.0) * 0.5 / math.tan(math.radians(vfov_deg) * 0.5)
    az = _unit([BODY_AZIMUTH[0], BODY_AZIMUTH[1], 0.0])
    el = math.radians(-BODY_PITCH_DEG)
    d_cm = dist_m * 100.0 / g["scale"]
    cam = (centre[0] + az[0] * math.cos(el) * d_cm, centre[1] + az[1] * math.cos(el) * d_cm,
           centre[2] + math.sin(el) * d_cm)
    return look_at(to_world(g, cam), to_world(g, centre))


def strip(rep, names, frames, warm, vfov, top):
    """Evenly spaced stills of one clip from a single camera -> Saved/Screenshots/gp/strip_<Clip>.png."""
    g, out = rep["giant"], []
    for name in names:
        hit = [c for c in rep["clips"] if c["asset"] == "A_GP_" + name]
        if not hit:
            print("no report entry for %s" % name)
            continue
        clip = hit[0]
        pose = strip_pose(g, clip, vfov, top)
        cells = []
        for i in range(frames):
            t = clip["length"] * i / float(frames - 1) if frames > 1 else 0.0
            t = min(t, clip["length"] - 0.5 / clip["fps"])  # the last frame of a non-looping clip
            ue("--pose", "%s:%.4f" % (name, t))
            p = os.path.join(SINGLE, "strip_%s_%d.png" % (name, i))
            shoot(p, pose, warm)
            cells.append((crop_centre(p, 0.75), "%.2f s" % t, "%d / %d" % (i + 1, frames)))
        title = u"Tread M0 · %s %s · %.2f s · %d fps · 固定机位（125 2.4 动作甄选）" % (
            clip["use"], clip["asset"], clip["length"], clip["fps"])
        path = os.path.join(SINGLE, "strip_%s.png" % name)
        tile(cells, path, 380, 0.75, title, cols=min(STRIP_COLS, frames))
        print("strip:", path)
        out.append(path)
    return out


def speed_plot(rep, out=SPEED):
    """Root speed curves of the in-place clips (report root_motion.curve), drawn with PIL."""
    curves = [(c["asset"][len("A_GP_"):], c["use"], c["root_motion"]["curve"]) for c in rep["clips"]
              if c.get("root_motion", {}).get("curve")]
    if not curves:
        return None
    W, H = 1320, 620
    L, R, T, B = 78, 330, 76, 56  # plot margins; R leaves a legend column on the right
    im = Image.new("RGB", (W, H), (24, 24, 28))
    d = ImageDraw.Draw(im)
    f_t, f_s = ImageFont.truetype(FONT, 25), ImageFont.truetype(FONT, 16)
    t_max = max((len(c[2]["speed_cm_s"]) - 1) / float(c[2]["fps"]) for c in curves)
    v_max = max(max(c[2]["speed_cm_s"]) for c in curves) * 1.08
    px = lambda t, v: (L + (W - L - R) * t / t_max, H - B - (H - B - T) * v / v_max)
    d.text((24, 22), u"Tread M0 · GP 位移动作根速度（骨架 cm/s，×巨人缩放 = 世界速度）· 125 2.3 / 127", font=f_t,
           fill=(235, 235, 235))
    d.rectangle([L, T, W - R, H - B], outline=(70, 72, 80))
    for i in range(6):  # grid + axes
        v = v_max * i / 5.0
        y = px(0, v)[1]
        d.line([L, y, W - R, y], fill=(44, 46, 52))
        d.text((L - 46, y - 9), "%4.0f" % v, font=f_s, fill=(150, 155, 165))
        t = t_max * i / 5.0
        x = px(t, 0)[0]
        d.line([x, T, x, H - B], fill=(44, 46, 52))
        d.text((x - 14, H - B + 10), "%.1fs" % t, font=f_s, fill=(150, 155, 165))
    cols = [(120, 200, 255), (255, 170, 90), (150, 230, 140), (255, 130, 160), (200, 160, 255), (240, 225, 120),
            (130, 220, 220), (255, 210, 180)]
    for i, (name, use, cv) in enumerate(curves):
        col = cols[i % len(cols)]
        pts = [px(f / float(cv["fps"]), v) for f, v in enumerate(cv["speed_cm_s"])]
        d.line([c for p in pts for c in p], fill=col, width=2)
        y = T + 6 + i * 24
        d.line([W - R + 16, y + 9, W - R + 44, y + 9], fill=col, width=3)
        d.text((W - R + 54, y), u"%s %s · 均 %.0f / 峰 %.0f" % (
            use, name, sum(cv["speed_cm_s"]) / len(cv["speed_cm_s"]), max(cv["speed_cm_s"])), font=f_s, fill=col)
    d.text((W - R + 16, T + 12 + len(curves) * 24), u"均 = 全片均速，峰 = 单帧峰值", font=f_s, fill=(140, 145, 155))
    im.save(out)
    print("speed plot:", out)
    return out


def main(argv):
    warm = int(argv[argv.index("--warm") + 1]) if "--warm" in argv else 4
    only = set(s.strip() for s in argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None
    with open(REPORT, encoding="utf-8") as f:
        rep = json.load(f)
    g = rep["giant"]
    top = max(clip_top(c) for c in rep["clips"])  # over the whole report, --only keeps the same scale
    os.makedirs(SINGLE, exist_ok=True)
    if "--speed" in argv and "--strip" not in argv and "--only" not in argv:
        speed_plot(rep)
        return 0
    vfov = None
    body, hands, log = [], [], []
    if "--strip" in argv:
        vfov = probe_vfov()
        strip(rep, [s.strip() for s in argv[argv.index("--strip") + 1].split(",")],
              int(argv[argv.index("--frames") + 1]) if "--frames" in argv else 6, warm, vfov, top)
        ue("--play", "Idle")
        return 0
    retile = "--tile" in argv  # reuse the stills already in gp/ (one clip re-shot with --only)
    for clip in rep["clips"]:
        s = clip["asset"][len("A_GP_"):]
        if only and s not in only:
            continue
        bpath, hpath = os.path.join(SINGLE, s + "_body.png"), os.path.join(SINGLE, s + "_hand.png")
        if retile:
            bp = hp = None
        else:
            ue("--pose", s + ":key")
            if vfov is None:
                vfov = probe_vfov()
            bp, hp = body_pose(g, clip, vfov, top), hand_pose(g, clip)
            shoot(bpath, bp, warm)
            shoot(hpath, hp, warm)
        label = "%s  %s" % (clip["use"], s)
        info = "%s @ %.2f%s / %.2f s · %d fps · %s" % (clip["asset"], clip["key_time"],
                                                       u"（指定）" if clip.get("key_pinned") else "", clip["length"],
                                                       clip["fps"], "L hand" if clip["key_hand"] == "leftHand" else "R hand")
        body.append((crop_centre(bpath, 0.75), label, info))
        hands.append((crop_centre(hpath, 1.0), label, info))
        log.append({"clip": clip["asset"], "body_camera": bp, "hand_camera": hp})
        print("%-10s body %s  hand %s" % (s, bp, hp))
    title = u"Tread M0 · GP 动作全集 %d 段（125 2.3 / 127 A2）· 关键帧 = 相对骨盆离首帧最远的一帧（或指定）· 巨人 %s ×%.2f" % (
        len(body), g["actor"], g["scale"])
    if not only:
        tile(body, SHEET, 380, 0.75, title)
        tile(hands, HANDS, 380, 1.0, title.replace(u"动作全集", u"动作全集手部特写"))
        print("sheets:", SHEET, HANDS)
        speed_plot(rep)
    if retile:
        return 0
    ue("--play", "Idle")
    if "--no-reload" not in argv:
        ue("--verify-reload")
        with open(REPORT, encoding="utf-8") as f:
            rep = json.load(f)
        idle = [c for c in rep["clips"] if c["asset"] == "A_GP_Idle"][0]
        shoot(os.path.join(SINGLE, "after_reload.png"), body_pose(g, idle, vfov or 50.0, top), warm)
        print("after reload:", rep.get("reload_check"))
    with open(os.path.join(SINGLE, "cameras.json"), "w", encoding="utf-8") as f:
        json.dump({"vfov_deg": vfov, "shots": log}, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
