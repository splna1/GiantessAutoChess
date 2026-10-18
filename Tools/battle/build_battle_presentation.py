"""Battle presentation table (document/12): timing, movement and the clip / effect mapping per profession and attack kind.

Writes Content/Data/Generated/BattlePresentation.json, read by ATreadM3BoardPresenter (TreadM3BattlePresentation.cpp).
The presenter only replays MatchState.BattleEvents; this table decides how an event looks, never what happens.

    python Tools/battle/build_battle_presentation.py

Clip names are the 33 GP clips (document/127) without the A_GP_ prefix; every character plays its own retargeted copy
(/Game/Tread/Characters/<Set>/<id>/Anim/A_GP_<Clip>) or, without one, the hero's whole set.
Clip lengths (char_002, seconds): Kick 6.53, KickRight 4.18, Smash 4.52, SmashLow 5.92, Stomp 2.87, Throw 2.25,
Crush 3.17, Rampage 4.60, KneelSmash 9.67, Grab 4.03, Hold 1.33, Defeat 6.50, Victory 3.45, Walk 1.50, Run 1.77.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "Content", "Data", "Generated", "BattlePresentation.json")
ROSTER = os.path.join(ROOT, "Content", "Data", "Generated", "CharacterRosterMap.json")

# Skill branches of document/12 §3.4 (old 113): one per profession, each with its own clip chain and colour.
PROFESSIONS = {
    "先锋": {"branch": "筑造修复", "melee": ["Kick", "KickRight"], "skill": ["Stomp"], "color": [1.00, 0.72, 0.18]},
    "近卫": {"branch": "特攻单体", "melee": ["Smash", "Kick", "SmashLow"], "skill": ["KneelSmash"], "color": [1.00, 0.22, 0.16]},
    "重装": {"branch": "碾压溅射", "melee": ["Stomp", "Smash"], "skill": ["Crush"], "color": [0.35, 0.62, 1.00]},
    "狙击": {"branch": "投掷远程爆发", "melee": ["KickRight"], "skill": ["Throw"], "color": [1.00, 0.86, 0.30]},
    "术士": {"branch": "空袭范围", "melee": ["SmashLow"], "skill": ["Rampage"], "color": [0.78, 0.36, 1.00]},
    "医疗": {"branch": "守护护盾治疗", "melee": ["Kick"], "skill": ["Hold"], "color": [0.30, 1.00, 0.55]},
    "辅助": {"branch": "咆哮眩晕", "melee": ["KickRight"], "skill": ["Rampage"], "color": [0.40, 0.95, 1.00]},
    "特种": {"branch": "抓取控制", "melee": ["KickRight", "SmashLow"], "skill": ["Grab", "Hold", "Throw"], "color": [1.00, 0.40, 0.75]},
}

# attackKind (roster) decides melee vs ranged: ranged and heal units throw a projectile from where they stand.
ATTACK_KINDS = {
    "melee": {"ranged": False, "clips": None},
    "none": {"ranged": False, "clips": None},
    "ranged": {"ranged": True, "clips": ["Throw"]},
    "heal": {"ranged": True, "clips": ["Throw"], "projectileColor": [0.30, 1.00, 0.55]},
}

TIMING = {
    "approachSec": 3.5,          # everyone reaches its engagement point by then (walk, run when farther)
    "secPerExchange": 2.2,       # event sequence -> time: exchanges of the resolver spread over the fight
    "fightMinSec": 8.0,
    "fightMaxSec": 27.0,         # approach + fight + victory stays well inside the 45 s battle cap
    "victoryDelaySec": 0.8,
    "victoryHoldSec": 3.6,
    "attackPlayRate": 1.6,
    "skillPlayRate": 1.35,
    "defeatPlayRate": 1.7,
    "defeatHoldSec": 1.0,
    "hitFraction": 0.42,         # share of an attack clip after which the blow lands (melee)
    "releaseFraction": 0.5,      # share of a throw after which the projectile leaves the hand
    "projectileSec": 0.55,
    "floaterSec": 1.4,
    "skillLabelSec": 2.4,
    "turnDegPerSec": 240.0,
}

MOVEMENT = {
    "walkCellsPerSec": 0.98,     # 196 m/s (document/127 §1.1) on 200 m cells
    "runCellsPerSec": 1.96,
    "meleeRangeCells": 0.8,
    # 1.8 (was 3.2): with the old half-board stop distance the ranged side stood still the whole battle
    # (only the melee side closed in); 1.8 makes both sides take visible steps before throwing.
    "rangedRangeCells": 1.8,
    "stackGapCells": 0.75,
    "minMoveSec": 0.8,           # short engagements still take a visible step (no teleporting into contact)
}

CLIPS = {"idle": "Idle", "walk": "Walk", "run": "Run", "defeat": "Defeat", "victory": "Victory"}

CAMERA = {
    # document/125 §4.1: east end of the x = 0 divider street, looking west at the Eiffel Tower (0, -1300) m.
    # document/162 §4.4: raised from 14 m to 34 m so the camera sits slightly above the board buildings (the
    # Haussmann L modules are ~24-26 m) and the line of sight clears the roofs; pitch follows the board centre.
    # document/180: 78 m clears the rooftops; the pitch stays near level (-1.5°) because a -7° tilt framed only
    # the giants' legs (units are 115 m tall, the camera is 78 m up).
    "audienceLocationM": [0.0, 1000.0, 78.0],
    "audienceYawDeg": -90.0,
    "audiencePitchDeg": -1.5,
    "audienceFovDeg": 20.0,
    "blendSec": 0.6,
    "killShotSec": 2.6,
    # document/162 §4.5: close-up kill camera. Units are 115 m tall, so the shot stands 380 m off (vertical frame at
    # 30° covers ~204 m); the camera sits high (170 m) so the frame tilts down onto the ground and the collapsing
    # buildings + dust around the victim are inside the shot, not only the unit's legs.
    "killCamDistanceM": 380.0,
    "killCamHeightM": 170.0,
    "killCamFovDeg": 30.0,
}


def main():
    roster = json.load(open(ROSTER, encoding="utf-8"))
    missing = sorted({r["profession"] for r in roster["characters"]} - set(PROFESSIONS))
    kinds = sorted({r["attackKind"] for r in roster["characters"]} - set(ATTACK_KINDS))
    if missing or kinds:
        raise SystemExit("unmapped professions %s / attack kinds %s" % (missing, kinds))
    doc = {"schema": "Tread.BattlePresentation.v1", "source": "document/12_BATTLE_PRESENTATION.md",
           "timing": TIMING, "movement": MOVEMENT, "clips": CLIPS, "camera": CAMERA,
           "professions": PROFESSIONS, "attackKinds": ATTACK_KINDS,
           "defaultProfession": "近卫"}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, ensure_ascii=False, indent=1)
    print("BattlePresentation.json: %d professions, %d attack kinds" % (len(PROFESSIONS), len(ATTACK_KINDS)))


if __name__ == "__main__":
    main()
