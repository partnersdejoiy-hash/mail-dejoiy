'use strict';
// Express app factory. Takes { pool, redis } so tests can inject pg-mem and
// skip Redis. index.js wires the real implementations.
const express = require('express');
const helmet = require('helmet');
const cors = require('cors');
const config = require('./config');
const { errorHandler, notFound } = require('./middleware/errors');
const { generalLimiter } = require('./middleware/rateLimit');

function createApp({ pool }) {
  const app = express();
  app.disable('x-powered-by');
  app.set('trust proxy', 1);

  app.use(helmet({ contentSecurityPolicy: false }));
  app.use(cors({ origin: process.env.CORS_ORIGIN ? process.env.CORS_ORIGIN.split(',') : true }));
  app.use(express.json({ limit: '5mb' }));

  // Health — no auth, used by docker-compose/orchestrators.
  app.get('/health', (_req, res) => res.json({ ok: true, env: config.env, version: '0.1.0' }));

  const api = express.Router();
  api.use(generalLimiter());
  api.use('/auth', require('./routes/auth').routes(pool));
  api.use('/admin', require('./routes/admin').routes(pool));
  api.use('/mail', require('./routes/mail').routes(pool));
  api.use('/settings', require('./routes/settings').routes(pool));
  app.use('/api/v1', api);

  app.use((_req, _res, next) => next(notFound('Route not found')));
  app.use(errorHandler);
  return app;
}

module.exports = { createApp };
