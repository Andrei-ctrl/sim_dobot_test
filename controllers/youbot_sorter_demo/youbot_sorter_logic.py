"""Pure helpers for youBot sorter product-bottle pipeline (Webots-independent)."""

import math
import os
import sys

_CONTROLLERS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CONTROLLERS_DIR not in sys.path:
    sys.path.insert(0, _CONTROLLERS_DIR)

import product_routing  # noqa: E402

CUBE_SIZE = 0.05
BOTTLES_PER_BOX = 3
CUBES_PER_BOX = BOTTLES_PER_BOX
UNITS_PER_CUBE = 2
MAX_LIVE_CUBES = 15
CUBE_DEF_PREFIX = "PRODUCT_CUBE_"

DEFAULT_PRODUCT_ID = product_routing.STOCK_PALLETS["BEER_STOCK"]["product_id"]
DEFAULT_PALLET_DEF = product_routing.DEFAULT_PALLET_DEF
SOURCE_PALLET_DEF = DEFAULT_PALLET_DEF  # legacy alias

BEER_SHELF_BASE = product_routing.STOCK_PALLETS["BEER_STOCK"]["shelf_base"]
SORTER_HOME_XYZ = [-7.5277, 4.58907, 0.101917]
SORTER_HOME_XY = SORTER_HOME_XYZ[:2]

# Calibrated product-specific sorting paths (world XYZ).
PRODUCT_SORT_ROUTES = {
    "BEER_BOTTLE": {
        "label": "beer",
        "pre_pickup": [-9.38793, 2.59907, 0.0977153],
        "pickup": [-10.3879, 2.59907, 0.0954989],
        "deposit": [-11.0279, 2.59907, 0.0940796],
        "idle_pre_pickup": [-9.2979, 2.59907, 0.0979143],
        "next_task_pickup": [-10.3879, 2.59907, 0.0954989],
    },
    "CHIPS": {
        "label": "chips",
        "pre_pickup": [-9.2979, 4.32907, 0.0979822],
        "pickup": [-10.3879, 4.32907, 0.0955662],
        "deposit": [-10.9679, 4.32907, 0.0942812],
        "idle_pre_pickup": [-9.2979, 4.32907, 0.0979822],
        "next_task_pickup": [-10.3879, 4.32907, 0.0955662],
    },
    "CHEESE": {
        "label": "cheese",
        "pre_pickup": [-9.1879, 6.09907, 0.0982963],
        "pickup": [-10.5079, 6.09907, 0.09537],
        "deposit": [-10.5079, 6.09907, 0.09537],
        "idle_pre_pickup": [-9.1879, 6.09907, 0.0982963],
        "next_task_pickup": [-10.5079, 6.09907, 0.09537],
    },
    "MILK": {
        "label": "milk",
        "pre_pickup": [-9.4279, 7.83907, 0.097832],
        "pickup": [-10.5379, 7.83907, 0.0953716],
        "deposit": [-10.5379, 7.83907, 0.0953716],
        "idle_pre_pickup": [-9.4279, 7.83907, 0.097832],
        "next_task_pickup": [-10.5379, 7.83907, 0.0953716],
    },
}

NAV_AXIS_TOL = 0.05
NAV_POS_TOL = 0.10

PALLET_LOOKAHEAD_M = 0.55
PALLET_BLOCK_EXTRA_M = 0.25

RESTOCK_PALLET_APPROACH_XY = product_routing.pallet_approach_xy(DEFAULT_PALLET_DEF)
BEER_SHELF_APPROACH_XY = product_routing.shelf_approach_xy(DEFAULT_PRODUCT_ID)

STAGING_PALLET_DEF = "MILK_STOCK"  # legacy alias
STORAGE_DRINKS_DEF = "Beer section"
STORAGE_DRINKS_BASE = BEER_SHELF_BASE

