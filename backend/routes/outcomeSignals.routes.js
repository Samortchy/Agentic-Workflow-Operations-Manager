const express = require('express');
const router  = express.Router();
const {
  getOutcomeSignals,
  getOutcomeSignalById,
  createOutcomeSignal,
  setVerdict,
  getTaskVerdictSummary,
} = require('../controllers/outcomeSignals.controller.js');

// GET /outcome-signals?company_id=&task_id=&verdict=&signal_type=
router.get('/', getOutcomeSignals);

// GET /outcome-signals/task/:task_id/summary
// Must come before /:signal_id so "task" isn't consumed as a signal ID
router.get('/task/:task_id/summary', getTaskVerdictSummary);

// GET /outcome-signals/:signal_id
router.get('/:signal_id', getOutcomeSignalById);

// POST /outcome-signals
router.post('/', createOutcomeSignal);

// PATCH /outcome-signals/:signal_id/verdict
router.patch('/:signal_id/verdict', setVerdict);

module.exports = router;
