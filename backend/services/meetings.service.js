const supabase            = require('../config/supabaseAdmin.js');
const { MEETING_STATUSES } = require('../config/constants.js');

const getAll = async (filters = {}) => {
  const { company_id, status, task_id } = filters;

  let query = supabase
    .from('meetings')
    .select('*')
    .order('created_at', { ascending: false });

  if (company_id) query = query.eq('company_id', company_id);
  if (status)     query = query.eq('status', status);
  if (task_id)    query = query.eq('task_id', task_id);

  const { data, error } = await query;
  if (error) throw new Error(error.message);
  return data;
};

const getById = async (meeting_id) => {
  const { data, error } = await supabase
    .from('meetings')
    .select('*')
    .eq('meeting_id', meeting_id)
    .single();

  if (error) throw new Error('Meeting not found.');
  return data;
};

// Called by the Meeting Scheduler agent after SlotRanker proposes slots.
const create = async ({
  company_id,
  task_id = null,
  title,
  organizer_email = null,
  participants = [],
  proposed_slots = [],
  confirmed_slot = null,
  status = 'proposed',
}) => {
  if (!company_id) throw new Error('company_id is required.');
  if (!title)      throw new Error('title is required.');
  if (!MEETING_STATUSES.includes(status)) {
    throw new Error(`status must be one of: ${MEETING_STATUSES.join(', ')}`);
  }

  const row = {
    company_id,
    task_id,
    title,
    organizer_email,
    participants,
    proposed_slots,
    confirmed_slot,
    status,
  };

  const { data, error } = await supabase
    .from('meetings')
    .insert([row])
    .select()
    .single();

  if (error) throw new Error(error.message);
  return data;
};

// Confirm / cancel / reschedule. Strips immutable fields.
const update = async (meeting_id, updates) => {
  delete updates.meeting_id;
  delete updates.company_id;
  delete updates.created_at;

  if (updates.status && !MEETING_STATUSES.includes(updates.status)) {
    throw new Error(`status must be one of: ${MEETING_STATUSES.join(', ')}`);
  }

  updates.updated_at = new Date().toISOString();

  const { data, error } = await supabase
    .from('meetings')
    .update(updates)
    .eq('meeting_id', meeting_id)
    .select()
    .single();

  if (error) throw new Error(error.message);
  return data;
};

module.exports = { getAll, getById, create, update };
