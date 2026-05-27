"""Pure detection/navigation helpers for youBot restocker (Webots-independent)."""

import math

# Calibrated wait pose (STORE_YOUBOT_RESTOCKER).
RESTOCKER_HOME_TRANSLATION = [
    -1.87451,
    0.573775,
    0.103458,
]
RESTOCKER_HOME_ROTATION = [
    -0.011047702244776967,
    0.9999389722620184,
    5.166130221864949e-06,
    0.0017881998985398793,
]
RESTOCKER_HOME_XY = RESTOCKER_HOME_TRANSLATION[:2]

# Calibrated fixed pick slot (cardboard box on conveyor at youBot).
FIXED_PICK_BOX_POS = [
    -1.250096294314212,
    0.5725919418293408,
    0.19910759327234218,
]
FIXED_PICK_RADIUS = 0.18

# Legacy rectangular zone (kept as fallback).
PICKUP_X_MAX = -1.05
CONVEYOR_Y = 0.5725919418293408
Y_TOLERANCE = 0.22
Z_MIN = 0.12
Z_MAX = 0.35

SENSOR_CLOSE = 120
SENSOR_MAX_VALID = 3200  # above = arm/gripper self-hit, not a box

# Delay before IPR spawns the next box after conveyor scanner detection.
SPAWN_DELAY_SEC = 50.0
# Task-manager pallet orders spawn right away; spacing is handled by the supervisor.
SPAWN_TASK_MANAGER_DELAY_SEC = 0.0

# 0 = unlimited simultaneous boxes (cap disabled).
MAX_LIVE_BOXES = 0
BOX_DEF_PREFIX = "SPAWNED_BOX_"
SCANNER_XY = [-0.01, 1.09]
SCANNER_RADIUS = 0.8
NEAR_CONVEYOR_RADIUS = 0.45
ROBOT_BOX_REACH = 0.85
SEARCH_DELAY_SEC = 100.0
# Physics settle before supervisor verifies pallet count increased after release.
RESTOCK_VERIFY_SETTLE_STEPS = 120

# Distance sensor lookup (YoubotBoxGrip arm5 IR sensor, value -> meters).
SENSOR_LOOKUP = (
    (4095, 0.0),
    (3200, 0.05),
    (1800, 0.15),
    (700, 0.35),
    (150, 0.6),
    (0, 1.0),
)
ALIGN_LATERAL_TOL = 0.035
ALIGN_FORWARD_TOL = 0.05


def box_limit_reached(live_count):
    return MAX_LIVE_BOXES > 0 and live_count >= MAX_LIVE_BOXES


def count_live_boxes(get_node, prefix=BOX_DEF_PREFIX, max_index=500):
    """Count existing SPAWNED_BOX_* nodes (get_node: callable like robot.getFromDef)."""
    count = 0
    for index in range(max_index):
        if get_node(f"{prefix}{index}") is not None:
            count += 1
    return count


def sensor_value_to_distance(sensor_value):
    """Convert arm IR reading to estimated range in meters (inverse lookup table)."""
    if sensor_value is None:
        return None
    table = SENSOR_LOOKUP
    if sensor_value >= table[0][0]:
        return table[0][1]
    if sensor_value <= table[-1][0]:
        return table[-1][1]
    for (v_hi, d_hi), (v_lo, d_lo) in zip(table, table[1:]):
        if v_lo <= sensor_value <= v_hi:
            if v_hi == v_lo:
                return d_hi
            t = (sensor_value - v_lo) / (v_hi - v_lo)
            return d_lo + t * (d_hi - d_lo)
    return None


def compute_alignment_errors(box_pos, robot_xy, home_xy=None, ref_box=None):
    """
    XY alignment error vs calibrated home→box geometry.
    Returns (forward_err, lateral_err) in robot/world axes (x=forward, y=lateral).
    Positive lateral → box is to the left of expected; positive forward → box is farther ahead.
    """
    home_xy = home_xy or RESTOCKER_HOME_XY
    ref_box = ref_box or FIXED_PICK_BOX_POS
    ref_forward = ref_box[0] - home_xy[0]
    ref_lateral = ref_box[1] - home_xy[1]
    forward = box_pos[0] - robot_xy[0]
    lateral = box_pos[1] - robot_xy[1]
    return forward - ref_forward, lateral - ref_lateral


def is_alignment_ok(forward_err, lateral_err, forward_tol=None, lateral_tol=None):
    forward_tol = forward_tol if forward_tol is not None else ALIGN_FORWARD_TOL
    lateral_tol = lateral_tol if lateral_tol is not None else ALIGN_LATERAL_TOL
    return abs(forward_err) <= forward_tol and abs(lateral_err) <= lateral_tol


