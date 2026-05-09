// Wraps async route handlers so unhandled promise rejections
// are forwarded to the global errorHandler middleware instead of
// crashing the process or hanging the request.
//
// Without this, an unhandled async error in a controller just
// disappears silently in Express 4. Express 5 handles this natively
// but until then, wrap every async controller with this.
//
// Usage in routes:
//   const asyncHandler = require('../utils/asyncHandler.js');
//   router.get('/tasks', auth, setCompanyContext, asyncHandler(tasksController.getTasks));
//
// Or wrap at the controller level if you prefer:
//   const getTasks = asyncHandler(async (req, res) => { ... });

const asyncHandler = (fn) => (req, res, next) => {
  Promise.resolve(fn(req, res, next)).catch(next);
};

module.exports = asyncHandler;