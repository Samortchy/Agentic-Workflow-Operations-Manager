const auth              = require('./auth.js');
const setCompanyContext = require('./setCompanyContext.js');
const { AGENT_API_KEY_HEADER } = require('../config/constants.js');

// Combined authentication: a request is allowed if it carries EITHER
//   (a) a valid agent API key  → trusted internal Python agent, OR
//   (b) a valid Supabase JWT    → logged-in dashboard user.
//
// Many endpoints are hit by both callers (e.g. GET /tasks, /employees, /meetings),
// so we accept either credential here. Fine-grained authorization (requireLevel,
// per-company scoping) layers on top of this in 4B/4D.
//
// Agent path  → req.is_agent=true, company_id from query/body, access_level=4 (service).
// User  path  → auth() sets req.user, then setCompanyContext() sets req.company_id /
//               req.access_level / req.employee_id from the employee record.
const authenticate = (req, res, next) => {
  const agentKey = req.headers[AGENT_API_KEY_HEADER];

  if (agentKey) {
    if (agentKey !== process.env.AGENT_API_KEY) {
      return res.status(401).json({ error: 'Invalid agent API key.' });
    }
    req.is_agent     = true;
    req.company_id   = req.query.company_id || (req.body && req.body.company_id) || null;
    req.access_level = 4;   // agents act with service-level access
    return next();
  }

  // No agent key → require a user JWT, then resolve company context.
  return auth(req, res, (err) => {
    if (err) return next(err);
    return setCompanyContext(req, res, next);
  });
};

module.exports = authenticate;
