"""Product / stock-pallet / shelf routing registry (Webots-independent)."""

DEFAULT_PALLET_DEF = "BEER_STOCK"

STOCK_PALLETS = {
    "BEER_STOCK": {
        "def": "BEER_STOCK",
        "product_id": "BEER_BOTTLE",
        "display_name": "BEER STOCK",
        "translation": [-10.5, 1.83, -0.12],
        "approach_xy": [-11.0, 1.83],
        "shelf_name": "Beer section",
        "shelf_base": [-11.5, 2.7, 0.0],
        "shelf_approach_xy": [-10.0, 2.7],
    },
    "CHIPS_STOCK": {
        "def": "CHIPS_STOCK",
        "product_id": "CHIPS",
        "display_name": "CHIPS STOCK",
        "translation": [-10.5, 3.5, -0.09],
        "approach_xy": [-11.0, 3.5],
        "shelf_name": "Chips section",
        "shelf_base": [-11.5, 4.35, 0.0],
        "shelf_approach_xy": [-10.0, 4.35],
    },
    "CHEESE_STOCK": {
        "def": "CHEESE_STOCK",
        "product_id": "CHEESE",
        "display_name": "CHEESE STOCK",
        "translation": [-10.52, 5.27, -0.09],
        "approach_xy": [-11.0, 5.27],
        "shelf_name": "Cheese section",
        "shelf_base": [-11.5, 6.1, 0.0],
        "shelf_approach_xy": [-10.0, 6.1],
    },
    "MILK_STOCK": {
        "def": "MILK_STOCK",
        "product_id": "MILK",
        "display_name": "MILK STOCK",
        "translation": [-10.51, 7.14, -0.08],
        "approach_xy": [-11.0, 7.14],
        "shelf_name": "Milk section",
        "shelf_base": [-11.5, 7.9, 0.0],
        "shelf_approach_xy": [-10.0, 7.9],
    },
}

PALLET_ZONE_RADIUS = 0.45
BOX_DEF_PREFIX = "SPAWNED_BOX_"


def route_for_box_def(box_def):
    """All boxes route to BEER for now; extend here for multi-product."""
    return dict(STOCK_PALLETS[DEFAULT_PALLET_DEF])


def route_for_pallet_def(pallet_def):
    entry = STOCK_PALLETS.get(pallet_def)
    if entry is None:
        return dict(STOCK_PALLETS[DEFAULT_PALLET_DEF])
    return dict(entry)


def route_for_product_id(product_id):
    for entry in STOCK_PALLETS.values():
        if entry["product_id"] == product_id:
            return dict(entry)
    return dict(STOCK_PALLETS[DEFAULT_PALLET_DEF])


def pallet_approach_xy(pallet_def):
    return list(route_for_pallet_def(pallet_def)["approach_xy"])


def shelf_base_for_product(product_id):
    return list(route_for_product_id(product_id)["shelf_base"])


def shelf_approach_xy(product_id):
    return list(route_for_product_id(product_id)["shelf_approach_xy"])


def pallet_translation(pallet_def):
    return list(route_for_pallet_def(pallet_def)["translation"])


def box_on_pallet(box_pos, pallet_def, radius=None):
    radius = PALLET_ZONE_RADIUS if radius is None else radius
    px, py, _ = pallet_translation(pallet_def)
    dx = box_pos[0] - px
    dy = box_pos[1] - py
    return (dx * dx + dy * dy) ** 0.5 <= radius


def iter_pallet_defs():
    return tuple(STOCK_PALLETS.keys())


def pallet_obstacle_centers():
    """World XY + radius for static pallet collision checks."""
    radius = PALLET_ZONE_RADIUS + 0.25
    return [
        (entry["translation"][0], entry["translation"][1], radius)
        for entry in STOCK_PALLETS.values()
    ]
