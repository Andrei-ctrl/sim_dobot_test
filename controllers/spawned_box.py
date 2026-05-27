"""Spawn CardboardBox nodes with product name + unique id label."""

import json
import os
import re

import product_routing

DEFAULT_BOX_SIZE = (0.1, 0.1, 0.1)
DEFAULT_BOX_MASS = 0.1
DEFAULT_BOX_ROTATION = [4.66295e-18, -8.32667e-18, 1, 3.13905]
COUNTER_FILENAME = "spawn_box_counter.json"


def _data_dir(project_root):
    return os.path.join(project_root, "data")


def _counter_path(project_root):
    return os.path.join(_data_dir(project_root), COUNTER_FILENAME)


def allocate_box_uid(project_root):
    """Persistent unique label id (BOX-000001, BOX-000002, ...)."""
    path = _counter_path(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
            counter = int(payload.get("next", 1))
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
        counter = 1
    uid = f"BOX-{counter:06d}"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"next": counter + 1}, handle, indent=2)
    return uid


def product_label(product_id):
    product_id = (product_id or "").strip() or "UNASSIGNED"
    try:
        route = product_routing.route_for_product_id(product_id)
        return str(route.get("product_id") or product_id)
    except (KeyError, TypeError):
        return product_id


def box_scene_name(product_id, box_def, box_uid):
    safe_product = re.sub(r"[^A-Za-z0-9_]+", "_", product_label(product_id))
    return f"{safe_product}_{box_uid}"


def _vrml_string(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def build_cardboard_box_vrml(
    box_def,
    position,
    rotation,
    *,
    product_id,
    box_uid,
    size=DEFAULT_BOX_SIZE,
    mass=DEFAULT_BOX_MASS,
):
    sx, sy, sz = size
    rx, ry, rz, ra = rotation
    name = _vrml_string(box_scene_name(product_id, box_def, box_uid))
    return (
        f"DEF {box_def} CardboardBox {{\n"
        f"  translation {position[0]} {position[1]} {position[2]}\n"
        f"  rotation {rx} {ry} {rz} {ra}\n"
        f'  name "{name}"\n'
        f"  size {sx} {sy} {sz}\n"
        f"  mass {mass}\n"
        f"}}"
    )


def build_label_vrml(product_id, box_uid, box_size_z=DEFAULT_BOX_SIZE[2]):
    line1 = _vrml_string(product_label(product_id))
    line2 = _vrml_string(box_uid)
    font_size = min(0.028, box_size_z * 0.24)
    z = box_size_z / 2 + 0.002
    max_width = box_size_z * 0.92
    return (
        f"Pose {{\n"
        f"  translation 0 0 {z}\n"
        f"  rotation 1 0 0 -1.57079632679\n"
        f"  children [\n"
        f"    Shape {{\n"
        f"      appearance Appearance {{\n"
        f"        material Material {{\n"
        f"          emissiveColor 0.08 0.08 0.08\n"
        f"          diffuseColor 0.12 0.12 0.12\n"
        f"        }}\n"
        f"      }}\n"
        f"      geometry Text {{\n"
        f"        fontSize {font_size}\n"
        f'        string [\n'
        f'          "{line1}"\n'
        f'          "{line2}"\n'
        f"        ]\n"
        f"        maxWidth {max_width}\n"
        f"      }}\n"
        f"    }}\n"
        f"  ]\n"
        f"}}"
    )


def attach_product_label(get_from_def, box_def, product_id, box_uid, box_size_z=DEFAULT_BOX_SIZE[2]):
    node = get_from_def(box_def)
    if node is None:
        return False
    children = node.getField("children")
    if children is None:
        return False
    children.importMFNodeFromString(
        -1,
        build_label_vrml(product_id, box_uid, box_size_z=box_size_z),
    )
    return True


def spawn_labeled_box(
    children_field,
    get_from_def,
    project_root,
    box_def,
    position,
    rotation,
    product_id,
    *,
    size=DEFAULT_BOX_SIZE,
    mass=DEFAULT_BOX_MASS,
    box_uid=None,
):
    """
    Spawn a labeled cardboard box. Returns (box_def, box_uid) or (None, None).
    """
    box_uid = box_uid or allocate_box_uid(project_root)
    node_string = build_cardboard_box_vrml(
        box_def,
        position,
        rotation,
        product_id=product_id,
        box_uid=box_uid,
        size=size,
        mass=mass,
    )
    children_field.importMFNodeFromString(-1, node_string)
    if get_from_def(box_def) is None:
        return None, None
    attach_product_label(
        get_from_def,
        box_def,
        product_id,
        box_uid,
        box_size_z=size[2],
    )
    return box_def, box_uid
