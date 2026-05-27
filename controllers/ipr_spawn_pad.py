"""IPR cardboard box spawn pad — DEF IPR_BOX_SPAWN_PAD (right_pallet_spawner(1))."""

import math

IPR_BOX_SPAWN_PAD_DEF = "IPR_BOX_SPAWN_PAD"

# Canonical world translation of DEF IPR_BOX_SPAWN_PAD in Factory_environment_copy_new.wbt
SPAWN_PAD_ROBOT_XYZ = [9.38, 1.19, -0.1]

# Measured box pose on the spawn pallet (world coordinates).
BOX_SPAWN_XYZ = [8.92989, 1.15124, 0.18998]
BOX_SPAWN_ROTATION = [
    -1.0825425125806883e-12,
    1.6007498474861455e-15,
    1,
    3.1390500000002186,
]

SPAWN_AREA_RADIUS = 0.25
FALLBACK_SPAWN_XYZ = list(BOX_SPAWN_XYZ)
FALLBACK_SPAWN_ROTATION = list(BOX_SPAWN_ROTATION)


def _node_world_xyz(node):
    """World XYZ for a scene node (Supervisor API)."""
    try:
        pos = node.getPosition()
        if pos and len(pos) >= 3:
            return [float(pos[0]), float(pos[1]), float(pos[2])]
    except (AttributeError, TypeError, RuntimeError):
        pass
    field = node.getField("translation")
    if field is not None:
        return [float(v) for v in field.getSFVec3f()]
    return None


def resolve_spawn_pad(get_from_def):
    """
    World XYZ + rotation for a box on the IPR pick pallet pad.
    Uses the measured box pose on DEF IPR_BOX_SPAWN_PAD.
    """
    node = get_from_def(IPR_BOX_SPAWN_PAD_DEF)
    if node is None:
        return list(FALLBACK_SPAWN_XYZ), list(FALLBACK_SPAWN_ROTATION), False
    return list(BOX_SPAWN_XYZ), list(BOX_SPAWN_ROTATION), True


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


def spawn_pad_label(position, pad_ok):
    pad_xyz = SPAWN_PAD_ROBOT_XYZ
    status = "DEF IPR_BOX_SPAWN_PAD" if pad_ok else "fallback (DEF missing)"
    return (
        f"{status} robot=({pad_xyz[0]:.2f}, {pad_xyz[1]:.2f}, {pad_xyz[2]:.2f}) "
        f"box=({position[0]:.3f}, {position[1]:.3f}, {position[2]:.3f})"
    )
