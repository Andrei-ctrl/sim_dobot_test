# Dobot E6 Twin Control System - Complete File Index

## folder Project Structure

```
controllers/e6_twin/
|--- doc Core Files
|   |--- e6_twin.py                      # Main Webots controller entry point
|   |--- config.py                       # System configuration
|   |--- demo.py                         # Interactive demo script
|   `--- examples.py                     # 6 detailed usage examples
|
|--- books Documentation
|   |--- README.md                       # Complete documentation (main reference)
|   |--- GETTING_STARTED.md              # Quick start guide
|   |--- IMPLEMENTATION_SUMMARY.md       # Technical implementation details
|   |--- QUICKSTART.py                   # Code snippet reference
|   |--- architecture.py                 # System architecture visualization
|   `--- INDEX.md                        # This file
|
|--- design Frontend (User Interface)
|   |--- frontend/
|   |   |--- __init__.py
|   |   `--- frontend.py                 # GUI implementation (Tkinter)
|
`--- gear Backend (Core Logic)
    `--- backend/
        |--- __init__.py
        |
        |--- controller/                  # Command Interface
        |   |--- __init__.py
        |   `--- command.py              # Command types, queue, validation
        |
        |--- tcp_connections/            # Robot Controllers
        |   |--- __init__.py
        |   |--- digital_robot.py        # Webots simulation controller
        |   `--- physical_robot.py       # Physical robot TCP connection
        |
        `--- orchestrator/               # Coordination
            |--- __init__.py
            `--- orchestrator.py         # Synchronization & routing
