'use strict';
// /api/v1/settings/* — self-service settings for the authenticated user.
const express = require('express');
const bcrypt = require('bcrypt');
const { z } = require('zod');
const { validate } = require('../middleware/validate');
const { asyncHandler, unauthorized } = require('../middleware/errors');
const { authMiddleware, requireAuth } = require('../middleware/auth');
const config = require('../config');

function routes(pool) {
  const r = express.Router();
  r.use(authMiddleware(pool), requireAuth);

  // GET /settings/profile
  r.get('/profile', asyncHandler(async (req, res) => {
    const { rows } = await pool.query(
      `SELECT u.id, u.email, u.display_name, u.role, u.status, u.totp_enabled,
              m.local_part, d.domain, m.quota_bytes, m.used_bytes,
              m.vacation_enabled, m.vacation_subject
         FROM users u
         LEFT JOIN mailboxes m ON m.user_id=u.id
         LEFT JOIN domains d ON d.id=m.domain_id
        WHERE u.id=$1`, [req.auth.user.id]);
    const u = rows[0];
    res.json({ data: {
      id: u.id, email: u.email, displayName: u.display_name, role: u.role,
      totpEnabled: u.totp_enabled,
      mailbox: u.local_part ? {
        address: `${u.local_part}@${u.domain}`,
        quotaBytes: Number(u.quota_bytes), usedBytes: Number(u.used_bytes),
        vacationEnabled: u.vacation_enabled, vacationSubject: u.vacation_subject,
      } : null,
    }});
  }));

  // PATCH /settings/profile { displayName }
  r.patch('/profile', validate({ body: z.object({ displayName: z.string().min(1).max(120) }) }),
    asyncHandler(async (req, res) => {
      await pool.query('UPDATE users SET display_name=$2, updated_at=now() WHERE id=$1',
        [req.auth.user.id, req.body.displayName]);
      res.json({ data: { ok: true } });
    }));

  // POST /settings/password { currentPassword, newPassword }
  r.post('/password', validate({ body: z.object({
    currentPassword: z.string().min(1),
    newPassword: z.string().min(8).max(128),
  }) }), asyncHandler(async (req, res) => {
    const { rows } = await pool.query('SELECT password_hash FROM users WHERE id=$1', [req.auth.user.id]);
    if (!(await bcrypt.compare(req.body.currentPassword, rows[0].password_hash))) {
      throw unauthorized('Current password is incorrect');
    }
    const hash = await bcrypt.hash(req.body.newPassword, config.bcryptRounds);
    await pool.query('UPDATE users SET password_hash=$2, updated_at=now() WHERE id=$1', [req.auth.user.id, hash]);
    // Revoke all other sessions on password change.
    const header = req.headers.authorization || '';
    const current = header.replace(/^Bearer\s+/i, '').trim();
    const { hashToken } = require('../middleware/auth');
    await pool.query(
      `UPDATE api_sessions SET revoked_at=now()
        WHERE user_id=$1 AND revoked_at IS NULL AND token_hash <> $2`,
      [req.auth.user.id, hashToken(current)]);
    res.json({ data: { ok: true } });
  }));

  // PATCH /settings/vacation { enabled, subject?, body? }
  r.patch('/vacation', validate({ body: z.object({
    enabled: z.boolean(),
    subject: z.string().max(200).optional(),
    body: z.string().max(5000).optional(),
  }) }), asyncHandler(async (req, res) => {
    const { rowCount } = await pool.query(
      `UPDATE mailboxes SET vacation_enabled=$2, vacation_subject=$3, vacation_body=$4
        WHERE user_id=$1`,
      [req.auth.user.id, req.body.enabled, req.body.subject || null, req.body.body || null]);
    if (!rowCount) throw unauthorized('No mailbox for this user');
    res.json({ data: { ok: true } });
  }));

  return r;
}

module.exports = { routes };
