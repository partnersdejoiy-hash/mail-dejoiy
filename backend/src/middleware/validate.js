'use strict';
// Zod-based request validation. Schemas live next to routes; this helper runs
// them and converts failures into 400 responses with field-level detail.
const { badRequest } = require('./errors');

function validate(schemas) {
  // schemas: { body?, query?, params? } — each a zod schema
  return (req, _res, next) => {
    try {
      for (const key of ['body', 'query', 'params']) {
        if (schemas[key]) {
          req[key] = schemas[key].parse(req[key]);
        }
      }
      next();
    } catch (err) {
      const details = (err.issues || []).map((i) => ({
        path: i.path.join('.'),
        message: i.message,
      }));
      next(badRequest('Validation failed', details));
    }
  };
}

module.exports = { validate };
