from controller import Supervisor

TIME_STEP = 32


class IprPickDemo:
    def __init__(self):
        self.robot = Supervisor()
                # Bottle spawning setup
        self.root = self.robot.getRoot()
        self.children = self.root.getField("children")

        self.spawn_position = [8.87145140667246, 1.1187441034141428, 0.14049550861833085]
        self.spawn_rotation = [
            0.00013521511490656202,
            -3.11940885354833e-05,
            0.9999999903719008,
            0.09627163371207904
        ]

        self.spawn_count = 0
        self.spawned_bottles = []
        self.max_spawned_bottles = 5

        self.motor_names = [
            "base",
            "upperarm",
            "forearm",
            "wrist",
            "rotational_wrist"
        ]

        self.motors = []

        for name in self.motor_names:
            motor = self.robot.getDevice(name)

            if motor is None:
                print(f"[ERROR] Motor not found: {name}")
            else:
                motor.setVelocity(1)
                self.motors.append(motor)
                print(f"[IPR] Motor loaded: {name}")

        self.gripper_left = self.robot.getDevice("gripper::left")
        self.gripper_right = self.robot.getDevice("gripper::right")

        if self.gripper_left is None:
            print("[ERROR] gripper::left not found")
        else:
            self.gripper_left.setVelocity(0.5)
            print("[IPR] Gripper loaded: gripper::left")

        if self.gripper_right is None:
            print("[ERROR] gripper::right not found")
        else:
            self.gripper_right.setVelocity(0.5)
            print("[IPR] Gripper loaded: gripper::right")

        self.poses = [
            # name, [base, upperarm, forearm, wrist, rotational_wrist], gripper, duration

            ("base_min", [0.0, 0.0, 0.0, 0.0, 0.0], 1.0, 200),
            ("pre_pick", [0.0, -2, 1, -1, 0.0], 1.0, 160),
            ("pick", [0.0, -2, 1, -1, 0.0], 0.0, 160),
            ("base_min_return", [0.0, 0.0, 0.0, 0.0, 0.0], 0.0, 200),
            ("turn_to_conveyer", [1.5, -1, 1, -2, 0.0], 0.0, 300),
            ("turn_to_conveyer", [1.5, -1, 1, -2, 0.0], 1.0, 300),

            #("home", [0.0, 0.0, 0.0, 0.0, 0.0], 1.0, 120),

            # rotate toward bottle
            #("turn_to_bottle", [-0.45, 0.0, 0.0, 0.0, 0.0], 1.0, 120),

            # bend close to bottle, still open
            #("pre_pick", [-0.45, 0.25, 0.35, -0.2, 0.0], 1.0, 160),

            # final pickup pose, bottle should be centered between fingers
            #("pick", [-0.45, 0.35, 0.45, -0.35, 0.0], 1.0, 200),

            # wait before closing
            #("settle", [-0.45, 0.35, 0.45, -0.35, 0.0], 1.0, 80),

            # close gradually
            #("grip_soft", [-0.45, 0.35, 0.45, -0.35, 0.0], 0.7, 80),
            #("grip_medium", [-0.45, 0.35, 0.45, -0.35, 0.0], 0.45, 80),
            #("grip", [-0.45, 0.35, 0.45, -0.35, 0.0], 0.25, 160),

            # lift slowly
            #("lift", [-0.45, -0.15, 0.75, -0.2, 0.0], 0.25, 250),

            # move to conveyor
            #("place_on_belt", [0.8, -0.10, 0.65, -0.15, 0.0], 0.25, 300),

            # release
            #("release", [0.8, 0.10, 0.45, -0.25, 0.0], 1.0, 140),
        ]

        self.pose_index = 0
        self.pose_step = 0
        self.last_announced_pose = None

        print("[SPAWNER] Bottle spawner initialized")
        print("[IPR] Pick demo initialized")
        print("[IPR] Physical grip mode: bottle is NOT teleported")
        #self.spawn_bottle()

    def set_pose(self, values):
        for motor, value in zip(self.motors, values):
            motor.setPosition(value)

    def set_gripper(self, value):
        # IPR gripper maxPosition is 1.22171 according to the PROTO.
        # 1.0 = open, lower values = more closed.
        safe_value = min(1.0, max(0.0, value))

        if self.gripper_left is not None:
            self.gripper_left.setPosition(safe_value)

        if self.gripper_right is not None:
            self.gripper_right.setPosition(safe_value)
            
    def spawn_bottle(self):
        bottle_def = f"DEMO_BOTTLE_{self.spawn_count}"

        node_string = f"""
        DEF {bottle_def} BeerBottle {{
        translation {self.spawn_position[0]} {self.spawn_position[1]} {self.spawn_position[2]}
        rotation {self.spawn_rotation[0]} {self.spawn_rotation[1]} {self.spawn_rotation[2]} {self.spawn_rotation[3]}
        name "BEER_BOTTLE"
        mass 0.4
        }}
        """

        self.children.importMFNodeFromString(-1, node_string)

        new_bottle = self.robot.getFromDef(bottle_def)

        if new_bottle is not None:
            self.spawned_bottles.append(new_bottle)
            print(f"[SPAWNER] Spawned BeerBottle: {bottle_def}")
        else:
            print(f"[SPAWNER ERROR] Could not spawn {bottle_def}")

        self.spawn_count += 1

        if len(self.spawned_bottles) > self.max_spawned_bottles:
            old_bottle = self.spawned_bottles.pop(0)
            old_bottle.remove()
            print("[SPAWNER] Removed oldest bottle")

    def run(self):
        while self.robot.step(TIME_STEP) != -1:
            label, pose, gripper, duration = self.poses[self.pose_index]

            self.set_pose(pose)
            self.set_gripper(gripper)

            if label != self.last_announced_pose:
                print(f"[DEBUG] pose={label}, joints={pose}, gripper={gripper}")

                if label == "home":
                    print("[IPR] Home")
                elif label == "turn_to_bottle":
                    print("[IPR] Turning toward bottle")
                elif label == "pre_pick":
                    print("[IPR] Moving near bottle")
                elif label == "pick":
                    print("[IPR] Aligning fingers around bottle")
                elif label == "settle":
                    print("[IPR] Waiting before grip")
                elif label == "grip_soft":
                    print("[IPR] Soft grip")
                elif label == "grip_medium":
                    print("[IPR] Medium grip")
                elif label == "grip":
                    print("[IPR] Bottle gripped")
                elif label == "lift":
                    print("[IPR] Lifting bottle")
                elif label == "place_on_belt":
                    print("[IPR] Moving to conveyor")
                elif label == "release":
                    print("[IPR] Releasing bottle")

                self.last_announced_pose = label

            self.pose_step += 1

            if self.pose_step >= duration:
                self.pose_step = 0
                self.pose_index += 1

                # If the sequence is finished, restart and spawn a new bottle.
                if self.pose_index >= len(self.poses):
                    self.pose_index = 0
                    self.spawn_bottle()


if __name__ == "__main__":
    IprPickDemo().run()