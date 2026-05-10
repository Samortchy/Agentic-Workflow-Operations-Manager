const TASK_ID = window.TASK_ID;
let _task = null;
let _activeTab = 'overview';

document.addEventListener('DOMContentLoaded', async () => {
  if (!Auth.requireAuth()) return;
  await initSidebar();
  await loadTask();
});

async function loadTask() {
  try {
    _task = await api.get(`/api/tasks/${TASK_ID}`);
    renderHeader();
    renderMeta();
    await renderTab('overview');
  } catch (e) {
    document.getElementById('task-header').innerHTML =
      `<p style="color:#E05252;font-size:13px;">Failed to load task: ${e.message}</p>`;
  }
}

function renderHeader() {
  const t         = _task;
  const taskType  = t.task_type || t.envelope?.task?.task_type || 'Unknown Task';
  const title     = t.envelope?.task?.title || taskType;

  document.getElementById('topbar-id').textContent = (t.task_id || '').slice(0, 8);

  const pillsEl = document.getElementById('topbar-pills');
  pillsEl.innerHTML = `${statusPill(t.status)} ${priorityBadge(t.priority_score, t.priority_label)}`;

  document.getElementById('task-header').innerHTML = `
    <h2 style="font-family:'DM Serif Display',serif;font-size:26px;color:#FCF3E3;margin:0 0 8px;line-height:1.2;">${title}</h2>
    <p style="font-size:13px;color:#8DD3CE;margin:0;font-family:'JetBrains Mono',monospace;font-size:12px;">${t.task_id}</p>
  `;
}

function renderMeta() {
  const t = _task;
  document.getElementById('meta-dept').textContent      = t.department || '—';
  document.getElementById('meta-requester').textContent = t.requester_email || t.envelope?.task?.requester_name || '—';
  document.getElementById('meta-deadline').textContent  = t.stated_deadline || t.envelope?.task?.stated_deadline || '—';
  document.getElementById('meta-agent').textContent     = t.agent_name || '—';
}

function switchTab(tab, btn) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  ['overview','envelope','timeline','signals'].forEach(t => {
    const el = document.getElementById(`tab-${t}`);
    if (el) el.style.display = t === tab ? 'block' : 'none';
  });
  _activeTab = tab;
  renderTab(tab);
}

async function renderTab(tab) {
  if (tab === 'overview')  renderOverview();
  if (tab === 'envelope')  renderEnvelope();
  if (tab === 'timeline')  await renderTimeline();
  if (tab === 'signals')   await renderSignals();
}

