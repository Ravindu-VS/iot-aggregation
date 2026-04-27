/* ============================================
   IOT DATA AGGREGATION - FRONTEND APPLICATION
   ============================================ */

// Configuration
const API_BASE_URL = window.IOT_API_BASE_URL || '/api';
const AUTO_REFRESH_INTERVAL = 2000; // 2 seconds
const STATUS_REFRESH_INTERVAL = 1000; // 1 second local UI refresh
const NODE_ONLINE_THRESHOLD_MS = 15000;

const zoomPlugin = window.ChartZoom || window.chartjsPluginZoom || window['chartjs-plugin-zoom'];
if (zoomPlugin && window.Chart && typeof window.Chart.register === 'function') {
  window.Chart.register(zoomPlugin);
}

// Global State
let appState = {
  currentSection: 'dashboard',
  autoRefresh: true,
  refreshInterval: null,
  statusInterval: null,
  allData: [],
  historyRange: {
    from: '',
    to: '',
  },
  alerts: [],
  activeAlertKeys: new Set(),
  charts: {},
};

// ============================================
// DOM INITIALIZATION
// ============================================

document.addEventListener('DOMContentLoaded', () => {
  initializeEventListeners();
  switchToSection('dashboard');
  loadDashboardData();
  setupAutoRefresh();
  setupStatusRefresh();
});

function initializeEventListeners() {
  // Navigation
  document.querySelectorAll('.nav-link').forEach((link) => {
    link.addEventListener('click', (e) => {
      const section = e.target.dataset.section;
      switchToSection(section);
    });
  });

  // Controls
  document.getElementById('refreshBtn').addEventListener('click', refreshCurrentSection);
  document.getElementById('autoRefreshToggle').addEventListener('change', toggleAutoRefresh);

  // Node Filter in Dashboard
  const nodeFilter = document.getElementById('nodeFilter');
  if (nodeFilter) {
    nodeFilter.addEventListener('change', loadDashboardData);
  }

  const applyHistoryRangeBtn = document.getElementById('applyHistoryRangeBtn');
  if (applyHistoryRangeBtn) {
    applyHistoryRangeBtn.addEventListener('click', applyHistoryRange);
  }

  const clearHistoryRangeBtn = document.getElementById('clearHistoryRangeBtn');
  if (clearHistoryRangeBtn) {
    clearHistoryRangeBtn.addEventListener('click', clearHistoryRange);
  }

  // Analytics
  const searchSummaryBtn = document.getElementById('searchSummaryBtn');
  const summarySearchId = document.getElementById('summarySearchId');
  if (searchSummaryBtn) {
    searchSummaryBtn.addEventListener('click', searchSummary);
  }
  if (summarySearchId) {
    summarySearchId.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') searchSummary();
    });
  }

  // History
  document.getElementById('statusFilter').addEventListener('change', loadHistoryData);
  document.getElementById('exportBtn').addEventListener('click', exportData);

}

// ============================================
// SECTION NAVIGATION
// ============================================

function switchToSection(sectionId) {
  // Hide all sections
  document.querySelectorAll('.section').forEach((section) => {
    section.classList.remove('active');
  });

  // Show selected section
  const selectedSection = document.getElementById(`${sectionId}-section`);
  if (selectedSection) {
    selectedSection.classList.add('active');
  }

  // Update nav links
  document.querySelectorAll('.nav-link').forEach((link) => {
    link.classList.toggle('active', link.dataset.section === sectionId);
  });

  appState.currentSection = sectionId;

  // Load section-specific data
  switch (sectionId) {
    case 'dashboard':
      loadDashboardData();
      break;
    case 'analytics':
      loadAnalyticsData();
      break;
    case 'history':
      loadHistoryData();
      break;
  }
}

// ============================================
// DASHBOARD
// ============================================

