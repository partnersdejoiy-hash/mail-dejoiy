'use strict';
// /api/v1/admin/* — organization administration. Requires admin role or above.
// Every query is scoped to req.auth.org.id (multi-tenant isolation).
const express = require('express');
const bcrypt = require('bcrypt');
const { z } = require('zod');
const { v4: uuidv4 } = require('uuid');
const config = require('../config');
const { validate } = require('../middleware/validate');
const { asyncHandler, notFound, conflict, forbidden, badRequest } = require('../middleware/errors');
const { authMiddleware, requireAuth, requireRole } = require('../middleware/auth');
const { publicUser } = require('./auth');
const domainsSvc = require('../services/domains');
const billing = require('../services/billing');

const DEFAULT_FOLDERS = [
  { name: 'Inbox', kind: 'inbox', position: 0 },
  { name: 'Sent', kind: 'sent', position: 1 },
  { name: 'Drafts', kind: 'drafts', position: 2 },
  { name: 'Spam', kind: 'spam', position: 3 },
  { name: 'Trash', kind: 'trash', position: 4 },
];

async function ensureDefaultFolders(client, orgId, mailboxId) {
  for (const f of DEFAULT_FOLDERS) {
    await client.query(
      `INSERT INTO folders (id, org_id, mailbox_id, name, kind, position)
       VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT (mailbox_id, name) DO NOTHING`,
      [uuidv4(), orgId, mailboxId, f.name, f.kind, f.position]
    );
  }
}

async function audit(pool, orgId, actorId, action, targetType, targetId, meta) {
  await pool.query(
    `INSERT INTO audit_log (id, org_id, actor_user_id, action, target_type, target_id, meta)
     VALUES ($1,$2,$3,$4,$5,$6,$7)`,
    [uuidv4(), orgId, actorId, action, targetType || null, targetId || null, JSON.stringify(meta || {})]
  );
}

