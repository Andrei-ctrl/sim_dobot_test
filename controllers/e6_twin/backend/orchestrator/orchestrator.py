"""
Orchestrator for synchronizing digital and physical robots.
Manages command execution and position synchronization between robots.
"""
import time
import threading
from typing import Optional, List
from queue import Queue, Empty

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from backend.controller.command import (
    RobotCommand, CommandType, TargetRobot,
    JointPosition, CommandQueue
)
from backend.tcp_connections.digital_robot import DigitalRobot
from backend.tcp_connections.physical_robot import PhysicalRobot
try:
    import config
except Exception:
    config = None

# IK solver is imported lazily so that missing ikpy does not crash the system
_ik_solver = None

def _get_ik_solver():
    global _ik_solver
    if _ik_solver is None:
        from backend.ik.ik_service import IKSolver
        _ik_solver = IKSolver()
    return _ik_solver


class RobotOrchestrator:
    """
    Orchestrates communication between digital (Webots) and physical robots.
    Ensures position synchronization and command routing.
    """
    
    def __init__(self, 
                 use_digital: bool = True,
                 use_physical: bool = False,
                 physical_host: str = "192.168.1.6",
                 physical_port: int = 29999):
        """
        Initialize the orchestrator.
        
        Args:
            use_digital: Enable digital robot (Webots)
            use_physical: Enable physical robot
            physical_host: IP address of physical robot
            physical_port: TCP port of physical robot
        """
        self.use_digital = use_digital
        self.use_physical = use_physical
        
        # Initialize robots
        self.digital_robot: Optional[DigitalRobot] = None
        self.physical_robot: Optional[PhysicalRobot] = None
        
        if use_digital:
            self.digital_robot = DigitalRobot()
        
        if use_physical:
            self.physical_robot = PhysicalRobot(physical_host, physical_port)
        
        # Command queue
        self.command_queue = CommandQueue()
        
        # Synchronization settings
        self.sync_enabled = config.ENABLE_SYNC if config else True
        self.sync_interval = config.SYNC_INTERVAL if config else 0.1  # seconds
        self.physical_velocity = config.PHYSICAL_VELOCITY if config else 50.0
        
        # Threading
        self._running = False
        self._command_thread = None
        self._sync_thread = None
        self._lock = threading.Lock()
        
        print("[Orchestrator] Initialized")
    
    def start(self) -> bool:
        """
        Start the orchestrator and initialize robots.
        
        Returns:
            True if started successfully
        """
        success = True
        
        # Start digital robot
        if self.digital_robot:
            self.digital_robot.start()
            print("[Orchestrator] Digital robot started")
        
        # Connect and start physical robot
        if self.physical_robot:
            if self.physical_robot.connect():
                # Set callback for position updates from physical robot
                self.physical_robot.start_feedback(
                    callback=self._on_physical_position_update
                )
                print("[Orchestrator] Physical robot connected and started")
            else:
                print("[Orchestrator] Failed to connect to physical robot")
                success = False
        
        # Start command processing thread
        self._running = True
        self._command_thread = threading.Thread(
            target=self._command_processing_loop,
            daemon=True
        )
        self._command_thread.start()
        
        # Start synchronization thread
        if self.sync_enabled and self.digital_robot and self.physical_robot and self.physical_robot.connected:
            self._sync_thread = threading.Thread(
                target=self._sync_loop,
                daemon=True
            )
            self._sync_thread.start()
            print("[Orchestrator] Synchronization enabled")
        
        print("[Orchestrator] Started successfully")
        return success
    
    def stop(self):
        """Stop the orchestrator and cleanup."""
        self._running = False
        
        # Wait for threads
        if self._command_thread:
            self._command_thread.join(timeout=2.0)
        if self._sync_thread:
            self._sync_thread.join(timeout=2.0)
        
        # Stop robots
        if self.digital_robot:
            self.digital_robot.stop()
        
        if self.physical_robot:
            self.physical_robot.disconnect()
        
        print("[Orchestrator] Stopped")
    
    def _command_processing_loop(self):
        """Process commands from the queue."""
        while self._running:
            try:
                command = self.command_queue.get_command(block=True, timeout=0.1)
                if command:
                    self._execute_command(command)
            except Exception as e:
                print(f"[Orchestrator] Command loop error: {e}")
                continue
    
    def _execute_command(self, command: RobotCommand):
        """
        Execute a robot command.
        
        Args:
            command: The command to execute
        """
        print(f"[Orchestrator] Executing command: {command.command_type.value} -> {command.target.value}")
        
        # Route command based on target
        if command.target == TargetRobot.DIGITAL_ONLY:
            self._execute_on_digital(command)
        
        elif command.target == TargetRobot.PHYSICAL_ONLY:
            self._execute_on_physical(command)
        
        elif command.target == TargetRobot.BOTH:
            # Execute on both robots
            self._execute_on_digital(command)
            self._execute_on_physical(command)
    
    def _execute_on_digital(self, command: RobotCommand):
        """Execute command on digital robot."""
        if not self.digital_robot:
            return
        
        if command.command_type == CommandType.MOVE_JOINT:
            if command.joint_position:
                self.digital_robot.set_joint_positions(
                    command.joint_position.to_list(),
                    velocity=max(0.0, min(1.0, command.speed))
                )
        
        elif command.command_type == CommandType.STOP:
            self.digital_robot.disable_motors()
        
        elif command.command_type == CommandType.ENABLE:
            self.digital_robot.enable_motors()
        
        elif command.command_type == CommandType.DISABLE:
            self.digital_robot.disable_motors()
        
        elif command.command_type == CommandType.GET_POSITION:
            _ = self.digital_robot.get_joint_positions()
    
    def _execute_on_physical(self, command: RobotCommand):
        """Execute command on physical robot."""
        if not self.physical_robot or not self.physical_robot.connected:
            return
        
        if command.command_type == CommandType.MOVE_JOINT:
            if command.joint_position:
                speed = max(0.0, min(1.0, command.speed))
                velocity = self.physical_velocity * speed  # Scale velocity
                self.physical_robot.set_joint_positions(
                    command.joint_position.to_list(),
                    velocity=velocity
                )
        
        elif command.command_type == CommandType.MOVE_CARTESIAN:
            if command.cartesian_position:
                pos = command.cartesian_position
                speed = max(0.0, min(1.0, command.speed))
                velocity = self.physical_velocity * speed
                self.physical_robot.set_cartesian_position(
                    pos.x, pos.y, pos.z, pos.rx, pos.ry, pos.rz,
                    velocity=velocity
                )
        
        elif command.command_type == CommandType.STOP:
            self.physical_robot.stop()
        
        elif command.command_type == CommandType.ENABLE:
            self.physical_robot.enable()
        
        elif command.command_type == CommandType.DISABLE:
            self.physical_robot.disable()

        elif command.command_type == CommandType.GET_POSITION:
            _ = self.physical_robot.get_joint_positions()
    
    def _on_physical_position_update(self, positions: List[float]):
        """
        Callback when physical robot position updates.
        Updates digital robot to match.
        
        Args:
            positions: Current joint positions from physical robot
        """
        if not self.sync_enabled or not self.digital_robot:
            return
        
        # Update digital robot to match physical robot position
        with self._lock:
            self.digital_robot.set_joint_positions(positions, velocity=2.0)
    
    def _sync_loop(self):
        """
        Periodic synchronization loop.
        Keeps digital robot in sync with physical robot.
        """
        while self._running:
            try:
                if (self.sync_enabled and self.physical_robot and self.physical_robot.connected
                        and self.digital_robot):
                    # Get physical robot position
                    physical_pos = self.physical_robot.get_joint_positions()
                    
                    # Update digital robot
                    with self._lock:
                        self.digital_robot.set_joint_positions(physical_pos, velocity=2.0)
                
                time.sleep(self.sync_interval)
                
            except Exception as e:
                print(f"[Orchestrator] Sync error: {e}")
                time.sleep(1.0)
    
    def send_command(self, command: RobotCommand) -> bool:
        """
        Send a command to the orchestrator.
        
        Args:
            command: The command to send
        
        Returns:
            True if command was queued successfully
        """
        return self.command_queue.add_command(command)
    
    def move_joint(self, positions: List[float], 
                   target: TargetRobot = TargetRobot.BOTH,
                   speed: float = 1.0) -> bool:
        """
        Move robot to joint positions.
        
        Args:
            positions: List of 6 joint positions in radians
            target: Which robot(s) to move
            speed: Movement speed factor
        
        Returns:
            True if command sent successfully
        """
        joint_pos = JointPosition.from_list(positions)
        command = RobotCommand(
            command_type=CommandType.MOVE_JOINT,
            target=target,
            joint_position=joint_pos,
            speed=speed
        )
        return self.send_command(command)
    
    def enable_sync(self):
        """Enable position synchronization."""
        self.sync_enabled = True
        if (self._running and self.digital_robot and self.physical_robot
                and self.physical_robot.connected and not self._sync_thread):
            self._sync_thread = threading.Thread(
                target=self._sync_loop,
                daemon=True
            )
            self._sync_thread.start()
        print("[Orchestrator] Synchronization enabled")
    
    def disable_sync(self):
        """Disable position synchronization."""
        self.sync_enabled = False
        print("[Orchestrator] Synchronization disabled")
    
    def get_digital_position(self) -> Optional[List[float]]:
        """Get current digital robot position."""
        if self.digital_robot:
            return self.digital_robot.get_joint_positions()
        return None
    
    def get_physical_position(self) -> Optional[List[float]]:
        """Get current physical robot position."""
        if self.physical_robot:
            return self.physical_robot.get_joint_positions()
        return None
    
    # ------------------------------------------------------------------
    # Inverse kinematics helpers
    # ------------------------------------------------------------------

    def move_to_xyz(
        self,
        x: float,
        y: float,
        z: float,
        rx: float = 0.0,
        ry: float = 0.0,
        rz: float = 0.0,
        target: TargetRobot = TargetRobot.DIGITAL_ONLY,
        speed: float = 1.0,
        position_only: bool = False,
    ) -> bool:
        """
        Move the end-effector to a Cartesian position using inverse kinematics.

        This is the easiest way for students to control the robot in task space.
        Internally it calls :class:`~backend.ik.ik_service.IKSolver` to compute
        the required joint angles and then issues a standard MOVE_JOINT command.

        Args:
            x, y, z:       Target end-effector position in **metres**
                           (robot base frame, Z = up).
            rx, ry, rz:    Target end-effector orientation in **radians**
                           (roll-pitch-yaw).  Ignored when *position_only*
                           is ``True``.
            target:        Which robot to move (default: digital / Webots).
            speed:         Speed factor 0.0 – 1.0.
            position_only: When ``True`` the solver ignores orientation and
                           may find solutions more easily.

        Returns:
            ``True`` if the IK succeeded and the command was queued,
            ``False`` otherwise.

        Example::

            orchestrator.move_to_xyz(x=0.20, y=0.00, z=0.35)
            orchestrator.move_to_xyz(0.15, 0.10, 0.30, position_only=True)
        """
        try:
            solver = _get_ik_solver()
        except Exception as e:
            print(f"[Orchestrator] IK solver unavailable: {e}")
            return False

        if position_only:
            joints = solver.solve_position(x, y, z)
        else:
            joints = solver.solve(x, y, z, rx, ry, rz)

        if joints is None:
            print(f"[Orchestrator] IK failed for target ({x}, {y}, {z})")
            return False

        print(f"[Orchestrator] IK solution: {[f'{j:.3f}' for j in joints]}")
        return self.move_joint(joints, target=target, speed=speed)

    def get_end_effector_position(
        self, use_digital: bool = True
    ):
        """
        Return the current end-effector (x, y, z) position in metres.

        Uses forward kinematics on the current joint angles read from
        the robot.

        Args:
            use_digital: Read from the digital (Webots) robot when ``True``,
                         from the physical robot when ``False``.

        Returns:
            Tuple ``(x, y, z)`` in metres, or ``None`` if unavailable.

        Example::

            x, y, z = orchestrator.get_end_effector_position()
            print(f"EE is at ({x:.3f}, {y:.3f}, {z:.3f}) m")
        """
        if use_digital:
            joints = self.get_digital_position()
        else:
            joints = self.get_physical_position()

        if joints is None:
            return None

        try:
            solver = _get_ik_solver()
            return solver.get_end_effector_position(joints)
        except Exception as e:
            print(f"[Orchestrator] FK error: {e}")
            return None

    def get_status(self) -> dict:
        """
        Get status of all components.
        
        Returns:
            Dictionary with status information
        """
        status = {
            "running": self._running,
            "sync_enabled": self.sync_enabled,
            "digital_robot": None,
            "physical_robot": None
        }
        
        if self.digital_robot:
            status["digital_robot"] = self.digital_robot.get_status()
        
        if self.physical_robot:
            status["physical_robot"] = self.physical_robot.get_status()
        
        return status
