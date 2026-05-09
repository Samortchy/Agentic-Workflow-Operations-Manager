const supabase        = require('../config/supabase.js');
const { AGENT_NAMES } = require('../config/constants.js');

// Valid values — mirrors spec Section 10.3
const VALID_STEP_TYPES = ['extractor', 'processor', 'dispatcher', 'custom', 'agent_call'];
const VALID_APPROVALS  = ['none', 'single_confirm', 'single_confirm_if_low_confidence', 'manager_sign_off'];
const REQUIRED_CONFIG_FIELDS = [
  'agent_name', 'agent_version', 'department',
  'risk_tier', 'approval', 'steps', 'on_failure', 'outcome_signal',
];

// GET /agent-configs?company_id=&agent_name=&is_active=
const getAgentConfigs = async (req, res) => {
  try {
    const { company_id, agent_name, is_active } = req.query;

    let query = supabase
      .from('agent_configs')
      .select('*')
      .order('agent_name', { ascending: true });

    if (company_id)              query = query.eq('company_id', company_id);
    if (agent_name)              query = query.eq('agent_name', agent_name);
    if (is_active !== undefined) query = query.eq('is_active', is_active === 'true');

    const { data, error } = await query;
    if (error) return res.status(400).json({ error: error.message });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// GET /agent-configs/:config_id
const getAgentConfigById = async (req, res) => {
  try {
    const { config_id } = req.params;

    const { data, error } = await supabase
      .from('agent_configs')
      .select('*')
      .eq('config_id', config_id)
      .single();

    if (error) return res.status(404).json({ error: 'Agent config not found.' });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// GET /agent-configs/active/:agent_name?company_id=
// What the factory runner calls at startup to load its config.
const getActiveConfig = async (req, res) => {
  try {
    const { agent_name } = req.params;
    const { company_id } = req.query;

    if (!company_id) {
      return res.status(400).json({ error: 'company_id query param is required.' });
    }

    const { data, error } = await supabase
      .from('agent_configs')
      .select('*')
      .eq('agent_name', agent_name)
      .eq('company_id', company_id)
      .eq('is_active', true)
      .order('created_at', { ascending: false })
      .limit(1)
      .single();

    if (error) {
      return res.status(404).json({
        error: `No active config found for agent '${agent_name}'.`,
      });
    }
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// POST /agent-configs
// Validates config against spec before inserting.
// Body: { company_id, agent_name, config, version? }
const createAgentConfig = async (req, res) => {
  try {
    const { company_id, agent_name, config, version = '1.0' } = req.body;

    if (!company_id || !agent_name || !config) {
      return res.status(400).json({
        error: 'company_id, agent_name, and config are required.',
      });
    }

    // Validate agent_name against known agents
    if (!AGENT_NAMES.includes(agent_name)) {
      return res.status(400).json({
        error: `agent_name must be one of: ${AGENT_NAMES.join(', ')}`,
      });
    }

    // Validate required top-level config fields (spec Section 10.3)
    const missingFields = REQUIRED_CONFIG_FIELDS.filter((f) => !(f in config));
    if (missingFields.length > 0) {
      return res.status(400).json({
        error: `Config missing required fields: ${missingFields.join(', ')}`,
      });
    }

    // Validate step types
    const invalidSteps = config.steps.filter((s) => !VALID_STEP_TYPES.includes(s.type));
    if (invalidSteps.length > 0) {
      return res.status(400).json({
        error: `Invalid step types: ${invalidSteps.map((s) => s.type).join(', ')}. Must be one of: ${VALID_STEP_TYPES.join(', ')}`,
      });
    }

    // Validate approval value
    if (!VALID_APPROVALS.includes(config.approval)) {
      return res.status(400).json({
        error: `approval must be one of: ${VALID_APPROVALS.join(', ')}`,
      });
    }

    // Validate step names are unique within the config
    const stepNames = config.steps.map((s) => s.name);
    const uniqueNames = new Set(stepNames);
    if (uniqueNames.size !== stepNames.length) {
      return res.status(400).json({
        error: 'Step names must be unique within a config.',
      });
    }

    const { data, error } = await supabase
      .from('agent_configs')
      .insert([{ company_id, agent_name, config, version, is_active: true }])
      .select()
      .single();

    if (error) return res.status(400).json({ error: error.message });
    return res.status(201).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// PATCH /agent-configs/:config_id
// Body: { config, version? }
const updateAgentConfig = async (req, res) => {
  try {
    const { config_id }      = req.params;
    const { config, version } = req.body;

    if (!config) return res.status(400).json({ error: 'config is required.' });

    const updates = { config, updated_at: new Date().toISOString() };
    if (version) updates.version = version;

    const { data, error } = await supabase
      .from('agent_configs')
      .update(updates)
      .eq('config_id', config_id)
      .select()
      .single();

    if (error) return res.status(400).json({ error: error.message });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// PATCH /agent-configs/:config_id/deactivate
// Soft-deactivate before creating a new version of the same agent config.
const deactivateAgentConfig = async (req, res) => {
  try {
    const { config_id } = req.params;

    const { data, error } = await supabase
      .from('agent_configs')
      .update({ is_active: false, updated_at: new Date().toISOString() })
      .eq('config_id', config_id)
      .select()
      .single();

    if (error) return res.status(400).json({ error: error.message });
    return res.status(200).json({ message: 'Config deactivated.', config: data });
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

module.exports = {
  getAgentConfigs,
  getAgentConfigById,
  getActiveConfig,
  createAgentConfig,
  updateAgentConfig,
  deactivateAgentConfig,
};