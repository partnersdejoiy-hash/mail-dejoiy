'use strict';
// Mail + admin endpoint tests: folders, drafts, send, flags, trash, filters,
// tenant isolation, seat enforcement.
const test = require('node:test');
const assert = require('node:assert/strict');
const request = require('supertest');
const { setupTestApp, seedOrg } = require('./helpers');

async function authed(t, app, pool, overrides = {}) {
  const org = await seedOrg(pool, { slug: 'mail-' + Math.random().toString(36).slice(2, 8), ...overrides });
  const login = await request(app).post('/api/v1/auth/login')
    .send({ email: org.email, password: overrides.password || 'TestPass123!' });
  assert.equal(login.status, 200);
  const auth = (req) => req.set('Authorization', `Bearer ${login.body.data.token}`);
  t.after(() => pool.end());
  return { org, auth };
}

test('mail: default folders exist', async (t) => {
  const { app, pool } = await setupTestApp();
  const { auth } = await authed(t, app, pool);
  const res = await auth(request(app).get('/api/v1/mail/folders'));
  assert.equal(res.status, 200);
  const kinds = res.body.data.map((f) => f.kind).sort();
  assert.deepEqual(kinds, ['drafts', 'inbox', 'sent', 'spam', 'trash']);
});

test('mail: draft -> send -> appears in Sent, outbox queued', async (t) => {
  const { app, pool } = await setupTestApp();
  const { auth } = await authed(t, app, pool);

  const draft = await auth(request(app).post('/api/v1/mail/drafts')).send({
    to: ['friend@example.com'], subject: 'Hello', bodyText: 'Hi there',
  });
  assert.equal(draft.status, 201);
  const draftId = draft.body.data.id;

  const drafts = await auth(request(app).get('/api/v1/mail/messages?folder=drafts'));
  assert.equal(drafts.body.pagination.total, 1);

  const sent = await auth(request(app).post('/api/v1/mail/send')).send({ draftId });
  assert.equal(sent.status, 202);
  assert.equal(sent.body.data.outbox.status, 'queued');
  assert.equal(sent.body.data.outbox.delivered, false); // stub: never claims delivery

  const inSent = await auth(request(app).get('/api/v1/mail/messages?folder=sent'));
  assert.equal(inSent.body.pagination.total, 1);
  assert.equal(inSent.body.data[0].subject, 'Hello');

  const outbox = await pool.query(`SELECT status FROM outbox WHERE message_id=$1`, [draftId]);
  assert.equal(outbox.rows[0].status, 'queued');
});

test('mail: read/star/move/delete lifecycle', async (t) => {
  const { app, pool } = await setupTestApp();
  const { auth } = await authed(t, app, pool);

  const created = await auth(request(app).post('/api/v1/mail/drafts')).send({
    to: ['a@example.com'], subject: 'Lifecycle', bodyText: 'body',
  });
  const id = created.body.data.id;

  const starred = await auth(request(app).patch(`/api/v1/mail/messages/${id}`)).send({ isStarred: true, isRead: true });
  assert.equal(starred.status, 200);
  assert.equal(starred.body.data.isStarred, true);

  const starredList = await auth(request(app).get('/api/v1/mail/messages?folder=drafts&starred=true'));
  assert.equal(starredList.body.pagination.total, 1);

  const del1 = await auth(request(app).delete(`/api/v1/mail/messages/${id}`));
  assert.equal(del1.body.data.deleted, 'moved_to_trash');
  const inTrash = await auth(request(app).get('/api/v1/mail/messages?folder=trash'));
  assert.equal(inTrash.body.pagination.total, 1);

  const del2 = await auth(request(app).delete(`/api/v1/mail/messages/${id}`));
  assert.equal(del2.body.data.deleted, 'permanent');
  assert.equal((await auth(request(app).get(`/api/v1/mail/messages/${id}`))).status, 404);
});

test('mail: validation rejects bad input', async (t) => {
  const { app, pool } = await setupTestApp();
  const { auth } = await authed(t, app, pool);
  const res = await auth(request(app).post('/api/v1/mail/send')).send({
    to: ['not-an-email'], subject: 'x',
  });
  assert.equal(res.status, 400);
  assert.equal(res.body.error.code, 'bad_request');
});