BOTTLE_UPRIGHT_ROTATION = [
    0.9999999143416298,
    9.791416094629902e-09,
    -0.0004139042558314946,
    4.478218134559611e-05,
]

# Legacy aliases mapped from beer route.
BEER_PALLET_LOAD_XY = PRODUCT_SORT_ROUTES["BEER_BOTTLE"]["pickup"][:2]
PALLET_STAGING_XY = PRODUCT_SORT_ROUTES["BEER_BOTTLE"]["pre_pickup"][:2]
BOX_LOAD_XY = PRODUCT_SORT_ROUTES["BEER_BOTTLE"]["pickup"][:2]
SAFE_AISLE_X = -8.0

# Front IR distance sensor lookup (value -> meters).
FRONT_SENSOR_LOOKUP = (
    (0.0, 4095.0),
    (0.05, 3200.0),
    (0.15, 1800.0),
    (0.35, 700.0),
    (0.6, 150.0),
    (1.0, 0.0),
)
FRONT_SENSOR_MIN_VALID = 50.0
FRONT_SENSOR_MAX_VALID = 4000.0
OBSTACLE_DISTANCE_M = 0.38
# Readings closer than this are usually the back platform / self-geometry.
OBSTACLE_SELF_HIT_M = 0.12

PLATFORM_SLOTS = [
    [0.0, -0.04, 0.17],
    [0.0, 0.0, 0.17],
    [0.0, 0.04, 0.17],
]

# Single cardboard box carried on the sorter back-platform (local to robot).
BOX_PLATFORM_SLOT = [0.0, 0.0, 0.19]
BOX_ON_PALLET_ROTATION = [4.66295e-18, -8.32667e-18, 1, 3.13905]

# Legacy aisle corners (reserved for multi-product routes later).
SHELF_ROUTE_CORNER_1 = [-8.77, 8.91]
SHELF_ROUTE_CORNER_2 = [-12.36, 8.91]

# Calibrated beer shelf grid: 3 rows x 3 columns (9 hardcoded world XYZ slots).
# Shelf node at (-11.5, 2.7, 0). Rows are top -> middle -> bottom (high Z -> low Z).
BEER_SHELF_CENTER_Y = 2.7
SHELF_MAX_SORT_OPERATIONS = 3
SHELF_ROW_LABELS = ("top", "middle", "bottom")
SLOT_XY_RADIUS = 0.14
SLOT_Z_RADIUS = 0.22

BEER_SHELF_ALL_SLOTS = [
    # Operation 1 — top row
    [-11.569700137512447, 2.890000000000004, 0.8126949793078967],
    [-11.569700137512447, 2.6700000000000035, 0.8126949793078965],
    [-11.569713967598007, 2.460000000006549, 0.8127515552576389],
    # Operation 2 — middle row
    [-11.569700013828156, 2.890000000000001, 0.4823633206741502],
    [-11.569700013828156, 2.6800000000000006, 0.4823633206741502],
    [-11.569700013828156, 2.4600000000000004, 0.4823633206741502],
    # Operation 3 — bottom row
    [-11.569700619186117, 2.9100000000000126, 0.10049580653231352],
    [-11.569700619186117, 2.6800000000000126, 0.10049580653231352],
    [-11.569700619186117, 2.4600000000000124, 0.10049580653231352],
]

BEER_SHELF_BOTTLE_POSITIONS = BEER_SHELF_ALL_SLOTS[:BOTTLES_PER_BOX]

# Calibrated milk shelf row 1 (ops 1) at y ≈ 7.9; rows 2–3 use beer Z spacing.
MILK_SHELF_ROW1 = [
    [-11.569699999997416, 8.1500135446762, 0.8399823417531128],
    [-11.569699999377539, 7.9402592559070655, 0.8395681483961769],
    [-11.569699999391307, 7.650497765754047, 0.839382911428412],
]

