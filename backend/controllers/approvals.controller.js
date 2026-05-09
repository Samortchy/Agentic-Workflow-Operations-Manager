const approvalsService = require('../services/approvals.service.js');

const getApprovals = async (req, res) => {
  try {
    const data = await approvalsService.getAll({ ...req.query, company_id: req.company_id });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const getApprovalById = async (req, res) => {
  try {
    const data = await approvalsService.getById(req.params.approval_id);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(404).json({ error: err.message });
  }
};

const createApproval = async (req, res) => {
  try {
    const data = await approvalsService.create({ ...req.body, company_id: req.company_id });
    return res.status(201).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const resolveApproval = async (req, res) => {
  try {
    const data = await approvalsService.resolve(req.params.approval_id, req.body);
    return res.status(200).json(data);
  } catch (err) {
    const status = err.message.includes('timed out') || err.message.includes('already') ? 409 : 400;
    return res.status(status).json({ error: err.message });
  }
};

const sweepTimedOutApprovals = async (req, res) => {
  try {
    const data = await approvalsService.sweepTimedOut();
    return res.status(200).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

module.exports = { getApprovals, getApprovalById, createApproval, resolveApproval, sweepTimedOutApprovals };