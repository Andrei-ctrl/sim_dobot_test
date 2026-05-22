from controller import Robot

TIME_STEP = 32

robot = Robot()
print("[YOUBOT SORTER] Safe idle controller started")

while robot.step(TIME_STEP) != -1:
    # Movement is handled by grocery_supervisor to keep the demo deterministic.
    pass
