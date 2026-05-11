const supabase        = require('../config/supabaseAdmin.js');
const { AGENT_NAMES } = require('../config/constants.js');

const VALID_STEP_TYPES = ['extractor', 'processor', 'dispatcher', 'custom', 'agent_call'];
const VALID_APPROVALS  = ['none', 'single_confirm', 'single_confirm_if_low_confidence', 'manager_sign_off'];
const REQUIRED_CONFIG_FIELDS = [
  'agent_name', 'agent_version', 'department',
  'risk_tier', 'approval', 'steps', 'on_failure', 'outcome_signal',
];

const _validateConfig = (config) => {
  const missing = REQUIRED_CONFIG_FIELDS.filter((f) => !(f in config));
  if (missing.length > 0) throw new Error(`Config missing required fields: ${missing.join(', ')}`);

  const invalidSteps = config.steps.filter((s) => !VALID_STEP_TYPES.includes(s.type));
  if (invalidSteps.length > 0) {
    throw new Error(`Invalid step types: ${invalidSteps.map((s) => s.type).join(', ')}`);
  }

  if (!VALID_APPROVALS.includes(config.approval)) {
    throw new Error(`approval must be one of: ${VALID_APPROVALS.join(', ')}`);
  }

  const stepNames  = config.steps.map((s) => s.name);
  const uniqueNames = new Set(stepNames);
  if (uniqueNames.size !== stepNames.length) {
    throw new Error('Step names must be unique within a config.');
  }
};

const getAll = async (filters = {}) => {
  const { company_id, agent_name, is_active } = filters;

  let query = supabase
    .from('agent_configs')
    .select('*')
    .order('agent_name', { ascending: true });

  // Return configs that belong to this company OR are global (company_id IS NULL)
  if (company_id) query = query.or(`company_id.eq.${company_id},company_id.is.null`);
  if (agent_name)              query = query.eq('agent_name', agent_name);
  if (is_active !== undefined) query = query.eq('is_active', is_active === 'true' || is_active === true);

  const { data, error } = await query;
  if (error) throw new Error(error.message);
  return data;
};

const getById = async (config_id) => {
  const { data, error } = await supabase
    .from('agent_configs')
    .select('*')
    .eq('config_id', config_id)
    .single();

  if (error) throw new Error('Agent config not found.');
  return data;
};

// Called by the factory runner at startup to load its config.
const getActive = async (agent_name, company_id) => {
  // 1. Try company-specific config first
  if (company_id) {
    const { data } = await supabase
      .from('agent_configs')
      .select('*')
      .eq('agent_name', agent_name)
      .eq('company_id', company_id)
      .eq('is_active', true)
      .order('created_at', { ascending: false })
      .limit(1)
      .maybeSingle();

    if (data) return data;
  }

  // 2. Fall back to any active config with this agent_name (universal / unscoped)
  const { data, error } = await supabase
    .from('agent_configs')
    .select('*')
    .eq('agent_name', agent_name)
    .eq('is_active', true)
    .order('created_at', { ascending: false })
    .limit(1)
    .single();

  if (error) throw new Error(`No active config found for agent '${agent_name}'.`);
  return data;
};

const create = async ({ company_id, agent_name, config, version = '1.0' }) => {
  if (!AGENT_NAMES.includes(agent_name)) {
    throw new Error(`agent_name must be one of: ${AGENT_NAMES.join(', ')}`);
  }
  _validateConfig(config);

  const { data, error } = await supabase
    .from('agent_configs')
    .insert([{ company_id, agent_name, config, version, is_active: true }])
    .select()
    .single();

  if (error) throw new Error(error.message);
  return data;
};

const update = async (config_id, { config, version }) => {
  const updates = { config, updated_at: new Date().toISOString() };
  if (version) updates.version = version;

  const { data, error } = await supabase
    .from('agent_configs')
    .update(updates)
    .eq('config_id', config_id)
    .select()
    .single();

  if (error) throw new Error(error.message);
  return data;
};

const deactivate = async (config_id) => {
  const { data, error } = await supabase
    .from('agent_configs')
    .update({ is_active: false, updated_at: new Date().toISOString() })
    .eq('config_id', config_id)
    .select()
    .single();

  if (error) throw new Error(error.message);
  return data;
};

module.exports = { getAll, getById, getActive, create, update, deactivate };