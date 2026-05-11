const supabase                  = require('../config/supabaseAdmin.js');
const { SUBSCRIPTION_STATUSES } = require('../config/constants.js');

const getAll = async () => {
  const { data, error } = await supabase
    .from('companies')
    .select('*')
    .order('created_at', { ascending: false });

  if (error) throw new Error(error.message);
  return data;
};

const getById = async (company_id) => {
  const { data, error } = await supabase
    .from('companies')
    .select('*')
    .eq('company_id', company_id)
    .single();

  if (error) throw new Error('Company not found.');
  return data;
};

const create = async ({ name, domain, email_domains = [], settings = {} }) => {
  const { data, error } = await supabase
    .from('companies')
    .insert([{ name, domain, email_domains, settings, subscription_status: 'trial' }])
    .select()
    .single();

  if (error) throw new Error(error.message);
  return data;
};

const update = async (company_id, updates) => {
  // Protect immutable fields
  delete updates.company_id;
  delete updates.created_at;

  if (updates.subscription_status && !SUBSCRIPTION_STATUSES.includes(updates.subscription_status)) {
    throw new Error(`subscription_status must be one of: ${SUBSCRIPTION_STATUSES.join(', ')}`);
  }

  updates.updated_at = new Date().toISOString();

  const { data, error } = await supabase
    .from('companies')
    .update(updates)
    .eq('company_id', company_id)
    .select()
    .single();

  if (error) throw new Error(error.message);
  return data;
};

const remove = async (company_id) => {
  const { error } = await supabase
    .from('companies')
    .delete()
    .eq('company_id', company_id);

  if (error) throw new Error(error.message);
};

module.exports = { getAll, getById, create, update, remove };