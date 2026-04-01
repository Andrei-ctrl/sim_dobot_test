from controller import Supervisor

spv = Supervisor()
timestep = int(spv.getBasicTimeStep())

rx = spv.getDevice("rx")
rx.enable(timestep)

belt = spv.getFromDef("RIGHT_BELT")
if belt is None:
    print("ERROR: Belt DEF not found. Set DEF PALLET_RIGHT_BELT on the conveyor node.")
    # still run so you can see prints
    belt_speed_field = None
else:
    belt_speed_field = belt.getField("speed")

RUN_SPEED = 1.0
speed = 0.0


while spv.step(timestep) != -1:
    while rx.getQueueLength() > 0:
        msg = rx.getString().strip()
        rx.nextPacket()
        print(f"[RIGHT BELT] Received message: '{msg}'")

        if msg == "START":
            speed = RUN_SPEED
        elif msg == "STOP":
            speed = 0.0
        else:
            try:
                speed = float(msg)
            except:
                pass

        belt_speed_field.setSFFloat(speed)

    # keep applying (optional, but nice if something else changes it)
    belt_speed_field.setSFFloat(speed)