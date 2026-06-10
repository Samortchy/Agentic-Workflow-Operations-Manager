const crypto = require('crypto');
const employeesService = require('../services/employees.service.js');
const supabaseAdmin = require('../config/supabaseAdmin.js');

// Auto-generated temp password (alphanumeric, with a letter+digit for complexity).
function genTempPassword() {
  return crypto.randomBytes(12).toString('base64').replace(/[^a-zA-Z0-9]/g, '').slice(0, 12) + 'A1';
}

const getEmployees = async (req, res) => {
  try {
    // Scope to authenticated user's company — set by setCompanyContext middleware
    const data = await employeesService.getAll({ ...req.query, company_id: req.company_id });

    // Demo-only convenience: surface stored temp passwords to admins (level >= 3).
    if ((req.access_level || 1) >= 3 && Array.isArray(data)) {
      try {
        const { data: comp } = await supabaseAdmin.from('companies')
          .select('settings').eq('company_id', req.company_id).single();
        const pwmap = ((comp && comp.settings) || {}).demo_passwords || {};
        data.forEach(e => { if (pwmap[e.email]) e.temp_password = pwmap[e.email]; });
      } catch (_) { /* non-fatal */ }
    }

    return res.status(200).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

// Store a generated temp password in the company settings (demo-only visibility).
async function _storeTempPassword(company_id, email, password) {
  try {
    const { data: comp } = await supabaseAdmin.from('companies')
      .select('settings').eq('company_id', company_id).single();
    const settings = (comp && comp.settings) || {};
    settings.demo_passwords = { ...(settings.demo_passwords || {}), [email]: password };
    await supabaseAdmin.from('companies').update({ settings }).eq('company_id', company_id);
  } catch (_) { /* non-fatal */ }
}

const getEmployeeById = async (req, res) => {
  try {
    const data = await employeesService.getById(req.params.employee_id);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(404).json({ error: err.message });
  }
};

const createEmployee = async (req, res) => {
  try {
    const data = await employeesService.create({ ...req.body, company_id: req.company_id });

    // Also provision a login (auto temp password) so the employee can sign in.
    let temp_password = null, login_note = null;
    try {
      temp_password = genTempPassword();
      const { error: authErr } = await supabaseAdmin.auth.admin.createUser({
        email: data.email, password: temp_password, email_confirm: true,
      });
      if (authErr) throw new Error(authErr.message);
    } catch (e) {
      temp_password = null;
      login_note = /already.*regist|already.*exist|exists/i.test(e.message)
        ? 'A login already exists for this email; it was left unchanged.'
        : 'Employee added, but creating a login failed: ' + e.message;
    }

    if (temp_password) await _storeTempPassword(req.company_id, data.email, temp_password);

    return res.status(201).json({ employee: data, temp_password, login_note });
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const updateEmployee = async (req, res) => {
  try {
    const data = await employeesService.update(req.params.employee_id, req.body);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const deactivateEmployee = async (req, res) => {
  try {
    // You can't deactivate your own account (would lock you out).
    if (req.params.employee_id === req.employee_id) {
      return res.status(400).json({ error: 'You cannot deactivate your own account.' });
    }
    const data = await employeesService.deactivate(req.params.employee_id);
    return res.status(200).json({ message: 'Employee deactivated.', employee: data });
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

module.exports = { getEmployees, getEmployeeById, createEmployee, updateEmployee, deactivateEmployee };