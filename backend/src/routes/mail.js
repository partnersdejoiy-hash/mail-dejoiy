'use strict';
// /api/v1/mail/* — mailbox access for the authenticated user.
// All queries scoped to the user's own mailbox (org isolation included).
const express = require('express');
const { z } = require('zod');
const { v4: uuidv4 } = require('uuid');
const { validate } = require('../middleware/validate');
const { asyncHandler, notFound, badRequest, forbidden } = require('../middleware/errors');
const { authMiddleware, requireAuth } = require('../middleware/auth');
const mailer = require('../services/mailer');

const SYSTEM_KINDS = ['inbox', 'sent', 'drafts', 'spam', 'trash'];

function snippetOf(text, n = 140) {
  const s = (text || '').replace(/\s+/g, ' ').trim();
  return s.length > n ? s.slice(0, n) + '…' : s;
}

function routes(pool) {
  const r = express.Router();
  r.use(authMiddleware(pool), requireAuth);

  async function mailboxOf(req) {
    const { rows } = await pool.query(
      `SELECT m.*, d.domain FROM mailboxes m JOIN domains d ON d.id=m.domain_id
        WHERE m.user_id=$1 AND m.org_id=$2`,
      [req.auth.user.id, req.auth.org.id]
    );
    if (!rows[0]) throw notFound('No mailbox for this user');
    return rows[0];
  }

  async function folderByIdOrKind(req, mailbox, ref) {
    // ref may be a folder id (uuid-ish) or a system kind name.
    let row;
    if (SYSTEM_KINDS.includes(ref)) {
      const { rows } = await pool.query(
        'SELECT * FROM folders WHERE mailbox_id=$1 AND kind=$2', [mailbox.id, ref]);
      row = rows[0];
    } else {
      const { rows } = await pool.query(
        'SELECT * FROM folders WHERE id=$1 AND mailbox_id=$2', [ref, mailbox.id]);
      row = rows[0];
    }
    if (!row) throw notFound('Folder not found');
    return row;
  }

  const publicMessage = (m) => ({
    id: m.id, threadId: m.thread_id, from: m.from_addr,
    to: m.to_addrs, cc: m.cc_addrs, subject: m.subject, snippet: m.snippet,
    isRead: m.is_read, isStarred: m.is_starred, hasAttachments: m.has_attachments,
    folderId: m.folder_id, internalDate: m.internal_date, sizeBytes: m.size_bytes,
  });

  // ---------- folders ----------
  r.get('/folders', asyncHandler(async (req, res) => {
    const mb = await mailboxOf(req);
    const { rows } = await pool.query(
      `SELECT id, org_id, mailbox_id, name, kind, parent_id, position, created_at
         FROM folders WHERE mailbox_id=$1 ORDER BY position, name`, [mb.id]);
    // Unread counts in a separate grouped query (keeps this portable and fast).
    const { rows: counts } = await pool.query(
      `SELECT folder_id, COUNT(*)::int AS unread FROM messages
        WHERE mailbox_id=$1 AND is_read=FALSE GROUP BY folder_id`, [mb.id]);
    const unreadBy = Object.fromEntries(counts.map((c) => [c.folder_id, c.unread]));
    res.json({ data: rows.map((f) => ({ ...f, mailboxId: f.mailbox_id, unread: unreadBy[f.id] || 0 })) });
  }));

  r.post('/folders', validate({ body: z.object({
    name: z.string().min(1).max(80),
    parentId: z.string().uuid().optional(),
  }) }), asyncHandler(async (req, res) => {
    const mb = await mailboxOf(req);
    if (req.body.parentId) {
      const p = await pool.query('SELECT id FROM folders WHERE id=$1 AND mailbox_id=$2',
        [req.body.parentId, mb.id]);
      if (!p.rows[0]) throw notFound('Parent folder not found');
    }
    const id = uuidv4();
    try {
      const { rows } = await pool.query(
        `INSERT INTO folders (id, org_id, mailbox_id, name, kind, parent_id, position)
         VALUES ($1,$2,$3,$4,'custom',$5,(SELECT COALESCE(MAX(position),0)+1 FROM folders WHERE mailbox_id=$2))
         RETURNING *`,
        [id, req.auth.org.id, mb.id, req.body.name.trim(), req.body.parentId || null]
      );
      res.status(201).json({ data: rows[0] });
    } catch (e) {
      if (e.code === '23505') throw badRequest('A folder with this name already exists');
      throw e;
    }
  }));

  r.patch('/folders/:id', validate({ body: z.object({ name: z.string().min(1).max(80) }) }),
    asyncHandler(async (req, res) => {
      const mb = await mailboxOf(req);
      const { rows } = await pool.query(
        `UPDATE folders SET name=$3 WHERE id=$1 AND mailbox_id=$2 AND kind='custom' RETURNING *`,
        [req.params.id, mb.id, req.body.name.trim()]);
      if (!rows[0]) throw notFound('Custom folder not found');
      res.json({ data: rows[0] });
    }));

  r.delete('/folders/:id', asyncHandler(async (req, res) => {
    const mb = await mailboxOf(req);
    const f = await pool.query(
      `SELECT * FROM folders WHERE id=$1 AND mailbox_id=$2 AND kind='custom'`, [req.params.id, mb.id]);
    if (!f.rows[0]) throw notFound('Custom folder not found');
    const { rows: c } = await pool.query('SELECT COUNT(*)::int AS n FROM messages WHERE folder_id=$1', [req.params.id]);
    if (c[0].n > 0) throw badRequest('Folder is not empty — move or delete its messages first');
    await pool.query('DELETE FROM folders WHERE id=$1', [req.params.id]);
    res.json({ data: { ok: true } });
  }));

  // ---------- messages ----------
  const listQuery = z.object({
    folder: z.string().default('inbox'),
    page: z.coerce.number().int().min(1).default(1),
    limit: z.coerce.number().int().min(1).max(100).default(25),
    q: z.string().max(200).optional(),
    unread: z.coerce.boolean().optional(),
    starred: z.coerce.boolean().optional(),
  });

  r.get('/messages', validate({ query: listQuery }), asyncHandler(async (req, res) => {
    const mb = await mailboxOf(req);
    const folder = await folderByIdOrKind(req, mb, req.query.folder);
    const { page, limit, q, unread, starred } = req.query;
    const conds = ['m.mailbox_id=$1', 'm.folder_id=$2'];
    const vals = [mb.id, folder.id];
    let i = 3;
    if (unread) { conds.push(`m.is_read=FALSE`); }
    if (starred) { conds.push(`m.is_starred=TRUE`); }
    if (q) { conds.push(`(m.subject ILIKE $${i} OR m.from_addr ILIKE $${i} OR m.snippet ILIKE $${i})`); vals.push(`%${q}%`); i++; }
    const where = 'WHERE ' + conds.join(' AND ');
    const total = (await pool.query(`SELECT COUNT(*)::int AS n FROM messages m ${where}`, vals)).rows[0].n;
    const { rows } = await pool.query(
      `SELECT m.* FROM messages m ${where} ORDER BY m.internal_date DESC LIMIT $${i} OFFSET $${i + 1}`,
      [...vals, limit, (page - 1) * limit]
    );
    res.json({ data: rows.map(publicMessage), pagination: { page, limit, total } });
  }));

  r.get('/messages/:id', asyncHandler(async (req, res) => {
    const mb = await mailboxOf(req);
    const { rows } = await pool.query(
      'SELECT * FROM messages WHERE id=$1 AND mailbox_id=$2', [req.params.id, mb.id]);
    if (!rows[0]) throw notFound('Message not found');
    const atts = await pool.query(
      'SELECT id, filename, content_type, size_bytes FROM attachments WHERE message_id=$1',
      [req.params.id]);
    res.json({ data: { ...publicMessage(rows[0]), bodyText: rows[0].body_text, bodyHtml: rows[0].body_html, attachments: atts.rows } });
  }));

  r.patch('/messages/:id', validate({ body: z.object({
    isRead: z.boolean().optional(),
    isStarred: z.boolean().optional(),
    folderId: z.string().optional(),
  }) }), asyncHandler(async (req, res) => {
    const mb = await mailboxOf(req);
    const { rows } = await pool.query(
      'SELECT * FROM messages WHERE id=$1 AND mailbox_id=$2', [req.params.id, mb.id]);
    if (!rows[0]) throw notFound('Message not found');
    const sets = []; const vals = []; let i = 1;
    if (req.body.isRead !== undefined) { sets.push(`is_read=$${i++}`); vals.push(req.body.isRead); }
    if (req.body.isStarred !== undefined) { sets.push(`is_starred=$${i++}`); vals.push(req.body.isStarred); }
    if (req.body.folderId !== undefined) {
      const f = await folderByIdOrKind(req, mb, req.body.folderId);
      sets.push(`folder_id=$${i++}`); vals.push(f.id);
    }
    if (!sets.length) throw badRequest('Nothing to update');
    vals.push(req.params.id);
    const upd = await pool.query(`UPDATE messages SET ${sets.join(', ')} WHERE id=$${i} RETURNING *`, vals);
    res.json({ data: publicMessage(upd.rows[0]) });
  }));

  // DELETE: first delete moves to Trash; deleting from Trash purges permanently.
  r.delete('/messages/:id', asyncHandler(async (req, res) => {
    const mb = await mailboxOf(req);
    const { rows } = await pool.query(
      `SELECT m.*, f.kind FROM messages m JOIN folders f ON f.id=m.folder_id
        WHERE m.id=$1 AND m.mailbox_id=$2`, [req.params.id, mb.id]);
    if (!rows[0]) throw notFound('Message not found');
    if (rows[0].kind === 'trash') {
      await pool.query('DELETE FROM messages WHERE id=$1', [req.params.id]);
      return res.json({ data: { deleted: 'permanent' } });
    }
    const trash = await folderByIdOrKind(req, mb, 'trash');
    await pool.query('UPDATE messages SET folder_id=$2 WHERE id=$1', [req.params.id, trash.id]);
    res.json({ data: { deleted: 'moved_to_trash' } });
  }));

  // ---------- drafts & send ----------
  const draftSchema = z.object({
    to: z.array(z.string().email()).min(1).max(50),
    cc: z.array(z.string().email()).max(50).default([]),
    bcc: z.array(z.string().email()).max(50).default([]),
    subject: z.string().max(500).default(''),
    bodyText: z.string().max(1000000).default(''),
    bodyHtml: z.string().max(2000000).default(''),
  });

  async function saveDraft(pool, mb, orgId, userEmail, body, draftId) {
    const folder = await pool.query(
      `SELECT * FROM folders WHERE mailbox_id=$1 AND kind='drafts'`, [mb.id]);
    const drafts = folder.rows[0];
    if (!drafts) throw badRequest('Drafts folder missing');
    const text = body.bodyText || '';
    const data = {
      id: draftId || uuidv4(), org_id: orgId, mailbox_id: mb.id, folder_id: drafts.id,
      from_addr: userEmail, to_addrs: JSON.stringify(body.to), cc_addrs: JSON.stringify(body.cc || []),
      bcc_addrs: JSON.stringify(body.bcc || []), subject: body.subject || '',
      snippet: snippetOf(text), body_text: text, body_html: body.bodyHtml || '',
      size_bytes: Buffer.byteLength(text + (body.bodyHtml || ''), 'utf8'),
    };
    if (draftId) {
      const sets = Object.keys(data).filter((k) => !['id', 'org_id', 'mailbox_id'].includes(k));
      const vals = sets.map((k) => data[k]);
      vals.push(draftId);
      const { rows } = await pool.query(
        `UPDATE messages SET ${sets.map((k, idx) => `${k}=$${idx + 1}`).join(', ')}
          WHERE id=$${sets.length + 1} AND mailbox_id=$${sets.length + 2} RETURNING *`,
        [...vals, mb.id]
      );
      if (!rows[0]) throw notFound('Draft not found');
      return rows[0];
    }
    const cols = Object.keys(data);
    const { rows } = await pool.query(
      `INSERT INTO messages (${cols.join(', ')}) VALUES (${cols.map((_, idx) => `$${idx + 1}`).join(', ')}) RETURNING *`,
      cols.map((k) => data[k])
    );
    return rows[0];
  }

  r.post('/drafts', validate({ body: draftSchema }), asyncHandler(async (req, res) => {
    const mb = await mailboxOf(req);
    const userEmail = `${mb.local_part}@${mb.domain}`;
    const draft = await saveDraft(pool, mb, req.auth.org.id, userEmail, req.body, null);
    res.status(201).json({ data: publicMessage(draft) });
  }));

  r.patch('/drafts/:id', validate({ body: draftSchema.partial() }), asyncHandler(async (req, res) => {
    const mb = await mailboxOf(req);
    const userEmail = `${mb.local_part}@${mb.domain}`;
    const draft = await saveDraft(pool, mb, req.auth.org.id, userEmail, { to: req.body.to, ...req.body }, req.params.id);
    res.json({ data: publicMessage(draft) });
  }));

  // POST /send — accepts either { draftId } or a full message body.
  r.post('/send', validate({ body: z.union([
    z.object({ draftId: z.string().uuid() }),
    draftSchema,
  ]) }), asyncHandler(async (req, res) => {
    const mb = await mailboxOf(req);
    const userEmail = `${mb.local_part}@${mb.domain}`;
    const sent = await pool.query(`SELECT * FROM folders WHERE mailbox_id=$1 AND kind='sent'`, [mb.id]);
    if (!sent.rows[0]) throw badRequest('Sent folder missing');

    let msg;
    if (req.body.draftId) {
      const { rows } = await pool.query(
        'SELECT * FROM messages WHERE id=$1 AND mailbox_id=$2', [req.body.draftId, mb.id]);
      if (!rows[0]) throw notFound('Draft not found');
      const upd = await pool.query(
        `UPDATE messages SET folder_id=$2, internal_date=now() WHERE id=$1 RETURNING *`,
        [req.body.draftId, sent.rows[0].id]);
      msg = upd.rows[0];
    } else {
      const draft = await saveDraft(pool, mb, req.auth.org.id, userEmail, req.body, null);
      const upd = await pool.query(
        `UPDATE messages SET folder_id=$2, internal_date=now() WHERE id=$1 RETURNING *`,
        [draft.id, sent.rows[0].id]);
      msg = upd.rows[0];
    }

    // Quota guard: block sending when the mailbox is over quota.
    if (mb.used_bytes >= mb.quota_bytes) {
      throw forbidden('Mailbox quota exceeded');
    }

    const result = await mailer.enqueue(pool, {
      orgId: req.auth.org.id, mailboxId: mb.id, messageId: msg.id,
    });
    res.status(202).json({ data: { message: publicMessage(msg), outbox: result } });
  }));

  // ---------- filters ----------
  const filterSchema = z.object({
    name: z.string().min(1).max(120),
    conditions: z.array(z.object({
      field: z.enum(['from', 'to', 'subject', 'body']),
      op: z.enum(['contains', 'equals', 'startsWith']),
      value: z.string().min(1).max(500),
    })).min(1).max(20),
    actions: z.array(z.object({
      type: z.enum(['move', 'markRead', 'star']),
      folderId: z.string().optional(),
    })).min(1).max(10),
    isActive: z.boolean().default(true),
  });

  r.get('/filters', asyncHandler(async (req, res) => {
    const mb = await mailboxOf(req);
    const { rows } = await pool.query(
      'SELECT * FROM filters WHERE mailbox_id=$1 ORDER BY position', [mb.id]);
    res.json({ data: rows });
  }));

  r.post('/filters', validate({ body: filterSchema }), asyncHandler(async (req, res) => {
    const mb = await mailboxOf(req);
    for (const a of req.body.actions) {
      if (a.type === 'move' && a.folderId) await folderByIdOrKind(req, mb, a.folderId);
    }
    const id = uuidv4();
    const { rows } = await pool.query(
      `INSERT INTO filters (id, org_id, mailbox_id, name, conditions, actions, is_active, position)
       VALUES ($1,$2,$3,$4,$5,$6,$7,(SELECT COALESCE(MAX(position),0)+1 FROM filters WHERE mailbox_id=$3))
       RETURNING *`,
      [id, req.auth.org.id, mb.id, req.body.name, JSON.stringify(req.body.conditions),
        JSON.stringify(req.body.actions), req.body.isActive]
    );
    res.status(201).json({ data: rows[0] });
  }));

  r.patch('/filters/:id', validate({ body: filterSchema.partial() }), asyncHandler(async (req, res) => {
    const mb = await mailboxOf(req);
    const sets = []; const vals = []; let i = 1;
    const map = { name: 'name', conditions: 'conditions', actions: 'actions', isActive: 'is_active' };
    for (const [bk, col] of Object.entries(map)) {
      if (req.body[bk] !== undefined) {
        const v = (bk === 'conditions' || bk === 'actions') ? JSON.stringify(req.body[bk]) : req.body[bk];
        sets.push(`${col}=$${i++}`); vals.push(v);
      }
    }
    if (!sets.length) throw badRequest('Nothing to update');
    vals.push(req.params.id, mb.id);
    const { rows } = await pool.query(
      `UPDATE filters SET ${sets.join(', ')} WHERE id=$${i} AND mailbox_id=$${i + 1} RETURNING *`, vals);
    if (!rows[0]) throw notFound('Filter not found');
    res.json({ data: rows[0] });
  }));

  r.delete('/filters/:id', asyncHandler(async (req, res) => {
    const mb = await mailboxOf(req);
    const { rowCount } = await pool.query('DELETE FROM filters WHERE id=$1 AND mailbox_id=$2', [req.params.id, mb.id]);
    if (!rowCount) throw notFound('Filter not found');
    res.json({ data: { ok: true } });
  }));

  return r;
}

module.exports = { routes };
