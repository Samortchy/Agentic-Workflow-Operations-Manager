const outcomeSignalsService = require('../services/outcomeSignals.service.js');

const getOutcomeSignals = async (req, res) => {
  try {
    const data = await outcomeSignalsService.getAll({ ...req.query, company_id: req.company_id });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const getOutcomeSignalById = async (req, res) => {
  try {
    const data = await outcomeSignalsService.getById(req.params.signal_id);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(404).json({ error: err.message });
  }
};

const createOutcomeSignal = async (req, res) => {
  try {
    const data = await outcomeSignalsService.create({ ...req.body, company_id: req.company_id });
    return res.status(201).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const setVerdict = async (req, res) => {
  try {
    const data = await outcomeSignalsService.setVerdict(req.params.signal_id, req.body.verdict);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const getTaskVerdictSummary = async (req, res) => {
  try {
    const data = await outcomeSignalsService.getTaskVerdictSummary(req.params.task_id);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

module.exports = { getOutcomeSignals, getOutcomeSignalById, createOutcomeSignal, setVerdict, getTaskVerdictSummary };