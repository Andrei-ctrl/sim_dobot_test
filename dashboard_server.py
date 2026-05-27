#!/usr/bin/env python3
"""Local dashboard for Webots factory sim: robots, tasks, inventory."""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

DEFAULT_STATE = {
    "sim_time": 0.0,
    "t": 0.0,
    "ds": None,
    "source": "",
    "inventory": {},
    "shelf_counts": {},
    "baseline_shelf_counts": {},
    "sort_queue": [],
    "restock_queue": [],
    "active_tasks": [],
    "robots": {
        "sorter": {"status": "unknown", "detail": "youBot sorter"},
        "restocker": {"status": "unknown", "detail": "youBot restocker"},
        "ipr": {"status": "unknown", "detail": "IPR pick arm"},
    },
    "last_event": None,
}

LATEST = dict(DEFAULT_STATE)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")


def _load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default if default is not None else {}


def state_with_disk():
    """Merge in-memory dashboard state with data/*.json from sim controllers."""
    state = dict(LATEST)
    shelf = _load_json(os.path.join(DATA_DIR, "shelf_counts.json"))
    if shelf:
        state = merge_state(
            state,
            {
                "sim_time": shelf.get("sim_time"),
                "shelf_counts": shelf.get("counts", {}),
                "baseline_shelf_counts": shelf.get("baseline_counts", {}),
                "source": shelf.get("source") or state.get("source"),
            },
        )
    inventory = _load_json(os.path.join(DATA_DIR, "inventory.json"))
    if inventory:
        counts = state.get("shelf_counts") or {}
        merged_inv = dict(inventory)
        for product_id, count in counts.items():
            item = dict(merged_inv.get(product_id) or {})
            item["front_stock"] = int(count) * 2
            merged_inv[product_id] = item
        state = merge_state(state, {"inventory": merged_inv})
    sort_queue = _load_json(os.path.join(DATA_DIR, "sort_queue.json"), default=[])
    if isinstance(sort_queue, list) and sort_queue:
        state["sort_queue"] = sort_queue
    restock_queue = _load_json(os.path.join(DATA_DIR, "restock_queue.json"), default=[])
    if isinstance(restock_queue, list) and restock_queue:
        state["restock_queue"] = restock_queue
    system = _load_json(os.path.join(DATA_DIR, "system_state.json"))
    if system:
        state = merge_state(state, system)
    return state