SHELF_Z_DROP_MID = BEER_SHELF_ALL_SLOTS[0][2] - BEER_SHELF_ALL_SLOTS[3][2]
SHELF_Z_DROP_LOW = BEER_SHELF_ALL_SLOTS[0][2] - BEER_SHELF_ALL_SLOTS[6][2]


def expand_shelf_rows_from_row1(row1):
    """Build 9 slots: row1 + two lower rows using beer shelf Z spacing."""
    slots = []
    for z_drop in (0.0, SHELF_Z_DROP_MID, SHELF_Z_DROP_LOW):
        for pos in row1:
            slots.append([pos[0], pos[1], pos[2] - z_drop])
    return slots


MILK_SHELF_ALL_SLOTS = expand_shelf_rows_from_row1(MILK_SHELF_ROW1)
PRODUCT_SHELF_CENTER_Y = {
    "BEER_BOTTLE": 2.7,
    "CHIPS": 4.35,
    "CHEESE": 6.1,
    "MILK": 7.9,
}


def derive_shelf_slots_from_beer(shelf_center_y):
    """Same X/Z grid as beer; shift Y to each shelf row."""
    return [
        [pos[0], shelf_center_y + (pos[1] - BEER_SHELF_CENTER_Y), pos[2]]
        for pos in BEER_SHELF_ALL_SLOTS
    ]


PRODUCT_SHELF_ALL_SLOTS = {
    "BEER_BOTTLE": [list(pos) for pos in BEER_SHELF_ALL_SLOTS],
    "CHIPS": derive_shelf_slots_from_beer(PRODUCT_SHELF_CENTER_Y["CHIPS"]),
    "CHEESE": derive_shelf_slots_from_beer(PRODUCT_SHELF_CENTER_Y["CHEESE"]),
    "MILK": [list(pos) for pos in MILK_SHELF_ALL_SLOTS],
}

PRODUCT_SHELF_SLOTS = {
    product_id: slots[:BOTTLES_PER_BOX]
    for product_id, slots in PRODUCT_SHELF_ALL_SLOTS.items()
}

PLATFORM_MIN_Z = 0.16

PRODUCT_SHELF_BASE = {
    entry["product_id"]: list(entry["shelf_base"])
    for entry in product_routing.STOCK_PALLETS.values()
}

PRODUCT_COLORS = {
    "BEER_BOTTLE": [0.9, 0.7, 0.2],
    "CHIPS": [0.95, 0.85, 0.2],
    "CHEESE": [0.95, 0.75, 0.3],
    "MILK": [0.9, 0.95, 1.0],
}

PRODUCT_SHELF_ITEM_PROTO = {
    "BEER_BOTTLE": "BeerBottle",
    "CHIPS": "ChipsPack",
    "MILK": "MilkCarton",
    "CHEESE": "CheeseWedge",
}


def shelf_item_proto(product_id):
    return PRODUCT_SHELF_ITEM_PROTO.get(product_id, "BeerBottle")


def normalize_angle(angle):
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle


def product_color(product_id):
    return PRODUCT_COLORS.get(product_id, [0.8, 0.8, 0.8])


def sort_route_for_product(product_id):
    """Return calibrated sort path for a product ID."""
    return dict(
        PRODUCT_SORT_ROUTES.get(product_id, PRODUCT_SORT_ROUTES[DEFAULT_PRODUCT_ID])
    )


def sort_route_label(product_id):
    return sort_route_for_product(product_id)["label"]


def deposit_xyz_for_product(product_id):
    return list(sort_route_for_product(product_id)["deposit"])


def shelf_base_for_product(product_id):
    deposit = deposit_xyz_for_product(product_id)
    return [deposit[0], deposit[1], 0.0]


