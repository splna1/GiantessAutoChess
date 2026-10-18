"""Render the M1 UI HTML prototype to PNG at 1600x900 / 1920x1080 / 2560x1440 and build the 1920x1080 overview.

    python Tools/ui/m1_ui_render.py [--screens prep,bp,...] [--res 1920x1080,...]

Steps: tokens.js <- M1_UI_Tokens.json; assets/board_bg.png <- M0 Board_Camera baseline (read-only copy);
icons/*.svg <- icons.js; Playwright (installed Chrome) renders index.html?screen=..&w=..&h=..; PIL builds the overview.
Output: document/M1_UI/renders/M1_UI_<screen>_<w>x<h>.png (+ _annotated at 1920x1080), M1_UI_Overview_1920x1080.png.
"""
import argparse
import json
import os
import pathlib
import shutil

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
UI = ROOT / "document" / "M1_UI"
PROTO = UI / "prototype"
RENDERS = UI / "renders"
BOARD_SHOT = ROOT / "Saved" / "Screenshots" / "M0_Paris_Realistic_Board_Baseline.png"
SCREENS = ["bp", "bp_done", "scout", "prep", "battle", "battle_end", "result", "result_out", "states"]
RESOLUTIONS = [(1600, 900), (1920, 1080), (2560, 1440)]
TITLES = {"bp": "① 赛前 BP（AI 选择中）", "scout": "② ScoutSnapshot 侦察", "prep": "③ 准备期 商店 / 拖拽部署",
          "battle": "④ 自动战斗", "result": "④ 结算（胜负 / 生命 / 名次 / 淘汰）", "states": "控件状态总表"}


def prepare():
    tokens = json.loads((UI / "M1_UI_Tokens.json").read_text(encoding="utf-8"))
    (PROTO / "tokens.js").write_text("// generated from M1_UI_Tokens.json - do not edit\nwindow.TOKENS = "
                                     + json.dumps(tokens, ensure_ascii=False, indent=1) + ";\n", encoding="utf-8")
    (PROTO / "assets").mkdir(exist_ok=True)
    background = PROTO / "assets" / "board_bg.png"
    if not background.exists():
        shutil.copyfile(BOARD_SHOT, background)
    RENDERS.mkdir(exist_ok=True)


def export_icons(page):
    icons = page.evaluate("window.ICONS")
    folder = UI / "icons"
    folder.mkdir(exist_ok=True)
    for name, body in icons.items():
        (folder / ("ic_" + name + ".svg")).write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" color="#FFFFFF">'
            + body.replace("currentColor", "#FFFFFF") + "</svg>\n", encoding="utf-8")
    return sorted(icons)


def render(screens, resolutions):
    out = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome")
        for width, height in resolutions:
            page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
            for screen in screens:
                for notes in ((0, 1) if (width, height) == (1920, 1080) and screen != "states" else (0,)):
                    url = (PROTO / "index.html").as_uri() + "?screen=%s&w=%d&h=%d&notes=%d" % (screen, width, height, notes)
                    page.goto(url)
                    page.wait_for_function("window.PROTO_READY === true")
                    page.evaluate("document.fonts.ready")
                    page.wait_for_timeout(150)
                    path = RENDERS / ("M1_UI_%s_%dx%d%s.png" % (screen, width, height, "_annotated" if notes else ""))
                    page.screenshot(path=str(path))
                    out.append(path)
            if (width, height) == (1920, 1080):
                icons = export_icons(page)
            page.close()
        browser.close()
    return out, icons


def overview():
    canvas = Image.new("RGB", (1920, 1080), (7, 10, 16))
    draw = ImageDraw.Draw(canvas)
    font_path = "C:/Windows/Fonts/NotoSansSC-VF.ttf"
    title = ImageFont.truetype(font_path, 34)
    label = ImageFont.truetype(font_path, 22)
    small = ImageFont.truetype(font_path, 18)
    draw.text((32, 20), "踏国 TREAD · M1 最小对局闭环 UI 总览（1920×1080 原型）", font=title, fill=(238, 242, 248))
    draw.text((32, 66), "主菜单 → 第 1 关 → R0 简报 → 赛前 BP → 准备期（商店/拖拽部署/侦察）→ 自动战斗 → 结算 → 下一回合", font=small, fill=(174, 184, 199))
    tiles = ["bp", "scout", "prep", "battle", "result", "states"]
    tile_w, tile_h, gap = 608, 342, 24
    for index, screen in enumerate(tiles):
        col, row = index % 3, index // 3
        x, y = 32 + col * (tile_w + gap), 112 + row * (tile_h + 64)
        image = Image.open(RENDERS / ("M1_UI_%s_1920x1080.png" % screen)).convert("RGB").resize((tile_w, tile_h), Image.LANCZOS)
        canvas.paste(image, (x, y))
        draw.rectangle((x - 1, y - 1, x + tile_w, y + tile_h), outline=(60, 72, 92), width=2)
        draw.text((x, y + tile_h + 10), TITLES[screen], font=label, fill=(238, 242, 248))
    swatches = [("玩家方", (61, 139, 255)), ("敌方/AI", (255, 77, 79)), ("资金", (245, 196, 81)), ("生命", (255, 90, 110)),
                ("可放置", (57, 208, 255)), ("落点", (255, 225, 77)), ("交换", (255, 176, 32)), ("成功", (61, 214, 140))]
    x = 32
    for name, rgb in swatches:
        draw.rounded_rectangle((x, 1030, x + 26, 1056), radius=6, fill=rgb)
        draw.text((x + 34, 1030), name, font=small, fill=(174, 184, 199))
        x += 150
    draw.text((1320, 1030), "原型 · 示例数据 · 字体 Noto Sans SC (OFL)", font=small, fill=(125, 135, 150))
    path = RENDERS / "M1_UI_Overview_1920x1080.png"
    canvas.save(path)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screens", default=",".join(SCREENS))
    parser.add_argument("--res", default=",".join("%dx%d" % r for r in RESOLUTIONS))
    args = parser.parse_args()
    screens = args.screens.split(",")
    resolutions = [tuple(int(v) for v in r.split("x")) for r in args.res.split(",")]
    prepare()
    files, icons = render(screens, resolutions)
    if all((RENDERS / ("M1_UI_%s_1920x1080.png" % s)).exists() for s in TITLES):
        files.append(overview())
    print("rendered %d files, %d icons" % (len(files), len(icons)))


if __name__ == "__main__":
    main()
