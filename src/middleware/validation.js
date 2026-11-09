import { body, param, query, validationResult } from 'express-validator';

export const handleValidationErrors = (req, res, next) => {
  const errors = validationResult(req);
  if (!errors.isEmpty()) {
    return res.status(400).json({
      success: false,
      message: 'Validation failed',
      errors: errors.array().map((err) => ({
        field: err.path || err.param,
        message: err.msg,
        value: err.value,
      })),
    });
  }
  next();
};

/**
 * Validates incoming battery reading ingestion from NodeMCU ESP8266 or simulated hardware
 */
export const validateIngestReading = [
  body('voltage')
    .notEmpty().withMessage('Voltage is required')
    .isFloat({ min: 0.0, max: 65.0 }).withMessage('Voltage must be a number between 0.0V and 65.0V'),
  body('current')
    .optional({ nullable: true })
    .isFloat({ min: -30.0, max: 30.0 }).withMessage('Current must be a number between -30.0A and 30.0A'),
  body('power')
    .optional({ nullable: true })
    .isFloat({ min: 0.0, max: 2000.0 }).withMessage('Power must be a number between 0.0W and 2000.0W'),
  body('temperature')
    .optional({ nullable: true })
    .isFloat({ min: -10.0, max: 85.0 }).withMessage('Temperature must be a number between -10.0°C and 85.0°C'),
  body('fanStatus')
    .optional()
    .isIn(['ON', 'OFF', 'on', 'off', true, false]).withMessage('Fan status must be ON or OFF'),
  body('buzzerStatus')
    .optional()
    .isIn(['ON', 'OFF', 'on', 'off', true, false]).withMessage('Buzzer status must be ON or OFF'),
  body('soc')
    .optional({ nullable: true })
    .isFloat({ min: 0, max: 100 }).withMessage('SOC must be a percentage between 0 and 100'),
  body('soh')
    .optional({ nullable: true })
    .isFloat({ min: 0, max: 100 }).withMessage('SOH must be a percentage between 0 and 100'),
  handleValidationErrors,
];

/**
 * Validates historical telemetry query filters
 */
export const validateHistoryQuery = [
  query('limit')
    .optional()
    .isInt({ min: 1, max: 1000 }).withMessage('Limit must be an integer between 1 and 1000'),
  query('range')
    .optional()
    .isIn(['1m', '10m', '1h', '24h', '7d', '30d', 'all', '1M', '10M', '1H', '24H', '7D', '30D', 'ALL'])
    .withMessage('Range must be one of: 1m, 10m, 1h, 24h, 7d, 30d, all'),
  query('startDate')
    .optional()
    .isISO8601().withMessage('startDate must be a valid ISO 8601 date string'),
  query('endDate')
    .optional()
    .isISO8601().withMessage('endDate must be a valid ISO 8601 date string'),
  handleValidationErrors,
];

/**
 * Validates device status update
 */
export const validateDeviceStatus = [
  body('status')
    .optional()
    .isIn(['ONLINE', 'OFFLINE', 'STALE_DATA', 'SENSOR_FAILURE', 'online', 'offline', 'stale_data', 'sensor_failure'])
    .withMessage('Status must be ONLINE, OFFLINE, STALE_DATA, or SENSOR_FAILURE'),
  body('sensorHealth')
    .optional()
    .isObject().withMessage('sensorHealth must be an object'),
  handleValidationErrors,
];

/**
 * Validates alert creation
 */
export const validateCreateAlert = [
  body('type').notEmpty().withMessage('Alert type is required').isString().trim(),
  body('severity')
    .optional()
    .isIn(['Critical', 'Warning', 'Info', 'CRITICAL', 'WARNING', 'INFO'])
    .withMessage('Invalid severity level (must be Critical, Warning, or Info)'),
  body('sensorValue').notEmpty().withMessage('Sensor value is required').isString().trim(),
  body('message').notEmpty().withMessage('Alert message is required').isString().trim(),
  handleValidationErrors,
];

/**
 * Validates alert status update
 */
export const validateUpdateAlertStatus = [
  param('id').notEmpty().withMessage('Alert ID is required'),
  body('status')
    .notEmpty().withMessage('Status is required')
    .isIn(['ACTIVE', 'RESOLVED', 'ACKNOWLEDGED', 'active', 'resolved', 'acknowledged'])
    .withMessage('Status must be ACTIVE, RESOLVED, or ACKNOWLEDGED'),
  handleValidationErrors,
];

/**
 * Validates alert filter query
 */
export const validateAlertsQuery = [
  query('limit')
    .optional()
    .isInt({ min: 1, max: 500 }).withMessage('Limit must be between 1 and 500'),
  query('status')
    .optional()
    .isIn(['ACTIVE', 'RESOLVED', 'ACKNOWLEDGED', 'ALL', 'active', 'resolved', 'acknowledged', 'all'])
    .withMessage('Status filter must be ACTIVE, RESOLVED, ACKNOWLEDGED, or ALL'),
  query('severity')
    .optional()
    .isIn(['Critical', 'Warning', 'Info', 'ALL', 'critical', 'warning', 'info', 'all'])
    .withMessage('Severity filter must be Critical, Warning, Info, or ALL'),
  handleValidationErrors,
];

/**
 * Validates report generation request
 */
export const validateCreateReport = [
  body('period')
    .optional()
    .isIn(['1h', '24h', '7d', '30d'])
    .withMessage('Period must be 1h, 24h, 7d, or 30d'),
  body('title').optional().isString().trim(),
  handleValidationErrors,
];
