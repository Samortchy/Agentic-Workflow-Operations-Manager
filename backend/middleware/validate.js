const {
  DEPARTMENTS,
  TASK_STATUSES,
  PRIORITY_SCORES,
  PRIORITY_LABELS,
  APPROVAL_TYPES,
  APPROVAL_STATUSES,
  AUDIT_EVENT_TYPES,
  OUTCOME_VERDICTS,
  AGENT_NAMES,
  SUBSCRIPTION_STATUSES,
} = require('../config/constants.js');

// validate(schema) returns a middleware that checks req.body against a schema.
//
// Schema format:
//   {
//     fieldName: { required: bool, type: 'string'|'number'|'boolean'|'object'|'array', oneOf: [...] }
//   }
//
// Usage in routes:
//   router.post('/tasks', auth, setCompanyContext, validate(schemas.createTask), tasksController.createTask);
//
// Returns 400 with a list of all validation errors if any field fails.
// Returns next() immediately if all fields pass.

const validate = (schema) => {
  return (req, res, next) => {
    const errors = [];
    const body   = req.body || {};

    for (const [field, rules] of Object.entries(schema)) {
      const value    = body[field];
      const isEmpty  = value === undefined || value === null || value === '';

      // Required check
      if (rules.required && isEmpty) {
        errors.push(`'${field}' is required.`);
        continue; // skip further checks if the field is missing
      }

      // Skip optional fields that weren't provided
      if (isEmpty) continue;

      // Type check
      if (rules.type) {
        const actualType = Array.isArray(value) ? 'array' : typeof value;
        if (actualType !== rules.type) {
          errors.push(`'${field}' must be a ${rules.type} (got ${actualType}).`);
          continue;
        }
      }

      // Enum check
      if (rules.oneOf && !rules.oneOf.includes(value)) {
        errors.push(`'${field}' must be one of: ${rules.oneOf.join(', ')}.`);
      }

      // Min/max for numbers
      if (rules.type === 'number' || typeof value === 'number') {
        if (rules.min !== undefined && value < rules.min) {
          errors.push(`'${field}' must be at least ${rules.min}.`);
        }
        if (rules.max !== undefined && value > rules.max) {
          errors.push(`'${field}' must be at most ${rules.max}.`);
        }
      }

      // minLength for strings
      if (rules.minLength && typeof value === 'string' && value.trim().length < rules.minLength) {
        errors.push(`'${field}' must be at least ${rules.minLength} characters.`);
      }
    }

    if (errors.length > 0) {
      return res.status(400).json({ errors });
    }

    next();
  };
};

// ── Pre-built schemas for every controller action ─────────────────────────────
// Import these in your route files alongside validate().

const schemas = {

  // auth
  register: {
    name:       { required: true,  type: 'string'  },
    email:      { required: true,  type: 'string'  },
    password:   { required: true,  type: 'string', minLength: 8 },
    role:       { required: true,  type: 'string'  },
    department: { required: true,  type: 'string',  oneOf: DEPARTMENTS },
    company_id: { required: true,  type: 'string'  },
  },

  login: {
    email:    { required: true, type: 'string' },
    password: { required: true, type: 'string' },
  },

  refreshToken: {
    refresh_token: { required: true, type: 'string' },
  },

  // companies
  createCompany: {
    name:   { required: true,  type: 'string' },
    domain: { required: true,  type: 'string' },
  },

  updateCompany: {
    subscription_status: { required: false, type: 'string', oneOf: SUBSCRIPTION_STATUSES },
  },

  // employees
  createEmployee: {
    name:         { required: true,  type: 'string' },
    email:        { required: true,  type: 'string' },
    role:         { required: true,  type: 'string' },
    department:   { required: true,  type: 'string', oneOf: DEPARTMENTS },
    company_id:   { required: true,  type: 'string' },
    access_level: { required: false, type: 'number', min: 1, max: 4 },
  },

  updateEmployee: {
    department:   { required: false, type: 'string', oneOf: DEPARTMENTS },
    access_level: { required: false, type: 'number', min: 1, max: 4 },
  },

  // tasks
  updateTaskStatus: {
    status: { required: true, type: 'string', oneOf: TASK_STATUSES },
  },

  updateTaskEnvelope: {
    execution: { required: true, type: 'object' },
  },

  addOutputFile: {
    file_path: { required: true, type: 'string' },
    file_type: { required: true, type: 'string' },
  },

  // approvals
  createApproval: {
    company_id:      { required: true,  type: 'string' },
    task_id:         { required: true,  type: 'string' },
    agent_name:      { required: true,  type: 'string', oneOf: AGENT_NAMES },
    command_preview: { required: true,  type: 'string' },
    required_level:  { required: true,  type: 'number', min: 1, max: 4 },
    approval_type:   { required: true,  type: 'string', oneOf: APPROVAL_TYPES },
    timeout_minutes: { required: false, type: 'number', min: 1 },
  },

  resolveApproval: {
    status:      { required: true, type: 'string', oneOf: ['approved', 'denied'] },
    resolved_by: { required: true, type: 'string' },
  },

  // audit logs
  createAuditLog: {
    company_id:  { required: true,  type: 'string' },
    agent_name:  { required: true,  type: 'string' },
    event_type:  { required: true,  type: 'string', oneOf: AUDIT_EVENT_TYPES },
  },

  // outcome signals
  createOutcomeSignal: {
    company_id:  { required: true,  type: 'string' },
    task_id:     { required: true,  type: 'string' },
    signal_type: { required: true,  type: 'string' },
  },

  setVerdict: {
    verdict: { required: true, type: 'string', oneOf: OUTCOME_VERDICTS },
  },

  // agent configs
  createAgentConfig: {
    company_id:  { required: true, type: 'string' },
    agent_name:  { required: true, type: 'string', oneOf: AGENT_NAMES },
    config:      { required: true, type: 'object' },
  },

  updateAgentConfig: {
    config: { required: true, type: 'object' },
  },
};

module.exports = { validate, schemas };