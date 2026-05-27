# Autonomous Factory / Grocery Simulation

Webots R2025a simulation of a small factory logistics pipeline: an IPR arm feeds cardboard boxes onto a conveyor, an upstream scanner tracks them, a KUKA youBot restocker picks boxes and delivers them to a pallet, and optional dashboard/inventory hooks record scan events.

**Primary world:** `worlds/Factory_environment_copy_new.wbt`

## Pipeline overview

```
IPR (ipr_pick_demo)
  └─ waits for upstream scanner trigger → spawns SPAWNED_BOX_* at IPR station
  └─ picks box → places on conveyor_cardbox

Conveyor belt
  └─ box travels toward youBot pick slot

Scanner (scanner_controller)
  └─ detects box in upstream zone → routes to BEER_STOCK (all boxes for now)
  └─ writes data/box_routing.json + data/spawn_signal.json

youBot restocker (youbot_restocker_demo)
  └─ waits at calibrated home pose beside conveyor
  └─ wheel-aligns to box center + IR sensor confirm → picks with gripper
  └─ drives to BEER_STOCK → places box → returns home (wheel drive + snap)

stock_monitoring (stock_monitoring supervisor)
  └─ detects box on stock pallet → writes data/sort_signal.json

youBot sorter (youbot_sorter_demo)
  └─ drives to BEER_STOCK → unpacks box → 3 BeerBottle on platform
  └─ drives to Beer section shelf → places bottles → updates inventory
```

## Quick start

### 1. Python environment

Use Python 3 with Webots’ controller packages available (or project venv):

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt   # if present; Webots supplies controller module
```

### 2. Optional dashboard

```bash
python dashboard_server.py
```

Runs at `http://127.0.0.1:8000`. The scanner POSTs scan events to `/update` when `SEND_TO_DASHBOARD` is enabled in `scanner_controller.py`.

### 3. Open Webots

Open `worlds/Factory_environment_copy_new.wbt` and run the simulation.

Controllers are assigned in the world file:

| Robot / node | Controller |
|---|---|
| `STORE_YOUBOT_RESTOCKER` (YoubotBoxGrip) | `youbot_restocker_demo` |
| `test_controller_sensor` | `scanner_controller` |
| `stock_monitoring` | `stock_monitoring` |
| `BEER STOCK` | `beer_pallet_spawner` (test: spawn box on pallet) |
| IPR (`IprHd6ms180`) | `ipr_pick_demo` |
| `youBot sorter` | `youbot_sorter_demo` |
| Conveyor belts | `conveyor_belt` (Webots built-in) |

## Project structure

```
sim_dobot_test/
├── README.md
├── dashboard_server.py          # optional HTTP dashboard for scanner events
├── worlds/
│   └── Factory_environment_copy_new.wbt   # main factory world
├── protos/
│   ├── YoubotBoxGrip.proto      # youBot + IPR gripper
│   └── IprHd6ms180.proto        # IPR pick arm
├── controllers/
│   ├── youbot_restocker_demo/   # restocker (main pick-and-place logic)
│   ├── scanner_controller/      # upstream conveyor scanner
│   ├── ipr_pick_demo/           # IPR box spawn + pick-to-conveyor
│   ├── spawn_signal.py          # file IPC: scanner → IPR spawner
│   ├── youbot_sorter_demo/      # idle sorter placeholder
│   └── …                        # other demos (grocery, e6_twin, pallet, etc.)
└── data/
    ├── spawn_signal.json        # conveyor scanner → IPR spawn trigger
    ├── inventory.json           # scanner inventory updates
    ├── products.json
    └── shelf_mapping.json
```

## Main controllers

### `youbot_restocker_demo`

Full restocker implementation with mecanum navigation and sensor-guided pickup.

- **Files:** `youbot_restocker_demo.py`, `youbot_restocker_logic.py`, `YoubotRestockerDemo.txt`
- **Robot:** `DEF STORE_YOUBOT_RESTOCKER` (YoubotBoxGrip)
- **Stock pallets:** `DEF BEER_STOCK`, `CHIPS_STOCK`, `CHEESE_STOCK`, `MILK_STOCK`
- **Monitoring:** `stock_monitoring` supervisor → `sort_signal.json`

Key behavior:

- Three-stage box detection (arm IR sensor, upstream scanner tracking, physical fallback)
- `ALIGN_TO_BOX` — mecanum fine-align to measured box center before grasp
- `SENSOR_CONFIRM` — IR sensor on arm5 must see box at hover height
- Returns to exact home pose via `snap_to_home_pose()` after each cycle
- Removes delivered box from world; respects `MAX_LIVE_BOXES = 3`

