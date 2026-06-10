const express = require('express');
const router  = express.Router();
const requireLevel = require('../middleware/requireLevel.js');
const { ACCESS_LEVELS } = require('../config/constants.js');
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

// Employee management is Manager+ (GET stays open — agents read participants).
// POST /employees
router.post('/', requireLevel(ACCESS_LEVELS.MANAGER), createEmployee);

// PATCH /employees/:employee_id
router.patch('/:employee_id', requireLevel(ACCESS_LEVELS.MANAGER), updateEmployee);

// DELETE /employees/:employee_id  → soft-deactivates (sets is_active = false)
router.delete('/:employee_id', requireLevel(ACCESS_LEVELS.MANAGER), deactivateEmployee);

module.exports = router;
