'use strict';
// Standalone migration runner: `npm run db:migrate`
const fs = require('fs');
const path = require('path');
const pool = require('../db');

async function main() {
  const sql = fs.readFileSync(path.join(__dirname, 'schema.sql'), 'utf8');
  await pool.query(sql);
  console.log('schema applied');
  await pool.end();
}

main().catch((e) => { console.error(e.message); process.exit(1); });
