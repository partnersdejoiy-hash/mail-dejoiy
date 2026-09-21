'use strict';
// Billing service — Razorpay integration is a STUB in this MVP.
//
// Design (from TECHNICAL_PLAN.md): per-seat monthly subscriptions.
//   - subscriptions table holds the canonical state (plan, seats, status).
//   - razorpay_* columns exist but are NEVER populated while BILLING_LIVE=false.
//   - Every public function below refuses to touch the network and throws
//     BillingNotLiveError unless BILLING_LIVE=true AND keys are configured.
//
// Seat changes are applied locally immediately (seat_events audit trail) so
// the product works end-to-end; reconciliation with Razorpay happens when the
// live integration lands.
const config = require('../config');
const { HttpError } = require('../middleware/errors');

class BillingNotLiveError extends HttpError {
  constructor(message = 'Billing provider is not connected (STUB mode). Seat change recorded locally.') {
    super(501, 'billing_not_live', message);
    this.recordedLocally = true;
  }
}

function assertLive() {
  if (!config.razorpay.live || !config.razorpay.keyId || !config.razorpay.keySecret) {
    throw new BillingNotLiveError();
  }
}

// --- Local (always available) -------------------------------------------
async function getSubscription(pool, orgId) {
  const { rows } = await pool.query(
    `SELECT s.*, p.code AS plan_code, p.name AS plan_name, p.price_inr_monthly, p.max_users
       FROM subscriptions s JOIN plans p ON p.id = s.plan_id
      WHERE s.org_id = $1`, [orgId]
  );
  return rows[0] || null;
}

async function setSeats(pool, orgId, seats, actorUserId) {
  if (!Number.isInteger(seats) || seats < 1 || seats > 10000) {
    throw new HttpError(400, 'bad_request', 'seats must be an integer between 1 and 10000');
  }
  const sub = await getSubscription(pool, orgId);
  if (!sub) throw new HttpError(404, 'not_found', 'No subscription for this organization');
  const prev = sub.seats;
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    await client.query('UPDATE subscriptions SET seats=$2, updated_at=now() WHERE org_id=$1', [orgId, seats]);
    const { v4: uuidv4 } = require('uuid');
    await client.query(
      `INSERT INTO seat_events (id, org_id, user_id, event) VALUES ($1,$2,$3,$4)`,
      [uuidv4(), orgId, actorUserId, seats > prev ? 'seat_added' : 'seat_removed']
    );
    await client.query('COMMIT');
  } catch (e) {
    await client.query('ROLLBACK');
    throw e;
  } finally {
    client.release();
  }
  return { ...(await getSubscription(pool, orgId)), previousSeats: prev, razorpaySynced: false };
}

// --- Razorpay (STUB — network calls live here when implemented) -----------
async function createRazorpaySubscription(_pool, _orgId, _planCode) {
  assertLive();
  // TODO(billing): razorpay.subscriptions.create({...}); store ids; webhook handler.
  throw new HttpError(501, 'not_implemented', 'Razorpay subscription creation not implemented yet');
}

async function handleRazorpayWebhook(_pool, _payload, _signature) {
  assertLive();
  // TODO(billing): verify signature, map events -> subscription status transitions.
  throw new HttpError(501, 'not_implemented', 'Razorpay webhook handling not implemented yet');
}

module.exports = {
  BillingNotLiveError,
  getSubscription,
  setSeats,
  createRazorpaySubscription,
  handleRazorpayWebhook,
};
