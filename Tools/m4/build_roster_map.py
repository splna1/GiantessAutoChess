#!/usr/bin/env python3
"""M4-B (host-side): the authoritative 112-row character roster map, its content staging and its audit.

Joins what each card is made of, by characterId:
  Content/Data/Generated/Roster112.json            operator binding (N1): name, tier, price, copies, pacts, stats
  Content/Data/Generated/Traits.json               the runtime card (must agree with the binding)
  Content/Data/Source/Roster100_Models.json        legacy model keys of char_001..char_100
  Content/Data/Source/Roster112_Models.json        the 12 MMD models
  <legacy>/MyProject/Assets/Resources/Tread/characters_100.json   portrait, voice key/style, legacy cost/height/range
  <legacy>/lihui/*.png                            100 portraits (doubao-seedream, generated for this project)
  <legacy>/audio/<style>/<key>_{1,2}.wav           600 skill voice lines (doubao-seed-tts), 2 per character per style
  <legacy>/MyProject/Assets/Resources/Tread/Audio  14 SFX wav + 2 BGM mp3

<legacy> is the old Unity project F:/AI/workbuddy/GiantessAutoChess, read-only: files are copied out, never written.

Output:
  Content/Data/Generated/CharacterRosterMap.json   schema Tread.M4.CharacterRosterMap.v2 (112 rows)
  Saved/Staging/m4_content/                         portraits (512x768, all 112), avatars (the chest-up model
                                                    screenshots of Tools/m4/ue_capture_avatars.py, all 112), the voice
                                                    lines of each character's own style, SFX, BGM (mp3 -> wav through
                                                    ffmpeg), manifest.json for Tools/m4/ue_import_content.py
  Saved/Reports/M4_CharacterRosterMap_Audit.json    every check, ok only if all pass

    python Tools/m4/build_roster_map.py [--no-stage] [--require-avatars]

Avatar vs portrait (owner's definition, 2026-10-14): the AVATAR (shop / bench / roster card) is a chest-up screenshot of
the character's 3D model; the PORTRAIT is the PNG illustration and is only the click-to-open detail image, never cropped
into an avatar.  --require-avatars makes a missing avatar screenshot an audit failure (default: reported as pending).

Deterministic for unchanged inputs.  Only the voice style named by characters_100.json is staged (200 of the 600
lines); the other two styles stay in the legacy folder.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
LEGACY = Path("F:/AI/workbuddy/GiantessAutoChess")
RES = LEGACY / "MyProject/Assets/Resources/Tread"
GEN = ROOT / "Content/Data/Generated"
SRC = ROOT / "Content/Data/Source"
STAGE = ROOT / "Saved/Staging/m4_content"
REPORT = ROOT / "Saved/Reports/M4_CharacterRosterMap_Audit.json"
CONTENT = ROOT / "Content"

STYLES = {"A": "A_温柔征服", "B": "B_热血突击", "C": "C_冷酷女帝"}
# characters_100.json voice keys that the audio batch wrote under another file stem (checked by hand 2026-10-14:
# the audio batch named files after the portrait, and these five portraits differ from the speaker's name).
VOICE_STEM_ALIAS = {"Prinz": "Prinz Eugen", "Ye": "Ye Shunguang", "Zhu": "Zhu Yuan", "TDA弱音": "弱音",
                    "NTE-MintSwimsuit": "薄荷"}
# document/187: lines the owner removed (voice stem, 1-based line index as in <stem>_N.wav). The legacy audio is
# read-only, so the exclusion lives here and in Content/Data/Generated/CharacterRosterMap.json.
VOICE_LINE_BLOCKLIST = {("Enterprise", 1)}
PORTRAIT_SIZE = (512, 768)
SFX = ["building_reward", "building_stomp", "character_select", "defeat", "eliminated", "giantess_deploy",
       "main_menu", "purchase", "pve_raid", "pvp_battle", "round_start", "skill_cast", "tread_footstep", "victory"]
BGM = {"battle": "tread_battle_bgm.mp3", "menu": "tread_menu_bgm.mp3"}

PORTRAIT_DIR = "/Game/Tread/UI/Portraits"
AVATAR_DIR = "/Game/Tread/UI/Avatars"
AVATAR_SRC = ROOT / "Saved/Staging/avatars"          # written by Tools/m4/ue_capture_avatars.py (512x512 PNG per id)
MMD_STAGE = ROOT / "Saved/Staging/mmd"               # <id>/portrait.png of the 12 MMD models (E:/AI/Tread/Tread/mmd_12)
VOICE_DIR = "/Game/Tread/Audio/Voice"
SFX_DIR = "/Game/Tread/Audio/SFX"
BGM_DIR = "/Game/Tread/Audio/BGM"
HERO_MESH = "/Game/Tread/Characters/Clukay416/SK_Clukay416"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def uasset(game_path):
    """Content/... file of a /Game/... package path."""
    return CONTENT / (game_path[len("/Game/"):] + ".uasset")


def mesh_for(cid):
    n = int(cid.split("_")[1])
    if n == 1:
        return "Hero", HERO_MESH
    if n <= 100:
        return "VRM", "/Game/Tread/Characters/VRM/%s/SK_VRM_%s" % (cid, cid)
    return "MMD", "/Game/Tread/Characters/MMD/%s/SK_MMD_%s" % (cid, cid)


def voice_lines(style_dir, stem):
    out = []
    for n in (1, 2):
        wav = LEGACY / "audio" / style_dir / ("%s_%d.wav" % (stem, n))
        side = Path(str(wav) + ".json")
        text = load(side).get("text", "") if side.exists() else ""
        out.append((wav, text))
    return out


def stage_portrait(src, dst):
    """Fit the illustration into 512x768 keeping its aspect (never cropped); any slack is padded with the edge colour."""
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return
    image = Image.open(src).convert("RGB")
    w, h = image.size
    scale = min(PORTRAIT_SIZE[0] / w, PORTRAIT_SIZE[1] / h)
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    fitted = image.resize(size, Image.LANCZOS)
    if size != PORTRAIT_SIZE:
        canvas = Image.new("RGB", PORTRAIT_SIZE, image.getpixel((2, 2)))
        canvas.paste(fitted, ((PORTRAIT_SIZE[0] - size[0]) // 2, (PORTRAIT_SIZE[1] - size[1]) // 2))
        fitted = canvas
    dst.parent.mkdir(parents=True, exist_ok=True)
    fitted.save(dst)


def stage_copy(src, dst):
    if dst.exists() and dst.stat().st_size == src.stat().st_size:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


def stage_mp3(src, dst):
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ar", "44100", "-ac", "2", str(dst)],
                   check=True)


def main(argv):
    stage = "--no-stage" not in argv
    roster = load(GEN / "Roster112.json")
    cards = {c["characterId"]: c for c in load(GEN / "Traits.json")["cards"]}
    economy = load(GEN / "Economy.json")
    legacy_models = {c["characterId"]: c for c in load(SRC / "Roster100_Models.json")["characters"]}
    mmd_models = {m["characterId"]: m for m in load(SRC / "Roster112_Models.json")["models"]}
    legacy_chars = load(RES / "characters_100.json")["characters"]
    if len(legacy_chars) != 100:
        raise SystemExit("characters_100.json has %d rows" % len(legacy_chars))
    # characters_100.json is in char_001..char_100 order (the M1 map was generated from it in that order).
    legacy_by_id = {"char_%03d" % (i + 1): c for i, c in enumerate(legacy_chars)}

    rows, manifest = [], {"portraits": [], "avatars": [], "voices": [], "sfx": [], "bgm": []}
    for r in roster["characters"]:
        cid = r["characterId"]
        model_set, mesh = mesh_for(cid)
        legacy = legacy_by_id.get(cid)
        old = legacy_models.get(cid, {})
        avatar_asset = "%s/T_Avatar_%s" % (AVATAR_DIR, cid)
        portrait_asset = "%s/T_Portrait_%s" % (PORTRAIT_DIR, cid)
        row = {
            "characterId": cid,
            "originalOperatorName": r["operatorName"],
            "operatorAppellation": r["operatorAppellation"],
            "operatorChessId": r["operatorChessId"],
            "operatorEliteChessId": r["operatorEliteChessId"],
            "ueModelCharacterId": old.get("ueModelCharacterId") or mmd_models.get(cid, {}).get("archivePrefix", ""),
            "ueModelName": r["modelName"],
            "modelSet": model_set,
            "modelSource": r["modelSource"],
            "meshAsset": mesh,
            "avatarAsset": avatar_asset,
            "portraitAsset": portrait_asset,
            "corePacts": r["corePacts"],
            "adjunctPacts": r["adjunctPacts"],
            "profession": r["profession"],
            "subProfession": r["subProfession"],
            "position": r["position"],
            "attackKind": r["attackKind"],
            "dmgType": r["dmgType"],
            "skillName": r["skillName"],
            "operatorTier": r["operatorTier"],
            "price": r["price"],
            "sellPrice": r["sellPrice"],
            "poolCopies": r["poolCopies"],
            "combineCopies": r["combineCopies"],
            "stats": r["stats"],
            "eliteStats": r["eliteStats"],
            "binding": r["binding"],
            "poolRule": {"isSharedPool": True, "cloneConsumesPool": False,
                         "copiesByOperatorTier": economy["poolCopiesByTier"]},
        }
        if r["operatorName"] == "缪尔赛思":
            row["poolRule"]["specialHandling"] = ("transform-clone source (变形同构体): clones carry copySourceCharacterId "
                                                  "and never consume the shared pool")
        if legacy:
            stem = legacy["portrait"].rsplit(".", 1)[0]
            voice_stem = VOICE_STEM_ALIAS.get(stem, stem)
            style_dir = STYLES[legacy["voiceStyle"]]
            portrait_src = LEGACY / "lihui" / legacy["portrait"]
            lines = voice_lines(style_dir, voice_stem)
            voice_assets = ["%s/%s/SW_Voice_%s_%d" % (VOICE_DIR, cid, cid, n) for n in (1, 2)]
            blocked = {n - 1 for name, n in VOICE_LINE_BLOCKLIST if name == voice_stem}
            if blocked:
                lines = [x for i, x in enumerate(lines) if i not in blocked]
                voice_assets = [x for i, x in enumerate(voice_assets) if i not in blocked]
            row.update({
                "legacyName": legacy["name"], "legacyCost": legacy["cost"], "legacyHeight": legacy["height"],
                "legacyAttackRange": legacy["attackRange"], "legacyShopWeight": legacy["shopWeight"],
                "legacyOrigin": legacy["origin"], "legacyClassName": legacy["className"],
                "portraitKey": legacy["portrait"],
                "portraitSha256": sha256(portrait_src) if portrait_src.exists() else None,
                "voiceKey": legacy["voiceKey"], "voiceStyle": legacy["voiceStyle"], "voiceFileStem": voice_stem,
                "voiceAssets": voice_assets, "voiceLines": [t for _, t in lines],
            })
            manifest["portraits"].append({"source": str(portrait_src), "staged": "portraits/T_Portrait_%s.png" % cid,
                                          "asset": portrait_asset})
            for (wav, _), asset in zip(lines, voice_assets):
                manifest["voices"].append({"source": str(wav), "staged": "voice/%s/%s.wav" % (cid, asset.rsplit("/", 1)[1]),
                                           "asset": asset})
        else:
            portrait_src = MMD_STAGE / cid / "portrait.png"
            row.update({"legacyName": mmd_models.get(cid, {}).get("modelName", r["modelName"]),
                        "portraitKey": "mmd_12/%s.png" % mmd_models.get(cid, {}).get("modelName", cid),
                        "portraitSha256": sha256(portrait_src) if portrait_src.exists() else None,
                        "voiceKey": None, "voiceStyle": None,
                        "voiceAssets": [], "voiceLines": [],
                        "contentNote": "MMD model (N2): the portrait is the PNG staged from mmd_12; no voice source "
                                       "exists, the shared SFX are used"})
            manifest["portraits"].append({"source": str(portrait_src), "staged": "portraits/T_Portrait_%s.png" % cid,
                                          "asset": portrait_asset})
        manifest["avatars"].append({"source": str(AVATAR_SRC / (cid + ".png")), "staged": "avatars/T_Avatar_%s.png" % cid,
                                    "asset": avatar_asset})
        rows.append(row)

    for name in SFX:
        manifest["sfx"].append({"source": str(RES / "Audio" / (name + ".wav")), "staged": "sfx/SW_SFX_%s.wav" % name,
                                "asset": "%s/SW_SFX_%s" % (SFX_DIR, name)})
    for key, file in BGM.items():
        manifest["bgm"].append({"source": str(RES / "Audio" / file), "staged": "bgm/SW_BGM_%s.wav" % key,
                                "asset": "%s/SW_BGM_%s" % (BGM_DIR, key), "loop": True})

    out = {"schemaVersion": "Tread.M4.CharacterRosterMap.v2",
           "note": "M4 authoritative roster map (2026-10-14): operator binding from Roster112.json (N1), model, portrait "
                   "and voice keys; built by Tools/m4/build_roster_map.py, do not edit by hand.",
           "sources": {"roster112": sha256(GEN / "Roster112.json"), "traits": sha256(GEN / "Traits.json"),
                       "characters100": sha256(RES / "characters_100.json")},
           "assetRoots": {"portraits": PORTRAIT_DIR, "avatars": AVATAR_DIR, "voices": VOICE_DIR, "sfx": SFX_DIR, "bgm": BGM_DIR},
           "sfx": {e["asset"].rsplit("SW_SFX_", 1)[1]: e["asset"] for e in manifest["sfx"]},
           "bgm": {e["asset"].rsplit("SW_BGM_", 1)[1]: e["asset"] for e in manifest["bgm"]},
           "characters": rows}
    dump(GEN / "CharacterRosterMap.json", out)

    if stage:
        for e in manifest["portraits"]:
            stage_portrait(Path(e["source"]), STAGE / e["staged"])
        for e in manifest["avatars"]:
            if Path(e["source"]).is_file():
                stage_copy(Path(e["source"]), STAGE / e["staged"])
        for e in manifest["voices"] + manifest["sfx"]:
            stage_copy(Path(e["source"]), STAGE / e["staged"])
        for e in manifest["bgm"]:
            stage_mp3(Path(e["source"]), STAGE / e["staged"])
        dump(STAGE / "manifest.json", manifest)

    report = audit(out, cards, economy, manifest, "--require-avatars" in argv)
    dump(REPORT, report)
    print("ROSTER rows=%d ok=%s failed=%s" % (len(rows), report["ok"], [k for k, v in report["checks"].items() if not v["ok"]]))
    return 0 if report["ok"] else 1


def check(ok, detail=None):
    return {"ok": bool(ok), "detail": detail if detail else []}


def audit(out, cards, economy, manifest, require_avatars=False):
    rows = out["characters"]
    ids = [r["characterId"] for r in rows]
    ops = [r["operatorChessId"] for r in rows]
    names = [r["originalOperatorName"] for r in rows]
    tiers = economy["poolCopiesByTier"]
    overrides = economy.get("poolCopiesOverrides", {})
    legacy = [r for r in rows if r["modelSet"] != "MMD"]

    mismatch = []
    for r in rows:
        c = cards.get(r["characterId"])
        if c is None:
            mismatch.append("%s: no card" % r["characterId"])
            continue
        for mine, theirs in (("originalOperatorName", "referenceOperatorName"), ("operatorTier", "operatorTier"),
                             ("price", "price"), ("poolCopies", "poolCopies"), ("corePacts", "corePacts"),
                             ("adjunctPacts", "adjunctPacts"), ("profession", "profession")):
            if r[mine] != c[theirs]:
                mismatch.append("%s.%s %r != card %r" % (r["characterId"], mine, r[mine], c[theirs]))
    pool_bad = ["%s %s %d" % (r["characterId"], r["operatorTier"], r["poolCopies"]) for r in rows
                if r["poolCopies"] != overrides.get(r["operatorChessId"], tiers[r["operatorTier"]])]
    missing_mesh = [r["meshAsset"] for r in rows if not uasset(r["meshAsset"]).exists()]
    missing_portrait_src = [r["characterId"] for r in legacy
                            if not (LEGACY / "lihui" / (r["portraitKey"] or "")).is_file()]
    missing_voice_src = [e["source"] for e in manifest["voices"] if not Path(e["source"]).is_file()]
    missing_audio_src = [e["source"] for e in manifest["sfx"] + manifest["bgm"] if not Path(e["source"]).is_file()]
    empty_lines = [r["characterId"] for r in legacy if not all(r["voiceLines"])]
    assets = [a for r in rows for a in [r["portraitAsset"], r["avatarAsset"]] + r["voiceAssets"]]
    missing_portrait_stage = [e["asset"] for e in manifest["portraits"] if not Path(e["source"]).is_file()]
    missing_avatar_src = [e["asset"] for e in manifest["avatars"] if not Path(e["source"]).is_file()]
    bad_avatar_names = [r["characterId"] for r in rows
                        if r["avatarAsset"] != "%s/T_Avatar_%s" % (AVATAR_DIR, r["characterId"])
                        or r["portraitAsset"] != "%s/T_Portrait_%s" % (PORTRAIT_DIR, r["characterId"])]
    muelsyse = [r for r in rows if r["originalOperatorName"] == "缪尔赛思"]
    checks = {
        "rows_112": check(len(rows) == 112, len(rows)),
        "unique_character_ids": check(len(set(ids)) == len(ids)),
        "unique_operators": check(len(set(ops)) == len(ops) and len(set(names)) == len(names)),
        "tier_I_to_VI": check(all(r["operatorTier"] in tiers for r in rows)),
        "card_agrees_with_binding": check(not mismatch, mismatch),
        "pool_copies_by_tier": check(not pool_bad, pool_bad),
        "clone_never_consumes_pool": check(all(r["poolRule"]["cloneConsumesPool"] is False for r in rows)),
        "mesh_assets_exist": check(not missing_mesh, missing_mesh),
        "legacy_rows_have_portrait_source": check(len(legacy) == 100 and not missing_portrait_src, missing_portrait_src),
        "legacy_rows_have_two_voice_lines": check(not missing_voice_src and not empty_lines, missing_voice_src + empty_lines),
        "every_row_has_avatar_and_portrait_asset": check(not bad_avatar_names and len(manifest["portraits"]) == 112
                                                         and len(manifest["avatars"]) == 112, bad_avatar_names),
        "portrait_sources_exist_112": check(not missing_portrait_stage, missing_portrait_stage),
        "avatar_screenshots_exist_112": check(not require_avatars or not missing_avatar_src, missing_avatar_src),
        "sfx_bgm_sources": check(not missing_audio_src, missing_audio_src),
        "asset_keys_unique": check(len(set(assets)) == len(assets)),
        "muelsyse_model_plays_muelsyse": check(len(muelsyse) == 1 and muelsyse[0]["ueModelName"] == "缪尔赛思"
                                              and muelsyse[0]["ueModelCharacterId"] == "modernia",
                                              [{k: m[k] for k in ("characterId", "ueModelName", "ueModelCharacterId")}
                                               for m in muelsyse]),
    }
    reuse = {}
    for r in rows:
        reuse.setdefault(r["meshAsset"], []).append(r["characterId"])
    return {"schema": "Tread.M4.CharacterRosterMap.Audit.v2", "ok": all(c["ok"] for c in checks.values()),
            "rowCount": len(rows), "legacyRows": len(legacy), "mmdRows": len(rows) - len(legacy),
            "avatarScreenshotsPending": len(missing_avatar_src), "requireAvatars": require_avatars,
            "checks": checks, "voiceStemAliases": VOICE_STEM_ALIAS,
            "modelReuse": {k: v for k, v in reuse.items() if len(v) > 1},
            "rows": [{k: r[k] for k in ("characterId", "originalOperatorName", "ueModelName", "modelSet",
                                        "operatorTier", "price", "poolCopies", "corePacts", "adjunctPacts",
                                        "profession", "avatarAsset", "portraitAsset", "voiceAssets")} for r in rows]}


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
