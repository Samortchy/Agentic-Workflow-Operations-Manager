const supabase      = require('../config/supabase.js');
const supabaseAdmin = require('../config/supabaseAdmin.js');
const { AGENT_API_KEY_HEADER } = require('../config/constants.js');

// ── Register ──────────────────────────────────────────────────────────────────
// Creates a new company + auth user + employee row in one transaction-like flow.
// Uses supabaseAdmin to bypass RLS for user creation.
// Body: { companyName, domain, email_domains, name, email, password, role, department }
const register = async ({ companyName, domain, email_domains = [], name, email, password, role, department }) => {
  // 1. Create the company first
  const { data: company, error: companyError } = await supabaseAdmin
    .from('companies')
    .insert([{
      name:                companyName,
      domain,
      email_domains,
      subscription_status: 'trial',
      settings:            {},
    }])
    .select()
    .single();

  if (companyError) throw new Error(`Company creation failed: ${companyError.message}`);

  // 2. Create the Supabase auth user
  const { data: authData, error: authError } = await supabaseAdmin.auth.admin.createUser({
    email,
    password,
    email_confirm: true,
  });

  if (authError) {
    // Roll back the company row if auth fails
    await supabaseAdmin.from('companies').delete().eq('company_id', company.company_id);
    throw new Error(`Auth user creation failed: ${authError.message}`);
  }

  // 3. Create the employee row linked to the company
  // First registrant gets access_level 4 (EXECUTIVE) — they own the company account
  const { data: employee, error: empError } = await supabaseAdmin
    .from('employees')
    .insert([{
      name,
      email,
      role,
      department,
      company_id:   company.company_id,
      access_level: 4,
      is_active:    true,
    }])
    .select()
    .single();

  if (empError) {
    // Roll back both if employee insert fails
    await supabaseAdmin.auth.admin.deleteUser(authData.user.id);
    await supabaseAdmin.from('companies').delete().eq('company_id', company.company_id);
    throw new Error(`Employee creation failed: ${empError.message}`);
  }

  return { company, user: authData.user, employee };
};

// ── Login ─────────────────────────────────────────────────────────────────────
const login = async ({ email, password }) => {
  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) throw new Error(error.message);

  return {
    access_token:  data.session.access_token,
    refresh_token: data.session.refresh_token,
    user:          data.user,
  };
};

// ── Logout ────────────────────────────────────────────────────────────────────
const logout = async () => {
  const { error } = await supabase.auth.signOut();
  if (error) throw new Error(error.message);
};

// ── Token refresh ─────────────────────────────────────────────────────────────
const refreshToken = async ({ refresh_token }) => {
  const { data, error } = await supabase.auth.refreshSession({ refresh_token });
  if (error) throw new Error(error.message);

  return {
    access_token:  data.session.access_token,
    refresh_token: data.session.refresh_token,
  };
};

// ── Agent API key validation ───────────────────────────────────────────────────
// Python agents post to the backend using a per-company API key stored in
// companies.settings.agent_api_key — not a user JWT.
// The key is passed via the x-agent-api-key header (AGENT_API_KEY_HEADER constant).
//
// Returns the company_id if the key is valid, throws if not.
// Used in a separate middleware for agent-only routes.
const validateAgentApiKey = async (req) => {
  const apiKey = req.headers[AGENT_API_KEY_HEADER];

  if (!apiKey) {
    throw new Error(`Missing ${AGENT_API_KEY_HEADER} header.`);
  }

  // Find the company whose settings.agent_api_key matches
  const { data: companies, error } = await supabaseAdmin
    .from('companies')
    .select('company_id, settings, subscription_status')
    .eq('subscription_status', 'active');

  if (error) throw new Error(`Agent key validation failed: ${error.message}`);

  const matched = (companies || []).find(
    (c) => c.settings?.agent_api_key === apiKey
  );

  if (!matched) {
    throw new Error('Invalid agent API key.');
  }

  return matched.company_id;
};

module.exports = { register, login, logout, refreshToken, validateAgentApiKey };