INDEX_HTML = b"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Factory Restock Dashboard</title>
  <style>
    :root {
      --bg: #0f1419;
      --panel: #1a2332;
      --border: #2d3a4f;
      --text: #e7ecf3;
      --muted: #8b9cb3;
      --accent: #3d8bfd;
      --ok: #3dd68c;
      --warn: #ffb020;
      --bad: #ff6b6b;
    }
    * { box-sizing: border-box; }
    body {
      font-family: "Segoe UI", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      margin: 0;
      padding: 20px 24px 40px;
    }
    h1 { margin: 0 0 4px; font-size: 1.5rem; font-weight: 600; }
    .subtitle { color: var(--muted); margin-bottom: 20px; font-size: 0.9rem; }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px;
    }
    .card h2 {
      margin: 0 0 12px;
      font-size: 0.85rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--muted);
    }
    .sim-time { font-size: 1.75rem; font-weight: 600; color: var(--accent); }
    table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border); }
    th { color: var(--muted); font-weight: 500; }
    .badge {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
    }
    .badge-idle { background: #243044; color: var(--muted); }
    .badge-active { background: #1e3a2f; color: var(--ok); }
    .badge-warn { background: #3a2e14; color: var(--warn); }
    .badge-unknown { background: #2a2438; color: #b8a8d8; }
    .robot-row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--border); }
    .robot-row:last-child { border-bottom: none; }
    .robot-name { font-weight: 600; }
    .robot-detail { font-size: 0.8rem; color: var(--muted); margin-top: 2px; }
    .event {
      background: #152238;
      border-left: 3px solid var(--accent);
      padding: 10px 12px;
      border-radius: 0 8px 8px 0;
      font-size: 0.85rem;
    }
    .empty { color: var(--muted); font-size: 0.85rem; }
    .low { color: var(--bad); font-weight: 600; }
    .sensor { margin-top: 12px; font-size: 0.8rem; color: var(--muted); }
  </style>
</head>
<body>
  <h1>Factory Restock Dashboard</h1>
  <div class="subtitle">triger_trashhold world - task manager, sorter, restocker, IPR</div>

  <div class="grid">
    <div class="card">
      <h2>Simulation</h2>
      <div class="sim-time" id="sim_time">-</div>
      <div class="sensor">Source: <span id="source">-</span></div>
      <div class="sensor">RangeFinder ds: <span id="ds">-</span></div>
    </div>

    <div class="card">
      <h2>Robots</h2>
      <div id="robots"></div>
    </div>

    <div class="card" style="grid-column: span 2;">
      <h2>Inventory &amp; Front Shelves</h2>
      <div id="inventory"><div class="empty">Waiting for data...</div></div>
    </div>

    <div class="card">
      <h2>Sort Queue</h2>
      <div id="sort_queue"><div class="empty">No sort tasks</div></div>
    </div>

    <div class="card">
      <h2>Restock Queue</h2>
      <div id="restock_queue"><div class="empty">No restock tasks</div></div>
    </div>

    <div class="card" style="grid-column: span 2;">
      <h2>Last Event</h2>
      <div id="last_event"><div class="empty">No events yet</div></div>
    </div>
  </div>

  <script>
    function badgeClass(status) {
      const s = (status || '').toLowerCase();
      if (s === 'idle' || s === 'done') return 'badge-idle';
      if (s === 'active' || s === 'busy' || s === 'running') return 'badge-active';
      if (s === 'waiting' || s === 'pending') return 'badge-warn';
      return 'badge-unknown';
    }

    function renderRobots(robots) {
      const el = document.getElementById('robots');
      if (!robots || !Object.keys(robots).length) {
        el.innerHTML = '<div class="empty">No robot status</div>';
        return;
      }
      el.innerHTML = Object.entries(robots).map(([name, info]) => {
        const status = (info && info.status) || 'unknown';
        const detail = (info && info.detail) || '';
        return `<div class="robot-row">
          <div>
            <div class="robot-name">${name}</div>
            <div class="robot-detail">${detail}</div>
          </div>
          <span class="badge ${badgeClass(status)}">${status}</span>
        </div>`;
      }).join('');
    }

    function renderInventory(inventory, shelfCounts, baselines) {
      const el = document.getElementById('inventory');
      const ids = new Set([
        ...Object.keys(inventory || {}),
        ...Object.keys(shelfCounts || {}),
      ]);
      if (!ids.size) {
        el.innerHTML = '<div class="empty">Waiting for data...</div>';
        return;
      }
      const rows = [...ids].sort().map(id => {
        const item = (inventory || {})[id] || {};
        const front = item.front_stock ?? '-';
        const storage = item.storage_stock ?? '-';
        const threshold = item.threshold ?? '-';
        const shelf = shelfCounts[id] ?? '-';
        const base = baselines[id] ?? '-';
        const low = typeof front === 'number' && typeof threshold === 'number' && front < threshold;
        return `<tr>
          <td>${id}</td>
          <td class="${low ? 'low' : ''}">${front}</td>
          <td>${storage}</td>
          <td>${threshold}</td>
          <td>${shelf} / ${base}</td>
        </tr>`;
      }).join('');
      el.innerHTML = `<table>
        <thead><tr>
          <th>Product</th><th>Front</th><th>Storage</th><th>Threshold</th><th>Shelf (now/base)</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
    }

    function renderTaskTable(elId, tasks, columns) {
      const el = document.getElementById(elId);
      if (!tasks || !tasks.length) {
        el.innerHTML = '<div class="empty">Empty</div>';
        return;
      }
      const head = columns.map(c => `<th>${c.label}</th>`).join('');
      const body = tasks.slice(-8).reverse().map(task => {
        return '<tr>' + columns.map(c => `<td>${c.fmt(task)}</td>`).join('') + '</tr>';
      }).join('');
      el.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
    }

    function renderEvent(ev) {
      const el = document.getElementById('last_event');
      if (!ev) {
        el.innerHTML = '<div class="empty">No events yet</div>';
        return;
      }
      const parts = Object.entries(ev).map(([k, v]) => `<strong>${k}</strong>: ${v}`).join(' | ');
      el.innerHTML = `<div class="event">${parts}</div>`;
    }

    async function tick() {
      try {
        const r = await fetch('/api/state', {cache: 'no-store'});
        const data = await r.json();
        const t = data.sim_time ?? data.t ?? 0;
        document.getElementById('sim_time').textContent = Number(t).toFixed(2) + ' s';
        document.getElementById('source').textContent = data.source || '-';
        document.getElementById('ds').textContent = (data.ds === null || data.ds === undefined) ? '-' : data.ds;
        renderRobots(data.robots);
        renderInventory(data.inventory, data.shelf_counts, data.baseline_shelf_counts);
        renderTaskTable('sort_queue', data.sort_queue, [
          {label: 'Seq', fmt: t => t.seq ?? '-'},
          {label: 'Product', fmt: t => t.product_id ?? '-'},
          {label: 'Type', fmt: t => t.task_type ?? '-'},
          {label: 'Status', fmt: t => t.status ?? 'pending'},
          {label: 'Reason', fmt: t => (t.reason || '').slice(0, 40)},
        ]);
        renderTaskTable('restock_queue', data.restock_queue, [
          {label: 'Seq', fmt: t => t.seq ?? '-'},
          {label: 'Product', fmt: t => t.product_id ?? '-'},
          {label: 'Status', fmt: t => t.status ?? 'pending'},
          {label: 'Reason', fmt: t => (t.reason || '').slice(0, 50)},
        ]);
        renderEvent(data.last_event);
      } catch (e) {
        // ignore transient errors
      }
    }
    setInterval(tick, 400);
    tick();
  </script>
</body>
</html>
"""


def merge_state(current, incoming):
    """Shallow merge with nested dict updates for robots/inventory."""
    merged = dict(current)
    for key, value in incoming.items():
        if key in ("robots", "inventory") and isinstance(value, dict):
            nested = dict(merged.get(key) or {})
            nested.update(value)
            merged[key] = nested
        elif value is not None:
            merged[key] = value
    if "sim_time" in incoming:
        merged["t"] = incoming["sim_time"]
    elif "t" in incoming:
        merged["sim_time"] = incoming["t"]
    return merged


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

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
        if path in ("/", "/index.html"):
            return self._send(200, INDEX_HTML, content_type="text/html; charset=utf-8")
        if path in ("/latest", "/api/state"):
            return self._send(200, state_with_disk())
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/update":
            return self._send(404, {"error": "not found"})

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
            global LATEST
            LATEST = merge_state(LATEST, data)
            return self._send(200, {"ok": True})
        except Exception as e:
            return self._send(400, {"ok": False, "error": str(e)})


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 8000), Handler)
    print("Dashboard server running at http://127.0.0.1:8000")
    server.serve_forever()
