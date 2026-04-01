from controller import Supervisor
import random
import os   
    
robot = Supervisor()
timestep = int(robot.getBasicTimeStep())

root = robot.getRoot()
children = root.getField("children")

# Setup receiver (child device of this robot)
receiver = robot.getDevice("receiver")
receiver.enable(timestep)

pallet_count = 0

def make_pallet_def(i: int, x: float, y: float, z: float) -> str:
    return f"""
DEF PALLET_{i} WoodenPallet {{
  translation {x:.4f} {y:.4f} {z:.4f}
  name "pallet_{i}"
  mass 25.0
}}
"""

def spawn_pallet():
    """Spawn a pallet at the spawner's location"""
    global pallet_count
    
    print(f"[RightPalletSpawner] Spawning pallet #{pallet_count}")
    
    # Get supervisor robot position
    self_node = robot.getSelf()
    tr_field = self_node.getField("translation")
    x0, y0, z0 = tr_field.getSFVec3f()

    x = x0 
    y = y0
    z = z0

    node_string = make_pallet_def(pallet_count, x, y, z)
    children.importMFNodeFromString(-1, node_string)

    pallet_count += 1

while robot.step(timestep) != -1:
    # Check for messages from receiver
    while receiver.getQueueLength() > 0:
        message = receiver.getString()
        print(f"[RightPalletSpawner] Received message: {message}")
        
        if message == "SPAWN":
            spawn_pallet()
        
        receiver.nextPacket()