```

---

## doc File Purposes

### Main Entry Points

| File | Purpose | When to Use |
|------|---------|-------------|
| **e6_twin.py** | Webots controller | Automatic when running in Webots |
| **demo.py** | Interactive demos | Testing, learning, standalone use |
| **examples.py** | Code examples | Learning API, testing features |

### Configuration

| File | Purpose | Edit When |
|------|---------|-----------|
| **config.py** | All settings | Changing robot IP, speeds, limits, presets |

### Documentation

| File | Purpose | Read When |
|------|---------|-----------|
| **README.md** | Full documentation | Need complete reference |
| **GETTING_STARTED.md** | Quick start | First time setup |
| **IMPLEMENTATION_SUMMARY.md** | Technical details | Understanding implementation |
| **QUICKSTART.py** | Code examples | Need quick code reference |
| **architecture.py** | System diagrams | Understanding architecture |

### Backend Core

| File | Lines | Purpose |
|------|-------|---------|
| **command.py** | ~170 | Command definitions, queue, validation |
| **digital_robot.py** | ~200 | Webots robot control |
| **physical_robot.py** | ~270 | Physical robot TCP communication |
| **orchestrator.py** | ~320 | Synchronization and coordination |

### Frontend

| File | Lines | Purpose |
|------|-------|---------|
| **frontend.py** | ~280 | GUI interface (Tkinter) |

---

## rocket Quick Access by Task

### I want to...

#### **Control robot in Webots simulation**
-> Run Webots with `world1.wbt`
-> Controller: `e6_twin.py` (automatic)
-> Reference: [GETTING_STARTED.md](GETTING_STARTED.md) Option A

#### **Test physical robot connection**
-> Run: `python demo.py`
-> Choose option 1
-> Reference: [GETTING_STARTED.md](GETTING_STARTED.md) Option B

#### **Use both robots synchronized**
-> Configure: [config.py](config.py)
-> Run: Webots or `python demo.py` option 3
-> Reference: [GETTING_STARTED.md](GETTING_STARTED.md) Option C

#### **Write my own control code**
-> Examples: [QUICKSTART.py](QUICKSTART.py)
-> Reference: [examples.py](examples.py)
-> API Docs: [README.md](README.md) - API Reference section

#### **Understand how it works**
-> Architecture: `python architecture.py`
-> Details: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
-> Code: Read [backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py)

#### **Change robot IP or settings**
-> Edit: [config.py](config.py)
-> See: Lines 10-12 for robot connection

#### **Add new features**
-> Commands: Edit [backend/controller/command.py](backend/controller/command.py)
-> Execution: Edit [backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py)
-> GUI: Edit [frontend/frontend.py](frontend/frontend.py)

#### **Troubleshoot issues**
-> Guide: [README.md](README.md) - Troubleshooting section
-> Quick fixes: [GETTING_STARTED.md](GETTING_STARTED.md) - Troubleshooting

---

## book Reading Order for New Users

### First Time Setup
1. [GETTING_STARTED.md](GETTING_STARTED.md) - Start here!
2. `python demo.py` - Interactive learning
3. [README.md](README.md) - Full reference

### Learning the System
1. `python architecture.py` - See structure
2. [QUICKSTART.py](QUICKSTART.py) - Code examples
3. `python examples.py` - Working examples
4. [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) - Deep dive

### Development
1. [config.py](config.py) - Configuration options
2. [backend/controller/command.py](backend/controller/command.py) - Command interface
3. [backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py) - Main logic
4. [README.md](README.md) - API reference

---

## tools Key Code Sections

### Creating Commands
**File:** [backend/controller/command.py](backend/controller/command.py)
**Lines:** 1-170
**Classes:** `CommandType`, `TargetRobot`, `JointPosition`, `RobotCommand`

### Digital Robot Control
**File:** [backend/tcp_connections/digital_robot.py](backend/tcp_connections/digital_robot.py)
**Lines:** 1-200
**Class:** `DigitalRobot`
**Key Methods:** `set_joint_positions()`, `get_joint_positions()`

### Physical Robot Control
**File:** [backend/tcp_connections/physical_robot.py](backend/tcp_connections/physical_robot.py)
**Lines:** 1-270
**Class:** `PhysicalRobot`
**Key Methods:** `connect()`, `set_joint_positions()`, `start_feedback()`

### Orchestration
**File:** [backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py)
**Lines:** 1-320
**Class:** `RobotOrchestrator`
**Key Methods:** `start()`, `move_joint()`, `send_command()`

### GUI
**File:** [frontend/frontend.py](frontend/frontend.py)
**Lines:** 1-280
**Class:** `RobotControlGUI`
**Key Methods:** `_move_to_position()`, `_toggle_sync()`

---

## stats Statistics

- **Total Files:** 16 Python files + 5 documentation files
- **Total Lines of Code:** ~1,500 (excluding docs)
- **Documentation Lines:** ~1,200
- **Core Components:** 4 (Command, Digital, Physical, Orchestrator)
- **Example Scripts:** 6 detailed examples
- **Demo Modes:** 4 interactive modes

---

## goals Feature Coverage

### [ok] Implemented Features
- [x] Digital robot control (Webots)
- [x] Physical robot control (TCP/IP)
- [x] Command interface with validation
- [x] Thread-safe operation
- [x] Position synchronization (Physical -> Digital)
- [x] GUI interface
- [x] Command queue
- [x] Joint and Cartesian control
- [x] Position monitoring
- [x] Error handling
- [x] Configurable settings
- [x] Multiple examples
- [x] Complete documentation

### sync Extensible Components
- [ ] Add custom commands (easy via `CommandType` enum)
- [ ] Add preset positions (easy via `config.py`)
- [ ] Add new GUI features (extend `frontend.py`)
- [ ] Add logging (hooks provided)
- [ ] Add trajectory planning (build on command queue)

---

## handshake Contributing

To add new features:

1. **New Command Type:**
   - Add to `CommandType` enum in [command.py](backend/controller/command.py)
   - Implement in `_execute_command()` in [orchestrator.py](backend/orchestrator/orchestrator.py)

2. **New GUI Feature:**
   - Edit [frontend.py](frontend/frontend.py)
   - Add widgets in `_create_widgets()`
   - Add handler methods

3. **Configuration:**
   - Add settings to [config.py](config.py)
   - Document in [README.md](README.md)

---

## phone Support

- **Documentation:** [README.md](README.md)
- **Quick Start:** [GETTING_STARTED.md](GETTING_STARTED.md)
- **Examples:** [examples.py](examples.py)
- **Code Reference:** [QUICKSTART.py](QUICKSTART.py)
- **Architecture:** `python architecture.py`

---

## done Quick Commands

```bash
# View architecture
python architecture.py

# Run demos
python demo.py

# Run examples
python examples.py

# Test connection (edit IP first)
python -c "from backend.tcp_connections.physical_robot import PhysicalRobot; r=PhysicalRobot('192.168.1.6',29999); print('Connected!' if r.connect() else 'Failed'); r.disconnect()"

# Start GUI (standalone)
python demo.py
# Then select option 3
```

---

**Last Updated:** January 28, 2026
**Version:** 1.0
**Status:** Production Ready [ok]
