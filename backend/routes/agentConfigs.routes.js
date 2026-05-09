const express = require('express');
const router = express.Router();
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

// POST /agent-configs
router.post('/', createAgentConfig);

// PATCH /agent-configs/:config_id
router.patch('/:config_id', updateAgentConfig);

// PATCH /agent-configs/:config_id/deactivate
router.patch('/:config_id/deactivate', deactivateAgentConfig);

module.exports = router;
