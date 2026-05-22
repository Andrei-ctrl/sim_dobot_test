# Autonomous Grocery Store Prototype

This project is a Webots-based prototype of an autonomous grocery store logistics flow. The prototype demonstrates how a robotic unloading arm, conveyor, product scanner, inventory logic, dashboard server, and restocking decision logic can work together as one information-system scenario.

The active world file is:

```text
worlds/Factory_environment_copy_new.wbt
```

## Current Prototype Status

The current version demonstrates the following end-to-end flow:

```text
Beer bottle appears on pallet
→ IPR robotic arm grips and moves the bottle
→ bottle is placed on / moved toward the conveyor
→ product scanner detects the bottle
→ product is identified as BEER_BOTTLE
→ dashboard receives scanner data
→ inventory is updated
→ restocking threshold is checked
→ restocking task is created for the youBot restocker
```

The console confirms that the main pipeline is working:

```text
[SCANNER] Product ID: BEER_BOTTLE
[SCANNER] Name: Beer Bottle
[SCANNER] Category: Drinks
[SCANNER] Target shelf: STORAGE_DRINKS
[INVENTORY] BEER_BOTTLE: storage=1, front=1, threshold=2
[RESTOCK TASK] Front shelf below threshold for BEER_BOTTLE
[RESTOCK TASK] Assign youBot restocker to move item to FRONT_DRINKS
[RESTOCK COMPLETE] BEER_BOTTLE: storage=0, front=2
```

## Project Structure

Expected project structure:

```text
sim_dobot_test/
├── worlds/
│   └── Factory_environment_copy_new.wbt
│
├── controllers/
│   ├── ipr_pick_demo/
│   │   └── ipr_pick_demo.py
│   │
│   ├── scanner_controller/
│   │   └── scanner_controller.py
│   │
│   ├── youbot_sorter_demo/
│   │   └── youbot_sorter_demo.py
│   │
│   └── youbot_restocker_demo/
│       └── youbot_restocker_demo.py
│
├── data/
│   └── inventory.json
│
└── dashboard_server.py
```

## Main Components

### 1. Webots World

File:

```text
worlds/Factory_environment_copy_new.wbt
```

This world contains the factory/grocery-store simulation environment, including:

- IPR robotic arm for unloading products from the pallet
- beer bottle product object
- pallet area
- conveyor belts
- scanner robot with a distance sensor
- youBot sorter
- youBot restocker
- shelves and store environment objects
- prototype conveyor/detection zones

The world must include an importable BeerBottle PROTO because the controller dynamically spawns bottles:

```vrml
IMPORTABLE EXTERNPROTO "https://raw.githubusercontent.com/cyberbotics/webots/R2025a/projects/objects/drinks/protos/BeerBottle.proto"
```

### 2. IPR Robotic Arm Controller

Controller:

```text
controllers/ipr_pick_demo/ipr_pick_demo.py
```

Purpose:

- controls the `IprHd6ms180` robotic arm
- opens and closes the gripper
- uses a sequence of predefined poses
- picks the beer bottle from the pallet
- moves it toward the conveyor
- spawns the next beer bottle after the movement cycle

The IPR arm uses the following motor names:

```text
base
upperarm
forearm
wrist
rotational_wrist
gripper::left
gripper::right
```

The pose format is:

```python
("pose_name", [base, upperarm, forearm, wrist, rotational_wrist], gripper_value, duration)
```

Example:

```python
("pre_pick", [0.0, -2, 1, -1, 0.0], 1.0, 160)
```

Meaning:

```text
base = base rotation
upperarm = main arm movement
forearm = elbow movement
wrist = wrist bend
rotational_wrist = gripper rotation
gripper_value = 1.0 open, 0.0 closed
duration = number of simulation steps
```

### 3. Bottle Spawner

The bottle spawner is implemented inside:

```text
controllers/ipr_pick_demo/ipr_pick_demo.py
```

It uses the Webots Supervisor API:

```python
self.children.importMFNodeFromString(-1, node_string)
```

The spawned product is a real `BeerBottle` PROTO object:

```vrml
DEF DEMO_BOTTLE_0 BeerBottle {
  translation ...
  rotation ...
  name "BEER_BOTTLE"
  mass 0.1
}
```

Important implementation note:

