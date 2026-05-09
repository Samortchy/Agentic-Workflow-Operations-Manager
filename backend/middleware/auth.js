const supabase = require('../config/supabase.js');

// Verifies the Supabase JWT from the Authorization header.
// Attaches the authenticated user to req.user on success.
// Every protected route must go through this middleware first.
//
// Usage in routes:
//   router.get('/tasks', auth, tasksController.getTasks);

const auth = async (req, res, next) => {
  try {
    const authHeader = req.headers['authorization'];

    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return res.status(401).json({ error: 'Missing or malformed Authorization header. Expected: Bearer <token>' });
    }

    const token = authHeader.split(' ')[1];

    // Verify the token against Supabase — this also checks expiry
    const { data, error } = await supabase.auth.getUser(token);

    if (error || !data?.user) {
      return res.status(401).json({ error: 'Invalid or expired token.' });
    }

    // Attach the full Supabase user object to the request
    req.user = data.user;

    next();
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

module.exports = auth;