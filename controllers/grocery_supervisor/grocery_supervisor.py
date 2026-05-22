from controller import Supervisor
import json
import os
import random

TIME_STEP = 32

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_DIR, "data")

PRODUCTS_FILE = os.path.join(DATA_DIR, "products.json")
INVENTORY_FILE = os.path.join(DATA_DIR, "inventory.json")
SHELF_MAPPING_FILE = os.path.join(DATA_DIR, "shelf_mapping.json")


class GrocerySupervisor:
    def __init__(self):
        self.robot = Supervisor()
        self.root = self.robot.getRoot()
        self.children = self.root.getField("children")

        self.products = self.load_json(PRODUCTS_FILE)
        self.inventory = self.load_json(INVENTORY_FILE)
        self.shelf_mapping = self.load_json(SHELF_MAPPING_FILE)

        self.product_count = 0
        self.spawn_timer = 0
        self.last_conveyor_log_second = -1
        self.active_products = []

        # Webots uses Z as the vertical axis.
        self.puma_pick_position = [8.35, 2.1, 0.42]
        self.puma_lift_position = [8.35, 2.1, 0.9]
        self.puma_carry_position = [7.8, 1.25, 0.78]
        self.conveyor_start_position = [7.55, 0.54, 0.28]
        self.detection_position = [2.25, 0.54, 0.28]
        self.conveyor_step = -0.012
        self.puma_pick_steps = 210
        self.sorter_pick_steps = 90
        self.sort_move_steps = 100
        self.restock_wait_steps = 80
        self.restock_move_steps = 120

        self.storage_positions = {
            "STORAGE_DAIRY": [0.6, 1.75, 0.85],
            "STORAGE_BAKERY": [0.6, 0.55, 0.85],
            "STORAGE_FRUIT": [0.6, -0.65, 0.85],
        }

        self.front_positions = {
            "FRONT_DAIRY": [-1.25, 1.75, 0.85],
            "FRONT_BAKERY": [-1.25, 0.55, 0.85],
            "FRONT_FRUIT": [-1.25, -0.65, 0.85],
        }

        self.sorter_node = self.robot.getFromDef("STORE_YOUBOT_SORTER")
        if self.sorter_node is None:
            self.sorter_node = self.robot.getFromDef("GROCERY_SORTER_AGENT")

        self.restocker_node = self.robot.getFromDef("STORE_YOUBOT_RESTOCKER")
        if self.restocker_node is None:
            self.restocker_node = self.robot.getFromDef("GROCERY_RESTOCKER_AGENT")

        print("[SYSTEM] Grocery store Supervisor started")
        print("[SYSTEM] Simulated detection, simplified grasping, JSON inventory")

    def load_json(self, path):
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)

    def save_inventory(self):
        with open(INVENTORY_FILE, "w", encoding="utf-8") as file:
            json.dump(self.inventory, file, indent=2)

    def print_inventory_summary(self):
        print("[INVENTORY SUMMARY]")
        for product_id, item in self.inventory.items():
            print(
                f"  {product_id}: "
                f"storage={item['storage_stock']} "
                f"front={item['front_stock']} "
                f"threshold={item['threshold']}"
            )

    def product_color(self, product):
        color = product.get("color", [0.8, 0.2, 0.2])
        return f"{color[0]} {color[1]} {color[2]}"

    def spawn_product(self):
        product = random.choice(self.products)
        product_id = product["product_id"]
        def_name = f"GROCERY_PRODUCT_{self.product_count}"

        node_string = f"""
        DEF {def_name} Solid {{
          translation {self.puma_pick_position[0]} {self.puma_pick_position[1]} {self.puma_pick_position[2]}
          children [
            Shape {{
              appearance PBRAppearance {{
                baseColor {self.product_color(product)}
                roughness 0.55
              }}
              geometry Box {{
                size 0.38 0.38 0.24
              }}
            }}
          ]
          name "{product_id}"
          model "grocery_product"
          boundingObject Box {{
            size 0.38 0.38 0.24
          }}
          physics Physics {{
            density -1
            mass 0.25
          }}
        }}
        """

        self.children.importMFNodeFromString(-1, node_string)
        product_node = self.robot.getFromDef(def_name)

        self.active_products.append({
            "node": product_node,
            "product_id": product_id,
            "state": "WAITING_FOR_PUMA",
            "timer": 0,
        })
        self.product_count += 1

        print(f"[SPAWN] Product {product_id} created at delivery zone")

    def move_agent(self, node, position):
        if node is not None:
            node.getField("translation").setSFVec3f([position[0], position[1], 0.11])

    def interpolate(self, start, end, progress):
        progress = max(0.0, min(1.0, progress))
        return [
            start[0] + (end[0] - start[0]) * progress,
            start[1] + (end[1] - start[1]) * progress,
            start[2] + (end[2] - start[2]) * progress,
        ]

    def set_product_position(self, product, position):
        product["node"].getField("translation").setSFVec3f(position)
        product["node"].resetPhysics()

    def move_products_on_conveyor(self):
        for product in self.active_products:
            if product["state"] == "WAITING_FOR_PUMA":
                product["timer"] += 1
                if product["timer"] == 1:
                    print(f"[PUMA PICK] PUMA picks {product['product_id']}")

                phase = product["timer"] / self.puma_pick_steps
                if phase < 0.35:
                    self.set_product_position(product, self.puma_pick_position)
                elif phase < 0.6:
                    progress = (phase - 0.35) / 0.25
                    self.set_product_position(
                        product,
                        self.interpolate(self.puma_pick_position, self.puma_lift_position, progress),
                    )
                elif phase < 0.85:
                    progress = (phase - 0.6) / 0.25
                    self.set_product_position(
                        product,
                        self.interpolate(self.puma_lift_position, self.puma_carry_position, progress),
                    )
                elif phase < 1.0:
                    progress = (phase - 0.85) / 0.15
                    self.set_product_position(
                        product,
                        self.interpolate(self.puma_carry_position, self.conveyor_start_position, progress),
                    )
                else:
                    self.set_product_position(product, self.conveyor_start_position)
                    product["state"] = "ON_CONVEYOR"
                    product["timer"] = 0
                    print(f"[PUMA PLACE] {product['product_id']} placed on conveyor")
                continue

            if product["state"] != "ON_CONVEYOR":
                if product["state"] == "WAITING_FOR_SORTER":
                    product["timer"] += 1
                    self.move_agent(self.sorter_node, self.detection_position)
                    if product["timer"] >= self.sorter_pick_steps:
                        product_id = product["product_id"]
                        storage_shelf = self.shelf_mapping[product_id]["storage_shelf"]
                        product["state"] = "SORTING_TO_STORAGE"
                        product["timer"] = 0
                        product["move_start"] = product["node"].getField("translation").getSFVec3f()
                        product["move_end"] = self.storage_positions[storage_shelf]
                        product["target_shelf"] = storage_shelf
                        print(f"[SORTING] {product_id} moving to {storage_shelf}")
                elif product["state"] == "SORTING_TO_STORAGE":
                    product["timer"] += 1
                    progress = product["timer"] / self.sort_move_steps
                    self.move_agent(self.sorter_node, product["move_end"])
                    self.set_product_position(
                        product,
                        self.interpolate(product["move_start"], product["move_end"], progress),
                    )
                    if progress >= 1.0:
                        self.finish_sort_product(product)
                elif product["state"] == "WAITING_FOR_RESTOCK":
                    product["timer"] += 1
                    product_id = product["product_id"]
                    front_shelf = self.shelf_mapping[product_id]["customer_shelf"]
                    self.move_agent(self.restocker_node, self.storage_positions[product["target_shelf"]])
                    if product["timer"] >= self.restock_wait_steps:
                        product["state"] = "RESTOCKING_TO_FRONT"
                        product["timer"] = 0
                        product["move_start"] = product["node"].getField("translation").getSFVec3f()
                        product["move_end"] = self.front_positions[front_shelf]
                        product["front_shelf"] = front_shelf
                        print(f"[RESTOCKING] {product_id} moving to {front_shelf}")
                elif product["state"] == "RESTOCKING_TO_FRONT":
                    product["timer"] += 1
                    progress = product["timer"] / self.restock_move_steps
                    self.move_agent(self.restocker_node, product["move_end"])
                    self.set_product_position(
                        product,
                        self.interpolate(product["move_start"], product["move_end"], progress),
                    )
                    if progress >= 1.0:
                        self.finish_restock_product(product)
                continue

            translation = product["node"].getField("translation")
            pos = translation.getSFVec3f()

            if pos[0] > self.detection_position[0]:
                pos[0] += self.conveyor_step
                translation.setSFVec3f(pos)
                current_second = int(self.robot.getTime())
                if current_second % 2 == 0 and current_second != self.last_conveyor_log_second:
                    print(f"[CONVEYOR] {product['product_id']} moving to detection zone")
                    self.last_conveyor_log_second = current_second
            else:
                product["state"] = "WAITING_FOR_SORTER"
                product["timer"] = 0
                print(f"[DETECTION] {product['product_id']} detected at detection zone")
                print(f"[SORT TASK] youBot sorter assigned to {product['product_id']}")

    def finish_sort_product(self, product):
        product_id = product["product_id"]
        storage_shelf = product["target_shelf"]

        product["state"] = "IN_STORAGE"

        self.inventory[product_id]["storage_stock"] += 1
        self.save_inventory()

        print(f"[SORTING] {product_id} moved to {storage_shelf}")
        self.print_inventory_line(product_id)
        self.print_inventory_summary()

        self.check_restocking_need(product_id)

    def check_restocking_need(self, product_id):
        item = self.inventory[product_id]

        if item["front_stock"] < item["threshold"] and item["storage_stock"] > 0:
            print(f"[RESTOCK TASK] youBot restocker assigned to {product_id}")
            for product in self.active_products:
                if product["product_id"] == product_id and product["state"] == "IN_STORAGE":
                    product["state"] = "WAITING_FOR_RESTOCK"
                    product["timer"] = 0
                    return

    def print_inventory_line(self, product_id):
        item = self.inventory[product_id]
        print(
            f"[INVENTORY] {product_id} "
            f"storage_stock={item['storage_stock']} "
            f"front_stock={item['front_stock']} "
            f"threshold={item['threshold']}"
        )

    def finish_restock_product(self, product):
        product_id = product["product_id"]
        front_shelf = product["front_shelf"]
        product["state"] = "ON_FRONT_SHELF"

        self.inventory[product_id]["storage_stock"] -= 1
        self.inventory[product_id]["front_stock"] += 1
        self.save_inventory()

        print(f"[RESTOCKING] {product_id} moved to {front_shelf}")
        self.print_inventory_line(product_id)
        self.print_inventory_summary()

    def run(self):
        while self.robot.step(TIME_STEP) != -1:
            self.spawn_timer += 1

            if self.spawn_timer > 240:
                self.spawn_product()
                self.spawn_timer = 0

            self.move_products_on_conveyor()


if __name__ == "__main__":
    GrocerySupervisor().run()
