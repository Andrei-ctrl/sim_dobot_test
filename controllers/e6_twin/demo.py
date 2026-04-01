"""
Standalone demo for Dobot E6 twin control.
Can be run independently of Webots for testing physical robot only.
"""
import sys
import os
import time

# Add backend to path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from backend.controller.command import (
    RobotCommand, CommandType, TargetRobot,
    JointPosition, CartesianPosition
)
from backend.tcp_connections.physical_robot import PhysicalRobot
from backend.orchestrator.orchestrator import RobotOrchestrator


def demo_physical_only():
    """Demo using physical robot only (no Webots)."""
    print("=" * 60)
    print("Physical Robot Demo")
    print("=" * 60)
    
    # Create orchestrator with physical robot only
    orchestrator = RobotOrchestrator(
        use_digital=False,
        use_physical=True,
        physical_host="192.168.1.6",  # Update with your robot's IP
        physical_port=29999
    )
    
    # Start orchestrator
    if not orchestrator.start():
        print("Failed to connect to physical robot")
        print("Make sure the robot is powered on and connected to the network")
        return
    
    try:
        print("\nPhysical robot connected!")
        print("Running demo sequence...\n")
        
        # Get initial position
        print("1. Getting current position...")
        current_pos = orchestrator.get_physical_position()
        if current_pos:
            print(f"   Current position: {[f'{p:.3f}' for p in current_pos]}")
        
        time.sleep(2)
        
        # Move to home position
        print("\n2. Moving to home position...")
        home_positions = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        orchestrator.move_joint(
            home_positions,
            target=TargetRobot.PHYSICAL_ONLY,
            speed=0.5
        )
        time.sleep(5)
        
        # Move to position 1
        print("\n3. Moving to position 1...")
        position1 = [0.5, 0.3, -0.3, 0.0, 0.5, 0.0]
        orchestrator.move_joint(
            position1,
            target=TargetRobot.PHYSICAL_ONLY,
            speed=0.7
        )
        time.sleep(5)
        
        # Move to position 2
        print("\n4. Moving to position 2...")
        position2 = [-0.5, 0.5, 0.2, 0.3, -0.2, 0.5]
        orchestrator.move_joint(
            position2,
            target=TargetRobot.PHYSICAL_ONLY,
            speed=0.7
        )
        time.sleep(5)
        
        # Return to home
        print("\n5. Returning to home position...")
        orchestrator.move_joint(
            home_positions,
            target=TargetRobot.PHYSICAL_ONLY,
            speed=0.5
        )
        time.sleep(5)
        
        print("\nDemo completed successfully!")
        
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")
    
    except Exception as e:
        print(f"\nError during demo: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        print("\nShutting down...")
        orchestrator.stop()


def demo_with_gui():
    """Demo with GUI interface."""
    print("=" * 60)
    print("Dobot E6 Control GUI Demo")
    print("=" * 60)
    
    # Ask user for configuration
    print("\nConfiguration:")
    print("1. Digital robot only (Webots)")
    print("2. Physical robot only")
    print("3. Both (synchronized)")
    
    choice = input("\nSelect option (1-3): ").strip()
    
    use_digital = choice in ["1", "3"]
    use_physical = choice in ["2", "3"]
    
    if use_physical:
        robot_ip = input("Enter robot IP address (default: 192.168.1.6): ").strip()
        if not robot_ip:
            robot_ip = "192.168.1.6"
    else:
        robot_ip = "192.168.1.6"
    
    # Create orchestrator
    orchestrator = RobotOrchestrator(
        use_digital=use_digital,
        use_physical=use_physical,
        physical_host=robot_ip,
        physical_port=29999
    )
    
    # Start orchestrator
    if not orchestrator.start():
        print("Failed to start orchestrator")
        return
    
    try:
        # Launch GUI
        from frontend.frontend import create_gui
        
        print("\nLaunching GUI...")
        gui = create_gui(orchestrator)
        gui.run()
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        print("\nShutting down...")
        orchestrator.stop()


def test_connection():
    """Test connection to physical robot."""
    print("=" * 60)
    print("Robot Connection Test")
    print("=" * 60)
    
    robot_ip = input("\nEnter robot IP address (default: 192.168.1.6): ").strip()
    if not robot_ip:
        robot_ip = "192.168.1.6"
    
    print(f"\nAttempting to connect to {robot_ip}:29999...")
    
    robot = PhysicalRobot(robot_ip, 29999)
    
    if robot.connect():
        print("✓ Connection successful!")
        
        # Get robot position
        print("\nStarting feedback...")
        robot.start_feedback()
        time.sleep(2)
        
        position = robot.get_joint_positions()
        print(f"Current position: {[f'{p:.3f}' for p in position]}")
        
        # Test movement
        test_move = input("\nTest a small movement? (y/n): ").strip().lower()
        if test_move == 'y':
            print("Moving joint 1 by 0.1 radians...")
            current = robot.get_joint_positions()
            current[0] += 0.1
            robot.set_joint_positions(current, velocity=20.0)
            time.sleep(3)
            
            print("Returning to original position...")
            current[0] -= 0.1
            robot.set_joint_positions(current, velocity=20.0)
            time.sleep(3)
        
        robot.disconnect()
        print("\n✓ Test completed successfully!")
    else:
        print("✗ Connection failed!")
        print("\nTroubleshooting:")
        print("1. Check if robot is powered on")
        print("2. Verify IP address is correct")
        print("3. Ensure robot is on the same network")
        print("4. Check firewall settings")


if __name__ == "__main__":
    print("Dobot E6 Twin Control - Demo Scripts")
    print("=" * 60)
    print("\nSelect demo:")
    print("1. Test robot connection")
    print("2. Physical robot demo (no GUI)")
    print("3. GUI demo")
    print("4. Exit")
    
    choice = input("\nEnter choice (1-4): ").strip()
    
    if choice == "1":
        test_connection()
    elif choice == "2":
        demo_physical_only()
    elif choice == "3":
        demo_with_gui()
    else:
        print("Exiting...")
