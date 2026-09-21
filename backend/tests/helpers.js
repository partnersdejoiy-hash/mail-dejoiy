'use strict';
// Test helpers: boots the app against an in-memory Postgres (pg-mem) so the
// suite runs with zero external services (no docker, no redis).
const fs = require('fs');
const path = require('path');
const { newDb } = require('pg-mem');
const bcrypt = require('bcrypt');
const { v4: uuidv4 } = require('uuid');
const { createApp } = require('../src/app');

const FOLDERS = [
  ['Inbox', 'inbox'], ['Sent', 'sent'], ['Drafts', 'drafts'], ['Spam', 'spam'], ['Trash', 'trash'],
];

async function createPool() {
  const db = newDb({ autoCreateForeignKeyIndices: true });
  const { Pool } = db.adapters.createPg();
  const pool = new Pool();
  const sql = fs.readFileSync(path.join(__dirname, '..', 'src', 'db', 'schema.sql'), 'utf8');
  // pg-mem executes better statement-by-statement for multi-statement DDL.
  const client = await pool.connect();
  try {
    for (const stmt of sql.split(/;\s*\n/).map((s) => s.trim()).filter(Boolean)) {
      await client.query(stmt);
    }
  } finally {
    client.release();
  }
  return pool;
}

async function seedOrg(pool, { slug, orgName, domain, email, password, role = 'admin', planCode = 'starter' } = {}) {
  const s = slug || 'org-' + uuidv4().slice(0, 8);
  const orgId = uuidv4();
  await pool.query(`INSERT INTO orgs (id, name, slug, plan) VALUES ($1,$2,$3,$4)`,
    [orgId, orgName || s.toUpperCase(), s, 'starter']);
  await pool.query(
    `INSERT INTO plans (id, code, name, price_inr_monthly, max_users, storage_gb)
     VALUES ($1,$2,$3,99,25,10) ON CONFLICT (code) DO NOTHING`,
    [uuidv4(), planCode, planCode]);
  const plan = await pool.query('SELECT id FROM plans WHERE code=$1', [planCode]);
  await pool.query(
    `INSERT INTO subscriptions (id, org_id, plan_id, status, seats) VALUES ($1,$2,$3,'trialing',5)`,
    [uuidv4(), orgId, plan.rows[0].id]);

  const dom = domain || `${s}.example.com`;
  const domainId = uuidv4();
  await pool.query(
    `INSERT INTO domains (id, org_id, domain, verification_status, verification_code)
     VALUES ($1,$2,$3,'verified',$4)`, [domainId, orgId, dom, 'verify-' + uuidv4()]);

  const mail = email || `admin@${dom}`;
  const [localPart] = mail.split('@');
  const userId = uuidv4();
  await pool.query(
    `INSERT INTO users (id, org_id, email, password_hash, display_name, role)
     VALUES ($1,$2,$3,$4,$5,$6)`,
    [userId, orgId, mail.toLowerCase(), await bcrypt.hash(password || 'TestPass123!', 4), 'Test User', role]);
  const mailboxId = uuidv4();
  await pool.query(
    `INSERT INTO mailboxes (id, org_id, user_id, domain_id, local_part)
     VALUES ($1,$2,$3,$4,$5)`, [mailboxId, orgId, userId, domainId, localPart]);
  for (const [name, kind] of FOLDERS) {
    await pool.query(
      `INSERT INTO folders (id, org_id, mailbox_id, name, kind) VALUES ($1,$2,$3,$4,$5)`,
      [uuidv4(), orgId, mailboxId, name, kind]);
  }
  return { orgId, slug: s, domainId, domain: dom, userId, email: mail.toLowerCase(), mailboxId };
}

async function setupTestApp() {
  const pool = await createPool();
  const app = createApp({ pool });
  return { app, pool };
}

module.exports = { createPool, seedOrg, setupTestApp };
