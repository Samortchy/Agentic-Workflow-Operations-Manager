// Lightweight structured logger.
// Wraps console methods with timestamps, log levels, and consistent JSON output.
// No external dependencies — drop-in for any environment.
//
// Usage:
//   const logger = require('../utils/logger.js');
//   logger.info('Task created', { task_id: 'TASK-001', agent: 'leave_checker' });
//   logger.error('Step failed', { step: 'fetch_record', error: err.message });
//   logger.warn('Low confidence score', { score: 0.55, task_id: 'TASK-002' });
//   logger.debug('Envelope state', { envelope });  // only logs in development

const LOG_LEVELS = { debug: 0, info: 1, warn: 2, error: 3 };

// In production, suppress debug logs.
// Set LOG_LEVEL=debug in .env to enable during development.
const CURRENT_LEVEL = LOG_LEVELS[process.env.LOG_LEVEL] ?? LOG_LEVELS.info;

const _log = (level, message, meta = {}) => {
  if (LOG_LEVELS[level] < CURRENT_LEVEL) return;

  const entry = {
    timestamp: new Date().toISOString(),
    level,
    message,
    ...(Object.keys(meta).length > 0 && { meta }),
  };

  // Errors go to stderr, everything else to stdout
  if (level === 'error') {
    console.error(JSON.stringify(entry));
  } else {
    console.log(JSON.stringify(entry));
  }
};

const logger = {
  debug: (message, meta = {}) => _log('debug', message, meta),
  info:  (message, meta = {}) => _log('info',  message, meta),
  warn:  (message, meta = {}) => _log('warn',  message, meta),
  error: (message, meta = {}) => _log('error', message, meta),

  // Convenience — logs an agent lifecycle event with consistent structure.
  // Mirrors the audit_log event_type values from constants.js.
  agentEvent: (event_type, { task_id, agent_name, details = {} } = {}) => {
    _log('info', `[agent] ${event_type}`, { task_id, agent_name, ...details });
  },

  // Convenience — logs an HTTP request. Use in app.js as a simple request logger.
  // For production, replace this with morgan or a proper HTTP logger.
  request: (req) => {
    _log('info', `${req.method} ${req.originalUrl}`, {
      ip:         req.ip,
      company_id: req.company_id || null,
      user_email: req.user?.email || null,
    });
  },
};

module.exports = logger;