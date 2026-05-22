from controller import Supervisor
import json
import os

TIME_STEP = 32

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_DIR, "data")

PRODUCTS_FILE = os.path.join(DATA_DIR, "products.json")
INVENTORY_FILE = os.path.join(DATA_DIR, "inventory.json")
SHELF_MAPPING_FILE = os.path.join(DATA_DIR, "shelf_mapping.json")


class MinimalStoreSupervisor:
    def __init__(self):
        self.robot = Supervisor()
        self.children = self.robot.getRoot().getField("children")

        self.products = self.load_json(PRODUCTS_FILE)
        self.inventory = self.load_json(INVENTORY_FILE)
        self.shelf_mapping = self.load_json(SHELF_MAPPING_FILE)

        self.delivery_arm = self.robot.getFromDef("DELIVERY_ARM")
        self.sorter = self.robot.getFromDef("SORTER_ROBOT")
        self.restocker = self.robot.getFromDef("RESTOCKER_ROBOT")

        self.product_id = "MILK_001"
        self.reset_demo_inventory()
        self.product_node = None

        self.delivery = [-3.2, 0.75, 0.34]
        self.arm_home = [-3.35, -0.75, 0.55]
        self.arm_above_product = [-3.2, 0.75, 0.92]
        self.arm_at_product = [-3.2, 0.75, 0.55]
        self.arm_lift = [-3.2, 0.75, 0.92]
        self.arm_above_belt = [-2.05, 0.0, 0.92]
        self.arm_at_belt = [-2.05, 0.0, 0.55]

        self.belt_start = [-2.05, 0.0, 0.34]
        self.detection = [1.35, 0.0, 0.34]
        self.storage = [2.7, 1.05, 0.86]
        self.front = [4.0, 1.05, 0.86]

        self.sorter_home = [1.35, -0.95, 0.16]
        self.sorter_pick = [1.35, -0.42, 0.16]
        self.sorter_storage = [2.7, 0.65, 0.16]

        self.restocker_home = [3.25, -0.95, 0.16]
        self.restocker_storage = [2.7, 0.65, 0.16]
        self.restocker_front = [4.0, 0.65, 0.16]

        self.state = "SPAWN"
        self.timer = 0
        self.state_started = True

        print("[SYSTEM] Clean one-product grocery demo started")
        print("[SYSTEM] Product -> delivery arm -> conveyor -> scanner -> sorter -> stock -> restocker -> shelf")

    def load_json(self, path):
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)

    def save_inventory(self):
        with open(INVENTORY_FILE, "w", encoding="utf-8") as file:
            json.dump(self.inventory, file, indent=2)

    def reset_demo_inventory(self):
        self.inventory[self.product_id] = {
            "storage_stock": 0,
            "front_stock": 0,
            "threshold": 1,
        }
        self.save_inventory()

    def product_data(self):
        for product in self.products:
            if product["product_id"] == self.product_id:
                return product
        return {"product_id": self.product_id, "name": "Milk", "color": [0.82, 0.92, 1.0]}

    def color_string(self, product):
        color = product.get("color", [0.82, 0.92, 1.0])
        return f"{color[0]} {color[1]} {color[2]}"

    def print_inventory(self):
        item = self.inventory[self.product_id]
        print(
            f"[INVENTORY] {self.product_id} "
            f"storage_stock={item['storage_stock']} "
            f"front_stock={item['front_stock']} "
            f"threshold={item['threshold']}"
        )

    def spawn_product(self):
        product = self.product_data()
        node = f"""
        DEF ONLY_PRODUCT Solid {{
          translation {self.delivery[0]} {self.delivery[1]} {self.delivery[2]}
          children [
            Shape {{
              appearance PBRAppearance {{
                baseColor {self.color_string(product)}
                roughness 0.38
              }}
              geometry Box {{
                size 0.34 0.28 0.38
              }}
            }}
            Pose {{
              translation 0 -0.145 0.02
              children [
                Shape {{
                  appearance PBRAppearance {{
                    baseColor 0.18 0.48 0.95
                    roughness 0.45
                  }}
                  geometry Box {{
                    size 0.24 0.012 0.18
                  }}
                }}
              ]
            }}
            Pose {{
              translation 0 -0.152 0.04
              children [
                Shape {{
                  appearance PBRAppearance {{
                    baseColor 1 1 1
                    roughness 0.35
                  }}
                  geometry Box {{
                    size 0.18 0.01 0.035
                  }}
                }}
              ]
            }}
            Pose {{
              translation 0 -0.153 -0.025
              children [
                Shape {{
                  appearance PBRAppearance {{
                    baseColor 1 1 1
                    roughness 0.35
                  }}
                  geometry Box {{
                    size 0.12 0.01 0.025
                  }}
                }}
              ]
            }}
            Pose {{
              translation 0 0 0.23
              children [
                Shape {{
                  appearance PBRAppearance {{
                    baseColor 0.94 0.98 1
                    roughness 0.38
                  }}
                  geometry Box {{
                    size 0.3 0.24 0.08
                  }}
                }}
              ]
            }}
            Pose {{
              translation 0.08 -0.03 0.31
              children [
                Shape {{
                  appearance PBRAppearance {{
                    baseColor 0.08 0.24 0.75
                    roughness 0.3
                  }}
                  geometry Cylinder {{
                    height 0.06
                    radius 0.045
                  }}
                }}
              ]
            }}
            Pose {{
              translation -0.18 0 0.0
              children [
                Shape {{
                  appearance PBRAppearance {{
                    baseColor 0.08 0.32 0.75
                    roughness 0.45
                  }}
                  geometry Box {{
                    size 0.012 0.22 0.22
                  }}
                }}
              ]
            }}
          ]
          name "{self.product_id}"
          model "single_demo_product"
          boundingObject Box {{
            size 0.34 0.28 0.5
          }}
          physics Physics {{
            density -1
            mass 0.25
          }}
        }}
        """
        self.children.importMFNodeFromString(-1, node)
        self.product_node = self.robot.getFromDef("ONLY_PRODUCT")
        print(f"[SPAWN] One product created: {self.product_id}")

    def lerp(self, start, end, progress):
        progress = max(0.0, min(1.0, progress))
        return [
            start[0] + (end[0] - start[0]) * progress,
            start[1] + (end[1] - start[1]) * progress,
            start[2] + (end[2] - start[2]) * progress,
        ]

    def set_node_position(self, node, position):
        if node is None:
            return
        node.getField("translation").setSFVec3f(position)
        node.resetPhysics()

    def set_robot_position(self, node, position):
        if node is None:
            return
        node.getField("translation").setSFVec3f(position)

    def set_arm_position(self, position):
        self.set_robot_position(self.delivery_arm, position)

    def carry_with_arm(self, arm_position):
        self.set_arm_position(arm_position)
        product_position = [arm_position[0], arm_position[1], arm_position[2] - 0.21]
        self.set_node_position(self.product_node, product_position)

    def change_state(self, state):
        self.state = state
        self.timer = 0
        self.state_started = True

    def run_state(self):
        if self.state == "SPAWN":
            self.spawn_product()
            self.set_arm_position(self.arm_home)
            self.set_robot_position(self.sorter, self.sorter_home)
            self.set_robot_position(self.restocker, self.restocker_home)
            self.change_state("ARM_MOVE_TO_PRODUCT")
            return

        if self.state == "ARM_MOVE_TO_PRODUCT":
            if self.state_started:
                print(f"[ARM] Delivery arm moves to {self.product_id}")
                self.state_started = False
            self.set_arm_position(self.lerp(self.arm_home, self.arm_above_product, self.timer / 100))
            self.set_node_position(self.product_node, self.delivery)
            if self.timer > 100:
                self.change_state("ARM_LOWER")

        elif self.state == "ARM_LOWER":
            self.set_arm_position(self.lerp(self.arm_above_product, self.arm_at_product, self.timer / 70))
            self.set_node_position(self.product_node, self.delivery)
            if self.timer > 70:
                self.change_state("ARM_GRIP")

        elif self.state == "ARM_GRIP":
            if self.state_started:
                print(f"[ARM PICK] Delivery arm grips {self.product_id}")
                self.state_started = False
            self.carry_with_arm(self.arm_at_product)
            if self.timer > 55:
                self.change_state("ARM_LIFT")

        elif self.state == "ARM_LIFT":
            self.carry_with_arm(self.lerp(self.arm_at_product, self.arm_lift, self.timer / 80))
            if self.timer > 80:
                self.change_state("ARM_CARRY_TO_BELT")

        elif self.state == "ARM_CARRY_TO_BELT":
            self.carry_with_arm(self.lerp(self.arm_lift, self.arm_above_belt, self.timer / 120))
            if self.timer > 120:
                self.change_state("ARM_LOWER_TO_BELT")

        elif self.state == "ARM_LOWER_TO_BELT":
            self.carry_with_arm(self.lerp(self.arm_above_belt, self.arm_at_belt, self.timer / 80))
            if self.timer > 80:
                self.change_state("ARM_RELEASE")

        elif self.state == "ARM_RELEASE":
            if self.state_started:
                print(f"[ARM PLACE] {self.product_id} placed on conveyor")
                self.state_started = False
            self.set_arm_position(self.arm_at_belt)
            self.set_node_position(self.product_node, self.belt_start)
            if self.timer > 60:
                self.change_state("CONVEYOR")

        elif self.state == "CONVEYOR":
            if self.state_started:
                print(f"[CONVEYOR] {self.product_id} moving to scanner")
                self.state_started = False
            self.set_arm_position(self.lerp(self.arm_at_belt, self.arm_home, self.timer / 140))
            self.set_node_position(self.product_node, self.lerp(self.belt_start, self.detection, self.timer / 190))
            if self.timer > 190:
                print(f"[SCANNER] Detected product_id={self.product_id}")
                self.change_state("SORTER_MOVE_TO_PRODUCT")

        elif self.state == "SORTER_MOVE_TO_PRODUCT":
            if self.state_started:
                print(f"[SORT TASK] Sorter robot receives {self.product_id}")
                self.state_started = False
            self.set_robot_position(self.sorter, self.lerp(self.sorter_home, self.sorter_pick, self.timer / 75))
            self.set_node_position(self.product_node, self.detection)
            if self.timer > 75:
                self.change_state("SORTER_CARRY_TO_STOCK")

        elif self.state == "SORTER_CARRY_TO_STOCK":
            self.set_robot_position(self.sorter, self.lerp(self.sorter_pick, self.sorter_storage, self.timer / 130))
            self.set_node_position(self.product_node, self.lerp(self.detection, self.storage, self.timer / 130))
            if self.timer > 130:
                self.inventory[self.product_id]["storage_stock"] += 1
                self.save_inventory()
                print(f"[SORTING] {self.product_id} placed in STORAGE_MILK")
                self.print_inventory()
                self.change_state("SHELF_CHECK")

        elif self.state == "SHELF_CHECK":
            if self.state_started:
                print("[SHELF CHECK] Restocker robot checks customer shelf")
                self.state_started = False
            if self.timer > 70:
                item = self.inventory[self.product_id]
                if item["front_stock"] < item["threshold"] and item["storage_stock"] > 0:
                    print(f"[RESTOCK TASK] {self.product_id} missing on customer shelf")
                    self.change_state("RESTOCKER_MOVE_TO_STOCK")
                else:
                    self.change_state("COMPLETE")

        elif self.state == "RESTOCKER_MOVE_TO_STOCK":
            self.set_robot_position(self.restocker, self.lerp(self.restocker_home, self.restocker_storage, self.timer / 90))
            self.set_node_position(self.product_node, self.storage)
            if self.timer > 90:
                self.change_state("RESTOCKER_CARRY_TO_FRONT")

        elif self.state == "RESTOCKER_CARRY_TO_FRONT":
            self.set_robot_position(self.restocker, self.lerp(self.restocker_storage, self.restocker_front, self.timer / 130))
            self.set_node_position(self.product_node, self.lerp(self.storage, self.front, self.timer / 130))
            if self.timer > 130:
                self.inventory[self.product_id]["storage_stock"] -= 1
                self.inventory[self.product_id]["front_stock"] += 1
                self.save_inventory()
                print(f"[RESTOCKING] {self.product_id} placed on FRONT_MILK")
                self.print_inventory()
                self.change_state("COMPLETE")

        elif self.state == "COMPLETE":
            if self.state_started:
                print("[COMPLETE] Autonomous one-product demo finished")
                self.state_started = False

        self.timer += 1

    def run(self):
        while self.robot.step(TIME_STEP) != -1:
            self.run_state()


if __name__ == "__main__":
    MinimalStoreSupervisor().run()
