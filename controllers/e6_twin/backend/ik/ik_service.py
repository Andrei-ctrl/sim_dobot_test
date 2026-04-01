"""
Inverse Kinematics service for the Dobot Me6 robot (e6_twin integration).

Uses the ikpy library to solve IK from Cartesian (x, y, z) target positions
to joint angles that can be sent directly to the robot.

Quick-start for students
------------------------
    from backend.ik.ik_service import IKSolver

    solver = IKSolver()

    # Move end-effector to x=0.20 m, y=0.00 m, z=0.30 m
    joints = solver.solve(x=0.20, y=0.00, z=0.30)

    if joints is not None:
        # joints is a list of 6 floats (radians) — pass straight to move_joint()
        orchestrator.move_joint(joints)

    # Or use the convenience method on the orchestrator directly:
    orchestrator.move_to_xyz(x=0.20, y=0.00, z=0.30)

Coordinate frame
----------------
    - Origin: robot base (base_link in the URDF)
    - All positions in **metres**, all angles in **radians**

Dependency
----------
    pip install ikpy
"""

import os
import numpy as np
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# ikpy import — give a helpful message if the library is missing
# ---------------------------------------------------------------------------
try:
    from ikpy.chain import Chain
    _IKPY_AVAILABLE = True
except ImportError:
    _IKPY_AVAILABLE = False
    print(
        "[IKSolver] WARNING: ikpy is not installed.\n"
        "  Install it with:  pip install ikpy\n"
        "  IK features will not be available until then."
    )

# Path to the URDF bundled alongside this file
_URDF_PATH = os.path.join(os.path.dirname(__file__), "me6_for_ikpy.urdf")


def _build_chain(urdf_path: str):
    """
    Load a URDF and return (chain, n_active_joints).

    ikpy skips fixed joints automatically and prepends an OriginLink, so
    we load once without a mask to discover the true chain length, then
    rebuild with active_mask = [False, True, True, ..., True].
    """
    chain_raw = Chain.from_urdf_file(urdf_path)
    n_links = len(chain_raw.links)          # 1 OriginLink + N revolute links
    active_mask = [False] + [True] * (n_links - 1)
    chain = Chain.from_urdf_file(urdf_path, active_links_mask=active_mask)
    return chain, n_links - 1               # n_active_joints = N


