let _meetings = [];

document.addEventListener('DOMContentLoaded', async () => {
  if (!Auth.requireAuth()) return;
  await initSidebar();
  await loadMeetings();
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeMeeting(); });
});

async function loadMeetings() {
  const wrap   = document.getElementById('timeline');
  const status = document.getElementById('filter-status').value;
  wrap.innerHTML = msg('Loading…');
  try {
    const params = status ? `?status=${encodeURIComponent(status)}` : '';
    const data = await api.get(`/api/meetings${params}`);
    _meetings = Array.isArray(data) ? data : (data?.meetings || []);
    renderTimeline(_meetings);
  } catch (e) {
    wrap.innerHTML = msg('Failed to load meetings');
  }
}

/* ── rendering ──────────────────────────────────────────── */

function meetingWhen(m) {
  return m.confirmed_slot
    || (Array.isArray(m.proposed_slots) && m.proposed_slots[0] && (m.proposed_slots[0].slot_start || m.proposed_slots[0]))
    || null;
}

function renderTimeline(list) {
  const wrap = document.getElementById('timeline');
  if (!list.length) { wrap.innerHTML = msg('No meetings scheduled yet'); return; }

  const groups = {};
  for (const m of list) {
    const when = meetingWhen(m);
    const key  = when ? new Date(when).toISOString().slice(0, 10) : 'unscheduled';
    (groups[key] = groups[key] || []).push(m);
  }
  const keys = Object.keys(groups).sort((a, b) =>
    a === 'unscheduled' ? 1 : b === 'unscheduled' ? -1 : a.localeCompare(b));

  let html = '';
  for (const k of keys) {
    const items = groups[k].sort((a, b) =>
      String(meetingWhen(a) || '').localeCompare(String(meetingWhen(b) || '')));
    html += dayHeader(k);
    html += `<div style="display:flex;flex-direction:column;gap:8px;margin:0 0 22px 0;">${items.map(card).join('')}</div>`;
  }
  wrap.innerHTML = html;
}

