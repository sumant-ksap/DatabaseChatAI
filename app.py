import os

from flask import Flask, request, jsonify, render_template_string
from agent import run_agent
import database

app = Flask(__name__)

# ── HTML ──────────────────────────────────────────────────────────────────────

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Database AI Agent</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    :root {
      --bg:      #0f1117;
      --surface: #1a1d27;
      --card:    #20243a;
      --border:  #2a2f4a;
      --accent:  #4f6ef7;
      --accent2: #e94560;
      --text:    #e2e8f0;
      --muted:   #8892a4;
      --green:   #22c55e;
      --yellow:  #f59e0b;
      --red:     #ef4444;
    }

    body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); height: 100vh; overflow: hidden; display: flex; flex-direction: column; }

    /* ── Header ── */
    header {
      display: flex; align-items: center; gap: 12px;
      padding: 0 20px; height: 54px; min-height: 54px;
      background: var(--surface); border-bottom: 1px solid var(--border);
      flex-shrink: 0;
    }
    header .logo { font-size: 1rem; font-weight: 700; color: var(--text); letter-spacing: .5px; }
    header .logo span { color: var(--accent); }
    header .spacer { flex: 1; }
    #conn-badge {
      display: flex; align-items: center; gap: 6px;
      font-size: .78rem; color: var(--muted);
      background: var(--card); border: 1px solid var(--border);
      border-radius: 20px; padding: 4px 12px;
      max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    #conn-badge .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--red); flex-shrink: 0; }
    #conn-badge .dot.on { background: var(--green); }
    #conn-badge #badge-text { overflow: hidden; text-overflow: ellipsis; }
    .btn {
      display: inline-flex; align-items: center; gap: 6px;
      border: none; border-radius: 8px; padding: 7px 14px;
      font-size: .82rem; font-weight: 600; cursor: pointer; transition: opacity .15s;
    }
    .btn:hover { opacity: .85; }
    .btn-primary   { background: var(--accent);  color: #fff; }
    .btn-danger    { background: var(--red);      color: #fff; }
    .btn-ghost     { background: var(--card);     color: var(--text); border: 1px solid var(--border); }
    #btn-connect    { }
    #btn-disconnect { display: none; }

    /* ── Setup overlay ── */
    #setup-overlay {
      position: fixed; inset: 0; background: rgba(0,0,0,.7);
      display: flex; align-items: center; justify-content: center;
      z-index: 100;
    }
    .modal {
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 16px; padding: 32px; width: 480px; max-width: 96vw;
    }
    .modal h2 { font-size: 1.15rem; margin-bottom: 6px; }
    .modal .subtitle { font-size: .82rem; color: var(--muted); margin-bottom: 24px; }
    .tabs { display: flex; gap: 4px; background: var(--card); border-radius: 8px; padding: 4px; margin-bottom: 20px; }
    .tab-btn {
      flex: 1; padding: 6px; border: none; border-radius: 6px; cursor: pointer;
      font-size: .82rem; font-weight: 600; background: transparent; color: var(--muted); transition: all .15s;
    }
    .tab-btn.active { background: var(--accent); color: #fff; }
    .form-group { margin-bottom: 14px; }
    label { display: block; font-size: .78rem; color: var(--muted); margin-bottom: 5px; font-weight: 600; letter-spacing: .4px; }
    input[type=text], input[type=password], input[type=number], input[type=url] {
      width: 100%; background: var(--card); border: 1px solid var(--border);
      border-radius: 8px; padding: 9px 12px; color: var(--text); font-size: .88rem; outline: none;
      transition: border-color .15s;
    }
    input:focus { border-color: var(--accent); }
    .form-row { display: grid; grid-template-columns: 2fr 1fr; gap: 10px; }
    #conn-error { color: var(--red); font-size: .8rem; margin-top: 10px; min-height: 18px; }
    #conn-success { color: var(--green); font-size: .8rem; margin-top: 10px; min-height: 18px; }
    .modal-footer { display: flex; gap: 10px; margin-top: 20px; }
    .modal-footer .btn { flex: 1; justify-content: center; }

    /* ── Main layout ── */
    #app { display: flex; flex: 1; overflow: hidden; }

    /* ── Sidebar ── */
    #sidebar {
      width: 220px; min-width: 220px; background: var(--surface);
      border-right: 1px solid var(--border); display: flex; flex-direction: column;
      overflow: hidden;
    }
    #sidebar-header {
      padding: 14px 16px 10px; font-size: .72rem; font-weight: 700;
      color: var(--muted); letter-spacing: 1px; text-transform: uppercase;
      border-bottom: 1px solid var(--border); flex-shrink: 0;
    }
    #table-list { flex: 1; overflow-y: auto; padding: 8px 8px; }
    .table-item {
      padding: 8px 10px; border-radius: 7px; cursor: pointer;
      font-size: .84rem; color: var(--muted); display: flex; align-items: center; gap: 7px;
      transition: background .12s, color .12s; user-select: none;
    }
    .table-item:hover  { background: var(--card); color: var(--text); }
    .table-item.active { background: var(--accent); color: #fff; }
    .table-item .icon { font-size: .75rem; opacity: .6; }
    #sidebar-loading { padding: 12px 16px; font-size: .8rem; color: var(--muted); }

    /* ── Content area ── */
    #content { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

    /* ── Inner tabs ── */
    #view-tabs {
      display: flex; gap: 0; border-bottom: 1px solid var(--border);
      background: var(--surface); flex-shrink: 0;
    }
    .view-tab {
      padding: 13px 22px; font-size: .85rem; font-weight: 600; cursor: pointer;
      color: var(--muted); border-bottom: 2px solid transparent; transition: all .15s;
    }
    .view-tab.active { color: var(--accent); border-bottom-color: var(--accent); }

    /* ── Data view ── */
    #data-view { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
    #data-header {
      display: flex; align-items: center; gap: 12px;
      padding: 12px 20px; border-bottom: 1px solid var(--border); flex-shrink: 0;
    }
    #data-title { font-size: .95rem; font-weight: 700; }
    #data-count  { font-size: .78rem; color: var(--muted); background: var(--card); padding: 3px 8px; border-radius: 20px; }
    #data-header .spacer { flex: 1; }
    #data-search {
      background: var(--card); border: 1px solid var(--border); border-radius: 7px;
      padding: 6px 12px; color: var(--text); font-size: .82rem; outline: none; width: 200px;
    }
    #data-search:focus { border-color: var(--accent); }
    #table-wrap { flex: 1; overflow: auto; }
    #table-wrap table {
      width: 100%; border-collapse: collapse; font-size: .8rem; min-width: 100%;
    }
    #table-wrap th {
      position: sticky; top: 0; background: var(--card);
      padding: 9px 12px; text-align: left; font-size: .72rem;
      font-weight: 700; color: var(--muted); letter-spacing: .5px;
      text-transform: uppercase; border-bottom: 1px solid var(--border);
      white-space: nowrap; z-index: 1;
    }
    #table-wrap td {
      padding: 8px 12px; border-bottom: 1px solid var(--border);
      color: var(--text); max-width: 260px; overflow: hidden;
      text-overflow: ellipsis; white-space: nowrap;
    }
    #table-wrap tr:hover td { background: var(--card); }
    #data-placeholder {
      flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
      color: var(--muted); gap: 10px; font-size: .9rem;
    }
    #data-placeholder .big { font-size: 2.5rem; }
    #pagination {
      display: flex; align-items: center; gap: 10px;
      padding: 10px 20px; border-top: 1px solid var(--border);
      font-size: .8rem; color: var(--muted); flex-shrink: 0;
    }
    #pagination .spacer { flex: 1; }

    /* ── Chat view ── */
    #chat-view { flex: 1; display: none; flex-direction: column; overflow: hidden; }
    #chat-messages { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 12px; }
    .bubble { max-width: 76%; padding: 11px 15px; border-radius: 16px; line-height: 1.6; font-size: .88rem; white-space: pre-wrap; word-break: break-word; }
    .user  { align-self: flex-end; background: var(--accent); color: #fff; border-bottom-right-radius: 4px; }
    .agent { align-self: flex-start; background: var(--card); border: 1px solid var(--border); border-bottom-left-radius: 4px; }
    .thinking { color: var(--muted); font-style: italic; }
    #chat-form { display: flex; gap: 10px; padding: 14px 20px; background: var(--surface); border-top: 1px solid var(--border); flex-shrink: 0; }
    #chat-msg {
      flex: 1; background: var(--card); border: 1px solid var(--border);
      border-radius: 22px; padding: 10px 18px; color: var(--text);
      font-size: .88rem; outline: none; resize: none; height: 44px;
      line-height: 1.4; font-family: inherit;
    }
    #chat-msg:focus { border-color: var(--accent); }
    #chat-send {
      background: var(--accent); border: none; border-radius: 22px;
      padding: 0 22px; color: #fff; font-size: .88rem; font-weight: 600;
      cursor: pointer; transition: opacity .15s;
    }
    #chat-send:hover    { opacity: .85; }
    #chat-send:disabled { opacity: .45; cursor: not-allowed; }

    /* ── No-connection state ── */
    #no-conn {
      flex: 1; display: flex; flex-direction: column; align-items: center;
      justify-content: center; color: var(--muted); gap: 12px; font-size: .9rem;
    }
    #no-conn .big { font-size: 3rem; }

    /* scrollbar */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
  </style>
