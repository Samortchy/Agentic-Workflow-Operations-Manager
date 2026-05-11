const supabase = require('../config/supabaseAdmin.js');

// Strips the domain from an email address.
// 'ali@company.com' → 'company.com'
const extractDomain = (email) => {
  if (!email || !email.includes('@')) {
    throw new Error(`Invalid email address: '${email}'`);
  }
  return email.split('@')[1].toLowerCase().trim();
};

// Matches an incoming sender email to a company by domain.
// Queries companies where email_domains array contains the sender's domain.
// Returns the matched company row or throws if no match found.
//
// Called before anything else in the pipeline — company context depends on this.
// If no company matches, the email cannot be processed and should be dropped.
const matchCompanyByEmail = async (senderEmail) => {
  const domain = extractDomain(senderEmail);

  const { data, error } = await supabase
    .from('companies')
    .select('company_id, name, domain, subscription_status, settings')
    .contains('email_domains', [domain])
    .eq('subscription_status', 'active')
    .single();

  if (error || !data) {
    throw new Error(
      `No active company found for email domain '${domain}'. ` +
      `Ensure the domain is registered in companies.email_domains.`
    );
  }

  return {
    company_id:          data.company_id,
    company_name:        data.name,
    domain:              data.domain,
    subscription_status: data.subscription_status,
    settings:            data.settings,
  };
};

// Checks whether a given domain is registered to any active company.
// Lightweight check used for validation before running the full match.
const isDomainRegistered = async (email) => {
  try {
    const domain = extractDomain(email);

    const { data } = await supabase
      .from('companies')
      .select('company_id')
      .contains('email_domains', [domain])
      .eq('subscription_status', 'active')
      .limit(1)
      .single();

    return !!data;
  } catch {
    return false;
  }
};

module.exports = { matchCompanyByEmail, isDomainRegistered, extractDomain };