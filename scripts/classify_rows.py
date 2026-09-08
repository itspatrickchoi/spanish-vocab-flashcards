"""
Step 2a: Deterministic classification of every extracted row.

Buckets every row into exactly one category so the row count always
reconciles to 990 (the accountability check the plan calls for). Handles
the known special structures found during exploration:
  - rows 599 (parent) + 600-610 (hidden continuation notes on "descanchado")
  - row 595 (isolated hidden dead Obsidian image reference)
  - rows 900-903 (a 4-sentence rewrite/practice drill -> one merged entry)
  - row 761 (context tag) + 762-764 (hidden, unrelated personal journal text)
  - row 955 (one cell bundling ~6 phrases via newlines -> split)

Output: data/classified_rows.json containing
  - "draftable_items": items that need Front/Back/Notes content drafted
    (each carries its source row(s) and raw source text)
  - "excluded_rows": every row classified as noise/duplicate/empty, with a
    reason, for the exclusion report
  - "counts": reconciliation counts (must sum to total data rows)
"""

import json
import re
from pathlib import Path

IN = Path(__file__).parent.parent / "data" / "extracted_rows.json"
OUT = Path(__file__).parent.parent / "data" / "classified_rows.json"

DATE_RE = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{2,4}$")
TAG_LINE_RE = re.compile(r"^[^:#]+:\s*#\w+$")

# Rows handled as one-off special structures (see docstring).
DESCANCHADO_PARENT_ROW = 599
DESCANCHADO_CONTINUATION_ROWS = list(range(600, 611))
ISOLATED_DEAD_IMAGE_ROW = 595
DRILL_ROWS = [900, 901, 902, 903]
TAG_ROW = 761
OFFTOPIC_ROWS = [762, 763, 764]
MULTI_ITEM_ROW = 955


def has_dead_image(text):
    return text is not None and "![[" in text


def is_placeholder(text):
    return text is not None and text.strip() in {"-", "--"}


def is_todo(text):
    return text is not None and text.strip().startswith("- [ ]")


def is_tag_line(text):
    return text is not None and bool(TAG_LINE_RE.match(text.strip()))


def is_date(text):
    return text is not None and bool(DATE_RE.match(text.strip()))


