"""
Digital robot controller for Webots simulation.
Handles communication with the virtual Dobot E6 robot in Webots.
"""
import sys
from typing import List, Optional, Tuple
from controller import Robot, Motor, PositionSensor
import threading
import time


class DigitalRobot:
    """
    Controller for the digital (Webots) Dobot E6 robot.
    Manages motors, sensors, and position control.
    """
    
    def __init__(self, timestep: int = 32):
        """
        Initialize the digital robot controller.
        
        Args:
            timestep: Simulation timestep in milliseconds
        """
        self.robot = Robot()
        self.timestep = timestep
        
        # Joint names matching the PROTO definition
        self.joint_names = ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6"]
        
        # Initialize motors and sensors (keep aligned with joint_names)
        self.motors: List[Optional[Motor]] = []
        self.sensors: List[Optional[PositionSensor]] = []
        
        self._initialize_devices()
        self._running = False
        self._update_thread = None
        self._lock = threading.Lock()
        
        print(f"[DigitalRobot] Initialized with {len(self.motors)} motors")
    
    def _initialize_devices(self):
        """Initialize motors and position sensors for all joints."""
        for joint_name in self.joint_names:
            # Get motor
            motor = self.robot.getDevice(joint_name)
            if motor is None:
                print(f"[DigitalRobot] Warning: Motor {joint_name} not found")
                self.motors.append(None)
                self.sensors.append(None)
                continue

            # Set motor to position control mode
            motor.setPosition(0.0)
            motor.setVelocity(1.0)  # Default velocity
            self.motors.append(motor)

            # Get position sensor
            sensor_name = f"{joint_name}_sensor"
            sensor = self.robot.getDevice(sensor_name)
            if sensor is None:
                print(f"[DigitalRobot] Warning: Sensor {sensor_name} not found")
                self.sensors.append(None)
                continue

            sensor.enable(self.timestep)
            self.sensors.append(sensor)
    
    def start(self):
        """Start the robot controller in a separate thread."""
        if self._running:
            return
        
        self._running = True
        self._update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self._update_thread.start()
        print("[DigitalRobot] Started")
    
    def stop(self):
        """Stop the robot controller."""
        self._running = False
        if self._update_thread:
            self._update_thread.join(timeout=2.0)
        print("[DigitalRobot] Stopped")
    
    def _update_loop(self):
        """Main update loop for the Webots controller."""
        while self._running:
            if self.robot.step(self.timestep) == -1:
                self._running = False
                break
    
    def set_joint_positions(self, positions: List[float], velocity: float = 1.0) -> bool:
        """
        Set target positions for all joints.
        
        Args:
            positions: List of 6 joint positions in radians
            velocity: Movement velocity (0.0 to max velocity)
        
        Returns:
            True if successful, False otherwise
        """
        if len(positions) != len(self.joint_names):
            print(f"[DigitalRobot] Error: Expected {len(self.joint_names)} positions, got {len(positions)}")
            return False
        
        with self._lock:
            for motor, position in zip(self.motors, positions):
                if motor is None:
                    continue
                motor.setVelocity(velocity)
                motor.setPosition(position)
        
        print(f"[DigitalRobot] Set joint positions: {[f'{p:.3f}' for p in positions]}")
        return True
    
    def get_joint_positions(self) -> List[float]:
        """
        Get current joint positions from sensors.
        
        Returns:
            List of 6 joint positions in radians
        """
        with self._lock:
            positions = [
                sensor.getValue() if sensor is not None else 0.0
                for sensor in self.sensors
            ]
        
        return positions
    
    def get_joint_position(self, joint_index: int) -> Optional[float]:
        """
        Get position of a specific joint.
        
        Args:
            joint_index: Index of the joint (0-5)
        
        Returns:
            Joint position in radians, or None if invalid index
        """
        if 0 <= joint_index < len(self.sensors):
            with self._lock:
                sensor = self.sensors[joint_index]
                if sensor is None:
                    return None
                return sensor.getValue()
        return None
    
    def set_joint_velocity(self, joint_index: int, velocity: float) -> bool:
        """
        Set velocity for a specific joint.
        
        Args:
            joint_index: Index of the joint (0-5)
            velocity: Target velocity
        
        Returns:
            True if successful, False otherwise
        """
        if 0 <= joint_index < len(self.motors):
            with self._lock:
                motor = self.motors[joint_index]
                if motor is None:
                    return False
                motor.setVelocity(velocity)
            return True
        return False
    
    def move_to_home_position(self):
        """Move robot to home position (all joints at 0)."""
        home_position = [0.0] * len(self.joint_names)
        self.set_joint_positions(home_position, velocity=0.5)
        print("[DigitalRobot] Moving to home position")
    
    def enable_motors(self):
        """Enable all motors (motors are enabled by default in Webots)."""
        print("[DigitalRobot] Motors enabled")
    
    def disable_motors(self):
        """Disable all motors by setting velocity to 0."""
        with self._lock:
            for motor in self.motors:
                motor.setVelocity(0.0)
        print("[DigitalRobot] Motors disabled")
    
    def wait_until_position_reached(self, target_positions: List[float], 
                                   tolerance: float = 0.01, 
                                   timeout: float = 30.0) -> bool:
        """
        Wait until the robot reaches target positions.
        
        Args:
            target_positions: Target joint positions
            tolerance: Position tolerance in radians
            timeout: Maximum wait time in seconds
        
        Returns:
            True if position reached, False if timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            current_positions = self.get_joint_positions()
            
            # Check if all joints are within tolerance
            all_reached = all(
                abs(current - target) < tolerance
                for current, target in zip(current_positions, target_positions)
            )
            
            if all_reached:
                return True
            
            time.sleep(0.1)
        
        return False
    
    def get_status(self) -> dict:
        """
        Get current robot status.
        
        Returns:
            Dictionary with robot status information
        """
        return {
            "running": self._running,
            "joint_positions": self.get_joint_positions(),
            "num_joints": len(self.motors),
            "timestep": self.timestep
        }
