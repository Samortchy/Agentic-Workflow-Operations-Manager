const employeesService = require('../services/employees.service.js');

const getEmployees = async (req, res) => {
  try {
    // Scope to authenticated user's company — set by setCompanyContext middleware
    const data = await employeesService.getAll({ ...req.query, company_id: req.company_id });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const getEmployeeById = async (req, res) => {
  try {
    const data = await employeesService.getById(req.params.employee_id);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(404).json({ error: err.message });
  }
};

const createEmployee = async (req, res) => {
  try {
    const data = await employeesService.create({ ...req.body, company_id: req.company_id });
    return res.status(201).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const updateEmployee = async (req, res) => {
  try {
    const data = await employeesService.update(req.params.employee_id, req.body);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const deactivateEmployee = async (req, res) => {
  try {
    const data = await employeesService.deactivate(req.params.employee_id);
    return res.status(200).json({ message: 'Employee deactivated.', employee: data });
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

module.exports = { getEmployees, getEmployeeById, createEmployee, updateEmployee, deactivateEmployee };