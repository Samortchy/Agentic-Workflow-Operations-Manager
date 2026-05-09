const supabase             = require('../config/supabase.js');
const { OUTCOME_VERDICTS } = require('../config/constants.js');

const getAll = async (filters = {}) => {
  const { company_id, task_id, verdict, signal_type } = filters;

  let query = supabase
    .from('outcome_signals')
    .select('*')
    .order('timestamp', { ascending: false });

  if (company_id)  query = query.eq('company_id', company_id);
  if (task_id)     query = query.eq('task_id', task_id);
  if (verdict)     query = query.eq('verdict', verdict);
  if (signal_type) query = query.eq('signal_type', signal_type);

  const { data, error } = await query;
  if (error) throw new Error(error.message);
  return data;
};

const getById = async (signal_id) => {
  const { data, error } = await supabase
    .from('outcome_signals')
    .select('*')
    .eq('signal_id', signal_id)
    .single();

  if (error) throw new Error('Outcome signal not found.');
  return data;
};

// verdict defaults to null — Outcome Tracker sets it later via setVerdict.
// The 'unknown' verdict is valid and must never be rejected — spec Section 12 rule 6.
const create = async ({ company_id, task_id, signal_type, value = {}, verdict = null }) => {
  if (verdict !== null && !OUTCOME_VERDICTS.includes(verdict)) {
    throw new Error(`verdict must be one of: ${OUTCOME_VERDICTS.join(', ')} or null.`);
  }

  const { data, error } = await supabase
    .from('outcome_signals')
    .insert([{ company_id, task_id, signal_type, value, verdict, timestamp: new Date().toISOString() }])
    .select()
    .single();

  if (error) throw new Error(error.message);
  return data;
};

// Called by Outcome Tracker when it resolves a signal.
// 'unknown' is intentional — spec Section 12 rule 6.
const setVerdict = async (signal_id, verdict) => {
  if (!OUTCOME_VERDICTS.includes(verdict)) {
    throw new Error(`verdict must be one of: ${OUTCOME_VERDICTS.join(', ')}`);
  }

  const { data, error } = await supabase
    .from('outcome_signals')
    .update({ verdict })
    .eq('signal_id', signal_id)
    .select()
    .single();

  if (error) throw new Error(error.message);
  return data;
};

// Verdict summary for a task — used by the Model Updater for retraining.
const getTaskVerdictSummary = async (task_id) => {
  const { data, error } = await supabase
    .from('outcome_signals')
    .select('verdict, timestamp')
    .eq('task_id', task_id)
    .order('timestamp', { ascending: false });

  if (error) throw new Error(error.message);

  const counts = { success: 0, failure: 0, unknown: 0, unresolved: 0 };
  for (const signal of data) {
    if (signal.verdict === null) counts.unresolved++;
    else counts[signal.verdict]++;
  }

  const latest_verdict = (data.find((s) => s.verdict !== null) || {}).verdict || null;

  return { task_id, total_signals: data.length, latest_verdict, counts };
};

module.exports = { getAll, getById, create, setVerdict, getTaskVerdictSummary };