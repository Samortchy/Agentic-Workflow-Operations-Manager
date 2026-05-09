// Anon key client — goes through RLS
// Use this everywhere except auth.service.js
// company context must be set via setCompanyContext middleware before any query

const { createClient } = require('@supabase/supabase-js');
const ws              = require('ws');

const supabaseUrl  = process.env.SUPABASE_URL;
const supabaseAnon = process.env.SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnon) {
    throw new Error('Missing SUPABASE_URL or SUPABASE_ANON_KEY in environment');
}

const supabase = createClient(supabaseUrl, supabaseAnon, {
    auth: {
        autoRefreshToken: false,
        persistSession:   false
    },
    realtime: { transport: ws },
});

module.exports = supabase;