/* api.js — Auth management, API client, shared UI helpers */

const Auth = {
  getTokens() {
    return {
      access:  localStorage.getItem('awom_access'),
      refresh: localStorage.getItem('awom_refresh'),
    };
  },
  setTokens(access, refresh) {
    localStorage.setItem('awom_access', access);
    if (refresh) localStorage.setItem('awom_refresh', refresh);
  },
  getUser()    { try { return JSON.parse(localStorage.getItem('awom_user') || 'null'); } catch { return null; } },
  setUser(u)   { localStorage.setItem('awom_user', JSON.stringify(u)); },
  getEmployee(){ try { return JSON.parse(localStorage.getItem('awom_employee') || 'null'); } catch { return null; } },
  setEmployee(e){ localStorage.setItem('awom_employee', JSON.stringify(e)); },
  clear() {
    ['awom_access','awom_refresh','awom_user','awom_employee'].forEach(k => localStorage.removeItem(k));
  },
  isLoggedIn() { return !!this.getTokens().access; },
  requireAuth() {
    if (!this.isLoggedIn()) { window.location.href = '/login'; return false; }
    // After sign-out, the browser's back/forward cache (bfcache) can restore this
    // protected page without re-running scripts — making logout look undone. Re-check
    // auth whenever the page is shown (incl. bfcache restores) and bounce if signed out.
    if (!this._bfGuard) {
      this._bfGuard = true;
      window.addEventListener('pageshow', () => {
        if (!Auth.isLoggedIn()) window.location.replace('/login');
      });
    }
    return true;
  },
  logout() {
    try {
      const { access } = this.getTokens();
      if (access) fetch(`${window.API_BASE}/api/auth/logout`, {
        method: 'POST', headers: { Authorization: `Bearer ${access}` },
      }).catch(() => {});
    } catch {}
    this.clear();
    window.location.href = '/login';
  },
};

let _refreshing = false;
let _refreshQueue = [];

