/* mock-data.js — demo mode data, loaded on every page */

const MOCK = {
  tasks: [
    { task_id: 'a1b2c3d4-0001', task_type: 'Leave Request', status: 'completed', priority_score: 2, priority_label: 'medium', department: 'HR', agent_name: 'leave_checker', requester_email: 'sarah.chen@acme.com', stated_deadline: '2026-05-15', is_autonomous: true, created_at: new Date(Date.now() - 3600000*2).toISOString(), updated_at: new Date(Date.now() - 3600000).toISOString(), completed_at: new Date(Date.now() - 3600000).toISOString(), output_files: [], envelope: { task: { title: 'Annual Leave — Sarah Chen', description: 'Employee requesting 5 days annual leave from 20 May.', task_type: 'Leave Request', requester_name: 'Sarah Chen', stated_deadline: '2026-05-15', action_required: 'Check leave balance and approve.', success_criteria: 'Leave approved and calendar updated.' }, intake: { department: 'HR', isAutonomous: true, confidence: 0.94 }, priority: { priority_score: 2, priority_label: 'medium' } } },
    { task_id: 'a1b2c3d4-0002', task_type: 'Software Provisioning', status: 'approval_pending', priority_score: 3, priority_label: 'high', department: 'IT', agent_name: 'software_provisioner', requester_email: 'james.okafor@acme.com', stated_deadline: '2026-05-12', is_autonomous: false, created_at: new Date(Date.now() - 7200000).toISOString(), updated_at: new Date(Date.now() - 1800000).toISOString(), completed_at: null, output_files: [], envelope: { task: { title: 'Adobe Creative Cloud — James Okafor', description: 'New hire needs Adobe CC license for design work.', task_type: 'Software Provisioning', requester_name: 'James Okafor', stated_deadline: '2026-05-12', action_required: 'Provision license via IT admin portal.', success_criteria: 'User can log into Adobe CC.' }, intake: { department: 'IT', isAutonomous: false, confidence: 0.88 }, priority: { priority_score: 3, priority_label: 'high' } } },
    { task_id: 'a1b2c3d4-0003', task_type: 'Expense Reimbursement', status: 'in_progress', priority_score: 2, priority_label: 'medium', department: 'Finance', agent_name: 'expense_tracker', requester_email: 'priya.nair@acme.com', stated_deadline: '2026-05-20', is_autonomous: true, created_at: new Date(Date.now() - 10800000).toISOString(), updated_at: new Date(Date.now() - 900000).toISOString(), completed_at: null, output_files: [], envelope: { task: { title: 'Client Travel Expenses — Priya Nair', description: 'Reimbursement claim for £342 client travel.', task_type: 'Expense Reimbursement', requester_name: 'Priya Nair', stated_deadline: '2026-05-20', action_required: 'Validate receipts and process reimbursement.', success_criteria: 'Amount transferred within 5 business days.' }, intake: { department: 'Finance', isAutonomous: true, confidence: 0.91 }, priority: { priority_score: 2, priority_label: 'medium' } } },
    { task_id: 'a1b2c3d4-0004', task_type: 'Onboarding', status: 'queued', priority_score: 3, priority_label: 'high', department: 'HR', agent_name: 'onboarding_coordinator', requester_email: 'hr@acme.com', stated_deadline: '2026-05-13', is_autonomous: false, created_at: new Date(Date.now() - 14400000).toISOString(), updated_at: new Date(Date.now() - 14400000).toISOString(), completed_at: null, output_files: [], envelope: { task: { title: 'New Hire Onboarding — Marcus Webb', description: 'Full onboarding flow for new senior developer starting 13 May.', task_type: 'Onboarding', requester_name: 'HR Team', stated_deadline: '2026-05-13', action_required: 'Set up accounts, arrange equipment, schedule orientation.', success_criteria: 'All accounts active, equipment delivered before start date.' }, intake: { department: 'HR', isAutonomous: false, confidence: 0.86 }, priority: { priority_score: 3, priority_label: 'high' } } },
    { task_id: 'a1b2c3d4-0005', task_type: 'Report Generation', status: 'completed', priority_score: 1, priority_label: 'low', department: 'Finance', agent_name: 'report_generator', requester_email: 'cfo@acme.com', stated_deadline: '2026-05-11', is_autonomous: true, created_at: new Date(Date.now() - 86400000).toISOString(), updated_at: new Date(Date.now() - 82800000).toISOString(), completed_at: new Date(Date.now() - 82800000).toISOString(), output_files: [{ file_path: 'reports/q1-summary-2026.pdf', file_type: 'pdf' }], envelope: { task: { title: 'Q1 Expense Summary Report', description: 'Automated monthly expense report for CFO review.', task_type: 'Report Generation', requester_name: 'CFO Office', stated_deadline: '2026-05-11', action_required: 'Generate and deliver PDF report.', success_criteria: 'Report delivered to CFO inbox.' }, intake: { department: 'Finance', isAutonomous: true, confidence: 0.98 }, priority: { priority_score: 1, priority_label: 'low' } } },
    { task_id: 'a1b2c3d4-0006', task_type: 'Account Access', status: 'escalated', priority_score: 4, priority_label: 'critical', department: 'IT', agent_name: 'account_manager', requester_email: 'dan.frost@acme.com', stated_deadline: '2026-05-11', is_autonomous: false, created_at: new Date(Date.now() - 18000000).toISOString(), updated_at: new Date(Date.now() - 600000).toISOString(), completed_at: null, output_files: [], envelope: { task: { title: 'Locked Account — Dan Frost', description: 'Director account locked after failed MFA resets. Production access blocked.', task_type: 'Account Access', requester_name: 'Dan Frost', stated_deadline: '2026-05-11', action_required: 'Restore MFA and unlock account.', success_criteria: 'Director can log in and access production systems.' }, intake: { department: 'IT', isAutonomous: false, confidence: 0.72 }, priority: { priority_score: 4, priority_label: 'critical' } } },
    { task_id: 'a1b2c3d4-0007', task_type: 'Invoice Routing', status: 'pending_human_review', priority_score: 2, priority_label: 'medium', department: 'Finance', agent_name: 'invoice_router', requester_email: 'ap@acme.com', stated_deadline: '2026-05-18', is_autonomous: false, created_at: new Date(Date.now() - 21600000).toISOString(), updated_at: new Date(Date.now() - 3600000).toISOString(), completed_at: null, output_files: [], envelope: { task: { title: 'Vendor Invoice £12,400 — Cloudware Ltd', description: 'Invoice requires department head sign-off before payment.', task_type: 'Invoice Routing', requester_name: 'AP Team', stated_deadline: '2026-05-18', action_required: 'Route to correct department head for approval.', success_criteria: 'Invoice approved and queued for payment.' }, intake: { department: 'Finance', isAutonomous: false, confidence: 0.81 }, priority: { priority_score: 2, priority_label: 'medium' } } },
    { task_id: 'a1b2c3d4-0008', task_type: 'Meeting Scheduling', status: 'completed', priority_score: 1, priority_label: 'low', department: 'cross-dept', agent_name: 'meeting_scheduler', requester_email: 'ops@acme.com', stated_deadline: '2026-05-10', is_autonomous: true, created_at: new Date(Date.now() - 172800000).toISOString(), updated_at: new Date(Date.now() - 169200000).toISOString(), completed_at: new Date(Date.now() - 169200000).toISOString(), output_files: [], envelope: { task: { title: 'Q2 Planning Session — All Departments', description: 'Schedule cross-department Q2 planning meeting for all team leads.', task_type: 'Meeting Scheduling', requester_name: 'Operations', stated_deadline: '2026-05-10', action_required: 'Find common availability and send invites.', success_criteria: 'Meeting booked with all required attendees confirmed.' }, intake: { department: 'cross-dept', isAutonomous: true, confidence: 0.96 }, priority: { priority_score: 1, priority_label: 'low' } } },
  ],

  approvals: [
    { approval_id: 'apr-0001', task_id: 'a1b2c3d4-0002', agent_name: 'software_provisioner', command_preview: 'provision_license(user="james.okafor@acme.com", product="adobe_cc", tier="enterprise", seats=1)', approval_type: 'manager_sign_off', required_level: 3, status: 'pending', context: { cost_monthly: '£54.99', licence_pool: '2 remaining', requester_department: 'IT' }, requested_at: new Date(Date.now() - 1800000).toISOString(), timeout_at: new Date(Date.now() + 3600000 * 22).toISOString(), resolved_at: null, resolution_note: null },
    { approval_id: 'apr-0002', task_id: 'a1b2c3d4-0007', agent_name: 'invoice_router', command_preview: 'route_invoice(vendor="Cloudware Ltd", amount=12400, currency="GBP", to="head.finance@acme.com")', approval_type: 'single_confirm', required_level: 3, status: 'pending', context: { vendor: 'Cloudware Ltd', po_number: 'PO-2026-0041', due_date: '2026-05-18' }, requested_at: new Date(Date.now() - 3600000).toISOString(), timeout_at: new Date(Date.now() + 3600000 * 21).toISOString(), resolved_at: null, resolution_note: null },
    { approval_id: 'apr-0003', task_id: 'a1b2c3d4-0006', agent_name: 'account_manager', command_preview: 'reset_mfa(account="dan.frost@acme.com", method="authenticator_app", revoke_sessions=true)', approval_type: 'two_key', required_level: 4, status: 'pending', context: { risk_level: 'high', last_login: '2026-05-09T14:22:00Z', failed_attempts: 7 }, requested_at: new Date(Date.now() - 600000).toISOString(), timeout_at: new Date(Date.now() + 3600000 * 4).toISOString(), resolved_at: null, resolution_note: null },
    { approval_id: 'apr-0004', task_id: 'a1b2c3d4-0001', agent_name: 'leave_checker', command_preview: 'approve_leave(employee="sarah.chen@acme.com", days=5, start="2026-05-20", type="annual")', approval_type: 'single_confirm', required_level: 2, status: 'approved', context: { balance_remaining: 12, team_coverage: 'confirmed' }, requested_at: new Date(Date.now() - 7200000).toISOString(), timeout_at: new Date(Date.now() - 3600000).toISOString(), resolved_at: new Date(Date.now() - 4000000).toISOString(), resolved_by: 'alex@acme-corp.com', resolution_note: 'Approved. Team coverage confirmed.' },
  ],

  employees: [
    { employee_id: 'emp-001', name: 'Alex Rivera', email: 'alex@acme-corp.com', role: 'Operations Manager', department: 'cross-dept', access_level: 4, is_active: true, created_at: '2025-01-10T09:00:00Z' },
    { employee_id: 'emp-002', name: 'Sarah Chen', email: 'sarah.chen@acme.com', role: 'HR Business Partner', department: 'HR', access_level: 3, is_active: true, created_at: '2025-02-14T09:00:00Z' },
    { employee_id: 'emp-003', name: 'James Okafor', email: 'james.okafor@acme.com', role: 'Senior Designer', department: 'IT', access_level: 1, is_active: true, created_at: '2025-03-01T09:00:00Z' },
    { employee_id: 'emp-004', name: 'Priya Nair', email: 'priya.nair@acme.com', role: 'Finance Analyst', department: 'Finance', access_level: 2, is_active: true, created_at: '2025-01-20T09:00:00Z' },
    { employee_id: 'emp-005', name: 'Dan Frost', email: 'dan.frost@acme.com', role: 'Engineering Director', department: 'IT', access_level: 4, is_active: true, created_at: '2024-11-01T09:00:00Z' },
    { employee_id: 'emp-006', name: 'Yuki Tanaka', email: 'yuki.tanaka@acme.com', role: 'IT Support Lead', department: 'IT', access_level: 3, is_active: true, created_at: '2025-04-05T09:00:00Z' },
    { employee_id: 'emp-007', name: 'Marcus Webb', email: 'marcus.webb@acme.com', role: 'Senior Developer', department: 'IT', access_level: 1, is_active: false, created_at: '2026-05-11T09:00:00Z' },
  ],

  auditLogs: [
    { log_id: 'log-001', task_id: 'a1b2c3d4-0002', agent_name: 'software_provisioner', event_type: 'agent_started', actor: 'system', details: { step: 'lookup_license_pool' }, timestamp: new Date(Date.now() - 1900000).toISOString() },
    { log_id: 'log-002', task_id: 'a1b2c3d4-0002', agent_name: 'software_provisioner', event_type: 'approval_requested', actor: 'system', details: { approval_type: 'manager_sign_off', required_level: 3 }, timestamp: new Date(Date.now() - 1800000).toISOString() },
    { log_id: 'log-003', task_id: 'a1b2c3d4-0006', agent_name: 'account_manager', event_type: 'escalated', actor: 'system', details: { reason: 'High-risk MFA reset on director account', failed_attempts: 7 }, timestamp: new Date(Date.now() - 650000).toISOString() },
    { log_id: 'log-004', task_id: 'a1b2c3d4-0001', agent_name: 'leave_checker', event_type: 'agent_completed', actor: 'system', details: { outcome: 'leave_approved', days_approved: 5 }, timestamp: new Date(Date.now() - 3600000).toISOString() },
    { log_id: 'log-005', task_id: 'a1b2c3d4-0003', agent_name: 'expense_tracker', event_type: 'agent_started', actor: 'system', details: { step: 'validate_receipts' }, timestamp: new Date(Date.now() - 950000).toISOString() },
    { log_id: 'log-006', task_id: 'a1b2c3d4-0005', agent_name: 'report_generator', event_type: 'agent_completed', actor: 'system', details: { file: 'reports/q1-summary-2026.pdf', pages: 14 }, timestamp: new Date(Date.now() - 82800000).toISOString() },
    { log_id: 'log-007', task_id: 'a1b2c3d4-0007', agent_name: 'invoice_router', event_type: 'approval_requested', actor: 'system', details: { amount: 12400, vendor: 'Cloudware Ltd' }, timestamp: new Date(Date.now() - 3600000).toISOString() },
    { log_id: 'log-008', task_id: 'a1b2c3d4-0004', agent_name: 'onboarding_coordinator', event_type: 'task_queued', actor: 'system', details: { start_date: '2026-05-13' }, timestamp: new Date(Date.now() - 14400000).toISOString() },
  ],

  agentConfigs: [
    { config_id: 'cfg-001', agent_name: 'leave_checker', version: '1.2.0', is_active: true, created_at: '2026-01-15T10:00:00Z', updated_at: '2026-04-01T10:00:00Z', config: { agent_name: 'leave_checker', agent_version: '1.2.0', department: 'HR', risk_tier: 'low', approval: { mode: 'single_confirm_if_low_confidence' }, steps: [{ name: 'check_balance', type: 'extractor' }, { name: 'validate_coverage', type: 'processor' }, { name: 'approve_or_escalate', type: 'dispatcher' }], on_failure: 'escalate', outcome_signal: 'leave_decision' } },
    { config_id: 'cfg-002', agent_name: 'software_provisioner', version: '2.0.1', is_active: true, created_at: '2026-02-01T10:00:00Z', updated_at: '2026-04-15T10:00:00Z', config: { agent_name: 'software_provisioner', agent_version: '2.0.1', department: 'IT', risk_tier: 'medium', approval: { mode: 'manager_sign_off' }, steps: [{ name: 'lookup_license_pool', type: 'extractor' }, { name: 'calculate_cost', type: 'processor' }, { name: 'provision_license', type: 'agent_call' }], on_failure: 'notify_it_admin', outcome_signal: 'license_provisioned' } },
    { config_id: 'cfg-003', agent_name: 'expense_tracker', version: '1.5.0', is_active: true, created_at: '2026-01-20T10:00:00Z', updated_at: '2026-03-10T10:00:00Z', config: { agent_name: 'expense_tracker', agent_version: '1.5.0', department: 'Finance', risk_tier: 'low', approval: { mode: 'none' }, steps: [{ name: 'validate_receipts', type: 'extractor' }, { name: 'categorise', type: 'processor' }, { name: 'submit_reimbursement', type: 'dispatcher' }], on_failure: 'return_to_employee', outcome_signal: 'reimbursement_status' } },
    { config_id: 'cfg-004', agent_name: 'report_generator', version: '3.1.0', is_active: true, created_at: '2025-12-01T10:00:00Z', updated_at: '2026-05-01T10:00:00Z', config: { agent_name: 'report_generator', agent_version: '3.1.0', department: 'Finance', risk_tier: 'low', approval: { mode: 'none' }, steps: [{ name: 'aggregate_data', type: 'extractor' }, { name: 'render_pdf', type: 'custom' }, { name: 'deliver_report', type: 'dispatcher' }], on_failure: 'retry_once', outcome_signal: 'report_delivered' } },
    { config_id: 'cfg-005', agent_name: 'account_manager', version: '1.0.3', is_active: true, created_at: '2026-03-01T10:00:00Z', updated_at: '2026-04-20T10:00:00Z', config: { agent_name: 'account_manager', agent_version: '1.0.3', department: 'IT', risk_tier: 'high', approval: { mode: 'manager_sign_off' }, steps: [{ name: 'verify_identity', type: 'extractor' }, { name: 'assess_risk', type: 'processor' }, { name: 'execute_action', type: 'agent_call' }], on_failure: 'escalate_to_security', outcome_signal: 'account_status' } },
  ],

  timeline: [
    { log_id: 'tl-001', event_type: 'task_queued',      agent_name: 'orchestrator',          actor: 'system', details: { priority: 'high' },                    timestamp: new Date(Date.now() - 7300000).toISOString() },
    { log_id: 'tl-002', event_type: 'task_picked_up',   agent_name: 'software_provisioner',  actor: 'system', details: {},                                      timestamp: new Date(Date.now() - 1950000).toISOString() },
    { log_id: 'tl-003', event_type: 'agent_started',    agent_name: 'software_provisioner',  actor: 'system', details: { step: 'lookup_license_pool' },         timestamp: new Date(Date.now() - 1900000).toISOString() },
    { log_id: 'tl-004', event_type: 'approval_requested', agent_name: 'software_provisioner', actor: 'system', details: { type: 'manager_sign_off', level: 3 }, timestamp: new Date(Date.now() - 1800000).toISOString() },
  ],

  signals: [
    { signal_id: 'sig-001', task_id: 'a1b2c3d4-0001', signal_type: 'leave_decision', verdict: 'success', value: { approved: true, days: 5 }, timestamp: new Date(Date.now() - 3600000).toISOString() },
    { signal_id: 'sig-002', task_id: 'a1b2c3d4-0001', signal_type: 'calendar_updated', verdict: 'success', value: { calendar: 'outlook', event_id: 'evt-991' }, timestamp: new Date(Date.now() - 3500000).toISOString() },
  ],
};

