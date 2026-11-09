/**
 * Structured HTTP Request Logger Middleware
 * Logs incoming HTTP method, URL, status code, response time in ms, and ISO timestamp.
 */
export const requestLogger = (req, res, next) => {
  const start = Date.now();
  const timestamp = new Date().toISOString();

  // Intercept response finish
  res.on('finish', () => {
    const duration = Date.now() - start;
    const statusCode = res.statusCode;
    const isError = statusCode >= 400;

    const logEntry = {
      timestamp,
      method: req.method,
      url: req.originalUrl || req.url,
      status: statusCode,
      durationMs: duration,
      ip: req.ip || req.connection.remoteAddress,
    };

    if (isError) {
      console.warn(`[API WARN] ${logEntry.method} ${logEntry.url} ${logEntry.status} - ${logEntry.durationMs}ms`);
    } else {
      console.log(`[API INFO] ${logEntry.method} ${logEntry.url} ${logEntry.status} - ${logEntry.durationMs}ms`);
    }
  });

  next();
};
