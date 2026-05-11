const auditLogsService = require('../services/auditLogs.service.js');

const getAuditLogs = async (req, res) => {
  try {
    const data = await auditLogsService.getAll({ ...req.query, company_id: req.company_id });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const getAuditLogById = async (req, res) => {
  try {
    const data = await auditLogsService.getById(req.params.log_id);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(404).json({ error: err.message });
  }
};

const createAuditLog = async (req, res) => {
  try {
    const company_id = req.company_id || req.body.company_id;
    const data = await auditLogsService.create({ ...req.body, company_id });
    return res.status(201).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const getTaskTimeline = async (req, res) => {
  try {
    const data = await auditLogsService.getTaskTimeline(req.params.task_id);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

module.exports = { getAuditLogs, getAuditLogById, createAuditLog, getTaskTimeline };