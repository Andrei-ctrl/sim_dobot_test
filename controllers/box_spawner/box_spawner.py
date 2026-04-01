from controller import Supervisor
import random

robot = Supervisor()
timestep = int(robot.getBasicTimeStep())

root = robot.getRoot()
children = root.getField("children")

spawn_every_s = 7.0
next_spawn_time = 0.0
box_count = 0

def make_box_def(i: int, x: float, y: float, z: float) -> str:
    sx = random.uniform(0.12, 0.50)
    sy = random.uniform(0.08, 0.56)
    sz = random.uniform(0.06, 0.52)
    return f"""
DEF BOX_{i} CardboardBox {{
  translation {x:.4f} {y:.4f} {z:.4f}
  rotation 0 0 1 {random.uniform(-0.4, 0.4):.4f}
  name "cardboard_box_{i}"
  size {sx:.4f} {sy:.4f} {sz:.4f}
  mass {(sx * sy * sz) * random.uniform(200, 400):.2f}
}}
"""

while robot.step(timestep) != -1:
    t = robot.getTime()
    if t >= next_spawn_time:
        # supervisor robot position
        self_node = robot.getSelf()
        tr_field = self_node.getField("translation")
        x0, y0, z0 = tr_field.getSFVec3f()

        x = x0
        y = y0
        z = z0

        node_string = make_box_def(box_count, x, y, z)
        children.importMFNodeFromString(-1, node_string)

        box_count += 1
        next_spawn_time = t + spawn_every_s