class IKSolver:
    """
    Inverse kinematics solver for the Dobot Me6 6-axis robot.

    Wraps ikpy so students only need to call a single method:

        joints = solver.solve(x, y, z)              # position only
        joints = solver.solve(x, y, z, rx, ry, rz)  # full pose

    Both methods return a list of joint angles (radians) ready to be
    passed to ``orchestrator.move_joint()``, or ``None`` if no solution
    could be found within tolerance.
    """

    def __init__(self, urdf_path: str = _URDF_PATH):
        """
        Build the kinematic chain from the bundled URDF.

        Args:
            urdf_path: Path to a URDF file describing the robot.
                       Defaults to the Me6 URDF shipped with this package.
        """
        if not _IKPY_AVAILABLE:
            raise RuntimeError(
                "ikpy is required for IKSolver. Run:  pip install ikpy"
            )
        if not os.path.isfile(urdf_path):
            raise FileNotFoundError(
                f"URDF not found at '{urdf_path}'. "
                "Make sure me6_for_ikpy.urdf is next to ik_service.py."
            )

        self.chain, self._n_joints = _build_chain(urdf_path)
        print(
            f"[IKSolver] Chain loaded — {len(self.chain.links)} links, "
            f"{self._n_joints} active joints"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def solve(
        self,
        x: float,
        y: float,
        z: float,
        rx: float = 0.0,
        ry: float = 0.0,
        rz: float = 0.0,
        initial_joints: Optional[List[float]] = None,
    ) -> Optional[List[float]]:
        """
        Solve inverse kinematics for a target end-effector pose.

        Args:
            x, y, z:    Target position in **metres** (robot base frame).
            rx, ry, rz: Target orientation in **radians** (roll-pitch-yaw).
                        Defaults to (0, 0, 0).
            initial_joints: Starting joint configuration [n_joints floats].
                            Defaults to home (all zeros).

        Returns:
            List of joint angles in radians, or ``None`` if not converged.

        Example::

            joints = solver.solve(x=0.20, y=0.00, z=0.35)
            if joints:
                orchestrator.move_joint(joints)
        """
        target = _build_target_matrix(x, y, z, rx, ry, rz)
        seed   = self._to_chain_vector(initial_joints or [0.0] * self._n_joints)

        result = self.chain.inverse_kinematics(
            target_position=target[:3, 3],
            target_orientation=target[:3, :3],
            orientation_mode="all",
            initial_position=seed,
        )

        joints = list(result[1:])        # skip OriginLink at index 0
        self._warn_if_diverged(result, target)
        return joints

    def solve_position(
        self,
        x: float,
        y: float,
        z: float,
        initial_joints: Optional[List[float]] = None,
    ) -> Optional[List[float]]:
        """
        Solve IK for a target position only (orientation is free).

        Finds solutions more easily because there is one fewer constraint.

        Args:
            x, y, z:        Target position in metres.
            initial_joints: Optional warm-start configuration.

        Returns:
            List of joint angles in radians, or ``None`` on failure.

        Example::

            joints = solver.solve_position(0.15, 0.10, 0.30)
        """
        target = _build_target_matrix(x, y, z)
        seed   = self._to_chain_vector(initial_joints or [0.0] * self._n_joints)

        result = self.chain.inverse_kinematics(
            target_position=target[:3, 3],
            orientation_mode=None,
            initial_position=seed,
        )

        joints = list(result[1:])
        self._warn_if_diverged(result, target)
        return joints

    def forward_kinematics(
        self, joint_angles: List[float]
    ) -> np.ndarray:
        """
        Compute the end-effector pose from joint angles.

        Args:
            joint_angles: List of joint angles in radians (length = n_joints).

        Returns:
            4×4 homogeneous transformation matrix.
            Position is in the last column: ``matrix[:3, 3]``.

        Example::

            T = solver.forward_kinematics([0, 0, 0, 0, 0, 0])
            print("EE position (m):", T[:3, 3])
        """
        return self.chain.forward_kinematics(self._to_chain_vector(joint_angles))

    def get_end_effector_position(
        self, joint_angles: List[float]
    ) -> Tuple[float, float, float]:
        """
        Return (x, y, z) end-effector position for a given configuration.

        Args:
            joint_angles: List of joint angles in radians.

        Returns:
            Tuple (x, y, z) in metres.

        Example::

            x, y, z = solver.get_end_effector_position([0]*6)
        """
        T = self.forward_kinematics(joint_angles)
        return float(T[0, 3]), float(T[1, 3]), float(T[2, 3])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_chain_vector(self, joint_angles: List[float]) -> np.ndarray:
        """
        Build the full ikpy chain vector: [0.0 (OriginLink), j1, j2, …, jN].
        """
        angles = list(joint_angles)
        if len(angles) != self._n_joints:
            angles = [0.0] * self._n_joints
        return np.array([0.0] + angles)

    def _warn_if_diverged(self, result: np.ndarray, target: np.ndarray):
        fk  = self.chain.forward_kinematics(result)
        err = float(np.linalg.norm(fk[:3, 3] - target[:3, 3]))
        if err > 0.01:
            print(
                f"[IKSolver] Warning: IK position error = {err*1000:.1f} mm. "
                "Try a different initial configuration."
            )


# ---------------------------------------------------------------------------
# Pure-math helper
# ---------------------------------------------------------------------------

def _build_target_matrix(
    x: float, y: float, z: float,
    rx: float = 0.0, ry: float = 0.0, rz: float = 0.0,
) -> np.ndarray:
    """4×4 homogeneous transform from position + RPY (intrinsic Rz·Ry·Rx)."""
    cr, sr = np.cos(rx), np.sin(rx)
    cp, sp = np.cos(ry), np.sin(ry)
    cy, sy = np.cos(rz), np.sin(rz)
    R = np.array([
        [cy*cp,  cy*sp*sr - sy*cr,  cy*sp*cr + sy*sr],
        [sy*cp,  sy*sp*sr + cy*cr,  sy*sp*cr - cy*sr],
        [  -sp,            cp*sr,             cp*cr  ],
    ])
    T      = np.eye(4)
    T[:3, :3] = R
    T[:3,  3] = [x, y, z]
    return T
