const express = require('express');
const router  = express.Router();
const {
  getApprovals,
  getApprovalById,
  createApproval,
  resolveApproval,
  sweepTimedOutApprovals,
} = require('../controllers/approvals.controller.js');

// GET /approvals?company_id=&status=&task_id=&assigned_to=
router.get('/', getApprovals);

// POST /approvals/timeout-sweep
// Must come before /:approval_id so "timeout-sweep" isn't consumed as an ID
router.post('/timeout-sweep', sweepTimedOutApprovals);

// GET /approvals/:approval_id
router.get('/:approval_id', getApprovalById);

// POST /approvals
router.post('/', createApproval);

// PATCH /approvals/:approval_id/resolve
router.patch('/:approval_id/resolve', resolveApproval);

module.exports = router;
