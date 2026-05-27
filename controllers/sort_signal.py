"""File-based sort trigger between stock_monitoring and youBot sorter."""

import json
import os

SIGNAL_FILENAME = "sort_signal.json"
QUEUE_FILENAME = "sort_queue.json"


def signal_path(project_root):
    return os.path.join(project_root, "data", SIGNAL_FILENAME)


def queue_path(project_root):
    return os.path.join(project_root, "data", QUEUE_FILENAME)


def read_signal(project_root):
    path = signal_path(project_root)
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def read_queue(project_root):
    path = queue_path(project_root)
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def reset_signal(project_root, clear_queue=False):
    """Clear stale sort trigger pointer from a previous Webots run.

    By default the task queue is preserved so RestockingTaskManager tasks
    are not wiped when the sorter or stock_monitoring controllers start.
    """
    data_dir = os.path.join(project_root, "data")
    os.makedirs(data_dir, exist_ok=True)
    queue = read_queue(project_root)
    baseline = max([int(task.get("seq", 0)) for task in queue], default=0)
    with open(signal_path(project_root), "w", encoding="utf-8") as handle:
        json.dump({"seq": baseline, "t": 0.0}, handle)
    if clear_queue:
        with open(queue_path(project_root), "w", encoding="utf-8") as handle:
            json.dump([], handle)


def write_signal(
    project_root,
    product_id,
    source_pallet,
    cube_count,
    units_per_cube,
    sim_time,
    cube_defs=None,
    box_def="",
    staging_pallet="",
    task_type="stock_pallet",
    reason="",
    triggered_by="",
    status="pending",
):
    path = signal_path(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    current = read_signal(project_root) or {}
    sequence = int(current.get("seq", 0)) + 1
    payload = {
        "seq": sequence,
        "product_id": product_id,
        "source_pallet": source_pallet,
        "staging_pallet": staging_pallet,
        "box_def": box_def,
        "cube_count": cube_count,
        "units_per_cube": units_per_cube,
        "cube_defs": cube_defs or [],
        "task_type": task_type,
        "reason": reason,
        "triggered_by": triggered_by,
        "status": status,
        "t": sim_time,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)

    queue = read_queue(project_root)
    queue.append(payload)
    with open(queue_path(project_root), "w", encoding="utf-8") as handle:
        json.dump(queue, handle, indent=2)
    return payload


def pending_tasks(project_root, last_seq):
    """Return queued sort tasks with seq greater than last_seq."""
    return [task for task in read_queue(project_root) if int(task.get("seq", 0)) > last_seq]


def mark_task_done(project_root, seq, status="done"):
    """Mark a queue entry completed so restarts do not replay it."""
    path = queue_path(project_root)
    queue = read_queue(project_root)
    updated = False
    for task in queue:
        if int(task.get("seq", 0)) == int(seq):
            task["status"] = status
            updated = True
    if updated:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(queue, handle, indent=2)


def last_completed_seq(project_root):
    """Highest seq the sorter has finished (persisted in queue status)."""
    finished = (
        "done",
        "skipped_full",
    )
    done = [
        int(task.get("seq", 0))
        for task in read_queue(project_root)
        if task.get("status") in finished
    ]
    return max(done) if done else 0
