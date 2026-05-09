// Service role client — bypasses RLS entirely
// ONLY import this in auth.service.js and nowhere else
// Never expose this client to routes or controllers

const { createClient } = require('@supabase/supabase-js');
const ws              = require('ws');

const supabaseUrl         = process.env.SUPABASE_URL;
const supabaseServiceKey  = process.env.SUPABASE_SERVICE_KEY;

if (!supabaseUrl || !supabaseServiceKey) {
    throw new Error('Missing SUPABASE_URL or SUPABASE_SERVICE_KEY in environment');
}

const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey, {
    auth: {
        autoRefreshToken: false,
        persistSession:   false
    },
    realtime: { transport: ws },
});

module.exports = supabaseAdmin;