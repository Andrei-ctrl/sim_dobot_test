"""Spawn and supervisor-move product bottles for the sorter pipeline."""

import os
import sys

_CONTROLLERS_DIR = os.path.dirname(os.path.abspath(__file__))
_SORTER_LOGIC_DIR = os.path.join(_CONTROLLERS_DIR, "youbot_sorter_demo")
for path in (_CONTROLLERS_DIR, _SORTER_LOGIC_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import youbot_sorter_logic as cube_logic  # noqa: E402


def move_node_to(node, position, rotation=None, reset_physics=True):
    if node is None:
        return False
    field = node.getField("translation")
    if field is None:
        return False
    field.setSFVec3f(list(position))
    if rotation is not None:
        rot_field = node.getField("rotation")
        if rot_field is not None:
            rot_field.setSFRotation(list(rotation))
    if reset_physics:
        node.resetPhysics()
    return True


def remove_node(node):
    if node is not None:
        node.remove()


def build_bottle_node_string(cube_def, position, rotation=None, product_id=None):
    return build_shelf_item_node_string(
        cube_def, position, product_id or cube_logic.DEFAULT_PRODUCT_ID, rotation
    )


def build_shelf_item_node_string(cube_def, position, product_id, rotation=None):
    rotation = rotation or cube_logic.BOTTLE_UPRIGHT_ROTATION
    rx, ry, rz, ra = rotation
    px, py, pz = position
    proto = cube_logic.shelf_item_proto(product_id)
    return (
        f"DEF {cube_def} {proto} {{\n"
        f"  translation {px} {py} {pz}\n"
        f"  rotation {rx} {ry} {rz} {ra}\n"
        f'  name "{product_id}"\n'
        f"  mass 0.1\n"
        f"}}"
    )


def build_cube_node_string(cube_def, position, product_id):
    """Legacy solid cube spawn (kept for tests / fallback)."""
    color = cube_logic.product_color(product_id)
    r, g, b = color
    size = cube_logic.CUBE_SIZE
    return (
        f"DEF {cube_def} Solid {{\n"
        f"  translation {position[0]} {position[1]} {position[2]}\n"
        f"  children [\n"
        f"    Shape {{\n"
        f"      appearance PBRAppearance {{\n"
        f"        baseColor {r} {g} {b}\n"
        f"        roughness 0.45\n"
        f"      }}\n"
        f"      geometry Box {{\n"
        f"        size {size} {size} {size}\n"
        f"      }}\n"
        f"    }}\n"
        f"  ]\n"
        f'  name "BEER_CUBE"\n'
        f"  boundingObject Box {{\n"
        f"    size {size} {size} {size}\n"
        f"  }}\n"
        f"  physics Physics {{\n"
        f"    density -1\n"
        f"    mass 0.01\n"
        f"  }}\n"
        f"}}"
    )


def get_pallet_translation(get_from_def, pallet_def):
    pallet = get_from_def(pallet_def)
    if pallet is None:
        return None
    return list(pallet.getField("translation").getSFVec3f())


def remove_box(get_from_def, box_def):
    if not box_def:
        return False
    node = get_from_def(box_def)
    if node is None:
        return False
    remove_node(node)
    return True


def spawn_bottles_on_platform(
    children_field,
    get_from_def,
    robot_xyz,
    robot_yaw,
    product_id=None,
    count=None,
    start_index=None,
):
    """Spawn beer bottles directly on the sorter back-platform slots."""
    product_id = product_id or cube_logic.DEFAULT_PRODUCT_ID
    count = count if count is not None else cube_logic.BOTTLES_PER_BOX

    live = cube_logic.count_live_cubes(get_from_def)
    if live + count > cube_logic.MAX_LIVE_CUBES:
        print(
            f"[PRODUCT CUBES] At bottle limit ({live}/{cube_logic.MAX_LIVE_CUBES}); "
            f"cannot spawn {count}"
        )
        return []

    if start_index is None:
        start_index = cube_logic.reserve_next_cube_index(get_from_def)

    spawn_positions = cube_logic.platform_world_positions(robot_xyz, robot_yaw)
    upright = cube_logic.BOTTLE_UPRIGHT_ROTATION
    spawned = []

    for i in range(count):
        cube_def = f"{cube_logic.CUBE_DEF_PREFIX}{start_index + i}"
        slot = spawn_positions[i % len(spawn_positions)]
        node_string = build_shelf_item_node_string(
            cube_def, slot, product_id, upright
        )
        children_field.importMFNodeFromString(-1, node_string)
        if get_from_def(cube_def) is not None:
            spawned.append(cube_def)
            print(
                f"[PRODUCT CUBES] Spawned bottle {cube_def} on platform "
                f"at ({slot[0]:.3f}, {slot[1]:.3f}, {slot[2]:.3f})"
            )
        else:
            print(f"[PRODUCT CUBES ERROR] Failed to spawn {cube_def}")

    return spawned


def _pallet_spawn_positions(pallet_pos):
    """Legacy staging-pallet bottle offsets (unused in active pipeline)."""
    px, py, pz = pallet_pos
    z = pz + 0.12
    return [
        [px - 0.08, py - 0.04, z],
        [px, py, z],
        [px + 0.08, py + 0.04, z],
    ]


def spawn_cubes_on_pallet(
    children_field,
    get_from_def,
    pallet_def,
    product_id=None,
    count=None,
    start_index=None,
):
    """
    Spawn beer bottles on a pallet. Returns list of spawned DEF names.
    children_field: supervisor root children Field from getRoot().getField("children")
    """
    product_id = product_id or cube_logic.DEFAULT_PRODUCT_ID
    count = count if count is not None else cube_logic.CUBES_PER_BOX

    live = cube_logic.count_live_cubes(get_from_def)
    if live + count > cube_logic.MAX_LIVE_CUBES:
        print(
            f"[PRODUCT CUBES] At bottle limit ({live}/{cube_logic.MAX_LIVE_CUBES}); "
            f"cannot spawn {count}"
        )
        return []

    pallet_pos = get_pallet_translation(get_from_def, pallet_def)
    if pallet_pos is None:
        print(f"[PRODUCT CUBES ERROR] Pallet DEF not found: {pallet_def}")
        return []

    if start_index is None:
        start_index = cube_logic.reserve_next_cube_index(get_from_def)

    spawn_positions = _pallet_spawn_positions(pallet_pos)
    upright = cube_logic.BOTTLE_UPRIGHT_ROTATION
    spawned = []

    for i in range(count):
        cube_def = f"{cube_logic.CUBE_DEF_PREFIX}{start_index + i}"
        offset = spawn_positions[i % len(spawn_positions)]
        node_string = build_shelf_item_node_string(
            cube_def, offset, product_id, upright
        )
        children_field.importMFNodeFromString(-1, node_string)
        if get_from_def(cube_def) is not None:
            spawned.append(cube_def)
            print(
                f"[PRODUCT CUBES] Spawned bottle {cube_def} on {pallet_def} "
                f"at ({offset[0]:.3f}, {offset[1]:.3f}, {offset[2]:.3f})"
            )
        else:
            print(f"[PRODUCT CUBES ERROR] Failed to spawn {cube_def}")

    return spawned


def collect_cube_nodes(get_from_def, cube_defs):
    nodes = []
    for cube_def in cube_defs:
        node = get_from_def(cube_def)
        if node is not None:
            nodes.append((cube_def, node))
    return nodes


def attach_box_to_platform(get_from_def, box_def, robot_xyz, robot_yaw):
    """Supervisor-snap the stock box onto the sorter back-platform."""
    if not box_def:
        return False
    node = get_from_def(box_def)
    if node is None:
        return False
    slot = cube_logic.box_platform_world_position(robot_xyz, robot_yaw)
    return move_node_to(
        node, slot, cube_logic.BOX_ON_PALLET_ROTATION, reset_physics=False
    )


def resnap_box_to_platform(get_from_def, box_def, robot_xyz, robot_yaw):
    return attach_box_to_platform(get_from_def, box_def, robot_xyz, robot_yaw)


def spawn_bottles_on_shelf(
    children_field,
    get_from_def,
    shelf_base=None,
    product_id=None,
    count=None,
    start_index=None,
    operation_index=0,
):
    """Supervisor-spawn beer bottles onto shelf slots for one sort operation."""
    product_id = product_id or cube_logic.DEFAULT_PRODUCT_ID
    count = count if count is not None else cube_logic.BOTTLES_PER_BOX

    live = cube_logic.count_live_cubes(get_from_def)
    if live + count > cube_logic.MAX_LIVE_CUBES:
        print(
            f"[PRODUCT CUBES] At bottle limit ({live}/{cube_logic.MAX_LIVE_CUBES}); "
            f"cannot spawn {count} on shelf"
        )
        return []

    if start_index is None:
        start_index = cube_logic.reserve_next_cube_index(get_from_def)

    positions = cube_logic.shelf_world_positions(
        shelf_base,
        product_id=product_id,
        operation_index=operation_index,
    )
    upright = cube_logic.BOTTLE_UPRIGHT_ROTATION
    spawned = []

    for i in range(count):
        cube_def = f"{cube_logic.CUBE_DEF_PREFIX}{start_index + i}"
        slot = positions[i % len(positions)]
        node_string = build_shelf_item_node_string(
            cube_def, slot, product_id, upright
        )
        children_field.importMFNodeFromString(-1, node_string)
        if get_from_def(cube_def) is not None:
            spawned.append(cube_def)
            print(
                f"[PRODUCT CUBES] Spawned {product_id} item {cube_def} on shelf "
                f"at ({slot[0]:.3f}, {slot[1]:.3f}, {slot[2]:.3f})"
            )
        else:
            print(f"[PRODUCT CUBES ERROR] Failed to spawn shelf bottle {cube_def}")

    return spawned


def unpack_box_to_shelf(
    children_field,
    get_from_def,
    box_def,
    shelf_base=None,
    product_id=None,
    count=None,
    operation_index=0,
):
    """Remove carried box and supervisor-place its bottles on the shelf."""
    remove_box(get_from_def, box_def)
    return spawn_bottles_on_shelf(
        children_field,
        get_from_def,
        shelf_base=shelf_base,
        product_id=product_id,
        count=count,
        operation_index=operation_index,
    )


def attach_cubes_to_platform(get_from_def, cube_defs, robot_xyz, robot_yaw):
    """Supervisor-snap bottles onto back-platform slots."""
    positions = cube_logic.platform_world_positions(robot_xyz, robot_yaw)
    upright = cube_logic.BOTTLE_UPRIGHT_ROTATION
    nodes = collect_cube_nodes(get_from_def, cube_defs)
    moved = []
    for i, (cube_def, node) in enumerate(nodes):
        slot = positions[i % len(positions)]
        if move_node_to(node, slot, upright):
            moved.append(cube_def)
    return moved


def place_cubes_on_shelf(
    get_from_def,
    cube_defs,
    shelf_base=None,
    product_id=None,
    operation_index=0,
):
    """Supervisor-snap bottles onto shelf slot grid."""
    positions = cube_logic.shelf_world_positions(
        shelf_base,
        product_id=product_id,
        operation_index=operation_index,
    )
    upright = cube_logic.BOTTLE_UPRIGHT_ROTATION
    nodes = collect_cube_nodes(get_from_def, cube_defs)
    placed = []
    for i, (cube_def, node) in enumerate(nodes):
        slot = positions[i % len(positions)]
        if move_node_to(node, slot, upright):
            placed.append(cube_def)
    return placed


def remove_cubes(get_from_def, cube_defs):
    removed = []
    for cube_def in cube_defs:
        node = get_from_def(cube_def)
        if node is not None:
            remove_node(node)
            removed.append(cube_def)
    return removed