async function loadDashboardData(options = {}) {
  const { silent = false } = options;
  try {
    if (!silent) {
      showSpinner(true);
    }
    const data = await fetchFromAPI('/list');
    appState.allData = (data.data || []).sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    );

    // Apply node filter if selected
    const nodeFilter = document.getElementById('nodeFilter')?.value || '';
    const filteredData = nodeFilter
      ? appState.allData.filter((d) => d.node_id === nodeFilter)
      : appState.allData;

    try {
      const alertsResponse = await fetchFromAPI('/alerts');
      appState.alerts = Array.isArray(alertsResponse.data) ? alertsResponse.data : [];
    } catch (alertError) {
      appState.alerts = [];
      console.warn('Failed to load alerts:', alertError);
    }

    updateStatistics(filteredData);
    updateNodePanels(filteredData);
    renderAlerts(appState.alerts);
    updateActivityFeed(filteredData);
    renderCharts(filteredData);
  } catch (error) {
    showToast('Error loading dashboard data', error.message, 'error');
  } finally {
    if (!silent) {
      showSpinner(false);
    }
  }
}

function updateStatistics(data = appState.allData) {
  const stats = {
    total: data.length,
    pending: data.filter((d) => d.status === 'pending').length,
    processing: data.filter((d) => d.status === 'processing').length,
    done: data.filter((d) => d.status === 'done').length,
    failed: data.filter((d) => d.status === 'failed').length,
  };

  const totalSubmissions = document.getElementById('totalSubmissions');
  const processingCount = document.getElementById('processingCount');
  const completedCount = document.getElementById('completedCount');
  const failedCount = document.getElementById('failedCount');

  if (totalSubmissions) {
    totalSubmissions.textContent = stats.total;
  }
  if (processingCount) {
    processingCount.textContent = stats.processing + stats.pending;
  }
  if (completedCount) {
    completedCount.textContent = stats.done;
  }
  if (failedCount) {
    failedCount.textContent = stats.failed;
  }
}

function updateNodePanels(data = appState.allData) {
  const nodeIds = ['NODE_TH', 'NODE_PA'];
  const now = Date.now();

  nodeIds.forEach((nodeId) => {
    const nodeData = data.filter((d) => d.node_id === nodeId);
    const latestRecord = nodeData.length
      ? nodeData.reduce((latest, current) => {
          return new Date(current.timestamp).getTime() > new Date(latest.timestamp).getTime()
            ? current
            : latest;
        })
      : null;

    const latestTimestamp = latestRecord ? new Date(latestRecord.timestamp).getTime() : 0;
    const isFresh = latestRecord && !Number.isNaN(latestTimestamp) && now - latestTimestamp <= NODE_ONLINE_THRESHOLD_MS;
    const statusEl = document.getElementById(`nodeStatus_${nodeId}`);
    const metricsEl = document.getElementById(`metrics_${nodeId}`);
    const metricKeys = nodeId === 'NODE_TH' ? ['temperature', 'humidity'] : ['pressure', 'ethanol'];

    if (statusEl) {
      if (!latestRecord) {
        statusEl.textContent = 'Offline';
        statusEl.className = 'node-status disconnected';
      } else if (!isFresh || latestRecord.status !== 'done') {
        statusEl.textContent = 'Disconnected';
        statusEl.className = 'node-status disconnected';
      } else {
        statusEl.textContent = 'Online';
        statusEl.className = 'node-status online';
      }
    }

    if (metricsEl) {
      const metricCards = Array.from(metricsEl.querySelectorAll('.metric-card'));
      metricCards.forEach((card, index) => {
        const valueEl = card.querySelector('.metric-value');
        const trendEl = card.querySelector('.metric-trend');
        const metricKey = metricKeys[index];
        // Use summary if available (processed), otherwise fall back to raw metrics
        const value = latestRecord?.summary?.[metricKey]?.latest ?? latestRecord?.metrics?.[metricKey];

        if (valueEl) {
          valueEl.textContent = value !== undefined && value !== null ? formatMetricValue(value) : '--';
        }
        if (trendEl) {
          trendEl.textContent = latestRecord && isFresh ? 'Latest' : 'No data';
        }
      });
    }
  });
}

