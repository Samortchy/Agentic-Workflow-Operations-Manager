'use strict';

const express      = require('express');
const cors         = require('cors');
const helmet       = require('helmet');
const morgan       = require('morgan');

const routes       = require('./routes/index.js');
const errorHandler = require('./middleware/errorHandler.js');
const logger       = require('./utils/logger.js');
const { AGENT_API_KEY_HEADER } = require('./config/constants.js');

// ─── App factory ──────────────────────────────────────────────────────────────
// Returns a configured Express application.
// Kept separate from server.js so it can be imported cleanly in tests.

const createApp = () => {
  const app = express();

  // ── Security headers ─────────────────────────────────────────────────────
  app.use(helmet());

  // ── CORS ─────────────────────────────────────────────────────────────────
  // In production, restrict origins to the exact frontend domain.
  const allowedOrigins = process.env.CORS_ORIGIN
    ? process.env.CORS_ORIGIN.split(',').map((o) => o.trim())
    : ['http://localhost:3000', 'http://localhost:5173'];

  app.use(
    cors({
      origin: (origin, callback) => {
        // Allow server-to-server (no origin) and listed origins
        if (!origin || allowedOrigins.includes(origin)) {
          callback(null, true);
        } else {
          callback(new Error(`CORS: origin '${origin}' not allowed.`));
        }
      },
      credentials: true,
    })
  );

  // ── Body parsing ─────────────────────────────────────────────────────────
  app.use(express.json({ limit: '2mb' }));
  app.use(express.urlencoded({ extended: true }));

  // ── HTTP request logging ─────────────────────────────────────────────────
  // Use morgan in development for readable logs; switch to JSON in production.
  if (process.env.NODE_ENV === 'production') {
    app.use(
      morgan('combined', {
        stream: { write: (msg) => logger.info(msg.trim()) },
      })
    );
  } else {
    app.use(morgan('dev'));
  }

  // ── Agent API key validation ─────────────────────────────────────────────
  // Internal Python agents authenticate with a shared API key header instead
  // of a Supabase JWT.  Routes that should only be reachable by agents
  // (e.g. POST /audit-logs, POST /outcome-signals) should add this middleware
  // in addition to, or instead of, the `auth` JWT middleware.
  //
  // Usage in a route file:
  //   const { agentKeyAuth } = require('../app.js');
  //   router.post('/', agentKeyAuth, controller.createAuditLog);
  //
  // The key is set in the environment as AGENT_API_KEY.
  const agentKeyAuth = (req, res, next) => {
    const key = req.headers[AGENT_API_KEY_HEADER];
    if (!key || key !== process.env.AGENT_API_KEY) {
      return res.status(401).json({ error: 'Invalid or missing agent API key.' });
    }
    next();
  };

  // ── Health check ─────────────────────────────────────────────────────────
  // Available without any authentication — used by container health probes.
  app.get('/health', (_req, res) =>
    res.status(200).json({ status: 'ok', timestamp: new Date().toISOString() })
  );

  // ── API routes ───────────────────────────────────────────────────────────
  app.use('/api', routes);

  // ── 404 handler ─────────────────────────────────────────────────────────
  // Catches any request that didn't match a registered route.
  app.use((_req, res) =>
    res.status(404).json({ error: 'Route not found.' })
  );

  // ── Global error handler ─────────────────────────────────────────────────
  // Must be registered LAST — after all routes and the 404 handler.
  app.use(errorHandler);

  return { app, agentKeyAuth };
};

module.exports = createApp;