def main():
    rows = json.load(open(IN, encoding="utf-8"))
    by_row = {r["row"]: r for r in rows}

    draftable_items = []
    excluded_rows = []
    handled_rows = set()

    def exclude(row_nums, reason, category):
        for rn in row_nums:
            handled_rows.add(rn)
        excluded_rows.append(
            {"rows": row_nums, "category": category, "reason": reason,
             "raw": [by_row[rn] for rn in row_nums]}
        )

    def add_item(item_id, row_nums, category, source_text):
        for rn in row_nums:
            handled_rows.add(rn)
        draftable_items.append(
            {
                "id": item_id,
                "rows": row_nums,
                "category": category,
                "source_text": source_text,
            }
        )

    # --- Special structural cases handled first ---------------------------

    exclude([ISOLATED_DEAD_IMAGE_ROW], "dead Obsidian image embed, no image data in file", "noise_dead_image")

    parent = by_row[DESCANCHADO_PARENT_ROW]
    cont_rows = [DESCANCHADO_PARENT_ROW] + DESCANCHADO_CONTINUATION_ROWS
    cont_text_parts = [f"[row {DESCANCHADO_PARENT_ROW}] {parent['back_raw']}"]
    for rn in DESCANCHADO_CONTINUATION_ROWS:
        r = by_row[rn]
        text = r["front_raw"] or r["back_raw"] or r["overflow_raw"]
        cont_text_parts.append(f"[row {rn}] {text}")
    add_item("descanchado", cont_rows, "continuation", "\n".join(cont_text_parts))

    drill_texts = [f"[row {rn}] {by_row[rn]['back_raw']}" for rn in DRILL_ROWS]
    add_item("puede_verse_drill", DRILL_ROWS, "continuation", "\n".join(drill_texts))

    exclude([TAG_ROW], "context tag, not a vocab entry", "noise_todo_or_tag")
    exclude(OFFTOPIC_ROWS, "personal/relationship journal text, not Spanish vocab", "noise_offtopic")

    multi_row = by_row[MULTI_ITEM_ROW]
    sub_items = [s.strip() for s in multi_row["back_raw"].split("\n") if s.strip()]
    for idx, sub in enumerate(sub_items):
        add_item(f"row955_{idx}", [MULTI_ITEM_ROW], "multi_item_cell", sub)

    # --- Generic pass over all remaining rows ------------------------------

    seen_back_normalized = {}  # normalized back text -> canonical item id/row

    for r in rows:
        rn = r["row"]
        if rn in handled_rows:
            continue

        if r["is_empty"]:
            exclude([rn], "blank row", "empty")
            continue

        a, b, c = r["front_raw"], r["back_raw"], r["overflow_raw"]
        combined_for_checks = " ".join(x for x in (a, b, c) if x)

        if has_dead_image(combined_for_checks):
            exclude([rn], "dead Obsidian image embed, no image data in file", "noise_dead_image")
            continue

        if is_date(a) or is_date(b):
            exclude([rn], "date-stamp used as an informal section separator", "noise_date")
            continue

        if is_placeholder(a) and is_placeholder(b):
            exclude([rn], "placeholder value ('-' / '--'), not a real entry", "noise_placeholder")
            continue
        if is_placeholder(b) and a is None:
            exclude([rn], "placeholder value ('-' / '--'), not a real entry", "noise_placeholder")
            continue

        if is_todo(a) or is_todo(b):
            exclude([rn], "to-do note embedded in the data, not vocab", "noise_todo_or_tag")
            continue

        if is_tag_line(a) or is_tag_line(b):
            exclude([rn], "context/source tag line, not vocab", "noise_todo_or_tag")
            continue

        # Pure overflow-only rows with no A/B content that weren't part of a
        # known continuation block: attach to the most recent draftable item
        # if one exists, else flag as an orphan continuation fragment.
        if a is None and b is None and c is not None:
            if draftable_items:
                draftable_items[-1]["source_text"] += f"\n[row {rn}, orphan overflow] {c}"
                draftable_items[-1]["rows"].append(rn)
                handled_rows.add(rn)
                continue
            exclude([rn], "overflow-only fragment with no preceding entry to attach to", "noise_orphan_fragment")
            continue

        # Duplicate detection on normalized back text.
        norm = (b or a or "").strip().lower()
        if norm and norm in seen_back_normalized and not is_placeholder(norm):
            exclude([rn], f"duplicate of row {seen_back_normalized[norm]}", "duplicate")
            continue
        if norm:
            seen_back_normalized[norm] = rn

        if a and b:
            add_item(f"row{rn}", [rn], "vocab_pair", f"Front(EN)={a} | Back(ES)={b}")
        elif b:
            add_item(f"row{rn}", [rn], "vocab_spanish_only", b)
        elif a:
            add_item(f"row{rn}", [rn], "vocab_spanish_only", a)
        else:
            exclude([rn], "no usable content", "noise_unclassified")

    total = len(rows)
    n_draft = len(draftable_items)
    # A physical row can be claimed by more than one draftable item (e.g. row
    # 955 splits into several sub-items) or appended to a preceding item
    # (orphan overflow rows), so the accountability check is: every physical
    # row must appear in exactly one of {handled_rows-that-are-draftable,
    # excluded_rows} -- i.e. len(handled_rows) must equal total, since
    # handled_rows is a set (no double counting of the same physical row).
    all_row_nums = {r["row"] for r in rows}
    unaccounted = all_row_nums - handled_rows
    n_excl_rows = sum(len(e["rows"]) for e in excluded_rows)

    counts = {
        "total_data_rows": total,
        "draftable_items": n_draft,
        "physical_rows_accounted_for": len(handled_rows),
        "rows_excluded": n_excl_rows,
        "unaccounted_rows": sorted(unaccounted),
        "reconciles": len(handled_rows) == total and not unaccounted,
    }

    OUT.write_text(
        json.dumps(
            {"draftable_items": draftable_items, "excluded_rows": excluded_rows, "counts": counts},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(json.dumps(counts, indent=2))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
