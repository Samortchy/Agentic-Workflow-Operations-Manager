document.addEventListener('DOMContentLoaded', async () => {
  if (!Auth.requireAuth()) return;
  await initSidebar();

  const emp = Auth.getEmployee();
  if (emp?.access_level >= 3) {
    const addBtn = document.getElementById('add-btn');
    if (addBtn) addBtn.style.display = 'inline-flex';
  }

  await loadEmployees();
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeAddModal(); });
});

async function loadEmployees() {
  const tbody = document.getElementById('employees-body');
  const dept   = document.getElementById('filter-dept').value;
  const active = document.getElementById('filter-active').value;

  try {
    const parts = [];
    if (dept)   parts.push(`department=${encodeURIComponent(dept)}`);
    if (active !== '') parts.push(`is_active=${active}`);
    const params = parts.length ? '?' + parts.join('&') : '';

    const data = await api.get(`/api/employees${params}`);
    const list = Array.isArray(data) ? data : (data?.employees || []);

    if (!list.length) {
      tbody.innerHTML = emptyRow(7, 'No employees found');
      return;
    }

    tbody.innerHTML = list.map(e => {
      const isActive = e.is_active !== false;
      return `<tr class="tbl-row">
        <td style="padding:12px 20px;font-size:13px;font-weight:500;color:#FCF3E3;">${e.name || '—'}</td>
        <td style="padding:12px 16px;font-size:12px;color:#8DD3CE;">${e.email || '—'}</td>
        <td style="padding:12px 16px;font-size:13px;color:#FCF3E3;">${e.role || '—'}</td>
        <td style="padding:12px 16px;"><span class="pill" style="color:#8DD3CE;background:rgba(141,211,206,0.1);">${e.department || '—'}</span></td>
        <td style="padding:12px 16px;font-size:12px;color:#FCF3E3;">${levelLabel(e.access_level)}</td>
        <td style="padding:12px 16px;">${isActive
          ? '<span class="pill" style="color:#5BC26A;background:rgba(91,194,106,0.12);">Active</span>'
          : '<span class="pill" style="color:#8DD3CE;background:rgba(141,211,206,0.08);">Inactive</span>'
        }</td>
        <td style="padding:12px 20px;text-align:right;">
          ${isActive && Auth.getEmployee()?.access_level >= 3
            ? `<button onclick="deactivateEmployee('${e.employee_id}')" style="font-size:11px;color:#8DD3CE;background:none;border:none;cursor:pointer;font-family:'DM Sans',sans-serif;" onmouseover="this.style.color='#E05252'" onmouseout="this.style.color='#8DD3CE'">Deactivate</button>`
            : ''
          }
        </td>
      </tr>`;
    }).join('');
  } catch (e) {
    tbody.innerHTML = emptyRow(7, 'Failed to load employees');
  }
}

async function deactivateEmployee(id) {
  if (!confirm('Deactivate this employee?')) return;
  try {
    await api.delete(`/api/employees/${id}`);
    showToast('Employee deactivated');
    loadEmployees();
  } catch (e) {
    showToast(e.message || 'Failed to deactivate', 'error');
  }
}

function openAddModal() {
  ['add-name','add-email','add-role'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  document.getElementById('add-error').style.display = 'none';
  document.getElementById('add-modal').style.display = 'flex';
}

function closeAddModal() {
  document.getElementById('add-modal').style.display = 'none';
}

async function submitAdd() {
  const errEl  = document.getElementById('add-error');
  const btn    = document.getElementById('add-submit-btn');
  errEl.style.display = 'none';
  btn.disabled = true;
  btn.textContent = 'Adding…';

  const body = {
    name:         document.getElementById('add-name').value.trim(),
    email:        document.getElementById('add-email').value.trim(),
    role:         document.getElementById('add-role').value.trim(),
    department:   document.getElementById('add-dept').value,
    access_level: parseInt(document.getElementById('add-level').value),
  };

  if (!body.name || !body.email || !body.role) {
    errEl.textContent = 'Name, email, and role are required.';
    errEl.style.display = 'block';
    btn.disabled = false;
    btn.textContent = 'Add Employee';
    return;
  }

  try {
    await api.post('/api/employees', body);
    showToast('Employee added successfully');
    closeAddModal();
    loadEmployees();
  } catch (e) {
    errEl.textContent = e.error || e.message || 'Failed to add employee';
    errEl.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Add Employee';
  }
}