function routes(pool) {
  const r = express.Router();
  r.use(authMiddleware(pool), requireAuth, requireRole('admin'));

  const orgOf = (req) => req.auth.org.id;

  // ---------- users ----------
  r.get('/users', asyncHandler(async (req, res) => {
    const { rows } = await pool.query(
      `SELECT u.*, (SELECT COUNT(*) FROM mailboxes m WHERE m.user_id=u.id) AS mailboxes
         FROM users u WHERE u.org_id=$1 ORDER BY u.created_at`,
      [orgOf(req)]
    );
    res.json({ data: rows.map(publicUser) });
  }));

  const createUserSchema = z.object({
    email: z.string().email().max(254),
    displayName: z.string().min(1).max(120),
    password: z.string().min(8).max(128),
    role: z.enum(['admin', 'user']).default('user'),
    domainId: z.string().uuid().optional(), // mailbox domain; defaults to org's first domain
  });

  r.post('/users', validate({ body: createUserSchema }), asyncHandler(async (req, res) => {
    const orgId = orgOf(req);
    const { email, displayName, password, role } = req.body;
    const clean = email.trim().toLowerCase();
    const [localPart, mailDomain] = clean.split('@');
    if (!localPart || !mailDomain) throw badRequest('Invalid email address');

    // Seat enforcement: active users must not exceed subscription seats.
    const sub = await billing.getSubscription(pool, orgId);
    if (sub) {
      const { rows: c } = await pool.query(
        `SELECT COUNT(*)::int AS n FROM users WHERE org_id=$1 AND status='active'`, [orgId]);
      if (c[0].n >= sub.seats) {
        throw forbidden(`Seat limit reached (${sub.seats} seats). Increase seats in billing first.`);
      }
    }

    let domainRow;
    if (req.body.domainId) {
      const d = await pool.query('SELECT * FROM domains WHERE id=$1 AND org_id=$2', [req.body.domainId, orgId]);
      if (!d.rows[0]) throw notFound('Domain not found in this organization');
      domainRow = d.rows[0];
    } else {
      const d = await pool.query('SELECT * FROM domains WHERE org_id=$1 ORDER BY created_at LIMIT 1', [orgId]);
      if (!d.rows[0]) throw badRequest('Organization has no domains yet — add one first');
      domainRow = d.rows[0];
    }
    if (domainRow.domain !== mailDomain) {
      throw badRequest(`Email domain must be ${domainRow.domain} (selected mailbox domain)`);
    }

    const exists = await pool.query('SELECT 1 FROM users WHERE org_id=$1 AND email=$2', [orgId, clean]);
    if (exists.rows[0]) throw conflict('A user with this email already exists');

    const passwordHash = await bcrypt.hash(password, config.bcryptRounds);
    const userId = uuidv4();
    const mailboxId = uuidv4();
    const client = await pool.connect();
    try {
      await client.query('BEGIN');
      await client.query(
        `INSERT INTO users (id, org_id, email, password_hash, display_name, role)
         VALUES ($1,$2,$3,$4,$5,$6)`,
        [userId, orgId, clean, passwordHash, displayName, role]
      );
      await client.query(
        `INSERT INTO mailboxes (id, org_id, user_id, domain_id, local_part)
         VALUES ($1,$2,$3,$4,$5)`,
        [mailboxId, orgId, userId, domainRow.id, localPart]
      );
      await ensureDefaultFolders(client, orgId, mailboxId);
      await client.query('COMMIT');
    } catch (e) {
      await client.query('ROLLBACK');
      throw e;
    } finally {
      client.release();
    }
    await audit(pool, orgId, req.auth.user.id, 'admin.user.create', 'user', userId, { email: clean, role });
    const { rows } = await pool.query('SELECT * FROM users WHERE id=$1', [userId]);
    res.status(201).json({ data: publicUser(rows[0]) });
  }));

  const patchUserSchema = z.object({
    displayName: z.string().min(1).max(120).optional(),
    role: z.enum(['super_admin', 'admin', 'user']).optional(),
    status: z.enum(['active', 'suspended']).optional(),
  });

  r.patch('/users/:id', validate({ body: patchUserSchema }), asyncHandler(async (req, res) => {
    const orgId = orgOf(req);
    const { rows } = await pool.query('SELECT * FROM users WHERE id=$1 AND org_id=$2', [req.params.id, orgId]);
    const target = rows[0];
    if (!target) throw notFound('User not found');
    if (target.id === req.auth.user.id && (req.body.role || req.body.status)) {
      throw forbidden('You cannot change your own role or status');
    }
    if (req.body.role === 'super_admin' && req.auth.user.role !== 'super_admin') {
      throw forbidden('Only a super_admin can grant super_admin');
    }
    const sets = [];
    const vals = [];
    let i = 1;
    for (const k of ['display_name', 'role', 'status']) {
      const bodyKey = { display_name: 'displayName', role: 'role', status: 'status' }[k];
      if (req.body[bodyKey] !== undefined) { sets.push(`${k}=$${i++}`); vals.push(req.body[bodyKey]); }
    }
    if (sets.length === 0) throw badRequest('Nothing to update');
    sets.push(`updated_at=now()`);
    vals.push(target.id);
    const upd = await pool.query(`UPDATE users SET ${sets.join(', ')} WHERE id=$${i} RETURNING *`, vals);
    await audit(pool, orgId, req.auth.user.id, 'admin.user.update', 'user', target.id, req.body);
    res.json({ data: publicUser(upd.rows[0]) });
  }));

  // DELETE suspends (soft) — mailbox data is retained for audit/recovery.
  r.delete('/users/:id', asyncHandler(async (req, res) => {
    const orgId = orgOf(req);
    if (req.params.id === req.auth.user.id) throw forbidden('You cannot suspend yourself');
    const { rows } = await pool.query(
      `UPDATE users SET status='suspended', updated_at=now()
        WHERE id=$1 AND org_id=$2 RETURNING *`, [req.params.id, orgId]);
    if (!rows[0]) throw notFound('User not found');
    await pool.query('UPDATE api_sessions SET revoked_at=now() WHERE user_id=$1 AND revoked_at IS NULL', [req.params.id]);
    await audit(pool, orgId, req.auth.user.id, 'admin.user.suspend', 'user', req.params.id, {});
    res.json({ data: publicUser(rows[0]) });
  }));

  // ---------- domains ----------
  r.get('/domains', asyncHandler(async (req, res) => {
    const { rows } = await pool.query(
      'SELECT * FROM domains WHERE org_id=$1 ORDER BY created_at', [orgOf(req)]);
    res.json({ data: rows });
  }));

  r.post('/domains', validate({ body: z.object({ domain: z.string().min(3).max(253) }) }),
    asyncHandler(async (req, res) => {
      const { domain, created } = await domainsSvc.createDomain(pool, orgOf(req), req.body.domain);
      await audit(pool, orgOf(req), req.auth.user.id, 'admin.domain.add', 'domain', domain.id, { domain: domain.domain });
      res.status(created ? 201 : 200).json({
        data: {
          ...domain,
          requiredRecords: domainsSvc.requiredRecords(domain.domain),
        },
      });
    }));

  r.get('/domains/:id', asyncHandler(async (req, res) => {
    const { rows } = await pool.query('SELECT * FROM domains WHERE id=$1 AND org_id=$2', [req.params.id, orgOf(req)]);
    if (!rows[0]) throw notFound('Domain not found');
    res.json({ data: { ...rows[0], requiredRecords: domainsSvc.requiredRecords(rows[0].domain) } });
  }));

  // POST /domains/:id/check — runs the (stub) DNS check and records the attempt.
  r.post('/domains/:id/check', asyncHandler(async (req, res) => {
    const { rows } = await pool.query('SELECT * FROM domains WHERE id=$1 AND org_id=$2', [req.params.id, orgOf(req)]);
    if (!rows[0]) throw notFound('Domain not found');
    const report = await domainsSvc.checkDomain(rows[0].domain);
    await pool.query('UPDATE domains SET last_checked_at=now() WHERE id=$1', [req.params.id]);
    await audit(pool, orgOf(req), req.auth.user.id, 'admin.domain.check', 'domain', req.params.id, { stub: true });
    res.json({ data: report });
  }));

  // POST /domains/:id/verify — marks verified after out-of-band confirmation.
  r.post('/domains/:id/verify', asyncHandler(async (req, res) => {
    const { rows } = await pool.query(
      `UPDATE domains SET verification_status='verified' WHERE id=$1 AND org_id=$2 RETURNING *`,
      [req.params.id, orgOf(req)]);
    if (!rows[0]) throw notFound('Domain not found');
    await audit(pool, orgOf(req), req.auth.user.id, 'admin.domain.verify', 'domain', req.params.id, {});
    res.json({ data: rows[0] });
  }));

  // ---------- billing ----------
  r.get('/billing', asyncHandler(async (req, res) => {
    const sub = await billing.getSubscription(pool, orgOf(req));
    if (!sub) return res.json({ data: null });
    const { rows: c } = await pool.query(
      `SELECT COUNT(*)::int AS active_users FROM users WHERE org_id=$1 AND status='active'`, [orgOf(req)]);
    res.json({ data: { ...sub, activeUsers: c[0].active_users, razorpayConnected: false } });
  }));

  r.post('/billing/seats', validate({ body: z.object({ seats: z.number().int() }) }),
    asyncHandler(async (req, res) => {
      const sub = await billing.setSeats(pool, orgOf(req), req.body.seats, req.auth.user.id);
      await audit(pool, orgOf(req), req.auth.user.id, 'admin.billing.seats', 'subscription', sub.id,
        { seats: req.body.seats, razorpaySynced: false });
      // NOTE: Razorpay sync is a stub — see services/billing.js.
      res.json({ data: { ...sub, razorpayConnected: false } });
    }));

  r.post('/billing/subscribe', validate({ body: z.object({ planCode: z.string() }) }),
    asyncHandler(async (req, res) => {
      await billing.createRazorpaySubscription(pool, orgOf(req), req.body.planCode);
      res.json({ data: { ok: true } });
    }));

  return r;
}

module.exports = { routes, ensureDefaultFolders };
