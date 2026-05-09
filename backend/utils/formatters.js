const {
  TASK_STATUSES,
  PRIORITY_LABELS,
  AUDIT_EVENT_TYPES,
  OUTCOME_VERDICTS,
  AGENT_NAMES,
} = require('../config/constants.js');

// ── Envelope formatters ───────────────────────────────────────────────────────

// Formats a raw Phase 1 envelope into the flat fields the tasks table expects.
// Used by tasks.service.js before inserting into Supabase.
const formatTaskRow = (envelope, company_id) => ({
  task_id:         envelope.task.task_id,
  company_id,
  envelope_id:     envelope.envelope_id,
  status:          'queued',
  department:      envelope.task.department,
  priority_score:  envelope.priority.priority_score,
  priority_label:  envelope.priority.priority_label,
  is_autonomous:   envelope.task.isAutonomous,
  requester_email: envelope.task.requester_name,
  task_type:       envelope.task.task_type,
  stated_deadline: envelope.task.stated_deadline,
  envelope,
  agent_name:      null,
  output_files:    [],
});

// Merges an execution section into an existing envelope.
// Append-only — never overwrites intake, task, or priority.
const mergeExecutionIntoEnvelope = (existingEnvelope, execution) => ({
  ...existingEnvelope,
  execution,
});

// Merges a resume signal into an envelope after an approval is granted.
// The orchestrator reads resume: true to know it should pick this task back up.
const mergeResumePayload = (existingEnvelope, { approval_id, resolved_by, resolution_note, resolved_at }) => ({
  ...existingEnvelope,
  resume: true,
  resume_payload: {
    approval_id,
    decision:        'approved',
    resolved_by,
    resolution_note,
    resolved_at,
  },
});

// ── Response formatters ───────────────────────────────────────────────────────

// Standard success response shape.
// Use when you want a consistent { success, data } wrapper.
// Optional — controllers can also just return data directly.
const successResponse = (data, message = null) => ({
  success: true,
  ...(message && { message }),
  data,
});

// Standard error response shape.
const errorResponse = (message, details = null) => ({
  success: false,
  error: message,
  ...(details && { details }),
});

// ── Audit log formatters ──────────────────────────────────────────────────────

// Builds a valid audit log payload from an agent event.
// Validates event_type before returning so invalid types fail loudly.
const formatAuditLog = ({ company_id, task_id = null, agent_name, event_type, actor = 'system', details = {} }) => {
  if (!AUDIT_EVENT_TYPES.includes(event_type)) {
    throw new Error(`Invalid event_type: '${event_type}'. Must be one of: ${AUDIT_EVENT_TYPES.join(', ')}`);
  }
  if (!AGENT_NAMES.includes(agent_name) && agent_name !== 'system') {
    throw new Error(`Invalid agent_name: '${agent_name}'.`);
  }
  return { company_id, task_id, agent_name, event_type, actor, details, timestamp: new Date().toISOString() };
};

// ── Task status formatters ────────────────────────────────────────────────────

// Builds the update payload for a task status change.
// Sets completed_at automatically when status is 'completed'.
const formatStatusUpdate = (status, agent_name = null) => {
  if (!TASK_STATUSES.includes(status)) {
    throw new Error(`Invalid status: '${status}'. Must be one of: ${TASK_STATUSES.join(', ')}`);
  }
  const update = { status, updated_at: new Date().toISOString() };
  if (agent_name)           update.agent_name   = agent_name;
  if (status === 'completed') update.completed_at = new Date().toISOString();
  return update;
};

// ── Outcome signal formatters ─────────────────────────────────────────────────

// Builds a verdict summary from an array of outcome signal rows.
// Used by outcomeSignals.service.js — extracted here so it can be tested independently.
const formatVerdictSummary = (task_id, signals = []) => {
  const counts = { success: 0, failure: 0, unknown: 0, unresolved: 0 };
  for (const signal of signals) {
    if (signal.verdict === null) counts.unresolved++;
    else counts[signal.verdict]++;
  }
  const latest_verdict = (signals.find((s) => s.verdict !== null) || {}).verdict || null;
  return { task_id, total_signals: signals.length, latest_verdict, counts };
};

module.exports = {
  formatTaskRow,
  mergeExecutionIntoEnvelope,
  mergeResumePayload,
  successResponse,
  errorResponse,
  formatAuditLog,
  formatStatusUpdate,
  formatVerdictSummary,
};