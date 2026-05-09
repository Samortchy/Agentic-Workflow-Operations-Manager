const supabase = require('../config/supabase.js');
const {
  TASK_STATUSES,
  DEPARTMENTS,
  PRIORITY_SCORES,
  PRIORITY_LABELS,
} = require('../config/constants.js');

// GET /tasks?company_id=&status=&department=&agent_name=&is_autonomous=&priority_score=
const getTasks = async (req, res) => {
  try {
    const { company_id, status, department, agent_name, is_autonomous, priority_score } = req.query;

    let query = supabase
      .from('tasks')
      .select('*')
      .order('priority_score', { ascending: false })  // highest priority first
      .order('created_at',     { ascending: true });   // then FIFO within same priority

    if (company_id)              query = query.eq('company_id', company_id);
    if (status)                  query = query.eq('status', status);
    if (department)              query = query.eq('department', department);
    if (agent_name)              query = query.eq('agent_name', agent_name);
    if (priority_score)          query = query.eq('priority_score', parseInt(priority_score));
    if (is_autonomous !== undefined) query = query.eq('is_autonomous', is_autonomous === 'true');

    const { data, error } = await query;
    if (error) return res.status(400).json({ error: error.message });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// GET /tasks/:task_id
const getTaskById = async (req, res) => {
  try {
    const { task_id } = req.params;

    const { data, error } = await supabase
      .from('tasks')
      .select('*')
      .eq('task_id', task_id)
      .single();

    if (error) return res.status(404).json({ error: 'Task not found.' });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// POST /tasks
// Called by the Phase 1 pipeline after Priority Agent completes.
// Body: full Phase 1 envelope JSON + company_id as query param.
const createTask = async (req, res) => {
  try {
    const envelope   = req.body;
    const { company_id } = req.query;

    if (!company_id) {
      return res.status(400).json({ error: 'company_id query param is required.' });
    }

    // Validate all three Phase 1 sections are present (spec Section 3.1)
    if (!envelope.intake || !envelope.task || !envelope.priority) {
      return res.status(400).json({
        error: 'Envelope must contain intake, task, and priority sections.',
      });
    }

    // Validate priority values against constants
    if (!PRIORITY_SCORES.includes(envelope.priority.priority_score)) {
      return res.status(400).json({
        error: `priority_score must be one of: ${PRIORITY_SCORES.join(', ')}`,
      });
    }

    if (!PRIORITY_LABELS.includes(envelope.priority.priority_label)) {
      return res.status(400).json({
        error: `priority_label must be one of: ${PRIORITY_LABELS.join(', ')}`,
      });
    }

    if (!DEPARTMENTS.includes(envelope.task.department)) {
      return res.status(400).json({
        error: `department must be one of: ${DEPARTMENTS.join(', ')}`,
      });
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
      envelope,         // full envelope stored as jsonb
      agent_name:      null,
      output_files:    [],
    };

    const { data, error } = await supabase
      .from('tasks')
      .insert([row])
      .select()
      .single();

    if (error) return res.status(400).json({ error: error.message });
    return res.status(201).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// PATCH /tasks/:task_id/status
// Used by base_agent.py and Gru to update task status.
// Body: { status, agent_name? }
const updateTaskStatus = async (req, res) => {
  try {
    const { task_id }            = req.params;
    const { status, agent_name } = req.body;

    if (!status) return res.status(400).json({ error: 'status is required.' });

    if (!TASK_STATUSES.includes(status)) {
      return res.status(400).json({
        error: `Invalid status. Must be one of: ${TASK_STATUSES.join(', ')}`,
      });
    }

    const updates = { status, updated_at: new Date().toISOString() };

    if (agent_name)           updates.agent_name    = agent_name;
    if (status === 'completed') updates.completed_at = new Date().toISOString();

    const { data, error } = await supabase
      .from('tasks')
      .update(updates)
      .eq('task_id', task_id)
      .select()
      .single();

    if (error) return res.status(400).json({ error: error.message });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// PATCH /tasks/:task_id/envelope
// Used by base_agent.py to write the execution section back to the stored envelope.
// Append-only — never overwrites intake, task, or priority sections.
// Body: { execution: { ... } }
const updateTaskEnvelope = async (req, res) => {
  try {
    const { task_id }  = req.params;
    const { execution } = req.body;

    if (!execution) return res.status(400).json({ error: 'execution section is required.' });

    // Fetch current envelope
    const { data: current, error: fetchError } = await supabase
      .from('tasks')
      .select('envelope')
      .eq('task_id', task_id)
      .single();

    if (fetchError) return res.status(404).json({ error: 'Task not found.' });

    // Merge — append-only, intake/task/priority are never touched
    const updatedEnvelope = { ...current.envelope, execution };

    const { data, error } = await supabase
      .from('tasks')
      .update({ envelope: updatedEnvelope, updated_at: new Date().toISOString() })
      .eq('task_id', task_id)
      .select()
      .single();

    if (error) return res.status(400).json({ error: error.message });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// PATCH /tasks/:task_id/output-files
// Appends a file reference to output_files array.
// Body: { file_path, file_type }
const addOutputFile = async (req, res) => {
  try {
    const { task_id }            = req.params;
    const { file_path, file_type } = req.body;

    if (!file_path || !file_type) {
      return res.status(400).json({ error: 'file_path and file_type are required.' });
    }

    const { data: current, error: fetchError } = await supabase
      .from('tasks')
      .select('output_files')
      .eq('task_id', task_id)
      .single();

    if (fetchError) return res.status(404).json({ error: 'Task not found.' });

    const newFile      = { file_path, file_type, created_at: new Date().toISOString() };
    const updatedFiles = [...(current.output_files || []), newFile];

    const { data, error } = await supabase
      .from('tasks')
      .update({ output_files: updatedFiles, updated_at: new Date().toISOString() })
      .eq('task_id', task_id)
      .select()
      .single();

    if (error) return res.status(400).json({ error: error.message });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

module.exports = {
  getTasks,
  getTaskById,
  createTask,
  updateTaskStatus,
  updateTaskEnvelope,
  addOutputFile,
};