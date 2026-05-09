const express = require('express');
const router = express.Router();
const {
  getTasks,
  getTaskById,
  createTask,
  updateTaskStatus,
  updateTaskEnvelope,
  addOutputFile,
} = require('../controllers/tasks.controller.js');

// GET /tasks?company_id=&status=&department=&agent_name=&is_autonomous=&priority_score=
router.get('/', getTasks);

// GET /tasks/:task_id
router.get('/:task_id', getTaskById);

// POST /tasks?company_id=
router.post('/', createTask);

// PATCH /tasks/:task_id/status
router.patch('/:task_id/status', updateTaskStatus);

// PATCH /tasks/:task_id/envelope
router.patch('/:task_id/envelope', updateTaskEnvelope);

// PATCH /tasks/:task_id/output-files
router.patch('/:task_id/output-files', addOutputFile);

module.exports = router;
