const { ACCESS_LEVELS } = require('../config/constants.js');

// Returns a middleware that blocks requests from users below the required access level.
//
// Must run AFTER auth and setCompanyContext — depends on req.access_level being set.
//
// Access levels (from constants.js):
//   1 — EMPLOYEE   : read their own tasks, submit requests
//   2 — SENIOR     : read all tasks in their department
//   3 — MANAGER    : approve medium-risk actions, sign off onboarding
//   4 — EXECUTIVE  : approve high-risk actions, access audit logs, manage company
//
// Usage in routes:
//   // Only managers and above can resolve approvals
//   router.patch('/approvals/:id/resolve', auth, setCompanyContext, requireLevel(ACCESS_LEVELS.MANAGER), approvalsController.resolveApproval);
//
//   // Only executives can delete a company
//   router.delete('/companies/:id', auth, setCompanyContext, requireLevel(ACCESS_LEVELS.EXECUTIVE), companiesController.deleteCompany);
//
//   // Any authenticated employee can view tasks
//   router.get('/tasks', auth, setCompanyContext, requireLevel(ACCESS_LEVELS.EMPLOYEE), tasksController.getTasks);

const requireLevel = (minLevel) => {
  return (req, res, next) => {
    if (req.access_level === undefined) {
      return res.status(500).json({
        error: 'setCompanyContext middleware must run before requireLevel.',
      });
    }

    if (req.access_level < minLevel) {
      const levelNames = Object.entries(ACCESS_LEVELS)
        .find(([, v]) => v === minLevel)?.[0] || `level ${minLevel}`;

      return res.status(403).json({
        error: `Access denied. This action requires ${levelNames} access or above. Your level: ${req.access_level}.`,
      });
    }

    next();
  };
};

module.exports = requireLevel;