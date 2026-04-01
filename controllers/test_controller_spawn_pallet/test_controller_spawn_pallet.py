from controller import Robot

robot = Robot()
timestep = int(robot.getBasicTimeStep())
left_belt_channel = 1
left_spawner_channel = 4
right_belt_channel = 2
right_spawner_channel = 3

# Emitter for pallet spawner
tx = robot.getDevice("tx")

pallet_spawned = False
belt_started = False

meter_to_travel = 2.0  # meters
conveyor_speed = 0.75  # m/s
time_to_run = meter_to_travel / conveyor_speed

while robot.step(timestep) != -1:
    t = robot.getTime()
    
    # Spawn pallet at t=1.0s
    if not pallet_spawned and t >= 1.0:
        tx.setChannel(right_spawner_channel)
        msg = "SPAWN"
        tx.send(msg.encode("utf-8"))
        pallet_spawned = True
    
    # Start belt at t=2.0s (give pallet time to settle)
    if not belt_started and t >= 2.0:
        tx.setChannel(right_belt_channel)
        msg = "0.75"
        tx.send(msg.encode("utf-8"))
        belt_started = True

    if belt_started and t >= 2.0 +time_to_run:
        tx.setChannel(right_belt_channel)
        msg = "STOP"
        tx.send(msg.encode("utf-8"))
        break  # end test after stopping belt