</head>
<body>

<!-- ── Header ─────────────────────────────────────────────────────────────── -->
<header>
  <div class="logo">AI <span>Database</span> Agent</div>
  <div id="conn-badge">
    <span class="dot" id="conn-dot"></span>
    <span id="badge-text">Not connected</span>
  </div>
  <div class="spacer"></div>
  <button class="btn btn-primary" id="btn-connect"   onclick="showSetup()">Connect to Database</button>
  <button class="btn btn-danger"  id="btn-disconnect" onclick="disconnect()">Disconnect</button>
</header>

<!-- ── Setup Modal ────────────────────────────────────────────────────────── -->
<div id="setup-overlay">
  <div class="modal">
    <h2>Connect to Database</h2>
    <p class="subtitle">Enter your database credentials. The connection is kept in memory only.</p>

    <div class="tabs">
      <button class="tab-btn active" id="db-postgres" onclick="switchDbType('postgres')">PostgreSQL</button>
      <button class="tab-btn"        id="db-mongodb"  onclick="switchDbType('mongodb')">MongoDB</button>
    </div>

    <div class="tabs">
      <button class="tab-btn active" id="tab-url"    onclick="switchTab('url')">Connection URL</button>
      <button class="tab-btn"        id="tab-fields"  onclick="switchTab('fields')">Individual Fields</button>
    </div>

    <!-- URL tab -->
    <div id="panel-url">
      <div class="form-group">
        <label>Connection URL</label>
        <input type="text" id="f-url" placeholder="postgresql://user:password@host:5432/dbname"/>
      </div>
      <div class="form-group" id="url-db-group" style="display:none">
        <label>Database Name</label>
        <input type="text" id="f-url-db" placeholder="mydb"/>
      </div>
    </div>

    <!-- Fields tab -->
    <div id="panel-fields" style="display:none">
      <div class="form-row">
        <div class="form-group">
          <label>Host</label>
          <input type="text" id="f-host" placeholder="localhost"/>
        </div>
        <div class="form-group">
          <label>Port</label>
          <input type="number" id="f-port" placeholder="5432" value="5432"/>
        </div>
      </div>
      <div class="form-group">
        <label>Database Name</label>
        <input type="text" id="f-db" placeholder="mydb"/>
      </div>
      <div class="form-group">
        <label>Username</label>
        <input type="text" id="f-user" placeholder="postgres"/>
      </div>
      <div class="form-group">
        <label>Password</label>
        <input type="password" id="f-pass" placeholder=""/>
      </div>
    </div>

    <div id="conn-error"></div>
    <div id="conn-success"></div>

    <div class="modal-footer">
      <button class="btn btn-ghost"   id="btn-cancel" onclick="hideSetup()" style="display:none">Cancel</button>
      <button class="btn btn-primary" id="btn-connect-submit" onclick="connect()">Connect</button>
    </div>
  </div>
