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
    "shelf_capacity": {},
    "pallet_counts": {},
    "stock_rules": {
        "pallet_target": 5,
        "pallet_reorder_below": 3,
    },
    "sort_queue": [],
    "restock_queue": [],
    "active_tasks": [],
    "robots": {
        "sorter": {"status": "unknown", "detail": "youBot sorter"},
        "restocker": {"status": "unknown", "detail": "youBot restocker"},
        "ipr": {"status": "unknown", "detail": "IPR pick arm"},
    },
    "last_event": None,
    "last_failure": None,
    "threshold_events": [],
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
                "shelf_capacity": shelf.get("capacity", {}),
                "source": shelf.get("source") or state.get("source"),
            },
        )
    system = _load_json(os.path.join(DATA_DIR, "system_state.json"))
    if system:
        state = merge_state(state, system)
    pallet = _load_json(os.path.join(DATA_DIR, "pallet_counts.json"))
    if pallet and pallet.get("counts"):
        state["pallet_counts"] = pallet["counts"]
        if pallet.get("stock_rules"):
            state["stock_rules"] = pallet["stock_rules"]
    sort_queue = _load_json(os.path.join(DATA_DIR, "sort_queue.json"), default=[])
    if isinstance(sort_queue, list) and sort_queue and not state.get("sort_queue"):
        state["sort_queue"] = sort_queue
    restock_queue = _load_json(os.path.join(DATA_DIR, "restock_queue.json"), default=[])
    if isinstance(restock_queue, list) and restock_queue and not state.get("restock_queue"):
        state["restock_queue"] = restock_queue
    if not state.get("stock_rules"):
        state["stock_rules"] = dict(DEFAULT_STATE["stock_rules"])
    failure = _load_json(os.path.join(DATA_DIR, "last_failure.json"))
    if failure and not state.get("last_failure"):
        state["last_failure"] = failure
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
    .event-failure {
      background: #2a1414;
      border-left-color: var(--bad);
    }
    .event-threshold {
      background: #14202a;
      border-left-color: var(--warn);
    }
    .empty { color: var(--muted); font-size: 0.85rem; }
    .low { color: var(--bad); font-weight: 600; }
    .full { color: var(--warn); font-weight: 600; }
    .ok { color: var(--ok); }
    .hint { font-size: 0.75rem; color: var(--muted); margin-top: 8px; }
    .sensor { margin-top: 12px; font-size: 0.8rem; color: var(--muted); }
  </style>
</head>
<body>
  <h1>Factory Restock Dashboard</h1>
  <div class="subtitle">exception_handling world - task manager, sorter, restocker, IPR</div>

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
      <h2>Stock &amp; Shelves</h2>
      <div id="inventory"><div class="empty">Waiting for data...</div></div>
      <div class="hint" id="stock_legend"></div>
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

    <div class="card" style="grid-column: span 2;">
      <h2>Last Failure</h2>
      <div id="last_failure"><div class="empty">No failures</div></div>
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

    function renderStock(data) {
      const el = document.getElementById('inventory');
      const legend = document.getElementById('stock_legend');
      const shelfCounts = data.shelf_counts || {};
      const shelfCapacity = data.shelf_capacity || {};
      const palletCounts = data.pallet_counts || {};
      const rules = data.stock_rules || {};
      const palletTarget = rules.pallet_target ?? 5;
      const palletReorderBelow = rules.pallet_reorder_below ?? 3;

      const ids = new Set([
        ...Object.keys(shelfCounts),
        ...Object.keys(palletCounts),
      ]);
      if (!ids.size) {
        el.innerHTML = '<div class="empty">Waiting for data...</div>';
        legend.textContent = '';
        return;
      }

      const rows = [...ids].sort().map(id => {
        const cap = shelfCapacity[id] || {};
        const shelfNow = shelfCounts[id] ?? cap.count ?? '-';
        const shelfMax = cap.max ?? data.baseline_shelf_counts?.[id] ?? 9;
        const shelfFull = typeof shelfNow === 'number' && typeof shelfMax === 'number' && shelfNow >= shelfMax;

        const palletNow = palletCounts[id];
        const palletText = typeof palletNow === 'number' ? `${palletNow} / ${palletTarget}` : '- / ' + palletTarget;
        const palletLow = typeof palletNow === 'number' && palletNow < palletReorderBelow;

        let status = 'OK';
        let statusClass = 'ok';
        if (palletLow) {
          status = 'Reorder pallet';
          statusClass = 'low';
        } else if (shelfFull) {
          status = 'Shelf full';
          statusClass = 'full';
        }

        return `<tr>
          <td>${id}</td>
          <td class="${shelfFull ? 'full' : ''}">${shelfNow} / ${shelfMax}</td>
          <td class="${palletLow ? 'low' : ''}">${palletText}</td>
          <td class="${statusClass}">${status}</td>
        </tr>`;
      }).join('');

      el.innerHTML = `<table>
        <thead><tr>
          <th>Product</th>
          <th>Front shelf (items / max)</th>
          <th>Stock pallet (boxes / ${palletTarget})</th>
          <th>Status</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
      legend.textContent =
        `Front shelf: item count from shelf monitoring (max 9). ` +
        `Stock pallet: live boxes on warehouse pallet (reorder when below ${palletReorderBelow}).`;
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

    function renderEvent(ev, elId, emptyText) {
      const el = document.getElementById(elId);
      if (!ev) {
        el.innerHTML = `<div class="empty">${emptyText}</div>`;
        return;
      }
      let cls = 'event';
      if (ev.event === 'robot_failure') cls += ' event-failure';
      else if (ev.event === 'threshold_check' || ev.event === 'threshold_skip') cls += ' event-threshold';
      const parts = Object.entries(ev).map(([k, v]) => `<strong>${k}</strong>: ${v}`).join(' | ');
      el.innerHTML = `<div class="${cls}">${parts}</div>`;
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
        renderStock(data);
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
        renderEvent(data.last_event, 'last_event', 'No events yet');
        renderEvent(data.last_failure, 'last_failure', 'No failures');
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
        elif key in ("pallet_counts", "shelf_counts", "shelf_capacity") and isinstance(
            value, dict
        ):
            if not value:
                continue
            merged[key] = value
        elif key == "last_failure" and value:
            merged[key] = value
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
