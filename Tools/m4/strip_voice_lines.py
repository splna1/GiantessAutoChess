"""document/187: remove the owner-blocked placeholder voice lines from CharacterRosterMap.json.

The legacy Unity audio is read-only, so the project-side roster is the source of truth for which lines ship.
Keeps voiceAssets and voiceLines aligned (same index removed from both).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "Content/Data/Generated/CharacterRosterMap.json"
# characterId -> 1-based line indices (1 = <stem>_1.wav)
BLOCK = {"char_053": {1}}


def main():
    doc = json.loads(TARGET.read_text(encoding="utf-8-sig"))
    removed = 0
    for row in doc["characters"]:
        indices = BLOCK.get(row["characterId"])
        if not indices:
            continue
        for line_no in sorted(indices, reverse=True):
            index = line_no - 1
            if index < len(row.get("voiceAssets", [])):
                row["voiceAssets"].pop(index)
                removed += 1
            if index < len(row.get("voiceLines", [])):
                row["voiceLines"].pop(index)
    TARGET.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print("stripped %d voice assets from %s" % (removed, TARGET))


if __name__ == "__main__":
    main()
