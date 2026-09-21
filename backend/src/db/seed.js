'use strict';
// Seed: `npm run db:seed`
// Creates demo org "DEJOIY" + domain workmail.dejoiy.com + an admin user.
// Idempotent: exits quietly if the org already exists.
//
// Admin password: set SEED_ADMIN_PASSWORD. If unset, a clearly-marked DEV
// password is used and printed with a warning — never use it in production.
const bcrypt = require('bcrypt');
const { v4: uuidv4 } = require('uuid');
const config = require('../config');
const pool = require('../db');
const { ensureDefaultFolders } = require('../routes/admin');

const PLANS = [
  { code: 'free', name: 'Free', price_inr_monthly: 0, max_users: 2, storage_gb: 5 },
  { code: 'starter', name: 'Starter', price_inr_monthly: 99, max_users: 25, storage_gb: 10 },
  { code: 'business', name: 'Business', price_inr_monthly: 149, max_users: 200, storage_gb: 25 },
];

async function main() {
  const existing = await pool.query(`SELECT id FROM orgs WHERE slug='dejoiy'`);
  if (existing.rows[0]) {
    console.log('seed: org "dejoiy" already exists, nothing to do');
    await pool.end();
    return;
  }

  let adminPassword = process.env.SEED_ADMIN_PASSWORD;
  if (!adminPassword) {
    adminPassword = 'DejoiyDev123!';
    console.warn('seed: WARNING — using default DEV password "DejoiyDev123!". Set SEED_ADMIN_PASSWORD for anything real.');
  }

  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    for (const p of PLANS) {
      await client.query(
        `INSERT INTO plans (id, code, name, price_inr_monthly, max_users, storage_gb)
         VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT (code) DO NOTHING`,
        [uuidv4(), p.code, p.name, p.price_inr_monthly, p.max_users, p.storage_gb]
      );
    }

    const orgId = uuidv4();
    await client.query(
      `INSERT INTO orgs (id, name, slug, plan) VALUES ($1,'DEJOIY','dejoiy','starter')`, [orgId]);

    const domainId = uuidv4();
    await client.query(
      `INSERT INTO domains (id, org_id, domain, verification_status, verification_code, dkim_selector)
       VALUES ($1,$2,'workmail.dejoiy.com','pending',$3,'dmail')`,
      [domainId, orgId, 'dmail-verify-' + uuidv4().replace(/-/g, '')]
    );

    const userId = uuidv4();
    const passwordHash = await bcrypt.hash(adminPassword, config.bcryptRounds);
    await client.query(
      `INSERT INTO users (id, org_id, email, password_hash, display_name, role)
       VALUES ($1,$2,'admin@workmail.dejoiy.com',$3,'Dejoiy Admin','super_admin')`,
      [userId, orgId, passwordHash]
    );

    const mailboxId = uuidv4();
    await client.query(
      `INSERT INTO mailboxes (id, org_id, user_id, domain_id, local_part)
       VALUES ($1,$2,$3,$4,'admin')`, [mailboxId, orgId, userId, domainId]
    );
    await ensureDefaultFolders(client, orgId, mailboxId);

    const starter = await client.query(`SELECT id FROM plans WHERE code='starter'`);
    await client.query(
      `INSERT INTO subscriptions (id, org_id, plan_id, status, seats, current_period_start, current_period_end)
       VALUES ($1,$2,$3,'trialing',5,now(),now() + interval '14 days')`,
      [uuidv4(), orgId, starter.rows[0].id]
    );

    // Welcome message in Inbox.
    const inbox = await client.query(
      `SELECT id FROM folders WHERE mailbox_id=$1 AND kind='inbox'`, [mailboxId]);
    const body = 'Welcome to Dejoiy Mail!\n\nYour organization workspace is ready. Add users from Admin → Users, and verify your domain from Admin → Domains.\n\n— The Dejoiy Mail team';
    await client.query(
      `INSERT INTO messages (id, org_id, mailbox_id, folder_id, from_addr, to_addrs, subject, snippet, body_text, size_bytes)
       VALUES ($1,$2,$3,$4,'team@dmail.dejoiy.com',$5,'Welcome to Dejoiy Mail','Welcome to Dejoiy Mail! Your organization workspace is ready.',$6,$7)`,
      [uuidv4(), orgId, mailboxId, inbox.rows[0].id,
        JSON.stringify(['admin@workmail.dejoiy.com']), body, Buffer.byteLength(body)]
    );

    await client.query('COMMIT');
    console.log('seed: org "DEJOIY" created');
    console.log('seed: admin login → admin@workmail.dejoiy.com');
  } catch (e) {
    await client.query('ROLLBACK');
    throw e;
  } finally {
    client.release();
    await pool.end();
  }
}

main().catch((e) => { console.error('seed failed:', e.message); process.exit(1); });
