"""Upstream conveyor scanner events for pallet replenishment timing."""

import json
import os

import sim_session

SCAN_FILENAME = "conveyor_scan_signal.json"


def scan_path(project_root):
    return os.path.join(project_root, "data", SCAN_FILENAME)


def read_scan(project_root):
    path = scan_path(project_root)
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def write_scan(project_root, box_def, product_id, sim_time):
    path = scan_path(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    current = read_scan(project_root) or {}
    sequence = int(current.get("seq", 0)) + 1
    payload = {
        "seq": sequence,
        "run_id": sim_session.current_run_id(project_root),
        "box_def": box_def,
        "product_id": product_id,
        "t": sim_time,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return payload
