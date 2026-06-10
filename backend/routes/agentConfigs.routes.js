const express = require('express');
const router = express.Router();
const requireLevel = require('../middleware/requireLevel.js');
const { ACCESS_LEVELS } = require('../config/constants.js');
const {
  getAgentConfigs,
  getAgentConfigById,
  getActiveConfig,
  createAgentConfig,
  updateAgentConfig,
  deactivateAgentConfig,
} = require('../controllers/agentConfigs.controller.js');

// GET /agent-configs?company_id=&agent_name=&is_active=
router.get('/', getAgentConfigs);

// GET /agent-configs/active/:agent_name?company_id=
// Must come before /:config_id so Express doesn't swallow "active" as an ID
router.get('/active/:agent_name', getActiveConfig);

// GET /agent-configs/:config_id
router.get('/:config_id', getAgentConfigById);

// Config writes are Executive-only (agents authenticate at service level and pass).
// POST /agent-configs
router.post('/', requireLevel(ACCESS_LEVELS.EXECUTIVE), createAgentConfig);

// PATCH /agent-configs/:config_id
router.patch('/:config_id', requireLevel(ACCESS_LEVELS.EXECUTIVE), updateAgentConfig);

// PATCH /agent-configs/:config_id/deactivate
router.patch('/:config_id/deactivate', requireLevel(ACCESS_LEVELS.EXECUTIVE), deactivateAgentConfig);

module.exports = router;
