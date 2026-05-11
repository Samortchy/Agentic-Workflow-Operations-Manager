const supabase      = require('../config/supabaseAdmin.js');
const supabaseAdmin = require('../config/supabaseAdmin.js');
const { APPROVAL_TYPES } = require('../config/constants.js');

const getAll = async (filters = {}) => {
  const { company_id, status, task_id, assigned_to } = filters;

  let query = supabase
    .from('approval_requests')
    .select('*')
    .order('requested_at', { ascending: false });

  if (company_id)  query = query.eq('company_id', company_id);
  if (status)      query = query.eq('status', status);
  if (task_id)     query = query.eq('task_id', task_id);
  if (assigned_to) query = query.eq('assigned_to', assigned_to);

  const { data, error } = await query;
  if (error) throw new Error(error.message);
  return data;
};

const getById = async (approval_id) => {
  const { data, error } = await supabase
    .from('approval_requests')
    .select('*')
    .eq('approval_id', approval_id)
    .single();

  if (error) throw new Error('Approval request not found.');
  return data;
};

// Creates an approval request and writes it to Supabase.
// Supabase Realtime will push the insert to the desktop app automatically.
const create = async ({
  company_id,
  task_id,
  agent_name,
  command_preview,
  required_level,
  approval_type,
  context         = {},
  assigned_to     = null,
  timeout_minutes = 60,
}) => {
  if (!APPROVAL_TYPES.includes(approval_type)) {
    throw new Error(`approval_type must be one of: ${APPROVAL_TYPES.join(', ')}`);
  }
  if (required_level < 1 || required_level > 4) {
    throw new Error('required_level must be between 1 and 4.');
  }

  const now     = new Date();
  const timeout = new Date(now.getTime() + timeout_minutes * 60 * 1000);

  const { data, error } = await supabase
    .from('approval_requests')
    .insert([{
      company_id,
      task_id,
      agent_name,
      command_preview,
      required_level,
      approval_type,
      context,
      assigned_to,
      status:       'pending',
      requested_at: now.toISOString(),
      timeout_at:   timeout.toISOString(),
    }])
    .select()
    .single();

  if (error) throw new Error(error.message);

  // Realtime pushes this insert to the desktop app — no extra work needed here.
  // The desktop app subscribes to approval_requests where company_id = their company.

  return data;
};

// Resolves an approval as 'approved' or 'denied'.
// On approved: flips task back to 'queued' so the orchestrator picks it up.
// On denied:   flips task to 'failed' and logs to audit_logs.
const _isUuid = (v) => typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);

const resolve = async (approval_id, { status, resolved_by, resolution_note = '' }) => {
  // resolved_by must be a UUID (FK to employees) — coerce anything else to null
  if (!_isUuid(resolved_by)) resolved_by = null;
  if (!['approved', 'denied'].includes(status)) {
    throw new Error("status must be 'approved' or 'denied'.");
  }

  // Fetch current approval state
  const { data: existing, error: fetchError } = await supabase
    .from('approval_requests')
    .select('status, timeout_at, task_id, agent_name, company_id')
    .eq('approval_id', approval_id)
    .single();

  if (fetchError) throw new Error('Approval request not found.');
  if (existing.status !== 'pending') {
    throw new Error(`Cannot resolve: approval is already '${existing.status}'.`);
  }

  // Auto-expire if past timeout
  if (new Date() > new Date(existing.timeout_at)) {
    await supabase
      .from('approval_requests')
      .update({ status: 'timed_out', resolved_at: new Date().toISOString() })
      .eq('approval_id', approval_id);

    throw new Error('Approval request has timed out.');
  }

  // Write the resolution
  const { data: resolved, error: resolveError } = await supabase
    .from('approval_requests')
    .update({
      status,
      resolved_by,
      resolution_note,
      resolved_at: new Date().toISOString(),
    })
    .eq('approval_id', approval_id)
    .select()
    .single();

  if (resolveError) throw new Error(resolveError.message);

  const now = new Date().toISOString();

  if (status === 'approved') {
    // Flip task back to queued + write resume signal into envelope
    // so the orchestrator knows to resume from where it paused
    const { data: task } = await supabase
      .from('tasks')
      .select('envelope')
      .eq('task_id', existing.task_id)
      .single();

    const updatedEnvelope = {
      ...task.envelope,
      resume: true,
      resume_payload: {
        approval_id,
        decision:        'approved',
        resolved_by,
        resolution_note,
        resolved_at:     now,
      },
    };

    await supabase
      .from('tasks')
      .update({
        status:           'queued',
        envelope:         updatedEnvelope,
        updated_at:       now,
      })
      .eq('task_id', existing.task_id);

    await _logAudit({
      company_id:  existing.company_id,
      task_id:     existing.task_id,
      agent_name:  existing.agent_name,
      event_type:  'approval_granted',
      actor:       resolved_by,
      details:     { approval_id, resolution_note },
    });
  }

  if (status === 'denied') {
    // Flip task to failed
    await supabase
      .from('tasks')
      .update({ status: 'failed', updated_at: now })
      .eq('task_id', existing.task_id);

    await _logAudit({
      company_id:  existing.company_id,
      task_id:     existing.task_id,
      agent_name:  existing.agent_name,
      event_type:  'approval_denied',
      actor:       resolved_by,
      details:     { approval_id, resolution_note },
    });
  }

  return resolved;
};

// Sweeps all pending approvals where timeout_at has passed.
// Flips them to timed_out and logs each to audit_logs.
// Called by a cron job — no HTTP context needed.
const sweepTimedOut = async () => {
  const now = new Date().toISOString();

  const { data: expired, error } = await supabase
    .from('approval_requests')
    .update({ status: 'timed_out', resolved_at: now })
    .eq('status', 'pending')
    .lt('timeout_at', now)
    .select();

  if (error) throw new Error(error.message);

  // Log each timed-out approval to audit_logs
  for (const approval of (expired || [])) {
    await _logAudit({
      company_id: approval.company_id,
      task_id:    approval.task_id,
      agent_name: approval.agent_name,
      event_type: 'approval_timed_out',
      actor:      'system',
      details:    { approval_id: approval.approval_id },
    });
  }

  return { swept: expired.length, records: expired };
};

// Internal helper — writes to audit_logs without importing auditLogs.service
// to avoid circular dependencies.
const _logAudit = async ({ company_id, task_id, agent_name, event_type, actor = 'system', details = {} }) => {
  await supabaseAdmin
    .from('audit_logs')
    .insert([{ company_id, task_id, agent_name, event_type, actor, details, timestamp: new Date().toISOString() }]);
};

module.exports = { getAll, getById, create, resolve, sweepTimedOut };