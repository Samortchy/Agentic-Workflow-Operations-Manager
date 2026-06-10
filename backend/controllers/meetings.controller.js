const meetingsService = require('../services/meetings.service.js');
const { ACCESS_LEVELS } = require('../config/constants.js');

// company_id comes from setCompanyContext once auth is wired (Phase 4); until then
// fall back to the query/body value the caller supplies (frontend + Python agent).
const resolveCompanyId = (req) =>
  req.company_id || req.query.company_id || req.body.company_id;

const getMeetings = async (req, res) => {
  try {
    const data = await meetingsService.getAll({ ...req.query, company_id: resolveCompanyId(req) });
    return res.status(200).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const getMeetingById = async (req, res) => {
  try {
    const data = await meetingsService.getById(req.params.meeting_id);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(404).json({ error: err.message });
  }
};

const createMeeting = async (req, res) => {
  try {
    const data = await meetingsService.create({ ...req.body, company_id: resolveCompanyId(req) });
    return res.status(201).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

const updateMeeting = async (req, res) => {
  try {
    // Authorization (4B): agents (service) and Managers (>=3) may modify any meeting;
    // a regular user may modify only a meeting they organize.
    if (!req.is_agent && (req.access_level || 0) < ACCESS_LEVELS.MANAGER) {
      const meeting = await meetingsService.getById(req.params.meeting_id);
      const email = req.user && req.user.email;
      if (!email || email !== meeting.organizer_email) {
        return res.status(403).json({
          error: 'Only the meeting organizer or a manager can modify this meeting.',
        });
      }
    }
    const data = await meetingsService.update(req.params.meeting_id, req.body);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
};

module.exports = { getMeetings, getMeetingById, createMeeting, updateMeeting };
