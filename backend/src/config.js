'use strict';
// Central configuration. Everything comes from the environment; nothing secret
// is hard-coded. See .env.example for the full list.
require('dotenv').config();

function num(name, fallback) {
  const v = process.env[name];
  if (v === undefined || v === '') return fallback;
  const n = Number(v);
  if (Number.isNaN(n)) throw new Error(`Invalid numeric env ${name}=${v}`);
  return n;
}

const config = {
  env: process.env.NODE_ENV || 'development',
  port: num('PORT', 4000),
  databaseUrl: process.env.DATABASE_URL || 'postgres://dejoiy:dejoiy@localhost:5432/dejoiy_mail',
  redisUrl: process.env.REDIS_URL || 'redis://localhost:6379',
  redisEnabled: (process.env.REDIS_ENABLED || 'true').toLowerCase() !== 'false',
  sessionTtlDays: num('SESSION_TTL_DAYS', 30),
  bcryptRounds: num('BCRYPT_ROUNDS', 12),
  // Rate limits (requests per window)
  rateLimit: {
    windowMs: num('RATE_LIMIT_WINDOW_MS', 15 * 60 * 1000),
    max: num('RATE_LIMIT_MAX', 300),
    authMax: num('RATE_LIMIT_AUTH_MAX', 30),
  },
  // Razorpay — STUB in MVP. Keys intentionally absent; billing service refuses
  // to run live until RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are provided AND
  // BILLING_LIVE=true.
  razorpay: {
    keyId: process.env.RAZORPAY_KEY_ID || '',
    keySecret: process.env.RAZORPAY_KEY_SECRET || '',
    live: (process.env.BILLING_LIVE || 'false').toLowerCase() === 'true',
  },
  mail: {
    // Outbound provider for MVP: "stub" (queues only) | "ses" | "smtp".
    provider: process.env.MAIL_PROVIDER || 'stub',
    fromDomain: process.env.MAIL_FROM_DOMAIN || 'workmail.dejoiy.com',
  },
};

module.exports = config;
