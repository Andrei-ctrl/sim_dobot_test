"""
Command interface for controlling the Dobot E6 robot.
Provides data structures and validation for robot commands.
"""
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum


class CommandType(Enum):
    """Types of commands that can be sent to the robot."""
    MOVE_JOINT = "move_joint"
    MOVE_CARTESIAN = "move_cartesian"
    GET_POSITION = "get_position"
    STOP = "stop"
    ENABLE = "enable"
    DISABLE = "disable"


class TargetRobot(Enum):
    """Target robot for command execution."""
    DIGITAL_ONLY = "digital"      # Send to Webots only
    PHYSICAL_ONLY = "physical"    # Send to real robot only
    BOTH = "both"                 # Send to both and sync


@dataclass
class JointPosition:
    """Represents joint positions for the robot."""
    joint1: float
    joint2: float
    joint3: float
    joint4: float
    joint5: float
    joint6: float
    
    def to_list(self) -> List[float]:
        """Convert to list format."""
        return [self.joint1, self.joint2, self.joint3, 
                self.joint4, self.joint5, self.joint6]
    
    @classmethod
    def from_list(cls, values: List[float]) -> 'JointPosition':
        """Create from list format."""
        if len(values) != 6:
            raise ValueError(f"Expected 6 joint values, got {len(values)}")
        return cls(*values)
    
    def validate(self) -> bool:
        """Validate joint positions are within limits."""
        # Dobot E6 typical limits (in radians)
        limits = [
            (-6.28, 6.28),   # joint1
            (-2.356, 2.356), # joint2
            (-2.356, 2.356), # joint3
            (-6.28, 6.28),   # joint4
            (-2.356, 2.356), # joint5
            (-6.28, 6.28),   # joint6
        ]
        
        for value, (min_val, max_val) in zip(self.to_list(), limits):
            if not (min_val <= value <= max_val):
                return False
        return True


@dataclass
class CartesianPosition:
    """Represents Cartesian position and orientation."""
    x: float
    y: float
    z: float
    rx: float  # rotation around x-axis
    ry: float  # rotation around y-axis
    rz: float  # rotation around z-axis
    
    def to_list(self) -> List[float]:
        """Convert to list format."""
        return [self.x, self.y, self.z, self.rx, self.ry, self.rz]
    
    @classmethod
    def from_list(cls, values: List[float]) -> 'CartesianPosition':
        """Create from list format."""
        if len(values) != 6:
            raise ValueError(f"Expected 6 cartesian values, got {len(values)}")
        return cls(*values)


@dataclass
class RobotCommand:
    """
    Represents a command to be sent to the robot.
    """
    command_type: CommandType
    target: TargetRobot
    joint_position: Optional[JointPosition] = None
    cartesian_position: Optional[CartesianPosition] = None
    speed: float = 1.0  # Speed factor (0.0 to 1.0)
    
    def validate(self) -> bool:
        """Validate command parameters."""
        if self.command_type == CommandType.MOVE_JOINT:
            if self.joint_position is None:
                return False
            return self.joint_position.validate()
        
        elif self.command_type == CommandType.MOVE_CARTESIAN:
            if self.cartesian_position is None:
                return False
            return True
        
        return True
    
    def to_dict(self) -> dict:
        """Convert command to dictionary format."""
        data = {
            "command_type": self.command_type.value,
            "target": self.target.value,
            "speed": self.speed
        }
        
        if self.joint_position:
            data["joint_position"] = self.joint_position.to_list()
        
        if self.cartesian_position:
            data["cartesian_position"] = self.cartesian_position.to_list()
        
        return data


class CommandQueue:
    """Thread-safe command queue for managing robot commands."""
    
    def __init__(self):
        from queue import Queue
        self._queue = Queue()
    
    def add_command(self, command: RobotCommand) -> bool:
        """Add a command to the queue."""
        if not command.validate():
            return False
        
        self._queue.put(command)
        return True
    
    def get_command(self, block: bool = True, timeout: Optional[float] = None) -> Optional[RobotCommand]:
        """Get the next command from the queue."""
        try:
            return self._queue.get(block=block, timeout=timeout)
        except:
            return None
    
    def is_empty(self) -> bool:
        """Check if the queue is empty."""
        return self._queue.empty()
    
    def clear(self) -> None:
        """Clear all commands from the queue."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except:
                break
