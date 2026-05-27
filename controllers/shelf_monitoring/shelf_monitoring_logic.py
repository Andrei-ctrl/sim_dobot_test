"""Front-shelf item counting by slot proximity (Webots-independent)."""

import json
import math
import os
import sys

sorter_logic = None


def _load_sorter_logic():
    global sorter_logic
    if sorter_logic is not None:
        return sorter_logic
    shelf_dir = os.path.dirname(os.path.abspath(__file__))
    controllers_dir = os.path.dirname(shelf_dir)
    sorter_dir = os.path.join(controllers_dir, "youbot_sorter_demo")
    for path in (controllers_dir, sorter_dir):
        if path not in sys.path:
            sys.path.insert(0, path)
    try:
        import youbot_sorter_logic as loaded

        sorter_logic = loaded
    except ImportError:
        sorter_logic = False
    return sorter_logic

SHELF_COUNTS_FILENAME = "shelf_counts.json"

PRODUCT_NODE_TYPES = {
    "BeerBottle": "BEER_BOTTLE",
    "ChipsPack": "CHIPS",
    "CheeseWedge": "CHEESE",
    "MilkCarton": "MILK",
}

PRODUCT_TYPE_NAMES = frozenset(PRODUCT_NODE_TYPES.keys())

SLOT_XY_RADIUS = 0.14
SLOT_Z_RADIUS = 0.22

SHELF_BANK_X_MIN = -12.2
SHELF_BANK_X_MAX = -10.8
SHELF_BANK_Y_MIN = 2.0
SHELF_BANK_Y_MAX = 8.8
SHELF_BANK_Z_MIN = 0.04
SHELF_BANK_Z_MAX = 1.05

UNITS_PER_ITEM = 2


def data_dir(project_root):
    return os.path.join(project_root, "data")


def shelf_counts_path(project_root):
    return os.path.join(data_dir(project_root), SHELF_COUNTS_FILENAME)


def product_ids():
    logic = _load_sorter_logic()
    if logic is not None and logic is not False:
        return list(logic.PRODUCT_SHELF_ALL_SLOTS.keys())
    return list(PRODUCT_NODE_TYPES.values())


def slots_for_product(product_id):
    logic = _load_sorter_logic()
    if logic is None or logic is False:
        return []
    return logic.PRODUCT_SHELF_ALL_SLOTS.get(product_id, [])


def in_shelf_bank(pos):
    x, y, z = pos[0], pos[1], pos[2]
    return (
        SHELF_BANK_X_MIN <= x <= SHELF_BANK_X_MAX
        and SHELF_BANK_Y_MIN <= y <= SHELF_BANK_Y_MAX
        and SHELF_BANK_Z_MIN <= z <= SHELF_BANK_Z_MAX
    )


def slot_match(pos, slot):
    return (
        math.hypot(pos[0] - slot[0], pos[1] - slot[1]) <= SLOT_XY_RADIUS
        and abs(pos[2] - slot[2]) <= SLOT_Z_RADIUS
    )


def product_id_for_node_type(type_name):
    return PRODUCT_NODE_TYPES.get(type_name or "")


def product_positions_on_shelf(node_entries, product_id):
    """World XYZ for shelf items matching product_id."""
    return [
        list(entry[2])
        for entry in node_entries
        if product_id_for_node_type(entry[1]) == product_id
    ]


def find_placement_slots(node_entries, product_id, count=3):
    """
    Choose hardcoded shelf row/slots for a sort box (3 items).
    Prefers the first empty row: top, then middle, then bottom.
    """
    logic = _load_sorter_logic()
    if logic is None or logic is False:
        return None, []
    positions = product_positions_on_shelf(node_entries, product_id)
    return logic.find_empty_row_placement(positions, product_id, count=count)


def count_items_for_product(node_entries, product_id):
    """node_entries: list of (index, type_name, [x,y,z])"""
    slots = slots_for_product(product_id)
    candidates = [
        entry
        for entry in node_entries
        if product_id_for_node_type(entry[1]) == product_id
    ]
    if not slots:
        return len(candidates)

    filled = 0
    used = set()
    for slot in slots:
        for index, _type_name, pos in candidates:
            if index in used:
                continue
            if slot_match(pos, slot):
                filled += 1
                used.add(index)
                break
    if filled == 0 and candidates:
        in_bank = [entry for entry in candidates if in_shelf_bank(entry[2])]
        if in_bank:
            return min(len(in_bank), len(slots))
    return filled


