const supabase              = require('../config/supabase.js');
const { DEPARTMENTS }       = require('../config/constants.js');

// GET /employees?company_id=&department=&is_active=
const getEmployees = async (req, res) => {
  try {
    const { company_id, department, is_active } = req.query;

    let query = supabase
      .from('employees')
      .select('*')
      .order('name', { ascending: true });

    if (company_id)          query = query.eq('company_id', company_id);
    if (department)          query = query.eq('department', department);
    if (is_active !== undefined) query = query.eq('is_active', is_active === 'true');

    const { data, error } = await query;
    if (error) return res.status(400).json({ error: error.message });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// GET /employees/:employee_id
const getEmployeeById = async (req, res) => {
  try {
    const { employee_id } = req.params;

    const { data, error } = await supabase
      .from('employees')
      .select('*')
      .eq('employee_id', employee_id)
      .single();

    if (error) return res.status(404).json({ error: 'Employee not found.' });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// POST /employees
// Body: { name, email, role, department, company_id, access_level? }
const createEmployee = async (req, res) => {
  try {
    const { name, email, role, department, company_id, access_level = 1 } = req.body;

    if (!name || !email || !role || !department || !company_id) {
      return res.status(400).json({
        error: 'name, email, role, department, and company_id are required.',
      });
    }

    if (!DEPARTMENTS.includes(department)) {
      return res.status(400).json({
        error: `department must be one of: ${DEPARTMENTS.join(', ')}`,
      });
    }

    if (access_level < 1 || access_level > 4) {
      return res.status(400).json({ error: 'access_level must be between 1 and 4.' });
    }

    const { data, error } = await supabase
      .from('employees')
      .insert([{ name, email, role, department, company_id, access_level, is_active: true }])
      .select()
      .single();

    if (error) return res.status(400).json({ error: error.message });
    return res.status(201).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// PATCH /employees/:employee_id
// Body: any subset of { name, email, role, department, access_level, is_active }
const updateEmployee = async (req, res) => {
  try {
    const { employee_id } = req.params;
    const updates = { ...req.body };

    // Protect immutable / sensitive fields
    delete updates.employee_id;
    delete updates.company_id;  // company reassignment not allowed via this route
    delete updates.created_at;

    if (updates.department && !DEPARTMENTS.includes(updates.department)) {
      return res.status(400).json({
        error: `department must be one of: ${DEPARTMENTS.join(', ')}`,
      });
    }

    if (updates.access_level && (updates.access_level < 1 || updates.access_level > 4)) {
      return res.status(400).json({ error: 'access_level must be between 1 and 4.' });
    }

    updates.updated_at = new Date().toISOString();

    const { data, error } = await supabase
      .from('employees')
      .update(updates)
      .eq('employee_id', employee_id)
      .select()
      .single();

    if (error) return res.status(400).json({ error: error.message });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// DELETE /employees/:employee_id
// Soft delete — sets is_active = false.
// Hard delete breaks FK refs in audit_logs.
const deactivateEmployee = async (req, res) => {
  try {
    const { employee_id } = req.params;

    const { data, error } = await supabase
      .from('employees')
      .update({ is_active: false, updated_at: new Date().toISOString() })
      .eq('employee_id', employee_id)
      .select()
      .single();

    if (error) return res.status(400).json({ error: error.message });
    return res.status(200).json({ message: 'Employee deactivated.', employee: data });
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

module.exports = { getEmployees, getEmployeeById, createEmployee, updateEmployee, deactivateEmployee };