def build_box_scan_info(box_def, pos, scanner_xy=None, scanner_radius=None):
    """Build a dict of box metadata for scanner / restocker logging."""
    scanner_xy = scanner_xy or SCANNER_XY
    scanner_radius = scanner_radius if scanner_radius is not None else SCANNER_RADIUS
    dist_scanner = math.hypot(pos[0] - scanner_xy[0], pos[1] - scanner_xy[1])
    dist_pick = distance_to_fixed_pick(pos)
    in_scanner = dist_scanner <= scanner_radius
    at_pick = is_at_fixed_pick_slot(pos)
    return {
        "def": box_def,
        "position": list(pos),
        "dist_to_scanner": dist_scanner,
        "dist_to_pick_slot": dist_pick,
        "in_scanner_zone": in_scanner,
        "at_fixed_pick_slot": at_pick,
        "pickable": is_box_pickable(pos),
    }


def format_box_scan_log(info, prefix="[SCANNER]"):
    pos = info["position"]
    lines = [
        f"{prefix} Box scan:",
        f"  DEF={info['def']}",
        f"  position=({pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f})",
        f"  dist_scanner={info['dist_to_scanner']:.3f}m "
        f"in_zone={info['in_scanner_zone']}",
        f"  dist_pick_slot={info['dist_to_pick_slot']:.3f}m "
        f"at_slot={info['at_fixed_pick_slot']} pickable={info['pickable']}",
    ]
    if info.get("product_id"):
        lines.append(f"  product_id={info['product_id']}")
    if info.get("name"):
        lines.append(f"  name={info['name']}")
    if info.get("category"):
        lines.append(f"  category={info['category']}")
    if info.get("size"):
        size = info["size"]
        lines.append(f"  size=({size[0]:.3f}, {size[1]:.3f}, {size[2]:.3f})")
    if info.get("mass") is not None:
        lines.append(f"  mass={info['mass']:.3f}")
    if info.get("zone"):
        lines.append(f"  zone={info['zone']}")
    if info.get("distance_sensor") is not None:
        lines.append(f"  distance_sensor={info['distance_sensor']}")
    return "\n".join(lines)


def search_allowed(conveyor_box_detected, detect_time, current_time, delay=None):
    """Search is only allowed after upstream conveyor scanner saw a box and delay elapsed."""
    if not conveyor_box_detected or detect_time is None:
        return False
    delay = delay if delay is not None else SEARCH_DELAY_SEC
    return (current_time - detect_time) >= delay


def normalize_angle(angle):
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle


