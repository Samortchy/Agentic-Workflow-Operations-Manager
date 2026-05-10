document.addEventListener('DOMContentLoaded', async () => {
  if (!Auth.requireAuth()) return;
  await initSidebar();
  await loadLogs();
});

async function loadLogs() {
  const tbody = document.getElementById('logs-body');
  const countEl = document.getElementById('log-count');

  const agent = document.getElementById('filter-agent').value;
  const event = document.getElementById('filter-event').value;
  const from  = document.getElementById('filter-from').value;
  const to    = document.getElementById('filter-to').value;

  const parts = [];
  if (agent) parts.push(`agent_name=${encodeURIComponent(agent)}`);
  if (event) parts.push(`event_type=${encodeURIComponent(event)}`);
  if (from)  parts.push(`from=${encodeURIComponent(from)}`);
  if (to)    parts.push(`to=${encodeURIComponent(to)}`);
  const params = parts.length ? '?' + parts.join('&') : '';

  try {
    const data = await api.get(`/api/audit-logs${params}`);
    const logs = Array.isArray(data) ? data : (data?.logs || []);

    if (countEl) countEl.textContent = `${logs.length} event${logs.length !== 1 ? 's' : ''}`;

    if (!logs.length) {
      tbody.innerHTML = emptyRow(6, 'No audit logs match the current filters');
      return;
    }

    tbody.innerHTML = logs.map(log => {
      const isError   = log.event_type?.includes('failed') || log.event_type?.includes('error');
      const isSuccess = log.event_type?.includes('complete') || log.event_type?.includes('granted');
      const eventColor = isError ? '#E05252' : isSuccess ? '#5BC26A' : '#8DD3CE';

      const details = log.details && Object.keys(log.details).length
        ? `<span title="${JSON.stringify(log.details)}" style="cursor:help;font-family:'JetBrains Mono',monospace;font-size:10px;color:#8DD3CE;">${JSON.stringify(log.details).slice(0,60)}${JSON.stringify(log.details).length > 60 ? '…' : ''}</span>`
        : '—';

      return `<tr class="tbl-row">
        <td style="padding:12px 20px;font-size:12px;color:#8DD3CE;white-space:nowrap;">${fmtDate(log.timestamp)}</td>
        <td style="padding:12px 16px;">
          <span style="font-family:'JetBrains Mono',monospace;font-size:11px;color:${eventColor};">${log.event_type || '—'}</span>
        </td>
        <td style="padding:12px 16px;font-family:'JetBrains Mono',monospace;font-size:11px;color:#8DD3CE;">${log.agent_name || '—'}</td>
        <td style="padding:12px 16px;font-family:'JetBrains Mono',monospace;font-size:11px;color:#8DD3CE;">
          ${log.task_id
            ? `<a href="/tasks/${log.task_id}" style="color:#8DD3CE;text-decoration:none;" onmouseover="this.style.color='#F4A258'" onmouseout="this.style.color='#8DD3CE'">${(log.task_id || '').slice(0,8)}</a>`
            : '—'
          }
        </td>
        <td style="padding:12px 16px;font-size:12px;color:#8DD3CE;">${log.actor || '—'}</td>
        <td style="padding:12px 20px;font-size:12px;color:#8DD3CE;">${details}</td>
      </tr>`;
    }).join('');
  } catch (e) {
    tbody.innerHTML = emptyRow(6, 'Failed to load audit logs');
  }
}

function clearLogFilters() {
  document.getElementById('filter-agent').value = '';
  document.getElementById('filter-event').value = '';
  document.getElementById('filter-from').value  = '';
  document.getElementById('filter-to').value    = '';
  loadLogs();
}
