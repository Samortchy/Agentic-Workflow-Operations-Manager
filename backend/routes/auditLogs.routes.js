const express = require('express');
const router  = express.Router();
const {
  getAuditLogs,
  getAuditLogById,
  createAuditLog,
  getTaskTimeline,
} = require('../controllers/auditLogs.controller.js');

// GET /audit-logs?company_id=&task_id=&agent_name=&event_type=&from=&to=
router.get('/', getAuditLogs);

// GET /audit-logs/task/:task_id/timeline
// Must come before /:log_id so "task" isn't consumed as a log ID
router.get('/task/:task_id/timeline', getTaskTimeline);

// GET /audit-logs/:log_id
router.get('/:log_id', getAuditLogById);

// POST /audit-logs
router.post('/', createAuditLog);

module.exports = router;
