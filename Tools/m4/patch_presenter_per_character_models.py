#!/usr/bin/env python3
"""Patch TreadM3BoardPresenter so each unit renders its own model instead of always the M1 hero.

Before: every unit used BodyMesh (Clukay416) with BodyMaterials copied onto it.
After:  char_101..112 load /Game/Tread/Characters/MMD/<id>/SK_MMD_<id>; everything else (including
        char_100, which is the 100th VRM and not an MMD model) falls back to BodyMesh.

Three defects in the first cut of this patch, all fixed here:
  * BodyMaterials (the hero's 23 slots) were copied onto every mesh. An MMD mesh has 24..43 slots
    carrying its own per-slot toon instances from ue_mmd_materials.py, so the copy smeared the
    hero's textures over the MMD character. Materials are now applied only to the hero mesh.
  * CharacterId.StartsWith("char_1") also matched char_100, a legacy VRM, and strayed into a
    pointless LoadObject for a mesh that does not exist. char_100 is now excluded explicitly.
  * The header member was a bare TObjectPtr plus a bare TMap, both GC-invisible. The cache is now
    a single UPROPERTY TMap, so one annotation covers the caching and the reference.

Convergent: every region is rewritten to its target text whenever it still differs, so replaying
this from a pristine checkout, from the first cut's half-patched state, or from the finished file
all converge on the same bytes. Re-running on a finished file changes nothing.

    python Tools/m4/patch_presenter_per_character_models.py
"""
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / "Source/Tread/TreadM3BoardPresenter.h"
CPP = ROOT / "Source/Tread/TreadM3BoardPresenter.cpp"
BACKUP = ROOT / "Saved/Staging/m4_backup/src_n2"

# --- header ------------------------------------------------------------------------------------
HEADER_MEMBER_ANCHOR = "\tUPROPERTY() TObjectPtr<USkeletalMesh> BodyMesh;\n"
HEADER_MEMBER_ADDED = (
    "\tUPROPERTY() TObjectPtr<USkeletalMesh> BodyMesh;\n"
    "\t/** CharacterId -> mesh; a character without its own model resolves to BodyMesh (Clukay416). */\n"
    "\tUPROPERTY() TMap<FString, TObjectPtr<USkeletalMesh>> CharacterMeshCache;\n"
)
HEADER_DECL_ANCHOR = "\tvoid Sync();\n"
HEADER_DECL_ADDED = (
    "\tvoid Sync();\n"
    "\tUSkeletalMesh* LoadCharacterMesh(const FString& CharacterId);\n"
)
# The first cut's members: stripped from wherever they are found so a half-patched header converges
# on the annotated form instead of keeping a duplicate, GC-invisible CharacterMeshCache behind.
LEGACY_HEADER_PATTERNS = (
    re.compile(r"^\tTObjectPtr<USkeletalMesh> FallbackBody;[^\n]*\n", re.MULTILINE),
    re.compile(r"^\tTMap<FString, TObjectPtr<USkeletalMesh>> CharacterMeshCache;[^\n]*\n", re.MULTILINE),
)

# --- cpp ---------------------------------------------------------------------------------------
CPP_IMPL = '''
USkeletalMesh* ATreadM3BoardPresenter::LoadCharacterMesh(const FString& CharacterId)
{
\tif (TObjectPtr<USkeletalMesh>* Cached = CharacterMeshCache.Find(CharacterId))
\t{
\t\treturn *Cached;
\t}
\t// char_101..112 have their own imported MMD mesh; every other character (and any import that
\t// failed) falls back to the M1 hero, BodyMesh, which FindTemplates() resolved from the level.
\tUSkeletalMesh* Mesh = BodyMesh;
\tif (CharacterId.StartsWith(TEXT("char_1")) && CharacterId != TEXT("char_100"))
\t{
\t\tconst FString MeshPath = FString::Printf(TEXT("/Game/Tread/Characters/MMD/%s/SK_MMD_%s.SK_MMD_%s"),
\t\t\t*CharacterId, *CharacterId, *CharacterId);
\t\tif (USkeletalMesh* Loaded = LoadObject<USkeletalMesh>(nullptr, *MeshPath))
\t\t{
\t\t\tMesh = Loaded;
\t\t}
\t}
\tCharacterMeshCache.Add(CharacterId, Mesh);
\treturn Mesh;
}

'''

