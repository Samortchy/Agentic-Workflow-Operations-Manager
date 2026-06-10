const express = require('express');
const router  = express.Router();
const requireLevel = require('../middleware/requireLevel.js');
const { ACCESS_LEVELS } = require('../config/constants.js');
const {
  getAllCompanies,
  getCompanyById,
  createCompany,
  updateCompany,
  deleteCompany,
} = require('../controllers/companies.controller.js');

// GET /companies  (also used by agents for company auto-discovery — keep readable)
router.get('/', getAllCompanies);

// GET /companies/:company_id
router.get('/:company_id', getCompanyById);

// Company management is Executive-only.
// POST /companies
router.post('/', requireLevel(ACCESS_LEVELS.EXECUTIVE), createCompany);

// PATCH /companies/:company_id
router.patch('/:company_id', requireLevel(ACCESS_LEVELS.EXECUTIVE), updateCompany);

// DELETE /companies/:company_id
router.delete('/:company_id', requireLevel(ACCESS_LEVELS.EXECUTIVE), deleteCompany);

module.exports = router;
