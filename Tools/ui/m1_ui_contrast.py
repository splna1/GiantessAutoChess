"""WCAG contrast audit of the M1 UI tokens (pure Python, no UE).

Every text/background pair is composited over the worst-case world pixel under the translucent panel: pure white
(sunlit facade) and pure black (shadow). The lower ratio is reported; pairs below their minimum fail.

    python Tools/ui/m1_ui_contrast.py            -> prints a table, writes document/M1_UI/M1_UI_Contrast_Report.json
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOKENS = os.path.join(ROOT, "document", "M1_UI", "M1_UI_Tokens.json")
REPORT = os.path.join(ROOT, "document", "M1_UI", "M1_UI_Contrast_Report.json")


def parse(value):
    """'#RRGGBB' or 'rgba(r, g, b, a)' -> (r, g, b, a) in 0..1."""
    if value.startswith("#"):
        return tuple(int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)) + (1.0,)
    numbers = [float(n) for n in re.findall(r"[\d.]+", value)]
    return numbers[0] / 255, numbers[1] / 255, numbers[2] / 255, numbers[3] if len(numbers) > 3 else 1.0


def over(top, bottom):
    alpha = top[3]
    return tuple(top[i] * alpha + bottom[i] * (1 - alpha) for i in range(3)) + (1.0,)


def luminance(color):
    channel = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in color[:3]]
    return 0.2126 * channel[0] + 0.7152 * channel[1] + 0.0722 * channel[2]


def ratio(a, b):
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def lookup(tokens, dotted):
    node = tokens
    for key in dotted.split("."):
        node = node[key]
    return node


# (label, foreground token, background stack bottom->top above the world pixel, minimum ratio)
PAIRS = [
    ("正文 on panel", "color.text.primary", ["color.bg.panel"], 4.5),
    ("次要文字 on panel", "color.text.secondary", ["color.bg.panel"], 4.5),
    ("禁用文字 on panel (非必需信息)", "color.text.disabled", ["color.bg.panel"], 3.0),
    ("正文 on raised panel", "color.text.primary", ["color.bg.panelRaised"], 4.5),
    ("次要文字 on raised panel", "color.text.secondary", ["color.bg.panelRaised"], 4.5),
    ("正文 on modal (scrim+raised)", "color.text.primary", ["color.bg.scrimModal", "color.bg.panelRaised"], 4.5),
    ("生命数字 on panel", "color.resource.healthText", ["color.bg.panel"], 4.5),
    ("资金数字 on panel", "color.resource.funds", ["color.bg.panel"], 4.5),
    ("等级数字 on panel", "color.resource.level", ["color.bg.panel"], 4.5),
    ("人口数字 on panel", "color.resource.population", ["color.bg.panel"], 4.5),
    ("玩家蓝文字 on panel", "color.faction.playerText", ["color.bg.panel"], 4.5),
    ("敌方红文字 on panel", "color.faction.enemyText", ["color.bg.panel"], 4.5),
    ("AI1 文字 on panel", "color.faction.ai1Text", ["color.bg.panel"], 4.5),
    ("AI2 文字 on panel", "color.faction.ai2Text", ["color.bg.panel"], 4.5),
    ("AI3 文字 on panel", "color.faction.ai3Text", ["color.bg.panel"], 4.5),
    ("成功 on panel", "color.semantic.success", ["color.bg.panel"], 4.5),
    ("警告 on panel", "color.semantic.warning", ["color.bg.panel"], 4.5),
    ("锁定金 on panel", "color.semantic.locked", ["color.bg.panel"], 4.5),
    ("白字 on 玩家主按钮", "color.text.onAccent", ["color.faction.playerStrong"], 4.5),
    ("白字 on 敌方深红", "color.text.onAccent", ["color.faction.enemyStrong"], 4.5),
    ("深字 on 黄色落点", "color.text.inverse", ["color.cell.targetEdge"], 4.5),
    ("深字 on 资金金色徽章", "color.text.inverse", ["color.resource.funds"], 4.5),
    ("星级 on panel", "color.star", ["color.bg.panel"], 3.0),
] + [("阶级 %s on panel" % tier, "color.tier.%s" % tier, ["color.bg.panel"], 4.5) for tier in ("I", "II", "III", "IV", "V", "VI")]


def main():
    with open(TOKENS, encoding="utf-8") as stream:
        tokens = json.load(stream)
    rows = []
    for label, fg_key, bg_keys, minimum in PAIRS:
        worst = None
        for world in ((1.0, 1.0, 1.0, 1.0), (0.0, 0.0, 0.0, 1.0)):
            backdrop = world
            for key in bg_keys:
                backdrop = over(parse(lookup(tokens, key)), backdrop)
            value = ratio(over(parse(lookup(tokens, fg_key)), backdrop), backdrop)
            worst = value if worst is None else min(worst, value)
        rows.append({"pair": label, "fg": fg_key, "bg": bg_keys, "worst_ratio": round(worst, 2), "min": minimum,
                     "pass": worst >= minimum})
    with open(REPORT, "w", encoding="utf-8") as stream:
        json.dump({"tokens": "M1_UI_Tokens.json", "method": "composited over white and black world pixel, worst kept",
                   "rows": rows, "ok": all(row["pass"] for row in rows)}, stream, ensure_ascii=False, indent=2)
    sys.stdout.reconfigure(encoding="utf-8")
    for row in rows:
        print("%-28s %6.2f  (>= %.1f)  %s" % (row["pair"], row["worst_ratio"], row["min"], "PASS" if row["pass"] else "FAIL"))
    failed = [row for row in rows if not row["pass"]]
    print("ok" if not failed else "%d FAIL" % len(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
