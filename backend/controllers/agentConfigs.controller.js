const agentConfigsService = require('../services/agentConfigs.service.js');

const getAgentConfigs = async (req, res) => {
  try {
    const data = await agentConfigsService.getAll({ ...req.query, company_id: req.company_id });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const getAgentConfigById = async (req, res) => {
  try {
    const data = await agentConfigsService.getById(req.params.config_id);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(404).json({ error: err.message });
  }
};

const getActiveConfig = async (req, res) => {
  try {
    const data = await agentConfigsService.getActive(req.params.agent_name, req.company_id);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(404).json({ error: err.message });
  }
};

const createAgentConfig = async (req, res) => {
  try {
    const data = await agentConfigsService.create({ ...req.body, company_id: req.company_id });
    return res.status(201).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const updateAgentConfig = async (req, res) => {
  try {
    const data = await agentConfigsService.update(req.params.config_id, req.body);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const deactivateAgentConfig = async (req, res) => {
  try {
    const data = await agentConfigsService.deactivate(req.params.config_id);
    return res.status(200).json({ message: 'Config deactivated.', config: data });
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

module.exports = { getAgentConfigs, getAgentConfigById, getActiveConfig, createAgentConfig, updateAgentConfig, deactivateAgentConfig };