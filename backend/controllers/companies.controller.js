const supabase                 = require('../config/supabase.js');
const { SUBSCRIPTION_STATUSES } = require('../config/constants.js');

// GET /companies
const getAllCompanies = async (req, res) => {
  try {
    const { data, error } = await supabase
      .from('companies')
      .select('*')
      .order('created_at', { ascending: false });

    if (error) return res.status(400).json({ error: error.message });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// GET /companies/:company_id
const getCompanyById = async (req, res) => {
  try {
    const { company_id } = req.params;

    const { data, error } = await supabase
      .from('companies')
      .select('*')
      .eq('company_id', company_id)
      .single();

    if (error) return res.status(404).json({ error: 'Company not found.' });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// POST /companies
// Body: { name, domain, email_domains?, settings? }
const createCompany = async (req, res) => {
  try {
    const { name, domain, email_domains = [], settings = {} } = req.body;

    if (!name || !domain) {
      return res.status(400).json({ error: 'name and domain are required.' });
    }

    const { data, error } = await supabase
      .from('companies')
      .insert([{ name, domain, email_domains, settings, subscription_status: 'trial' }])
      .select()
      .single();

    if (error) return res.status(400).json({ error: error.message });
    return res.status(201).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// PATCH /companies/:company_id
// Body: any subset of { name, domain, email_domains, settings, subscription_status }
const updateCompany = async (req, res) => {
  try {
    const { company_id } = req.params;
    const updates = { ...req.body };

    // Protect immutable fields
    delete updates.company_id;
    delete updates.created_at;

    if (updates.subscription_status && !SUBSCRIPTION_STATUSES.includes(updates.subscription_status)) {
      return res.status(400).json({
        error: `subscription_status must be one of: ${SUBSCRIPTION_STATUSES.join(', ')}`,
      });
    }

    updates.updated_at = new Date().toISOString();

    const { data, error } = await supabase
      .from('companies')
      .update(updates)
      .eq('company_id', company_id)
      .select()
      .single();

    if (error) return res.status(400).json({ error: error.message });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// DELETE /companies/:company_id
const deleteCompany = async (req, res) => {
  try {
    const { company_id } = req.params;

    const { error } = await supabase
      .from('companies')
      .delete()
      .eq('company_id', company_id);

    if (error) return res.status(400).json({ error: error.message });
    return res.status(200).json({ message: `Company ${company_id} deleted.` });
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

module.exports = { getAllCompanies, getCompanyById, createCompany, updateCompany, deleteCompany };