"""POST simulation events to dashboard_server.py (shared by controllers)."""

import json
import os
import urllib.error
import urllib.request

DEFAULT_DASHBOARD_URL = "http://127.0.0.1:8000/update"
FAILURE_FILENAME = "last_failure.json"
THRESHOLD_LOG_FILENAME = "threshold_log.json"


def data_dir(project_root):
    return os.path.join(project_root, "data")


def failure_path(project_root):
    return os.path.join(data_dir(project_root), FAILURE_FILENAME)


def threshold_log_path(project_root):
    return os.path.join(data_dir(project_root), THRESHOLD_LOG_FILENAME)


def dashboard_enabled():
    return os.environ.get("SEND_TO_DASHBOARD", "1") not in ("0", "false", "False")


def post_update(payload, url=DEFAULT_DASHBOARD_URL, timeout=0.4):
    if not dashboard_enabled():
        return False
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def save_failure(project_root, event):
    path = failure_path(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(event, handle, indent=2)


def append_threshold_log(project_root, entry, max_entries=24):
    path = threshold_log_path(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, encoding="utf-8") as handle:
            log = json.load(handle)
            if not isinstance(log, list):
                log = []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        log = []
    log.append(entry)
    log = log[-max_entries:]
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(log, handle, indent=2)


def post_event(project_root, event, source="", extra=None):
    payload = {"source": source, "last_event": event}
    if extra:
        payload.update(extra)
    if event.get("event") == "robot_failure":
        save_failure(project_root, event)
        payload["last_failure"] = event
    return post_update(payload)


def post_robot_failure(project_root, robot, reason, source="", sim_time=None, **fields):
    event = {
        "event": "robot_failure",
        "robot": robot,
        "reason": reason,
    }
    if sim_time is not None:
        event["t"] = sim_time
    event.update(fields)
    return post_event(project_root, event, source=source or robot)