def axis_waypoints(from_xyz, to_xyz, axis_tol=NAV_AXIS_TOL):
    """World-frame path moving Y first, then X (sideways then forward/back)."""
    fx, fy, fz = from_xyz[0], from_xyz[1], from_xyz[2] if len(from_xyz) > 2 else 0.0
    tx, ty, tz = to_xyz[0], to_xyz[1], to_xyz[2] if len(to_xyz) > 2 else fz
    points = []
    if abs(fy - ty) > axis_tol:
        points.append([fx, ty, fz])
    if abs(fx - tx) > axis_tol or abs(fy - ty) > axis_tol:
        points.append([tx, ty, tz])
    if not points:
        points.append([tx, ty, tz])
    return points


def pickup_task_waypoints(from_xyz, product_id):
    """pre-pickup -> pickup -> deposit for an active sort task."""
    route = sort_route_for_product(product_id)
    path = []
    for key in ("pre_pickup", "pickup", "deposit"):
        segment = axis_waypoints(from_xyz, route[key])
        path.extend(segment)
        from_xyz = route[key]
    return path


def post_deposit_waypoints(from_xyz, product_id, has_next_same_product):
    route = sort_route_for_product(product_id)
    target = route["next_task_pickup"] if has_next_same_product else route["idle_pre_pickup"]
    return axis_waypoints(from_xyz, target)


def nav_log_message(action, product_id):
    label = sort_route_label(product_id)
    messages = {
        "pre_pickup": f"Moving to {label} pre-pickup",
        "pickup": f"Picking {label}",
        "deposit": f"Depositing {label} on shelf",
        "next_task": f"Returning for next {label} task",
        "idle": "Returning to idle/pre-pickup position",
        "via_prev_pre_pickup": f"Via {label} pre-pickup before product switch",
    }
    return messages.get(action, action)


def append_axis_steps(steps, from_xyz, to_xyz, action, log):
    origin = list(from_xyz)
    for waypoint in axis_waypoints(origin, to_xyz):
        steps.append(
            {
                "xyz": list(waypoint),
                "action": action,
                "log": log,
            }
        )


def build_product_switch_steps(from_xyz, prev_product_id, new_product_id):
    """
    When switching products: visit previous product pre-pickup, then run new pickup path.
    """
    prev_route = sort_route_for_product(prev_product_id)
    prev_pre = prev_route["pre_pickup"]
    steps = []
    append_axis_steps(
        steps,
        from_xyz,
        prev_pre,
        "continue",
        nav_log_message("via_prev_pre_pickup", prev_product_id),
    )
    steps.extend(build_nav_steps(prev_pre, new_product_id, "pickup_run"))
    return steps


def build_nav_steps(from_xyz, product_id, phase):
    """
    Build labelled navigation steps for pickup/post-deposit phases.
    Each step: {xyz, action, log}
    """
    route = sort_route_for_product(product_id)
    steps = []
    if phase == "pickup_run":
        sequence = (
            ("pre_pickup", "pre_pickup"),
            ("pickup", "pickup"),
            ("deposit", "deposit"),
        )
        origin = list(from_xyz)
        for key, action in sequence:
            target = route[key]
            for waypoint in axis_waypoints(origin, target):
                steps.append(
                    {
                        "xyz": list(waypoint),
                        "action": action,
                        "log": nav_log_message(action, product_id),
                    }
                )
            origin = list(target)
    elif phase == "post_next":
        target = route["next_task_pickup"]
        for waypoint in axis_waypoints(from_xyz, target):
            steps.append(
                {
                    "xyz": list(waypoint),
                    "action": "next_task",
                    "log": nav_log_message("next_task", product_id),
                }
            )
    elif phase == "post_idle":
        target = route["idle_pre_pickup"]
        for waypoint in axis_waypoints(from_xyz, target):
            steps.append(
                {
                    "xyz": list(waypoint),
                    "action": "idle",
                    "log": nav_log_message("idle", product_id),
                }
            )
    return steps


def is_same_product_task(task, product_id):
    return bool(task) and task.get("product_id") == product_id


