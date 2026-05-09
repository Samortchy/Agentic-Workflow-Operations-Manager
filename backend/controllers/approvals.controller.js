const supabase = require('../config/supabase.js');
const {
  APPROVAL_TYPES,
  APPROVAL_STATUSES,
} = require('../config/constants.js');

// GET /approvals?company_id=&status=&task_id=&assigned_to=
const getApprovals = async (req, res) => {
  try {
    const { company_id, status, task_id, assigned_to } = req.query;

    let query = supabase
      .from('approval_requests')
      .select('*')
      .order('requested_at', { ascending: false });

    if (company_id)  query = query.eq('company_id', company_id);
    if (status)      query = query.eq('status', status);
    if (task_id)     query = query.eq('task_id', task_id);
    if (assigned_to) query = query.eq('assigned_to', assigned_to);

    const { data, error } = await query;
    if (error) return res.status(400).json({ error: error.message });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// GET /approvals/:approval_id
const getApprovalById = async (req, res) => {
  try {
    const { approval_id } = req.params;

    const { data, error } = await supabase
      .from('approval_requests')
      .select('*')
      .eq('approval_id', approval_id)
      .single();

    if (error) return res.status(404).json({ error: 'Approval request not found.' });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// POST /approvals
// Called by approval_gate.py when an agent pauses for confirmation.
// Body: { company_id, task_id, agent_name, command_preview, required_level,
//         approval_type, context?, assigned_to?, timeout_minutes? }
const createApproval = async (req, res) => {
  try {
    const {
      company_id,
      task_id,
      agent_name,
      command_preview,
      required_level,
      approval_type,
      context         = {},
      assigned_to     = null,
      timeout_minutes = 60,
    } = req.body;

    if (!company_id || !task_id || !agent_name || !command_preview || !required_level || !approval_type) {
      return res.status(400).json({
        error: 'company_id, task_id, agent_name, command_preview, required_level, and approval_type are required.',
      });
    }

    if (!APPROVAL_TYPES.includes(approval_type)) {
      return res.status(400).json({
        error: `approval_type must be one of: ${APPROVAL_TYPES.join(', ')}`,
      });
    }

    if (required_level < 1 || required_level > 4) {
      return res.status(400).json({ error: 'required_level must be between 1 and 4.' });
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

    if (error) return res.status(400).json({ error: error.message });
    return res.status(201).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// PATCH /approvals/:approval_id/resolve
// Called when a human approves or denies in the UI.
// Body: { status, resolved_by, resolution_note? }
// status must be 'approved' or 'denied'
const resolveApproval = async (req, res) => {
  try {
    const { approval_id }                          = req.params;
    const { status, resolved_by, resolution_note = '' } = req.body;

    if (!status || !resolved_by) {
      return res.status(400).json({ error: 'status and resolved_by are required.' });
    }

    if (!['approved', 'denied'].includes(status)) {
      return res.status(400).json({ error: "status must be 'approved' or 'denied'." });
    }

    // Check current state before resolving
    const { data: existing, error: fetchError } = await supabase
      .from('approval_requests')
      .select('status, timeout_at')
      .eq('approval_id', approval_id)
      .single();

    if (fetchError) return res.status(404).json({ error: 'Approval request not found.' });

    if (existing.status !== 'pending') {
      return res.status(409).json({
        error: `Cannot resolve: approval is already '${existing.status}'.`,
      });
    }

    // Auto-expire if past timeout
    if (new Date() > new Date(existing.timeout_at)) {
      await supabase
        .from('approval_requests')
        .update({ status: 'timed_out', resolved_at: new Date().toISOString() })
        .eq('approval_id', approval_id);

      return res.status(409).json({ error: 'Approval request has timed out.' });
    }

    const { data, error } = await supabase
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

    if (error) return res.status(400).json({ error: error.message });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// POST /approvals/timeout-sweep
// Called by a cron job to mark all expired pending approvals as timed_out.
const sweepTimedOutApprovals = async (req, res) => {
  try {
    const now = new Date().toISOString();

    const { data, error } = await supabase
      .from('approval_requests')
      .update({ status: 'timed_out', resolved_at: now })
      .eq('status', 'pending')
      .lt('timeout_at', now)
      .select();

    if (error) return res.status(400).json({ error: error.message });
    return res.status(200).json({ swept: data.length, records: data });
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

module.exports = {
  getApprovals,
  getApprovalById,
  createApproval,
  resolveApproval,
  sweepTimedOutApprovals,
};