let _allTasks = [];

document.addEventListener('DOMContentLoaded', async () => {
  if (!Auth.requireAuth()) return;
  await initSidebar();
  await loadTasks();

  document.getElementById('filter-search').addEventListener('keydown', e => {
    if (e.key === 'Enter') applyFilters();
  });
});

async function loadTasks() {
  const tbody = document.getElementById('tasks-body');
  try {
    const params = buildParams();
    const data   = await api.get(`/api/tasks${params}`);
    _allTasks    = Array.isArray(data) ? data : (data?.tasks || []);

    renderTable(_allTasks);
  } catch (e) {
    tbody.innerHTML = emptyRow(8, 'Failed to load tasks');
  }
}

function buildParams() {
  const status   = document.getElementById('filter-status').value;
  const dept     = document.getElementById('filter-dept').value;
  const priority = document.getElementById('filter-priority').value;
  const parts    = [];
  if (status)   parts.push(`status=${encodeURIComponent(status)}`);
  if (dept)     parts.push(`department=${encodeURIComponent(dept)}`);
  if (priority) parts.push(`priority_score=${encodeURIComponent(priority)}`);
  return parts.length ? '?' + parts.join('&') : '';
}

function applyFilters() {
  const search = document.getElementById('filter-search').value.toLowerCase();
  const filtered = search
    ? _allTasks.filter(t =>
        (t.task_type || '').toLowerCase().includes(search) ||
        (t.requester_email || '').toLowerCase().includes(search) ||
        (t.envelope?.task?.task_type || '').toLowerCase().includes(search)
      )
    : _allTasks;

  // Re-fetch with server-side filters, client-side search
  loadTasks();
}

function clearFilters() {
  document.getElementById('filter-status').value   = '';
  document.getElementById('filter-dept').value     = '';
  document.getElementById('filter-priority').value = '';
  document.getElementById('filter-search').value   = '';
  loadTasks();
}

function renderTable(tasks) {
  const tbody    = document.getElementById('tasks-body');
  const countEl  = document.getElementById('task-count');
  const search   = document.getElementById('filter-search').value.toLowerCase();

  const list = search
    ? tasks.filter(t =>
        (t.task_type || '').toLowerCase().includes(search) ||
        (t.requester_email || '').toLowerCase().includes(search)
      )
    : tasks;

  if (countEl) countEl.textContent = `${list.length} task${list.length !== 1 ? 's' : ''}`;

  if (!list.length) {
    tbody.innerHTML = emptyRow(8, 'No tasks match the current filters');
    return;
  }

  tbody.innerHTML = list.map(t => {
    const type      = t.task_type || t.envelope?.task?.task_type || '—';
    const agent     = t.agent_name || '—';
    const requester = t.requester_email || '—';
    return `<tr class="tbl-row" onclick="window.location.href='/tasks/${t.task_id}'">
      <td style="padding:12px 20px;font-family:'JetBrains Mono',monospace;font-size:11px;color:#8DD3CE;white-space:nowrap;">${(t.task_id || '—').slice(0,8)}</td>
      <td style="padding:12px 16px;font-size:13px;color:#FCF3E3;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${type}</td>
      <td style="padding:12px 16px;">${statusPill(t.status)}</td>
      <td style="padding:12px 16px;">${priorityBadge(t.priority_score, t.priority_label)}</td>
      <td style="padding:12px 16px;font-family:'JetBrains Mono',monospace;font-size:11px;color:#8DD3CE;">${t.department || '—'}</td>
      <td style="padding:12px 16px;font-family:'JetBrains Mono',monospace;font-size:11px;color:#8DD3CE;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${agent}</td>
      <td style="padding:12px 16px;font-size:12px;color:#8DD3CE;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${requester}</td>
      <td style="padding:12px 20px;font-size:12px;color:#8DD3CE;text-align:right;white-space:nowrap;">${fmtRelative(t.created_at)}</td>
    </tr>`;
  }).join('');
}
