"""Detect foreign objects on the grocery conveyor belt (supervisor scene scan)."""

import math

try:
    import youbot_restocker_logic as _scan_logic
except ImportError:
    _scan_logic = None

# Main cardbox belt (conveyor_cardbox): translation ~3.7, size 10 x 0.7, Y ~ 0.54
CONVEYOR_Y = 0.54
CONVEYOR_Y_HALF = 0.42
CONVEYOR_X_MIN = -1.5
CONVEYOR_X_MAX = 8.8
CONVEYOR_Z_MIN = 0.08
CONVEYOR_Z_MAX = 0.55

KNOWN_DEF_PREFIXES = (
    "SPAWNED_BOX_",
    "BOX_",
    "DEMO_BOTTLE",
    "BEER_BOTTLE",
    "STORE_YOUBOT",
    "IPR_",
    "RESTOCK_PALLET",
    "STOCK_PALLET",
    "FRONT_SHELF",
    "LEFT_BELT",
    "RIGHT_BELT",
    "GROCERY_",
)

IGNORE_TYPE_NAMES = frozenset(
    {
        "ConveyorBelt",
        "Robot",
        "WorldInfo",
        "Viewpoint",
        "TexturedBackground",
        "TexturedBackgroundLight",
        "Floor",
        "UnevenTerrain",
        "Wall",
        "SolidBox",
        "Group",
        "Transform",
        "Pose",
        "Slot",
        "DistanceSensor",
        "Receiver",
        "Emitter",
        "Camera",
        "InfraredEmitter",
        "InfraredReceiver",
        "GPS",
        "Compass",
        "Gyro",
        "Accelerometer",
        "WoodenPallet",
        "WoodenPalletStack",
        "Shelves",
        "Monitor",
        "LeverValve",
        "TruckSimple",
        "YoubotBoxGrip",
        "IprHd6ms180",
        "Shape",
        "DEF",
    }
)

PHYSICAL_TYPE_NAMES = frozenset(
    {
        "Solid",
        "CardboardBox",
        "RubberDuck",
        "PlasticContainer",
        "BeerBottle",
        "WoodenCrate",
        "BiscuitBox",
    }
)

IGNORE_NAME_PREFIXES = (
    "conveyor",
    "CONVEYOR",
    "DETECTION",
    "RESTOCK",
    "STORE_",
    "test_controller",
    "spawn",
    "IPR_",
    "pallet",
    "sorting dock",
)

IGNORE_EXACT_NAMES = frozenset(
    {
        "CONVEYOR_ZONE",
        "DETECTION_ZONE",
        "GROCERY_CONVEYOR",
    }
)


def is_known_def(def_name):
    if not def_name:
        return False
    return any(def_name.startswith(prefix) for prefix in KNOWN_DEF_PREFIXES)


def in_conveyor_corridor(pos):
    if pos is None or len(pos) < 3:
        return False
    x, y, z = pos[0], pos[1], pos[2]
    return (
        CONVEYOR_X_MIN <= x <= CONVEYOR_X_MAX
        and abs(y - CONVEYOR_Y) <= CONVEYOR_Y_HALF
        and CONVEYOR_Z_MIN <= z <= CONVEYOR_Z_MAX
    )


def in_scanner_zone(pos, scanner_xy=None, radius=None):
    """Upstream conveyor scanner zone (same geometry as SPAWNED_BOX_* scan)."""
    if pos is None or len(pos) < 3:
        return False
    if _scan_logic is not None:
        return _scan_logic.box_in_scanner_zone(pos, scanner_xy, radius)
    scanner_xy = scanner_xy or [-0.01, 1.09]
    radius = radius if radius is not None else 0.8
    return math.hypot(pos[0] - scanner_xy[0], pos[1] - scanner_xy[1]) <= radius


def node_world_position(node):
    for getter in ("getPosition", "getPose"):
        try:
            method = getattr(node, getter, None)
            if method is None:
                continue
            values = method()
            if values and len(values) >= 3:
                return [float(values[0]), float(values[1]), float(values[2])]
        except (AttributeError, TypeError, RuntimeError):
            continue
    field = node.getField("translation")
    if field is not None:
        return list(field.getSFVec3f())
    return None


def node_def_name(node):
    try:
        def_name = node.getDef()
        if def_name:
            return def_name
    except (AttributeError, RuntimeError):
        pass
    return ""


def node_label(node, def_name="", type_name=""):
    name_field = node.getField("name")
    name = ""
    if name_field is not None:
        try:
            name = name_field.getSFString()
        except (AttributeError, RuntimeError):
            name = ""
    if def_name:
        return def_name
    if name:
        return name
    return type_name or "unknown"


