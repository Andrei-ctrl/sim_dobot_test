"""
Main controller for Dobot E6 twin robots.
This is the Webots controller entry point.
"""
import sys
import os

# Add parent directories to path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from backend.orchestrator.orchestrator import RobotOrchestrator
from frontend.frontend import create_gui
import config


def main():
    """
    Main entry point for the Dobot E6 twin controller.
    Runs in Webots as a robot controller.
    """
    print("=" * 60)
    print("Dobot E6 Twin Controller")
    print("=" * 60)
    
    # Configuration
    USE_DIGITAL = config.USE_DIGITAL_ROBOT  # Always true when running in Webots
    USE_PHYSICAL = config.USE_PHYSICAL_ROBOT
    PHYSICAL_HOST = config.PHYSICAL_ROBOT_HOST
    PHYSICAL_PORT = config.PHYSICAL_ROBOT_PORT
    
    # Create orchestrator
    orchestrator = RobotOrchestrator(
        use_digital=USE_DIGITAL,
        use_physical=USE_PHYSICAL,
        physical_host=PHYSICAL_HOST,
        physical_port=PHYSICAL_PORT
    )
    
    # Start orchestrator
    if not orchestrator.start():
        print("[Main] Failed to start orchestrator")
        return 1
    
    try:
        # Create and run GUI
        print("[Main] Starting GUI...")
        gui = create_gui(orchestrator)
        gui.run()
        
    except KeyboardInterrupt:
        print("\n[Main] Interrupted by user")
    
    except Exception as e:
        print(f"[Main] Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        print("[Main] Shutting down...")
        orchestrator.stop()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
