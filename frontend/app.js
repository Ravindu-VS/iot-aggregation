/* ============================================
   IOT DATA AGGREGATION - FRONTEND APPLICATION
   PRODUCTION-READY VERSION
   ============================================ */

// ============================================
// CONFIGURATION
// ============================================

// API_BASE_URL will be set to the CloudFront HTTPS domain
const API_BASE_URL = 'https://dbobaqxodowtk.cloudfront.net';

const AUTO_REFRESH_INTERVAL = 2000;
const STATUS_REFRESH_INTERVAL = 1000;
const NODE_ONLINE_THRESHOLD_MS = 15000;

// Chart plugin safe register
const zoomPlugin =
  window.ChartZoom ||
  window.chartjsPluginZoom ||
  window['chartjs-plugin-zoom'];

if (zoomPlugin && window.Chart?.register) {
  window.Chart.register(zoomPlugin);
}

// ============================================
// GLOBAL STATE
// ============================================

let appState = {
  currentSection: 'dashboard',
  autoRefresh: true,
  refreshInterval: null,
  statusInterval: null,
  allData: [],
  historyRange: { from: '', to: '' },
  alerts: [],
  activeAlertKeys: new Set(),
  charts: {},
};

// ============================================
// INIT
// ============================================

document.addEventListener('DOMContentLoaded', () => {
  initializeEventListeners();
  switchToSection('dashboard');
  safeLoadDashboard();
  setupAutoRefresh();
  setupStatusRefresh();
});

// ============================================
// EVENT BINDING
// ============================================

function initializeEventListeners() {
  document.querySelectorAll('.nav-link').forEach((link) => {
    link.addEventListener('click', (e) => {
      switchToSection(e.target.dataset.section);
    });
  });

  document.getElementById('refreshBtn')?.addEventListener('click', () => refreshCurrentSection());
  document.getElementById('autoRefreshToggle')?.addEventListener('change', (e) => {
    appState.autoRefresh = e.target.checked;
    if (appState.refreshInterval) clearInterval(appState.refreshInterval);
    if (appState.autoRefresh) setupAutoRefresh();
  });

  document.getElementById('nodeFilter')?.addEventListener('change', safeLoadDashboard);
  document.getElementById('applyHistoryRangeBtn')?.addEventListener('click', applyHistoryRange);
  document.getElementById('clearHistoryRangeBtn')?.addEventListener('click', clearHistoryRange);
  document.getElementById('searchSummaryBtn')?.addEventListener('click', searchSummary);
  document.getElementById('summarySearchId')?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') searchSummary();
  });
  document.getElementById('statusFilter')?.addEventListener('change', () => loadHistoryData());
  document.getElementById('exportBtn')?.addEventListener('click', exportData);
}

// ============================================
// NAVIGATION
// ============================================

function switchToSection(sectionId) {
  document.querySelectorAll('.section').forEach((s) => s.classList.remove('active'));
  document.getElementById(`${sectionId}-section`)?.classList.add('active');

  document.querySelectorAll('.nav-link').forEach((l) => {
    l.classList.toggle('active', l.dataset.section === sectionId);
  });

  appState.currentSection = sectionId;

  if (sectionId === 'dashboard') safeLoadDashboard();
  if (sectionId === 'analytics') loadAnalyticsData();
  if (sectionId === 'history') loadHistoryData();
}

// ============================================
// REFRESH
// ============================================

function refreshCurrentSection() {
  switch (appState.currentSection) {
    case 'dashboard': safeLoadDashboard(); break;
    case 'analytics': loadAnalyticsData(); break;
    case 'history': loadHistoryData(); break;
    default: safeLoadDashboard();
  }
}

function setupAutoRefresh() {
  if (appState.refreshInterval) clearInterval(appState.refreshInterval);
  if (appState.autoRefresh) {
    appState.refreshInterval = setInterval(() => refreshCurrentSection(), AUTO_REFRESH_INTERVAL);
  }
}