def count_all_products(node_entries):
    return {
        product_id: count_items_for_product(node_entries, product_id)
        for product_id in product_ids()
    }


def front_units(item_count, units_per_item=UNITS_PER_ITEM):
    return int(item_count) * units_per_item


def merge_peak_counts(peak, current):
    """Per-product maximum seen during the baseline settle window."""
    merged = {product_id: int(peak.get(product_id, 0)) for product_id in product_ids()}
    for product_id, count in current.items():
        merged[product_id] = max(merged.get(product_id, 0), int(count))
    return merged


def build_counts_payload(
    sim_time,
    counts,
    *,
    baseline=None,
    baseline_locked=False,
    source="shelf_monitoring",
    run_id=None,
):
    payload = {
        "sim_time": sim_time,
        "source": source,
        "counts": counts,
        "front_units": {
            product_id: front_units(count)
            for product_id, count in counts.items()
        },
        "baseline_locked": bool(baseline_locked),
    }
    if run_id is not None:
        payload["run_id"] = int(run_id)
    if baseline is not None:
        payload["baseline_counts"] = baseline
    return payload


def _payload_for_run(payload, run_id=None):
    if not payload:
        return None
    if run_id is None:
        return payload
    file_run = payload.get("run_id")
    if file_run is None:
        return None
    return payload if int(file_run) == int(run_id) else None


def save_shelf_counts(project_root, payload):
    path = shelf_counts_path(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def load_shelf_counts(project_root, default=None):
    path = shelf_counts_path(project_root)
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default if default is not None else {}


def read_counts(project_root, run_id=None):
    payload = _payload_for_run(load_shelf_counts(project_root, default={}), run_id)
    if not payload:
        return {}
    counts = payload.get("counts") or {}
    return {product_id: int(counts.get(product_id, 0)) for product_id in product_ids()}


def read_baseline_counts(project_root, run_id=None):
    payload = _payload_for_run(load_shelf_counts(project_root, default={}), run_id)
    if not payload or not payload.get("baseline_locked"):
        return None
    baseline = payload.get("baseline_counts")
    if isinstance(baseline, dict) and baseline:
        return {product_id: int(baseline.get(product_id, 0)) for product_id in product_ids()}
    return None


def max_slots_for_product(product_id):
    slots = slots_for_product(product_id)
    return len(slots) if slots else 9


def bottles_per_sort_box():
    logic = _load_sorter_logic()
    if logic is not None and logic is not False:
        return int(logic.BOTTLES_PER_BOX)
    return 3


def shelf_is_full(count, product_id):
    return int(count) >= max_slots_for_product(product_id)


def shelf_has_space(count, product_id, add_items=None):
    """True if add_items (default one sort box = 3 bottles) fit on the front shelf."""
    add_items = bottles_per_sort_box() if add_items is None else int(add_items)
    return int(count) + add_items <= max_slots_for_product(product_id)


def can_accept_sort(count, product_id, cube_count=None):
    return shelf_has_space(count, product_id, add_items=cube_count or bottles_per_sort_box())


def shelf_capacity_summary(counts):
    """Per-product capacity view for dashboard / logs."""
    summary = {}
    for product_id in product_ids():
        current = int(counts.get(product_id, 0))
        maximum = max_slots_for_product(product_id)
        summary[product_id] = {
            "count": current,
            "max": maximum,
            "full": current >= maximum,
            "free_slots": max(0, maximum - current),
        }
    return summary


def shelf_monitoring_ready(project_root, min_sim_time=0.5, run_id=None):
    """Shelf counts file exists, baseline was captured, and counts are non-zero."""
    payload = _payload_for_run(load_shelf_counts(project_root, default={}), run_id)
    if not payload or not payload.get("counts"):
        return False
    if not payload.get("baseline_locked"):
        return False
    if float(payload.get("sim_time", 0)) < min_sim_time:
        return False
    baseline = payload.get("baseline_counts")
    if not isinstance(baseline, dict) or sum(int(v) for v in baseline.values()) <= 0:
        return False
    if sum(int(v) for v in payload["counts"].values()) <= 0:
        return False
    return True
