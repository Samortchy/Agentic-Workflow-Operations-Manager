require('dotenv').config({ path: require('path').resolve(__dirname, '../.env') });
const admin = require('./config/supabaseAdmin.js');

// usage: node _approvals.js relax   OR   node _approvals.js restore <json>
const MODE = process.argv[2];
const TARGETS = ['email_agent', 'report_generator', 'powerpoint_agent'];

(async () => {
  const { data, error } = await admin.from('agent_configs')
    .select('config_id, agent_name, config').in('agent_name', TARGETS);
  if (error) { console.log('ERR', error.message); process.exit(1); }

  if (MODE === 'relax') {
    const originals = {};
    for (const row of data) {
      originals[row.agent_name] = row.config.approval;
      const cfg = { ...row.config, approval: 'none' };
      await admin.from('agent_configs').update({ config: cfg }).eq('config_id', row.config_id);
      console.log(`relaxed ${row.agent_name}: ${row.config.approval} -> none`);
    }
    console.log('ORIGINALS=' + JSON.stringify(originals));
  } else if (MODE === 'restore') {
    const orig = JSON.parse(process.argv[3]);
    for (const row of data) {
      const cfg = { ...row.config, approval: orig[row.agent_name] };
      await admin.from('agent_configs').update({ config: cfg }).eq('config_id', row.config_id);
      console.log(`restored ${row.agent_name}: none -> ${orig[row.agent_name]}`);
    }
  }
  process.exit(0);
})();
