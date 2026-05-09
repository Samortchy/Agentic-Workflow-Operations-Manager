// Global error handler.
// Must be the LAST middleware registered in your Express app — after all routes.
//
// Usage in app.js / index.js (after all router.use() calls):
//   const errorHandler = require('./middleware/errorHandler.js');
//   app.use(errorHandler);
//
// Any route or middleware that calls next(err) will land here.
// Controllers that throw synchronously also land here if you wrap
// your routes with an async error catcher (see asyncCatch below).

const errorHandler = (err, req, res, next) => {
  // Log the full error server-side for debugging
  console.error(`[${new Date().toISOString()}] ${req.method} ${req.originalUrl}`);
  console.error(err);

  // Supabase / PostgREST errors come with a code field
  if (err.code) {
    // Foreign key violation
    if (err.code === '23503') {
      return res.status(400).json({ error: 'Referenced record does not exist.' });
    }
    // Unique constraint violation
    if (err.code === '23505') {
      return res.status(409).json({ error: 'A record with this value already exists.' });
    }
    // Not null violation
    if (err.code === '23502') {
      return res.status(400).json({ error: `Required field missing: ${err.column || 'unknown'}` });
    }
    // Check constraint violation
    if (err.code === '23514') {
      return res.status(400).json({ error: 'Value failed a database constraint check.' });
    }
  }

  // JWT errors
  if (err.name === 'JsonWebTokenError' || err.name === 'TokenExpiredError') {
    return res.status(401).json({ error: 'Invalid or expired token.' });
  }

  // Validation errors (thrown manually)
  if (err.status === 400) {
    return res.status(400).json({ error: err.message });
  }

  // Forbidden
  if (err.status === 403) {
    return res.status(403).json({ error: err.message });
  }

  // Not found
  if (err.status === 404) {
    return res.status(404).json({ error: err.message });
  }

  // Everything else — 500
  return res.status(500).json({
    error: process.env.NODE_ENV === 'production'
      ? 'Internal server error.'
      : err.message || 'Internal server error.',
  });
};

// asyncCatch — wraps async route handlers so unhandled promise rejections
// are forwarded to errorHandler instead of crashing the process.
//
// Usage in routes (optional but recommended):
//   const { asyncCatch } = require('./middleware/errorHandler.js');
//   router.get('/tasks', auth, setCompanyContext, asyncCatch(tasksController.getTasks));

const asyncCatch = (fn) => (req, res, next) => {
  Promise.resolve(fn(req, res, next)).catch(next);
};

module.exports = errorHandler;
module.exports.asyncCatch = asyncCatch;