def shelf_route_waypoints(product_id=None, from_xy=None):
    """Legacy wrapper — deposit approach for product."""
    product_id = product_id or DEFAULT_PRODUCT_ID
    deposit = deposit_xyz_for_product(product_id)
    target = deposit[:2]
    if from_xy is None:
        return [target]
    return axis_waypoints([from_xy[0], from_xy[1], 0.0], deposit)


def home_route_waypoints(from_xy):
    """Legacy wrapper — axis path back to spawn home."""
    return axis_waypoints([from_xy[0], from_xy[1], 0.0], SORTER_HOME_XYZ)


def pickup_route_waypoints(from_xy):
    """Legacy wrapper — axis path to beer pre-pickup."""
    pre = PRODUCT_SORT_ROUTES[DEFAULT_PRODUCT_ID]["pre_pickup"]
    return axis_waypoints([from_xy[0], from_xy[1], 0.0], pre)


def beer_rear_pickup_shelf_xy():
    deposit = deposit_xyz_for_product(DEFAULT_PRODUCT_ID)
    return deposit[:2]


def beer_rear_pickup_pallet_xy():
    pickup = PRODUCT_SORT_ROUTES[DEFAULT_PRODUCT_ID]["pickup"]
    return pickup[:2]


def beer_rear_heading(shelf_xy=None, pallet_xy=None):
    shelf_xy = shelf_xy or beer_rear_pickup_shelf_xy()
    pallet_xy = pallet_xy or beer_rear_pickup_pallet_xy()
    dx = shelf_xy[0] - pallet_xy[0]
    dy = shelf_xy[1] - pallet_xy[1]
    return math.atan2(dy, dx)


def pallet_approach_for_def(pallet_def):
    return product_routing.pallet_approach_xy(pallet_def)


def shelf_approach_for_product(product_id):
    deposit = deposit_xyz_for_product(product_id)
    return deposit[:2]


def pallet_obstacle_centers():
    return product_routing.pallet_obstacle_centers()


def point_near_pallet(x, y, centers=None, margin=0.0):
    centers = centers if centers is not None else pallet_obstacle_centers()
    for px, py, radius in centers:
        if math.hypot(x - px, y - py) <= radius + margin:
            return True
    return False


def probe_hits_pallet(probe_x, probe_y, centers=None, margin=0.0):
    return point_near_pallet(probe_x, probe_y, centers, margin)


def forward_probe_xy(robot_xy, yaw, distance=PALLET_LOOKAHEAD_M):
    x, y = robot_xy
    return x + distance * math.cos(yaw), y + distance * math.sin(yaw)


def return_after_shelf_steps():
    """Legacy helper — post-shelf navigation is handled in the controller."""
    return [{"action": "drive_home"}]


def is_beer_sort_task(task):
    return is_same_product_task(task, DEFAULT_PRODUCT_ID)


def inventory_delta(cube_count, units_per_cube=None):
    units = units_per_cube if units_per_cube is not None else UNITS_PER_CUBE
    return cube_count * units


def reserve_next_cube_index(get_node, prefix=CUBE_DEF_PREFIX, max_index=200):
    index = 0
    while get_node(f"{prefix}{index}") is not None:
        index += 1
    return index


def count_live_cubes(get_node, prefix=CUBE_DEF_PREFIX, max_index=200):
    count = 0
    for index in range(max_index):
        if get_node(f"{prefix}{index}") is not None:
            count += 1
    return count


def local_to_world(local_xyz, robot_xyz, yaw):
    lx, ly, lz = local_xyz
    x, y, z = robot_xyz
    cos_a = math.cos(yaw)
    sin_a = math.sin(yaw)
    return [
        x + lx * cos_a - ly * sin_a,
        y + lx * sin_a + ly * cos_a,
        z + lz,
    ]


def world_positions_from_base(base_xyz, offsets):
    return [
        [base_xyz[0] + off[0], base_xyz[1] + off[1], base_xyz[2] + off[2]]
        for off in offsets
    ]


