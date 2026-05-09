const supabase = require('../config/supabase.js');

// Resolves the company that the authenticated user belongs to
// and attaches it to req.company_id.
//
// Must run AFTER auth middleware — it depends on req.user being set.
// Must run BEFORE any controller that queries a company-scoped table.
//
// Usage in routes:
//   router.get('/tasks', auth, setCompanyContext, tasksController.getTasks);
//
// How it works:
//   Looks up the employees table by req.user.email to find the company_id.
//   The employees table links auth users (by email) to their company.
//   Once resolved, company_id is available in every downstream controller
//   via req.company_id — no controller needs to accept it from the client.
//
// Why this matters:
//   All tables have a company_id FK. Scoping every query to req.company_id
//   ensures a user from Company A can never read or write Company B's data,
//   even if they somehow know the other company's IDs.

const setCompanyContext = async (req, res, next) => {
  try {
    if (!req.user || !req.user.email) {
      return res.status(401).json({ error: 'auth middleware must run before setCompanyContext.' });
    }

    const { data: employee, error } = await supabase
      .from('employees')
      .select('company_id, employee_id, department, access_level, is_active')
      .eq('email', req.user.email)
      .eq('is_active', true)
      .single();

    if (error || !employee) {
      return res.status(403).json({
        error: 'No active employee record found for this user. Contact your administrator.',
      });
    }

    // Attach company context — available to all downstream middleware and controllers
    req.company_id   = employee.company_id;
    req.employee_id  = employee.employee_id;
    req.department   = employee.department;
    req.access_level = employee.access_level;

    next();
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

module.exports = setCompanyContext;