function renderOverview() {
  const t = _task;
  const env = t.envelope || {};
  const task = env.task || {};
  const intake = env.intake || {};

  const fields = [
    ['Task Type',    t.task_type || task.task_type || '—'],
    ['Is Autonomous',String(t.is_autonomous ?? intake.isAutonomous ?? '—')],
    ['Description',  task.description || '—'],
    ['Action Required', task.action_required || '—'],
    ['Success Criteria', task.success_criteria || '—'],
    ['Requester',    task.requester_name || t.requester_email || '—'],
    ['Deadline',     t.stated_deadline || task.stated_deadline || '—'],
    ['Created',      fmtDate(t.created_at)],
    ['Updated',      fmtDate(t.updated_at)],
    ['Completed',    fmtDate(t.completed_at)],
    ['Output Files', (t.output_files || []).length
      ? (t.output_files || []).map(f => `<span style="font-family:'JetBrains Mono',monospace;font-size:11px;color:#8DD3CE;">${f.file_path}</span>`).join('<br/>')
      : '—'],
  ];

  document.getElementById('overview-content').innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
      ${fields.map(([label, val]) => `
        <div>
          <p style="font-size:11px;color:#8DD3CE;font-family:'JetBrains Mono',monospace;text-transform:uppercase;letter-spacing:0.08em;margin:0 0 4px;">${label}</p>
          <p style="font-size:13px;color:#FCF3E3;margin:0;line-height:1.5;">${val}</p>
        </div>
      `).join('')}
    </div>
  `;
}

function renderEnvelope() {
  const env = _task.envelope || _task;
  document.getElementById('envelope-content').innerHTML = `
    <pre class="code-block" style="max-height:600px;overflow-y:auto;">${JSON.stringify(env, null, 2)}</pre>
  `;
}

async function renderTimeline() {
  const el = document.getElementById('timeline-content');
  try {
    const data = await api.get(`/api/audit-logs/task/${TASK_ID}/timeline`);
    const logs = Array.isArray(data) ? data : (data?.logs || []);

    if (!logs.length) {
      el.innerHTML = `<p style="color:#8DD3CE;font-size:13px;">No audit events yet</p>`;
      return;
    }

    el.innerHTML = `<div style="display:flex;flex-direction:column;gap:0;">
      ${logs.map((log, i) => {
        const isLast = i === logs.length - 1;
        const dotColor = log.event_type?.includes('failed') || log.event_type?.includes('error')
          ? '#E05252'
          : log.event_type?.includes('complete') || log.event_type?.includes('granted')
          ? '#5BC26A'
          : '#8DD3CE';

        return `<div style="display:flex;gap:16px;padding-bottom:${isLast ? '0' : '20px'};">
          <div style="display:flex;flex-direction:column;align-items:center;flex-shrink:0;">
            <div class="timeline-dot" style="background:${dotColor};"></div>
            ${!isLast ? `<div style="width:1px;flex:1;background:#0A5A7C;margin-top:4px;"></div>` : ''}
          </div>
          <div style="flex:1;padding-bottom:${isLast ? '0' : '4px'};">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px;">
              <span style="font-size:12px;font-weight:500;color:#FCF3E3;font-family:'JetBrains Mono',monospace;">${log.event_type || '—'}</span>
              ${log.agent_name ? `<span class="pill" style="color:#8DD3CE;background:rgba(141,211,206,0.1);font-size:10px;">${log.agent_name}</span>` : ''}
              <span style="font-size:11px;color:#8DD3CE;margin-left:auto;">${fmtDate(log.timestamp)}</span>
            </div>
            ${log.actor && log.actor !== 'system' ? `<p style="margin:0 0 4px;font-size:12px;color:#8DD3CE;">by ${log.actor}</p>` : ''}
            ${log.details && Object.keys(log.details).length
              ? `<pre style="margin:4px 0 0;font-family:'JetBrains Mono',monospace;font-size:11px;color:#8DD3CE;background:#011F30;border:1px solid #0A5A7C;padding:8px;border-radius:3px;overflow-x:auto;white-space:pre-wrap;">${JSON.stringify(log.details, null, 2)}</pre>`
              : ''
            }
          </div>
        </div>`;
      }).join('')}
    </div>`;
  } catch (e) {
    el.innerHTML = `<p style="color:#E05252;font-size:13px;">Failed to load timeline: ${e.message}</p>`;
  }
}

async function renderSignals() {
  const el = document.getElementById('signals-content');
  try {
    const [summaryData, signalsData] = await Promise.all([
      api.get(`/api/outcome-signals/task/${TASK_ID}/summary`),
      api.get(`/api/outcome-signals?task_id=${TASK_ID}`),
    ]);
    const signals = Array.isArray(signalsData) ? signalsData : (signalsData?.signals || []);

    const verdictColor = { success: '#5BC26A', failure: '#E05252', unknown: '#8DD3CE' };

    el.innerHTML = `
      ${summaryData ? `
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px;">
          <div class="stat-card">
            <p style="font-size:11px;color:#8DD3CE;font-family:'JetBrains Mono',monospace;text-transform:uppercase;letter-spacing:0.08em;margin:0 0 6px;">Total</p>
            <p style="font-family:'DM Serif Display',serif;font-size:28px;color:#FCF3E3;margin:0;">${summaryData.total_signals || 0}</p>
          </div>
          <div class="stat-card">
            <p style="font-size:11px;color:#8DD3CE;font-family:'JetBrains Mono',monospace;text-transform:uppercase;letter-spacing:0.08em;margin:0 0 6px;">Latest Verdict</p>
            <p style="font-family:'DM Serif Display',serif;font-size:22px;margin:0;color:${verdictColor[summaryData.latest_verdict] || '#FCF3E3'};">${summaryData.latest_verdict || '—'}</p>
          </div>
          <div class="stat-card">
            <p style="font-size:11px;color:#8DD3CE;font-family:'JetBrains Mono',monospace;text-transform:uppercase;letter-spacing:0.08em;margin:0 0 6px;">Success / Failure</p>
            <p style="font-family:'DM Serif Display',serif;font-size:22px;margin:0;color:#FCF3E3;"><span style="color:#5BC26A;">${summaryData.counts?.success || 0}</span> / <span style="color:#E05252;">${summaryData.counts?.failure || 0}</span></p>
          </div>
          <div class="stat-card">
            <p style="font-size:11px;color:#8DD3CE;font-family:'JetBrains Mono',monospace;text-transform:uppercase;letter-spacing:0.08em;margin:0 0 6px;">Unresolved</p>
            <p style="font-family:'DM Serif Display',serif;font-size:28px;margin:0;color:#FCF3E3;">${summaryData.counts?.unresolved || 0}</p>
          </div>
        </div>
      ` : ''}

      ${signals.length ? `
        <div class="section-card" style="overflow:hidden;">
          <table style="width:100%;border-collapse:collapse;">
            <thead>
              <tr style="border-bottom:1px solid #0A5A7C;">
                <th style="padding:10px 20px;text-align:left;font-size:11px;color:#8DD3CE;font-family:'JetBrains Mono',monospace;font-weight:400;text-transform:uppercase;letter-spacing:0.06em;">Signal Type</th>
                <th style="padding:10px 16px;text-align:left;font-size:11px;color:#8DD3CE;font-family:'JetBrains Mono',monospace;font-weight:400;text-transform:uppercase;letter-spacing:0.06em;">Verdict</th>
                <th style="padding:10px 16px;text-align:left;font-size:11px;color:#8DD3CE;font-family:'JetBrains Mono',monospace;font-weight:400;text-transform:uppercase;letter-spacing:0.06em;">Value</th>
                <th style="padding:10px 20px;text-align:right;font-size:11px;color:#8DD3CE;font-family:'JetBrains Mono',monospace;font-weight:400;text-transform:uppercase;letter-spacing:0.06em;">Timestamp</th>
              </tr>
            </thead>
            <tbody>
              ${signals.map(s => `
                <tr class="tbl-row">
                  <td style="padding:11px 20px;font-family:'JetBrains Mono',monospace;font-size:12px;color:#8DD3CE;">${s.signal_type || '—'}</td>
                  <td style="padding:11px 16px;">${s.verdict ? statusPill(s.verdict) : '<span style="color:#8DD3CE;font-size:12px;">—</span>'}</td>
                  <td style="padding:11px 16px;font-family:'JetBrains Mono',monospace;font-size:11px;color:#8DD3CE;max-width:200px;overflow:hidden;text-overflow:ellipsis;">${s.value ? JSON.stringify(s.value) : '—'}</td>
                  <td style="padding:11px 20px;font-size:12px;color:#8DD3CE;text-align:right;white-space:nowrap;">${fmtDate(s.timestamp)}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      ` : `<p style="color:#8DD3CE;font-size:13px;">No outcome signals yet</p>`}
    `;
  } catch (e) {
    el.innerHTML = `<p style="color:#E05252;font-size:13px;">Failed to load signals: ${e.message}</p>`;
  }
}