def should_ignore_node(type_name, name, def_name):
    if type_name in IGNORE_TYPE_NAMES:
        return True
    if def_name and is_known_def(def_name):
        return True
    if name in IGNORE_EXACT_NAMES:
        return True
    lowered = (name or "").lower()
    for prefix in IGNORE_NAME_PREFIXES:
        if lowered.startswith(prefix.lower()):
            return True
    return False


def is_physical_candidate(type_name, node):
    if type_name in PHYSICAL_TYPE_NAMES:
        return True
    mass_field = node.getField("mass")
    if mass_field is not None:
        try:
            return mass_field.getSFFloat() > 0.0
        except (AttributeError, RuntimeError):
            pass
    return False


def walk_conveyor_objects(children_field, max_depth=14, zone_filter=None):
    """Yield dicts for scene nodes that could be foreign objects on the belt."""
    if children_field is None:
        return
    if zone_filter is None:
        zone_filter = in_conveyor_corridor

    def _walk(field, depth):
        if field is None or depth > max_depth:
            return
        index = 0
        while True:
            try:
                count = field.getCount()
            except (AttributeError, RuntimeError):
                break
            if index >= count:
                break
            try:
                node = field.getMFNode(index)
            except (AttributeError, RuntimeError):
                index += 1
                continue
            if node is None:
                index += 1
                continue

            type_name = node.getTypeName()
            def_name = node_def_name(node)
            name_field = node.getField("name")
            name = ""
            if name_field is not None:
                try:
                    name = name_field.getSFString()
                except (AttributeError, RuntimeError):
                    name = ""

            if not should_ignore_node(type_name, name, def_name):
                if is_physical_candidate(type_name, node):
                    pos = node_world_position(node)
                    if zone_filter(pos):
                        yield {
                            "def_name": def_name,
                            "name": name,
                            "type_name": type_name,
                            "position": pos,
                            "label": node_label(node, def_name, type_name),
                        }

            try:
                nested = node.getField("children")
            except (AttributeError, RuntimeError):
                nested = None
            if nested is not None:
                yield from _walk(nested, depth + 1)
            index += 1

    yield from _walk(children_field, 0)


def _filter_unknown_objects(objects, get_from_def=None):
    unknowns = []
    for obj in objects:
        def_name = obj.get("def_name") or ""
        if is_known_def(def_name):
            continue
        if def_name.startswith("SPAWNED_BOX_") or def_name.startswith("BOX_"):
            continue
        unknowns.append(obj)
    unknowns.sort(key=lambda item: item["position"][0])
    return unknowns


def find_unknown_objects(children_field, get_from_def=None):
    """Return foreign objects anywhere on the main conveyor corridor."""
    objects = walk_conveyor_objects(children_field, zone_filter=in_conveyor_corridor)
    return _filter_unknown_objects(objects, get_from_def)


def find_unknown_at_scanner(
    children_field,
    get_from_def=None,
    scanner_xy=None,
    radius=None,
):
    """Return foreign objects currently in the upstream conveyor scanner zone."""

    def _zone(pos):
        return in_scanner_zone(pos, scanner_xy, radius)

    objects = walk_conveyor_objects(children_field, zone_filter=_zone)
    return _filter_unknown_objects(objects, get_from_def)


def unknown_still_present(children_field, signal, get_from_def=None):
    """True while a signaled unknown object is still anywhere in the scene."""
    if not signal or not signal.get("active"):
        return False
    label = signal.get("label") or ""
    name = signal.get("object_name") or ""

    def _anywhere(pos):
        return pos is not None and len(pos) >= 3

    for obj in walk_conveyor_objects(children_field, zone_filter=_anywhere):
        if label and obj.get("label") == label:
            return True
        if name and obj.get("name") == name:
            return True
    return False


def object_key(obj):
    pos = obj.get("position") or [0.0, 0.0, 0.0]
    label = obj.get("label") or obj.get("name") or obj.get("type_name") or "unknown"
    return (
        label,
        round(pos[0], 2),
        round(pos[1], 2),
        round(pos[2], 2),
    )


def format_object_label(obj):
    label = obj.get("label") or "unknown"
    pos = obj.get("position") or [0.0, 0.0, 0.0]
    return f"{label} @ ({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f})"


def dist_to_pick_slot(pos, pick_xy=(-1.250096294314212, 0.5725919418293408)):
    if pos is None:
        return float("inf")
    return math.hypot(pos[0] - pick_xy[0], pos[1] - pick_xy[1])