`BeerBottle` does not support `customData`, so product identification is handled using:

```vrml
name "BEER_BOTTLE"
```

or by detecting DEF names such as:

```text
DEMO_BOTTLE
DEMO_BOTTLE_0
DEMO_BOTTLE_1
...
```

### 4. Product Scanner

Controller:

```text
controllers/scanner_controller/scanner_controller.py
```

Purpose:

- loads the Webots distance sensor
- detects when a product enters the scanner zone
- identifies product type
- sends scan data to the dashboard server
- updates inventory
- triggers restocking decision logic

The scanner currently identifies the beer bottle as:

```text
Product ID: BEER_BOTTLE
Name: Beer Bottle
Category: Drinks
Target shelf: STORAGE_DRINKS
```

The scanner uses a product database similar to:

```python
self.product_database = {
    "BEER_BOTTLE": {
        "name": "Beer Bottle",
        "category": "Drinks",
        "target_shelf": "STORAGE_DRINKS"
    }
}
```

### 5. Inventory System

Inventory file:

```text
data/inventory.json
```

Example structure:

```json
{
  "BEER_BOTTLE": {
    "name": "Beer Bottle",
    "category": "Drinks",
    "storage_stock": 0,
    "front_stock": 2,
    "threshold": 2,
    "storage_shelf": "STORAGE_DRINKS",
    "front_shelf": "FRONT_DRINKS"
  }
}
```

The scanner updates the inventory after product scanning.

Current logic:

```text
If BEER_BOTTLE is scanned:
    storage_stock increases
    if front_stock < threshold:
        create restocking task
        move one item from storage_stock to front_stock
```

Example console output:

```text
[INVENTORY] BEER_BOTTLE: storage=1, front=1, threshold=2
[RESTOCK TASK] Front shelf below threshold for BEER_BOTTLE
[RESTOCK TASK] Assign youBot restocker to move item to FRONT_DRINKS
[RESTOCK COMPLETE] BEER_BOTTLE: storage=0, front=2
```

### 6. Dashboard Server

File:

```text
dashboard_server.py
```

Purpose:

- runs a local HTTP server
- receives scanner updates from Webots controllers
- displays latest scanner/inventory data in the browser

Run it before starting the Webots simulation:

```bash
python dashboard_server.py
```

Open the dashboard at:

```text
http://127.0.0.1:8000
```

Do not open `/update` directly in the browser. That endpoint is for POST requests from the scanner controller.

### 7. youBot Controllers

Controllers:

```text
controllers/youbot_sorter_demo/youbot_sorter_demo.py
controllers/youbot_restocker_demo/youbot_restocker_demo.py
```

Current role:

- safe idle controllers
- keep the youBots active in the simulation
- print startup messages
- planned to be connected to restocking/sorting task logic later

Current console output:

```text
[YOUBOT SORTER] Safe idle controller started
[YOUBOT RESTOCKER] Safe idle controller started
```

## How to Run

1. Start the dashboard server:

```bash
cd C:\Users\andru\Desktop\sim_dobot_test
python dashboard_server.py
```

2. Open Webots.

3. Open the world:

```text
worlds/Factory_environment_copy_new.wbt
```

4. Run/reset the simulation.

5. Check the Webots console for:

```text
[IPR] Pick demo initialized
[SCANNER] Product scanner started.
[SCANNER] Product ID: BEER_BOTTLE
[INVENTORY] ...
[RESTOCK TASK] ...
```

6. Open the dashboard:

```text
http://127.0.0.1:8000
```

## Known Warnings

The simulation currently shows repeated Webots warnings such as:

```text
too low requested position: -3.65949e-11 < 0
too low requested position: -1.26847e-11 < 0
```

These are very small numerical values close to zero. They mainly come from youBot finger motors or small joint limit rounding errors. They do not currently prevent the prototype from running.

There may also be a warning:

```text
Robot "test_controller_sensor": The remote control library has not been found.
```

This should be cleaned later by removing the old unused `test_controller_sensor` node or making sure only the active `PRODUCT_SCANNER` node uses the scanner controller.

## What Works

The following features currently work:

