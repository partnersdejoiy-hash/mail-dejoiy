'use strict';
// Session auth: Bearer token -> api_sessions (token stored as SHA-256 hash).
// Attaches req.auth = { user, org, session }. RBAC via requireRole().
const crypto = require('crypto');
const { unauthorized, forbidden } = require('./errors');

const ROLE_RANK = { user: 1, admin: 2, super_admin: 3 };

function hashToken(token) {
  return crypto.createHash('sha256').update(token).digest('hex');
}

function authMiddleware(pool) {
  return async (req, _res, next) => {
    const header = req.headers.authorization || '';
    const match = header.match(/^Bearer\s+(.+)$/i);
    if (!match) return next(unauthorized());

    const tokenHash = hashToken(match[1].trim());
    const { rows } = await pool.query(
      `SELECT s.id AS session_id, s.expires_at, s.revoked_at,
              u.id AS user_id, u.org_id, u.email, u.display_name, u.role, u.status AS user_status,
              o.id AS org_id2, o.name AS org_name, o.slug AS org_slug, o.status AS org_status
         FROM api_sessions s
         JOIN users u ON u.id = s.user_id
         JOIN orgs o ON o.id = s.org_id
        WHERE s.token_hash = $1`,
      [tokenHash]
    );
    const row = rows[0];
    if (!row || row.revoked_at || new Date(row.expires_at) < new Date()) {
      return next(unauthorized('Session expired or invalid'));
    }
    if (row.user_status !== 'active' || row.org_status !== 'active') {
      return next(forbidden('Account or organization is suspended'));
    }
    req.auth = {
      sessionId: row.session_id,
      user: {
        id: row.user_id, orgId: row.org_id, email: row.email,
        displayName: row.display_name, role: row.role,
      },
      org: { id: row.org_id, name: row.org_name, slug: row.org_slug },
    };
    return next();
  };
}

function requireAuth(req, _res, next) {
  if (!req.auth) return next(unauthorized());
  return next();
}

// requireRole('admin') allows admin AND super_admin. Roles are hierarchical.
function requireRole(minRole) {
  const minRank = ROLE_RANK[minRole];
  if (!minRank) throw new Error(`Unknown role: ${minRole}`);
  return (req, _res, next) => {
    if (!req.auth) return next(unauthorized());
    const rank = ROLE_RANK[req.auth.user.role] || 0;
    if (rank < minRank) return next(forbidden());
    return next();
  };
}

module.exports = { authMiddleware, requireAuth, requireRole, hashToken, ROLE_RANK };