async function _doRefresh() {
  if (_refreshing) return new Promise(r => _refreshQueue.push(r));
  _refreshing = true;
  const { refresh } = Auth.getTokens();
  if (!refresh) { _refreshing = false; return false; }
  try {
    const res = await fetch(`${window.API_BASE}/api/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!res.ok) { _refreshing = false; return false; }
    const d = await res.json();
    Auth.setTokens(d.access_token, d.refresh_token);
    _refreshQueue.forEach(r => r(true));
    _refreshQueue = [];
    _refreshing = false;
    return true;
  } catch {
    _refreshing = false;
    return false;
  }
}

async function _req(method, path, body, retry = false) {
  const { access } = Auth.getTokens();
  const headers = { 'Content-Type': 'application/json' };
  if (access) headers['Authorization'] = `Bearer ${access}`;

  const res = await fetch(`${window.API_BASE}${path}`, {
    method,
    headers,
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });

  if (res.status === 401 && !retry) {
    const before = Auth.getTokens().access;
    const ok = await _doRefresh();
    if (ok) return _req(method, path, body, true);
    // A concurrent request or another tab/page may have already refreshed the
    // token — if so, use the latest one instead of terminating the session.
    const after = Auth.getTokens().access;
    if (after && after !== before) return _req(method, path, body, true);
    Auth.logout();
    return null;
  }

  const text = await res.text();
  const data = text ? JSON.parse(text) : {};
  if (!res.ok) throw Object.assign(new Error(data.error || `HTTP ${res.status}`), data);
  return data;
}

const api = {
  get:    (p)    => _req('GET', p),
  post:   (p, b) => _req('POST', p, b),
  patch:  (p, b) => _req('PATCH', p, b),
  delete: (p)    => _req('DELETE', p),
};

/* ── UI helpers ─────────────────────────────────────────── */

function statusPill(status) {
  const m = {
    queued:               ['Queued',           '#8DD3CE', 'rgba(141,211,206,0.12)'],
    in_progress:          ['In Progress',      '#F4A258', 'rgba(244,162,88,0.12)'],
    completed:            ['Completed',        '#5BC26A', 'rgba(91,194,106,0.12)'],
    pending_human_review: ['Needs Review',     '#F4A258', 'rgba(244,162,88,0.15)'],
    approval_pending:     ['Approval Pending', '#F4A258', 'rgba(244,162,88,0.15)'],
    escalated:            ['Escalated',        '#E05252', 'rgba(224,82,82,0.15)'],
    failed:               ['Failed',           '#E05252', 'rgba(224,82,82,0.15)'],
    paused:               ['Paused',           '#8DD3CE', 'rgba(141,211,206,0.08)'],
    pending:              ['Pending',          '#8DD3CE', 'rgba(141,211,206,0.12)'],
    approved:             ['Approved',         '#5BC26A', 'rgba(91,194,106,0.12)'],
    denied:               ['Denied',           '#E05252', 'rgba(224,82,82,0.15)'],
    timed_out:            ['Timed Out',        '#E05252', 'rgba(224,82,82,0.12)'],
    active:               ['Active',           '#5BC26A', 'rgba(91,194,106,0.12)'],
    proposed:             ['Proposed',         '#F4A258', 'rgba(244,162,88,0.12)'],
    confirmed:            ['Confirmed',        '#5BC26A', 'rgba(91,194,106,0.12)'],
    suspended:            ['Suspended',        '#E05252', 'rgba(224,82,82,0.12)'],
    trial:                ['Trial',            '#F4A258', 'rgba(244,162,88,0.12)'],
    cancelled:            ['Cancelled',        '#8DD3CE', 'rgba(141,211,206,0.08)'],
  };
  const [label, color, bg] = m[status] || [status, '#FCF3E3', 'rgba(252,243,227,0.08)'];
  return `<span class="pill" style="color:${color};background:${bg};">${label}</span>`;
}

function priorityBadge(score, label) {
  const c = { 1: '#8DD3CE', 2: '#FCF3E3', 3: '#F4A258', 4: '#E05252' }[score] || '#FCF3E3';
  return `<span style="color:${c};font-family:'JetBrains Mono',monospace;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">${label || score || '—'}</span>`;
}

function levelLabel(n) {
  return ['', 'Employee', 'Senior', 'Manager', 'Executive'][n] || String(n);
}

function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function fmtDateShort(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

function fmtRelative(iso) {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60000)    return 'Just now';
  if (diff < 3600000)  return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return fmtDateShort(iso);
}

function showToast(msg, type = 'success') {
  const el = document.createElement('div');
  el.className = 'toast';
  el.style.background  = type === 'error' ? 'rgba(224,82,82,0.95)' : 'rgba(10,90,124,0.95)';
  el.style.border      = `1px solid ${type === 'error' ? '#E05252' : '#8DD3CE'}`;
  el.style.color       = '#FCF3E3';
  el.textContent       = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

function emptyRow(cols, msg = 'No records found') {
  return `<tr><td colspan="${cols}" style="padding:40px;text-align:center;color:#8DD3CE;font-size:13px;">${msg}</td></tr>`;
}

/* ── Sidebar init ───────────────────────────────────────── */

async function initSidebar() {
  let emp = Auth.getEmployee();

  if (!emp) {
    try {
      const user = Auth.getUser();
      const data = await api.get('/api/employees');
      const list = Array.isArray(data) ? data : (data.employees || []);
      emp = list.find(e => e.email === user?.email) || list[0];
      if (emp) Auth.setEmployee(emp);
    } catch {}
  }

  if (emp) {
    const initials = (emp.name || '?').split(' ').map(w => w[0]).join('').slice(0,2).toUpperCase();
    const avatar = document.getElementById('sidebar-avatar');
    const name   = document.getElementById('sidebar-name');
    const email  = document.getElementById('sidebar-email');
    const level  = document.getElementById('sidebar-level');

    if (avatar) avatar.textContent = initials;
    if (name)   name.textContent   = emp.name  || '—';
    if (email)  email.textContent  = emp.email || '—';
    if (level)  level.textContent  = levelLabel(emp.access_level);

    if (emp.access_level < 4) {
      const el = document.getElementById('nav-agent-configs');
      if (el) el.style.display = 'none';
    }
    if (emp.access_level < 3) {
      const el = document.getElementById('nav-employees');
      if (el) el.style.display = 'none';
    }
  }

  // Pending approvals badge
  try {
    const emp = Auth.getEmployee();
    if (emp && emp.access_level >= 3) {
      const data = await api.get('/api/approvals?status=pending');
      const count = (Array.isArray(data) ? data : (data.approvals || [])).length;
      if (count > 0) {
        const badge = document.getElementById('approvals-badge');
        if (badge) { badge.textContent = count; badge.style.display = 'inline'; }
      }
    }
  } catch {}
}
