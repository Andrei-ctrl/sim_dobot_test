"""Central task orchestration: inventory thresholds, shelf row gaps, JSON task queues."""

import json
import math
import os
import sys

import product_routing

_SHELF_MON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shelf_monitoring")
if _SHELF_MON_DIR not in sys.path:
    sys.path.insert(0, _SHELF_MON_DIR)

try:
    import shelf_monitoring_logic as shelf_mon
except ImportError:
    shelf_mon = None

try:
    import sort_signal
except ImportError:
    sort_signal = None  # unit tests may stub

INVENTORY_FILENAME = "inventory.json"
STATE_FILENAME = "task_manager_state.json"
RESTOCK_QUEUE_FILENAME = "restock_queue.json"
SYSTEM_STATE_FILENAME = "system_state.json"

BOTTLES_PER_ROW = 3
SHELF_CUBE_RADIUS = 0.35
MAX_CUBE_SCAN = 40
MAX_BOX_SCAN = 100
DEFAULT_THRESHOLD = 2
RESTOCK_COOLDOWN_SEC = 12.0
PALLET_TARGET_BOXES = 5
PALLET_MIN_BOXES = 3

try:
    _RESTOCKER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "youbot_restocker_demo")
    if _RESTOCKER_DIR not in sys.path:
        sys.path.insert(0, _RESTOCKER_DIR)
    import youbot_restocker_logic as restocker_logic

    SPAWN_ORDER_COOLDOWN_SEC = restocker_logic.SPAWN_DELAY_SEC
except ImportError:
    restocker_logic = None
    SPAWN_ORDER_COOLDOWN_SEC = 50.0

try:
    import spawn_signal
except ImportError:
    spawn_signal = None


def data_dir(project_root):
    return os.path.join(project_root, "data")


def inventory_path(project_root):
    return os.path.join(data_dir(project_root), INVENTORY_FILENAME)


def state_path(project_root):
    return os.path.join(data_dir(project_root), STATE_FILENAME)


def restock_queue_path(project_root):
    return os.path.join(data_dir(project_root), RESTOCK_QUEUE_FILENAME)


def system_state_path(project_root):
    return os.path.join(data_dir(project_root), SYSTEM_STATE_FILENAME)


def load_json(path, default=None):
    default = default if default is not None else {}
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def save_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def load_inventory(project_root):
    return load_json(inventory_path(project_root), default={})


def save_inventory(project_root, inventory):
    save_json(inventory_path(project_root), inventory)


def load_state(project_root):
    return load_json(
        state_path(project_root),
        default={
            "baseline_shelf_counts": {},
            "last_shelf_counts": {},
            "last_trigger_time": {},
            "pending_products": [],
        },
    )


def save_state(project_root, state):
    save_json(state_path(project_root), state)


def load_restock_queue(project_root):
    data = load_json(restock_queue_path(project_root), default=[])
    return data if isinstance(data, list) else []


def save_restock_queue(project_root, queue):
    save_json(restock_queue_path(project_root), queue)


def iter_product_ids():
    for pallet_def in product_routing.iter_pallet_defs():
        yield product_routing.route_for_pallet_def(pallet_def)["product_id"]


def shelf_slots_for_product(product_id):
    try:
        import youbot_sorter_logic as sorter_logic
    except ImportError:
        return []
    return sorter_logic.PRODUCT_SHELF_ALL_SLOTS.get(product_id, [])


def cube_near_shelf(pos, product_id):
    for slot in shelf_slots_for_product(product_id):
        if math.hypot(pos[0] - slot[0], pos[1] - slot[1]) <= SHELF_CUBE_RADIUS:
            if abs(pos[2] - slot[2]) <= 0.55:
                return True
    return False


def count_shelf_cubes(get_from_def, product_id, max_cubes=MAX_CUBE_SCAN):
    prefix = "PRODUCT_CUBE_"
    count = 0
    for index in range(max_cubes):
        node = get_from_def(f"{prefix}{index}")
        if node is None:
            continue
        pos = node.getField("translation").getSFVec3f()
        if cube_near_shelf(pos, product_id):
            count += 1
    return count


def count_all_shelf_cubes(get_from_def):
    return {
        product_id: count_shelf_cubes(get_from_def, product_id)
        for product_id in iter_product_ids()
    }


def rows_on_shelf(item_count):
    return item_count // BOTTLES_PER_ROW


def missing_row_count(baseline_count, current_count):
    """Full rows missing compared to baseline (3 items per row)."""
    if baseline_count <= 0:
        return 0
    missing_items = max(0, baseline_count - current_count)
    return missing_items // BOTTLES_PER_ROW


def shelf_needs_restock(baseline_count, current_count):
    return missing_row_count(baseline_count, current_count) >= 1


def inventory_needs_restock(inventory, product_id, shelf_item_count=None):
    item = inventory.get(product_id) or {}
    threshold = int(item.get("threshold", DEFAULT_THRESHOLD))
    storage = int(item.get("storage_stock", 0))
    if shelf_item_count is not None:
        front = shelf_item_count * 2
    else:
        front = int(item.get("front_stock", 0))
    return front < threshold and storage > 0


