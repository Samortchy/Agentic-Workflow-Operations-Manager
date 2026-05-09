const express = require('express');
const router  = express.Router();
const {
  getEmployees,
  getEmployeeById,
  createEmployee,
  updateEmployee,
  deactivateEmployee,
} = require('../controllers/employees.controller.js');

// GET /employees?company_id=&department=&is_active=
router.get('/', getEmployees);

// GET /employees/:employee_id
router.get('/:employee_id', getEmployeeById);

// POST /employees
router.post('/', createEmployee);

// PATCH /employees/:employee_id
router.patch('/:employee_id', updateEmployee);

// DELETE /employees/:employee_id  → soft-deactivates (sets is_active = false)
router.delete('/:employee_id', deactivateEmployee);

module.exports = router;
