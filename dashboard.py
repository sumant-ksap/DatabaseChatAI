import sqlite3

from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

DB_PATH = "yard_management.db"

# ── SQLite helpers ───────────────────────────────────────────────────────────
# Standalone demo dashboard over the bundled yard_management.db — deliberately
# separate from database.py, which is the generic Postgres/MongoDB connector
# the main chat agent (app.py) uses for user-supplied databases.

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def setup_database() -> None:
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS shipments (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tracking_number TEXT NOT NULL,
                type            TEXT NOT NULL,
                status          TEXT NOT NULL,
                carrier         TEXT,
                origin          TEXT,
                destination     TEXT,
                weight_kg       REAL,
                units           INTEGER,
                dock_door       TEXT,
                scheduled_at    TEXT,
                arrived_at      TEXT,
                departed_at     TEXT,
                created_at      TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS trailers (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                plate_number TEXT NOT NULL,
                carrier      TEXT,
                driver_name  TEXT,
                status       TEXT NOT NULL,
                shipment_id  INTEGER,
                arrived_at   TEXT,
                departed_at  TEXT
            );
            CREATE TABLE IF NOT EXISTS dock_doors (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                door_number TEXT NOT NULL,
                door_type   TEXT DEFAULT 'standard',
                status      TEXT NOT NULL,
                shipment_id INTEGER,
                assigned_at TEXT
            );
            CREATE TABLE IF NOT EXISTS yard_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type  TEXT NOT NULL,
                shipment_id INTEGER,
                trailer_id  INTEGER,
                door_number TEXT,
                notes       TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
    finally:
        conn.close()


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    cur = conn.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


# ── API endpoints ──────────────────────────────────────────────────────────────

@app.route("/api/summary")
def api_summary():
    conn = get_connection()
    try:
        statuses = {r["status"]: r["cnt"] for r in _rows(conn,
            "SELECT status, COUNT(*) as cnt FROM shipments GROUP BY status")}
        types = {r["type"]: r["cnt"] for r in _rows(conn,
            "SELECT type, COUNT(*) as cnt FROM shipments GROUP BY type")}
        docks = {r["status"]: r["cnt"] for r in _rows(conn,
            "SELECT status, COUNT(*) as cnt FROM dock_doors GROUP BY status")}
        in_yard = conn.execute(
            "SELECT COUNT(*) FROM trailers WHERE status IN ('in_yard','docked')").fetchone()[0]
        total_kg = conn.execute(
            "SELECT COALESCE(SUM(weight_kg),0) FROM shipments WHERE arrived_at LIKE '2026-06-11%'").fetchone()[0]
        return jsonify({
            "statuses": statuses,
            "types": types,
            "docks": docks,
            "trailers_in_yard": in_yard,
            "total_kg_today": round(total_kg, 1),
            "total_shipments": sum(statuses.values()),
        })
    finally:
        conn.close()


@app.route("/api/shipments")
def api_shipments():
    conn = get_connection()
    try:
        rows = _rows(conn,
            "SELECT tracking_number,type,status,carrier,origin,destination,"
            "weight_kg,units,dock_door,scheduled_at,arrived_at,departed_at "
            "FROM shipments ORDER BY COALESCE(arrived_at,scheduled_at) DESC LIMIT 20"
        )
        return jsonify(rows)
    finally:
        conn.close()


@app.route("/api/docks")
def api_docks():
    conn = get_connection()
    try:
        rows = _rows(conn,
            "SELECT d.door_number,d.door_type,d.status,d.assigned_at,"
            "s.tracking_number,s.carrier,s.type AS ship_type,s.status AS ship_status,s.units "
            "FROM dock_doors d LEFT JOIN shipments s ON d.shipment_id=s.id "
            "ORDER BY d.door_number"
        )
        return jsonify(rows)
    finally:
        conn.close()


@app.route("/api/events")
def api_events():
    conn = get_connection()
    try:
        rows = _rows(conn,
            "SELECT e.event_type,e.door_number,e.notes,e.created_at,"
            "s.tracking_number,t.plate_number "
            "FROM yard_events e "
            "LEFT JOIN shipments s ON e.shipment_id=s.id "
            "LEFT JOIN trailers t  ON e.trailer_id=t.id "
            "ORDER BY e.created_at DESC LIMIT 20"
        )
        return jsonify(rows)
    finally:
        conn.close()


# ── Dashboard HTML ─────────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>YMS Dashboard — KSAPTECH Logistics Yard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bg:      #f4f6f9;
    --surface: #ffffff;
    --border:  #dde3ea;
    --row-line:#edf1f5;
    --text:    #1f2937;
    --muted:   #64748b;
    --green:   #16a34a;
    --blue:    #1f4e9c;
    --blue-hover: #173d7a;
    --blue-soft:  #e8eef8;
    --yellow:  #d97706;
    --red:     #dc2626;
    --purple:  #6d28d9;
    --cyan:    #0e7490;
    --shadow:  0 1px 3px rgba(15, 23, 42, .08), 0 1px 2px rgba(15, 23, 42, .04);
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family:'Segoe UI','Inter',system-ui,-apple-system,sans-serif; background:var(--bg); color:var(--text); min-height:100vh; }

  /* header */
  header { background:var(--surface); border-bottom:1px solid var(--border); padding:0 28px;
           border-top:3px solid var(--blue); box-shadow:var(--shadow);
           display:flex; align-items:center; justify-content:space-between; height:60px; }
  header h1 { font-size:1.1rem; font-weight:700; letter-spacing:.3px; }
  header h1 span { color:var(--blue); }
  .header-right { display:flex; align-items:center; gap:16px; }
  .refresh-badge { font-size:.75rem; color:var(--muted); }
  .chat-link { background:var(--blue); color:#fff; border:none; border-radius:6px;
               padding:8px 16px; font-size:.85rem; font-weight:600; text-decoration:none;
               cursor:pointer; transition:background .15s; }
  .chat-link:hover { background:var(--blue-hover); }

  /* layout */
  main { padding:24px 28px; display:flex; flex-direction:column; gap:20px; }

  /* KPI cards */
  .kpi-row { display:grid; grid-template-columns:repeat(5,1fr); gap:16px; }
  .kpi { background:var(--surface); border:1px solid var(--border); border-radius:8px;
         box-shadow:var(--shadow); border-top:3px solid var(--border);
         padding:18px 20px; display:flex; flex-direction:column; gap:6px; }
  .kpi-label { font-size:.75rem; color:var(--muted); text-transform:uppercase; letter-spacing:.8px; }
  .kpi-value { font-size:2rem; font-weight:700; line-height:1; }
  .kpi-sub   { font-size:.75rem; color:var(--muted); }
  .kpi.green  { border-top-color:var(--green); }
  .kpi.blue   { border-top-color:var(--blue); }
  .kpi.yellow { border-top-color:var(--yellow); }
  .kpi.purple { border-top-color:var(--purple); }
  .kpi.red    { border-top-color:var(--red); }
  .kpi.green .kpi-value { color:var(--green); }
  .kpi.blue  .kpi-value { color:var(--blue);  }
  .kpi.yellow.kpi-value { color:var(--yellow);}
  .kpi.yellow .kpi-value{ color:var(--yellow);}
  .kpi.red   .kpi-value { color:var(--red);   }
  .kpi.purple.kpi-value { color:var(--purple);}
  .kpi.purple .kpi-value{ color:var(--purple);}

  /* charts row */
  .charts-row { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
  .card { background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:20px; box-shadow:var(--shadow); }
  .card h2 { font-size:.8rem; color:var(--text); font-weight:700; text-transform:uppercase; letter-spacing:.8px; margin-bottom:16px; }
  .chart-wrap { height:220px; display:flex; align-items:center; justify-content:center; }

  /* dock grid */
  .bottom-row { display:grid; grid-template-columns:1fr 1.6fr; gap:16px; }
  .dock-grid { display:grid; grid-template-columns:repeat(5,1fr); gap:10px; margin-top:4px; }
  .door { border-radius:6px; padding:12px 8px; text-align:center; border:1px solid var(--border); }
  .door .door-num  { font-size:1.1rem; font-weight:700; }
  .door .door-type { font-size:.65rem; color:var(--muted); text-transform:uppercase; margin-top:2px; }
  .door .door-stat { font-size:.7rem; font-weight:600; margin-top:6px; text-transform:uppercase; letter-spacing:.5px; }
  .door .door-info { font-size:.65rem; color:var(--muted); margin-top:4px; line-height:1.4; }
  .door.available   { background:#ecfdf3; border-color:#86efac; }
  .door.available   .door-stat { color:var(--green); }
  .door.occupied    { background:var(--blue-soft); border-color:#9db5dd; }
  .door.occupied    .door-stat { color:var(--blue); }
  .door.maintenance { background:#fffbeb; border-color:#fcd34d; }
  .door.maintenance .door-stat { color:var(--yellow); }

  /* events table */
  .events-wrap { overflow-y:auto; max-height:320px; }
  table { width:100%; border-collapse:collapse; font-size:.8rem; }
  thead th { position:sticky; top:0; background:#f1f4f8; padding:8px 10px;
             text-align:left; color:var(--muted); font-weight:700; font-size:.72rem;
             text-transform:uppercase; letter-spacing:.5px; border-bottom:1px solid var(--border); }
  tbody td { padding:8px 10px; border-bottom:1px solid var(--row-line); vertical-align:top; }
  tbody tr:nth-child(even) td { background:#fafbfd; }
  tbody tr:hover td { background:var(--blue-soft); }
  .badge { display:inline-block; border-radius:4px; padding:2px 8px; font-size:.7rem; font-weight:600; }
  .badge.inbound    { background:#ecfeff; color:var(--cyan);   }
  .badge.outbound   { background:#f5f3ff; color:var(--purple); }
  .badge.arrival    { background:#ecfdf3; color:var(--green);  }
  .badge.departure  { background:#fffbeb; color:var(--yellow); }
  .badge.dock       { background:var(--blue-soft); color:var(--blue); }
  .badge.loading    { background:#f5f3ff; color:var(--purple); }

  /* shipments table section */
  .ship-wrap { overflow-x:auto; }
  .status-pill { display:inline-block; border-radius:20px; padding:2px 10px; font-size:.7rem; font-weight:700; }
  .status-pill.scheduled  { background:#f1f5f9; color:#475569; }
  .status-pill.arrived    { background:#fffbeb; color:var(--yellow); }
  .status-pill.docked     { background:var(--blue-soft); color:var(--blue); }
  .status-pill.loading    { background:#f5f3ff; color:var(--purple); }
  .status-pill.unloading  { background:#ecfeff; color:var(--cyan);   }
  .status-pill.completed  { background:#ecfdf3; color:var(--green);  }
  .status-pill.departed   { background:#fef2f2; color:var(--red);    }
</style>
</head>
<body>
<header>
  <h1>YMS <span>KSAPTECH Logistics Yard</span> — Operations Dashboard</h1>
  <div class="header-right">
    <span class="refresh-badge" id="last-refresh">Loading…</span>
    <a class="chat-link" href="http://localhost:5000" target="_blank">💬 AI Agent Chat</a>
  </div>
</header>

<main>
  <!-- KPI Cards -->
  <div class="kpi-row" id="kpi-row">
    <div class="kpi blue">  <div class="kpi-label">Total Shipments</div><div class="kpi-value" id="k-total">—</div><div class="kpi-sub">in system</div></div>
    <div class="kpi yellow"><div class="kpi-label">Active Operations</div><div class="kpi-value" id="k-active">—</div><div class="kpi-sub">loading / docked</div></div>
    <div class="kpi green"> <div class="kpi-label">Completed Today</div><div class="kpi-value" id="k-completed">—</div><div class="kpi-sub">shipments</div></div>
    <div class="kpi purple"><div class="kpi-label">Trailers in Yard</div><div class="kpi-value" id="k-trailers">—</div><div class="kpi-sub">active / docked</div></div>
    <div class="kpi green"> <div class="kpi-label">Available Docks</div><div class="kpi-value" id="k-docks">—</div><div class="kpi-sub">ready for assignment</div></div>
  </div>

  <!-- Charts -->
  <div class="charts-row">
    <div class="card">
      <h2>Shipment Status Distribution</h2>
      <div class="chart-wrap"><canvas id="statusChart"></canvas></div>
    </div>
    <div class="card">
      <h2>Inbound vs Outbound</h2>
      <div class="chart-wrap"><canvas id="typeChart"></canvas></div>
    </div>
  </div>

  <!-- Dock Doors -->
  <div class="card">
    <h2>Dock Door Status</h2>
    <div class="dock-grid" id="dock-grid">Loading…</div>
  </div>

  <!-- Bottom: Events + Shipments -->
  <div class="bottom-row">
    <div class="card">
      <h2>Recent Yard Events</h2>
      <div class="events-wrap">
        <table>
          <thead><tr><th>Time</th><th>Event</th><th>Shipment</th><th>Notes</th></tr></thead>
          <tbody id="events-body"></tbody>
        </table>
      </div>
    </div>
    <div class="card">
      <h2>Shipments</h2>
      <div class="ship-wrap">
        <table>
          <thead><tr><th>Tracking</th><th>Type</th><th>Status</th><th>Carrier</th><th>Route</th><th>Units</th><th>Door</th></tr></thead>
          <tbody id="ship-body"></tbody>
        </table>
      </div>
    </div>
  </div>
</main>

<script>
let statusChart, typeChart;

function fmt(s){ return s ? s.replace('_',' ') : '—'; }

function eventBadgeClass(et){
  if(et.includes('arrival'))  return 'arrival';
  if(et.includes('depart'))   return 'departure';
  if(et.includes('dock'))     return 'dock';
  if(et.includes('load'))     return 'loading';
  return 'dock';
}

async function loadSummary(){
  const d = await fetch('/api/summary').then(r=>r.json());
  document.getElementById('k-total').textContent     = d.total_shipments;
  document.getElementById('k-active').textContent    = (d.statuses.loading||0)+(d.statuses.unloading||0)+(d.statuses.docked||0);
  document.getElementById('k-completed').textContent = d.statuses.completed||0;
  document.getElementById('k-trailers').textContent  = d.trailers_in_yard;
  document.getElementById('k-docks').textContent     = d.docks.available||0;

  const statusLabels = Object.keys(d.statuses);
  const statusVals   = Object.values(d.statuses);
  const palette = ['#1f4e9c','#d97706','#0e7490','#6d28d9','#16a34a','#dc2626','#64748b'];
  if(!statusChart){
    statusChart = new Chart(document.getElementById('statusChart'),{
      type:'doughnut',
      data:{ labels:statusLabels, datasets:[{data:statusVals, backgroundColor:palette, borderWidth:2, borderColor:'#ffffff'}]},
      options:{ plugins:{legend:{labels:{color:'#475569',font:{size:11}}}}, cutout:'62%', maintainAspectRatio:false }
    });
  } else {
    statusChart.data.labels   = statusLabels;
    statusChart.data.datasets[0].data = statusVals;
    statusChart.update();
  }

  const typeLabels = ['Inbound','Outbound'];
  const typeVals   = [d.types.inbound||0, d.types.outbound||0];
  if(!typeChart){
    typeChart = new Chart(document.getElementById('typeChart'),{
      type:'bar',
      data:{ labels:typeLabels, datasets:[{
        data:typeVals, backgroundColor:['#1f4e9c','#7a9cd0'],
        borderRadius:8, borderSkipped:false
      }]},
      options:{
        plugins:{legend:{display:false}},
        scales:{
          x:{ ticks:{color:'#64748b'}, grid:{display:false} },
          y:{ ticks:{color:'#64748b'}, grid:{color:'#edf1f5'}, beginAtZero:true }
        },
        maintainAspectRatio:false
      }
    });
  } else {
    typeChart.data.datasets[0].data = typeVals;
    typeChart.update();
  }
}

async function loadDocks(){
  const doors = await fetch('/api/docks').then(r=>r.json());
  const grid  = document.getElementById('dock-grid');
  grid.innerHTML = doors.map(d => `
    <div class="door ${d.status}">
      <div class="door-num">${d.door_number}</div>
      <div class="door-type">${d.door_type}</div>
      <div class="door-stat">${d.status}</div>
      <div class="door-info">${d.status==='occupied'
        ? `${d.tracking_number||''}<br>${d.carrier||''}<br>${d.ship_status||''}`
        : d.status==='maintenance' ? 'Out of service' : 'Ready'
      }</div>
    </div>`).join('');
}

async function loadEvents(){
  const evts = await fetch('/api/events').then(r=>r.json());
  document.getElementById('events-body').innerHTML = evts.map(e=>`
    <tr>
      <td style="white-space:nowrap;color:var(--muted)">${(e.created_at||'').slice(11,16)}</td>
      <td><span class="badge ${eventBadgeClass(e.event_type)}">${fmt(e.event_type)}</span></td>
      <td style="white-space:nowrap">${e.tracking_number||'—'}</td>
      <td style="color:var(--muted)">${e.notes||''}</td>
    </tr>`).join('');
}

async function loadShipments(){
  const ships = await fetch('/api/shipments').then(r=>r.json());
  document.getElementById('ship-body').innerHTML = ships.map(s=>`
    <tr>
      <td style="white-space:nowrap;font-size:.78rem">${s.tracking_number}</td>
      <td><span class="badge ${s.type}">${s.type}</span></td>
      <td><span class="status-pill ${s.status}">${s.status}</span></td>
      <td style="font-size:.78rem">${s.carrier||'—'}</td>
      <td style="font-size:.72rem;color:var(--muted)">${(s.origin||'').split(',')[0]} → ${(s.destination||'').split(',')[0]}</td>
      <td style="text-align:center">${s.units||'—'}</td>
      <td style="text-align:center;font-weight:700;color:var(--blue)">${s.dock_door||'—'}</td>
    </tr>`).join('');
}

async function refresh(){
  await Promise.all([loadSummary(), loadDocks(), loadEvents(), loadShipments()]);
  document.getElementById('last-refresh').textContent =
    'Last refreshed: ' + new Date().toLocaleTimeString();
}

refresh();
setInterval(refresh, 30000);
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML)


if __name__ == "__main__":
    setup_database()
    app.run(debug=True, port=5001)