/* ── Intercept api calls in demo mode ───────────────────── */

const _demoMode = localStorage.getItem('awom_demo') === 'true';

if (_demoMode) {
  const _realReq = window._req;

  window._req = async function(method, path, body, retry) {
    // Strip query params for matching
    const clean = path.split('?')[0];

    if (method === 'GET') {
      if (clean === '/api/tasks')                        return [...MOCK.tasks];
      if (clean.startsWith('/api/tasks/'))               { const id = clean.split('/')[3]; return MOCK.tasks.find(t => t.task_id === id || id?.startsWith(t.task_id.slice(0,8))) || MOCK.tasks[0]; }
      if (clean === '/api/approvals')                    return [...MOCK.approvals].filter(a => !path.includes('status=pending') || a.status === 'pending');
      if (clean === '/api/employees')                    return [...MOCK.employees];
      if (clean === '/api/audit-logs')                   return [...MOCK.auditLogs];
      if (clean.startsWith('/api/audit-logs/task/'))     return [...MOCK.timeline];
      if (clean === '/api/agent-configs')                return [...MOCK.agentConfigs];
      if (clean.startsWith('/api/outcome-signals/task/') && clean.endsWith('/summary')) {
        return { task_id: 'a1b2c3d4-0001', total_signals: 2, latest_verdict: 'success', counts: { success: 2, failure: 0, unknown: 0, unresolved: 0 } };
      }
      if (clean === '/api/outcome-signals')              return [...MOCK.signals];
    }

    if (method === 'PATCH' && clean.includes('/resolve')) {
      return { message: 'Demo mode — no changes saved' };
    }
    if (method === 'PATCH' && clean.includes('/deactivate')) {
      return { message: 'Demo mode — no changes saved' };
    }
    if (method === 'POST' && clean === '/api/employees') {
      return { message: 'Demo mode — employee not actually saved' };
    }

    return {};
  };

  // Also patch the exported api object
  const _apiOverride = {
    get:    (p)    => window._req('GET', p),
    post:   (p, b) => window._req('POST', p, b),
    patch:  (p, b) => window._req('PATCH', p, b),
    delete: (p)    => window._req('DELETE', p),
  };
  Object.assign(api, _apiOverride);

  // Banner
  document.addEventListener('DOMContentLoaded', () => {
    const banner = document.createElement('div');
    banner.innerHTML = `
      <span style="font-family:'JetBrains Mono',monospace;font-size:11px;letter-spacing:0.04em;">PREVIEW MODE — mock data, no backend</span>
      <button onclick="exitPreview()" style="margin-left:16px;font-size:11px;color:#F4A258;background:none;border:none;cursor:pointer;font-family:'JetBrains Mono',monospace;padding:0;">Exit preview</button>
    `;
    banner.style.cssText = 'position:fixed;bottom:0;left:0;right:0;background:#013D5A;border-top:1px solid #0A5A7C;padding:8px 24px;display:flex;align-items:center;justify-content:center;color:#8DD3CE;z-index:50;';
    document.body.appendChild(banner);
  });
}

function exitPreview() {
  localStorage.removeItem('awom_demo');
  Auth.clear();
  window.location.href = '/login';
}
