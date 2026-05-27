"""File-based box → stock-pallet assignment (scanner → restocker)."""

import json
import os

import product_routing

ROUTING_FILENAME = "box_routing.json"


def routing_path(project_root):
    return os.path.join(project_root, "data", ROUTING_FILENAME)


def read_all(project_root):
    path = routing_path(project_root)
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def read_assignment(project_root, box_def):
    return read_all(project_root).get(box_def)


def write_assignment(project_root, box_def, route, sim_time, *, box_uid=""):
    path = routing_path(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = read_all(project_root)
    data[box_def] = {
        "box_def": box_def,
        "box_uid": box_uid,
        "target_pallet": route["def"],
        "product_id": route["product_id"],
        "shelf_name": route["shelf_name"],
        "shelf_base": list(route["shelf_base"]),
        "approach_xy": list(route["approach_xy"]),
        "t": sim_time,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    return data[box_def]


def assign_box(project_root, box_def, sim_time):
    route = product_routing.route_for_box_def(box_def)
    return write_assignment(project_root, box_def, route, sim_time)


def assign_box_to_pallet(project_root, box_def, pallet_def, sim_time, *, box_uid=""):
    route = product_routing.route_for_pallet_def(pallet_def)
    return write_assignment(
        project_root, box_def, route, sim_time, box_uid=box_uid
    )