function renderAlerts(alerts = appState.alerts) {
  const alertsList = document.getElementById('alertsList');
  if (!alertsList) {
    return;
  }

  const activeAlerts = [...(alerts || [])].filter((alert) => alert.status === 'active');
  const normalizedAlerts = activeAlerts.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

  const nextAlertKeys = new Set(normalizedAlerts.map((alert) => alert.alert_id));
  const previousAlertKeys = appState.activeAlertKeys;

  normalizedAlerts.forEach((alert) => {
    if (!previousAlertKeys.has(alert.alert_id)) {
      showToast('Sensor Alert', `${alert.node_id} ${alert.metric} ${alert.message}`, 'warning');
    }
  });

  appState.activeAlertKeys = nextAlertKeys;

  if (normalizedAlerts.length === 0) {
    alertsList.innerHTML = '<div class="empty-state compact">No active alerts.</div>';
    return;
  }

  alertsList.innerHTML = normalizedAlerts
    .map(
      (alert) => `
      <div class="alert-item">
        <div>
          <div class="alert-title">${alert.node_id} · ${alert.metric}</div>
          <div class="alert-message">${alert.message}</div>
          <div class="alert-time">${formatDateTime(alert.timestamp)}</div>
        </div>
        <div class="alert-actions">
          <div class="alert-value">${Number(alert.value).toFixed(2)}</div>
          <button type="button" class="btn btn-small btn-secondary clear-alert-btn" data-alert-id="${alert.alert_id}">Clear</button>
        </div>
      </div>
    `
    )
    .join('');

  alertsList.querySelectorAll('.clear-alert-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const alertId = btn.dataset.alertId;
      if (!alertId) {
        return;
      }
      await clearAlert(alertId);
    });
  });
}

async function clearAlert(alertId) {
  try {
    await fetchFromAPI(`/alerts/${encodeURIComponent(alertId)}`, { method: 'DELETE' });
    appState.alerts = appState.alerts.filter((alert) => alert.alert_id !== alertId);
    appState.activeAlertKeys.delete(alertId);
    renderAlerts(appState.alerts);
    showToast('Alert Cleared', `Alert ${truncateId(alertId)} cleared`, 'success');
  } catch (error) {
    showToast('Clear Alert Failed', error.message, 'error');
  }
}

function updateActivityFeed(data = appState.allData) {
  const activityList = document.getElementById('activityList');
  if (!activityList) {
    return;
  }

  const sorted = [...(data || [])].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  const latestItems = sorted.slice(0, 8);

  if (latestItems.length === 0) {
    activityList.innerHTML = '<div class="empty-state">No data available. Waiting for sensor node uploads.</div>';
    return;
  }

  activityList.innerHTML = latestItems
    .map((item) => `
      <div class="activity-item">
        <div class="activity-time">${formatTime(item.timestamp)}</div>
        <div class="activity-text">
          <strong>${item.sensor_id || 'Unknown sensor'}</strong> (${item.node_id || 'Unknown node'}) • ${truncateId(item.data_id)}
        </div>
        <div class="activity-status ${getStatusClass(item.status)}">${item.status || 'unknown'}</div>
      </div>
    `)
    .join('');
}

