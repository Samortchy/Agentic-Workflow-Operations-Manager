const companiesService = require('../services/companies.service.js');

const getAllCompanies = async (req, res) => {
  try {
    const data = await companiesService.getAll();
    return res.status(200).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const getCompanyById = async (req, res) => {
  try {
    const data = await companiesService.getById(req.params.company_id);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(404).json({ error: err.message });
  }
};

const createCompany = async (req, res) => {
  try {
    const data = await companiesService.create(req.body);
    return res.status(201).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const updateCompany = async (req, res) => {
  try {
    const data = await companiesService.update(req.params.company_id, req.body);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const deleteCompany = async (req, res) => {
  try {
    await companiesService.remove(req.params.company_id);
    return res.status(200).json({ message: `Company ${req.params.company_id} deleted.` });
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

module.exports = { getAllCompanies, getCompanyById, createCompany, updateCompany, deleteCompany };