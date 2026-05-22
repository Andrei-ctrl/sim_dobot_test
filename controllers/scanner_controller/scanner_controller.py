from controller import Supervisor
import json
import urllib.request
import os

TIME_STEP = 32

DASHBOARD_URL = "http://127.0.0.1:8000/update"
SEND_TO_DASHBOARD = True


class ScannerController:
    def __init__(self):
        self.robot = Supervisor()
        self.timestep = int(self.robot.getBasicTimeStep())
        self.project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.inventory_path = os.path.join(self.project_root, "data", "inventory.json")

        self.ds = self.robot.getDevice("distance sensor")
        if self.ds is None:
            print("[SCANNER ERROR] Distance sensor not found. Check sensor name.")
        else:
            self.ds.enable(self.timestep)
            print("[SCANNER] Distance sensor loaded.")

        self.self_node = self.robot.getSelf()
        self.scanner_position = self.self_node.getField("translation").getSFVec3f()

        self.scan_radius = 0.8
        self.scanned_products = set()

        self.product_database = {
            "BEER_BOTTLE": {
                "name": "Beer Bottle",
                "category": "Drinks",
                "target_shelf": "STORAGE_DRINKS"
            }
        }

        print("[SCANNER] Product scanner started.")
        print(f"[SCANNER] Scanner position: {self.scanner_position}")

    def post_json(self, payload):
        if not SEND_TO_DASHBOARD:
            return

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            DASHBOARD_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=0.2) as resp:
                resp.read()
        except Exception:
            pass

    def get_bottle_defs(self):
        bottle_defs = ["DEMO_BOTTLE"]

        for i in range(100):
            bottle_defs.append(f"DEMO_BOTTLE_{i}")

        return bottle_defs

    def distance_2d(self, pos_a, pos_b):
        dx = pos_a[0] - pos_b[0]
        dy = pos_a[1] - pos_b[1]
        return (dx * dx + dy * dy) ** 0.5

    def scan_products(self):
        ds_value = self.ds.getValue() if self.ds is not None else None

        for bottle_def in self.get_bottle_defs():
            bottle = self.robot.getFromDef(bottle_def)

            if bottle is None:
                continue

            if bottle_def in self.scanned_products:
                continue

            bottle_position = bottle.getField("translation").getSFVec3f()
            distance = self.distance_2d(bottle_position, self.scanner_position)

            if distance <= self.scan_radius:
                product_id = self.identify_product_id(bottle_def, bottle)

                product_info = self.product_database.get(product_id, {
                    "name": "Unknown product",
                    "category": "Unknown",
                    "target_shelf": "UNKNOWN_SHELF"
                })

                print("[SCANNER] Product entered scanner zone")
                print(f"[SCANNER] DEF: {bottle_def}")
                print(f"[SCANNER] Product ID: {product_id}")
                print(f"[SCANNER] Name: {product_info['name']}")
                print(f"[SCANNER] Category: {product_info['category']}")
                print(f"[SCANNER] Target shelf: {product_info['target_shelf']}")

                updated_inventory_item = self.update_inventory_after_scan(product_id)
                print(f"[SCANNER] Distance sensor value: {ds_value}")
                
                updated_inventory_item = self.update_inventory_after_scan(product_id)

                payload = {
                    "t": self.robot.getTime(),
                    "event": "product_scanned",
                    "def": bottle_def,
                    "product_id": product_id,
                    "name": product_info["name"],
                    "category": product_info["category"],
                    "target_shelf": product_info["target_shelf"],
                    "inventory": updated_inventory_item,
                    "ds": ds_value,
                }
                self.post_json(payload)
                self.scanned_products.add(bottle_def)

    def run(self):
        while self.robot.step(self.timestep) != -1:
            self.scan_products()
    
    def load_inventory(self):
        try:
            with open(self.inventory_path, "r", encoding="utf-8") as file:
                return json.load(file)
        except FileNotFoundError:
            print("[INVENTORY ERROR] inventory.json not found")
            return {}

    def save_inventory(self, inventory):
        with open(self.inventory_path, "w", encoding="utf-8") as file:
            json.dump(inventory, file, indent=2)

    def update_inventory_after_scan(self, product_id):
        inventory = self.load_inventory()

        if product_id not in inventory:
            print(f"[INVENTORY] Unknown product, cannot update: {product_id}")
            return None

        inventory[product_id]["storage_stock"] += 1

        item = inventory[product_id]

        print(
            f"[INVENTORY] {product_id}: "
            f"storage={item['storage_stock']}, "
            f"front={item['front_stock']}, "
            f"threshold={item['threshold']}"
        )

        if item["front_stock"] < item["threshold"] and item["storage_stock"] > 0:
            print(f"[RESTOCK TASK] Front shelf below threshold for {product_id}")
            print(f"[RESTOCK TASK] Assign youBot restocker to move item to {item['front_shelf']}")

            item["storage_stock"] -= 1
            item["front_stock"] += 1

            print(
                f"[RESTOCK COMPLETE] {product_id}: "
                f"storage={item['storage_stock']}, "
                f"front={item['front_stock']}"
            )

        self.save_inventory(inventory)
        return inventory[product_id]
    
    def identify_product_id(self, bottle_def, bottle):
        # Reliable rule for this prototype:
        # all DEMO_BOTTLE / DEMO_BOTTLE_0 / DEMO_BOTTLE_1 objects are beer bottles.
        if bottle_def == "DEMO_BOTTLE" or bottle_def.startswith("DEMO_BOTTLE_"):
            return "BEER_BOTTLE"

        # Fallback: try reading name
        name_field = bottle.getField("name")
        if name_field is not None:
            name_value = name_field.getSFString()

            # Normalize Webots auto-renamed values like "beer bottle(12)"
            if "beer bottle" in name_value.lower():
                return "BEER_BOTTLE"

            if name_value:
                return name_value

        return "UNKNOWN_PRODUCT"


if __name__ == "__main__":
    ScannerController().run()