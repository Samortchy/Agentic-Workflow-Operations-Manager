const express = require('express');
const router  = express.Router();
const {
  getAllCompanies,
  getCompanyById,
  createCompany,
  updateCompany,
  deleteCompany,
} = require('../controllers/companies.controller.js');

// GET /companies
router.get('/', getAllCompanies);

// GET /companies/:company_id
router.get('/:company_id', getCompanyById);

// POST /companies
router.post('/', createCompany);

// PATCH /companies/:company_id
router.patch('/:company_id', updateCompany);

// DELETE /companies/:company_id
router.delete('/:company_id', deleteCompany);

module.exports = router;
