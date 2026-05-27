"""Persist upstream scanner detections of foreign conveyor objects."""

import json
import os

SIGNAL_FILENAME = "conveyor_unknown.json"


def signal_path(project_root):
    return os.path.join(project_root, "data", SIGNAL_FILENAME)


def read_signal(project_root):
    path = signal_path(project_root)
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def write_signal(project_root, obj, sim_time, *, scanner_xy=None):
    path = signal_path(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "active": True,
        "label": obj.get("label") or obj.get("name") or "unknown",
        "object_name": obj.get("name") or "",
        "object_type": obj.get("type_name") or "",
        "object_def": obj.get("def_name") or "",
        "position": obj.get("position"),
        "scanner_xy": list(scanner_xy) if scanner_xy else None,
        "t": sim_time,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return payload


def clear_signal(project_root):
    path = signal_path(project_root)
    try:
        os.remove(path)
    except OSError:
        pass