Detailed state machine, tuning parameters, and function reference:

→ `controllers/youbot_restocker_demo/YoubotRestockerDemo.txt`

**Run unit tests:**

```bash
cd controllers/youbot_restocker_demo
python test_youbot_restocker_demo.py
```

### `scanner_controller`

Upstream conveyor scanner on robot `test_controller_sensor`.

- Detects `SPAWNED_BOX_*` entering zone at `(-0.01, 1.09)` radius `0.8 m`
- Logs pick-slot arrival at fixed youBot pick coordinates
- Writes `data/spawn_signal.json` to trigger IPR spawner (one box per scan, capped by live box count)
- Optionally POSTs events to dashboard and updates `data/inventory.json`

**Tests:**

```bash
cd controllers/scanner_controller
python test_scanner_controller.py
```

### `ipr_pick_demo`

IPR arm supervisor: spawns cardboard boxes and places them on the conveyor.

- **Does not** spawn on startup — waits at home until conveyor scanner triggers via `spawn_signal.json`
- One seed box (`SPAWNED_BOX_0`) on the conveyor in the world bootstraps the first scanner event
- Pick cycle: home → pick spawned box → lift → move to conveyor → release → wait for next spawn

### `spawn_signal.py`

Shared file-based signal between scanner and IPR:

```json
{"seq": 1, "box_def": "SPAWNED_BOX_0", "t": 12.5}
```

IPR reads `seq` and spawns the next `SPAWNED_BOX_N` only when the sequence increments.

### `dashboard_server.py`

Minimal HTTP server:

| Route | Method | Purpose |
|---|---|---|
| `/`, `/index.html` | GET | Dashboard page |
| `/latest` | GET | Latest scanner payload |
| `/update` | POST | Receive JSON from scanner |

### Other controllers

| Controller | Role |
|---|---|
| `youbot_sorter_demo` | Idle placeholder for sorter youBot |
| `grocery_supervisor` | Grocery store workflow (alternate world) |
| `minimal_store_supervisor` | Minimal store demo |
| `box_spawner` | Standalone timed box spawner (not used in main world) |
| `e6_twin/` | ME6 robot twin / IK demo (separate subsystem) |

## Calibrated poses (restocker)

| Name | Translation (x, y, z) |
|---|---|
| Restocker home | `-1.87451, 0.55379, 0.10346` |
| Box pick slot | `-1.25034, 0.58500, 0.19861` |

Constants live in `controllers/youbot_restocker_demo/youbot_restocker_logic.py` (`RESTOCKER_HOME_*`, `FIXED_PICK_BOX_POS`).

## Data files

| File | Purpose |
|---|---|
| `data/spawn_signal.json` | Scanner → IPR spawn trigger (sequence counter) |
| `data/inventory.json` | Stock levels updated by scanner |
| `data/products.json` | Product catalog (grocery demos) |
| `data/shelf_mapping.json` | Shelf assignments (grocery demos) |

## Requirements

- [Webots R2025a](https://cyberbotics.com/) or later
- Python 3.10+
- Webots Python API (`controller` module — provided by Webots when controllers run inside the simulator)

## Troubleshooting

**Webots crashes at “pre-finalizing nodes”**

- Reload a clean world; avoid saving mid-simulation with many colliding boxes
- World file should not contain duplicate `DEF SPAWNED_BOX_*` names or stale `hidden` velocity fields
- `MAX_LIVE_BOXES = 3` limits runtime spawns; restocker removes boxes after pallet delivery

**IPR does not spawn boxes**

- `CardboardBox` must be `IMPORTABLE EXTERNPROTO` in the world file for runtime spawn
- Check console for `Could not spawn SPAWNED_BOX_*` — usually missing IMPORTABLE proto
- Ensure seed box on conveyor passes scanner so `spawn_signal.json` seq increments

**Restocker misses pick**

- Verify home pose matches calibrated `RESTOCKER_HOME_TRANSLATION` in world and logic file
- Check `[YOUBOT RESTOCKER DIAG]` logs for detection stage (1/2/3)
- See `YoubotRestockerDemo.txt` for alignment and sensor tuning parameters

**Sensor reads ~3700 (self-hit)**

- Arm is hitting itself, not the box — ignored above `SENSOR_MAX_VALID = 3200`
- Wait for `SENSOR_CONFIRM` or wheel align to finish before descend

## Further reading

- Restocker deep dive: `controllers/youbot_restocker_demo/YoubotRestockerDemo.txt`
- ME6 twin / IK: `controllers/e6_twin/README.md`