</div>

<!-- ── Main App ───────────────────────────────────────────────────────────── -->
<div id="app">
  <!-- Sidebar -->
  <div id="sidebar">
    <div id="sidebar-header">Tables</div>
    <div id="table-list">
      <div id="sidebar-loading" style="display:none">Loading…</div>
    </div>
  </div>

  <!-- Content -->
  <div id="content">
    <!-- Not connected placeholder -->
    <div id="no-conn">
      <div class="big">🔌</div>
      <div>Connect to PostgreSQL or MongoDB to get started</div>
      <button class="btn btn-primary" onclick="showSetup()">Connect Now</button>
    </div>

    <!-- View tabs (hidden until connected) -->
    <div id="view-tabs" style="display:none">
      <div class="view-tab active" id="vtab-data" onclick="switchView('data')">Dashboard</div>
      <div class="view-tab"       id="vtab-chat" onclick="switchView('chat')">AI Chat</div>
    </div>

    <!-- Data view -->
    <div id="data-view" style="display:none">
      <div id="data-header">
        <span id="data-title">Select a table</span>
        <span id="data-count" style="display:none"></span>
        <span class="spacer"></span>
        <input id="data-search" type="text" placeholder="Filter rows…" oninput="filterRows(this.value)" style="display:none"/>
      </div>
      <div id="data-placeholder">
        <div class="big">📊</div>
        <div id="data-placeholder-text">Select a table from the sidebar to view its data</div>
      </div>
      <div id="table-wrap" style="display:none">
        <table id="data-table"><thead id="data-thead"></thead><tbody id="data-tbody"></tbody></table>
      </div>
      <div id="pagination" style="display:none">
        <span id="page-info"></span>
        <span class="spacer"></span>
        <button class="btn btn-ghost" id="btn-prev" onclick="changePage(-1)">← Prev</button>
        <button class="btn btn-ghost" id="btn-next" onclick="changePage(1)">Next →</button>
      </div>
    </div>

    <!-- Chat view -->
    <div id="chat-view">
      <div id="chat-messages"></div>
      <form id="chat-form" onsubmit="sendChat(event)">
        <textarea id="chat-msg" placeholder="Ask anything about your database…" rows="1"></textarea>
        <button type="submit" id="chat-send">Send</button>
      </form>
    </div>
  </div>
