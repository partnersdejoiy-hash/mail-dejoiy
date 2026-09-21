'use strict';
// POST /api/v1/auth/* — login, logout, me, TOTP 2FA.
const express = require('express');
const bcrypt = require('bcrypt');
const crypto = require('crypto');
const { z } = require('zod');
const { authenticator } = require('otplib');
const { v4: uuidv4 } = require('uuid');
const config = require('../config');
const { validate } = require('../middleware/validate');
const { asyncHandler, unauthorized, badRequest, notFound } = require('../middleware/errors');
const { authMiddleware, requireAuth, hashToken } = require('../middleware/auth');
const { authLimiter } = require('../middleware/rateLimit');

function routes(pool) {
  const r = express.Router();

  const loginSchema = z.object({
    email: z.string().email().max(254),
    password: z.string().min(1).max(256),
    orgSlug: z.string().min(1).max(64).optional(),
    totpCode: z.string().regex(/^\d{6}$/).optional(),
  });

  // POST /auth/login
  r.post('/login', authLimiter(), validate({ body: loginSchema }), asyncHandler(async (req, res) => {
    const { email, password, orgSlug, totpCode } = req.body;
    const clean = email.trim().toLowerCase();

    const { rows } = await pool.query(
      `SELECT u.*, o.slug AS org_slug, o.name AS org_name, o.status AS org_status
         FROM users u JOIN orgs o ON o.id = u.org_id
        WHERE u.email = $1`, [clean]
    );
    let user = null;
    if (rows.length === 1) {
      user = rows[0];
    } else if (rows.length > 1) {
      if (!orgSlug) {
        return res.status(400).json({ error: {
          code: 'org_required',
          message: 'This email exists in multiple organizations; pass orgSlug.',
          details: rows.map((x) => ({ orgSlug: x.org_slug, orgName: x.org_name })),
        }});
      }
      user = rows.find((x) => x.org_slug === orgSlug) || null;
    }
    // Constant-time-ish failure path: always run a bcrypt compare to avoid
    // user-enumeration via timing. Use a dummy hash when the user is missing.
    const hash = user ? user.password_hash : '$2b$12$...............................................';
    const ok = await bcrypt.compare(password, hash);
    if (!user || !ok) throw unauthorized('Invalid email or password');
    if (user.status !== 'active') throw unauthorized('Account is suspended');
    if (user.org_status !== 'active') throw unauthorized('Organization is suspended');

    if (user.totp_enabled) {
      if (!totpCode || !authenticator.check(totpCode, user.totp_secret_enc)) {
        return res.status(401).json({ error: { code: 'totp_required', message: 'Two-factor code required' } });
      }
    }

    const token = crypto.randomBytes(32).toString('hex');
    const sessionId = uuidv4();
    const expiresAt = new Date(Date.now() + config.sessionTtlDays * 24 * 3600 * 1000);
    await pool.query(
      `INSERT INTO api_sessions (id, org_id, user_id, token_hash, ip, user_agent, expires_at)
       VALUES ($1,$2,$3,$4,$5,$6,$7)`,
      [sessionId, user.org_id, user.id, hashToken(token), req.ip, req.headers['user-agent'] || null, expiresAt]
    );
    await pool.query(
      `INSERT INTO audit_log (id, org_id, actor_user_id, action, meta)
       VALUES ($1,$2,$3,'auth.login',$4)`,
      [uuidv4(), user.org_id, user.id, JSON.stringify({ ip: req.ip })]
    );
    res.json({ data: {
      token,
      expiresAt: expiresAt.toISOString(),
      user: publicUser(user),
      org: { id: user.org_id, name: user.org_name, slug: user.org_slug },
    }});
  }));

  const authed = [authMiddleware(pool), requireAuth];

  // GET /auth/me
  r.get('/me', ...authed, asyncHandler(async (req, res) => {
    res.json({ data: { user: {
      id: req.auth.user.id, email: req.auth.user.email,
      displayName: req.auth.user.displayName, role: req.auth.user.role,
    }, org: req.auth.org } });
  }));

  // POST /auth/logout — revokes the current session only.
  r.post('/logout', ...authed, asyncHandler(async (req, res) => {
    await pool.query('UPDATE api_sessions SET revoked_at=now() WHERE id=$1', [req.auth.sessionId]);
    res.json({ data: { ok: true } });
  }));

  // POST /auth/2fa/setup — returns a secret + otpauth URL; not enabled until verified.
  r.post('/2fa/setup', ...authed, asyncHandler(async (req, res) => {
    const secret = authenticator.generateSecret();
    // TODO(security): encrypt with KMS before storing. MVP stores the raw
    // secret; the column is named *_enc to force the issue before production.
    await pool.query('UPDATE users SET totp_secret_enc=$2 WHERE id=$1', [req.auth.user.id, secret]);
    const otpauth = authenticator.keyuri(req.auth.user.email, 'Dejoiy Mail', secret);
    res.json({ data: { secret, otpauthUrl: otpauth } });
  }));

  // POST /auth/2fa/enable { code } — verifies the code, then enables.
  r.post('/2fa/enable', ...authed, validate({ body: z.object({ code: z.string().regex(/^\d{6}$/) }) }),
    asyncHandler(async (req, res) => {
      const { rows } = await pool.query('SELECT totp_secret_enc FROM users WHERE id=$1', [req.auth.user.id]);
      const secret = rows[0] && rows[0].totp_secret_enc;
      if (!secret || !authenticator.check(req.body.code, secret)) {
        throw badRequest('Invalid verification code');
      }
      await pool.query('UPDATE users SET totp_enabled=TRUE WHERE id=$1', [req.auth.user.id]);
      res.json({ data: { totpEnabled: true } });
    }));

  // POST /auth/2fa/disable { password }
  r.post('/2fa/disable', ...authed, validate({ body: z.object({ password: z.string().min(1) }) }),
    asyncHandler(async (req, res) => {
      const { rows } = await pool.query('SELECT password_hash FROM users WHERE id=$1', [req.auth.user.id]);
      if (!rows[0] || !(await bcrypt.compare(req.body.password, rows[0].password_hash))) {
        throw unauthorized('Invalid password');
      }
      await pool.query('UPDATE users SET totp_enabled=FALSE, totp_secret_enc=NULL WHERE id=$1', [req.auth.user.id]);
      res.json({ data: { totpEnabled: false } });
    }));

  return r;
}

function publicUser(u) {
  return { id: u.id, email: u.email, displayName: u.display_name, role: u.role, totpEnabled: !!u.totp_enabled };
}

module.exports = { routes, publicUser };
