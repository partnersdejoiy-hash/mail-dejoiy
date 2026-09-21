'use strict';
// PostgreSQL connection pool. One shared pool per process.
const { Pool } = require('pg');
const config = require('./config');

const pool = new Pool({
  connectionString: config.databaseUrl,
  max: 20,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 5000,
});

pool.on('error', (err) => {
  // A broken idle client must not crash the process silently.
  // eslint-disable-next-line no-console
  console.error('[db] idle client error', err.message);
});

module.exports = pool;
