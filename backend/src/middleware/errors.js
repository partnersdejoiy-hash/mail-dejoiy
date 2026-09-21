'use strict';
// Consistent JSON error shape: { error: { code, message, details? } }

class HttpError extends Error {
  constructor(status, code, message, details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

const badRequest = (msg = 'Bad request', details) => new HttpError(400, 'bad_request', msg, details);
const unauthorized = (msg = 'Authentication required') => new HttpError(401, 'unauthorized', msg);
const forbidden = (msg = 'Insufficient permissions') => new HttpError(403, 'forbidden', msg);
const notFound = (msg = 'Not found') => new HttpError(404, 'not_found', msg);
const conflict = (msg = 'Conflict') => new HttpError(409, 'conflict', msg);

// eslint-disable-next-line no-unused-vars
function errorHandler(err, _req, res, _next) {
  const status = err.status || 500;
  const code = err.code || 'internal_error';
  if (status >= 500) {
    // eslint-disable-next-line no-console
    console.error('[api] unhandled error:', err);
  }
  res.status(status).json({
    error: {
      code,
      message: status >= 500 ? 'Internal server error' : err.message,
      ...(err.details ? { details: err.details } : {}),
    },
  });
}

function asyncHandler(fn) {
  return (req, res, next) => Promise.resolve(fn(req, res, next)).catch(next);
}

module.exports = { HttpError, badRequest, unauthorized, forbidden, notFound, conflict, errorHandler, asyncHandler };
