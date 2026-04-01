# controllers/dobot_wave/dobot_wave.py
from controller import Robot
import math

robot = Robot()
TIME_STEP = int(robot.getBasicTimeStep())

# Motors and sensors provided by the PROTO:
motors = [robot.getDevice(f"joint{i}") for i in range(1, 7)]
sensors = [robot.getDevice(f"joint{i}_sensor") for i in range(1, 7)]

# Enable sensors + set motor speed limits
for s in sensors:
    s.enable(TIME_STEP)
for m in motors:
    m.setVelocity(1.5)      # rad/s (tune as needed)
    m.setPosition(0.0)      # home pose

t = 0.0
k = 0
while robot.step(TIME_STEP) != -1:
    t += TIME_STEP / 1000.0

    # Simple joint targets (radians)
    motors[1].setPosition(0.6 * math.sin(1.0 * t))   # joint2
    motors[4].setPosition(1.2 * math.sin(2.5 * t))   # joint6

    # Print feedback ~2x per second
    k += 1
    if k % int(500 / TIME_STEP) == 0:
        j2 = sensors[1].getValue()
        j6 = sensors[4].getValue()
        print(f"t={t:5.2f}s | joint2={j2:+.2f} rad | joint6={j6:+.2f} rad")
