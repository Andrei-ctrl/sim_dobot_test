from controller import Robot
import json
import time
import urllib.request

robot = Robot()
timestep = int(robot.getBasicTimeStep())

ds = robot.getDevice("distance sensor")
ds.enable(timestep)

DASHBOARD_URL = "http://127.0.0.1:8000/update"

# send at ~10 Hz to keep it light
SEND_PERIOD_S = 0.1
last_send = 0.0

def post_json(url: str, payload: dict) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=0.2) as resp:
            resp.read()
    except Exception:
        pass

while robot.step(timestep) != -1:
    now = robot.getTime()
    if now - last_send >= SEND_PERIOD_S:
        last_send = now
        payload = {
            "t": now,
            "ds": ds.getValue(),
        }
        post_json(DASHBOARD_URL, payload)