function renderCharts(data = appState.allData) {
  const metricConfigs = [
    { chartKey: 'temperatureChart', label: 'Temperature (°C)', metricKey: 'temperature', color: '#22c55e' },
    { chartKey: 'humidityChart', label: 'Humidity (%)', metricKey: 'humidity', color: '#38bdf8' },
    { chartKey: 'pressureChart', label: 'Pressure (hPa)', metricKey: 'pressure', color: '#f97316' },
    { chartKey: 'ethanolChart', label: 'Ethanol (ppm)', metricKey: 'ethanol', color: '#f43f5e' },
  ];

  metricConfigs.forEach((config) => {
    const chartData = buildMetricHistorySeries(data, config.metricKey);
    const ctx = document.getElementById(config.chartKey);
    if (!ctx) {
      return;
    }

    if (appState.charts[config.chartKey]) {
      appState.charts[config.chartKey].destroy();
    }

    appState.charts[config.chartKey] = new Chart(ctx, {
      type: 'line',
      data: {
        labels: chartData.labels,
        datasets: [
          {
            label: config.label,
            data: chartData.values,
            borderColor: config.color,
            backgroundColor: `${config.color}22`,
            fill: true,
            tension: 0.35,
            pointBackgroundColor: config.color,
            pointBorderColor: '#1e293b',
            pointBorderWidth: 2,
            pointRadius: 3,
            pointHoverRadius: 5,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        interaction: {
          mode: 'index',
          intersect: false,
        },
        plugins: {
          zoom: {
            pan: {
              enabled: true,
              mode: 'x',
            },
            zoom: {
              wheel: {
                enabled: true,
              },
              pinch: {
                enabled: true,
              },
              mode: 'x',
            },
          },
          legend: {
            labels: {
              color: '#cbd5e1',
            },
          },
          tooltip: {
            backgroundColor: 'rgba(15, 23, 42, 0.8)',
            titleColor: '#00d4ff',
            bodyColor: '#cbd5e1',
            borderColor: '#00d4ff',
            borderWidth: 1,
          },
        },
        scales: {
          y: {
            beginAtZero: false,
            ticks: {
              color: '#cbd5e1',
            },
            grid: {
              color: '#334155',
            },
          },
          x: {
            ticks: {
              color: '#cbd5e1',
            },
            grid: {
              color: '#334155',
            },
          },
        },
      },
    });
  });
}

function buildMetricHistorySeries(data, metricKey) {
  const series = [...data]
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
    .map((item) => {
      const summary = item.summary?.[metricKey];
      const value = summary?.latest ?? item.metrics?.[metricKey];
      if (value === undefined || value === null) {
        return null;
      }

      return {
        timestamp: item.timestamp,
        value: Number(value),
      };
    })
    .filter(Boolean);

  return {
    labels: series.map((entry) => formatDateTime(entry.timestamp)),
    values: series.map((entry) => entry.value),
  };
}

// ============================================
// ANALYTICS
// ============================================

async function loadAnalyticsData(options = {}) {
  const { silent = false } = options;
  try {
    if (!silent) {
      showSpinner(true);
    }
    const data = await fetchFromAPI('/list');
    const records = (data.data || []).sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    );
    renderAnalyticsInsights(records);

    const summaryResult = document.getElementById('summaryResult');
    if (summaryResult && !summaryResult.innerHTML.trim()) {
      summaryResult.innerHTML =
        '<div class="empty-state">Use Record Lookup to inspect one specific submission summary.</div>';
    }
  } catch (error) {
    showToast('Error loading analytics', error.message, 'error');
  } finally {
    if (!silent) {
      showSpinner(false);
    }
  }
}

function renderAnalyticsInsights(records) {
  renderAnalyticsKpis(records);
  renderAnalyticsMetricRows(records);
  renderAnalyticsNodeCards(records);
}

function renderAnalyticsKpis(records) {
  const container = document.getElementById('analyticsKpiGrid');
  if (!container) return;

  const now = Date.now();
  const in24h = records.filter((r) => new Date(r.timestamp).getTime() >= now - 24 * 60 * 60 * 1000);
  const in60m = records.filter((r) => new Date(r.timestamp).getTime() >= now - 60 * 60 * 1000);
  const done24h = in24h.filter((r) => r.status === 'done').length;
  const failed24h = in24h.filter((r) => r.status === 'failed').length;
  const completion24h = in24h.length > 0 ? (done24h / in24h.length) * 100 : 0;
  const activeNodes60m = new Set(in60m.map((r) => r.node_id).filter(Boolean)).size;

  const cards = [
    { label: 'Samples (24h)', value: in24h.length, hint: 'Total submissions in last 24 hours' },
    { label: 'Completion (24h)', value: `${completion24h.toFixed(1)}%`, hint: `${done24h} done / ${failed24h} failed` },
    { label: 'Samples (60m)', value: in60m.length, hint: 'Recent submission throughput' },
    { label: 'Active Nodes (60m)', value: activeNodes60m, hint: 'Nodes seen in last hour' },
  ];

  container.innerHTML = cards
    .map(
      (card) => `
      <div class="analytics-kpi-card">
        <div class="analytics-kpi-label">${card.label}</div>
        <div class="analytics-kpi-value">${card.value}</div>
        <div class="analytics-kpi-hint">${card.hint}</div>
      </div>
    `
    )
    .join('');
}

function renderAnalyticsMetricRows(records) {
  const tbody = document.getElementById('analyticsMetricBody');
  if (!tbody) return;

  const metricConfig = [
    { key: 'temperature', label: 'Temperature (°C)' },
    { key: 'humidity', label: 'Humidity (%)' },
    { key: 'pressure', label: 'Pressure (hPa)' },
    { key: 'ethanol', label: 'Ethanol (ppm)' },
  ];

  const now = Date.now();
  const doneRecords = records.filter((r) => r.status === 'done');

  const rows = metricConfig
    .map((metric) => {
      const values24h = collectMetricValues(doneRecords, metric.key, now - 24 * 60 * 60 * 1000, now);
      const values60m = collectMetricValues(doneRecords, metric.key, now - 60 * 60 * 1000, now);
      const valuesPrev60m = collectMetricValues(doneRecords, metric.key, now - 2 * 60 * 60 * 1000, now - 60 * 60 * 1000);
      const latest = collectMetricValues(doneRecords, metric.key, 0, now).at(-1);

      const stats24h = summarizeValues(values24h);
      const stats60m = summarizeValues(values60m);
      const statsPrev60m = summarizeValues(valuesPrev60m);

      const trendPct = stats60m.avg !== null && statsPrev60m.avg !== null && statsPrev60m.avg !== 0
        ? ((stats60m.avg - statsPrev60m.avg) / statsPrev60m.avg) * 100
        : null;

      const trendText = trendPct === null ? 'N/A' : `${trendPct >= 0 ? '+' : ''}${trendPct.toFixed(1)}%`;
      const trendClass = trendPct === null ? 'flat' : trendPct > 0 ? 'up' : trendPct < 0 ? 'down' : 'flat';

      if (stats24h.count === 0 && stats60m.count === 0 && latest === null) {
        return `
          <tr>
            <td>${metric.label}</td>
            <td colspan="6" style="color: var(--text-tertiary);">No recent data</td>
          </tr>
        `;
      }

      return `
        <tr>
          <td>${metric.label}</td>
          <td>${formatMetricValue(latest)}</td>
          <td>${formatMetricValue(stats60m.avg)}</td>
          <td>${formatMetricValue(stats24h.avg)}</td>
          <td class="analytics-trend ${trendClass}">${trendText}</td>
          <td>${formatMetricValue(stats24h.min)}</td>
          <td>${formatMetricValue(stats24h.max)}</td>
        </tr>
      `;
    })
    .join('');

  tbody.innerHTML = rows;
}

function renderAnalyticsNodeCards(records) {
  const container = document.getElementById('analyticsNodesGrid');
  if (!container) return;

  const nodeIds = [...new Set(records.map((r) => r.node_id).filter(Boolean))].sort();
  if (nodeIds.length === 0) {
    container.innerHTML = '<div class="empty-state">No node analytics available yet.</div>';
    return;
  }

  const now = Date.now();
  container.innerHTML = nodeIds
    .map((nodeId) => {
      const nodeRecords = records.filter((r) => r.node_id === nodeId);
      const latestRecord = nodeRecords.at(-1);
      const samples60m = nodeRecords.filter((r) => new Date(r.timestamp).getTime() >= now - 60 * 60 * 1000).length;

      const metricSummaries = ['temperature', 'humidity', 'pressure', 'ethanol']
        .map((metricKey) => {
          const values = collectMetricValues(
            nodeRecords.filter((r) => r.status === 'done'),
            metricKey,
            now - 60 * 60 * 1000,
            now
          );
          const stats = summarizeValues(values);
          if (stats.count === 0) return null;
          return `<span>${metricKey}: ${formatMetricValue(stats.avg)} avg</span>`;
        })
        .filter(Boolean)
        .join('');

      return `
        <div class="analytics-node-card">
          <div class="analytics-node-title">${nodeId}</div>
          <div class="analytics-node-meta">Last seen: ${latestRecord ? formatTime(latestRecord.timestamp) : 'Never'}</div>
          <div class="analytics-node-meta">Samples (60m): ${samples60m}</div>
          <div class="analytics-node-metrics">${metricSummaries || '<span>No metric averages in last hour</span>'}</div>
        </div>
      `;
    })
    .join('');
}

function collectMetricValues(records, metricKey, fromMs, toMs) {
  return records
    .filter((record) => {
      const t = new Date(record.timestamp).getTime();
      return !Number.isNaN(t) && t >= fromMs && t <= toMs;
    })
    .map((record) => record.summary?.[metricKey]?.latest ?? record.metrics?.[metricKey])
    .filter((value) => value !== undefined && value !== null)
    .map((value) => Number(value))
    .filter((value) => !Number.isNaN(value));
}

function summarizeValues(values) {
  if (!values || values.length === 0) {
    return { min: null, max: null, avg: null, count: 0 };
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const avg = values.reduce((acc, n) => acc + n, 0) / values.length;
  return { min, max, avg, count: values.length };
}

function formatMetricValue(value) {
  return value === null || value === undefined ? 'N/A' : Number(value).toFixed(2);
}

async function searchSummary() {
  try {
    const dataId = document.getElementById('summarySearchId').value.trim();
    if (!dataId) {
      showToast('Validation Error', 'Please enter a Data ID', 'error');
      return;
    }

    showSpinner(true);
    const response = await fetchFromAPI(`/summary?id=${encodeURIComponent(dataId)}`);
    renderSummaries([response.data]);
  } catch (error) {
    showToast('Error searching summary', error.message, 'error');
  } finally {
    showSpinner(false);
  }
}

function renderSummaries(summaries) {
  const container = document.getElementById('summaryResult');

  if (summaries.length === 0) {
    container.innerHTML = '<div class="empty-state">No completed summaries found</div>';
    return;
  }

  container.innerHTML = summaries
    .map(
      (item) => `
    <div class="summary-card">
      <div class="summary-header">
        <div>
          <div class="summary-id">${item.data_id}</div>
          <div class="summary-sensor">${item.sensor_id}</div>
        </div>
        <span class="summary-status ${getStatusClass(item.status)}">${item.status}</span>
      </div>
      <div class="summary-stats">
        ${
          item.summary
            ? `
          ${renderSummaryStats(item.summary)}
        `
            : '<div class="empty-state">Summary not yet available</div>'
        }
      </div>
      <div style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--border-color); font-size: 0.85rem; color: var(--text-tertiary);">
        Submitted: ${formatTime(item.timestamp)}
      </div>
    </div>
  `
    )
    .join('');
}

// ============================================
// HISTORY
// ============================================

async function loadHistoryData(options = {}) {
  const { silent = false } = options;
  try {
    if (!silent) {
      showSpinner(true);
    }
    const data = await fetchFromAPI('/list');
    let records = data.data || [];

    // Filter by status
    const statusFilter = document.getElementById('statusFilter').value;
    if (statusFilter) {
      records = records.filter((r) => r.status === statusFilter);
    }

    // Sort by timestamp descending
    records.sort(
      (a, b) =>
        new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    );

    renderHistoryTable(records);
  } catch (error) {
    showToast('Error loading history', error.message, 'error');
  } finally {
    if (!silent) {
      showSpinner(false);
    }
  }
}

function renderHistoryTable(records) {
  const tbody = document.getElementById('historyTableBody');

  if (records.length === 0) {
    tbody.innerHTML =
      '<tr><td colspan="6" class="text-center">No records found</td></tr>';
    return;
  }

  tbody.innerHTML = records
    .map(
      (record) => `
    <tr>
      <td class="data-id-cell" title="${record.data_id}">${truncateId(record.data_id)}</td>
      <td>${record.sensor_id}</td>
      <td><span class="summary-status ${getStatusClass(record.status)}">${record.status}</span></td>
      <td>${formatDateTime(record.timestamp)}</td>
      <td>
        ${
          record.summary
            ? `
          <div style="font-size: 0.85rem;">
            ${renderHistorySummary(record.summary)}
          </div>
        `
            : '<span style="color: var(--text-tertiary);">Pending</span>'
        }
      </td>
      <td>
        <div class="table-actions">
          <button class="btn btn-small btn-secondary" onclick="viewDetailSummary('${record.data_id}')">
            View Summary
          </button>
        </div>
      </td>
    </tr>
  `
    )
    .join('');
}

function viewDetailSummary(dataId) {
  switchToSection('analytics');
  document.getElementById('summarySearchId').value = dataId;
  searchSummary();
}

function exportData() {
  try {
    const records = appState.allData;
    const csv = [
      ['Data ID', 'Sensor ID', 'Node ID', 'Status', 'Timestamp', 'Summary JSON'],
      ...records.map((r) => [
        r.data_id,
        r.sensor_id,
        r.node_id || '',
        r.status,
        r.timestamp,
        r.summary ? JSON.stringify(r.summary) : '',
      ]),
    ]
      .map((row) => row.map((cell) => `"${cell}"`).join(','))
      .join('\n');

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `iot-data-export-${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);

    showToast('Success', 'Data exported to CSV', 'success');
  } catch (error) {
    showToast('Export Failed', error.message, 'error');
  }
}

function renderSummaryStats(summary) {
  // Metrics-based structure can be compact ({latest,count}) or aggregate ({latest,min,max,avg,count})
  const metricEntries = Object.entries(summary || {}).filter(([, value]) => {
    return value && typeof value === 'object' && value.latest !== undefined;
  });

  if (metricEntries.length > 0) {
    return metricEntries
      .map(([metricName, metric]) => {
        const hasAggregateStats =
          metric.min !== undefined && metric.max !== undefined && metric.avg !== undefined;

        const detailLine = hasAggregateStats
          ? `Min:${Number(metric.min).toFixed(2)} Max:${Number(metric.max).toFixed(2)} Avg:${Number(metric.avg).toFixed(2)} Count:${metric.count ?? 1}`
          : `Count:${metric.count ?? 1}`;

        return `
        <div class="stat-item">
          <div class="stat-label">${metricName.toUpperCase()}</div>
          <div class="stat-value-lg">${Number(metric.latest).toFixed(2)}</div>
          <div class="stat-value-lg" style="font-size:0.9rem; margin-top:0.25rem;">
            ${detailLine}
          </div>
        </div>
      `;
      })
      .join('');
  }

  // Legacy flat structure: {min,max,avg,count}
  return `
    <div class="stat-item">
      <div class="stat-label">Min Value</div>
      <div class="stat-value-lg">${summary.min !== undefined ? Number(summary.min).toFixed(2) : 'N/A'}</div>
    </div>
    <div class="stat-item">
      <div class="stat-label">Max Value</div>
      <div class="stat-value-lg">${summary.max !== undefined ? Number(summary.max).toFixed(2) : 'N/A'}</div>
    </div>
    <div class="stat-item">
      <div class="stat-label">Average</div>
      <div class="stat-value-lg">${summary.avg !== undefined ? Number(summary.avg).toFixed(2) : 'N/A'}</div>
    </div>
    <div class="stat-item">
      <div class="stat-label">Count</div>
      <div class="stat-value-lg">${summary.count ?? 'N/A'}</div>
    </div>
  `;
}

function renderHistorySummary(summary) {
  const metricEntries = Object.entries(summary || {}).filter(([, value]) => {
    return value && typeof value === 'object' && value.latest !== undefined;
  });
  if (metricEntries.length > 0) {
    return metricEntries
      .map(([metricName, metric]) => {
        const hasAggregateStats =
          metric.min !== undefined && metric.max !== undefined && metric.avg !== undefined;

        if (hasAggregateStats) {
          return `${metricName}: Latest=${Number(metric.latest).toFixed(2)}, Avg=${Number(metric.avg).toFixed(2)}`;
        }

        return `${metricName}: Latest=${Number(metric.latest).toFixed(2)}, Count=${metric.count ?? 1}`;
      })
      .join(' | ');
  }

  return `Min: ${summary.min !== undefined ? Number(summary.min).toFixed(2) : 'N/A'} | Max: ${summary.max !== undefined ? Number(summary.max).toFixed(2) : 'N/A'} | Avg: ${summary.avg !== undefined ? Number(summary.avg).toFixed(2) : 'N/A'}`;
}

function applyHistoryRange() {
  const fromValue = document.getElementById('historyFrom')?.value || '';
  const toValue = document.getElementById('historyTo')?.value || '';

  if (fromValue && toValue && new Date(fromValue).getTime() > new Date(toValue).getTime()) {
    showToast('Validation Error', 'The From date/time must be earlier than the To date/time.', 'error');
    return;
  }

  appState.historyRange = {
    from: fromValue,
    to: toValue,
  };

  renderCharts(getDashboardNodeFilteredData());
}

function clearHistoryRange() {
  const fromInput = document.getElementById('historyFrom');
  const toInput = document.getElementById('historyTo');

  if (fromInput) fromInput.value = '';
  if (toInput) toInput.value = '';

  appState.historyRange = {
    from: '',
    to: '',
  };

  renderCharts(getDashboardNodeFilteredData());
}

function filterRecordsByHistoryRange(records) {
  const { from, to } = appState.historyRange;

  if (!from && !to) {
    return records;
  }

  const fromTime = from ? new Date(from).getTime() : null;
  const toTime = to ? new Date(to).getTime() : null;

  return records.filter((record) => {
    const timestamp = new Date(record.timestamp).getTime();
    if (Number.isNaN(timestamp)) {
      return false;
    }

    if (fromTime !== null && timestamp < fromTime) {
      return false;
    }

    if (toTime !== null && timestamp > toTime) {
      return false;
    }

    return true;
  });
}

function getDashboardNodeFilteredData() {
  const nodeFilter = document.getElementById('nodeFilter')?.value || '';
  let records = appState.allData;

  if (nodeFilter) {
    records = records.filter((record) => record.node_id === nodeFilter);
  }

  return records;
}

// ============================================
// API UTILITIES
// ============================================

async function fetchFromAPI(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    ...((options.headers) || {}),
  };

  const response = await fetch(url, {
    ...options,
    headers,
  });

  const rawBody = await response.text();
  let data;
  try {
    data = rawBody ? JSON.parse(rawBody) : null;
  } catch {
    const snippet = rawBody ? rawBody.slice(0, 140).replace(/\s+/g, ' ').trim() : 'empty response body';
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${snippet}`);
    }
    throw new Error(`Invalid JSON response: ${snippet}`);
  }

  if (!response.ok) {
    throw new Error(data?.error || `HTTP Error: ${response.status}`);
  }

  // Normalize response format
  if (data && typeof data === 'object' && !Array.isArray(data) && Object.prototype.hasOwnProperty.call(data, 'data')) {
    return data;
  }

  return { data };
}

