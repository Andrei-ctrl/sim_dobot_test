"""
Frontend interface for controlling the Dobot E6 twin robots.
Provides a simple GUI for sending commands and monitoring robot status.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
from typing import Optional

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from backend.orchestrator.orchestrator import RobotOrchestrator
from backend.controller.command import TargetRobot, JointPosition
import config


class RobotControlGUI:
    """
    GUI for controlling the digital and physical Dobot E6 robots.
    """
    
    def __init__(self, orchestrator: RobotOrchestrator):
        """
        Initialize the GUI.
        
        Args:
            orchestrator: The robot orchestrator instance
        """
        self.orchestrator = orchestrator
        
        # Create main window
        self.root = tk.Tk()
        self.root.title("Dobot E6 Twin Control")
        self.root.geometry(f"{config.GUI_WIDTH}x{config.GUI_HEIGHT}")
        
        # Status update thread
        self._running = False
        self._update_thread = None
        
        self._create_widgets()
        self._start_status_updates()
    
    def _create_widgets(self):
        """Create GUI widgets."""
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Robot target selection
        target_frame = ttk.LabelFrame(main_frame, text="Target Robot", padding="10")
        target_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.target_var = tk.StringVar(value="both")
        ttk.Radiobutton(target_frame, text="Digital Only (Webots)", 
                       variable=self.target_var, value="digital").grid(row=0, column=0, padx=5)
        ttk.Radiobutton(target_frame, text="Physical Only", 
                       variable=self.target_var, value="physical").grid(row=0, column=1, padx=5)
        ttk.Radiobutton(target_frame, text="Both (Synchronized)", 
                       variable=self.target_var, value="both").grid(row=0, column=2, padx=5)
        
        # Joint control
        joint_frame = ttk.LabelFrame(main_frame, text="Joint Positions (radians)", padding="10")
        joint_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.joint_entries = []
        for i in range(6):
            ttk.Label(joint_frame, text=f"Joint {i+1}:").grid(row=i, column=0, sticky=tk.W, pady=2)
            entry = ttk.Entry(joint_frame, width=10)
            entry.insert(0, "0.0")
            entry.grid(row=i, column=1, padx=5, pady=2)
            self.joint_entries.append(entry)
        
        # Speed control
        ttk.Label(joint_frame, text="Speed:").grid(row=6, column=0, sticky=tk.W, pady=2)
        self.speed_var = tk.DoubleVar(value=config.DEFAULT_SPEED)
        speed_scale = ttk.Scale(joint_frame, from_=0.1, to=1.0,
                               variable=self.speed_var, orient=tk.HORIZONTAL)
        speed_scale.grid(row=6, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)

        # ── Inverse Kinematics ──────────────────────────────────────────────
        ik_frame = ttk.LabelFrame(main_frame, text="Inverse Kinematics — Move to XYZ (metres)", padding="10")
        ik_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        # X / Y / Z
        for col, label in enumerate(("X:", "Y:", "Z:")):
            ttk.Label(ik_frame, text=label).grid(row=0, column=col*2, sticky=tk.W, padx=(10 if col else 0, 2))
        self.ik_x = ttk.Entry(ik_frame, width=8)
        self.ik_x.insert(0, "0.20")
        self.ik_x.grid(row=0, column=1, padx=2)
        self.ik_y = ttk.Entry(ik_frame, width=8)
        self.ik_y.insert(0, "0.00")
        self.ik_y.grid(row=0, column=3, padx=2)
        self.ik_z = ttk.Entry(ik_frame, width=8)
        self.ik_z.insert(0, "0.35")
        self.ik_z.grid(row=0, column=5, padx=2)

        # Optional orientation (collapsed by default — advanced)
        self.ik_show_orient = tk.BooleanVar(value=False)
        ttk.Checkbutton(ik_frame, text="Set orientation (rx/ry/rz rad)",
                        variable=self.ik_show_orient,
                        command=self._toggle_ik_orient).grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=(4, 0))

        self._ik_orient_frame = ttk.Frame(ik_frame)
        self._ik_orient_frame.grid(row=2, column=0, columnspan=6, sticky=tk.W)
        self._ik_orient_frame.grid_remove()   # hidden initially

        for col, label in enumerate(("RX:", "RY:", "RZ:")):
            ttk.Label(self._ik_orient_frame, text=label).grid(row=0, column=col*2, sticky=tk.W, padx=(10 if col else 0, 2))
        self.ik_rx = ttk.Entry(self._ik_orient_frame, width=8)
        self.ik_rx.insert(0, "0.0")
        self.ik_rx.grid(row=0, column=1, padx=2)
        self.ik_ry = ttk.Entry(self._ik_orient_frame, width=8)
        self.ik_ry.insert(0, "0.0")
        self.ik_ry.grid(row=0, column=3, padx=2)
        self.ik_rz = ttk.Entry(self._ik_orient_frame, width=8)
        self.ik_rz.insert(0, "0.0")
        self.ik_rz.grid(row=0, column=5, padx=2)

        # IK buttons
        ik_btn_frame = ttk.Frame(ik_frame)
        ik_btn_frame.grid(row=3, column=0, columnspan=6, pady=(8, 0))
        ttk.Button(ik_btn_frame, text="Move to XYZ",
                   command=self._ik_move).grid(row=0, column=0, padx=5)
        ttk.Button(ik_btn_frame, text="Solve IK (preview)",
                   command=self._ik_preview).grid(row=0, column=1, padx=5)
        ttk.Button(ik_btn_frame, text="Get EE Position",
                   command=self._ik_get_ee).grid(row=0, column=2, padx=5)

        # Control buttons
        button_frame = ttk.Frame(main_frame, padding="10")
        button_frame.grid(row=3, column=0, columnspan=2, pady=10)
        
        ttk.Button(button_frame, text="Move to Position", 
                  command=self._move_to_position).grid(row=0, column=0, padx=5)
        ttk.Button(button_frame, text="Home Position", 
                  command=self._move_to_home).grid(row=0, column=1, padx=5)
        ttk.Button(button_frame, text="Get Current Position", 
                  command=self._get_current_position).grid(row=0, column=2, padx=5)
        ttk.Button(button_frame, text="Stop", 
                  command=self._stop_robot).grid(row=0, column=3, padx=5)
        
        # Preset positions
        preset_frame = ttk.LabelFrame(main_frame, text="Preset Positions", padding="10")
        preset_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        ttk.Button(preset_frame, text="Position 1",
                  command=lambda: self._load_preset(config.PRESET_POSITIONS["position_1"])).grid(row=0, column=0, padx=5)
        ttk.Button(preset_frame, text="Position 2",
                  command=lambda: self._load_preset(config.PRESET_POSITIONS["position_2"])).grid(row=0, column=1, padx=5)
        ttk.Button(preset_frame, text="Position 3",
                  command=lambda: self._load_preset(config.PRESET_POSITIONS["position_3"])).grid(row=0, column=2, padx=5)

        # Synchronization control
        sync_frame = ttk.LabelFrame(main_frame, text="Synchronization", padding="10")
        sync_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        self.sync_var = tk.BooleanVar(value=config.ENABLE_SYNC)
        ttk.Checkbutton(sync_frame, text="Enable Physical -> Digital Sync",
                       variable=self.sync_var,
                       command=self._toggle_sync).grid(row=0, column=0, padx=5)

        ttk.Label(sync_frame, text="(Physical robot movements will update Webots)").grid(row=0, column=1, padx=5)

        # Status display
        status_frame = ttk.LabelFrame(main_frame, text="Robot Status", padding="10")
        status_frame.grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        self.status_summary = ttk.Label(status_frame, text="Status: --")
        self.status_summary.grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        
        self.status_text = tk.Text(status_frame, height=10, width=70)
        self.status_text.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        scrollbar = ttk.Scrollbar(status_frame, orient=tk.VERTICAL, command=self.status_text.yview)
        scrollbar.grid(row=1, column=1, sticky=(tk.N, tk.S))
        self.status_text['yscrollcommand'] = scrollbar.set
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        status_frame.rowconfigure(1, weight=1)
        main_frame.rowconfigure(6, weight=1)
    
    # ------------------------------------------------------------------
    # IK helpers
    # ------------------------------------------------------------------

    def _toggle_ik_orient(self):
        """Show/hide the optional orientation row."""
        if self.ik_show_orient.get():
            self._ik_orient_frame.grid()
        else:
            self._ik_orient_frame.grid_remove()

    def _get_ik_values(self):
        """Parse the XYZ (and optional RPY) entries. Returns (x,y,z,rx,ry,rz) or None."""
        try:
            x = float(self.ik_x.get())
            y = float(self.ik_y.get())
            z = float(self.ik_z.get())
            rx = float(self.ik_rx.get()) if self.ik_show_orient.get() else 0.0
            ry = float(self.ik_ry.get()) if self.ik_show_orient.get() else 0.0
            rz = float(self.ik_rz.get()) if self.ik_show_orient.get() else 0.0
            return x, y, z, rx, ry, rz
        except ValueError:
            messagebox.showerror("Error", "Invalid XYZ/RPY values. Please enter numbers.")
            return None

    def _ik_move(self):
        """Solve IK and send the resulting joint command to the robot."""
        vals = self._get_ik_values()
        if vals is None:
            return
        x, y, z, rx, ry, rz = vals
        target = self._get_target()
        speed = self.speed_var.get()
        position_only = not self.ik_show_orient.get()

        success = self.orchestrator.move_to_xyz(
            x, y, z, rx, ry, rz,
            target=target, speed=speed,
            position_only=position_only,
        )
        if success:
            self._update_status(f"IK move → ({x:.3f}, {y:.3f}, {z:.3f}) m")
        else:
            messagebox.showerror("IK Error",
                                 "Inverse kinematics could not find a solution.\n"
                                 "The target may be out of reach.")

    def _ik_preview(self):
        """Solve IK and show joint angles in the joint entries (without moving)."""
        vals = self._get_ik_values()
        if vals is None:
            return
        x, y, z, rx, ry, rz = vals
        position_only = not self.ik_show_orient.get()

        try:
            from backend.ik.ik_service import IKSolver
            solver = IKSolver()
            if position_only:
                joints = solver.solve_position(x, y, z)
            else:
                joints = solver.solve(x, y, z, rx, ry, rz)
        except Exception as e:
            messagebox.showerror("IK Error", str(e))
            return

        if joints is None:
            messagebox.showwarning("IK", "No solution found for the given target.")
            return

        # Load result into joint entries so the student can inspect / tweak
        for entry, value in zip(self.joint_entries, joints):
            entry.delete(0, tk.END)
            entry.insert(0, f"{value:.4f}")

        self._update_status(
            f"IK preview ({x:.3f}, {y:.3f}, {z:.3f}) → "
            f"{[f'{j:.3f}' for j in joints]}"
        )

    def _ik_get_ee(self):
        """Read current joint positions and display the FK end-effector position."""
        try:
            result = self.orchestrator.get_end_effector_position(use_digital=True)
        except Exception as e:
            messagebox.showerror("FK Error", str(e))
            return

        if result is None:
            self._update_status("Could not read end-effector position (robot not ready?)")
            return

        x, y, z = result
        # Populate the XYZ entries for convenience
        self.ik_x.delete(0, tk.END); self.ik_x.insert(0, f"{x:.4f}")
        self.ik_y.delete(0, tk.END); self.ik_y.insert(0, f"{y:.4f}")
        self.ik_z.delete(0, tk.END); self.ik_z.insert(0, f"{z:.4f}")
        self._update_status(f"EE position: x={x:.4f}, y={y:.4f}, z={z:.4f} m")

    def _get_target(self) -> TargetRobot:
        """Get selected target robot."""
        target_map = {
            "digital": TargetRobot.DIGITAL_ONLY,
            "physical": TargetRobot.PHYSICAL_ONLY,
            "both": TargetRobot.BOTH
        }
        return target_map[self.target_var.get()]
    
    def _get_joint_values(self) -> Optional[list]:
        """Get joint values from entries."""
        try:
            values = [float(entry.get()) for entry in self.joint_entries]
            return values
        except ValueError:
            messagebox.showerror("Error", "Invalid joint values. Please enter numbers.")
            return None
    
    def _move_to_position(self):
        """Move robot to specified joint positions."""
        values = self._get_joint_values()
        if values is None:
            return
        
        # Validate positions
        joint_pos = JointPosition.from_list(values)
        if not joint_pos.validate():
            messagebox.showwarning("Warning", 
                                 "Joint positions may be outside safe limits!")
        
        # Send command
        target = self._get_target()
        speed = self.speed_var.get()
        
        success = self.orchestrator.move_joint(values, target=target, speed=speed)
        if success:
            self._update_status(f"Moving to position: {[f'{v:.3f}' for v in values]}")
        else:
            messagebox.showerror("Error", "Failed to send movement command")
    
    def _move_to_home(self):
        """Move robot to home position."""
        home_values = [0.0] * 6
        for entry, value in zip(self.joint_entries, home_values):
            entry.delete(0, tk.END)
            entry.insert(0, str(value))
        
        self._move_to_position()
    
    def _get_current_position(self):
        """Get and display current robot positions."""
        target = self._get_target()
        
        if target == TargetRobot.DIGITAL_ONLY or target == TargetRobot.BOTH:
            digital_pos = self.orchestrator.get_digital_position()
            if digital_pos:
                self._update_status(f"Digital position: {[f'{v:.3f}' for v in digital_pos]}")
                # Update entries with digital position
                for entry, value in zip(self.joint_entries, digital_pos):
                    entry.delete(0, tk.END)
                    entry.insert(0, f"{value:.3f}")
        
        if target == TargetRobot.PHYSICAL_ONLY or target == TargetRobot.BOTH:
            physical_pos = self.orchestrator.get_physical_position()
            if physical_pos:
                self._update_status(f"Physical position: {[f'{v:.3f}' for v in physical_pos]}")
    
    def _stop_robot(self):
        """Stop robot movement."""
        from backend.controller.command import RobotCommand, CommandType
        
        command = RobotCommand(
            command_type=CommandType.STOP,
            target=self._get_target()
        )
        
        if self.orchestrator.send_command(command):
            self._update_status("Robot stopped")
    
    def _load_preset(self, positions: list):
        """Load preset position into entry fields."""
        for entry, value in zip(self.joint_entries, positions):
            entry.delete(0, tk.END)
            entry.insert(0, f"{value:.3f}")
    
    def _toggle_sync(self):
        """Toggle synchronization."""
        if self.sync_var.get():
            self.orchestrator.enable_sync()
            self._update_status("Synchronization enabled")
        else:
            self.orchestrator.disable_sync()
            self._update_status("Synchronization disabled")
    
    def _update_status(self, message: str):
        """Update status text."""
        timestamp = time.strftime("%H:%M:%S")
        self.status_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.status_text.see(tk.END)
    
    def _start_status_updates(self):
        """Start periodic status updates."""
        self._running = True
        self._update_thread = threading.Thread(target=self._status_update_loop, daemon=True)
        self._update_thread.start()
    
    def _status_update_loop(self):
        """Periodic status update loop."""
        while self._running:
            try:
                # Get status from orchestrator
                status = self.orchestrator.get_status()
                
                # Update status display (in main thread)
                self.root.after(0, self._display_status, status)
                
                time.sleep(config.GUI_UPDATE_INTERVAL)
                
            except Exception as e:
                print(f"Status update error: {e}")
    
    def _display_status(self, status: dict):
        """Display status information."""
        # This runs in the main thread
        digital = status.get("digital_robot") or {}
        physical = status.get("physical_robot") or {}

        digital_state = "on" if digital.get("running") else "off"
        physical_state = "connected" if physical.get("connected") else "disconnected"
        sync_state = "on" if status.get("sync_enabled") else "off"

        summary = f"Status: digital={digital_state}, physical={physical_state}, sync={sync_state}"
        self.status_summary.config(text=summary)
    
    def run(self):
        """Run the GUI main loop."""
        try:
            self.root.mainloop()
        finally:
            self._running = False
    
    def cleanup(self):
        """Cleanup resources."""
        self._running = False
        if self._update_thread:
            self._update_thread.join(timeout=1.0)


def create_gui(orchestrator: RobotOrchestrator) -> RobotControlGUI:
    """
    Create and return GUI instance.
    
    Args:
        orchestrator: Robot orchestrator instance
    
    Returns:
        GUI instance
    """
    return RobotControlGUI(orchestrator)
