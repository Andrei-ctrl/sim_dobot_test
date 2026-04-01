"""
Quick Start Guide for Dobot E6 Twin Control
"""

# SCENARIO 1: Using Webots Simulation Only
# ==========================================
from backend.orchestrator.orchestrator import RobotOrchestrator
from backend.controller.command import TargetRobot

# Create orchestrator with digital robot only
orchestrator = RobotOrchestrator(
    use_digital=True,
    use_physical=False
)

# Start the system
orchestrator.start()

# Move the robot
positions = [0.5, 0.3, -0.3, 0.0, 0.5, 0.0]
orchestrator.move_joint(positions, target=TargetRobot.DIGITAL_ONLY, speed=0.7)

# Get current position
current_pos = orchestrator.get_digital_position()
print(f"Current position: {current_pos}")

# Stop
orchestrator.stop()


# SCENARIO 2: Using Physical Robot Only
# ======================================
orchestrator = RobotOrchestrator(
    use_digital=False,
    use_physical=True,
    physical_host="192.168.1.6",  # Your robot IP
    physical_port=29999
)

orchestrator.start()

# Move physical robot
positions = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # Home position
orchestrator.move_joint(positions, target=TargetRobot.PHYSICAL_ONLY, speed=0.5)

orchestrator.stop()


# SCENARIO 3: Both Robots with Synchronization
# ============================================
orchestrator = RobotOrchestrator(
    use_digital=True,
    use_physical=True,
    physical_host="192.168.1.6"
)

orchestrator.start()

# Enable sync - physical robot movements will update digital twin
orchestrator.enable_sync()

# Send command to both robots
positions = [0.5, 0.3, -0.3, 0.0, 0.5, 0.0]
orchestrator.move_joint(positions, target=TargetRobot.BOTH, speed=0.7)

# When you move the physical robot manually, the digital twin will follow!

orchestrator.stop()


# SCENARIO 4: Using Custom Commands
# ==================================
from backend.controller.command import RobotCommand, CommandType, JointPosition

orchestrator = RobotOrchestrator(use_digital=True, use_physical=False)
orchestrator.start()

# Create custom command
joint_pos = JointPosition(
    joint1=0.5,
    joint2=0.3,
    joint3=-0.3,
    joint4=0.0,
    joint5=0.5,
    joint6=0.0
)

command = RobotCommand(
    command_type=CommandType.MOVE_JOINT,
    target=TargetRobot.DIGITAL_ONLY,
    joint_position=joint_pos,
    speed=0.8
)

orchestrator.send_command(command)
orchestrator.stop()


# SCENARIO 5: Direct Robot Control (Advanced)
# ==========================================
from backend.tcp_connections.digital_robot import DigitalRobot
from backend.tcp_connections.physical_robot import PhysicalRobot

# Digital robot only
digital = DigitalRobot()
digital.start()
digital.set_joint_positions([0.0, 0.0, 0.0, 0.0, 0.0, 0.0], velocity=1.0)
# ... do work ...
digital.stop()

# Physical robot only
physical = PhysicalRobot("192.168.1.6", 29999)
if physical.connect():
    physical.start_feedback()
    physical.set_joint_positions([0.0, 0.0, 0.0, 0.0, 0.0, 0.0], velocity=30.0)
    # ... do work ...
    physical.disconnect()


# SCENARIO 6: Using GUI
# =====================
from frontend.frontend import create_gui

orchestrator = RobotOrchestrator(
    use_digital=True,
    use_physical=True,
    physical_host="192.168.1.6"
)

orchestrator.start()

# Create and run GUI
gui = create_gui(orchestrator)
gui.run()

orchestrator.stop()


# SCENARIO 7: Position Monitoring Callback
# ========================================
def on_position_update(positions):
    """Called when physical robot position updates."""
    print(f"Robot moved to: {positions}")

# Create physical robot with callback
from backend.tcp_connections.physical_robot import PhysicalRobot

robot = PhysicalRobot("192.168.1.6", 29999)
if robot.connect():
    robot.start_feedback(callback=on_position_update)
    # Now whenever the robot moves, on_position_update will be called
    # ... do work ...
    robot.disconnect()


# COMMON OPERATIONS
# =================

# Move to home position
orchestrator.move_joint([0, 0, 0, 0, 0, 0], TargetRobot.BOTH, speed=0.5)

# Get status
status = orchestrator.get_status()
print(status)

# Emergency stop
from backend.controller.command import RobotCommand, CommandType
stop_cmd = RobotCommand(command_type=CommandType.STOP, target=TargetRobot.BOTH)
orchestrator.send_command(stop_cmd)

# Check positions
digital_pos = orchestrator.get_digital_position()
physical_pos = orchestrator.get_physical_position()
print(f"Digital: {digital_pos}")
print(f"Physical: {physical_pos}")