</div>

<script>
// Skip ngrok's browser-warning interstitial so it never intercepts our fetch() calls.
const _fetch = window.fetch;
window.fetch = (url, opts = {}) => _fetch(url, { ...opts, headers: { ...(opts.headers || {}), 'ngrok-skip-browser-warning': 'true' } });

// ── State ──────────────────────────────────────────────────────────────────
let connected   = false;
let activeTable = null;
let allRows     = [];
let filteredRows = [];
let currentPage = 0;
const PAGE_SIZE = 50;
const chatHistory = [];
let activeTab = 'url';
let dbType = 'postgres';

// ── Init ───────────────────────────────────────────────────────────────────
async function init() {
  const res  = await fetch('/api/status');
  const data = await res.json();
  if (data.connected) {
    switchDbType(data.db_type || 'postgres');
    onConnected(data.display, data.db_type || 'postgres');
  }
}

// ── Setup modal ────────────────────────────────────────────────────────────
function showSetup() {
  document.getElementById('setup-overlay').style.display = 'flex';
  document.getElementById('btn-cancel').style.display = connected ? '' : 'none';
  document.getElementById('conn-error').textContent   = '';
  document.getElementById('conn-success').textContent = '';
}
function hideSetup() {
  document.getElementById('setup-overlay').style.display = 'none';
}
function switchTab(tab) {
  activeTab = tab;
  document.getElementById('panel-url').style.display    = tab === 'url'    ? '' : 'none';
  document.getElementById('panel-fields').style.display = tab === 'fields' ? '' : 'none';
  document.getElementById('tab-url').classList.toggle('active',    tab === 'url');
  document.getElementById('tab-fields').classList.toggle('active', tab === 'fields');
}

