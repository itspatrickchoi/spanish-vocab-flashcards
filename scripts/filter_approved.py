"""
Step 3b: Apply the user's review decision.

The user reviewed the 502-card draft and said: drop everything flagged
confidence == "low", keep the rest as-is. This produces the final approved
card set used to build the deck, plus a log of what was dropped (so it still
shows up in the Excluded sheet rather than silently vanishing).
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
DRAFTS = json.load(open(ROOT / "data" / "merged_drafts.json", encoding="utf-8"))

approved = [d for d in DRAFTS if d.get("confidence") != "low"]
dropped = [d for d in DRAFTS if d.get("confidence") == "low"]

json.dump(approved, open(ROOT / "data" / "approved_drafts.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump(dropped, open(ROOT / "data" / "dropped_low_confidence.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)

print(f"Total drafts: {len(DRAFTS)}")
print(f"Approved (kept): {len(approved)}")
print(f"Dropped (low confidence, per user request): {len(dropped)}")
