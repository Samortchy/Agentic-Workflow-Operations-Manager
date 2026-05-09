const supabase              = require('../config/supabase.js');
const { OUTCOME_VERDICTS }  = require('../config/constants.js');

// GET /outcome-signals?company_id=&task_id=&verdict=&signal_type=
const getOutcomeSignals = async (req, res) => {
  try {
    const { company_id, task_id, verdict, signal_type } = req.query;

    let query = supabase
      .from('outcome_signals')
      .select('*')
      .order('timestamp', { ascending: false });

    if (company_id)  query = query.eq('company_id', company_id);
    if (task_id)     query = query.eq('task_id', task_id);
    if (verdict)     query = query.eq('verdict', verdict);
    if (signal_type) query = query.eq('signal_type', signal_type);

    const { data, error } = await query;
    if (error) return res.status(400).json({ error: error.message });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// GET /outcome-signals/:signal_id
const getOutcomeSignalById = async (req, res) => {
  try {
    const { signal_id } = req.params;

    const { data, error } = await supabase
      .from('outcome_signals')
      .select('*')
      .eq('signal_id', signal_id)
      .single();

    if (error) return res.status(404).json({ error: 'Outcome signal not found.' });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// POST /outcome-signals
// Called by outcome_emitter.py after an agent completes.
// The 'unknown' verdict is valid and must never be rejected — spec Section 12 rule 6.
// Body: { company_id, task_id, signal_type, value?, verdict? }
// verdict defaults to null — Outcome Tracker sets it later via PATCH /verdict
const createOutcomeSignal = async (req, res) => {
  try {
    const {
      company_id,
      task_id,
      signal_type,
      value   = {},
      verdict = null,
    } = req.body;

    if (!company_id || !task_id || !signal_type) {
      return res.status(400).json({
        error: 'company_id, task_id, and signal_type are required.',
      });
    }

    // null verdict is valid — only validate if one is provided
    if (verdict !== null && !OUTCOME_VERDICTS.includes(verdict)) {
      return res.status(400).json({
        error: `verdict must be one of: ${OUTCOME_VERDICTS.join(', ')} or null.`,
      });
    }

    const { data, error } = await supabase
      .from('outcome_signals')
      .insert([{
        company_id,
        task_id,
        signal_type,
        value,
        verdict,
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

// PATCH /outcome-signals/:signal_id/verdict
// Called by Outcome Tracker when it resolves a signal.
// 'unknown' is intentional and must be accepted — spec Section 12 rule 6.
// Body: { verdict }
const setVerdict = async (req, res) => {
  try {
    const { signal_id } = req.params;
    const { verdict }   = req.body;

    if (!verdict) return res.status(400).json({ error: 'verdict is required.' });

    if (!OUTCOME_VERDICTS.includes(verdict)) {
      return res.status(400).json({
        error: `verdict must be one of: ${OUTCOME_VERDICTS.join(', ')}`,
      });
    }

    const { data, error } = await supabase
      .from('outcome_signals')
      .update({ verdict })
      .eq('signal_id', signal_id)
      .select()
      .single();

    if (error) return res.status(400).json({ error: error.message });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// GET /outcome-signals/task/:task_id/summary
// Verdict summary for a task — used by the Model Updater for retraining.
const getTaskVerdictSummary = async (req, res) => {
  try {
    const { task_id } = req.params;

    const { data, error } = await supabase
      .from('outcome_signals')
      .select('verdict, timestamp')
      .eq('task_id', task_id)
      .order('timestamp', { ascending: false });

    if (error) return res.status(400).json({ error: error.message });

    const counts = { success: 0, failure: 0, unknown: 0, unresolved: 0 };
    for (const signal of data) {
      if (signal.verdict === null) counts.unresolved++;
      else counts[signal.verdict]++;
    }

    const latest_verdict = (data.find((s) => s.verdict !== null) || {}).verdict || null;

    return res.status(200).json({
      task_id,
      total_signals: data.length,
      latest_verdict,
      counts,
    });
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

module.exports = {
  getOutcomeSignals,
  getOutcomeSignalById,
  createOutcomeSignal,
  setVerdict,
  getTaskVerdictSummary,
};