function setupStatusRefresh() {
  if (appState.statusInterval) clearInterval(appState.statusInterval);
  appState.statusInterval = setInterval(() => {
    if (appState.currentSection === 'dashboard') {
      updateNodePanels(appState.allData);
      renderAlerts(appState.alerts);
    }
  }, STATUS_REFRESH_INTERVAL);
}

// ============================================
// API FETCH (ROBUST)
// ============================================

async function fetchFromAPI(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  try {
    const response = await fetch(url, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    });
    const text = await response.text();
    let data;
    try { data = text ? JSON.parse(text) : null; } catch {
      throw new Error(`Invalid JSON: ${text.slice(0, 120)}`);
    }
    if (!response.ok) throw new Error(data?.error || `HTTP ${response.status}`);
    return data?.data !== undefined ? data : { data };
  } catch (err) {
    console.error('API ERROR:', url, err.message);
    throw err;
  }
}

// ============================================
// DASHBOARD LOADER
// ============================================

async function safeLoadDashboard() {
  try {
    showSpinner(true);
    const data = await fetchFromAPI('/list').catch(() => ({ data: [] }));
    appState.allData = (data.data || []).sort(
      (a, b) => new Date(a.timestamp) - new Date(b.timestamp)
    );
    const alerts = await fetchFromAPI('/alerts').catch(() => ({ data: [] }));
    appState.alerts = alerts.data || [];

    updateStatistics(appState.allData);
    updateNodePanels(appState.allData);
    renderAlerts(appState.alerts);
    updateActivityFeed(appState.allData);
    renderCharts(appState.allData);
  } catch (err) {
    showToast('Backend Error', err.message, 'error');
  } finally {
    showSpinner(false);
  }
}

// ============================================
// UPDATE STATISTICS
// ============================================

function updateStatistics(data) {
  const container = document.querySelector('.stats-grid');
  if (!container) return;

  const nodeIds = new Set(data.map(d => d.node_id).filter(Boolean));
  const now = Date.now();
  const activeNodes = data.filter(d => {
    const ts = new Date(d.timestamp).getTime();
    return now - ts < NODE_ONLINE_THRESHOLD_MS;
  });
  const activeNodeIds = new Set(activeNodes.map(d => d.node_id).filter(Boolean));

  const latestMetrics = {};
  data.forEach(d => {
    if (d.metrics) {
      Object.entries(d.metrics).forEach(([k, v]) => { latestMetrics[k] = v; });
    }
  });

  const stats = [
    { label: 'Total Readings', value: data.length, change: `${nodeIds.size} node(s) total` },
    { label: 'Active Nodes', value: activeNodeIds.size, change: `of ${nodeIds.size} registered` },
    { label: 'Temperature', value: latestMetrics.temperature != null ? `${Number(latestMetrics.temperature).toFixed(1)}°C` : '--', change: 'Latest reading' },
    { label: 'Humidity', value: latestMetrics.humidity != null ? `${Number(latestMetrics.humidity).toFixed(1)}%` : '--', change: 'Latest reading' },
  ];

  container.innerHTML = stats.map(s => `
    <div class="stat-card">
      <div class="stat-header"><h3>${s.label}</h3></div>
      <div class="stat-value">${s.value}</div>
      <div class="stat-change">${s.change}</div>
    </div>
  `).join('');
}

// ============================================
// UPDATE NODE PANELS
// ============================================

