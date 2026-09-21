'use strict';
// Process entry point: connects Postgres + Redis, runs migrations, starts HTTP.
const fs = require('fs');
const path = require('path');
const config = require('./config');
const pool = require('./db');
const redis = require('./redis');
const { createApp } = require('./app');

async function migrate() {
  const sql = fs.readFileSync(path.join(__dirname, 'db', 'schema.sql'), 'utf8');
  await pool.query(sql);
}

async function main() {
  await redis.init(); // non-fatal if unavailable
  try {
    await migrate();
    console.log('[db] schema up to date');
  } catch (err) {
    console.error('[db] migration failed:', err.message);
    process.exit(1);
  }
  const app = createApp({ pool });
  const server = app.listen(config.port, () => {
    console.log(`[api] listening on :${config.port} (${config.env})`);
  });

  const shutdown = async () => {
    console.log('[api] shutting down');
    server.close(async () => {
      await pool.end();
      const c = redis.getClient();
      if (c) await c.quit().catch(() => {});
      process.exit(0);
    });
    setTimeout(() => process.exit(1), 10000).unref();
  };
  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);
}

main().catch((err) => {
  console.error('[api] fatal:', err);
  process.exit(1);
});
