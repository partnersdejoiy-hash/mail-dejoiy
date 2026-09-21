'use strict';
// Redis client. Optional at runtime: if Redis is unavailable the app keeps
// working with in-memory fallbacks (rate limiter, queue) and logs a warning.
// Nothing here is on the critical path for correctness.
const { createClient } = require('redis');
const config = require('./config');

let client = null;
let available = false;

async function init() {
  if (!config.redisEnabled) {
    console.warn('[redis] disabled via REDIS_ENABLED=false; using in-memory fallbacks');
    return null;
  }
  try {
    client = createClient({ url: config.redisUrl });
    client.on('error', (err) => console.error('[redis] client error:', err.message));
    await client.connect();
    available = true;
    console.log('[redis] connected');
    return client;
  } catch (err) {
    console.warn('[redis] unavailable, using in-memory fallbacks:', err.message);
    client = null;
    available = false;
    return null;
  }
}

function getClient() {
  return available ? client : null;
}

function isAvailable() {
  return available;
}

module.exports = { init, getClient, isAvailable };
