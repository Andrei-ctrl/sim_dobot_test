"""File-based spawn trigger between conveyor scanner / task manager and IPR box spawner."""

import json
import os

import product_routing

SIGNAL_FILENAME = "spawn_signal.json"


def signal_path(project_root):
    return os.path.join(project_root, "data", SIGNAL_FILENAME)


def read_signal(project_root):
    path = signal_path(project_root)
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def write_signal(
    project_root,
    box_def,
    sim_time,
    *,
    product_id="",
    target_pallet="",
    reason="",
    triggered_by="scanner",
):
    path = signal_path(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    current = read_signal(project_root) or {}
    sequence = int(current.get("seq", 0)) + 1
    payload = {
        "seq": sequence,
        "box_def": box_def,
        "product_id": product_id,
        "target_pallet": target_pallet,
        "reason": reason,
        "triggered_by": triggered_by,
        "t": sim_time,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return payload


def write_spawn_request(
    project_root,
    product_id,
    sim_time,
    *,
    reason="",
    triggered_by="task_manager",
):
    """Order IPR to spawn a box for a specific stock pallet product."""
    route = product_routing.route_for_product_id(product_id)
    return write_signal(
        project_root,
        "",
        sim_time,
        product_id=product_id,
        target_pallet=route["def"],
        reason=reason,
        triggered_by=triggered_by,
    )