function switchDbType(type) {
  dbType = type;
  document.getElementById('db-postgres').classList.toggle('active', type === 'postgres');
  document.getElementById('db-mongodb').classList.toggle('active', type === 'mongodb');
  document.getElementById('f-url').placeholder = type === 'mongodb'
    ? 'mongodb://user:password@host:27017/dbname'
    : 'postgresql://user:password@host:5432/dbname';
  document.getElementById('f-port').placeholder = type === 'mongodb' ? '27017' : '5432';
  document.getElementById('f-port').value = type === 'mongodb' ? '27017' : '5432';
  document.getElementById('f-user').placeholder = type === 'mongodb' ? 'optional' : 'postgres';
  document.getElementById('url-db-group').style.display = type === 'mongodb' ? '' : 'none';
  document.getElementById('sidebar-header').textContent = type === 'mongodb' ? 'Collections' : 'Tables';
  document.getElementById('data-title').textContent = type === 'mongodb' ? 'Select a collection' : 'Select a table';
  document.getElementById('data-placeholder-text').textContent = type === 'mongodb'
    ? 'Select a collection from the sidebar to view its documents'
    : 'Select a table from the sidebar to view its data';
}

// ── Connect ────────────────────────────────────────────────────────────────
async function connect() {
  const errEl  = document.getElementById('conn-error');
  const okEl   = document.getElementById('conn-success');
  const btn    = document.getElementById('btn-connect-submit');
  errEl.textContent  = '';
  okEl.textContent   = '';
  btn.disabled       = true;
  btn.textContent    = 'Connecting…';

  const body = activeTab === 'url'
    ? { db_type: dbType, url: document.getElementById('f-url').value.trim(), database: document.getElementById('f-url-db').value.trim() }
    : {
        db_type:  dbType,
        host:     document.getElementById('f-host').value.trim(),
        port:     document.getElementById('f-port').value.trim() || (dbType === 'mongodb' ? '27017' : '5432'),
        database: document.getElementById('f-db').value.trim(),
        user:     document.getElementById('f-user').value.trim(),
        password: document.getElementById('f-pass').value,
      };

  try {
    const res  = await fetch('/api/connect', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
    const data = await res.json();
    if (data.ok) {
      okEl.textContent = '✓ ' + data.version.split(' ').slice(0,2).join(' ');
      setTimeout(() => { hideSetup(); onConnected(data.display, data.db_type || dbType); }, 800);
    } else {
      errEl.textContent = '✗ ' + data.error;
    }
  } catch(e) {
    errEl.textContent = 'Network error: ' + e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Connect';
  }
}

async function disconnect() {
  await fetch('/api/disconnect', { method: 'POST' });
  connected   = false;
  activeTable = null;
  allRows     = [];
  document.getElementById('conn-dot').classList.remove('on');
  document.getElementById('badge-text').textContent = 'Not connected';
  document.getElementById('btn-connect').style.display    = '';
  document.getElementById('btn-disconnect').style.display = 'none';
  document.getElementById('no-conn').style.display    = '';
  document.getElementById('view-tabs').style.display  = 'none';
  document.getElementById('data-view').style.display  = 'none';
  document.getElementById('chat-view').style.display  = 'none';
  document.getElementById('table-list').innerHTML = '';
  showSetup();
}

// ── Post-connect UI ────────────────────────────────────────────────────────
function onConnected(display, type) {
  connected = true;
  switchDbType(type || dbType);
  document.getElementById('conn-dot').classList.add('on');
  document.getElementById('badge-text').textContent      = display;
  document.getElementById('btn-connect').style.display    = 'none';
  document.getElementById('btn-disconnect').style.display = '';
  document.getElementById('no-conn').style.display  = 'none';
  document.getElementById('view-tabs').style.display = '';
  switchView('data');
  loadTables();
}

// ── View tabs ──────────────────────────────────────────────────────────────
function switchView(view) {
  document.getElementById('vtab-data').classList.toggle('active', view === 'data');
  document.getElementById('vtab-chat').classList.toggle('active', view === 'chat');
  document.getElementById('data-view').style.display = view === 'data' ? 'flex' : 'none';
  document.getElementById('chat-view').style.display = view === 'chat' ? 'flex' : 'none';
}

// ── Table sidebar ──────────────────────────────────────────────────────────
async function loadTables() {
  const list = document.getElementById('table-list');
  list.innerHTML = '<div id="sidebar-loading">Loading…</div>';
  try {
    const res   = await fetch('/api/tables');
    const data  = await res.json();
    list.innerHTML = '';
    if (!data.tables || data.tables.length === 0) {
      const emptyLabel = dbType === 'mongodb' ? 'No collections found' : 'No tables found';
      list.innerHTML = `<div style="padding:12px;font-size:.8rem;color:var(--muted)">${emptyLabel}</div>`;
      return;
    }
    data.tables.forEach(t => {
      const el = document.createElement('div');
      el.className = 'table-item';
      el.dataset.table = t;
      el.innerHTML = '<span class="icon">▤</span>' + escHtml(t);
      el.onclick = () => loadTable(t);
      list.appendChild(el);
    });
  } catch(e) {
    list.innerHTML = '<div style="padding:12px;font-size:.8rem;color:var(--red)">Error loading tables</div>';
  }
}

// ── Table data ─────────────────────────────────────────────────────────────
async function loadTable(name) {
  activeTable = name;
  currentPage = 0;

  // Mark sidebar active
  document.querySelectorAll('.table-item').forEach(el => el.classList.toggle('active', el.dataset.table === name));

  document.getElementById('data-title').textContent = name;
  document.getElementById('data-placeholder').style.display = 'none';
  document.getElementById('table-wrap').style.display = '';
  document.getElementById('data-search').style.display = '';
  document.getElementById('data-search').value = '';
  document.getElementById('data-count').style.display = '';
  document.getElementById('data-count').textContent = 'Loading…';

  try {
    const res  = await fetch(`/api/table/${encodeURIComponent(name)}?limit=1000`);
    const data = await res.json();
    if (data.error) { document.getElementById('data-count').textContent = 'Error: ' + data.error; return; }

    allRows      = data.rows;
    filteredRows = allRows;
    renderTable(data.columns, filteredRows);
    document.getElementById('data-count').textContent = data.total + (dbType === 'mongodb' ? ' documents' : ' rows');
  } catch(e) {
    document.getElementById('data-count').textContent = 'Error';
  }
}

function renderTable(columns, rows) {
  const thead = document.getElementById('data-thead');
  const tbody = document.getElementById('data-tbody');
  thead.innerHTML = '<tr>' + columns.map(c => `<th>${escHtml(c)}</th>`).join('') + '</tr>';

  const start = currentPage * PAGE_SIZE;
  const page  = rows.slice(start, start + PAGE_SIZE);
  tbody.innerHTML = page.map(row =>
    '<tr>' + columns.map(c => `<td title="${escHtml(formatCell(row[c]))}">${escHtml(formatCell(row[c]))}</td>`).join('') + '</tr>'
  ).join('');

  const pageInfo = document.getElementById('page-info');
  const total    = rows.length;
  pageInfo.textContent = `Rows ${start+1}–${Math.min(start+PAGE_SIZE, total)} of ${total}`;
  document.getElementById('pagination').style.display = total > PAGE_SIZE ? '' : 'none';
  document.getElementById('btn-prev').disabled = currentPage === 0;
  document.getElementById('btn-next').disabled = start + PAGE_SIZE >= total;
}

function filterRows(q) {
  if (!activeTable) return;
  q = q.toLowerCase();
  filteredRows = q
    ? allRows.filter(row => Object.values(row).some(v => String(v ?? '').toLowerCase().includes(q)))
    : allRows;
  currentPage = 0;
  const cols = filteredRows.length > 0
    ? Object.keys(filteredRows[0])
    : (allRows.length > 0 ? Object.keys(allRows[0]) : []);
  renderTable(cols, filteredRows);
}

function changePage(delta) {
  currentPage = Math.max(0, currentPage + delta);
  const cols = filteredRows.length > 0 ? Object.keys(filteredRows[0]) : [];
  renderTable(cols, filteredRows);
}

// ── Chat ───────────────────────────────────────────────────────────────────
const chatMessages = document.getElementById('chat-messages');

document.getElementById('chat-msg').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); document.getElementById('chat-form').requestSubmit(); }
});

