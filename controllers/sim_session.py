"""Shared sim-time guards for file-based IPC signals between Webots runs."""

STALE_FUTURE_SEC = 1.0


def is_signal_from_current_run(signal_time, sim_start_time, current_time):
    """Reject signals written before this run or impossibly far ahead of now."""
    if signal_time < sim_start_time - 0.01:
        return False
    if signal_time > current_time + STALE_FUTURE_SEC:
        return False
    return True