function updateNodePanels(data) {
  const now = Date.now();
  const nodes = { NODE_TH: { metrics: ['temperature', 'humidity'] }, NODE_PA: { metrics: ['pressure', 'ethanol'] } };

  Object.entries(nodes).forEach(([nodeId, config]) => {
    const nodeData = data.filter(d => d.node_id === nodeId);
    const latest = nodeData[nodeData.length - 1];
    const statusEl = document.getElementById(`nodeStatus_${nodeId}`);
    const metricsEl = document.getElementById(`metrics_${nodeId}`);

    if (statusEl) {
      const isOnline = latest && (now - new Date(latest.timestamp).getTime()) < NODE_ONLINE_THRESHOLD_MS;
      statusEl.textContent = isOnline ? 'Online' : 'Offline';
      statusEl.className = `node-status ${isOnline ? 'online' : 'offline'}`;
    }

    if (metricsEl) {
      const cards = metricsEl.querySelectorAll('.metric-card');
      config.metrics.forEach((metric, i) => {
        if (cards[i]) {
          const valEl = cards[i].querySelector('.metric-value');
          const trendEl = cards[i].querySelector('.metric-trend');
          const val = latest?.metrics?.[metric];
          if (valEl) valEl.textContent = val != null ? Number(val).toFixed(2) : '--';
          if (trendEl) trendEl.textContent = latest ? `Updated: ${new Date(latest.timestamp).toLocaleTimeString()}` : 'No data';
        }
      });
    }
  });

  // Handle node filter visibility
  const filter = document.getElementById('nodeFilter')?.value;
  document.querySelectorAll('.node-panel').forEach(panel => {
    const nid = panel.dataset.nodeId;
    panel.style.display = (!filter || filter === nid) ? '' : 'none';
  });
}

// ============================================
// RENDER ALERTS
// ============================================

function renderAlerts(alerts) {
  const list = document.getElementById('alertsList');
  if (!list) return;

  if (!alerts || alerts.length === 0) {
    list.innerHTML = '<div class="empty-state compact">No active alerts.</div>';
    return;
  }

  list.innerHTML = alerts.map(a => `
    <div class="alert-item">
      <div>
        <div class="alert-title">${escapeHtml(a.alert_type || a.metric || 'Alert')}</div>
        <div class="alert-message">${escapeHtml(a.message || `${a.metric}: ${a.value}`)}</div>
        <div class="alert-time">${a.timestamp ? new Date(a.timestamp).toLocaleString() : ''}</div>
      </div>
      <div class="alert-actions">
        <span class="alert-value">${a.value != null ? Number(a.value).toFixed(2) : ''}</span>
      </div>
    </div>
  `).join('');
}

// ============================================
// UPDATE ACTIVITY FEED
// ============================================

function updateActivityFeed(data) {
  const list = document.getElementById('activityList');
  if (!list) return;

  if (!data || data.length === 0) {
    list.innerHTML = '<div class="empty-state">No data available. Waiting for sensor node uploads.</div>';
    return;
  }

  const recent = data.slice(-20).reverse();
  list.innerHTML = recent.map(d => {
    const statusClass = `status-${d.status || 'pending'}`;
    const metricsStr = d.metrics ? Object.entries(d.metrics).map(([k, v]) => `${k}: ${Number(v).toFixed(2)}`).join(', ') : '';
    return `
      <div class="activity-item">
        <div class="activity-time">${new Date(d.timestamp).toLocaleString()}</div>
        <div class="activity-text">${escapeHtml(d.node_id || d.sensor_id || 'Unknown')} — ${metricsStr || 'No metrics'}</div>
        <span class="activity-status ${statusClass}">${d.status || 'pending'}</span>
      </div>
    `;
  }).join('');
}

// ============================================
// RENDER CHARTS (Chart.js)
// ============================================

