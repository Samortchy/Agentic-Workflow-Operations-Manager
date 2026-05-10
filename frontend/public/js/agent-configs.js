let _currentConfigId = null;

document.addEventListener('DOMContentLoaded', async () => {
  if (!Auth.requireAuth()) return;
  await initSidebar();

  const emp = Auth.getEmployee();
  if (emp?.access_level >= 4) {
    const btn = document.getElementById('create-btn');
    if (btn) btn.style.display = 'inline-flex';
  }

  await loadConfigs();
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeViewModal(); });
});

async function loadConfigs() {
  const tbody = document.getElementById('configs-body');
  const agentFilter  = document.getElementById('filter-agent').value;
  const activeFilter = document.getElementById('filter-active').value;

  const parts = [];
  if (agentFilter)          parts.push(`agent_name=${encodeURIComponent(agentFilter)}`);
  if (activeFilter !== '')  parts.push(`is_active=${activeFilter}`);
  const params = parts.length ? '?' + parts.join('&') : '';

  try {
    const data    = await api.get(`/api/agent-configs${params}`);
    const configs = Array.isArray(data) ? data : (data?.configs || []);

    if (!configs.length) {
      tbody.innerHTML = emptyRow(7, 'No agent configs found');
      return;
    }

    tbody.innerHTML = configs.map(c => {
      const cfg     = c.config || {};
      const isActive = c.is_active !== false;
      return `<tr class="tbl-row">
        <td style="padding:12px 20px;font-family:'JetBrains Mono',monospace;font-size:12px;color:#8DD3CE;">${c.agent_name || '—'}</td>
        <td style="padding:12px 16px;font-family:'JetBrains Mono',monospace;font-size:11px;color:#8DD3CE;">${cfg.agent_version || c.version || '—'}</td>
        <td style="padding:12px 16px;"><span class="pill" style="color:#8DD3CE;background:rgba(141,211,206,0.1);">${cfg.department || '—'}</span></td>
        <td style="padding:12px 16px;font-family:'JetBrains Mono',monospace;font-size:11px;color:${cfg.risk_tier === 'high' ? '#F4A258' : cfg.risk_tier === 'critical' ? '#E05252' : '#8DD3CE'};">${cfg.risk_tier || '—'}</td>
        <td style="padding:12px 16px;font-family:'JetBrains Mono',monospace;font-size:11px;color:#8DD3CE;">${cfg.approval?.mode || '—'}</td>
        <td style="padding:12px 16px;">${isActive
          ? '<span class="pill" style="color:#5BC26A;background:rgba(91,194,106,0.12);">Active</span>'
          : '<span class="pill" style="color:#8DD3CE;background:rgba(141,211,206,0.08);">Inactive</span>'
        }</td>
        <td style="padding:12px 20px;text-align:right;">
          <button onclick="openViewModal('${c.config_id}')" style="font-size:12px;color:#8DD3CE;background:none;border:none;cursor:pointer;font-family:'DM Sans',sans-serif;" onmouseover="this.style.color='#F4A258'" onmouseout="this.style.color='#8DD3CE'">View</button>
        </td>
      </tr>`;
    }).join('');

    window._configsList = configs;
  } catch (e) {
    tbody.innerHTML = emptyRow(7, 'Failed to load agent configs');
  }
}

function openViewModal(configId) {
  const c = (window._configsList || []).find(x => x.config_id === configId);
  if (!c) return;

  _currentConfigId = configId;

  document.getElementById('modal-agent-name').textContent = c.agent_name || '—';
  document.getElementById('modal-config-meta').textContent =
    `Config ID: ${(c.config_id || '').slice(0,16)} · v${c.version || '1'} · Updated ${fmtDate(c.updated_at)}`;
  document.getElementById('modal-config-json').textContent = JSON.stringify(c.config || {}, null, 2);

  const emp = Auth.getEmployee();
  const deactivateBtn = document.getElementById('deactivate-btn');
  if (deactivateBtn) {
    deactivateBtn.style.display = (emp?.access_level >= 4 && c.is_active !== false) ? 'inline-flex' : 'none';
  }

  document.getElementById('view-modal').style.display = 'flex';
}

function closeViewModal() {
  document.getElementById('view-modal').style.display = 'none';
  _currentConfigId = null;
}

async function deactivateConfig() {
  if (!_currentConfigId) return;
  if (!confirm('Deactivate this agent config?')) return;
  try {
    await api.patch(`/api/agent-configs/${_currentConfigId}/deactivate`);
    showToast('Config deactivated');
    closeViewModal();
    loadConfigs();
  } catch (e) {
    showToast(e.message || 'Failed to deactivate', 'error');
  }
}

function openCreateModal() {
  showToast('Config creation coming soon — use the API directly.', 'success');
}
