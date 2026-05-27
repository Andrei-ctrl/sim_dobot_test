"""Shared run-id guards for file-based IPC signals between Webots sessions."""

import json
import os
import time

RUN_FILENAME = "sim_run.json"
STALE_FUTURE_SEC = 1.0


def _run_path(project_root):
    return os.path.join(project_root, "data", RUN_FILENAME)


def begin_run(project_root):
    """Start a new Webots session; returns monotonic run_id."""
    path = _run_path(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        run_id = int(payload.get("run_id", 0)) + 1
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
        run_id = 1
    payload = {"run_id": run_id, "wall_time": time.time()}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return run_id


def current_run_id(project_root):
    try:
        with open(_run_path(project_root), encoding="utf-8") as handle:
            return int(json.load(handle).get("run_id", 0))
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
        return 0


def signal_for_current_run(signal, project_root):
    """True when signal was written during this Webots session."""
    if not signal:
        return False
    signal_run = int(signal.get("run_id", 0) or 0)
    if signal_run <= 0:
        return False
    return signal_run == current_run_id(project_root)


def is_signal_from_current_run(signal_time, sim_start_time, current_time):
    """Reject signals impossibly far ahead of now (legacy time guard)."""
    if signal_time > current_time + STALE_FUTURE_SEC:
        return False
    return True
