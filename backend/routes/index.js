const express = require('express');
const router  = express.Router();

router.use('/auth',            require('./auth.routes.js'));
router.use('/companies',       require('./companies.routes.js'));
router.use('/employees',       require('./employees.routes.js'));
router.use('/tasks',           require('./tasks.routes.js'));
router.use('/approvals',       require('./approvals.routes.js'));
router.use('/audit-logs',      require('./auditLogs.routes.js'));
router.use('/outcome-signals', require('./outcomeSignals.routes.js'));
router.use('/agent-configs',   require('./agentConfigs.routes.js'));

module.exports = router;
