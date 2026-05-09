const supabase = require('../config/supabase.js');
const {
  TASK_STATUSES,
  DEPARTMENTS,
  PRIORITY_SCORES,
  PRIORITY_LABELS,
} = require('../config/constants.js');

const getAll = async (filters = {}) => {
  const { company_id, status, department, agent_name, is_autonomous, priority_score } = filters;

  let query = supabase
    .from('tasks')
    .select('*')
    .order('priority_score', { ascending: false })
    .order('created_at',     { ascending: true });

  if (company_id)              query = query.eq('company_id', company_id);
  if (status)                  query = query.eq('status', status);
  if (department)              query = query.eq('department', department);
  if (agent_name)              query = query.eq('agent_name', agent_name);
  if (priority_score)          query = query.eq('priority_score', parseInt(priority_score));
  if (is_autonomous !== undefined) query = query.eq('is_autonomous', is_autonomous === 'true' || is_autonomous === true);

  const { data, error } = await query;
  if (error) throw new Error(error.message);
  return data;
};

const getById = async (task_id) => {
  const { data, error } = await supabase
    .from('tasks')
    .select('*')
    .eq('task_id', task_id)
    .single();

  if (error) throw new Error('Task not found.');
  return data;
};

// Called by the Phase 1 pipeline after Priority Agent completes.
// envelope is the full Phase 1 JSON — we extract fields from it.
const create = async (envelope, company_id) => {
  if (!envelope.intake || !envelope.task || !envelope.priority) {
    throw new Error('Envelope must contain intake, task, and priority sections.');
  }
  if (!PRIORITY_SCORES.includes(envelope.priority.priority_score)) {
    throw new Error(`priority_score must be one of: ${PRIORITY_SCORES.join(', ')}`);
  }
  if (!PRIORITY_LABELS.includes(envelope.priority.priority_label)) {
    throw new Error(`priority_label must be one of: ${PRIORITY_LABELS.join(', ')}`);
  }
  if (!DEPARTMENTS.includes(envelope.task.department)) {
    throw new Error(`department must be one of: ${DEPARTMENTS.join(', ')}`);
  }

  const row = {
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
  };

  const { data, error } = await supabase
    .from('tasks')
    .insert([row])
    .select()
    .single();

  if (error) throw new Error(error.message);
  return data;
};

// Used by base_agent.py and Gru to update task status.
const updateStatus = async (task_id, { status, agent_name }) => {
  if (!TASK_STATUSES.includes(status)) {
    throw new Error(`Invalid status. Must be one of: ${TASK_STATUSES.join(', ')}`);
  }

  const updates = { status, updated_at: new Date().toISOString() };
  if (agent_name)           updates.agent_name   = agent_name;
  if (status === 'completed') updates.completed_at = new Date().toISOString();

  const { data, error } = await supabase
    .from('tasks')
    .update(updates)
    .eq('task_id', task_id)
    .select()
    .single();

  if (error) throw new Error(error.message);
  return data;
};

// Writes the execution section back to the stored envelope.
// Append-only — never overwrites intake, task, or priority.
const updateEnvelope = async (task_id, execution) => {
  const { data: current, error: fetchError } = await supabase
    .from('tasks')
    .select('envelope')
    .eq('task_id', task_id)
    .single();

  if (fetchError) throw new Error('Task not found.');

  const updatedEnvelope = { ...current.envelope, execution };

  const { data, error } = await supabase
    .from('tasks')
    .update({ envelope: updatedEnvelope, updated_at: new Date().toISOString() })
    .eq('task_id', task_id)
    .select()
    .single();

  if (error) throw new Error(error.message);
  return data;
};

// Appends a file reference to output_files array.
const addOutputFile = async (task_id, { file_path, file_type }) => {
  const { data: current, error: fetchError } = await supabase
    .from('tasks')
    .select('output_files')
    .eq('task_id', task_id)
    .single();

  if (fetchError) throw new Error('Task not found.');

  const newFile      = { file_path, file_type, created_at: new Date().toISOString() };
  const updatedFiles = [...(current.output_files || []), newFile];

  const { data, error } = await supabase
    .from('tasks')
    .update({ output_files: updatedFiles, updated_at: new Date().toISOString() })
    .eq('task_id', task_id)
    .select()
    .single();

  if (error) throw new Error(error.message);
  return data;
};

module.exports = { getAll, getById, create, updateStatus, updateEnvelope, addOutputFile };