# Dobot E6 Twin Control System

A comprehensive control system for synchronizing a Dobot E6 robot between Webots simulation (digital twin) and the physical robot.

## Features

- **Dual Control**: Control both digital (Webots) and physical robots
- **Synchronization**: Automatic position sync from physical to digital robot
- **Flexible Targeting**: Send commands to digital only, physical only, or both
- **GUI Interface**: User-friendly tkinter interface for robot control
- **Command Queue**: Thread-safe command processing
- **Position Monitoring**: Real-time position feedback from both robots

## Architecture

```
controllers/e6_twin/
|--- backend/
|   |--- controller/
|   |   `--- command.py          # Command definitions and queue
|   |--- tcp_connections/
|   |   |--- digital_robot.py    # Webots robot controller
|   |   `--- physical_robot.py   # TCP connection to physical robot
|   `--- orchestrator/
|       `--- orchestrator.py     # Synchronization and command routing
|--- frontend/
|   `--- frontend.py             # GUI interface
|--- e6_twin.py                  # Main Webots controller
`--- demo.py                     # Standalone demo scripts
```

## Setup

### Prerequisites

- Python 3.7+
- Webots R2025a or later
- Dobot E6 robot (optional, for physical robot control)
- Network connection to robot (if using physical robot)

### Installation

1. Ensure your Webots installation includes the Python controller library
2. No additional Python packages required for basic operation
3. For GUI: tkinter (usually included with Python)

### Configuration

Edit the configuration in `config.py`:

```python
USE_DIGITAL_ROBOT = True        # Enable Webots simulation
USE_PHYSICAL_ROBOT = False      # Enable physical robot
PHYSICAL_ROBOT_HOST = "192.168.1.6"  # Robot IP address
PHYSICAL_ROBOT_PORT = 29999          # Robot TCP port
```

## Usage

### Running in Webots

1. Open the world file in Webots: `worlds/world1.wbt`
2. Set the DobotE6 robot controller to "e6_twin"
3. Run the simulation
4. The GUI will appear automatically

### Running Standalone

For testing or controlling only the physical robot:

```bash
python controllers/e6_twin/demo.py
```

Select from the demo options:
1. **Test robot connection** - Verify connection to physical robot
2. **Physical robot demo** - Run automated movement sequence
3. **GUI demo** - Launch GUI for manual control
4. **Exit**

## Command Interface

### Command Types

- `MOVE_JOINT`: Move to specific joint positions (radians)
- `MOVE_CARTESIAN`: Move to Cartesian coordinates (physical robot only)
- `GET_POSITION`: Query current position
- `STOP`: Emergency stop
- `ENABLE`: Enable motors
- `DISABLE`: Disable motors

### Target Options

- `DIGITAL_ONLY`: Command sent to Webots only
- `PHYSICAL_ONLY`: Command sent to physical robot only
- `BOTH`: Command sent to both robots (synchronized)

### Example Code

```python
from backend.orchestrator.orchestrator import RobotOrchestrator
from backend.controller.command import TargetRobot

# Create orchestrator
orchestrator = RobotOrchestrator(
    use_digital=True,
    use_physical=True,
    physical_host="192.168.1.6"
)

# Start system
orchestrator.start()

# Move both robots to position
positions = [0.5, 0.3, -0.3, 0.0, 0.5, 0.0]
orchestrator.move_joint(
    positions,
    target=TargetRobot.BOTH,
    speed=0.7
)

# Get positions
digital_pos = orchestrator.get_digital_position()
physical_pos = orchestrator.get_physical_position()

# Cleanup
orchestrator.stop()
```

## GUI Features

### Robot Target Selection
- Choose which robot(s) to control: Digital, Physical, or Both

### Joint Position Control
- Enter desired position for each of 6 joints (in radians)
- Adjust movement speed (0.1 to 1.0)
- Validate positions against robot limits

