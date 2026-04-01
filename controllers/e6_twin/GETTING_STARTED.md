# GETTING STARTED - Dobot E6 Twin Control

## Quick Start in 3 Steps

### Option A: Using Webots Simulation Only (No Physical Robot)

**Step 1:** Open Webots
- Launch Webots R2025a
- Open: `worlds/world1.wbt`

**Step 2:** Run Simulation
- Click the "Play" button in Webots
- The controller will start automatically

**Step 3:** Control the Robot
- GUI will appear automatically
- Select "Digital Only (Webots)"
- Enter joint positions or use preset buttons
- Click "Move to Position"

That's it! The virtual robot will move in Webots.

---

### Option B: Testing Physical Robot Connection

**Step 1:** Configure Connection
Edit `controllers/e6_twin/config.py`:
```python
USE_PHYSICAL_ROBOT = True
PHYSICAL_ROBOT_HOST = "192.168.1.6"  # Your robot's IP
```

**Step 2:** Test Connection
```bash
cd controllers/e6_twin
python demo.py
```
- Select option 1: "Test robot connection"
- Enter your robot's IP address
- Follow prompts

**Step 3:** Run Demo
If connection successful:
- Select option 2: "Physical robot demo"
- Watch the robot perform automated movements

---

### Option C: Full Digital Twin (Both Robots)

**Step 1:** Configure
Edit `config.py`:
```python
USE_DIGITAL_ROBOT = True
USE_PHYSICAL_ROBOT = True
PHYSICAL_ROBOT_HOST = "192.168.1.6"
```

**Step 2:** Start Webots
- Open `worlds/world1.wbt`
- Click Play

**Step 3:** Control Both Robots
- GUI appears
- Select "Both (Synchronized)"
- Enable "Physical -> Digital Sync"
- Move physical robot - watch Webots follow!
- Send commands - both robots move together!

---

## What You Can Do

### 1. Manual Control via GUI
- Enter joint positions (in radians)
- Adjust speed slider
- Click "Move to Position"
- Use preset positions for quick testing

### 2. Get Current Position
- Click "Get Current Position"
- Values populate in entry fields
- Shows current state of robot(s)

### 3. Quick Actions
- **Home**: All joints to 0
- **Stop**: Emergency stop
- **Preset Positions**: Pre-configured positions

### 4. Synchronization
- Check "Enable Physical -> Digital Sync"
- Move physical robot manually
- Digital twin follows automatically!
- Real-time position matching

---

## Testing Examples

### Test 1: Simple Movement (Simulation)
```python
# In Webots console or demo.py
from backend.orchestrator.orchestrator import RobotOrchestrator

orch = RobotOrchestrator(use_digital=True, use_physical=False)
orch.start()

# Move to a position
orch.move_joint([0.5, 0.3, -0.3, 0, 0.5, 0])

orch.stop()
```

### Test 2: Physical Robot Connection
```python
from backend.tcp_connections.physical_robot import PhysicalRobot

robot = PhysicalRobot("192.168.1.6", 29999)
if robot.connect():
    print("Connected!")
    robot.move_to_home_position()
    robot.disconnect()
```

### Test 3: Synchronized Control
```python
orch = RobotOrchestrator(use_digital=True, use_physical=True)
orch.start()
orch.enable_sync()

# Move both
orch.move_joint([0.3, 0.2, -0.2, 0, 0.3, 0], target=TargetRobot.BOTH)

orch.stop()
```

---

## Running Different Scripts

### Demo Script (Interactive)
```bash
python demo.py
```
Options:
1. Test connection
2. Physical robot demo
3. GUI demo

### Examples Script (6 Examples)
```bash
python examples.py
```
Demonstrates:
1. Webots only
2. Physical only
3. Synchronized twins
4. Command queue
5. Position monitoring
6. Error handling

### Architecture Visualization
```bash
python architecture.py
```
Shows system architecture diagrams

---

## Configuration Quick Reference

Edit `config.py` for:

**Robot Selection:**
```python
USE_DIGITAL_ROBOT = True   # Webots
USE_PHYSICAL_ROBOT = False  # Real robot
```

**Connection:**
```python
PHYSICAL_ROBOT_HOST = "192.168.1.6"
PHYSICAL_ROBOT_PORT = 29999
```

**Synchronization:**
```python
ENABLE_SYNC = True
SYNC_INTERVAL = 0.1  # seconds
```

**Safety:**
```python
DEFAULT_SPEED = 0.7
POSITION_TOLERANCE = 0.01
```

---

## Troubleshooting Quick Fixes

### Problem: Can't connect to physical robot
**Fix:**
1. Check robot is powered on
2. Verify IP address: `ping 192.168.1.6`
3. Check robot is in remote mode
4. Disable firewall temporarily

### Problem: Webots controller not starting
**Fix:**
1. Check controller is set to "e6_twin" in world file
2. Verify Python path in Webots preferences
3. Check for syntax errors: `python e6_twin.py`

### Problem: GUI not appearing
**Fix:**
1. Check `ENABLE_GUI = True` in config.py
2. Verify tkinter is installed: `python -c "import tkinter"`
3. Run manually: `python demo.py` -> option 3

### Problem: Sync not working
**Fix:**
1. Check "Enable Physical -> Digital Sync" is checked
2. Verify both robots are enabled
3. Check `ENABLE_SYNC = True` in config.py
4. Ensure physical robot feedback is running

---

## File Reference

**Main Files:**
- `e6_twin.py` - Webots controller entry point
- `config.py` - Configuration settings
- `demo.py` - Interactive demos
- `examples.py` - Code examples

**Documentation:**
- `README.md` - Complete documentation
- `IMPLEMENTATION_SUMMARY.md` - Technical details
- `QUICKSTART.py` - Code snippets
- `architecture.py` - System diagrams

**Core Code:**
- `backend/controller/command.py` - Command interface
- `backend/tcp_connections/digital_robot.py` - Webots control
- `backend/tcp_connections/physical_robot.py` - Physical robot
- `backend/orchestrator/orchestrator.py` - Coordination
- `frontend/frontend.py` - GUI

---

## Next Steps

1. **Learn the basics**: Run `python examples.py` and try Example 1
2. **Test connection**: If you have physical robot, run connection test
3. **Explore GUI**: Start Webots and use the GUI
4. **Read docs**: Check README.md for detailed information
5. **Write code**: Use QUICKSTART.py as reference

---

## Getting Help

1. Check `README.md` - Comprehensive documentation
2. Check `TROUBLESHOOTING` section in README
3. Run `python architecture.py` - See how it works
4. Read `examples.py` - Working code examples
5. Check configuration in `config.py`

---

## Success Checklist

- [ ] Webots simulation working
- [ ] Can control virtual robot via GUI
- [ ] Physical robot connection tested (if available)
- [ ] Synchronization working (if using both)
- [ ] Understand basic command structure
- [ ] Can run example scripts
- [ ] Know how to configure system

Once you check all boxes, you're ready to use the system for your projects!

---

**Happy robot controlling! robot**
