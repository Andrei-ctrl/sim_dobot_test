from controller import Robot

robot = Robot()
timestep = int(robot.getBasicTimeStep())

belt_node = robot.getFromDef("LEFT_BELT")
belt_speed_field = belt_node.getField("speed")

rx = robot.getDevice("rx")
rx.enable(timestep)

speed = 0.0

while robot.step(timestep) != -1:
    while rx.getQueueLength() > 0:
        msg = rx.getString().strip()
        rx.nextPacket()
        print(f"[BELT] Received message: '{msg}'")

        if msg == "START":
            speed = 1.0
        elif msg == "STOP":
            speed = 0.0
        else:
            # allow numeric speed
            try:
                speed = float(msg)
            except ValueError:
                pass

        belt_speed_field.setSFFloat(speed)