def platform_world_positions(robot_xyz, yaw, slots=None):
    slots = slots or PLATFORM_SLOTS
    return [local_to_world(slot, robot_xyz, yaw) for slot in slots]


def box_platform_world_position(robot_xyz, yaw):
    return local_to_world(BOX_PLATFORM_SLOT, robot_xyz, yaw)


def distance_from_front_sensor(value):
    """Estimate forward clearance from IR sensor reading."""
    if value <= FRONT_SENSOR_MIN_VALID:
        return float("inf")
    if value >= FRONT_SENSOR_MAX_VALID:
        return 0.0
    for i in range(len(FRONT_SENSOR_LOOKUP) - 1):
        d0, v0 = FRONT_SENSOR_LOOKUP[i]
        d1, v1 = FRONT_SENSOR_LOOKUP[i + 1]
        if value <= v0 and value >= v1:
            if abs(v0 - v1) < 1e-9:
                return d0
            ratio = (value - v1) / (v0 - v1)
            return d1 + ratio * (d0 - d1)
    return float("inf")


def obstacle_blocks_forward(sensor_value, min_distance_m=None):
    min_distance_m = OBSTACLE_DISTANCE_M if min_distance_m is None else min_distance_m
    if sensor_value <= FRONT_SENSOR_MIN_VALID:
        return False
    clearance = distance_from_front_sensor(sensor_value)
    if clearance <= OBSTACLE_SELF_HIT_M:
        return False
    return clearance <= min_distance_m


def shelf_row_label(row_index):
    if 0 <= int(row_index) < len(SHELF_ROW_LABELS):
        return SHELF_ROW_LABELS[int(row_index)]
    return f"row_{int(row_index) + 1}"


def slot_match(pos, slot, *, xy_radius=SLOT_XY_RADIUS, z_radius=SLOT_Z_RADIUS):
    return (
        math.hypot(pos[0] - slot[0], pos[1] - slot[1]) <= xy_radius
        and abs(pos[2] - slot[2]) <= z_radius
    )


def all_slots_for_product(product_id):
    return PRODUCT_SHELF_ALL_SLOTS.get(
        product_id, PRODUCT_SHELF_ALL_SLOTS[DEFAULT_PRODUCT_ID]
    )


def row_slot_indices(row_index):
    start = int(row_index) * BOTTLES_PER_BOX
    return list(range(start, start + BOTTLES_PER_BOX))


def occupied_slot_indices(positions, product_id):
    """positions: list of [x,y,z] for items already on this product shelf."""
    slots = all_slots_for_product(product_id)
    occupied = set()
    used = set()
    for slot_index, slot in enumerate(slots):
        for pos_index, pos in enumerate(positions):
            if pos_index in used:
                continue
            if slot_match(pos, slot):
                occupied.add(slot_index)
                used.add(pos_index)
                break
    return occupied


def find_empty_row_placement(positions, product_id, count=None):
    """
    Pick the first wholly empty row (top -> middle -> bottom), else empty slots.
    Returns (row_index, [slot_xyz, ...]) or (None, []).
    """
    count = BOTTLES_PER_BOX if count is None else int(count)
    slots = all_slots_for_product(product_id)
    if not slots:
        return None, []

    occupied = occupied_slot_indices(positions, product_id)
    for row in range(SHELF_MAX_SORT_OPERATIONS):
        row_indices = row_slot_indices(row)
        if all(index not in occupied for index in row_indices):
            return row, [list(slots[index]) for index in row_indices[:count]]

    empty_indices = [index for index in range(len(slots)) if index not in occupied]
    if len(empty_indices) >= count:
        chosen = empty_indices[:count]
        row = chosen[0] // BOTTLES_PER_BOX
        return row, [list(slots[index]) for index in chosen]
    return None, []


def shelf_operation_index(inventory, product_id):
    """Legacy fallback row index from inventory counter."""
    item = inventory.get(product_id) or {}
    used = int(item.get("shelf_operations", 0))
    return min(used, SHELF_MAX_SORT_OPERATIONS - 1)


