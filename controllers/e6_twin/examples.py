"""
Example usage scenarios for the Dobot E6 twin control system.
Run these examples to understand different use cases.
"""
import time
import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(__file__))

from backend.orchestrator.orchestrator import RobotOrchestrator
from backend.controller.command import (
    RobotCommand, CommandType, TargetRobot,
    JointPosition, CartesianPosition
)


def example_1_webots_only():
    """
    Example 1: Control Webots simulation only
    Use this when testing in simulation without physical robot.
    """
    print("\n" + "="*60)
    print("Example 1: Webots Simulation Only")
    print("="*60)
    
    # Initialize with digital robot only
    orch = RobotOrchestrator(use_digital=True, use_physical=False)
    orch.start()
    
    print("\n1. Moving to home position...")
    orch.move_joint([0, 0, 0, 0, 0, 0], TargetRobot.DIGITAL_ONLY, speed=0.5)
    time.sleep(3)
    
    print("2. Moving to position 1...")
    orch.move_joint([0.5, 0.3, -0.3, 0.0, 0.5, 0.0], TargetRobot.DIGITAL_ONLY, speed=0.7)
    time.sleep(3)
    
    print("3. Getting current position...")
    pos = orch.get_digital_position()
    print(f"   Current position: {[f'{p:.3f}' for p in pos]}")
    
    orch.stop()
    print("Example 1 completed!\n")


def example_2_physical_only():
    """
    Example 2: Control physical robot only
    Use this for testing physical robot without Webots.
    """
    print("\n" + "="*60)
    print("Example 2: Physical Robot Only")
    print("="*60)
    
    # Update this with your robot's IP
    robot_ip = input("Enter robot IP (default 192.168.1.6): ").strip() or "192.168.1.6"
    
    orch = RobotOrchestrator(
        use_digital=False,
        use_physical=True,
        physical_host=robot_ip
    )
    
    if not orch.start():
        print("Failed to connect to physical robot!")
        return
    
    print("\n1. Moving to home position...")
    orch.move_joint([0, 0, 0, 0, 0, 0], TargetRobot.PHYSICAL_ONLY, speed=0.5)
    time.sleep(4)
    
    print("2. Small movement test...")
    orch.move_joint([0.2, 0.1, -0.1, 0.0, 0.1, 0.0], TargetRobot.PHYSICAL_ONLY, speed=0.6)
    time.sleep(4)
    
    print("3. Return to home...")
    orch.move_joint([0, 0, 0, 0, 0, 0], TargetRobot.PHYSICAL_ONLY, speed=0.5)
    time.sleep(4)
    
    orch.stop()
    print("Example 2 completed!\n")


def example_3_synchronized_twins():
    """
    Example 3: Synchronized digital and physical robots
    Commands sent to both robots, physical movements sync to digital.
    """
    print("\n" + "="*60)
    print("Example 3: Synchronized Digital and Physical Twins")
    print("="*60)
    
    robot_ip = input("Enter robot IP (default 192.168.1.6): ").strip() or "192.168.1.6"
    
    orch = RobotOrchestrator(
        use_digital=True,
        use_physical=True,
        physical_host=robot_ip
    )
    
    if not orch.start():
        print("Failed to start orchestrator!")
        return
    
    # Enable synchronization
    print("\n1. Synchronization enabled")
    print("   (Physical robot movements will update Webots)")
    orch.enable_sync()
    time.sleep(2)
    
    print("\n2. Moving both robots to home...")
    orch.move_joint([0, 0, 0, 0, 0, 0], TargetRobot.BOTH, speed=0.5)
    time.sleep(4)
    
    print("\n3. Moving both robots to position 1...")
    orch.move_joint([0.3, 0.2, -0.2, 0.0, 0.3, 0.0], TargetRobot.BOTH, speed=0.7)
    time.sleep(4)
    
    print("\n4. Checking positions...")
    digital_pos = orch.get_digital_position()
    physical_pos = orch.get_physical_position()
    print(f"   Digital:  {[f'{p:.3f}' for p in digital_pos]}")
    print(f"   Physical: {[f'{p:.3f}' for p in physical_pos]}")
    
    print("\n5. Moving only physical robot...")
    print("   (Watch Webots follow automatically!)")
    orch.move_joint([0.5, 0.3, -0.3, 0.0, 0.5, 0.0], TargetRobot.PHYSICAL_ONLY, speed=0.6)
    time.sleep(5)
    
    print("\n6. Return both to home...")
    orch.move_joint([0, 0, 0, 0, 0, 0], TargetRobot.BOTH, speed=0.5)
    time.sleep(4)
    
    orch.stop()
    print("Example 3 completed!\n")


