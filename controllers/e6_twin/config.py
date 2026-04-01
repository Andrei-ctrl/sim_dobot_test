"""
Configuration file for Dobot E6 Twin Control System
Modify these settings to match your setup.
"""

# ============================================================================
# ROBOT CONFIGURATION
# ============================================================================

# Digital Robot (Webots Simulation)
USE_DIGITAL_ROBOT = True  # Set to True to use Webots simulation

# Physical Robot (Real Dobot E6)
USE_PHYSICAL_ROBOT = False  # Set to True to connect to real robot

# Physical Robot Connection Settings
PHYSICAL_ROBOT_HOST = "192.168.1.6"  # IP address of physical robot
PHYSICAL_ROBOT_PORT = 29999          # TCP port (default for Dobot)

# ============================================================================
# SYNCHRONIZATION SETTINGS
# ============================================================================

# Enable automatic position sync from physical to digital robot
ENABLE_SYNC = True

# Synchronization update rate (seconds)
# Lower = more responsive, but more CPU usage
SYNC_INTERVAL = 0.1  # 10 Hz

# ============================================================================
# CONTROL SETTINGS
# ============================================================================

# Default movement speed (0.0 to 1.0)
DEFAULT_SPEED = 0.7

# Default velocity for physical robot (degrees/second for joint, mm/s for Cartesian)
PHYSICAL_VELOCITY = 50.0

# Webots timestep (milliseconds)
WEBOTS_TIMESTEP = 32

# ============================================================================
# SAFETY SETTINGS
# ============================================================================

# Joint position limits (radians)
# Format: (min, max) for each joint
JOINT_LIMITS = [
    (-6.28, 6.28),   # Joint 1 (+/-360deg)
    (-2.356, 2.356), # Joint 2 (+/-135deg)
    (-2.356, 2.356), # Joint 3 (+/-135deg)
    (-6.28, 6.28),   # Joint 4 (+/-360deg)
    (-2.356, 2.356), # Joint 5 (+/-135deg)
    (-6.28, 6.28),   # Joint 6 (+/-360deg)
]

# Position tolerance for "reached" detection (radians)
POSITION_TOLERANCE = 0.01

# Maximum wait time for position reached (seconds)
POSITION_TIMEOUT = 30.0

# ============================================================================
# GUI SETTINGS
# ============================================================================

# Enable GUI on startup (when running from Webots)
ENABLE_GUI = True

# GUI window size
GUI_WIDTH = 800
GUI_HEIGHT = 600

# Status update interval for GUI (seconds)
GUI_UPDATE_INTERVAL = 2.0

# ============================================================================
# PRESET POSITIONS
# ============================================================================

# Define preset positions (radians)
# Format: [joint1, joint2, joint3, joint4, joint5, joint6]

PRESET_POSITIONS = {
    "home": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "position_1": [0.5, 0.3, -0.3, 0.0, 0.5, 0.0],
    "position_2": [-0.5, 0.5, 0.2, 0.3, -0.2, 0.5],
    "position_3": [0.0, -0.4, 0.4, 0.0, 0.3, 0.0],
    "safe_test": [0.2, 0.1, -0.1, 0.0, 0.1, 0.0],
}

# ============================================================================
# INVERSE KINEMATICS SETTINGS
# ============================================================================

# Enable IK features (requires: pip install ikpy)
ENABLE_IK = True

# IK position tolerance (metres) — warn if FK error exceeds this after solving
IK_POSITION_TOLERANCE = 0.005  # 5 mm

# ============================================================================
# LOGGING SETTINGS
# ============================================================================

# Enable debug logging
DEBUG_MODE = False

# Log file path (None to disable file logging)
LOG_FILE = None  # Example: "dobot_e6_log.txt"

# ============================================================================
# ADVANCED SETTINGS
# ============================================================================

# Connection timeout for physical robot (seconds)
CONNECTION_TIMEOUT = 5.0

# Feedback update rate for physical robot (Hz)
FEEDBACK_RATE = 20

# Command queue size (0 = unlimited)
COMMAND_QUEUE_SIZE = 0

# Enable automatic error clearing on physical robot
AUTO_CLEAR_ERRORS = True
