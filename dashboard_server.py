#!/usr/bin/env python3
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

LATEST = {"t": 0.0, "ds": None}

INDEX_HTML = b"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Webots Sensor Dashboard (Toy)</title>
  <style>
    body { font-family: sans-serif; padding: 20px; }
    .card { border: 1px solid #ddd; border-radius: 10px; padding: 16px; max-width: 420px; }
    .big { font-size: 28px; }
    .muted { color: #666; }
  </style>
</head>
<body>
  <h2>Webots Sensor Dashboard</h2>
  <div class="card">
    <div class="muted">Last update:</div>
    <div id="t" class="big">-</div>
    <div class="muted" style="margin-top:10px;">RangeFinder ds:</div>
    <div id="ds" class="big">-</div>
  </div>

  <script>
    async function tick() {
      try {
        const r = await fetch('/latest', {cache: 'no-store'});
        const data = await r.json();
        document.getElementById('t').textContent = data.t.toFixed(3) + ' s';
        document.getElementById('ds').textContent = (data.ds === null) ? '-' : data.ds;
      } catch (e) {
        // ignore transient errors
      }
    }
    setInterval(tick, 200);
    tick();
  </script>
</body>
</html>
"""

class Handler(BaseHTTPRequestHandler):
  def _send(self, code, body, content_type="application/json"):
    self.send_response(code)
    self.send_header("Content-Type", content_type)
    self.send_header("Access-Control-Allow-Origin", "*")
    self.end_headers()
    if isinstance(body, (dict, list)):
      body = json.dumps(body).encode("utf-8")
    self.wfile.write(body)

  def do_OPTIONS(self):
    self.send_response(204)
    self.send_header("Access-Control-Allow-Origin", "*")
    self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    self.send_header("Access-Control-Allow-Headers", "Content-Type")
    self.end_headers()

  def do_GET(self):
    path = urlparse(self.path).path
    if path == "/" or path == "/index.html":
      return self._send(200, INDEX_HTML, content_type="text/html; charset=utf-8")
    if path == "/latest":
      return self._send(200, LATEST)
    return self._send(404, {"error": "not found"})

  def do_POST(self):
    path = urlparse(self.path).path
    if path != "/update":
      return self._send(404, {"error": "not found"})

    length = int(self.headers.get("Content-Length", "0"))
    raw = self.rfile.read(length).decode("utf-8", errors="replace")
    try:
      data = json.loads(raw)
      # accept only expected keys in this toy
      if "t" in data: LATEST["t"] = float(data["t"])
      if "ds" in data: LATEST["ds"] = data["ds"]
      return self._send(200, {"ok": True})
    except Exception as e:
      return self._send(400, {"ok": False, "error": str(e)})

if __name__ == "__main__":
  server = HTTPServer(("127.0.0.1", 8000), Handler)
  print("Dashboard server running at http://127.0.0.1:8000")
  server.serve_forever()
