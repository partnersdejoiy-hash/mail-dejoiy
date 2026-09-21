'use strict';
// Auth flow tests: login, sessions, RBAC, 2FA.
const test = require('node:test');
const assert = require('node:assert/strict');
const request = require('supertest');
const { authenticator } = require('otplib');
const { setupTestApp, seedOrg } = require('./helpers');

test('auth: login success, /me, logout revokes session', async (t) => {
  const { app, pool } = await setupTestApp();
  t.after(() => pool.end());
  const org = await seedOrg(pool, { slug: 'acme', domain: 'acme.example.com', password: 'Secret123!' });

  const login = await request(app).post('/api/v1/auth/login')
    .send({ email: org.email, password: 'Secret123!' });
  assert.equal(login.status, 200);
  assert.ok(login.body.data.token);
  const token = login.body.data.token;

  const me = await request(app).get('/api/v1/auth/me')
    .set('Authorization', `Bearer ${token}`);
  assert.equal(me.status, 200);
  assert.equal(me.body.data.user.email, org.email);
  assert.equal(me.body.data.org.slug, 'acme');

  const logout = await request(app).post('/api/v1/auth/logout')
    .set('Authorization', `Bearer ${token}`);
  assert.equal(logout.status, 200);

  const meAfter = await request(app).get('/api/v1/auth/me')
    .set('Authorization', `Bearer ${token}`);
  assert.equal(meAfter.status, 401);
});

test('auth: wrong password and unknown email are rejected', async (t) => {
  const { app, pool } = await setupTestApp();
  t.after(() => pool.end());
  const org = await seedOrg(pool, { slug: 'acme2', password: 'Secret123!' });

  const bad = await request(app).post('/api/v1/auth/login')
    .send({ email: org.email, password: 'WrongPass!' });
  assert.equal(bad.status, 401);

  const unknown = await request(app).post('/api/v1/auth/login')
    .send({ email: 'nobody@nowhere.example', password: 'Whatever1!' });
  assert.equal(unknown.status, 401);
});

test('auth: missing/invalid token is rejected', async (t) => {
  const { app, pool } = await setupTestApp();
  t.after(() => pool.end());
  await seedOrg(pool, { slug: 'acme3' });

  assert.equal((await request(app).get('/api/v1/auth/me')).status, 401);
  assert.equal((await request(app).get('/api/v1/auth/me')
    .set('Authorization', 'Bearer deadbeef')).status, 401);
});

test('auth: multi-org email requires orgSlug', async (t) => {
  const { app, pool } = await setupTestApp();
  t.after(() => pool.end());
  await seedOrg(pool, { slug: 'org-a', domain: 'a.example.com', email: 'boss@shared.example', password: 'Secret123!' });
  await seedOrg(pool, { slug: 'org-b', domain: 'b.example.com', email: 'boss@shared.example', password: 'Other123!' });

  const ambiguous = await request(app).post('/api/v1/auth/login')
    .send({ email: 'boss@shared.example', password: 'Secret123!' });
  assert.equal(ambiguous.status, 400);
  assert.equal(ambiguous.body.error.code, 'org_required');

  const ok = await request(app).post('/api/v1/auth/login')
    .send({ email: 'boss@shared.example', password: 'Secret123!', orgSlug: 'org-a' });
  assert.equal(ok.status, 200);
  assert.equal(ok.body.data.org.slug, 'org-a');
});

test('auth: plain user cannot reach admin endpoints (RBAC)', async (t) => {
  const { app, pool } = await setupTestApp();
  t.after(() => pool.end());
  const org = await seedOrg(pool, { slug: 'acme4', role: 'user', password: 'Secret123!' });
  const login = await request(app).post('/api/v1/auth/login')
    .send({ email: org.email, password: 'Secret123!' });
  const res = await request(app).get('/api/v1/admin/users')
    .set('Authorization', `Bearer ${login.body.data.token}`);
  assert.equal(res.status, 403);
});

test('auth: TOTP 2FA setup -> enable -> enforced on login', async (t) => {
  const { app, pool } = await setupTestApp();
  t.after(() => pool.end());
  const org = await seedOrg(pool, { slug: 'acme5', password: 'Secret123!' });
  const login = await request(app).post('/api/v1/auth/login')
    .send({ email: org.email, password: 'Secret123!' });
  const token = login.body.data.token;

  const setup = await request(app).post('/api/v1/auth/2fa/setup')
    .set('Authorization', `Bearer ${token}`);
  assert.equal(setup.status, 200);
  const secret = setup.body.data.secret;
  const code = authenticator.generate(secret);

  const enable = await request(app).post('/api/v1/auth/2fa/enable')
    .set('Authorization', `Bearer ${token}`)
    .send({ code });
  assert.equal(enable.status, 200);

  // New login without code -> totp_required
  const noCode = await request(app).post('/api/v1/auth/login')
    .send({ email: org.email, password: 'Secret123!' });
  assert.equal(noCode.status, 401);
  assert.equal(noCode.body.error.code, 'totp_required');

  // With fresh code -> success
  const withCode = await request(app).post('/api/v1/auth/login')
    .send({ email: org.email, password: 'Secret123!', totpCode: authenticator.generate(secret) });
  assert.equal(withCode.status, 200);
});
