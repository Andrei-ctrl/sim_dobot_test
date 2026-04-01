"""
Physical robot controller for the real Dobot E6 robot.
Handles TCP/IP communication with the physical robot.
"""
import socket
import threading
import time
import json
from typing import List, Optional, Tuple, Callable
import struct


class PhysicalRobot:
    """
    Controller for the physical Dobot E6 robot via TCP/IP.
    Handles connection, command sending, and position feedback.
    """
    
    def __init__(self, host: str = "192.168.1.6", port: int = 29999):
        """
        Initialize the physical robot controller.
        
        Args:
            host: IP address of the robot controller
            port: TCP port for communication (default 29999 for Dobot)
        """
        self.host = host
        self.port = port
        self.socket: Optional[socket.socket] = None
        self.connected = False
        
        self._running = False
        self._feedback_thread = None
        self._lock = threading.Lock()
        self._io_lock = threading.Lock()
        
        # Current robot state
        self._current_positions = [0.0] * 6
        self._position_callback: Optional[Callable] = None
        
        print(f"[PhysicalRobot] Initialized for {host}:{port}")
    
    def connect(self, timeout: float = 5.0) -> bool:
        """
        Connect to the physical robot.
        
        Args:
            timeout: Connection timeout in seconds
        
        Returns:
            True if connected, False otherwise
        """
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(timeout)
            self.socket.connect((self.host, self.port))
            self.connected = True
            
            # Enable robot
            self._send_command("EnableRobot()")
            time.sleep(0.5)
            
            print(f"[PhysicalRobot] Connected to {self.host}:{self.port}")
            return True
            
        except Exception as e:
            print(f"[PhysicalRobot] Connection failed: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from the physical robot."""
        self.stop_feedback()
        
        if self.socket:
            try:
                # Disable robot before disconnecting
                self._send_command("DisableRobot()")
                self.socket.close()
            except:
                pass
            finally:
                self.socket = None
                self.connected = False
        
        print("[PhysicalRobot] Disconnected")
    
    def start_feedback(self, callback: Optional[Callable] = None):
        """
        Start the feedback loop to monitor robot position.
        
        Args:
            callback: Optional callback function called when position updates
        """
        if self._running:
            return
        
        self._position_callback = callback
        self._running = True
        self._feedback_thread = threading.Thread(target=self._feedback_loop, daemon=True)
        self._feedback_thread.start()
        print("[PhysicalRobot] Feedback started")
    
    def stop_feedback(self):
        """Stop the feedback loop."""
        self._running = False
        if self._feedback_thread:
            self._feedback_thread.join(timeout=2.0)
        print("[PhysicalRobot] Feedback stopped")
    
    def _feedback_loop(self):
        """Continuous loop to read robot position feedback."""
        while self._running and self.connected:
            try:
                positions = self._get_current_position()
                if positions:
                    with self._lock:
                        self._current_positions = positions
                    
                    # Call callback if provided
                    if self._position_callback:
                        self._position_callback(positions)
                
                time.sleep(0.05)  # 20Hz update rate
                
            except Exception as e:
                print(f"[PhysicalRobot] Feedback error: {e}")
                time.sleep(0.5)
    
    def _send_command(self, command: str) -> Optional[str]:
        """
        Send a command to the robot and get response.
        
        Args:
            command: Command string to send
        
        Returns:
            Response string or None if failed
        """
        if not self.connected or not self.socket:
            print("[PhysicalRobot] Not connected")
            return None
        
        try:
            # Send command (Dobot expects commands ending with newline)
            message = command.strip() + "\n"
            with self._io_lock:
                self.socket.sendall(message.encode("utf-8"))

                # Receive response until newline or timeout
                chunks = []
                while True:
                    data = self.socket.recv(4096)
                    if not data:
                        break
                    chunks.append(data)
                    if b"\n" in data:
                        break

            response = b"".join(chunks).decode("utf-8", errors="ignore").strip()
            return response or None

        except Exception as e:
            print(f"[PhysicalRobot] Command failed: {e}")
            return None
    
    def _get_current_position(self) -> Optional[List[float]]:
        """
        Get current joint positions from the robot.
        
        Returns:
            List of 6 joint positions in radians, or None if failed
        """
        response = self._send_command("GetAngle()")
        if not response:
            return None
        
        try:
            # Parse response format: {joint1,joint2,joint3,joint4,joint5,joint6}
            # Remove braces and split
            values_str = response.strip().strip("{}")
            values = [float(v.strip()) for v in values_str.split(',')]
            
            # Convert degrees to radians
            positions = [v * 3.14159265359 / 180.0 for v in values[:6]]
            return positions
            
        except Exception as e:
            print(f"[PhysicalRobot] Failed to parse position: {e}")
            return None
    
    def set_joint_positions(self, positions: List[float], velocity: float = 50.0) -> bool:
        """
        Set target positions for all joints.
        
        Args:
            positions: List of 6 joint positions in radians
            velocity: Movement velocity (degrees/second)
        
        Returns:
            True if successful, False otherwise
        """
        if len(positions) != 6:
            print(f"[PhysicalRobot] Error: Expected 6 positions, got {len(positions)}")
            return False
        
        # Convert radians to degrees
        positions_deg = [p * 180.0 / 3.14159265359 for p in positions]
        
        # Build MovJ command (joint move)
        command = f"MovJ({{{','.join([f'{p:.2f}' for p in positions_deg])}}},{velocity})"
        
        response = self._send_command(command)
        if response:
            print(f"[PhysicalRobot] Set joint positions: {[f'{p:.3f}' for p in positions]}")
            return True
        
        return False
    
    def get_joint_positions(self) -> List[float]:
        """
        Get current joint positions.
        
        Returns:
            List of 6 joint positions in radians
        """
        with self._lock:
            return self._current_positions.copy()
    
    def set_cartesian_position(self, x: float, y: float, z: float, 
                              rx: float, ry: float, rz: float,
                              velocity: float = 50.0) -> bool:
        """
        Set target Cartesian position.
        
        Args:
            x, y, z: Position in mm
            rx, ry, rz: Orientation in degrees
            velocity: Movement velocity (mm/second)
        
        Returns:
            True if successful, False otherwise
        """
        command = f"MovL({{{x:.2f},{y:.2f},{z:.2f},{rx:.2f},{ry:.2f},{rz:.2f}}},{velocity})"
        
        response = self._send_command(command)
        if response:
            print(f"[PhysicalRobot] Set cartesian position: ({x:.2f}, {y:.2f}, {z:.2f})")
            return True
        
        return False
    
    def enable(self) -> bool:
        """Enable the robot."""
        response = self._send_command("EnableRobot()")
        if response:
            print("[PhysicalRobot] Robot enabled")
            return True
        return False
    
    def disable(self) -> bool:
        """Disable the robot."""
        response = self._send_command("DisableRobot()")
        if response:
            print("[PhysicalRobot] Robot disabled")
            return True
        return False
    
    def stop(self) -> bool:
        """Stop the robot movement immediately."""
        response = self._send_command("Stop()")
        if response:
            print("[PhysicalRobot] Robot stopped")
            return True
        return False
    
    def move_to_home_position(self) -> bool:
        """Move robot to home position."""
        home_positions = [0.0] * 6  # All joints at 0 radians
        return self.set_joint_positions(home_positions, velocity=30.0)
    
    def clear_error(self) -> bool:
        """Clear robot error state."""
        response = self._send_command("ClearError()")
        if response:
            print("[PhysicalRobot] Errors cleared")
            return True
        return False
    
    def get_status(self) -> dict:
        """
        Get current robot status.
        
        Returns:
            Dictionary with robot status information
        """
        return {
            "connected": self.connected,
            "running": self._running,
            "joint_positions": self.get_joint_positions(),
            "host": self.host,
            "port": self.port
        }
    
    def wait_until_position_reached(self, target_positions: List[float], 
                                   tolerance: float = 0.01, 
                                   timeout: float = 30.0) -> bool:
        """
        Wait until the robot reaches target positions.
        
        Args:
            target_positions: Target joint positions in radians
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
