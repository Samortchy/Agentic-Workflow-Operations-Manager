let _currentApprovalId = null;

document.addEventListener('DOMContentLoaded', async () => {
  if (!Auth.requireAuth()) return;
  await initSidebar();
  await loadApprovals();
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
});

async function loadApprovals() {
  const tbody = document.getElementById('approvals-body');
  const status = document.getElementById('filter-status').value;

  try {
    const params = status ? `?status=${status}` : '';
    const data   = await api.get(`/api/approvals${params}`);
    const list   = Array.isArray(data) ? data : (data?.approvals || []);

    if (!list.length) {
      tbody.innerHTML = emptyRow(8, status === 'pending' ? 'No pending approvals' : 'No approvals found');
      return;
    }

    tbody.innerHTML = list.map(a => {
      const preview  = (a.command_preview || '').slice(0, 80);
      const isPending = a.status === 'pending';
      return `<tr class="tbl-row">
        <td style="padding:12px 20px;font-family:'JetBrains Mono',monospace;font-size:11px;color:#8DD3CE;white-space:nowrap;">${(a.task_id || '—').slice(0,8)}</td>
        <td style="padding:12px 16px;font-size:13px;color:#FCF3E3;font-weight:500;">${a.agent_name || '—'}</td>
        <td style="padding:12px 16px;font-family:'JetBrains Mono',monospace;font-size:11px;color:#8DD3CE;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${a.command_preview || ''}">${preview || '—'}${a.command_preview?.length > 80 ? '…' : ''}</td>
        <td style="padding:12px 16px;font-family:'JetBrains Mono',monospace;font-size:11px;color:#8DD3CE;">${a.approval_type || '—'}</td>
        <td style="padding:12px 16px;font-size:12px;color:#FCF3E3;">${levelLabel(a.required_level)}</td>
        <td style="padding:12px 16px;">${statusPill(a.status)}</td>
        <td style="padding:12px 16px;font-size:12px;color:${isExpiringSoon(a.timeout_at) ? '#F4A258' : '#8DD3CE'};white-space:nowrap;">${fmtDate(a.timeout_at)}</td>
        <td style="padding:12px 20px;text-align:right;">
          ${isPending ? `<button onclick="openModal('${a.approval_id}')" class="btn-primary" style="font-size:12px;padding:6px 14px;">Resolve</button>` : ''}
        </td>
      </tr>`;
    }).join('');

    // Store for modal use
    window._approvalsList = list;
  } catch (e) {
    tbody.innerHTML = emptyRow(8, 'Failed to load approvals');
  }
}

function isExpiringSoon(timeoutAt) {
  if (!timeoutAt) return false;
  return new Date(timeoutAt).getTime() - Date.now() < 30 * 60 * 1000;
}

function openModal(approvalId) {
  const a = (window._approvalsList || []).find(x => x.approval_id === approvalId);
  if (!a) return;

  _currentApprovalId = approvalId;

  document.getElementById('modal-agent-name').textContent = `${a.agent_name} — ${a.approval_type}`;
  document.getElementById('modal-command').textContent    = a.command_preview || '—';
  document.getElementById('modal-note').value             = '';

  const ctxEl = document.getElementById('modal-context-block');
  if (a.context && Object.keys(a.context).length) {
    document.getElementById('modal-context').textContent = JSON.stringify(a.context, null, 2);
    ctxEl.style.display = 'block';
  } else {
    ctxEl.style.display = 'none';
  }

  document.getElementById('resolve-modal').style.display = 'flex';
}

function closeModal() {
  document.getElementById('resolve-modal').style.display = 'none';
  _currentApprovalId = null;
}

async function resolveApproval(status) {
  if (!_currentApprovalId) return;

  const emp  = Auth.getEmployee();
  const note = document.getElementById('modal-note').value.trim();

  const approveBtn = document.getElementById('approve-btn');
  const denyBtn    = document.getElementById('deny-btn');
  approveBtn.disabled = denyBtn.disabled = true;

  try {
    await api.patch(`/api/approvals/${_currentApprovalId}/resolve`, {
      status,
      resolved_by:     emp?.email || 'unknown',
      resolution_note: note || undefined,
    });

    showToast(`Approval ${status === 'approved' ? 'approved' : 'denied'} successfully`);
    closeModal();
    await loadApprovals();
  } catch (e) {
    showToast(e.message || 'Failed to resolve approval', 'error');
  } finally {
    approveBtn.disabled = denyBtn.disabled = false;
  }
}