def distance_3d(a, b):
    return math.sqrt(
        (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2
    )


def distance_to_fixed_pick(pos, fixed_pos=None):
    fixed_pos = fixed_pos or FIXED_PICK_BOX_POS
    return distance_3d(pos, fixed_pos)


def is_at_fixed_pick_slot(pos, fixed_pos=None, radius=None):
    """Primary pick detection: box center near the calibrated fixed slot."""
    radius = radius if radius is not None else FIXED_PICK_RADIUS
    return distance_to_fixed_pick(pos, fixed_pos) <= radius


def box_in_scanner_zone(pos, scanner_xy=None, radius=None):
    scanner_xy = scanner_xy or SCANNER_XY
    radius = radius if radius is not None else SCANNER_RADIUS
    return math.hypot(pos[0] - scanner_xy[0], pos[1] - scanner_xy[1]) <= radius


def is_at_pick_station(pos):
    """Fallback rectangular pick zone."""
    return (
        pos[0] <= PICKUP_X_MAX
        and abs(pos[1] - CONVEYOR_Y) < Y_TOLERANCE
        and Z_MIN <= pos[2] <= Z_MAX
    )


def is_box_pickable(pos):
    return is_at_fixed_pick_slot(pos) or is_at_pick_station(pos)


def sensor_sees_box(sensor_value, sensor_present=True, threshold=None, max_valid=None):
    """True when arm sensor reads a box at plausible distance (not self-hit)."""
    threshold = threshold if threshold is not None else SENSOR_CLOSE
    max_valid = max_valid if max_valid is not None else SENSOR_MAX_VALID
    if not sensor_present:
        return False
    if sensor_value is None:
        return False
    return threshold <= sensor_value <= max_valid


def is_near_conveyor(robot_xy, home_xy, radius=None):
    radius = radius if radius is not None else NEAR_CONVEYOR_RADIUS
    return math.hypot(robot_xy[0] - home_xy[0], robot_xy[1] - home_xy[1]) <= radius


def box_within_robot_reach(robot_xy, box_pos, reach=None):
    reach = reach if reach is not None else ROBOT_BOX_REACH
    return math.hypot(box_pos[0] - robot_xy[0], box_pos[1] - robot_xy[1]) <= reach


def pick_station_rejection_reason(pos):
    if is_at_fixed_pick_slot(pos):
        return []
    reasons = []
    dist = distance_to_fixed_pick(pos)
    reasons.append(
        f"dist_to_fixed_slot={dist:.3f} > {FIXED_PICK_RADIUS} "
        f"(target {FIXED_PICK_BOX_POS[0]:.3f},{FIXED_PICK_BOX_POS[1]:.3f},{FIXED_PICK_BOX_POS[2]:.3f})"
    )
    if pos[0] > PICKUP_X_MAX:
        reasons.append(f"x={pos[0]:.3f} > {PICKUP_X_MAX} (too far on conveyor)")
    if abs(pos[1] - CONVEYOR_Y) >= Y_TOLERANCE:
        reasons.append(
            f"|y-{CONVEYOR_Y}|={abs(pos[1] - CONVEYOR_Y):.3f} >= {Y_TOLERANCE}"
        )
    if pos[2] < Z_MIN or pos[2] > Z_MAX:
        reasons.append(f"z={pos[2]:.3f} outside [{Z_MIN}, {Z_MAX}]")
    return reasons


def find_pickable_box(boxes, completed_boxes):
    """Return (box_def, pos) for the nearest box at the fixed pick slot."""
    best = None
    best_dist = None
    for box_def, pos in boxes:
        if box_def in completed_boxes:
            continue
        if not is_box_pickable(pos):
            continue
        dist = distance_to_fixed_pick(pos)
        if best is None or dist < best_dist:
            best = (box_def, pos)
            best_dist = dist
    if best is None:
        return None, None
    return best


def find_nearest_box_to_fixed_slot(boxes, completed_boxes):
    best_def = None
    best_pos = None
    best_dist = None
    for box_def, pos in boxes:
        if box_def in completed_boxes:
            continue
        dist = distance_to_fixed_pick(pos)
        if best_dist is None or dist < best_dist:
            best_def = box_def
            best_pos = pos
            best_dist = dist
    return best_def, best_pos, best_dist


def find_scanner_box(boxes, completed_boxes, scanner_xy=None, radius=None):
    for box_def, pos in boxes:
        if box_def in completed_boxes:
            continue
        if box_in_scanner_zone(pos, scanner_xy, radius):
            return box_def, pos
    return None, None


def uses_hardcoded_pick_pose(box_pos, fixed_pos=None, epsilon=0.02):
    fixed_pos = fixed_pos or FIXED_PICK_BOX_POS
    return distance_to_fixed_pick(box_pos, fixed_pos) <= epsilon


def evaluate_detection(
    boxes,
    completed_boxes,
    sensor_value,
    sensor_present,
    robot_xy,
    home_xy,
    conveyor_box_detected=False,
    pending_box_def=None,
):
    """
    Evaluate all detection paths and return a diagnostic dict.

    Pick stages:
      2 — arm sensor sees box at fixed pick slot (valid reading range)
      1 — upstream scanner saw box, now at pick slot
      3 — physical: box at fixed slot, robot near conveyor (primary fallback)
    """
    pick_def, pick_pos = find_pickable_box(boxes, completed_boxes)
    scan_def, scan_pos = find_scanner_box(boxes, completed_boxes)
    nearest_def, nearest_pos, nearest_dist = find_nearest_box_to_fixed_slot(
        boxes, completed_boxes
    )
    at_pick = pick_def is not None
    sensor_valid = sensor_sees_box(sensor_value, sensor_present)
    sensor_self_hit = (
        sensor_present
        and sensor_value is not None
        and sensor_value > SENSOR_MAX_VALID
    )
    stage2 = at_pick and sensor_valid
    stage1 = (
        at_pick
        and conveyor_box_detected
        and pending_box_def is not None
        and pick_def == pending_box_def
    )
    near = is_near_conveyor(robot_xy, home_xy)
    in_reach = at_pick and box_within_robot_reach(robot_xy, pick_pos)
    stage3 = at_pick and (near or in_reach)

    should_pick = stage2 or stage1 or stage3
    if stage2:
        stage = 2
    elif stage1:
        stage = 1
    elif stage3:
        stage = 3
    else:
        stage = None

    box_reports = []
    for box_def, pos in boxes:
        if box_def in completed_boxes:
            box_reports.append(
                {
                    "def": box_def,
                    "pos": pos,
                    "status": "completed",
                }
            )
            continue
        at_fixed = is_at_fixed_pick_slot(pos)
        box_reports.append(
            {
                "def": box_def,
                "pos": pos,
                "at_fixed_slot": at_fixed,
                "at_pick_station": is_box_pickable(pos),
                "dist_to_fixed_slot": distance_to_fixed_pick(pos),
                "in_scanner_zone": box_in_scanner_zone(pos),
                "pick_reject_reasons": pick_station_rejection_reason(pos),
                "distance_to_robot": math.hypot(
                    pos[0] - robot_xy[0], pos[1] - robot_xy[1]
                ),
            }
        )

    return {
        "pick_def": pick_def,
        "pick_pos": pick_pos,
        "at_pick_station": at_pick,
        "nearest_box_def": nearest_def,
        "nearest_box_pos": nearest_pos,
        "nearest_box_dist": nearest_dist,
        "scanner_def": scan_def,
        "scanner_pos": scan_pos,
        "scanner_triggered": scan_def is not None,
        "sensor_value": sensor_value,
        "sensor_present": sensor_present,
        "sensor_valid": sensor_valid,
        "sensor_self_hit": sensor_self_hit,
        "stage2": stage2,
        "stage1": stage1,
        "stage3": stage3,
        "near_conveyor": near,
        "in_robot_reach": in_reach,
        "should_pick": should_pick,
        "pick_stage": stage,
        "conveyor_box_detected": conveyor_box_detected,
        "pending_box_def": pending_box_def,
        "fixed_pick_pos": list(FIXED_PICK_BOX_POS),
        "boxes": box_reports,
    }


def format_detection_log(diag, prefix="[YOUBOT RESTOCKER DIAG]"):
    fixed = diag.get("fixed_pick_pos", FIXED_PICK_BOX_POS)
    lines = [f"{prefix} detection snapshot:"]
    lines.append(
        f"  fixed_pick_slot=({fixed[0]:.3f}, {fixed[1]:.3f}, {fixed[2]:.3f}) "
        f"radius={FIXED_PICK_RADIUS}"
    )
    lines.append(
        f"  robot=({diag.get('robot_xy', ('?', '?'))[0]:.3f}, "
        f"{diag.get('robot_xy', ('?', '?'))[1]:.3f}) "
        f"near_conveyor={diag['near_conveyor']}"
    )
    sensor_note = ""
    if diag.get("sensor_self_hit"):
        sensor_note = " (SELF-HIT ignored)"
    lines.append(
        f"  sensor={'present' if diag['sensor_present'] else 'MISSING'} "
        f"value={diag['sensor_value']} valid={diag.get('sensor_valid')} "
        f"range=[{SENSOR_CLOSE},{SENSOR_MAX_VALID}]{sensor_note}"
    )
    lines.append(
        f"  scanner_hit={diag['scanner_triggered']} "
        f"pending={diag['pending_box_def']} stage1={diag['stage1']}"
    )
    lines.append(
        f"  at_pick={diag['at_pick_station']} in_reach={diag['in_robot_reach']} "
        f"stage3={diag['stage3']}"
    )
    if diag.get("nearest_box_dist") is not None:
        lines.append(
            f"  nearest_box={diag.get('nearest_box_def')} "
            f"dist_to_slot={diag['nearest_box_dist']:.3f}m"
        )
    if diag["should_pick"]:
        lines.append(
            f"  -> PICK READY via stage {diag['pick_stage']} ({diag['pick_def']})"
        )
    else:
        lines.append("  -> NO PICK")
    # Per-box position spam disabled — too noisy when many SPAWNED_BOX_* exist on pallets.
    # for box in diag["boxes"]:
    #     pos = box["pos"]
    #     if box.get("status") == "completed":
    #         lines.append(f"  box {box['def']}: COMPLETED (skipped)")
    #         continue
    #     flags = []
    #     if box.get("at_fixed_slot"):
    #         flags.append("FIXED_SLOT")
    #     elif box.get("at_pick_station"):
    #         flags.append("PICK_ZONE")
    #     if box.get("in_scanner_zone"):
    #         flags.append("SCANNER_ZONE")
    #     flag_str = ",".join(flags) if flags else "no zone"
    #     dist_slot = box.get("dist_to_fixed_slot", distance_to_fixed_pick(pos))
    #     dist_robot = box["distance_to_robot"]
    #     lines.append(
    #         f"  box {box['def']} @ ({pos[0]:.3f},{pos[1]:.3f},{pos[2]:.3f}) "
    #         f"[{flag_str}] dist_slot={dist_slot:.3f}m dist_robot={dist_robot:.2f}m"
    #     )
    #     if box["pick_reject_reasons"]:
    #         lines.append(f"    pick reject: {'; '.join(box['pick_reject_reasons'])}")
    return "\n".join(lines)