# The body/face components are replaced as one region, bounded by the component lines above and
# below them: a bare "if (FaceMesh)" occurs twice in the file, so matching it alone is ambiguous.
SPAWN_START = "\tV.Body = NewObject<USkeletalMeshComponent>(this);\n"
SPAWN_END = "\tV.Ring = NewObject<UStaticMeshComponent>(this);\n"
SPAWN_LEGACY_MARKERS = ("bHasFaceMesh", "SetSkeletalMeshAsset(BodyMesh)")
SPAWN_BLOCK = '''\tV.Body = NewObject<USkeletalMeshComponent>(this);
\tUSkeletalMesh* CharMesh = LoadCharacterMesh(Unit.CharacterId);
\tV.Body->SetSkeletalMeshAsset(CharMesh);
\t// BodyMaterials are the M1 hero's own slots, and the hero is a body mesh plus a face mesh that
\t// shares its pose. An MMD mesh is single-mesh and carries its own per-slot toon instances from
\t// the import step (24..43 slots against the hero's 23), so it must keep them.
\tconst bool bHeroMesh = (CharMesh == BodyMesh.Get());
\tif (bHeroMesh)
\t{
\t\tfor (int32 Slot = 0; Slot < BodyMaterials.Num(); ++Slot) V.Body->SetMaterial(Slot, BodyMaterials[Slot]);
\t}
\tV.Body->SetCollisionEnabled(ECollisionEnabled::NoCollision);
\tV.Body->SetupAttachment(RootComponent);
\tV.Body->RegisterComponent();
\tif (IdleAnim) V.Body->PlayAnimation(IdleAnim, true);
\t// Desynchronise the idle loops so a full board does not breathe in lockstep.
\tV.Body->SetPosition(FMath::Fmod(static_cast<float>(GetTypeHash(Id) % 997) * 0.37f, IdleAnim ? IdleAnim->GetPlayLength() : 1.0f));
\t// The M1 hero is a body mesh plus a face mesh sharing its pose; MMD models are single-mesh.
\tif (FaceMesh && bHeroMesh)
\t{
\t\tV.Face = NewObject<USkeletalMeshComponent>(this);
\t\tV.Face->SetSkeletalMeshAsset(FaceMesh);
\t\tfor (int32 Slot = 0; Slot < FaceMaterials.Num(); ++Slot) V.Face->SetMaterial(Slot, FaceMaterials[Slot]);
\t\tV.Face->SetCollisionEnabled(ECollisionEnabled::NoCollision);
\t\tV.Face->SetupAttachment(V.Body);
\t\tV.Face->RegisterComponent();
\t\tV.Face->SetLeaderPoseComponent(V.Body);
\t\tOwned.Add(V.Face);
\t}
'''

SPAWN_DEF = "ATreadM3BoardPresenter::FUnitVisual& ATreadM3BoardPresenter::Spawn("
HELPER_MARKER = "\nUSkeletalMesh* ATreadM3BoardPresenter::LoadCharacterMesh"


def patch_header():
    src = original = HEADER.read_text(encoding="utf-8")
    for pattern in LEGACY_HEADER_PATTERNS:
        src = pattern.sub("", src, count=1)
    # Guards test for the target text itself, not for a name the first cut also wrote.
    if "CharacterMeshCache" not in src:
        if HEADER_MEMBER_ANCHOR not in src:
            raise SystemExit("header anchor missing: BodyMesh member not found")
        src = src.replace(HEADER_MEMBER_ANCHOR, HEADER_MEMBER_ADDED, 1)
    if "LoadCharacterMesh" not in src:
        if HEADER_DECL_ANCHOR not in src:
            raise SystemExit("header anchor missing: Sync() declaration not found")
        src = src.replace(HEADER_DECL_ANCHOR, HEADER_DECL_ADDED, 1)
    if src == original:
        print("  header: already applied")
        return
    HEADER.write_text(src, encoding="utf-8")
    print("  header: wrote CharacterMeshCache member + LoadCharacterMesh declaration")


def patch_cpp():
    src = original = CPP.read_text(encoding="utf-8")
    # Helper: rewrite the whole function if any version of it is present, else insert it.
    if HELPER_MARKER in src:
        start = src.index(HELPER_MARKER)
        src = src[:start] + CPP_IMPL + src[src.index(SPAWN_DEF, start):]
    else:
        if SPAWN_DEF not in src:
            raise SystemExit("cpp anchor missing: Spawn() definition not found")
        src = src.replace(SPAWN_DEF, CPP_IMPL + SPAWN_DEF, 1)
    # Body/face block: rewrite only while the first cut's shape is still there.
    if any(marker in src for marker in SPAWN_LEGACY_MARKERS):
        start, end = src.find(SPAWN_START), src.find(SPAWN_END)
        if start < 0 or end < start:
            raise SystemExit("cpp anchor missing: Spawn() body/ring components not found in order")
        src = src[:start] + SPAWN_BLOCK + src[end:]
    if src == original:
        print("  cpp: already applied")
        return
    CPP.write_text(src, encoding="utf-8")
    print("  cpp: wrote LoadCharacterMesh + the Spawn mesh/material/face block")


def main():
    print("=== Patching TreadM3BoardPresenter for per-character models ===\n")
    for path in (HEADER, CPP):
        if not path.exists():
            print("ERROR: %s not found" % path)
            return 1
    # Snapshot only once: a later replay would otherwise overwrite a pristine copy with a patched one.
    BACKUP.mkdir(parents=True, exist_ok=True)
    for path in (HEADER, CPP):
        target = BACKUP / path.name
        if target.exists():
            print("  backup kept: %s" % target)
        else:
            shutil.copy2(path, target)
            print("  backed up: %s" % target)
    patch_header()
    patch_cpp()
    print("\nDone. Rebuild with UnrealBuildTool, then check tier VI units in M3_Paris_Match PIE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