- Webots world loads.
- IPR robotic arm controller starts.
- IPR motors and grippers are detected.
- IPR pose sequence runs.
- Bottle spawner works.
- BeerBottle objects can be spawned dynamically.
- Scanner controller starts.
- Distance sensor loads.
- Product is detected.
- Product is identified as `BEER_BOTTLE`.
- Dashboard server receives scanner data.
- Inventory file is updated.
- Restocking threshold logic works.
- Restocking task is printed for the youBot restocker.

## What Is Left To Do

### High Priority

1. Clean the scanner placement.

   The scanner currently still appears to report an old position in some logs:

   ```text
   Scanner position: [-0.01, 1.09, 0.24]
   ```

   It should be moved near the actual conveyor path where the bottle passes.

2. Remove or rename the old `test_controller_sensor` node.

   The active scanner should have a clear DEF/name such as:

   ```vrml
   DEF PRODUCT_SCANNER Robot {
     name "product scanner"
     controller "scanner_controller"
     supervisor TRUE
   }
   ```

3. Make youBot restocker react visually.

   Current restocking is logical only. The next implementation step is to make the youBot restocker move or animate when a restocking task is created.

4. Add a task queue.

   Create a file such as:

   ```text
   data/tasks.json
   ```

   Example task:

   ```json
   {
     "task_id": 1,
     "type": "RESTOCK",
     "product_id": "BEER_BOTTLE",
     "from": "STORAGE_DRINKS",
     "to": "FRONT_DRINKS",
     "assigned_robot": "STORE_YOUBOT_RESTOCKER",
     "status": "pending"
   }
   ```

### Medium Priority

5. Add more product types.

   Example:

   ```text
   MILK_BOTTLE
   CEREAL_BOX
   WATER_BOTTLE
   ```

   Each should have its own category, storage shelf, front shelf, and threshold.

6. Improve the dashboard.

   The dashboard should show:

   - latest scanned product
   - inventory table
   - pending restocking tasks
   - robot status
   - scanner status

7. Add visual labels in Webots.

   Add signs or colored zones for:

   - pallet pickup area
   - scanner zone
   - conveyor
   - storage shelf
   - front shelf

8. Reduce console warnings.

   Clamp tiny negative values in the youBot controllers and remove unused test nodes.

### Optional / Advanced

9. Replace hardcoded pose sequence with task states.

   Instead of only cycling through poses, define robot states:

   ```text
   WAITING_FOR_PRODUCT
   PICKING
   MOVING_TO_CONVEYOR
   RELEASING
   RETURNING_HOME
   ```

10. Use Webots Emitter/Receiver for task communication.

   Scanner can emit a task message to the youBot restocker instead of only writing a JSON file.

11. Add better physical product handling.

   The current BeerBottle physics is acceptable for prototype demonstration, but gripping can still be sensitive. It can be improved by:

   - tuning gripper values
   - lowering arm velocity
   - simplifying product bounding objects
   - adding stable pickup fixtures

12. Add logging.

   Create logs such as:

   ```text
   data/events.log
   ```

   Each scan, inventory update, and robot action can be recorded.

## Prototype Explanation

This prototype demonstrates a simplified autonomous grocery-store process. The IPR robot unloads beer bottles from a pallet and places them onto a conveyor. A scanner identifies the product using its object name or DEF pattern and maps it to a product database. The scanner then updates a JSON-based inventory file and checks whether the front shelf stock is below the configured threshold. If restocking is needed, the system creates a logical restocking task for the youBot restocker.

The current implementation focuses on showing the integration between robotics simulation and information-system logic: product identification, inventory updates, stock threshold monitoring, and task assignment.

## Current Limitations

- Product recognition is simulated using object names/DEF names, not computer vision.
- Inventory is stored in a local JSON file, not a real database.
- Restocking task execution is currently logical/console-based.
- youBots do not yet physically move products between shelves.
- Some object positions and scanner coordinates are still hardcoded.
- The simulation still contains some old test nodes and warnings that should be cleaned before final submission.

## Recommended Next Milestone

The next milestone should be:

```text
Scanner detects BEER_BOTTLE
→ inventory creates RESTOCK task
→ task is written to data/tasks.json
→ youBot restocker reads task
→ youBot performs a simple visible restocking animation
→ dashboard shows task status changing from pending to completed
```

This would make the prototype clearly demonstrate the full process:

```text
delivery unloading
→ product identification
→ inventory update
→ restocking decision
→ robot task assignment
→ restocking execution
```