test('mail: filters CRUD', async (t) => {
  const { app, pool } = await setupTestApp();
  const { auth } = await authed(t, app, pool);
  const created = await auth(request(app).post('/api/v1/mail/filters')).send({
    name: 'Star boss mail',
    conditions: [{ field: 'from', op: 'contains', value: 'boss@' }],
    actions: [{ type: 'star' }],
  });
  assert.equal(created.status, 201);
  const list = await auth(request(app).get('/api/v1/mail/filters'));
  assert.equal(list.body.data.length, 1);
  const del = await auth(request(app).delete(`/api/v1/mail/filters/${created.body.data.id}`));
  assert.equal(del.status, 200);
});

test('mail: tenant isolation — org B cannot touch org A messages', async (t) => {
  const { app, pool } = await setupTestApp();
  t.after(() => pool.end());
  const a = await seedOrg(pool, { slug: 'iso-a', password: 'TestPass123!' });
  const b = await seedOrg(pool, { slug: 'iso-b', password: 'TestPass123!' });
  const loginA = await request(app).post('/api/v1/auth/login').send({ email: a.email, password: 'TestPass123!' });
  const loginB = await request(app).post('/api/v1/auth/login').send({ email: b.email, password: 'TestPass123!' });

  const draft = await request(app).post('/api/v1/mail/drafts')
    .set('Authorization', `Bearer ${loginA.body.data.token}`)
    .send({ to: ['x@example.com'], subject: 'secret', bodyText: 's3cret' });

  const snooped = await request(app).get(`/api/v1/mail/messages/${draft.body.data.id}`)
    .set('Authorization', `Bearer ${loginB.body.data.token}`);
  assert.equal(snooped.status, 404);

  const moved = await request(app).patch(`/api/v1/mail/messages/${draft.body.data.id}`)
    .set('Authorization', `Bearer ${loginB.body.data.token}`)
    .send({ isRead: true });
  assert.equal(moved.status, 404);
});

test('admin: create user provisions mailbox + folders; seat limit enforced', async (t) => {
  const { app, pool } = await setupTestApp();
  const { org, auth } = await authed(t, app, pool, { slug: 'adm1' });

  // subscription has 5 seats; 1 used (the admin). Fill to the cap.
  for (let i = 0; i < 4; i++) {
    const r = await auth(request(app).post('/api/v1/admin/users')).send({
      email: `u${i}@${org.domain}`, displayName: `U ${i}`, password: 'UserPass123!',
    });
    assert.equal(r.status, 201, JSON.stringify(r.body));
  }
  const over = await auth(request(app).post('/api/v1/admin/users')).send({
    email: `extra@${org.domain}`, displayName: 'Extra', password: 'UserPass123!',
  });
  assert.equal(over.status, 403);

  // New user can log in and has default folders.
  const login = await request(app).post('/api/v1/auth/login')
    .send({ email: `u0@${org.domain}`, password: 'UserPass123!' });
  assert.equal(login.status, 200);
  const folders = await request(app).get('/api/v1/mail/folders')
    .set('Authorization', `Bearer ${login.body.data.token}`);
  assert.equal(folders.body.data.length, 5);
});

test('admin: domain add returns DNS records; billing seats update', async (t) => {
  const { app, pool } = await setupTestApp();
  const { auth } = await authed(t, app, pool, { slug: 'adm2' });

  const added = await auth(request(app).post('/api/v1/admin/domains')).send({ domain: 'ClientCo.com' });
  assert.equal(added.status, 201);
  assert.equal(added.body.data.domain, 'clientco.com'); // normalized
  assert.ok(Array.isArray(added.body.data.requiredRecords));
  assert.ok(added.body.data.requiredRecords.some((r) => r.type === 'MX'));
  assert.ok(added.body.data.requiredRecords.some((r) => r.host.includes('_domainkey')));

  const billing = await auth(request(app).get('/api/v1/admin/billing'));
  assert.equal(billing.status, 200);
  assert.equal(billing.body.data.razorpayConnected, false); // stub honesty

  const seats = await auth(request(app).post('/api/v1/admin/billing/seats')).send({ seats: 10 });
  assert.equal(seats.status, 200);
  assert.equal(seats.body.data.seats, 10);
  assert.equal(seats.body.data.razorpaySynced, false);
});
