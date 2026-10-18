"""Render the M1 UMG hierarchy diagram (layer tree + 1920x1080 anchor map with board keep-out) to PNG.

    python Tools/ui/m1_ui_umg_diagram.py

Reads document/M1_UI/M1_UI_Tokens.json (layout, zOrder, boardKeepOut); writes
document/M1_UI/renders/M1_UI_UMG_Hierarchy.png via Playwright (installed Chrome).
"""
import json
import pathlib

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
UI = ROOT / "document" / "M1_UI"
OUT = UI / "renders" / "M1_UI_UMG_Hierarchy.png"

VIS = {"S": ("#8FD3FF", "SelfHitTestInvisible"), "H": ("#7D8796", "HitTestInvisible"), "V": ("#3DD68C", "Visible")}

# (depth, name, visibility, zOrder/anchor note)
TREE = [
    (0, "WBP_MatchHUD 根 CanvasPanel", "S", "Viewport"),
    (1, "WorldLayer", "H", "Z0"),
    (2, "WBP_UnitPlate ×N · WBP_DamageNumber ×N · WBP_CellHint", "H", "投影跟随"),
    (1, "HudBase", "S", "Z10"),
    (2, "WBP_PlayerStatus", "S", "TL"), (2, "WBP_RoundStatus", "H", "TC"), (2, "WBP_RankStrip → WBP_RankChip ×4", "V", "TR"),
    (1, "HudPanels", "S", "Z20"),
    (2, "WBP_StrategyChip", "V", "TL"), (2, "WBP_ShopPanel → WBP_ShopCard ×5 · 刷新 · 经验 · 锁", "V", "TR"),
    (2, "WBP_SellZone（几何判定）", "H", "BL"), (2, "WBP_BenchBar → WBP_BenchSlot ×8", "V", "BC"),
    (2, "WBP_ActionPanel → 部署 · 自动战斗", "V", "BR"), (2, "WBP_MatchupPanel（战斗）", "H", "TL"),
    (2, "WBP_KillFeed（战斗）", "H", "TR"),
    (1, "ScoutDismissCatcher（点外部关闭）", "V", "Z29"),
    (1, "WBP_ScoutPanel → ScoutRow ×4 · 4×8 阵容 · 备战席 · 装备 · 盟约", "V", "Z30 TC"),
    (1, "WBP_BattleEndBanner", "H", "Z40 TC"),
    (1, "WBP_BPScreen → StrategyCard ×32 · BPSidePanel · 确认", "V", "Z50 Fill"),
    (1, "WBP_ResultModal → ResultRow ×4 · 继续", "V", "Z60 Center"),
    (1, "TooltipLayer → WBP_Tooltip · WBP_ScoutTooltip", "H", "Z80"),
    (1, "WBP_DragVisual（跟随鼠标）", "H", "Z90"),
    (1, "ToastLayer → WBP_Toast", "H", "Z95"),
]

MAP = [("playerStatus", "PlayerStatus"), ("roundStatus", "RoundStatus"), ("rankStrip", "RankStrip"),
       ("strategyChip", "StrategyChip"), ("shopPanel", "ShopPanel"), ("sellZone", "SellZone"), ("bench", "BenchBar"),
       ("actionPanel", "ActionPanel"), ("matchupPanel", "MatchupPanel（战斗）"), ("killFeed", "KillFeed（战斗）"),
       ("scoutPanel", "ScoutPanel（按需）")]


def rect(layout):
    (w, h), (px, py), anchor = layout["size"], layout["pos"], layout["anchor"]
    x = {"Left": px, "Center": 960 - w / 2 + px, "Right": 1920 + px - w}[
        "Left" if anchor.endswith("Left") else "Right" if anchor.endswith("Right") else "Center"]
    y = py if anchor.startswith("Top") else 1080 + py - h
    return x, y, w, h