function dayHeader(key) {
  const label = key === 'unscheduled'
    ? 'Unscheduled'
    : new Date(key + 'T00:00:00').toLocaleDateString('en-GB',
        { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' });
  return `<div style="display:flex;align-items:center;gap:12px;margin:6px 0 12px;">
      <span style="font-family:'JetBrains Mono',monospace;font-size:12px;color:#F4A258;text-transform:uppercase;letter-spacing:0.06em;">${label}</span>
      <span style="flex:1;height:1px;background:#0A5A7C;"></span>
    </div>`;
}

function card(m) {
  const when = meetingWhen(m);
  const time = when ? new Date(when).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : '—';
  const cancelled = m.status === 'cancelled';
  const parts = Array.isArray(m.participants) ? m.participants.length : 0;
  const dim = cancelled ? 'opacity:0.55;' : '';
  const strike = cancelled ? 'text-decoration:line-through;' : '';
  return `<div onclick="openMeeting('${m.meeting_id}')" class="tbl-row"
       style="display:flex;align-items:center;gap:16px;padding:14px 16px;border:1px solid #0A5A7C;border-radius:8px;cursor:pointer;background:#012A3D;${dim}">
      <div style="width:56px;flex-shrink:0;font-family:'JetBrains Mono',monospace;font-size:14px;color:#8DD3CE;">${time}</div>
      <div style="flex:1;min-width:0;">
        <div style="font-size:14px;font-weight:500;color:#FCF3E3;${strike}overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(m.title || 'Untitled meeting')}</div>
        <div style="font-size:12px;color:#8DD3CE;margin-top:2px;">${parts} participant${parts === 1 ? '' : 's'}</div>
      </div>
      ${statusPill(m.status || 'proposed')}
    </div>`;
}

/* ── detail modal ───────────────────────────────────────── */

function canManage(m) {
  const emp = Auth.getEmployee();
  if (!emp) return false;
  return emp.access_level >= 3 || (!!emp.email && emp.email === m.organizer_email);
}

function openMeeting(id) {
  const m = _meetings.find(x => x.meeting_id === id);
  if (!m) return;
  const when  = meetingWhen(m);
  const parts = Array.isArray(m.participants) ? m.participants : [];
  const manage = canManage(m) && m.status !== 'cancelled';

  const partsHtml = parts.length
    ? parts.map(p => `<li style="padding:4px 0;font-size:13px;color:#FCF3E3;">${escapeHtml(p)}</li>`).join('')
    : '<li style="font-size:13px;color:#8DD3CE;">No participants listed</li>';

  const actionsHtml = manage ? `
      <div style="border-top:1px solid #0A5A7C;margin-top:20px;padding-top:18px;">
        <label style="display:block;font-size:12px;color:#8DD3CE;margin-bottom:6px;">Reschedule to</label>
        <div style="display:flex;gap:10px;">
          <input type="datetime-local" id="reschedule-input" class="input-field" style="flex:1;" value="${toLocalInput(when)}" />
          <button onclick="submitReschedule('${m.meeting_id}')" class="btn-primary" id="reschedule-btn">Reschedule</button>
        </div>
        <button onclick="cancelMeeting('${m.meeting_id}')" class="btn-ghost" id="cancel-btn"
          style="margin-top:14px;color:#E05252;border-color:#E05252;">Cancel meeting</button>
      </div>` : '';

  document.getElementById('meeting-modal-box').innerHTML = `
    <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:16px;">
      <h3 style="font-family:'DM Serif Display',serif;font-size:18px;color:#FCF3E3;margin:0;">${escapeHtml(m.title || 'Untitled meeting')}</h3>
      <button onclick="closeMeeting()" style="background:none;border:none;cursor:pointer;color:#8DD3CE;font-size:20px;line-height:1;padding:0;">×</button>
    </div>
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;">
      ${statusPill(m.status || 'proposed')}
      <span style="font-size:13px;color:#FCF3E3;">${when ? fmtDate(when) : 'Time TBD'}</span>
    </div>
    <div style="font-size:12px;color:#8DD3CE;margin-bottom:4px;">Organizer</div>
    <div style="font-size:13px;color:#FCF3E3;margin-bottom:16px;">${escapeHtml(m.organizer_email || '—')}</div>
    <div style="font-size:12px;color:#8DD3CE;margin-bottom:4px;">Participants (${parts.length})</div>
    <ul style="list-style:none;margin:0;padding:0;max-height:180px;overflow-y:auto;">${partsHtml}</ul>
    ${actionsHtml}`;

  document.getElementById('meeting-modal').style.display = 'flex';
}

function closeMeeting() {
  document.getElementById('meeting-modal').style.display = 'none';
}

async function cancelMeeting(id) {
  if (!confirm('Cancel this meeting? Participants will need to be notified separately.')) return;
  try {
    await api.patch(`/api/meetings/${id}`, { status: 'cancelled' });
    showToast('Meeting cancelled');
    closeMeeting();
    await loadMeetings();
  } catch (e) {
    showToast(e.error || e.message || 'Failed to cancel', 'error');
  }
}

async function submitReschedule(id) {
  const val = document.getElementById('reschedule-input').value;
  if (!val) { showToast('Pick a new date/time first', 'error'); return; }
  const btn = document.getElementById('reschedule-btn');
  btn.disabled = true; btn.textContent = 'Saving…';
  try {
    await api.patch(`/api/meetings/${id}`, { confirmed_slot: new Date(val).toISOString(), status: 'confirmed' });
    showToast('Meeting rescheduled');
    closeMeeting();
    await loadMeetings();
  } catch (e) {
    showToast(e.error || e.message || 'Failed to reschedule', 'error');
    btn.disabled = false; btn.textContent = 'Reschedule';
  }
}

/* ── helpers ────────────────────────────────────────────── */

function toLocalInput(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return '';
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

function msg(text) {
  return `<div style="padding:40px;text-align:center;color:#8DD3CE;font-size:13px;">${text}</div>`;
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