def find_box_on_pallet(get_from_def, pallet_def):
    prefix = product_routing.BOX_DEF_PREFIX
    for index in range(MAX_BOX_SCAN):
        box_def = f"{prefix}{index}"
        node = get_from_def(box_def)
        if node is None:
            continue
        pos = node.getField("translation").getSFVec3f()
        if product_routing.box_on_pallet(pos, pallet_def):
            return box_def
    return ""


def count_boxes_on_pallet(get_from_def, pallet_def):
    prefix = product_routing.BOX_DEF_PREFIX
    count = 0
    for index in range(MAX_BOX_SCAN):
        box_def = f"{prefix}{index}"
        node = get_from_def(box_def)
        if node is None:
            continue
        pos = node.getField("translation").getSFVec3f()
        if product_routing.box_on_pallet(pos, pallet_def):
            count += 1
    return count


def count_boxes_for_product(get_from_def, product_id):
    route = product_routing.route_for_product_id(product_id)
    return count_boxes_on_pallet(get_from_def, route["def"])


def count_all_pallet_boxes(get_from_def):
    return {
        pallet_def: count_boxes_on_pallet(get_from_def, pallet_def)
        for pallet_def in product_routing.iter_pallet_defs()
    }


def pallet_spawn_cooldown_elapsed(state, product_id, sim_time):
    last = float((state.get("last_pallet_spawn_time") or {}).get(product_id, -1e9))
    return (sim_time - last) >= SPAWN_ORDER_COOLDOWN_SEC


def evaluate_pallet_stock_needs(project_root, get_from_def, sim_time, state):
    """
    When a stock pallet drops below PALLET_MIN_BOXES, order IPR spawns until
    PALLET_TARGET_BOXES is reached (one spawn request per cooldown interval).
    """
    if get_from_def is None or spawn_signal is None:
        return []

    replenish = state.setdefault("pallet_replenish_target", {})
    ever_full = state.setdefault("pallet_ever_full", {})
    actions = []

    for product_id in iter_product_ids():
        route = product_routing.route_for_product_id(product_id)
        pallet_def = route["def"]
        count = count_boxes_on_pallet(get_from_def, pallet_def)
        target = replenish.get(product_id)

        if count >= PALLET_TARGET_BOXES:
            ever_full[product_id] = True
            if target is not None and count >= target:
                replenish.pop(product_id, None)
            continue

        if not ever_full.get(product_id):
            continue

        if target is None and count < PALLET_MIN_BOXES:
            replenish[product_id] = PALLET_TARGET_BOXES
            target = PALLET_TARGET_BOXES
        elif target is not None and count >= target:
            replenish.pop(product_id, None)
            continue
        elif target is None:
            continue

        if not pallet_spawn_cooldown_elapsed(state, product_id, sim_time):
            continue

        actions.append(
            {
                "kind": "spawn_box",
                "product_id": product_id,
                "pallet_def": pallet_def,
                "current_count": count,
                "target_count": target,
                "reason": (
                    f"pallet stock {count}/{target} "
                    f"(replenish to {PALLET_TARGET_BOXES})"
                ),
            }
        )

    return actions


def create_spawn_request(project_root, product_id, sim_time, *, reason=""):
    if spawn_signal is None:
        return None
    return spawn_signal.write_spawn_request(
        project_root,
        product_id,
        sim_time,
        reason=reason,
        triggered_by="task_manager",
    )


def has_open_sort_task(project_root, product_id, sort_queue=None):
    if sort_queue is None and sort_signal is not None:
        sort_queue = sort_signal.read_queue(project_root)
    sort_queue = sort_queue or []
    for task in sort_queue:
        if task.get("product_id") == product_id and task.get("status", "pending") != "done":
            return True
    return False


def has_open_restock_task(project_root, product_id, restock_queue=None):
    restock_queue = restock_queue if restock_queue is not None else load_restock_queue(project_root)
    for task in restock_queue:
        if task.get("product_id") == product_id and task.get("status", "pending") != "done":
            return True
    return False


def cooldown_elapsed(state, product_id, sim_time, cooldown_sec=RESTOCK_COOLDOWN_SEC):
    last = float((state.get("last_trigger_time") or {}).get(product_id, -1e9))
    return (sim_time - last) >= cooldown_sec


def create_sort_task(
    project_root,
    product_id,
    sim_time,
    *,
    box_def="",
    task_type="front_restock",
    reason="",
    triggered_by="task_manager",
):
    if sort_signal is None:
        raise RuntimeError("sort_signal module unavailable")
    route = product_routing.route_for_product_id(product_id)
    try:
        import youbot_sorter_logic as sorter_logic
        cube_count = sorter_logic.BOTTLES_PER_BOX
        units_per_cube = sorter_logic.UNITS_PER_CUBE
    except ImportError:
        cube_count = BOTTLES_PER_ROW
        units_per_cube = 2

    payload = sort_signal.write_signal(
        project_root,
        product_id=product_id,
        source_pallet=route["def"],
        cube_count=cube_count,
        units_per_cube=units_per_cube,
        sim_time=sim_time,
        box_def=box_def or "",
        task_type=task_type,
        reason=reason,
        triggered_by=triggered_by,
    )
    return payload