def example_4_custom_command_queue():
    """
    Example 4: Using custom commands and command queue
    Demonstrates advanced command queueing and custom commands.
    """
    print("\n" + "="*60)
    print("Example 4: Custom Command Queue")
    print("="*60)
    
    orch = RobotOrchestrator(use_digital=True, use_physical=False)
    orch.start()
    
    print("\n1. Queuing multiple commands...")
    
    # Create sequence of commands
    positions_sequence = [
        [0.2, 0.1, -0.1, 0.0, 0.1, 0.0],
        [0.4, 0.2, -0.2, 0.0, 0.2, 0.0],
        [0.6, 0.3, -0.3, 0.0, 0.3, 0.0],
        [0.4, 0.2, -0.2, 0.0, 0.2, 0.0],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    ]
    
    for i, positions in enumerate(positions_sequence, 1):
        print(f"   Queuing position {i}...")
        joint_pos = JointPosition.from_list(positions)
        command = RobotCommand(
            command_type=CommandType.MOVE_JOINT,
            target=TargetRobot.DIGITAL_ONLY,
            joint_position=joint_pos,
            speed=0.8
        )
        orch.send_command(command)
        time.sleep(2)  # Commands are processed by queue
    
    print("\n2. All commands completed!")
    time.sleep(2)
    
    orch.stop()
    print("Example 4 completed!\n")


def example_5_position_monitoring():
    """
    Example 5: Real-time position monitoring
    Monitor robot positions in real-time.
    """
    print("\n" + "="*60)
    print("Example 5: Real-time Position Monitoring")
    print("="*60)
    
    robot_ip = input("Enter robot IP (default 192.168.1.6): ").strip() or "192.168.1.6"
    
    from backend.tcp_connections.physical_robot import PhysicalRobot
    
    def position_callback(positions):
        """Called when robot position updates."""
        print(f"   Position: {[f'{p:.3f}' for p in positions]}")
    
    robot = PhysicalRobot(robot_ip, 29999)
    
    if robot.connect():
        print("\n1. Starting position feedback...")
        robot.start_feedback(callback=position_callback)
        
        print("\n2. Move the robot manually or send commands...")
        print("   (You'll see position updates in real-time)")
        
        # Send a test movement
        print("\n3. Sending test movement...")
        robot.set_joint_positions([0.2, 0.1, -0.1, 0.0, 0.1, 0.0], velocity=30.0)
        time.sleep(5)
        
        print("\n4. Returning to home...")
        robot.set_joint_positions([0, 0, 0, 0, 0, 0], velocity=30.0)
        time.sleep(5)
        
        robot.disconnect()
        print("\nExample 5 completed!\n")
    else:
        print("Failed to connect to physical robot!")


def example_6_error_handling():
    """
    Example 6: Error handling and validation
    Demonstrates proper error handling.
    """
    print("\n" + "="*60)
    print("Example 6: Error Handling and Validation")
    print("="*60)
    
    orch = RobotOrchestrator(use_digital=True, use_physical=False)
    orch.start()
    
    print("\n1. Testing position validation...")
    
    # Try invalid position (out of range)
    invalid_pos = JointPosition.from_list([10.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    if not invalid_pos.validate():
        print("   ✓ Correctly detected invalid position!")
    
    # Try valid position
    valid_pos = JointPosition.from_list([0.5, 0.3, -0.3, 0.0, 0.5, 0.0])
    if valid_pos.validate():
        print("   ✓ Valid position accepted")
    
    print("\n2. Testing command validation...")
    
    # Command without required data
    bad_command = RobotCommand(
        command_type=CommandType.MOVE_JOINT,
        target=TargetRobot.DIGITAL_ONLY
        # Missing joint_position!
    )
    if not bad_command.validate():
        print("   ✓ Correctly rejected incomplete command")
    
    # Valid command
    good_command = RobotCommand(
        command_type=CommandType.MOVE_JOINT,
        target=TargetRobot.DIGITAL_ONLY,
        joint_position=valid_pos
    )
    if good_command.validate():
        print("   ✓ Valid command accepted")
        orch.send_command(good_command)
    
    time.sleep(2)
    orch.stop()
    print("\nExample 6 completed!\n")


def main():
    """Main menu for running examples."""
    examples = {
        "1": ("Webots Simulation Only", example_1_webots_only),
        "2": ("Physical Robot Only", example_2_physical_only),
        "3": ("Synchronized Twins", example_3_synchronized_twins),
        "4": ("Custom Command Queue", example_4_custom_command_queue),
        "5": ("Position Monitoring", example_5_position_monitoring),
        "6": ("Error Handling", example_6_error_handling),
    }
    
    print("\n" + "="*60)
    print("Dobot E6 Twin Control - Example Usage")
    print("="*60)
    
    print("\nAvailable Examples:")
    for key, (name, _) in examples.items():
        print(f"{key}. {name}")
    print("0. Exit")
    
    while True:
        choice = input("\nSelect example (0-6): ").strip()
        
        if choice == "0":
            print("Goodbye!")
            break
        
        if choice in examples:
            _, example_func = examples[choice]
            try:
                example_func()
                
                another = input("\nRun another example? (y/n): ").strip().lower()
                if another != 'y':
                    break
            except KeyboardInterrupt:
                print("\n\nInterrupted by user")
                break
            except Exception as e:
                print(f"\nError: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("Invalid choice!")


if __name__ == "__main__":
    main()
