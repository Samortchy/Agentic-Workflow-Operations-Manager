// Mirrors your database CHECK constraints exactly —
// single source of truth for the backend and orchestrator

const DEPARTMENTS = ['IT', 'HR', 'Finance', 'cross-dept', 'Other'];

const TASK_STATUSES = [
    'queued',
    'in_progress',
    'completed',
    'paused',
    'pending_human_review',
    'approval_pending',
    'escalated',
    'failed'
];

const PRIORITY_SCORES = [1, 2, 3, 4];

const PRIORITY_LABELS = ['low', 'medium', 'high', 'critical'];

const ACCESS_LEVELS = {
    EMPLOYEE:   1,
    SENIOR:     2,
    MANAGER:    3,
    EXECUTIVE:  4
};

const APPROVAL_TYPES = ['two_key', 'single_confirm', 'manager_sign_off'];

const APPROVAL_STATUSES = ['pending', 'approved', 'denied', 'timed_out'];

const SUBSCRIPTION_STATUSES = ['active', 'suspended', 'trial', 'cancelled'];

const AUDIT_EVENT_TYPES = [
    'agent_started',
    'agent_completed',
    'agent_failed',
    'approval_requested',
    'approval_granted',
    'approval_denied',
    'approval_timed_out',
    'step_failed',
    'escalated',
    'task_queued',
    'task_picked_up',
    'outcome_signal_received',
    'orchestrator_dispatched',
    'task_resumed'
];

const OUTCOME_VERDICTS = ['success', 'failure', 'unknown'];

const AGENT_NAMES = [
    'escalation_router',
    'document_summarizer',
    'report_generator',
    'leave_checker',
    'email_agent',
    'powerpoint_agent',
    'meeting_scheduler',
    'expense_tracker',
    'onboarding_coordinator',
    'account_manager',
    'software_provisioner',
    'invoice_router'
];

const STORAGE_BUCKET = 'task-outputs';

const AGENT_API_KEY_HEADER = 'x-agent-api-key';

module.exports = {
    DEPARTMENTS,
    TASK_STATUSES,
    PRIORITY_SCORES,
    PRIORITY_LABELS,
    ACCESS_LEVELS,
    APPROVAL_TYPES,
    APPROVAL_STATUSES,
    SUBSCRIPTION_STATUSES,
    AUDIT_EVENT_TYPES,
    OUTCOME_VERDICTS,
    AGENT_NAMES,
    STORAGE_BUCKET,
    AGENT_API_KEY_HEADER
};