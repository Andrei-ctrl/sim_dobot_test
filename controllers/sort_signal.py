"""File-based sort task queue: restocking_task_manager → youBot sorter."""

import json
import os

import sim_session

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


def reset_for_new_run(project_root, run_id):
    """Clear sort queue and pointer when a new Webots session starts."""
    data_dir = os.path.join(project_root, "data")
    os.makedirs(data_dir, exist_ok=True)
    with open(queue_path(project_root), "w", encoding="utf-8") as handle:
        json.dump([], handle)
    with open(signal_path(project_root), "w", encoding="utf-8") as handle:
        json.dump({"seq": 0, "t": 0.0, "run_id": int(run_id)}, handle)


def reset_signal(project_root, clear_queue=False):
    """Legacy pointer reset; prefer reset_for_new_run from task_manager."""
    data_dir = os.path.join(project_root, "data")
    os.makedirs(data_dir, exist_ok=True)
    queue = read_queue(project_root)
    baseline = max([int(task.get("seq", 0)) for task in queue], default=0)
    run_id = sim_session.current_run_id(project_root)
    with open(signal_path(project_root), "w", encoding="utf-8") as handle:
        json.dump({"seq": baseline, "t": 0.0, "run_id": run_id}, handle)
    if clear_queue:
        with open(queue_path(project_root), "w", encoding="utf-8") as handle:
            json.dump([], handle)


def _task_for_run(task, run_id):
    if not task:
        return False
    session_run = int(run_id)
    task_run = int(task.get("run_id", 0) or 0)
    if session_run <= 0:
        return True
    if task_run <= 0:
        return False
    return task_run == session_run


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
    run_id=None,
):
    path = signal_path(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    current = read_signal(project_root) or {}
    sequence = int(current.get("seq", 0)) + 1
    session_run = int(run_id if run_id is not None else sim_session.current_run_id(project_root))
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
        "run_id": session_run,
        "t": sim_time,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)

    queue = read_queue(project_root)
    queue.append(payload)
    with open(queue_path(project_root), "w", encoding="utf-8") as handle:
        json.dump(queue, handle, indent=2)
    return payload


def pending_tasks(project_root, last_seq, run_id=None):
    """Return open queued sort tasks for the current Webots session."""
    session_run = int(run_id if run_id is not None else sim_session.current_run_id(project_root))
    pending = []
    for task in read_queue(project_root):
        if int(task.get("seq", 0)) <= int(last_seq):
            continue
        if not _task_for_run(task, session_run):
            continue
        if not task_is_open(task):
            continue
        pending.append(task)
    return pending


TERMINAL_TASK_STATUSES = frozenset({"done", "skipped_full", "failed"})


def skip_open_tasks_for_product(
    project_root, product_id, *, run_id=None, status="skipped_full"
):
    """Close all pending sort tasks for one product (e.g. shelf already full)."""
    session_run = int(run_id if run_id is not None else sim_session.current_run_id(project_root))
    path = queue_path(project_root)
    queue = read_queue(project_root)
    skipped = []
    for task in queue:
        if task.get("product_id") != product_id:
            continue
        if not _task_for_run(task, session_run):
            continue
        if not task_is_open(task):
            continue
        task["status"] = status
        skipped.append(int(task.get("seq", 0)))
    if skipped:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(queue, handle, indent=2)
    return skipped


def mark_task_done(project_root, seq, status="done", sim_time=None):
    """Mark a queue entry completed so restarts do not replay it."""
    path = queue_path(project_root)
    queue = read_queue(project_root)
    updated = False
    for task in queue:
        if int(task.get("seq", 0)) == int(seq):
            task["status"] = status
            if status == "failed" and sim_time is not None:
                task["t_failed"] = float(sim_time)
            updated = True
    if updated:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(queue, handle, indent=2)


def task_is_open(task):
    return task.get("status", "pending") not in TERMINAL_TASK_STATUSES


def last_completed_seq(project_root, run_id=None):
    """Highest seq the sorter has finished for the current Webots session."""
    session_run = int(run_id if run_id is not None else sim_session.current_run_id(project_root))
    finished = TERMINAL_TASK_STATUSES
    done = [
        int(task.get("seq", 0))
        for task in read_queue(project_root)
        if task.get("status") in finished and _task_for_run(task, session_run)
    ]
    return max(done) if done else 0
