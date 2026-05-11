const supabase              = require('../config/supabaseAdmin.js');
const { AUDIT_EVENT_TYPES } = require('../config/constants.js');

const getAll = async (filters = {}) => {
  const { company_id, task_id, agent_name, event_type, from, to } = filters;

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
  if (error) throw new Error(error.message);
  return data;
};

const getById = async (log_id) => {
  const { data, error } = await supabase
    .from('audit_logs')
    .select('*')
    .eq('log_id', log_id)
    .single();

  if (error) throw new Error('Audit log not found.');
  return data;
};

const create = async ({ company_id, agent_name, event_type, task_id = null, actor = 'system', details = {} }) => {
  if (!AUDIT_EVENT_TYPES.includes(event_type)) {
    throw new Error(`event_type must be one of: ${AUDIT_EVENT_TYPES.join(', ')}`);
  }

  const { data, error } = await supabase
    .from('audit_logs')
    .insert([{ company_id, agent_name, event_type, task_id, actor, details, timestamp: new Date().toISOString() }])
    .select()
    .single();

  if (error) throw new Error(error.message);
  return data;
};

// Full event timeline for a single task oldest-first — used for debugging agent runs.
const getTaskTimeline = async (task_id) => {
  const { data, error } = await supabase
    .from('audit_logs')
    .select('*')
    .eq('task_id', task_id)
    .order('timestamp', { ascending: true });

  if (error) throw new Error(error.message);
  return data;
};

module.exports = { getAll, getById, create, getTaskTimeline };