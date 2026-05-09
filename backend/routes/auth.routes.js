const express = require('express');
const router  = express.Router();
const {
  register,
  login,
  logout,
  refreshToken,
} = require('../controllers/auth.controller.js');

// POST /auth/register
router.post('/register', register);

// POST /auth/login
router.post('/login', login);

// POST /auth/logout
router.post('/logout', logout);

// POST /auth/refresh
router.post('/refresh', refreshToken);

module.exports = router;
