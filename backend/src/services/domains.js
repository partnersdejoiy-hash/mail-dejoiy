'use strict';
// Domain onboarding service: generates the DNS records a customer must add
// (Option A from TECHNICAL_PLAN.md) and tracks verification state.
//
// Real DNS verification (dig MX/TXT/DKIM/DMARC) is intentionally NOT performed
// in this MVP — it needs the production network + nameserver config. The
// checkDomain() function is a clearly-marked stub that returns the expected
// records so the admin UI can display them; verification flips to "verified"
// only via an explicit admin call after out-of-band confirmation.
const crypto = require('crypto');
const { v4: uuidv4 } = require('uuid');

const MAIL_HOST = 'mail.dmail.dejoiy.com';
const DKIM_SELECTOR = 'dmail';

function requiredRecords(domain) {
  return [
    { type: 'MX', host: '@', value: `10 ${MAIL_HOST}`, purpose: 'Inbound mail routing' },
    { type: 'TXT', host: '@', value: `v=spf1 include:${MAIL_HOST} ~all`, purpose: 'SPF: authorize our senders' },
    { type: 'TXT', host: `${DKIM_SELECTOR}._domainkey`, value: '(public key — generated on verify)', purpose: 'DKIM signature' },
    { type: 'TXT', host: '_dmarc', value: 'v=DMARC1; p=none; rua=mailto:dmarc@dejoiy.com', purpose: 'DMARC monitoring' },
    { type: 'CNAME', host: 'webmail', value: 'dmail.dejoiy.com', purpose: 'Optional white-label login', optional: true },
  ];
}

function newVerificationCode() {
  return 'dmail-verify-' + crypto.randomBytes(16).toString('hex');
}

// STUB: returns what *should* be found. Production implementation will query
// DNS (MX, TXT @, TXT dmail._domainkey, TXT _dmarc) and compare.
async function checkDomain(_domain) {
  return {
    checkedAt: new Date().toISOString(),
    stub: true,
    note: 'DNS verification not yet implemented — flip status via admin API after manual check.',
    expected: requiredRecords(_domain),
    results: { mx_ok: false, spf_ok: false, dkim_ok: false, dmarc_ok: false },
  };
}

async function createDomain(pool, orgId, domain) {
  const clean = domain.trim().toLowerCase();
  if (!/^(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$/.test(clean)) {
    const { badRequest } = require('../middleware/errors');
    throw badRequest('Invalid domain name');
  }
  const id = uuidv4();
  const code = newVerificationCode();
  // TODO(security): generate a real DKIM keypair per domain and store the
  // private key encrypted (KMS). MVP stores only the selector; the keypair
  // generation lands with the mail-server work (Pillar 1).
  const { rows } = await pool.query(
    `INSERT INTO domains (id, org_id, domain, verification_status, verification_code, dkim_selector)
     VALUES ($1,$2,$3,'pending',$4,$5)
     ON CONFLICT (org_id, domain) DO NOTHING
     RETURNING *`,
    [id, orgId, clean, code, DKIM_SELECTOR]
  );
  if (rows.length === 0) {
    const existing = await pool.query(
      'SELECT * FROM domains WHERE org_id=$1 AND domain=$2', [orgId, clean]
    );
    return { domain: existing.rows[0], created: false };
  }
  return { domain: rows[0], created: true };
}

module.exports = { requiredRecords, checkDomain, createDomain, newVerificationCode, MAIL_HOST, DKIM_SELECTOR };
