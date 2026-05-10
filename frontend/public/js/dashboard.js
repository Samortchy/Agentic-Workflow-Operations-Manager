document.addEventListener('DOMContentLoaded', async () => {
  if (!Auth.requireAuth()) return;

  const dateEl = document.getElementById('topbar-date');
  if (dateEl) {
    dateEl.textContent = new Date().toLocaleDateString('en-GB', {
      weekday: 'short', day: '2-digit', month: 'short', year: 'numeric',
    });
  }

  await initSidebar();
  await Promise.all([loadStats(), loadRecentTasks(), loadPendingApprovals()]);
});

async function loadStats() {
  try {
    const [taskData, approvalData] = await Promise.all([
      api.get('/api/tasks'),
      api.get('/api/approvals?status=pending').catch(() => []),
    ]);

    const tasks     = Array.isArray(taskData) ? taskData : (taskData?.tasks || []);
    const approvals = Array.isArray(approvalData) ? approvalData : (approvalData?.approvals || []);
    const today     = new Date().toDateString();

    const active    = tasks.filter(t => t.status === 'in_progress').length;
    const completed = tasks.filter(t =>
      t.status === 'completed' && new Date(t.updated_at || t.completed_at).toDateString() === today
    ).length;

    document.getElementById('stat-total').textContent     = tasks.length;
    document.getElementById('stat-approvals').textContent = approvals.length;
    document.getElementById('stat-active').textContent    = active;
    document.getElementById('stat-completed').textContent = completed;
  } catch (e) {
    console.error('Stats error:', e);
  }
}

async function loadRecentTasks() {
  const tbody = document.getElementById('tasks-body');
  try {
    const data  = await api.get('/api/tasks');
    const tasks = (Array.isArray(data) ? data : (data?.tasks || [])).slice(0, 12);

    if (!tasks.length) {
      tbody.innerHTML = emptyRow(6, 'No tasks yet');
      return;
    }

    tbody.innerHTML = tasks.map(t => {
      const type = t.task_type || t.envelope?.task?.task_type || '—';
      return `<tr class="tbl-row" onclick="window.location.href='/tasks/${t.task_id}'">
        <td style="padding:11px 20px;font-family:'JetBrains Mono',monospace;font-size:11px;color:#8DD3CE;white-space:nowrap;">${(t.task_id || '—').slice(0,8)}</td>
        <td style="padding:11px 16px;font-size:13px;color:#FCF3E3;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${type}</td>
        <td style="padding:11px 16px;">${statusPill(t.status)}</td>
        <td style="padding:11px 16px;">${priorityBadge(t.priority_score, t.priority_label)}</td>
        <td style="padding:11px 16px;font-family:'JetBrains Mono',monospace;font-size:11px;color:#8DD3CE;">${t.department || '—'}</td>
        <td style="padding:11px 20px;font-size:12px;color:#8DD3CE;text-align:right;white-space:nowrap;">${fmtRelative(t.created_at)}</td>
      </tr>`;
    }).join('');
  } catch (e) {
    tbody.innerHTML = emptyRow(6, 'Failed to load tasks');
  }
}

async function loadPendingApprovals() {
  const list = document.getElementById('approvals-list');
  try {
    const data      = await api.get('/api/approvals?status=pending').catch(() => []);
    const approvals = (Array.isArray(data) ? data : (data?.approvals || [])).slice(0, 6);

    if (!approvals.length) {
      list.innerHTML = `<p style="padding:20px;color:#8DD3CE;font-size:13px;margin:0;">No pending approvals</p>`;
      return;
    }

    list.innerHTML = approvals.map(a => {
      const preview = (a.command_preview || '').slice(0, 70);
      return `<div style="padding:12px 20px;border-bottom:1px solid #0A5A7C;cursor:pointer;transition:background 120ms;" onclick="window.location.href='/approvals'" onmouseover="this.style.background='rgba(10,90,124,0.2)'" onmouseout="this.style.background='transparent'">
        <div style="display:flex;align-items:start;justify-content:space-between;gap:8px;margin-bottom:4px;">
          <p style="margin:0;font-size:13px;color:#FCF3E3;font-weight:500;">${a.agent_name || '—'}</p>
          <span style="font-size:11px;color:#8DD3CE;white-space:nowrap;flex-shrink:0;">${fmtRelative(a.requested_at)}</span>
        </div>
        <p style="margin:0;font-size:11px;color:#8DD3CE;font-family:'JetBrains Mono',monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${preview || '—'}${a.command_preview?.length > 70 ? '…' : ''}</p>
      </div>`;
    }).join('');
  } catch {
    list.innerHTML = `<p style="padding:20px;color:#8DD3CE;font-size:13px;margin:0;">Unavailable</p>`;
  }
}
