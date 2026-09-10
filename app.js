// ---------- Auth guard ----------
const TOKEN = localStorage.getItem('visipulse_token');
const ROLE = localStorage.getItem('visipulse_role');
const USERNAME = localStorage.getItem('visipulse_username');
const USER_ID = localStorage.getItem('visipulse_user_id');

if (!TOKEN) {
  window.location.href = 'login.html';
}

document.getElementById('sidebarUsername').textContent = USERNAME || '—';
document.getElementById('sidebarRole').textContent = (ROLE || '').replace('_', ' ');
if (ROLE === 'admin') document.getElementById('navAudit').classList.remove('hidden');
if (ROLE === 'admin' || ROLE === 'maintenance_tech') document.getElementById('btnAddDevice').classList.remove('hidden');

document.getElementById('signOutBtn').addEventListener('click', () => {
  localStorage.clear();
  window.location.href = 'login.html';
});

// ---------- Fetch wrapper ----------
async function api(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Authorization': `Bearer ${TOKEN}`,
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
  });
  if (res.status === 401) {
    localStorage.clear();
    window.location.href = 'login.html';
    return null;
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error((data && data.detail) || `Request failed (${res.status})`);
  return data;
}

// ---------- Clock ----------
function tickClock() {
  const el = document.getElementById('clock');
  const now = new Date();
  el.textContent = now.toLocaleString('en-GB', {
    weekday: 'short', year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}
tickClock();
setInterval(tickClock, 1000);

// ---------- Nav ----------
const sections = ['overview', 'devices', 'predictions', 'tickets', 'security', 'audit'];
const titles = {
  overview: ['Overview', 'Facility-wide equipment health, at a glance'],
  devices: ['Devices', 'Registered equipment and live status'],
  predictions: ['AI Predictions', 'Anomaly detections awaiting or under human review'],
  tickets: ['Maintenance Tickets', 'Work items tracked from detection through resolution'],
  security: ['Security Logs', 'Device-level software and security events'],
  audit: ['Audit Trail', 'Immutable record of every critical system action'],
};

document.querySelectorAll('.nav-item').forEach(btn => {
  btn.addEventListener('click', () => switchSection(btn.dataset.section));
});

function switchSection(name) {
  document.querySelectorAll('.nav-item').forEach(b => b.classList.toggle('active', b.dataset.section === name));
  sections.forEach(s => document.getElementById(`section-${s}`).classList.toggle('active', s === name));
  document.getElementById('pageTitle').textContent = titles[name][0];
  document.getElementById('pageSubtitle').textContent = titles[name][1];
  loadSection(name);
}

function loadSection(name) {
  if (name === 'overview') loadOverview();
  if (name === 'devices') loadDevices();
  if (name === 'predictions') loadPredictions();
  if (name === 'tickets') loadTickets();
  if (name === 'security') loadSecurityLogs();
  if (name === 'audit') loadAudit();
}

// ---------- Badges ----------
const STATUS_COLORS = {
  online:        { c: 'text-signal border-signal/40 bg-signal/10' },
  offline:       { c: 'text-muted border-hair bg-raised' },
  under_maintenance: { c: 'text-warn border-warn/40 bg-warn/10' },
  decommissioned: { c: 'text-muted border-hair bg-raised' },
  pending:       { c: 'text-warn border-warn/40 bg-warn/10' },
  approved:      { c: 'text-signal border-signal/40 bg-signal/10' },
  rejected:      { c: 'text-crit border-crit/40 bg-crit/10' },
  open:          { c: 'text-info border-info/40 bg-info/10' },
  in_progress:   { c: 'text-warn border-warn/40 bg-warn/10' },
  resolved:      { c: 'text-signal border-signal/40 bg-signal/10' },
  cancelled:     { c: 'text-muted border-hair bg-raised' },
  low:           { c: 'text-muted border-hair bg-raised' },
  medium:        { c: 'text-info border-info/40 bg-info/10' },
  high:          { c: 'text-warn border-warn/40 bg-warn/10' },
  urgent:        { c: 'text-crit border-crit/40 bg-crit/10' },
  info:          { c: 'text-info border-info/40 bg-info/10' },
  critical:      { c: 'text-crit border-crit/40 bg-crit/10' },
};

function badge(value) {
  if (!value) return '<span class="text-muted text-xs">—</span>';
  const style = STATUS_COLORS[value] || { c: 'text-muted border-hair bg-raised' };
  return `<span class="badge ${style.c}"><span class="dot" style="background:currentColor"></span>${value.replace(/_/g, ' ')}</span>`;
}

function riskColor(score) {
  if (score >= 85) return 'text-crit';
  if (score >= 70) return 'text-warn';
  return 'text-info';
}

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function filterPills(container, options, active, onSelect) {
  container.innerHTML = '';
  options.forEach(opt => {
    const btn = document.createElement('button');
    btn.textContent = opt.label;
    btn.className = `text-xs font-mono px-3 py-1.5 rounded-sm border transition-colors ${
      opt.value === active ? 'bg-signal/15 border-signal/40 text-signal' : 'border-hair text-muted hover:text-ink'
    }`;
    btn.addEventListener('click', () => onSelect(opt.value));
    container.appendChild(btn);
  });
}

// ---------- Devices cache (used by predictions/tickets tables for name lookup) ----------
let deviceCache = {};
async function ensureDeviceCache() {
  if (Object.keys(deviceCache).length) return deviceCache;
  const devices = await api('/devices');
  deviceCache = Object.fromEntries(devices.map(d => [d.device_id, d]));
  return deviceCache;
}

// ---------- Overview ----------
async function loadOverview() {
  const [devices, pending, tickets] = await Promise.all([
    api('/devices'),
    api('/predictions?status_filter=pending'),
    api('/tickets'),
  ]);

  const online = devices.filter(d => d.status === 'online').length;
  const openTickets = tickets.filter(t => t.status === 'open' || t.status === 'in_progress').length;
  const critical = pending.filter(p => p.risk_score >= 85).length;

  document.getElementById('kpiDevicesOnline').textContent = `${online}/${devices.length}`;
  document.getElementById('kpiPending').textContent = pending.length;
  document.getElementById('kpiOpenTickets').textContent = openTickets;
  document.getElementById('kpiCritical').textContent = critical;

  const navBadge = document.getElementById('navPredictionBadge');
  if (pending.length) {
    navBadge.textContent = pending.length;
    navBadge.classList.remove('hidden');
  } else {
    navBadge.classList.add('hidden');
  }

  await ensureDeviceCache();
  const attentionList = document.getElementById('overviewAttentionList');
  const sorted = [...pending].sort((a, b) => b.risk_score - a.risk_score).slice(0, 6);
  attentionList.innerHTML = sorted.length
    ? sorted.map(p => {
        const dev = deviceCache[p.device_id];
        return `<div class="px-5 py-3.5 flex items-center justify-between">
          <div>
            <div class="text-sm font-medium">${dev ? dev.device_name : `Device #${p.device_id}`}</div>
            <div class="text-xs text-muted mt-0.5">${p.predicted_failure_type || 'Anomaly detected'} · ${dev ? dev.location : ''}</div>
          </div>
          <div class="text-right">
            <div class="font-mono text-sm font-semibold ${riskColor(p.risk_score)}">${p.risk_score.toFixed(1)}</div>
            <div class="text-[10px] text-muted font-mono">risk score</div>
          </div>
        </div>`;
      }).join('')
    : `<div class="px-5 py-8 text-center text-sm text-muted">No devices currently flagged. All systems nominal.</div>`;

  const audit = await api('/audit?limit=8').catch(() => []);
  const activityList = document.getElementById('overviewActivityList');
  activityList.innerHTML = (audit || []).length
    ? audit.map(a => `<div class="px-5 py-3">
        <div class="text-xs font-mono text-ink">${a.action.replace(/_/g, ' ')}</div>
        <div class="text-[11px] text-muted mt-0.5">${a.entity_type} #${a.entity_id ?? '—'} · ${fmtDate(a.timestamp)}</div>
      </div>`).join('')
    : `<div class="px-5 py-8 text-center text-sm text-muted">No recent activity.</div>`;
}

// ---------- Devices ----------
let deviceStatusActive = null;
async function loadDevices() {
  filterPills(document.getElementById('deviceStatusFilters'), [
    { label: 'All', value: null },
    { label: 'Online', value: 'online' },
    { label: 'Offline', value: 'offline' },
    { label: 'Under maintenance', value: 'under_maintenance' },
  ], deviceStatusActive, (v) => { deviceStatusActive = v; loadDevices(); });

  const qs = deviceStatusActive ? `?status_filter=${deviceStatusActive}` : '';
  const devices = await api(`/devices${qs}`);
  deviceCache = Object.fromEntries(devices.map(d => [d.device_id, d]));

  const canScan = ROLE === 'admin' || ROLE === 'maintenance_tech';
  document.getElementById('devicesTableBody').innerHTML = devices.map(d => `
    <tr>
      <td class="font-medium">${d.device_name}</td>
      <td class="text-muted">${d.category}</td>
      <td class="text-muted">${d.location}</td>
      <td>${badge(d.status)}</td>
      <td class="font-mono text-xs text-muted">${fmtDate(d.last_checked)}</td>
      <td>${canScan ? `<button data-scan="${d.device_id}" class="text-xs font-mono text-signal hover:underline">Run AI scan</button>` : ''}</td>
    </tr>
  `).join('') || `<tr><td colspan="6" class="text-center text-muted py-8">No devices found.</td></tr>`;

  document.querySelectorAll('[data-scan]').forEach(btn => {
    btn.addEventListener('click', async () => {
      btn.textContent = 'Scanning…';
      try {
        const result = await api(`/predictions/run/${btn.dataset.scan}`, { method: 'POST' });
        btn.textContent = result ? `Flagged (${result.risk_score.toFixed(0)})` : 'No anomaly';
      } catch (e) {
        btn.textContent = 'Scan failed';
      }
    });
  });
}

// ---------- Predictions ----------
let predictionStatusActive = 'pending';
async function loadPredictions() {
  filterPills(document.getElementById('predictionStatusFilters'), [
    { label: 'Pending', value: 'pending' },
    { label: 'Approved', value: 'approved' },
    { label: 'Rejected', value: 'rejected' },
    { label: 'All', value: null },
  ], predictionStatusActive, (v) => { predictionStatusActive = v; loadPredictions(); });

  await ensureDeviceCache();
  const qs = predictionStatusActive ? `?status_filter=${predictionStatusActive}` : '';
  const predictions = await api(`/predictions${qs}`);
  const canDecide = ROLE === 'admin' || ROLE === 'medical_staff';

  document.getElementById('predictionsTableBody').innerHTML = predictions.map(p => {
    const dev = deviceCache[p.device_id];
    return `<tr>
      <td class="font-medium">${dev ? dev.device_name : `#${p.device_id}`}</td>
      <td class="font-mono font-semibold ${riskColor(p.risk_score)}">${p.risk_score.toFixed(1)}</td>
      <td class="text-muted">${p.predicted_failure_type || '—'}</td>
      <td>${badge(p.approval_status)}</td>
      <td class="font-mono text-xs text-muted">${fmtDate(p.prediction_time)}</td>
      <td class="text-muted text-xs">${p.approved_by ? 'User #' + p.approved_by : '—'}</td>
      <td>${canDecide && p.approval_status === 'pending'
        ? `<button data-review="${p.prediction_id}" class="text-xs font-mono text-signal hover:underline">Review</button>`
        : ''}</td>
    </tr>`;
  }).join('') || `<tr><td colspan="7" class="text-center text-muted py-8">No predictions in this view.</td></tr>`;

  document.querySelectorAll('[data-review]').forEach(btn => {
    btn.addEventListener('click', () => openDecisionModal(btn.dataset.review, predictions));
  });
}

function openDecisionModal(predictionId, predictions) {
  const p = predictions.find(x => String(x.prediction_id) === String(predictionId));
  const dev = deviceCache[p.device_id];
  document.getElementById('modalDeviceInfo').textContent =
    `${dev ? dev.device_name : 'Device #' + p.device_id} · risk ${p.risk_score.toFixed(1)} · ${p.predicted_failure_type || 'anomaly'}`;
  document.getElementById('modalNotes').value = '';
  document.getElementById('modalOpenTicket').checked = true;
  const modal = document.getElementById('decisionModal');
  modal.classList.remove('hidden');

  const close = () => modal.classList.add('hidden');
  document.getElementById('modalCancel').onclick = close;

  document.getElementById('modalApprove').onclick = async () => {
    await submitDecision(predictionId, true, close);
  };
  document.getElementById('modalReject').onclick = async () => {
    await submitDecision(predictionId, false, close);
  };
}

async function submitDecision(predictionId, approve, close) {
  try {
    await api(`/predictions/${predictionId}/decision`, {
      method: 'POST',
      body: JSON.stringify({
        approve,
        notes: document.getElementById('modalNotes').value || null,
        open_ticket: document.getElementById('modalOpenTicket').checked,
      }),
    });
    close();
    loadPredictions();
  } catch (e) {
    alert(e.message);
  }
}

// ---------- Tickets ----------
let ticketStatusActive = null;
async function loadTickets() {
  filterPills(document.getElementById('ticketStatusFilters'), [
    { label: 'All', value: null },
    { label: 'Open', value: 'open' },
    { label: 'In progress', value: 'in_progress' },
    { label: 'Resolved', value: 'resolved' },
    { label: 'Cancelled', value: 'cancelled' },
  ], ticketStatusActive, (v) => { ticketStatusActive = v; loadTickets(); });

  await ensureDeviceCache();
  const qs = ticketStatusActive ? `?status_filter=${ticketStatusActive}` : '';
  const tickets = await api(`/tickets${qs}`);
  const canManage = ROLE === 'admin' || ROLE === 'maintenance_tech';

  document.getElementById('ticketsTableBody').innerHTML = tickets.map(t => {
    const dev = deviceCache[t.device_id];
    return `<tr>
      <td class="font-mono text-xs text-muted">#${t.ticket_id}</td>
      <td class="font-medium">${dev ? dev.device_name : `#${t.device_id}`}</td>
      <td>${badge(t.priority)}</td>
      <td>${badge(t.status)}</td>
      <td class="text-muted text-xs">${t.assigned_to ? 'User #' + t.assigned_to : 'Unassigned'}</td>
      <td class="font-mono text-xs text-muted">${fmtDate(t.created_at)}</td>
      <td class="font-mono text-xs text-muted">${fmtDate(t.scheduled_for)}</td>
      <td>${canManage ? `<select data-ticket="${t.ticket_id}" class="bg-raised border border-hair rounded-sm text-xs font-mono px-2 py-1 outline-none">
        <option value="">Update…</option>
        <option value="in_progress">Mark in progress</option>
        <option value="resolved">Mark resolved</option>
        <option value="cancelled">Cancel</option>
      </select>` : ''}</td>
    </tr>`;
  }).join('') || `<tr><td colspan="8" class="text-center text-muted py-8">No tickets in this view.</td></tr>`;

  document.querySelectorAll('[data-ticket]').forEach(sel => {
    sel.addEventListener('change', async () => {
      if (!sel.value) return;
      try {
        await api(`/tickets/${sel.dataset.ticket}`, {
          method: 'PATCH',
          body: JSON.stringify({ status: sel.value }),
        });
        loadTickets();
      } catch (e) {
        alert(e.message);
      }
    });
  });
}

// ---------- Security Logs ----------
let securitySeverityActive = null;
async function loadSecurityLogs() {
  filterPills(document.getElementById('securityStatusFilters'), [
    { label: 'All', value: null },
    { label: 'Critical', value: 'critical' },
    { label: 'High', value: 'high' },
    { label: 'Medium', value: 'medium' },
    { label: 'Low', value: 'low' },
    { label: 'Info', value: 'info' },
  ], securitySeverityActive, (v) => { securitySeverityActive = v; loadSecurityLogs(); });

  await ensureDeviceCache();
  const qs = securitySeverityActive ? `?severity=${securitySeverityActive}` : '';
  const logs = await api(`/security-logs${qs}`);

  document.getElementById('securityTableBody').innerHTML = logs.map(l => {
    const dev = deviceCache[l.device_id];
    return `<tr>
      <td class="font-medium">${dev ? dev.device_name : `#${l.device_id}`}</td>
      <td class="text-muted">${l.log_type}</td>
      <td>${badge(l.severity_level)}</td>
      <td class="text-muted text-xs max-w-xs truncate">${l.details || '—'}</td>
      <td class="font-mono text-xs text-muted">${fmtDate(l.timestamp)}</td>
    </tr>`;
  }).join('') || `<tr><td colspan="5" class="text-center text-muted py-8">No security events in this view.</td></tr>`;
}

// ---------- Audit ----------
async function loadAudit() {
  const logs = await api('/audit?limit=200');
  document.getElementById('auditTableBody').innerHTML = logs.map(a => `
    <tr>
      <td class="font-mono text-xs text-muted">${fmtDate(a.timestamp)}</td>
      <td class="text-xs">${a.user_id ? 'User #' + a.user_id : 'system'}</td>
      <td class="font-mono text-xs">${a.action}</td>
      <td class="text-xs text-muted">${a.entity_type}${a.entity_id ? ' #' + a.entity_id : ''}</td>
      <td class="text-xs text-muted max-w-sm truncate">${a.details || '—'}</td>
      <td class="font-mono text-xs text-muted">${a.ip_address || '—'}</td>
    </tr>
  `).join('') || `<tr><td colspan="6" class="text-center text-muted py-8">No audit entries yet.</td></tr>`;
}

// ---------- Init ----------
loadOverview();