def html(tokens):
    rows = "".join(
        '<div class="r" style="padding-left:%dpx"><i style="background:%s"></i><b>%s</b><span>%s</span></div>'
        % (8 + depth * 26, VIS[vis][0], name, note) for depth, name, vis, note in TREE)
    legend = "".join('<span><i style="background:%s"></i>%s</span>' % c for c in VIS.values())
    s = 0.42
    boxes = ""
    for key, label in MAP:
        x, y, w, h = rect(tokens["layout"][key])
        dashed = "dashed" if key in ("matchupPanel", "killFeed", "scoutPanel") else "solid"
        boxes += ('<div class="b" style="left:%.0fpx;top:%.0fpx;width:%.0fpx;height:%.0fpx;border-style:%s">%s</div>'
                  % (x * s, y * s, w * s, h * s, dashed, label))
    quad = lambda q: " ".join("%.1f,%.1f" % (f[0] * 1920 * s, f[1] * 1080 * s) for f in q)
    keep = tokens["layout"]["boardKeepOut"]
    return """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body{margin:0;background:#070A10;color:#EEF2F8;font-family:'Noto Sans SC';width:1920px;height:1080px;position:relative}
h1{position:absolute;left:32px;top:16px;margin:0;font-size:34px} .sub{position:absolute;left:32px;top:64px;font-size:18px;color:#AEB8C7}
.tree{position:absolute;left:32px;top:110px;width:980px} .r{display:flex;align-items:center;gap:10px;height:36px;font-size:18px;border-bottom:1px solid rgba(255,255,255,.06)}
.r i,.lg i{width:14px;height:14px;border-radius:4px;display:inline-block;flex:0 0 auto} .r b{font-weight:700} .r span{margin-left:auto;color:#AEB8C7;font-size:16px;padding-right:8px}
.lg{position:absolute;left:32px;top:1020px;display:flex;gap:28px;font-size:16px;color:#AEB8C7} .lg span{display:flex;gap:8px;align-items:center}
.map{position:absolute;left:1052px;top:130px;width:806px;height:454px;background:#121822;border:2px solid #3C485C}
.b{position:absolute;border:2px solid #8FD3FF;background:rgba(143,211,255,.10);font-size:14px;color:#EEF2F8;padding:2px 4px;box-sizing:border-box;overflow:hidden;white-space:nowrap}
.cap{position:absolute;left:1052px;top:96px;font-size:18px;color:#AEB8C7} .notes{position:absolute;left:1052px;top:610px;width:806px;font-size:16px;color:#AEB8C7;line-height:1.6}
.notes b{color:#EEF2F8}
</style></head><body>
<h1>M1 UMG 控件层级图</h1><div class="sub">根 HUD 不拦截 3D 棋盘点击 · 拖拽松手只由 PlayerController 上的 UTreadDragController 处理一次 · 数值来自 M1_UI_Tokens.json</div>
<div class="tree">%s</div>
<div class="cap">锚点布局（1920×1080 ref，虚线=阶段性面板；红=玩家半场禁入区，橙虚线=全棋盘）</div>
<div class="map"><svg width="806" height="454" style="position:absolute;left:0;top:0">
<polygon points="%s" fill="none" stroke="#FFB020" stroke-width="2" stroke-dasharray="6 5"/>
<polygon points="%s" fill="rgba(255,77,79,.18)" stroke="#FF4D4F" stroke-width="2"/></svg>%s</div>
<div class="notes"><b>命中规则</b>：根与层容器 SelfHitTestInvisible；纯展示控件 HitTestInvisible；按钮/卡/槽 Visible。<br>
<b>禁入区</b>：准备期玩家 4 行投影内不得有 Visible 控件；战斗期整个棋盘内不得有 Visible 控件。<br>
<b>模态</b>：BPScreen(Z50)、ResultModal(Z60) 全屏 Scrim 拦截全部点击（这两个阶段棋盘不可操作）。<br>
<b>侦察</b>：ScoutDismissCatcher(Z29) 吃掉“点外部关闭”的那一次点击，避免误触棋盘/商店。<br>
<b>拖拽</b>：WBP 不实现 OnDrop / DragDropOperation；DragSessionId 一次松手一次消费，逻辑层同 Id 幂等。</div>
<div class="lg">%s</div></body></html>""" % (rows, quad(keep["fullBoardQuad"]), quad(keep["playerHalfQuad"]), boxes, legend)


def main():
    tokens = json.loads((UI / "M1_UI_Tokens.json").read_text(encoding="utf-8"))
    page_file = UI / "prototype" / "umg_diagram.html"
    page_file.write_text(html(tokens), encoding="utf-8")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto(page_file.as_uri())
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(200)
        page.screenshot(path=str(OUT))
        browser.close()
    print("wrote", OUT)


if __name__ == "__main__":
    main()