def append_restock_task(project_root, product_id, sim_time, reason=""):
    queue = load_restock_queue(project_root)
    seq = max([int(item.get("seq", 0)) for item in queue], default=0) + 1
    route = product_routing.route_for_product_id(product_id)
    task = {
        "seq": seq,
        "task_type": "pallet_restock",
        "product_id": product_id,
        "target_pallet": route["def"],
        "reason": reason,
        "status": "pending",
        "t": sim_time,
    }
    queue.append(task)
    save_restock_queue(project_root, queue)
    return task


def sync_front_stock_from_shelves(inventory, shelf_counts):
    """Keep front_stock aligned with visible shelf cubes (3 units per cube)."""
    updated = dict(inventory)
    for product_id, count in shelf_counts.items():
        item = dict(updated.get(product_id) or {})
        item["front_stock"] = count * 2
        updated[product_id] = item
    return updated


def evaluate_restock_needs(
    project_root,
    shelf_counts,
    baseline_counts,
    inventory,
    sim_time,
    state,
    get_from_def=None,
):
    """
    Return list of actions: sort and/or pallet restock requests.
    Does not write files — caller applies actions.
    """
    actions = []
    sort_queue = sort_signal.read_queue(project_root) if sort_signal else []

    for product_id in iter_product_ids():
        route = product_routing.route_for_product_id(product_id)
        baseline = int(baseline_counts.get(product_id, 0))
        current = int(shelf_counts.get(product_id, 0))
        if baseline <= 0:
            continue

        row_missing = shelf_needs_restock(baseline, current)
        threshold_hit = inventory_needs_restock(
            inventory, product_id, shelf_item_count=current
        )

        if not row_missing and not threshold_hit:
            continue
        # Threshold-only restock is deferred until shelf-capacity gating is validated.
        if threshold_hit and not row_missing:
            continue
        if shelf_mon is not None and not shelf_mon.can_accept_sort(current, product_id):
            continue
        if has_open_sort_task(project_root, product_id, sort_queue):
            continue
        if not cooldown_elapsed(state, product_id, sim_time):
            continue

        box_def = ""
        if get_from_def is not None:
            box_def = find_box_on_pallet(get_from_def, route["def"])

        storage = int((inventory.get(product_id) or {}).get("storage_stock", 0))
        reasons = []
        if row_missing:
            reasons.append(
                f"missing {missing_row_count(baseline, current)} row(s) "
                f"({current}/{baseline} items on shelf)"
            )
        if threshold_hit:
            reasons.append("front_stock below threshold")

        if box_def or storage > 0:
            actions.append(
                {
                    "kind": "sort",
                    "product_id": product_id,
                    "box_def": box_def,
                    "reason": "; ".join(reasons),
                }
            )
        else:
            if not has_open_restock_task(project_root, product_id):
                actions.append(
                    {
                        "kind": "restock",
                        "product_id": product_id,
                        "reason": "; ".join(reasons) + "; no box on stock pallet",
                    }
                )
    return actions


def build_system_state(
    project_root,
    sim_time,
    shelf_counts,
    baseline_counts,
    inventory,
    active_tasks=None,
    robots=None,
    event=None,
):
    sort_queue = sort_signal.read_queue(project_root) if sort_signal else []
    restock_queue = load_restock_queue(project_root)
    payload = {
        "sim_time": sim_time,
        "inventory": inventory,
        "shelf_counts": shelf_counts,
        "baseline_shelf_counts": baseline_counts,
        "sort_queue": sort_queue,
        "restock_queue": restock_queue,
        "active_tasks": active_tasks or [],
        "robots": robots
        or {
            "sorter": {"status": "idle", "detail": "youBot sorter"},
            "restocker": {"status": "idle", "detail": "youBot restocker"},
            "ipr": {"status": "idle", "detail": "IPR pick arm"},
        },
    }
    if event:
        payload["last_event"] = event
    return payload


def publish_system_state(project_root, payload):
    save_json(system_state_path(project_root), payload)


def dashboard_payload(project_root, sim_time, shelf_counts, baseline_counts, inventory, event=None):
    active = []
    if sort_signal:
        for task in sort_signal.read_queue(project_root)[-5:]:
            active.append(
                {
                    "type": "sort",
                    "seq": task.get("seq"),
                    "product_id": task.get("product_id"),
                    "task_type": task.get("task_type", "stock_pallet"),
                    "reason": task.get("reason", ""),
                    "status": task.get("status", "pending"),
                }
            )
    for task in load_restock_queue(project_root)[-5:]:
        active.append(
            {
                "type": "restock",
                "seq": task.get("seq"),
                "product_id": task.get("product_id"),
                "reason": task.get("reason", ""),
                "status": task.get("status", "pending"),
            }
        )
    return build_system_state(
        project_root,
        sim_time,
        shelf_counts,
        baseline_counts,
        inventory,
        active_tasks=active,
        event=event,
    )
