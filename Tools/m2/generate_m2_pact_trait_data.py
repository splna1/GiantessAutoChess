#!/usr/bin/env python3
"""M2 data generator: pacts, professions, 100-card traits, items and strategy-effect bus mapping.

Inputs (read-only):
  document/卫戍协议#1快查表.xlsx          primary operator/trait reference (95 rows)
  document/卫戍合约联机版资料整理.xlsx    pact thresholds/effects + alternative trait wording
  Content/Data/Generated/CharacterRosterMap.json   100-card key set (never modified here)
  Content/Data/Strategies.json                     32 BP strategies (never modified here)

Outputs:
  Content/Data/Source/M2_PactReference_Snapshot.json   raw rows + sha256 of both workbooks
  Content/Data/Generated/Pacts.json                    8 core + 15 adjunct pacts, thresholds, tier ops
  Content/Data/Generated/Traits.json                   100 cards -> pacts/profession/traits (event ops)
  Content/Data/Generated/M2_ItemSeeds.json             items referenced by traits / pact milestones
  Content/Data/Generated/StrategyEffects.json          strategy effect strings -> event-bus ops

Run:  python Tools/m2/generate_m2_pact_trait_data.py
The script is deterministic; re-running it with unchanged inputs produces byte-identical outputs.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from xlsx_reader import read_workbook  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "document"
QUICK_XLSX = DOC / "卫戍协议#1快查表.xlsx"
NOTES_XLSX = DOC / "卫戍合约联机版资料整理.xlsx"
ROSTER = ROOT / "Content/Data/Generated/CharacterRosterMap.json"
STRATEGIES = ROOT / "Content/Data/Strategies.json"
OUT_SOURCE = ROOT / "Content/Data/Source"
OUT_GEN = ROOT / "Content/Data/Generated"

CORE_PACTS = ["炎", "萨尔贡", "维多利亚", "谢拉格", "拉特兰", "阿戈尔", "叙拉古", "卡西米尔"]
ADJUNCT_PACTS = ["精准", "迅捷", "灵巧", "奥术", "坚守", "助力", "远见", "奇迹", "投资人",
                 "突袭", "不屈", "调和", "协防", "独行", "绝技"]
PACT_ALIASES = {"协防干员": "协防", "阿格尔": "阿戈尔"}
BENCH_COUNTED = {"远见", "奇迹", "投资人"}
PROFESSIONS = ["先锋", "近卫", "重装", "狙击", "术士", "医疗", "辅助", "特种"]
TIER_NUMBER = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6}

TRIGGER_LABELS = [
    ("<获得时>", "Acquire"), ("<进入休整期时>", "RoundStart"), ("<回合开始时>", "RoundStart"),
    ("<休整期结束时>", "RoundEnd"), ("<回合结束时>", "RoundEnd"), ("<战斗中>", "Battle"),
    ("<售出时>", "Sell"), ("<售出后>", "Sell"),
]

# Placeholder combat balance used by the M2 graybox resolver.  The reference sheets only say
# "受层数影响"; numbers are tagged balanceStatus=M2-placeholder and must be tuned in M4/M5.
CORE_COMBAT = {
    "炎": [("Attack", 0.010)], "萨尔贡": [("AttackSpeed", 0.010)], "维多利亚": [("Damage", 0.010)],
    "谢拉格": [("Damage", 0.010)], "拉特兰": [("Attack", 0.008)], "阿戈尔": [("Health", 0.012)],
    "叙拉古": [("Attack", 0.008)], "卡西米尔": [("Defense", 0.010)],
}
ADJUNCT_COMBAT = {
    "精准": [("Attack", 0.008)], "坚守": [("Health", 0.008)], "助力": [("Defense", 0.006)],
    "灵巧": [("AttackSpeed", 0.008)], "突袭": [("Attack", 0.006)], "迅捷": [("SkillRegen", 0.004)],
    "不屈": [("Health", 0.004)], "协防": [("DamageReduction", 0.0)], "奥术": [("Damage", 0.008)],
    "独行": [("Attack", 0.010)], "绝技": [("SkillRegen", 0.006)],
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nonblank(rows):
    return [r for r in rows if any(c not in (None, "") for c in r)]


def norm_pact(name):
    name = name.strip()
    return PACT_ALIASES.get(name, name)


def pacts_in(text):
    out = []
    for token in re.findall(r"【([^】]+)】", text):
        for part in token.split("/"):
            p = norm_pact(part)
            if p in CORE_PACTS or p in ADJUNCT_PACTS:
                if p not in out:
                    out.append(p)
    return out


def value_pair(text):
    """Return (base, elite) from the first 'a/b' pair in text; numbers stay as written (percent kept as number)."""
    m = re.search(r"([+-]?\d+(?:\.\d+)?)%?\s*/\s*[+-]?(\d+(?:\.\d+)?)", text)
    if not m:
        return None
    base, elite = float(m.group(1)), float(m.group(2))
    if base < 0:
        elite = -elite
    return (abs(base) if base >= 0 else base, elite)


def num(v):
    return int(v) if float(v).is_integer() else v


def effect(op, **kw):
    e = {"op": op}
    e.update(kw)
    for key in ("baseValue", "eliteValue"):
        if key in e:
            e[key] = num(e[key])
    return e


# ---------------------------------------------------------------------------------------------
# Trait text -> structured event ops.  Each rule returns a dict with the trait fields it decides;
# the caller fills ids, pacts and provenance.  Every reference row must match exactly one rule.
# ---------------------------------------------------------------------------------------------
def parse_trait(text, own_pacts):
    t = text.replace("（", "(").replace("）", ")").replace("，", ",").replace("“", "\"").replace("”", "\"")
    trig = "Passive"
    label = ""
    for lab, trg in TRIGGER_LABELS:
        if t.startswith(lab):
            trig, label = trg, lab
            t = t[len(lab):]
            break
    pair = value_pair(t)
    no_activation = "无需激活" in t
    named = pacts_in(t)
    res = {"trigger": trig, "triggerLabel": label, "triggerCondition": {}, "targets": "Self",
           "activationRequired": not no_activation, "worksOnBench": "整备区时也有效" in t,
           "repeatCount": 1, "effects": [], "runtimeSupport": "applied", "rule": ""}

    def stacks(selector, b, e, scale="Fixed", pacts=None, **kw):
        d = dict(pactSelector=selector, baseValue=b, eliteValue=e, amountScale=scale, **kw)
        if pacts:
            d["pacts"] = pacts
        return effect("AddStacks", **d)

    # Passive / combat-only abilities -------------------------------------------------------
    if trig == "Passive":
        res["stackMode"] = "Passive"
        if t.startswith("购买价格为1"):
            res.update(rule="purchase-cost-override", effects=[effect("PurchaseCostOverride", baseValue=1, eliteValue=1)])
            return res
        if t.startswith("只需2个相同"):
            res.update(rule="combine-copies", effects=[effect("CombineCopies", baseValue=2, eliteValue=2)])
            return res
        m = re.match(r"【([^】]+)】每叠加(\d+)层,本干员每秒回复(\d+)/(\d+)生命", t)
        if m:
            res.update(rule="stack-scaled-regen", runtimeSupport="combat-modifier", effects=[
                effect("StackScaledStat", pacts=[norm_pact(m.group(1))], perStacks=int(m.group(2)), stat="HealthRegen",
                       baseValue=float(m.group(3)), eliteValue=float(m.group(4)))])
            return res
        m = re.match(r"(.*?)每叠加(\d+)层,本干员(?:的)?(.+?)\+?([\d.]+)%?/[+-]?([\d.]+)", t)
        if m and named:
            stat = m.group(3)
            stat_id = ("AttackSpeed" if "攻击速度" in stat or "攻速" in stat else "Defense" if "防御" in stat
                       else "RedeployTime" if "再部署" in stat else "Attack")
            res.update(rule="stack-scaled-stat", runtimeSupport="combat-modifier",
                       effects=[effect("StackScaledStat", pacts=named, perStacks=int(m.group(2)), stat=stat_id,
                                       baseValue=float(m.group(4)), eliteValue=float(m.group(5)))])
            return res
        m = re.match(r"攻击力和生命值([\d.]+)%/\+?([\d.]+)%,核心盟约每叠加(\d+)层", t)
        if m:
            res.update(rule="core-stack-scaled-stats", runtimeSupport="combat-modifier", effects=[
                effect("FlatStat", stat="AttackHealth", baseValue=float(m.group(1)), eliteValue=float(m.group(2))),
                effect("StackScaledStat", pactSelector="OwnCorePacts", perStacks=int(m.group(3)), stat="AttackHealth",
                       baseValue=1, eliteValue=2)])
            return res
        if t.startswith("技力自然恢复速度"):
            res.update(rule="flat-skill-regen", runtimeSupport="combat-modifier",
                       effects=[effect("FlatStat", stat="SkillRegen", baseValue=pair[0], eliteValue=pair[1])])
            return res
        if t.startswith("攻击") and "敌人时攻击力提升至" in t:
            res.update(rule="enemy-tag-attack", runtimeSupport="logged-deferred-M4",
                       effects=[effect("EnemyTagAttack", tag=re.match(r"攻击(.+?)敌人", t).group(1),
                                       baseValue=pair[0], eliteValue=pair[1])])
            return res
        raise ValueError("unparsed passive: " + text)

    # Battle-time triggers -------------------------------------------------------------------
    if trig == "Battle":
        res["stackMode"] = "Battle"
        cond = res["triggerCondition"]
        if "造成的伤害变为弱点伤害" in t:
            res.update(rule="weakness-damage", runtimeSupport="logged-deferred-M4",
                       effects=[effect("WeaknessDamage", baseValue=1, eliteValue=1)])
            res["triggerCondition"] = {"event": "BattleStart"}
            return res
        if "冻结时,回复" in t:
            cond.update(event="EnemyFrozen", source="Self")
            res.update(rule="frozen-heal", runtimeSupport="logged-deferred-M4",
                       effects=[effect("HealPercent", baseValue=pair[0], eliteValue=pair[1])])
            return res
        m = re.search(r"冻结时,有(\d+)%/(\d+)%概率使已激活的【([^】]+)】层数\+(\d+)", t)
        if m:
            cond.update(event="EnemyFrozen", source="Self", chanceBase=int(m.group(1)), chanceElite=int(m.group(2)))
            amt = int(m.group(4))
            res.update(rule="frozen-chance-stacks", effects=[stacks("Pacts", amt, amt, pacts=[norm_pact(m.group(3))])])
            return res
        if t.startswith("自身被击倒"):
            cond.update(event="SelfKnockedOut", source="Self")
            effs = []
            for p, b, e in re.findall(r"【([^】]+)】层数\+(\d+)/\+(\d+)", t):
                effs.append(stacks("Pacts", int(b), int(e), pacts=[norm_pact(p)]))
            res.update(rule="self-knocked-out", effects=effs)
            return res
        m = re.search(r"每击倒(\d+)名敌人(?:时)?,使已激活的(.+?)层数\+(\d+)/\+(\d+)", t)
        if m:
            cond.update(event="Kill", source="Self", every=int(m.group(1)))
            res.update(rule="kill-every", effects=[stacks("Pacts", int(m.group(3)), int(m.group(4)), pacts=pacts_in(m.group(2)))])
            return res
        m = re.search(r"身前一格干员获得特质\"开启技能时使(已激活【([^】]+)】|自身所属已激活盟约)层数\+(\d+)/\+(\d+)\"\(每场战斗至多(\d+)层\)", t)
        if m:
            cond.update(event="SkillActivated", source="Front1", perBattleCap=int(m.group(5)))
            if m.group(2):
                eff = stacks("Pacts", int(m.group(3)), int(m.group(4)), pacts=[norm_pact(m.group(2))])
            else:
                eff = stacks("SourceUnitActivePacts", int(m.group(3)), int(m.group(4)))
            res.update(rule="grant-front-skill-trait", effects=[eff])
            return res
        m = re.search(r"(首次)?开启技能时,(?:若同一行有(\d+)名干员,)?(?:同一行每有1名干员,)?", t)
        if t.startswith("首次开启技能时") or t.startswith("开启技能时"):
            cond.update(event="SkillActivated", source="Self")
            if t.startswith("首次"):
                cond["firstOnly"] = True
            row = re.search(r"若同一行有(\d+)名干员", t)
            if row:
                cond["sameRowAtLeast"] = int(row.group(1))
            if "同一行每有1名干员" in t:
                b, e = pair
                res.update(rule="skill-row-scaled", effects=[stacks("HighestActivePact", b, e, scale="SameRowCount")])
                return res
            effs = [stacks("Pacts", int(b), int(e), pacts=[norm_pact(p)]) for p, b, e in
                    re.findall(r"【([^】]+)】(?:【[^】]+】)?层数\+(\d+)/\+(\d+)", t)]
            multi = re.search(r"((?:【[^】]+】)+)层数\+(\d+)/\+(\d+)", t)
            if multi:
                effs = [stacks("Pacts", int(multi.group(2)), int(multi.group(3)), pacts=pacts_in(multi.group(1)))]
            res.update(rule="skill-activated", effects=effs)
            return res
        m = re.search(r"(身前一格的干员|自身|自身正前方三格/身前六格的干员)每消耗(\d+)发(?:弹药|子弹),(?:若同一行有(\d+)名干员,)?使已激活的", t)
        if m:
            src = {"身前一格的干员": "Front1", "自身": "Self"}.get(m.group(1), "FrontColumn")
            cond.update(event="AmmoConsumed", source=src, every=int(m.group(2)))
            if src == "FrontColumn":
                cond.update(rangeBase=3, rangeElite=6)
            if m.group(3):
                cond["sameRowAtLeast"] = int(m.group(3))
            effs = []
            for grp, b, e in re.findall(r"((?:【[^】]+】)+)(?:干员)?层数\+(\d+)(?:/\+(\d+))?", t):
                effs.append(stacks("Pacts", int(b), int(e or b), pacts=pacts_in(grp)))
            res.update(rule="ammo-consumed", effects=effs)
            return res
        if "身前一格的干员因特质使层数提升时" in t:
            cond.update(event="FrontTraitStackGain", source="Front1")
            res.update(rule="amplify-front-stack-gain",
                       effects=[effect("AmplifyFrontStackGain", baseValue=pair[0], eliteValue=pair[1])])
            return res
        raise ValueError("unparsed battle: " + text)

    # Acquire / RoundStart / RoundEnd / Sell --------------------------------------------------
    res["stackMode"] = "Single" if trig == "Acquire" else "Persistent"
    row = re.match(r"若同一行(?:至少)?有(\d+)名干员(?:/无要求)?,", t)
    if row:
        res["triggerCondition"]["sameRowAtLeast"] = int(row.group(1))
        if "/无要求" in t[:row.end()]:
            res["triggerCondition"]["eliteIgnoresCondition"] = True
        t = t[row.end():]
    if re.match(r"(使)?(自身所属盟约|自身已激活的盟约)层数\+", t):
        sel = "OwnPacts" if "自身所属盟约" in t else "OwnActivePacts"
        res.update(rule="own-pacts", effects=[stacks(sel, *pair)])
        return res
    m = re.match(r"获得等于(\d+)%/(\d+)%的\"当前调度中心等级\"的【([^】]+)】层数", t)
    if m:
        res.update(rule="shop-level-scaled", effects=[stacks("Pacts", int(m.group(1)) / 100, int(m.group(2)) / 100,
                                                             scale="ShopLevel", pacts=[norm_pact(m.group(3))])])
        return res
    m = re.match(r"(?:使)?已激活的【([^】]+)】层数\+(\d+)/\+(\d+)", t)
    if m:
        res.update(rule="named-active-pact", effects=[stacks("Pacts", int(m.group(2)), int(m.group(3)), pacts=[norm_pact(m.group(1))])])
        return res
    m = re.match(r"((?:【[^】]+】)+)层数\+(\d+)/\+(\d+)", t)
    if m:
        res.update(rule="named-pacts", effects=[stacks("Pacts", int(m.group(2)), int(m.group(3)), pacts=pacts_in(m.group(1)))])
        return res
    if re.match(r"(进入下个休整期额外获得|使下个休整期额外获得)", t):
        res.update(rule="funds-next-round", effects=[effect("GainFundsNextRound", baseValue=pair[0], eliteValue=pair[1])])
        return res
    m = re.match(r"(?:本回合|当前休整期)每获得过(?:1|一)名干员,使已激活的(.+?)层数\+(\d+)/\+(\d+)", t)
    if m:
        res.update(rule="per-acquired", effects=[stacks("Pacts", int(m.group(2)), int(m.group(3)), scale="AcquiredThisRound", pacts=pacts_in(m.group(1)))])
        return res
    m = re.match(r"(?:当前激活且|当前已激活且)层数最多的盟约层数\+(\d+)/\+(\d+)", t)
    if m:
        res.update(rule="highest-active-pact", effects=[stacks("HighestActivePact", int(m.group(1)), int(m.group(2)))])
        return res
    m = re.match(r"使随机一个已激活的盟约层数\+(\d+)/\+(\d+),重复(\d+)次", t)
    if m:
        res.update(rule="random-active-pact", repeatCount=int(m.group(3)),
                   effects=[stacks("RandomActivePact", int(m.group(1)), int(m.group(2)))])
        return res
    m = re.match(r"使自身及身(后|前)一格干员的已激活盟约分别各层数\+(\d+)/\+(\d+)", t)
    if m:
        res.update(rule="self-and-neighbour", targets="SelfAndBehind1" if m.group(1) == "后" else "SelfAndFront1",
                   effects=[stacks("TargetActivePacts", int(m.group(2)), int(m.group(3)))])
        return res
    m = re.match(r"自身正前方的所有干员所属已激活盟约分别各层数\+(\d+)/\+(\d+)", t)
    if m:
        res.update(rule="front-column", targets="FrontColumn",
                   effects=[stacks("TargetActivePacts", int(m.group(1)), int(m.group(2)))])
        return res
    m = re.match(r"整备区每名干员所在的已激活盟约分别层数\+(\d+)/\+(\d+)", t)
    if m:
        res.update(rule="bench-units-pacts", targets="Bench",
                   effects=[stacks("TargetActivePacts", int(m.group(1)), int(m.group(2)))])
        return res
    m = re.match(r"整备区每有一个干员,使已激活的【([^】]+)】层数\+(\d+)/\+(\d+)", t)
    if m:
        res.update(rule="per-bench-unit", effects=[stacks("Pacts", int(m.group(2)), int(m.group(3)), scale="BenchCount", pacts=[norm_pact(m.group(1))])])
        return res
    m = re.match(r"本回合每花费1资金,使已激活的【([^】]+)】层数\+(\d+)/\+(\d+)", t)
    if m:
        res.update(rule="per-funds-spent", effects=[stacks("Pacts", int(m.group(2)), int(m.group(3)), scale="FundsSpentThisRound", pacts=[norm_pact(m.group(1))])])
        return res
    m = re.match(r"场上每有1名不同阶的(【[^】]+】(?:/【[^】]+】)?)干员,使已激活的(?:【[^】]+】(?:/【[^】]+】)?)层数\+(\d+)/\+(\d+)", t)
    if m:
        ps = pacts_in(m.group(1))
        res.update(rule="per-distinct-tier", effects=[stacks("Pacts", int(m.group(2)), int(m.group(3)), scale="DistinctTiersInPact", pacts=ps)])
        return res
    m = re.match(r"(?:随机)?(?:获得|制造)(\d+)/(\d+)(?:件|个)(.+)", t)
    if m and ("件" in t[:8] or "变形同构体" in t):
        item = m.group(3).strip("\"").replace("\"", "")
        res.update(rule="grant-item", effects=[effect("GrantItem", item=item, baseValue=int(m.group(1)), eliteValue=int(m.group(2)))])
        return res
    m = re.match(r"获得一件(.+?),有概率发现(.+?)。执行(\d+)/(\d+)次", t)
    if m:
        res.update(rule="grant-item-choice", effects=[effect("GrantItem", itemChoices=m.group(1).split("或"),
                                                             rareItem=m.group(2), baseValue=int(m.group(3)), eliteValue=int(m.group(4)))])
        return res
    m = re.match(r"(?:随机)?获得1名当前人数最多盟约的干员", t)
    if m:
        res.update(rule="grant-unit-top-pact", effects=[effect("GrantUnit", unitSelector="MostPopulatedPact", baseValue=1, eliteValue=1)])
        return res
    m = re.match(r"随机获得1个(.+?),执行(\d+)/(\d+)次", t)
    if m:
        names = re.split(r"[,、或]", m.group(1))
        res.update(rule="grant-unit-named", effects=[effect("GrantUnit", unitSelector="NamedOperators",
                                                            operators=[n for n in names if n], baseValue=int(m.group(2)), eliteValue=int(m.group(3)))])
        return res
    m = re.match(r"变为(\d+)/(\d+)个(.+)", t)
    if m:
        res.update(rule="sell-transform", effects=[effect("GrantUnit", unitSelector="NamedOperators",
                                                         operators=[m.group(3)], baseValue=int(m.group(1)), eliteValue=int(m.group(2)))])
        return res
    m = re.match(r"触发身前(两|1)格的其他干员的\"(获得时|休整期结束时)\"类效果", t)
    if m:
        res.update(rule="trigger-front-traits", targets="Front2" if m.group(1) == "两" else "Front1",
                   effects=[effect("TriggerTraits", triggerFilter="Acquire" if m.group(2) == "获得时" else "RoundEnd",
                                   baseValue=1, eliteValue=1)])
        return res
    if t.startswith("身前一格干员若为\"进入休整期时\"特质"):
        res.update(rule="copy-front-roundstart", targets="Front1",
                   effects=[effect("TriggerTraits", triggerFilter="RoundStart", anchor="Self", baseValue=1, eliteValue=1)])
        return res
    if t.startswith("触发场上一名拥有\"休整期结束时\"的干员的特质"):
        res.update(rule="sell-trigger-board-roundend", targets="TopRightBoardUnit",
                   effects=[effect("TriggerTraits", triggerFilter="RoundEnd", baseValue=1, eliteValue=1)])
        return res
    if t.startswith("获得1/2件随机装备") or t.startswith("获得1/2件随机"):
        res.update(rule="grant-random-item", effects=[effect("GrantItem", item="随机装备", baseValue=1, eliteValue=2)])
        return res
    raise ValueError("unparsed %s: %s" % (trig, text))


def display_value(trait):
    effs = [e for e in trait["effects"] if "baseValue" in e]
    if not effs:
        return ""
    e = effs[0]
    return "%s/%s" % (num(e["baseValue"]), num(e["eliteValue"]))


def main():
    quick = read_workbook(QUICK_XLSX)
    notes = read_workbook(NOTES_XLSX)
    quick_rows = nonblank(list(quick.values())[0])
    header = quick_rows[1]
    ref_rows = [r + [None] * (19 - len(r)) for r in quick_rows[2:] if r and r[0]]
    adj_cols = {i: norm_pact(h) for i, h in enumerate(header) if 4 <= i <= 15}

    # Alternate wording from the notes workbook (按等级 sheet) for provenance.
    alt_text = {}
    for r in nonblank(notes["按等级"])[1:]:
        if len(r) > 5 and r[1] and r[5]:
            alt_text[str(r[1]).strip()] = str(r[5]).strip()

    # ---------------------------------------------------------------- reference rows
    reference = []
    for idx, r in enumerate(ref_rows):
        name = str(r[0]).strip()
        core = [norm_pact(p) for p in str(r[3] or "").split("/") if p.strip()]
        adjunct = [adj_cols[i] for i in adj_cols if r[i] not in (None, "")]
        reference.append({
            "referenceRow": idx + 3, "operatorName": name, "operatorTier": str(r[1]).strip(),
            "profession": str(r[2]).strip(), "corePacts": core, "adjunctPacts": adjunct,
            "traitText": str(r[16]).strip(), "traitCategory": r[17], "traitTiming": r[18],
            "alternateTraitText": alt_text.get(name),
        })

    # ---------------------------------------------------------------- pacts
    pact_sheet = nonblank(notes["盟约效果"])
    sheet_info = {}
    current = None
    for r in pact_sheet[1:]:
        if len(r) < 4:
            continue
        if r[1]:
            m = re.match(r"(.+?)\((\d+)人\)", str(r[1]).strip())
            if not m:
                continue
            current = norm_pact(m.group(1))
            sheet_info[current] = {"memberCount": int(m.group(2)), "tiers": []}
        if current and r[2]:
            sheet_info[current]["tiers"].append({"count": int(str(r[2]).replace("人", "")),
                                                  "text": str(r[3]).strip()})

    def tier_ops(pid, count, text):
        ops = []
        if pid == "助力":
            ops.append(effect("AddStacks", trigger="RoundEnd", pactSelector="AllActivePacts",
                              baseValue=2 if count == 2 else 4, eliteValue=2 if count == 2 else 4, amountScale="Fixed"))
        if pid == "投资人":
            ops.append(effect("AcquireRepeat", trigger="Passive", baseValue=2, eliteValue=2))
        if pid == "协防":
            ops.append(effect("CombatFlat", trigger="Passive", stat="DamageReduction", baseValue=0.2, eliteValue=0.2))
        if pid == "调和":
            ops.append(effect("HarmonyCountsAsActiveCore", trigger="Passive", baseValue=1, eliteValue=1))
        return ops

    def milestones(pid):
        return {
            "远见": [{"every": 10, "op": "GainFundsNextRound", "amount": 2},
                   {"atLeast": 100, "once": True, "op": "ShopPriceDelta", "amount": -1}],
            "奇迹": [{"every": 50, "op": "GainFundsNextRound", "amount": 10}],
            "维多利亚": [{"every": 25, "op": "GrantItem", "item": "维氏重锤"}],
            "投资人": [{"atLeast": 70, "once": True, "op": "AcquireRepeat", "amount": 3}],
            "突袭": [{"atLeast": 30, "once": True, "op": "Flag", "flag": "DeployCostHalved"}],
            "迅捷": [{"atLeast": 40, "once": True, "op": "Flag", "flag": "AllSkillEndRegen"}],
        }.get(pid, [])

    pacts = []
    for kind, ids in (("Core", CORE_PACTS), ("Adjunct", ADJUNCT_PACTS)):
        for pid in ids:
            info = sheet_info.get(pid)
            default = [3, 6] if kind == "Core" else [2, 3]
            thresholds = [t["count"] for t in info["tiers"]] if info else default
            combat = (CORE_COMBAT if kind == "Core" else ADJUNCT_COMBAT).get(pid, [])
            tiers = []
            for i, count in enumerate(thresholds):
                text = info["tiers"][i]["text"] if info else "参考表缺失：效果待 M4 来源快照确认"
                tiers.append({"count": count, "text": text, "ops": tier_ops(pid, count, text)})
            pacts.append({
                "pactId": pid, "kind": kind, "displayName": pid,
                "thresholds": thresholds, "tiers": tiers,
                "thresholdSource": "资料整理.xlsx/盟约效果" if info else "default-%s" % "/".join(map(str, default)),
                "sourceStatus": "reference" if info else "missing-in-reference",
                "referenceMemberCount": info["memberCount"] if info else None,
                "countsBench": pid in BENCH_COUNTED,
                "isHarmony": pid == "调和",
                "skillAppliesFreeze": pid == "谢拉格",
                "combatPerStack": [{"stat": s, "perStack": v} for s, v in combat],
                "combatScope": "PactMembers" if kind == "Core" or pid in ("灵巧", "突袭", "迅捷", "独行", "绝技", "奥术") else "AllUnits",
                "balanceStatus": "M2-placeholder",
                "stackMilestones": milestones(pid),
            })

    # ---------------------------------------------------------------- items
    items = {}

    def add_item(name, provides=None, status="inferred-from-name", note=""):
        if name in items:
            return
        items[name] = {"itemId": "item_" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:8], "displayName": name,
                       "providesPacts": provides or [], "effectStatus": status, "enabled": True,
                       "note": note or "M2 seed: only pact membership is runtime-applied; full effect pending M4 ItemCatalog"}

    # ---------------------------------------------------------------- cards
    roster = json.loads(ROSTER.read_text(encoding="utf-8"))["characters"]
    by_name = {r["operatorName"]: r for r in reference}
    used = set()
    assignment = {}
    for c in roster:
        if c["originalOperatorName"] in by_name:
            assignment[c["characterId"]] = (by_name[c["originalOperatorName"]], "name-match")
            used.add(c["originalOperatorName"])
    queue = [r for r in reference if r["operatorName"] not in used]
    unassigned = [c for c in roster if c["characterId"] not in assignment]
    for c in unassigned:
        if queue:
            assignment[c["characterId"]] = (queue.pop(0), "provisional-order")
    # Five cards have no reference row.  They carry the pacts missing from both workbooks so each
    # missing pact has three members (enough for its first tier); flagged as M2 supplements.
    supplements = [
        (["叙拉古"], ["独行", "奥术"], "<获得时>自身所属盟约层数+2/+4（无需激活盟约）", "近卫"),
        (["卡西米尔"], ["绝技", "独行"], "<战斗中>每击倒1名敌人时，使已激活的【卡西米尔】层数+1/+2", "近卫"),
        (["叙拉古"], ["奥术", "绝技"], "<休整期结束时>使自身已激活的盟约层数+2/+4", "术士"),
        (["卡西米尔"], ["独行", "绝技"], "<售出时>进入下个休整期额外获得1/2资金", "狙击"),
        (["叙拉古", "卡西米尔"], ["奥术"], "<进入休整期时>使自身已激活的盟约层数+2/+4", "特种"),
    ]
    sup_iter = iter(supplements)

    cards = []
    trigger_counts = {}
    rule_counts = {}
    for c in roster:
        cid = c["characterId"]
        if cid in assignment:
            ref, how = assignment[cid]
            core, adj, prof, text = ref["corePacts"], ref["adjunctPacts"], ref["profession"], ref["traitText"]
            tier = ref["operatorTier"]
            source = "快查表#%d" % ref["referenceRow"]
            ref_name = ref["operatorName"]
        else:
            s = next(sup_iter)
            core, adj, text, prof = s[0], s[1], s[2], s[3]
            tier, how, source, ref_name = None, "supplement", "M2-supplement(no reference row)", None
        parsed = parse_trait(text, core + adj)
        for e in parsed["effects"]:
            for name in [e.get("item")] + list(e.get("itemChoices", [])) + [e.get("rareItem")]:
                if name:
                    add_item(name, ["迅捷"] if name == "迅捷作战箱" else ["谢拉格"] if name == "谢拉格不融冰"
                             else ["萨尔贡"] if name == "萨尔贡浓茶" else [])
        trait = {
            "id": "trait_%s_01" % cid, "cardId": cid,
            "rarity": TIER_NUMBER.get(tier) if tier else None,
            "corePacts": core, "adjunctPacts": adj,
            "trigger": parsed["trigger"], "triggerLabel": parsed["triggerLabel"],
            "triggerCondition": parsed["triggerCondition"], "stackMode": parsed["stackMode"],
            "targets": parsed["targets"], "activationRequired": parsed["activationRequired"],
            "worksOnBench": parsed["worksOnBench"], "repeatCount": parsed["repeatCount"],
            "effects": parsed["effects"], "stackCap": 100, "scalePerStack": 1,
            "displayText": text, "valueText": display_value(parsed),
            "sourcePattern": source, "parseRule": parsed["rule"], "runtimeSupport": parsed["runtimeSupport"],
        }
        first = next((e for e in parsed["effects"] if "baseValue" in e), None)
        trait["baseValue"] = first["baseValue"] if first else 0
        trait["eliteValue"] = first["eliteValue"] if first else 0
        combine = next((e["baseValue"] for e in parsed["effects"] if e["op"] == "CombineCopies"), 3)
        trigger_counts[trait["trigger"]] = trigger_counts.get(trait["trigger"], 0) + 1
        rule_counts[trait["parseRule"]] = rule_counts.get(trait["parseRule"], 0) + 1
        cards.append({
            "characterId": cid, "originalOperatorName": c["originalOperatorName"],
            "referenceOperatorName": ref_name, "referenceOperatorTier": tier,
            "assignment": how, "assignmentStatus": "M2-provisional; authoritative roster closes in M4",
            "corePacts": core, "adjunctPacts": adj, "profession": prof,
            "consumesAmmo": prof == "狙击", "combineCopies": combine, "traits": [trait],
        })
    add_item("维氏重锤", [], "inferred-from-name", "维多利亚 25-stack milestone reward")
    add_item("随机装备", [], "placeholder", "random equipment marker; resolved to a seed item at runtime")

    # ---------------------------------------------------------------- strategies -> bus
    strategies = json.loads(STRATEGIES.read_text(encoding="utf-8"))["strategies"]
    trig_map = {"MatchStart": "MatchStart", "RoundStart": "RoundStart", "RoundEnd": "RoundEnd", "Sell": "Sell",
                "BattleStart": "BattleStart", "Combine": "Combine", "Settlement": "Settlement"}
    effect_rules = [
        (r"^OpeningFunds\+(\d+)$", lambda m: effect("GainFunds", baseValue=int(m.group(1)), eliteValue=int(m.group(1)))),
        (r"^PrecisionPact\+(\d+)$", lambda m: effect("AddStacks", pactSelector="Pacts", pacts=["精准"], baseValue=int(m.group(1)), eliteValue=int(m.group(1)), amountScale="Fixed")),
        (r"^HarmonyPact\+(\d+)$", lambda m: effect("AddStacks", pactSelector="Pacts", pacts=["调和"], baseValue=int(m.group(1)), eliteValue=int(m.group(1)), amountScale="Fixed")),
        (r"^SellGold\+(\d+)$", lambda m: effect("GainFunds", baseValue=int(m.group(1)), eliteValue=int(m.group(1)))),
        (r"^FirstThreeCombineGold\+(\d+)$", lambda m: effect("GainFunds", baseValue=int(m.group(1)), eliteValue=int(m.group(1)), once=True)),
        (r"^ArcaneActivationThreshold-(\d+)$", lambda m: effect("PactThresholdDelta", pacts=["奥术"], baseValue=-int(m.group(1)), eliteValue=-int(m.group(1)))),
        (r"^BenchCountsForForesight$", lambda m: effect("PactCountsBench", pacts=["远见"], baseValue=1, eliteValue=1)),
    ]
    strategy_effects = []
    for s in strategies:
        ops = []
        for raw in s["effects"]:
            op = None
            for pat, build in effect_rules:
                m = re.match(pat, raw)
                if m:
                    op = build(m)
                    break
            ops.append({"raw": raw, "op": op, "runtimeSupport": "applied" if op else "logged-deferred-M4"})
        strategy_effects.append({"strategyId": s["strategyId"], "trigger": trig_map.get(s["trigger"], s["trigger"]),
                                 "sourceTrigger": s["trigger"], "effects": ops})

    # ---------------------------------------------------------------- write
    OUT_SOURCE.mkdir(parents=True, exist_ok=True)
    OUT_GEN.mkdir(parents=True, exist_ok=True)
    provenance = {"quickTable": {"path": "document/卫戍协议#1快查表.xlsx", "sha256": sha256(QUICK_XLSX), "rows": len(reference)},
                  "notesTable": {"path": "document/卫戍合约联机版资料整理.xlsx", "sha256": sha256(NOTES_XLSX)},
                  "roster": {"path": "Content/Data/Generated/CharacterRosterMap.json", "sha256": sha256(ROSTER)},
                  "strategies": {"path": "Content/Data/Strategies.json", "sha256": sha256(STRATEGIES)},
                  "generator": "Tools/m2/generate_m2_pact_trait_data.py"}

    def dump(path, obj):
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")

    dump(OUT_SOURCE / "M2_PactReference_Snapshot.json", {
        "schemaVersion": "Tread.M2.PactReferenceSnapshot.v1", "provenance": provenance,
        "pactSheet": sheet_info, "operators": reference})
    dump(OUT_GEN / "Pacts.json", {
        "schemaVersion": "Tread.M2.Pacts.v1", "provenance": provenance,
        "rules": {"countDistinctCharacters": True, "boardCounts": True, "benchCountsForPacts": sorted(BENCH_COUNTED),
                  "eliteStarAtLeast": 2, "stackCap": 999, "harmony": "each already-active core pact +1 per active 调和 member",
                  "professions": PROFESSIONS, "professionIsPact": False,
                  "battle": {"skillEveryAttacks": 3, "ammoPerAttack": 1, "frozenOnSkillForPact": "谢拉格"}},
        "pacts": pacts})
    dump(OUT_GEN / "Traits.json", {
        "schemaVersion": "Tread.M2.Traits.v1", "provenance": provenance,
        "summary": {"cards": len(cards), "traits": sum(len(c["traits"]) for c in cards), "triggers": trigger_counts,
                    "parseRules": rule_counts,
                    "assignment": {k: sum(1 for c in cards if c["assignment"] == k) for k in ("name-match", "provisional-order", "supplement")}},
        "cards": cards})
    dump(OUT_GEN / "M2_ItemSeeds.json", {"schemaVersion": "Tread.M2.ItemSeeds.v1", "provenance": provenance,
                                         "items": sorted(items.values(), key=lambda i: i["itemId"])})
    dump(OUT_GEN / "StrategyEffects.json", {"schemaVersion": "Tread.M2.StrategyEffects.v1", "provenance": provenance,
                                            "strategies": strategy_effects})
    print("cards=%d traits=%d triggers=%s" % (len(cards), len(cards), trigger_counts))
    print("rules=%s" % rule_counts)
    print("pacts=%d items=%d strategies=%d" % (len(pacts), len(items), len(strategy_effects)))


if __name__ == "__main__":
    main()