### Quick Actions
- **Move to Position**: Execute movement with current settings
- **Home Position**: Move all joints to 0 radians
- **Get Current Position**: Read and display current positions
- **Stop**: Emergency stop all movement

### Preset Positions
- Three configurable preset positions for quick testing

### Synchronization Control
- Enable/disable automatic sync from physical to digital robot
- When enabled, physical robot movements update Webots in real-time

### Status Display
- Real-time status updates
- Command execution feedback
- Position information

## Synchronization Behavior

When synchronization is enabled and both robots are active:

1. **Commands to BOTH**: Sent simultaneously to digital and physical robots
2. **Physical Updates**: Physical robot position changes automatically update the digital twin
3. **Sync Rate**: 10Hz (configurable via `sync_interval` in orchestrator)

### Typical Workflow

1. Start system with both robots enabled
2. Enable synchronization
3. Send commands to physical robot
4. Digital robot automatically follows physical robot movements
5. Can also send commands to both simultaneously

## Safety Features

### Position Validation
Joint positions are validated against robot limits:
- Joint 1, 4, 6: +/-6.28 radians (+/-360deg)
- Joint 2, 3, 5: +/-2.356 radians (+/-135deg)

### Command Queue
- Thread-safe command processing
- Commands executed in order
- Can be cleared in emergency situations

### Emergency Stop
- Immediate stop command available
- Stops both robots simultaneously
- Can be triggered from GUI or code

## Troubleshooting

### Cannot Connect to Physical Robot

1. **Check network connection**
   - Verify robot is on same network
   - Ping robot IP address
   - Check firewall settings

2. **Verify robot state**
   - Ensure robot is powered on
   - Check robot control panel for errors
   - Try power cycling the robot

3. **Connection settings**
   - Confirm IP address is correct
   - Default port is 29999 for Dobot
   - Check if robot is in remote control mode

### Webots Controller Not Starting

1. **Controller path**
   - Verify controller is set to "e6_twin" in world file
   - Check controller file exists in controllers/e6_twin/

2. **Python path**
   - Ensure Webots can find Python
   - Check Webots Python preferences

3. **Import errors**
   - Verify all backend modules are present
   - Check for syntax errors in Python files

### Synchronization Issues

1. **Lag or delays**
   - Adjust `sync_interval` in orchestrator (default 0.1s)
   - Check network latency for physical robot

2. **Position mismatch**
   - Verify both robots are enabled
   - Check synchronization is enabled in GUI
   - Ensure physical robot feedback is working

## API Reference

### RobotOrchestrator

Main orchestration class for managing both robots.

**Methods:**
- `start()`: Initialize and start both robots
- `stop()`: Stop and cleanup all resources
- `move_joint(positions, target, speed)`: Move to joint positions
- `get_digital_position()`: Get digital robot position
- `get_physical_position()`: Get physical robot position
- `enable_sync()`: Enable synchronization
- `disable_sync()`: Disable synchronization
- `send_command(command)`: Send custom command

### DigitalRobot

Webots simulation controller.

**Methods:**
- `set_joint_positions(positions, velocity)`: Set joint positions
- `get_joint_positions()`: Get current positions
- `move_to_home_position()`: Move to home
- `enable_motors()`: Enable motors
- `disable_motors()`: Disable motors

### PhysicalRobot

TCP/IP connection to physical robot.

**Methods:**
- `connect()`: Connect to robot
- `disconnect()`: Disconnect from robot
- `set_joint_positions(positions, velocity)`: Set joint positions
- `set_cartesian_position(x, y, z, rx, ry, rz, velocity)`: Set Cartesian position
- `get_joint_positions()`: Get current positions
- `enable()`: Enable robot
- `disable()`: Disable robot
- `stop()`: Emergency stop
- `start_feedback(callback)`: Start position monitoring

## License

Apache License 2.0

## Contributing

Feel free to submit issues and enhancement requests!
