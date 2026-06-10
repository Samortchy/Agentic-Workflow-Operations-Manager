const tasksService = require('../services/tasks.service.js');

const getTasks = async (req, res) => {
  try {
    const filters = { ...req.query, company_id: req.company_id };
    // Visibility: managers/admins (level >= 3) see all company tasks; everyone else
    // sees only their own requests plus their department's tasks.
    if ((req.access_level || 1) < 3) {
      filters.restrict_email = (req.user && req.user.email) || '';
      filters.restrict_department = req.department || '';
    }
    const data = await tasksService.getAll(filters);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const getTaskById = async (req, res) => {
  try {
    const data = await tasksService.getById(req.params.task_id);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(404).json({ error: err.message });
  }
};

// Called by the Phase 1 pipeline — envelope is the full Phase 1 JSON body.
const createTask = async (req, res) => {
  try {
    const company_id = req.company_id || req.body.company_id;
    const data = await tasksService.create(req.body, company_id);
    return res.status(201).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const updateTaskStatus = async (req, res) => {
  try {
    const data = await tasksService.updateStatus(req.params.task_id, req.body);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const updateTaskEnvelope = async (req, res) => {
  try {
    const data = await tasksService.updateEnvelope(req.params.task_id, req.body.execution);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const addOutputFile = async (req, res) => {
  try {
    const data = await tasksService.addOutputFile(req.params.task_id, req.body);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

module.exports = { getTasks, getTaskById, createTask, updateTaskStatus, updateTaskEnvelope, addOutputFile };