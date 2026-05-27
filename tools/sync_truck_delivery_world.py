"""Sync truck_delivery.wbt stock layout from triger_threshold.wbt."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORLDS = ROOT / "worlds"


def main():
    threshold = (WORLDS / "triger_threshold.wbt").read_text(encoding="utf-8")
    truck = (WORLDS / "truck_delivery.wbt").read_text(encoding="utf-8")

    viewpoint_match = re.search(r"Viewpoint \{.*?\n\}", truck, re.S)
    viewpoint_block = viewpoint_match.group(0) if viewpoint_match else None

    out = threshold.replace('title "Threshold Testing"', 'title "Truck Delivery"')
    if viewpoint_block:
        out = re.sub(r"Viewpoint \{.*?\n\}", viewpoint_block, out, count=1, flags=re.S)

    (WORLDS / "truck_delivery.wbt").write_text(out, encoding="utf-8")
    print(f"Updated {WORLDS / 'truck_delivery.wbt'} ({len(out.splitlines())} lines)")


if __name__ == "__main__":
    main()
