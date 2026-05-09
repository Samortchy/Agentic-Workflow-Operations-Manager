const authService = require('../services/auth.service.js');

const register = async (req, res) => {
  try {
    const data = await authService.register(req.body);
    return res.status(201).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const login = async (req, res) => {
  try {
    const data = await authService.login(req.body);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(401).json({ error: err.message });
  }
};

const logout = async (req, res) => {
  try {
    await authService.logout();
    return res.status(200).json({ message: 'Logged out successfully.' });
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const refreshToken = async (req, res) => {
  try {
    const data = await authService.refreshToken(req.body);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(401).json({ error: err.message });
  }
};

module.exports = { register, login, logout, refreshToken };