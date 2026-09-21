'use strict';
// Rate limiting. Uses Redis when available, otherwise the in-memory store.
// Auth endpoints get a stricter bucket to slow credential stuffing.
const rateLimit = require('express-rate-limit');
const config = require('../config');
const redis = require('../redis');

function makeLimiter({ max, message }) {
  const options = {
    windowMs: config.rateLimit.windowMs,
    max,
    standardHeaders: 'draft-7',
    legacyHeaders: false,
    message: { error: { code: 'rate_limited', message } },
  };
  const client = redis.getClient();
  if (client) {
    // Custom Redis-backed counter (avoids adding another dependency).
    options.store = {
      async increment(key) {
        const redisKey = `rl:${key}`;
        const count = await client.incr(redisKey);
        if (count === 1) await client.pExpire(redisKey, config.rateLimit.windowMs);
        const ttl = await client.pTtl(redisKey);
        return { totalHits: count, resetTime: new Date(Date.now() + Math.max(ttl, 0)) };
      },
      async decrement(key) { await client.decr(`rl:${key}`); },
      async resetKey(key) { await client.del(`rl:${key}`); },
    };
  }
  return rateLimit(options);
}

const generalLimiter = () => makeLimiter({
  max: config.rateLimit.max,
  message: 'Too many requests, please slow down.',
});

const authLimiter = () => makeLimiter({
  max: config.rateLimit.authMax,
  message: 'Too many login attempts, please try again later.',
});

module.exports = { generalLimiter, authLimiter };