// ============================================
// AUTO REFRESH
// ============================================

function setupAutoRefresh() {
  if (appState.autoRefresh) {
    appState.refreshInterval = setInterval(refreshCurrentSection, AUTO_REFRESH_INTERVAL);
  }
}

function setupStatusRefresh() {
  if (appState.statusInterval) {
    clearInterval(appState.statusInterval);
  }

  appState.statusInterval = setInterval(() => {
    if (appState.currentSection === 'dashboard') {
      updateNodePanels(appState.allData);
      renderAlerts(appState.alerts);
    }
  }, STATUS_REFRESH_INTERVAL);
}


function toggleAutoRefresh(e) {
  appState.autoRefresh = e.target.checked;

  if (appState.refreshInterval) {
    clearInterval(appState.refreshInterval);
  }

  if (appState.autoRefresh) {
    setupAutoRefresh();
    showToast('Auto-refresh enabled', 'Data will refresh every 5 seconds', 'success');
  } else {
    showToast('Auto-refresh disabled', 'Manual refresh only', 'warning');
  }
}

function refreshCurrentSection() {
  switch (appState.currentSection) {
    case 'dashboard':
      loadDashboardData({ silent: true });
      break;
    case 'analytics':
      loadAnalyticsData({ silent: true });
      break;
    case 'history':
      loadHistoryData({ silent: true });
      break;
  }
}

