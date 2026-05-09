const supabase               = require('../config/supabase.js');
const { AUDIT_EVENT_TYPES }  = require('../config/constants.js');

// GET /audit-logs?company_id=&task_id=&agent_name=&event_type=&from=&to=
const getAuditLogs = async (req, res) => {
  try {
    const { company_id, task_id, agent_name, event_type, from, to } = req.query;

    let query = supabase
      .from('audit_logs')
      .select('*')
      .order('timestamp', { ascending: false });

    if (company_id)  query = query.eq('company_id', company_id);
    if (task_id)     query = query.eq('task_id', task_id);
    if (agent_name)  query = query.eq('agent_name', agent_name);
    if (event_type)  query = query.eq('event_type', event_type);
    if (from)        query = query.gte('timestamp', from);
    if (to)          query = query.lte('timestamp', to);

    const { data, error } = await query;
    if (error) return res.status(400).json({ error: error.message });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// GET /audit-logs/:log_id
const getAuditLogById = async (req, res) => {
  try {
    const { log_id } = req.params;

    const { data, error } = await supabase
      .from('audit_logs')
      .select('*')
      .eq('log_id', log_id)
      .single();

    if (error) return res.status(404).json({ error: 'Audit log not found.' });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// POST /audit-logs
// Called by base_agent.py and outcome_emitter.py after every meaningful event.
// Body: { company_id, agent_name, event_type, task_id?, actor?, details? }
const createAuditLog = async (req, res) => {
  try {
    const {
      company_id,
      agent_name,
      event_type,
      task_id = null,
      actor   = 'system',
      details = {},
    } = req.body;

    if (!company_id || !agent_name || !event_type) {
      return res.status(400).json({
        error: 'company_id, agent_name, and event_type are required.',
      });
    }

    if (!AUDIT_EVENT_TYPES.includes(event_type)) {
      return res.status(400).json({
        error: `event_type must be one of: ${AUDIT_EVENT_TYPES.join(', ')}`,
      });
    }

    const { data, error } = await supabase
      .from('audit_logs')
      .insert([{
        company_id,
        agent_name,
        event_type,
        task_id,
        actor,
        details,
        timestamp: new Date().toISOString(),
      }])
      .select()
      .single();

    if (error) return res.status(400).json({ error: error.message });
    return res.status(201).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// GET /audit-logs/task/:task_id/timeline
// Full event timeline for a single task, oldest first — used for debugging agent runs.
const getTaskTimeline = async (req, res) => {
  try {
    const { task_id } = req.params;

    const { data, error } = await supabase
      .from('audit_logs')
      .select('*')
      .eq('task_id', task_id)
      .order('timestamp', { ascending: true });

    if (error) return res.status(400).json({ error: error.message });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

module.exports = { getAuditLogs, getAuditLogById, createAuditLog, getTaskTimeline };