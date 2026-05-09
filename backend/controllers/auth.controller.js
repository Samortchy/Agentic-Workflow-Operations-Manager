const supabase      = require('../config/supabase.js');
const supabaseAdmin = require('../config/supabaseAdmin.js');

// POST /auth/register
// Body: { name, email, password, role, department, company_id }
const register = async (req, res) => {
  try {
    const { name, email, password, role, department, company_id } = req.body;

    if (!name || !email || !password || !role || !department || !company_id) {
      return res.status(400).json({
        error: 'name, email, password, role, department, and company_id are required.',
      });
    }

    // Admin client bypasses RLS for user creation
    const { data: authData, error: authError } = await supabaseAdmin.auth.admin.createUser({
      email,
      password,
      email_confirm: true,
    });
    if (authError) return res.status(400).json({ error: authError.message });

    const { data: employee, error: empError } = await supabaseAdmin
      .from('employees')
      .insert([{ name, email, role, department, company_id, is_active: true }])
      .select()
      .single();

    if (empError) return res.status(400).json({ error: empError.message });

    return res.status(201).json({ user: authData.user, employee });
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// POST /auth/login
// Body: { email, password }
const login = async (req, res) => {
  try {
    const { email, password } = req.body;

    if (!email || !password) {
      return res.status(400).json({ error: 'email and password are required.' });
    }

    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) return res.status(401).json({ error: error.message });

    return res.status(200).json({
      access_token:  data.session.access_token,
      refresh_token: data.session.refresh_token,
      user:          data.user,
    });
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// POST /auth/logout
const logout = async (req, res) => {
  try {
    const { error } = await supabase.auth.signOut();
    if (error) return res.status(400).json({ error: error.message });
    return res.status(200).json({ message: 'Logged out successfully.' });
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

// POST /auth/refresh
// Body: { refresh_token }
const refreshToken = async (req, res) => {
  try {
    const { refresh_token } = req.body;
    if (!refresh_token) return res.status(400).json({ error: 'refresh_token is required.' });

    const { data, error } = await supabase.auth.refreshSession({ refresh_token });
    if (error) return res.status(401).json({ error: error.message });

    return res.status(200).json({
      access_token:  data.session.access_token,
      refresh_token: data.session.refresh_token,
    });
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

module.exports = { register, login, logout, refreshToken };