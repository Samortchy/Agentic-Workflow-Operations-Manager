const supabase        = require('../config/supabase.js');
const { DEPARTMENTS } = require('../config/constants.js');

const getAll = async (filters = {}) => {
  const { company_id, department, is_active } = filters;

  let query = supabase
    .from('employees')
    .select('*')
    .order('name', { ascending: true });

  if (company_id)              query = query.eq('company_id', company_id);
  if (department)              query = query.eq('department', department);
  if (is_active !== undefined) query = query.eq('is_active', is_active === 'true' || is_active === true);

  const { data, error } = await query;
  if (error) throw new Error(error.message);
  return data;
};

const getById = async (employee_id) => {
  const { data, error } = await supabase
    .from('employees')
    .select('*')
    .eq('employee_id', employee_id)
    .single();

  if (error) throw new Error('Employee not found.');
  return data;
};

const create = async ({ name, email, role, department, company_id, access_level = 1 }) => {
  if (!DEPARTMENTS.includes(department)) {
    throw new Error(`department must be one of: ${DEPARTMENTS.join(', ')}`);
  }
  if (access_level < 1 || access_level > 4) {
    throw new Error('access_level must be between 1 and 4.');
  }

  const { data, error } = await supabase
    .from('employees')
    .insert([{ name, email, role, department, company_id, access_level, is_active: true }])
    .select()
    .single();

  if (error) throw new Error(error.message);
  return data;
};

const update = async (employee_id, updates) => {
  delete updates.employee_id;
  delete updates.company_id;
  delete updates.created_at;

  if (updates.department && !DEPARTMENTS.includes(updates.department)) {
    throw new Error(`department must be one of: ${DEPARTMENTS.join(', ')}`);
  }
  if (updates.access_level && (updates.access_level < 1 || updates.access_level > 4)) {
    throw new Error('access_level must be between 1 and 4.');
  }

  updates.updated_at = new Date().toISOString();

  const { data, error } = await supabase
    .from('employees')
    .update(updates)
    .eq('employee_id', employee_id)
    .select()
    .single();

  if (error) throw new Error(error.message);
  return data;
};

// Soft delete — hard delete breaks FK refs in audit_logs
const deactivate = async (employee_id) => {
  const { data, error } = await supabase
    .from('employees')
    .update({ is_active: false, updated_at: new Date().toISOString() })
    .eq('employee_id', employee_id)
    .select()
    .single();

  if (error) throw new Error(error.message);
  return data;
};

module.exports = { getAll, getById, create, update, deactivate };