function renderCharts(data) {
  const filter = document.getElementById('nodeFilter')?.value;
  let filtered = filter ? data.filter(d => d.node_id === filter) : data;

  // Apply history range if set
  if (appState.historyRange.from) {
    const from = new Date(appState.historyRange.from).getTime();
    filtered = filtered.filter(d => new Date(d.timestamp).getTime() >= from);
  }
  if (appState.historyRange.to) {
    const to = new Date(appState.historyRange.to).getTime();
    filtered = filtered.filter(d => new Date(d.timestamp).getTime() <= to);
  }

  const chartConfigs = [
    { id: 'temperatureChart', metric: 'temperature', label: 'Temperature (°C)', color: '#ff6384', bg: 'rgba(255,99,132,0.15)' },
    { id: 'humidityChart', metric: 'humidity', label: 'Humidity (%)', color: '#36a2eb', bg: 'rgba(54,162,235,0.15)' },
    { id: 'pressureChart', metric: 'pressure', label: 'Pressure (hPa)', color: '#ffce56', bg: 'rgba(255,206,86,0.15)' },
    { id: 'ethanolChart', metric: 'ethanol', label: 'Ethanol (ppm)', color: '#4bc0c0', bg: 'rgba(75,192,192,0.15)' },
  ];

  chartConfigs.forEach(cfg => {
    const canvas = document.getElementById(cfg.id);
    if (!canvas) return;

    const points = filtered
      .filter(d => d.metrics && d.metrics[cfg.metric] != null)
      .map(d => ({ x: new Date(d.timestamp), y: Number(d.metrics[cfg.metric]) }));

    if (appState.charts[cfg.id]) {
      appState.charts[cfg.id].data.datasets[0].data = points;
      appState.charts[cfg.id].update('none');
      return;
    }

    const ctx = canvas.getContext('2d');
    appState.charts[cfg.id] = new Chart(ctx, {
      type: 'line',
      data: {
        datasets: [{
          label: cfg.label,
          data: points,
          borderColor: cfg.color,
          backgroundColor: cfg.bg,
          fill: true,
          tension: 0.3,
          pointRadius: 2,
          pointHoverRadius: 5,
          borderWidth: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { type: 'time', time: { tooltipFormat: 'HH:mm:ss', unit: 'minute' }, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8' } },
          y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8' } },
        },
        plugins: {
          legend: { labels: { color: '#cbd5e1' } },
          zoom: { zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'x' }, pan: { enabled: true, mode: 'x' } },
        },
        animation: { duration: 300 },
      },
    });
  });
}

// ============================================
// HISTORY RANGE
// ============================================

function applyHistoryRange() {
  const from = document.getElementById('historyFrom')?.value;
  const to = document.getElementById('historyTo')?.value;
  appState.historyRange = { from: from || '', to: to || '' };
  renderCharts(appState.allData);
  showToast('Range Applied', `Showing data ${from ? 'from ' + from : ''} ${to ? 'to ' + to : ''}`.trim(), 'info');
}

function clearHistoryRange() {
  appState.historyRange = { from: '', to: '' };
  const fromEl = document.getElementById('historyFrom');
  const toEl = document.getElementById('historyTo');
  if (fromEl) fromEl.value = '';
  if (toEl) toEl.value = '';
  renderCharts(appState.allData);
  showToast('Range Cleared', 'Showing all data', 'info');
}

// ============================================
// ANALYTICS
// ============================================

async function loadAnalyticsData() {
  try {
    showSpinner(true);
    const data = await fetchFromAPI('/list').catch(() => ({ data: [] }));
    const records = (data.data || []).sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
    appState.allData = records;

    renderAnalyticsKPIs(records);
    renderAnalyticsMetricTable(records);
    renderAnalyticsNodes(records);
  } catch (err) {
    showToast('Analytics Error', err.message, 'error');
  } finally {
    showSpinner(false);
  }
}

function renderAnalyticsKPIs(records) {
  const grid = document.getElementById('analyticsKpiGrid');
  if (!grid) return;

  const now = Date.now();
  const nodeIds = new Set(records.map(r => r.node_id).filter(Boolean));
  const activeNodes = new Set(records.filter(r => now - new Date(r.timestamp).getTime() < NODE_ONLINE_THRESHOLD_MS).map(r => r.node_id));
  const last24h = records.filter(r => now - new Date(r.timestamp).getTime() < 86400000);
  const uptime = records.length > 0 ? ((activeNodes.size / Math.max(nodeIds.size, 1)) * 100).toFixed(0) : 0;

  const kpis = [
    { label: 'Total Readings', value: records.length },
    { label: 'Active Nodes', value: `${activeNodes.size} / ${nodeIds.size}` },
    { label: '24h Readings', value: last24h.length },
    { label: 'Uptime', value: `${uptime}%` },
  ];

  grid.innerHTML = kpis.map(k => `
    <div class="stat-card"><div class="stat-header"><h3>${k.label}</h3></div><div class="stat-value">${k.value}</div></div>
  `).join('');
}

function renderAnalyticsMetricTable(records) {
  const tbody = document.getElementById('analyticsMetricBody');
  if (!tbody) return;

  const now = Date.now();
  const metrics = ['temperature', 'humidity', 'pressure', 'ethanol'];
  const last60m = records.filter(r => now - new Date(r.timestamp).getTime() < 3600000);
  const last24h = records.filter(r => now - new Date(r.timestamp).getTime() < 86400000);

  const rows = metrics.map(m => {
    const allVals = records.map(r => r.metrics?.[m]).filter(v => v != null).map(Number);
    const vals60 = last60m.map(r => r.metrics?.[m]).filter(v => v != null).map(Number);
    const vals24 = last24h.map(r => r.metrics?.[m]).filter(v => v != null).map(Number);
    const latest = allVals.length > 0 ? allVals[allVals.length - 1] : null;
    const avg60 = vals60.length > 0 ? (vals60.reduce((a, b) => a + b, 0) / vals60.length) : null;
    const avg24 = vals24.length > 0 ? (vals24.reduce((a, b) => a + b, 0) / vals24.length) : null;
    const min24 = vals24.length > 0 ? Math.min(...vals24) : null;
    const max24 = vals24.length > 0 ? Math.max(...vals24) : null;
    const trend = avg60 != null && avg24 != null ? (avg60 > avg24 ? '↑' : avg60 < avg24 ? '↓' : '→') : '—';

    const fmt = v => v != null ? Number(v).toFixed(2) : '—';
    return `<tr><td>${m}</td><td>${fmt(latest)}</td><td>${fmt(avg60)}</td><td>${fmt(avg24)}</td><td>${trend}</td><td>${fmt(min24)}</td><td>${fmt(max24)}</td></tr>`;
  });

  tbody.innerHTML = rows.join('') || '<tr><td colspan="7">No metric data available</td></tr>';
}

function renderAnalyticsNodes(records) {
  const grid = document.getElementById('analyticsNodesGrid');
  if (!grid) return;

  const nodeMap = {};
  records.forEach(r => {
    const nid = r.node_id || 'unknown';
    if (!nodeMap[nid]) nodeMap[nid] = [];
    nodeMap[nid].push(r);
  });

  grid.innerHTML = Object.entries(nodeMap).map(([nid, recs]) => {
    const latest = recs[recs.length - 1];
    const metricsStr = latest?.metrics ? Object.entries(latest.metrics).map(([k, v]) => `<div><strong>${k}:</strong> ${Number(v).toFixed(2)}</div>`).join('') : 'No metrics';
    return `
      <div class="stat-card">
        <div class="stat-header"><h3>${escapeHtml(nid)}</h3></div>
        <div class="stat-change">${recs.length} readings</div>
        <div style="margin-top:0.5rem;font-size:0.9rem;color:#cbd5e1">${metricsStr}</div>
      </div>`;
  }).join('');
}

// ============================================
// HISTORY
// ============================================

async function loadHistoryData() {
  try {
    showSpinner(true);
    const data = await fetchFromAPI('/list').catch(() => ({ data: [] }));
    let records = data.data || [];

    const statusFilter = document.getElementById('statusFilter')?.value;
    if (statusFilter) records = records.filter(r => r.status === statusFilter);

    records.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

    const tbody = document.getElementById('historyTableBody');
    if (!tbody) return;

    if (records.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No records found.</td></tr>';
      return;
    }

    tbody.innerHTML = records.map(r => {
      const statusClass = `status-${r.status || 'pending'}`;
      const hasSummary = r.summary && Object.keys(r.summary).length > 0;
      return `<tr>
        <td title="${escapeHtml(r.data_id)}">${escapeHtml((r.data_id || '').slice(0, 8))}…</td>
        <td>${escapeHtml(r.sensor_id || r.node_id || '—')}</td>
        <td><span class="activity-status ${statusClass}">${r.status || 'pending'}</span></td>
        <td>${new Date(r.timestamp).toLocaleString()}</td>
        <td>${hasSummary ? '✅ Yes' : '⏳ Pending'}</td>
        <td><button class="btn btn-small btn-primary" onclick="viewRecordSummary('${escapeHtml(r.data_id)}')">View</button></td>
      </tr>`;
    }).join('');
  } catch (err) {
    showToast('History Error', err.message, 'error');
  } finally {
    showSpinner(false);
  }
}

function viewRecordSummary(dataId) {
  document.getElementById('summarySearchId').value = dataId;
  switchToSection('analytics');
  setTimeout(() => searchSummary(), 300);
}

// ============================================
// SEARCH SUMMARY
// ============================================

async function searchSummary() {
  const input = document.getElementById('summarySearchId');
  const container = document.getElementById('summaryResult');
  if (!input || !container) return;

  const dataId = input.value.trim();
  if (!dataId) { showToast('Search', 'Please enter a Data ID', 'warning'); return; }

  try {
    container.innerHTML = '<div class="empty-state">Searching...</div>';
    const result = await fetchFromAPI(`/summary?id=${encodeURIComponent(dataId)}`);
    const r = result.data || result;

    const metricsHtml = r.metrics ? Object.entries(r.metrics).map(([k, v]) => `<div><strong>${k}:</strong> ${Number(v).toFixed(2)}</div>`).join('') : 'No metrics';
    const summaryHtml = r.summary && Object.keys(r.summary).length > 0
      ? Object.entries(r.summary).map(([k, v]) => `<div><strong>${k}:</strong> ${typeof v === 'object' ? JSON.stringify(v) : v}</div>`).join('')
      : 'No summary available';

    container.innerHTML = `
      <div class="stat-card" style="grid-column:1/-1">
        <div class="stat-header"><h3>${escapeHtml(r.data_id || dataId)}</h3></div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-top:1rem">
          <div><h4 style="color:#00d4ff;margin-bottom:0.5rem">Record Info</h4>
            <div>Status: <span class="activity-status status-${r.status || 'pending'}">${r.status || 'pending'}</span></div>
            <div>Node: ${escapeHtml(r.node_id || '—')}</div>
            <div>Sensor: ${escapeHtml(r.sensor_id || '—')}</div>
            <div>Time: ${r.timestamp ? new Date(r.timestamp).toLocaleString() : '—'}</div>
          </div>
          <div><h4 style="color:#00d4ff;margin-bottom:0.5rem">Metrics</h4>${metricsHtml}</div>
        </div>
        <div style="margin-top:1rem"><h4 style="color:#00d4ff;margin-bottom:0.5rem">Summary</h4>${summaryHtml}</div>
      </div>`;
  } catch (err) {
    container.innerHTML = `<div class="empty-state">Record not found or API error: ${escapeHtml(err.message)}</div>`;
  }
}

// ============================================
// EXPORT CSV
// ============================================

function exportData() {
  const data = appState.allData;
  if (!data || data.length === 0) { showToast('Export', 'No data to export', 'warning'); return; }

  const allMetricKeys = new Set();
  data.forEach(d => { if (d.metrics) Object.keys(d.metrics).forEach(k => allMetricKeys.add(k)); });
  const metricCols = [...allMetricKeys].sort();

  const headers = ['data_id', 'sensor_id', 'node_id', 'status', 'timestamp', ...metricCols];
  const rows = data.map(d => {
    const base = [d.data_id, d.sensor_id, d.node_id, d.status, d.timestamp];
    const metrics = metricCols.map(k => d.metrics?.[k] ?? '');
    return [...base, ...metrics].map(v => `"${String(v ?? '').replace(/"/g, '""')}"`).join(',');
  });

  const csv = [headers.join(','), ...rows].join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `iot_data_export_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
  showToast('Export', `Exported ${data.length} records`, 'success');
}

// ============================================
// UI HELPERS
// ============================================

function showSpinner(show) {
  const el = document.getElementById('loadingSpinner');
  if (!el) return;
  el.classList.toggle('active', show);
}

function showToast(title, message, type = 'info') {
  const container = document.getElementById('toastContainer');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<strong>${escapeHtml(title)}</strong><br/><small>${escapeHtml(message)}</small>`;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 5000);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
