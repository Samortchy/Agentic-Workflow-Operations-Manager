'use strict';

// Allow Node.js to connect to Supabase on Windows where the CA bundle may differ.
// Must be set before the first HTTPS connection — even before dotenv loads.
process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';

// Load environment variables first — before any config module is imported.
require('dotenv').config({ path: require('path').resolve(__dirname, '../.env') });

const createApp = require('./app.js');
const logger    = require('./utils/logger.js');

// ─── Env validation ────────────────────────────────────────────────────────
// Fail fast on startup if critical variables are missing.
const REQUIRED_ENV = [
  'SUPABASE_URL',
  'SUPABASE_ANON_KEY',
  'SUPABASE_SERVICE_KEY',
  'AGENT_API_KEY',
];

const missingEnv = REQUIRED_ENV.filter((key) => !process.env[key]);
if (missingEnv.length > 0) {
  logger.error('Missing required environment variables', { missing: missingEnv });
  process.exit(1);
}

// ─── Start server ──────────────────────────────────────────────────────────
const { app } = createApp();
const PORT    = parseInt(process.env.PORT || '4000', 10);

const server = app.listen(PORT, () => {
  logger.info('Server started', {
    port:     PORT,
    env:      process.env.NODE_ENV || 'development',
    pid:      process.pid,
  });
});



// ─── Graceful shutdown ─────────────────────────────────────────────────────
// Allows in-flight requests to complete before the process exits.
// Triggered by Ctrl-C in development, or SIGTERM from Docker / PM2.

const shutdown = (signal) => {
  logger.info(`${signal} received — shutting down gracefully`);

  server.close(() => {
    logger.info('HTTP server closed. Exiting.');
    process.exit(0);
  });

  // Force exit if graceful shutdown takes too long (e.g. hung DB connection)
  setTimeout(() => {
    logger.error('Graceful shutdown timed out — forcing exit');
    process.exit(1);
  }, 10_000);
};

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT',  () => shutdown('SIGINT'));

// ─── Unhandled rejection / exception guards ────────────────────────────────
process.on('unhandledRejection', (reason) => {
  logger.error('Unhandled promise rejection', { reason: String(reason) });
  // Don't exit — log and keep running; adjust to process.exit(1) in prod if preferred
});

process.on('uncaughtException', (err) => {
  logger.error('Uncaught exception — shutting down', { error: err.message });
  process.exit(1);
});
