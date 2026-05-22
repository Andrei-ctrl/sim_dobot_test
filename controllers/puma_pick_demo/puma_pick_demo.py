from controller import Supervisor

TIME_STEP = 32


class PumaPickDemo:
    def __init__(self):
        self.robot = Supervisor()

        # Arm motors
        self.motors = []

        for i in range(1, 7):
            motor_name = f"joint{i}"
            motor = self.robot.getDevice(motor_name)

            if motor is None:
                print(f"[ERROR] Motor not found: {motor_name}")
            else:
                motor.setVelocity(0.2)
                self.motors.append(motor)
                print(f"[PUMA] Motor loaded: {motor_name}")

        # Gripper motors
        self.gripper_right = self.robot.getDevice("gripper::right")
        self.gripper_left = self.robot.getDevice("gripper::left")

        for motor in self.motors:
            if motor is not None:
                motor.setVelocity(0.35)

        # Get the bottle from the Webots world.
        # IMPORTANT: the object must have DEF DEMO_BOTTLE
        self.bottle = self.robot.getFromDef("DEMO_BOTTLE")

        if self.bottle is None:
            print("[ERROR] DEMO_BOTTLE not found. Check the DEF name in Webots.")
            self.bottle_translation = None
        else:
            self.bottle_translation = self.bottle.getField("translation")
            print("[PUMA] DEMO_BOTTLE found")
        
        self.bottle_rotation = self.bottle.getField("rotation") if self.bottle else None
        

        # These coordinates must be adjusted for your scene.
        # Format: [x, y, z]
        
        # Bottle starts on pallet. This is the bottle base position.
        self.bottle_pick_position = [9.14205, 0.93318, 0.14048]
        self.bottle_gripped_position = [9.14205, 0.93318, 0.22]
        self.bottle_lift_position = [9.14205, 0.93318, 0.55]

        # Put this to the conveyor position you already found.
        # Keep z high while carrying.
        self.bottle_above_conveyor = [8.32, 0.71, 0.55]

        # Final bottle position on conveyor.
        # Tune only z if bottle is too high/low.
        self.bottle_on_conveyor = [8.32, 0.71, 0.18]
    

        self.poses = [
        #testing: move left and right to show range of motion
        #("test_left", [2.792, 0.0, 0.0, 0.0, 0.0, 0.0], 0.01, 150),
        #("test_right", [-2.792, 0.0, 0.0, 0.0, 0.0, 0.0], 0.01, 150),
        
        # Neutral start
        ("home", [0.45, 0.0, 0.0, 0.0, 0.0, 0.0], 0.01, 100),

        # Turn toward pallet/bottle
        ("turn_to_bottle", [-0.45, 0, 0.0, 0.0, 0.0, 0.0], 0.01, 100),
        ("bend_to_bottle_rotate_6", [-0.45, 0.04, 0.0, 0.0, 0.0, 1.5], 0.01, 190),
        ("reach_bottle", [-0.45, 0.04, 0.0, 0.0, -0.7, 1.5], 0.01, 190),
        ("grip", [-0.45, 0.04, 0.0, 0.0, -0.7, 1.5], 0.003, 190),
        ("release", [1, 0.05, 0.0, 0.0, 0.0, 0.0], 0.003, 90),
        ("release2", [1, 0.05, 0.0, 0.0, 0.0, 0.0], 0.01, 90)
        # Reach down toward bottle
        #("pick", [0.45, -2.35, 2.30, 0.0, 0.55, 0.0], 0.01, 140),

        # Close gripper
        #("grip", [0.45, -2.35, 2.30, 0.0, 0.55, 0.0], 0.0, 70),

        # Lift bottle up
        #("lift", [0.45, -1.70, 1.55, 0.0, 0.80, 0.0], 0.0, 120),

        # Turn toward conveyor
        #("place_on_belt", [-0.35, -1.70, 1.55, 0.0, 0.80, 0.0], 0.0, 140),

        # Lower and release
        #("release", [-0.35, -2.05, 1.90, 0.0, 0.75, 0.0], 0.01, 90),
]

        self.pose_index = 0
        self.pose_step = 0
        self.last_announced_pose = None
        
        self_node = self.robot.getSelf()
        print("[PUMA DEBUG] Self node:", self_node)
        print("[PUMA DEBUG] Robot name:", self.robot.getName())

        print("[PUMA] Arm animation controller started")
        print("[PUMA] Bottle pickup is simulated by Supervisor movement")

    def set_bottle_upright(self):
        if self.bottle_rotation is not None:
            self.bottle_rotation.setSFRotation([0, 0, 1, 0])

    def set_pose(self, values):
        for motor, value in zip(self.motors, values):
            if motor is not None:
                motor.setPosition(value)

    def set_gripper(self, value):
        safe_value = min(0.01, max(0.0, value))

        if self.gripper_right is not None:
            self.gripper_right.setPosition(safe_value)

        if self.gripper_left is not None:
            self.gripper_left.setPosition(safe_value)

    def set_bottle_position(self, position):
        if self.bottle_translation is not None:
            self.set_bottle_upright()
            self.bottle_translation.setSFVec3f(position)

            if self.bottle is not None:
                self.bottle.resetPhysics()

    def interpolate(self, start, end, progress):
        return [
            start[0] + (end[0] - start[0]) * progress,
            start[1] + (end[1] - start[1]) * progress,
            start[2] + (end[2] - start[2]) * progress,
        ]

    def move_bottle_for_state(self, label, duration):
        if self.bottle_translation is None:
            return

        progress = min(self.pose_step / max(duration, 1), 1.0)

        if label == "home":
            # Bottle stays on pallet.
            pass

        elif label == "pick":
            # Arm approaches. Do NOT move bottle yet.
            pass

        elif label == "grip":
            # Only now the bottle becomes attached.
            # Small upward correction makes it look like the gripper caught the neck.
            pos = self.interpolate(
                self.bottle_pick_position,
                self.bottle_gripped_position,
                progress
            )
            self.set_bottle_position(pos)

        elif label == "lift":
            # Lift upward: change Z.
            pos = self.interpolate(
                self.bottle_gripped_position,
                self.bottle_lift_position,
                progress
            )
            self.set_bottle_position(pos)

        elif label == "place_on_belt":
            # Move horizontally to conveyor while staying high.
            pos = self.interpolate(
                self.bottle_lift_position,
                self.bottle_above_conveyor,
                progress
            )
            self.set_bottle_position(pos)

        elif label == "release":
            # Lower onto conveyor.
            pos = self.interpolate(
                self.bottle_above_conveyor,
                self.bottle_on_conveyor,
                progress
            )
            self.set_bottle_position(pos)

    def run(self):
        while self.robot.step(TIME_STEP) != -1:
            label, pose, gripper, duration = self.poses[self.pose_index]

            self.set_pose(pose)
            self.set_gripper(gripper)
            #self.move_bottle_for_state(label, duration)

            if label != self.last_announced_pose:
                print(f"[DEBUG] Current pose: {label}, target joints: {pose}")
                
                if label == "turn_to_bottle":
                    print("[PUMA] Turning toward bottle")
                elif label == "pick":
                    print("[PUMA] Reaching toward bottle")
                elif label == "grip":
                    print("[PUMA] Bottle attached")
                elif label == "lift":
                    print("[PUMA] Lifting bottle")
                elif label == "place_on_belt":
                    print("[PUMA] Moving bottle toward conveyor")
                elif label == "release":
                    print("[PUMA] Releasing bottle on conveyor")
                elif label == "home":
                    print("[PUMA] Returning home")

                self.last_announced_pose = label

            self.pose_step += 1

            if self.pose_step >= duration:
                self.pose_step = 0
                self.pose_index = (self.pose_index + 1) % len(self.poses)


if __name__ == "__main__":
    PumaPickDemo().run()