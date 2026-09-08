"""
Step 6: Build the final Anki deck (.apkg) from the approved card set.

Note type: Front / Back / Notes / Reversible (4th field is a plain marker,
"1" or empty -- not shown to the user, just drives card generation).

Two card templates on one note type:
  - Card 1 (always generated): Front -> Back+Notes.
  - Card 2 (Back -> Front+Notes): its question template is wrapped in
    {{#Reversible}}...{{/Reversible}}. Anki (and genanki, which replicates
    Anki's own note-to-card logic) skips generating a card whose rendered
    question is empty -- so notes with Reversible="" produce only Card 1,
    and reversible notes produce both, with no extra logic needed on our
    side. This is the smart-split rule from the plan, implemented the
    standard Anki way instead of via tags (tags aren't visible to templates).

Notes carry tags for filtering in Anki: reversible/recognition-only, the
source category, needs-review (if flagged), and a rough date::YYYY-MM-DD
tag derived from the nearest preceding date-stamp row in the source sheet.
"""

import json
import re
from pathlib import Path

import genanki

ROOT = Path(__file__).parent.parent
APPROVED = json.load(open(ROOT / "data" / "approved_drafts.json", encoding="utf-8"))
CLASSIFIED = json.load(open(ROOT / "data" / "classified_rows.json", encoding="utf-8"))
OUT = ROOT / "data" / "spanish_vocab.apkg"

MODEL_ID = 1607392319
DECK_ID = 1607392320

DATE_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{2,4})$")


def parse_date_tag(text):
    m = DATE_RE.match(text.strip())
    if not m:
        return None
    day, month, year = m.groups()
    year = int(year)
    if year < 100:
        year += 2000
    return f"date::{year:04d}-{int(month):02d}-{int(day):02d}"


def build_date_lookup():
    """Map each source row number -> the tag for the nearest preceding
    date-stamp row, so cards can be tagged by roughly when they were logged."""
    date_rows = []
    for e in CLASSIFIED["excluded_rows"]:
        if e["category"] != "noise_date":
            continue
        raw0 = e["raw"][0]
        text = raw0.get("back_raw") or raw0.get("front_raw") or ""
        tag = parse_date_tag(text)
        if tag:
            date_rows.append((min(e["rows"]), tag))
    date_rows.sort()
    return date_rows


def tag_for_row(row, date_rows):
    current = None
    for r, tag in date_rows:
        if r <= row:
            current = tag
        else:
            break
    return current


MODEL = genanki.Model(
    MODEL_ID,
    "Spanish Vocab (Front/Back/Notes)",
    fields=[
        {"name": "Front"},
        {"name": "Back"},
        {"name": "Notes"},
        {"name": "Reversible"},
    ],
    templates=[
        {
            "name": "Recall (Spanish -> meaning)",
            "qfmt": "<div class=\"front\">{{Front}}</div>",
            "afmt": (
                "{{FrontSide}}<hr id=\"answer\">"
                "<div class=\"back\">{{Back}}</div>"
                "{{#Notes}}<div class=\"notes\">{{Notes}}</div>{{/Notes}}"
            ),
        },
        {
            "name": "Production (meaning -> Spanish)",
            "qfmt": "{{#Reversible}}<div class=\"front\">{{Back}}</div>{{/Reversible}}",
            "afmt": (
                "{{FrontSide}}<hr id=\"answer\">"
                "<div class=\"back\">{{Front}}</div>"
                "{{#Notes}}<div class=\"notes\">{{Notes}}</div>{{/Notes}}"
            ),
        },
    ],
    css=(
        ".card { font-family: Arial, sans-serif; font-size: 20px; text-align: center; color: #1a1a1a; background-color: #fafafa; }"
        ".back { margin-top: 10px; }"
        ".notes { margin-top: 14px; font-size: 15px; color: #555; }"
    ),
)


def main():
    date_rows = build_date_lookup()
    deck = genanki.Deck(DECK_ID, "Spanish Vocabulary")

    n_reversible = 0
    n_flagged = 0
    for d in APPROVED:
        reversible = bool(d.get("reversible"))
        if reversible:
            n_reversible += 1

        tags = [
            "reversible" if reversible else "recognition-only",
            d["category"],
        ]
        if d.get("flag_reason"):
            tags.append("needs-review")
            n_flagged += 1
        date_tag = tag_for_row(min(d["rows"]), date_rows)
        if date_tag:
            tags.append(date_tag)

        note = genanki.Note(
            model=MODEL,
            fields=[d["front"], d["back"], d["notes"], "1" if reversible else ""],
            tags=tags,
        )
        deck.add_note(note)

    genanki.Package(deck).write_to_file(OUT)

    print(f"Notes added: {len(APPROVED)}")
    print(f"Reversible notes (2 cards each): {n_reversible}")
    print(f"Recognition-only notes (1 card each): {len(APPROVED) - n_reversible}")
    print(f"Expected total cards: {n_reversible * 2 + (len(APPROVED) - n_reversible)}")
    print(f"Flagged (needs-review tag): {n_flagged}")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
