'use strict';
// Outbound mail service (MVP).
//
// The message is ALWAYS persisted first (messages table, sent folder) and an
// outbox row is created. Delivery itself is provider-dependent:
//
//   MAIL_PROVIDER=stub  (default) — no network. The outbox row stays "queued"
//                                  and a worker log line is emitted. Safe for
//                                  dev/test; nothing leaves the machine.
//   MAIL_PROVIDER=ses/smtp        — NOT implemented in this MVP. The service
//                                  throws a clear error instead of silently
//                                  pretending to send.
//
// This guarantees we never claim a mail was sent when it wasn't.
const { v4: uuidv4 } = require('uuid');
const config = require('../config');

async function enqueue(pool, { orgId, mailboxId, messageId }) {
  const id = uuidv4();
  const { rows } = await pool.query(
    `INSERT INTO outbox (id, org_id, mailbox_id, message_id, status)
     VALUES ($1,$2,$3,$4,'queued') RETURNING *`,
    [id, orgId, mailboxId, messageId]
  );
  const row = rows[0];

  if (config.mail.provider === 'stub') {
    // eslint-disable-next-line no-console
    console.log(`[mailer:stub] queued outbox ${row.id} (message ${messageId}); no delivery attempted`);
    return { outboxId: row.id, status: 'queued', delivered: false };
  }

  // Any real provider must be implemented before use.
  await pool.query(`UPDATE outbox SET status='failed', last_error=$2, updated_at=now() WHERE id=$1`,
    [row.id, `MAIL_PROVIDER=${config.mail.provider} is not implemented in this MVP`]);
  const { HttpError } = require('../middleware/errors');
  throw new HttpError(501, 'mail_provider_not_implemented',
    `Outbound provider "${config.mail.provider}" is not implemented yet; message kept as draft in outbox.`);
}

async function outboxStatus(pool, orgId, outboxId) {
  const { rows } = await pool.query(
    'SELECT * FROM outbox WHERE id=$1 AND org_id=$2', [outboxId, orgId]
  );
  return rows[0] || null;
}

module.exports = { enqueue, outboxStatus };