// ============================================
// UI HELPERS
// ============================================

function showSpinner(show) {
  const spinner = document.getElementById('loadingSpinner');
  if (show) {
    spinner.classList.add('active');
  } else {
    spinner.classList.remove('active');
  }
}

function showToast(title, message, type = 'info') {
  const container = document.getElementById('toastContainer');

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <div class="toast-content">
      <div class="toast-title">${title}</div>
      <div class="toast-message">${message}</div>
    </div>
    <button class="toast-close">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="18" y1="6" x2="6" y2="18"></line>
        <line x1="6" y1="6" x2="18" y2="18"></line>
      </svg>
    </button>
  `;

  container.appendChild(toast);

  const closeBtn = toast.querySelector('.toast-close');
  closeBtn.addEventListener('click', () => {
    toast.remove();
  });

  // Auto-remove after 5 seconds
  setTimeout(() => {
    toast.remove();
  }, 5000);
}

function truncateId(id) {
  return id.substring(0, 8) + '...' + id.substring(id.length - 8);
}

function formatTime(timestamp) {
  const date = new Date(timestamp);
  const now = new Date();
  const diff = now - date;

  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (seconds < 60) return 'Just now';
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;

  return date.toLocaleDateString();
}

function formatDateTime(timestamp) {
  const date = new Date(timestamp);
  return date.toLocaleString();
}

function getStatusClass(status) {
  switch (status) {
    case 'pending':
      return 'status-pending';
    case 'processing':
      return 'status-processing';
    case 'done':
      return 'status-done';
    case 'failed':
      return 'status-failed';
    default:
      return '';
  }
}