def shelf_has_capacity(inventory, product_id):
    item = inventory.get(product_id) or {}
    return int(item.get("shelf_operations", 0)) < SHELF_MAX_SORT_OPERATIONS


def shelf_slots_for_operation(product_id, operation_index):
    """Three bottle XYZ positions for one sort operation."""
    slots = PRODUCT_SHELF_ALL_SLOTS.get(
        product_id, PRODUCT_SHELF_ALL_SLOTS[DEFAULT_PRODUCT_ID]
    )
    start = operation_index * BOTTLES_PER_BOX
    end = start + BOTTLES_PER_BOX
    if start >= len(slots):
        start = max(0, len(slots) - BOTTLES_PER_BOX)
        end = len(slots)
    return [list(pos) for pos in slots[start:end]]


def increment_shelf_operation(inventory, product_id, operation_index=None):
    if product_id not in inventory:
        return 0
    used = int(inventory[product_id].get("shelf_operations", 0))
    if operation_index is not None:
        used = max(used, int(operation_index) + 1)
    else:
        used = min(used + 1, SHELF_MAX_SORT_OPERATIONS)
    used = min(used, SHELF_MAX_SORT_OPERATIONS)
    inventory[product_id]["shelf_operations"] = used
    return used


def shelf_world_positions(
    shelf_base=None,
    offsets=None,
    product_id=None,
    operation_index=0,
):
    if product_id in PRODUCT_SHELF_ALL_SLOTS:
        return shelf_slots_for_operation(product_id, operation_index)
    if shelf_base is None and product_id is not None:
        base = shelf_base_for_product(product_id)
    else:
        base = list(shelf_base or BEER_SHELF_BASE)
    y_off = (base[1] - BEER_SHELF_CENTER_Y) if product_id else 0.0
    return [
        [pos[0], pos[1] + y_off, pos[2]]
        for pos in shelf_slots_for_operation(DEFAULT_PRODUCT_ID, operation_index)
    ]


def parse_sort_signal(signal):
    if not signal:
        return None
    try:
        seq = int(signal.get("seq", 0))
    except (TypeError, ValueError):
        return None
    if seq <= 0:
        return None
    return {
        "seq": seq,
        "product_id": signal.get("product_id", DEFAULT_PRODUCT_ID),
        "source_pallet": signal.get("source_pallet", DEFAULT_PALLET_DEF),
        "box_def": signal.get("box_def", ""),
        "cube_count": int(signal.get("cube_count", BOTTLES_PER_BOX)),
        "units_per_cube": int(signal.get("units_per_cube", UNITS_PER_CUBE)),
        "cube_defs": list(signal.get("cube_defs") or []),
        "task_type": signal.get("task_type", "stock_pallet"),
        "reason": signal.get("reason", ""),
        "triggered_by": signal.get("triggered_by", ""),
        "t": float(signal.get("t", 0.0)),
    }


def initial_sort_seq_baseline(completed_seq=0):
    """Sorter resumes after last completed task seq (pending queue entries stay eligible)."""
    return int(completed_seq)


def should_process_signal(signal, last_seq, sim_start_time=None, current_time=None, run_id=None):
    parsed = parse_sort_signal(signal)
    if parsed is None:
        return False, None
    if run_id is not None:
        signal_run = int((signal or {}).get("run_id", 0) or 0)
        if signal_run <= 0 or signal_run != int(run_id):
            return False, parsed
    if parsed["seq"] <= last_seq:
        return False, parsed
    return True, parsed


def next_pending_task(tasks, last_seq):
    """Pick the oldest queued task not yet handled by the sorter."""
    pending = [parse_sort_signal(task) for task in tasks]
    pending = [task for task in pending if task is not None and task["seq"] > last_seq]
    if not pending:
        return None
    pending.sort(key=lambda task: task["seq"])
    return pending[0]
