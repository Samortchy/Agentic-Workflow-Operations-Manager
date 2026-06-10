const express = require('express');
const router  = express.Router();
const {
  getMeetings,
  getMeetingById,
  createMeeting,
  updateMeeting,
} = require('../controllers/meetings.controller.js');

// GET /meetings?company_id=&status=&task_id=
router.get('/', getMeetings);

// GET /meetings/:meeting_id
router.get('/:meeting_id', getMeetingById);

// POST /meetings
router.post('/', createMeeting);

// PATCH /meetings/:meeting_id  → confirm / cancel / reschedule
router.patch('/:meeting_id', updateMeeting);

module.exports = router;