function addBubble(text, role) {
  const el = document.createElement('div');
  el.className = 'bubble ' + role;
  el.textContent = text;
  chatMessages.appendChild(el);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return el;
}

async function sendChat(e) {
  e.preventDefault();
  const msgEl  = document.getElementById('chat-msg');
  const sendBtn = document.getElementById('chat-send');
  const text    = msgEl.value.trim();
  if (!text) return;
  msgEl.value = '';
  addBubble(text, 'user');
  sendBtn.disabled = true;
  const thinking = addBubble('Thinking…', 'agent thinking');

  try {
    const res  = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history: chatHistory })
    });
    const data = await res.json();
    const reply = data.reply || data.error || 'No response.';
    thinking.className   = 'bubble agent';
    thinking.textContent = reply;
    if (data.reply) {
      chatHistory.push({ role: 'user',      content: text  });
      chatHistory.push({ role: 'assistant', content: reply });
    }
  } catch(err) {
    thinking.className   = 'bubble agent';
    thinking.textContent = 'Error: could not reach the agent.';
  } finally {
    sendBtn.disabled = false;
    msgEl.focus();
  }
}

// ── Utility ────────────────────────────────────────────────────────────────
function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function formatCell(value) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

// ── Boot ───────────────────────────────────────────────────────────────────
init();
</script>
</body>
</html>
"""


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/status")
def api_status():
    return jsonify({
        "connected": database.is_connected(),
        "display":   database.get_connection_display(),
        "db_type":   database.get_db_type(),
    })


@app.route("/api/connect", methods=["POST"])
def api_connect():
    data = request.get_json(force=True) or {}
    try:
        database.set_config(
            db_type=data.get("db_type", "postgres"),
            url=data.get("url", ""),
            host=data.get("host", ""),
            port=data.get("port", 27017 if data.get("db_type") == "mongodb" else 5432),
            database=data.get("database", ""),
            user=data.get("user", ""),
            password=data.get("password", ""),
        )
        ok, msg = database.test_connection()
        if ok:
            return jsonify({
                "ok": True,
                "version": msg,
                "display": database.get_connection_display(),
                "db_type": database.get_db_type(),
            })
        else:
            database.clear_config()
            return jsonify({"ok": False, "error": msg}), 400
    except Exception as exc:
        database.clear_config()
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/disconnect", methods=["POST"])
def api_disconnect():
    database.clear_config()
    return jsonify({"ok": True})


@app.route("/api/tables")
def api_tables():
    if not database.is_connected():
        return jsonify({"error": "Not connected"}), 400
    try:
        schema = database.get_schema_info()
        return jsonify({"tables": list(schema.keys())})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/table/<table_name>")
def api_table(table_name):
    if not database.is_connected():
        return jsonify({"error": "Not connected"}), 400
    limit  = min(int(request.args.get("limit",  100)), 2000)
    offset = int(request.args.get("offset", 0))
    try:
        data = database.get_table_data(table_name, limit=limit, offset=offset)
        # Convert any non-serialisable values to strings
        for row in data["rows"]:
            for k, v in row.items():
                if not isinstance(v, (str, int, float, bool, type(None))):
                    row[k] = str(v)
        return jsonify(data)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/chat", methods=["POST"])
def chat():
    if not database.is_connected():
        return jsonify({"error": "No database connected. Please connect to a database first."}), 400
    data         = request.get_json(force=True)
    user_message = (data.get("message") or "").strip()
    history      = data.get("history") or []
    if not user_message:
        return jsonify({"error": "Empty message"}), 400
    try:
        reply = run_agent(user_message, history=history)
        return jsonify({"reply": reply})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
