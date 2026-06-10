document.addEventListener('DOMContentLoaded', async () => {
  if (!Auth.requireAuth()) return;
  await initSidebar();
  await loadPerformance();
});

async function loadPerformance() {
  const agentsBody = document.getElementById('p-agents');
  const recentBody = document.getElementById('p-recent');
  agentsBody.innerHTML = emptyRow(4, 'Loading…');
  recentBody.innerHTML = emptyRow(6, 'Loading…');

  let signals = [];
  try {
    const data = await api.get('/api/outcome-signals?signal_type=execution_eval');
    signals = Array.isArray(data) ? data : (data?.signals || []);
  } catch (e) {
    agentsBody.innerHTML = emptyRow(4, 'Failed to load');
    recentBody.innerHTML = emptyRow(6, 'Failed to load evaluations');
    return;
  }

  // Each signal: { task_id, timestamp, value: <verdict dict incl overall_score, agent_name,
  //                signal_verdict, auto_flag, issues, final_status> }
  const rows = signals.map(s => ({
    task_id: s.task_id,
    when:    s.timestamp,
    v:       s.value || {},
  })).filter(r => typeof r.v.overall_score === 'number');

  const total = rows.length;
  const successes = rows.filter(r => r.v.signal_verdict === 'success').length;
  const flagged   = rows.filter(r => r.v.auto_flag === true).length;
  const avg = total ? (rows.reduce((a, r) => a + (r.v.overall_score || 0), 0) / total) : 0;

  document.getElementById('p-total').textContent   = total;
  document.getElementById('p-success').textContent = total ? Math.round((successes / total) * 100) + '%' : '—';
  document.getElementById('p-avg').textContent     = total ? avg.toFixed(1) + '/5' : '—';
  document.getElementById('p-flagged').textContent = flagged;

  // ── Per-agent breakdown ──
  const byAgent = {};
  for (const r of rows) {
    const a = r.v.agent_name || 'unknown';
    (byAgent[a] = byAgent[a] || { runs: 0, sum: 0, ok: 0 });
    byAgent[a].runs++; byAgent[a].sum += (r.v.overall_score || 0);
    if (r.v.signal_verdict === 'success') byAgent[a].ok++;
  }
  const agents = Object.entries(byAgent).sort((a, b) => b[1].runs - a[1].runs);
  agentsBody.innerHTML = agents.length ? agents.map(([name, s]) => `
    <tr class="tbl-row">
      <td style="padding:11px 20px;font-size:13px;color:#FCF3E3;">${escapeHtml(name)}</td>
      <td style="padding:11px 12px;text-align:right;font-size:13px;color:#8DD3CE;">${s.runs}</td>
      <td style="padding:11px 12px;text-align:right;">${scoreBadge(s.sum / s.runs)}</td>
      <td style="padding:11px 20px;text-align:right;font-size:13px;color:#8DD3CE;">${Math.round((s.ok / s.runs) * 100)}%</td>
    </tr>`).join('') : emptyRow(4, 'No evaluations yet');

  renderCharts(rows, byAgent);
  loadClassification();

  // ── Recent evaluations ──
  const recent = rows.slice().sort((a, b) => String(b.when).localeCompare(String(a.when))).slice(0, 15);
  recentBody.innerHTML = recent.length ? recent.map(r => {
    const issue = Array.isArray(r.v.issues) && r.v.issues.length ? r.v.issues[0] : '—';
    const verdict = r.v.signal_verdict === 'success'
      ? '<span class="pill" style="color:#5BC26A;background:rgba(91,194,106,0.12);">success</span>'
      : '<span class="pill" style="color:#E05252;background:rgba(224,82,82,0.15);">failure</span>';
    return `<tr class="tbl-row">
      <td style="padding:11px 20px;font-family:'JetBrains Mono',monospace;font-size:11px;color:#8DD3CE;white-space:nowrap;">${(r.task_id || '—').slice(0,10)}</td>
      <td style="padding:11px 12px;font-size:13px;color:#FCF3E3;">${escapeHtml(r.v.agent_name || '—')}</td>
      <td style="padding:11px 12px;">${scoreBadge(r.v.overall_score)}</td>
      <td style="padding:11px 12px;">${verdict}${r.v.auto_flag ? ' <span class="pill" style="color:#F4A258;background:rgba(244,162,88,0.15);">flagged</span>' : ''}</td>
      <td style="padding:11px 16px;font-size:12px;color:#8DD3CE;max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(issue)}</td>
      <td style="padding:11px 20px;text-align:right;font-size:12px;color:#8DD3CE;white-space:nowrap;">${fmtRelative(r.when)}</td>
    </tr>`;
  }).join('') : emptyRow(6, 'No evaluations yet — run a task to generate one');
}

let _trendChart, _agentsChart;

function renderCharts(rows, byAgent) {
  if (typeof Chart === 'undefined') return;  // CDN unavailable — skip charts gracefully
  const opts = (min, max) => ({
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      y: { min, max, ticks: { color: '#8DD3CE' }, grid: { color: 'rgba(141,211,206,0.12)' } },
      x: { ticks: { color: '#8DD3CE' }, grid: { display: false } },
    },
  });

  // Trend: overall score in chronological order
  const chrono = rows.slice().sort((a, b) => String(a.when).localeCompare(String(b.when)));
  if (_trendChart) _trendChart.destroy();
  _trendChart = new Chart(document.getElementById('chart-trend'), {
    type: 'line',
    data: {
      labels: chrono.map((_, i) => i + 1),
      datasets: [{ data: chrono.map(r => r.v.overall_score), borderColor: '#F4A258',
        backgroundColor: 'rgba(244,162,88,0.15)', tension: 0.3, fill: true, pointRadius: 2 }],
    },
    options: opts(0, 5),
  });

  // Per-agent average score
  const aLabels = Object.keys(byAgent);
  if (_agentsChart) _agentsChart.destroy();
  _agentsChart = new Chart(document.getElementById('chart-agents'), {
    type: 'bar',
    data: {
      labels: aLabels,
      datasets: [{ data: aLabels.map(a => byAgent[a].sum / byAgent[a].runs), backgroundColor: '#8DD3CE' }],
    },
    options: opts(0, 5),
  });
}

async function loadClassification() {
  const el = document.getElementById('cls-summary');
  try {
    const data = await api.get('/api/outcome-signals?signal_type=classification_eval');
    const list = (Array.isArray(data) ? data : (data?.signals || [])).map(s => s.value || {});
    if (!list.length) { el.textContent = ''; return; }
    const deptOk = list.filter(v => v.intake && v.intake.score >= 4).length;
    const review = list.filter(v => v.needs_review).length;
    el.innerHTML = `Classification judge — department rated correct on `
      + `<strong style="color:#FCF3E3;">${Math.round((deptOk / list.length) * 100)}%</strong> of `
      + `${list.length} runs · <strong style="color:#F4A258;">${review}</strong> flagged for human review`;
  } catch { el.textContent = ''; }
}

function scoreBadge(score) {
  const s = Math.round((score || 0) * 10) / 10;
  const c = s >= 4 ? '#5BC26A' : s >= 3 ? '#F4A258' : '#E05252';
  return `<span style="color:${c};font-family:'JetBrains Mono',monospace;font-size:13px;">${s}/5</span>`;
}

function escapeHtml(x) {
  return String(x ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
