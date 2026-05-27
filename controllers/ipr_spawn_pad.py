"""IPR cardboard box spawn pad — right_pallet_spawner(1) in the world."""

import math

IPR_BOX_SPAWN_PAD_DEF = "IPR_BOX_SPAWN_PAD"

# Spawner Robot at z=-0.1 with WoodenPallet child at z=0.1 → box center ≈ +0.3.
PALLET_TOP_OFFSET_Z = 0.3
SPAWN_AREA_RADIUS = 0.25

# Fallback: right_pallet_spawner(1) in triger_trashhold.wbt
FALLBACK_SPAWN_XYZ = [9.38, 1.19, 0.2]
FALLBACK_SPAWN_ROTATION = [4.66295e-18, -8.32667e-18, 1, 3.13905]


def _node_world_xyz(node):
    try:
        pos = node.getPosition()
        if pos and len(pos) >= 3:
            return [float(pos[0]), float(pos[1]), float(pos[2])]
    except (AttributeError, TypeError, RuntimeError):
        pass
    field = node.getField("translation")
    if field is not None:
        return list(field.getSFVec3f())
    return None


def resolve_spawn_pad(get_from_def):
    """
    World XYZ + rotation for a box on the IPR pick pallet pad.
    Uses DEF IPR_BOX_SPAWN_PAD (right_pallet_spawner(1)).
    """
    node = get_from_def(IPR_BOX_SPAWN_PAD_DEF)
    if node is None:
        return list(FALLBACK_SPAWN_XYZ), list(FALLBACK_SPAWN_ROTATION), False

    origin = _node_world_xyz(node)
    if origin is None:
        return list(FALLBACK_SPAWN_XYZ), list(FALLBACK_SPAWN_ROTATION), False

    position = [origin[0], origin[1], origin[2] + PALLET_TOP_OFFSET_Z]
    return position, list(FALLBACK_SPAWN_ROTATION), True


def box_at_spawn_pad(get_from_def, spawn_xy, radius=SPAWN_AREA_RADIUS, max_scan=500):
    prefix = "SPAWNED_BOX_"
    for index in range(max_scan):
        box_def = f"{prefix}{index}"
        node = get_from_def(box_def)
        if node is None:
            continue
        pos = _node_world_xyz(node)
        if pos is None:
            continue
        if math.hypot(pos[0] - spawn_xy[0], pos[1] - spawn_xy[1]) <= radius:
            return box_def
    return None
