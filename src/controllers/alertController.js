import { 
  getAlerts, 
  updateAlertStatusInDb, 
  acknowledgeAllAlertsInDb 
} from '../services/firebaseService.js';
import { createAlertRecord } from '../services/alertService.js';

/**
 * GET /api/alerts
 * List alerts from Firebase with optional ?status=ACTIVE&severity=Critical&startDate=...&endDate=...&limit=50
 */
export const getAlertsList = async (req, res, next) => {
  try {
    const filters = {
      statusFilter: req.query.status || null,
      severityFilter: req.query.severity || null,
      startDate: req.query.startDate || req.query.from || null,
      endDate: req.query.endDate || req.query.to || null,
      limit: parseInt(req.query.limit || '50', 10),
    };

    const result = await getAlerts(filters);

    if (!result.data || result.data.length === 0) {
      return res.status(200).json({
        success: true,
        message: 'No alerts found in Firebase matching criteria',
        count: 0,
        data: [],
      });
    }

    res.status(200).json({
      success: true,
      count: result.data.length,
      data: result.data,
    });
  } catch (err) {
    next(err);
  }
};

/**
 * POST /api/alerts
 * Manually or programmatically trigger a new alert record into Firebase
 */
export const createAlert = async (req, res, next) => {
  try {
    const alertRecord = await createAlertRecord({
      type: req.body.type,
      severity: req.body.severity || 'Warning',
      sensorValue: req.body.sensorValue,
      message: req.body.message,
      aiExplanation: req.body.aiExplanation || null,
    });

    res.status(201).json({
      success: true,
      message: 'Alert persisted to Firebase successfully',
      data: alertRecord,
    });
  } catch (err) {
    next(err);
  }
};

/**
 * PATCH /api/alerts/:id
 * Update status of an existing alert (e.g. ACTIVE -> RESOLVED or ACKNOWLEDGED)
 */
export const updateAlert = async (req, res, next) => {
  try {
    const { id } = req.params;
    const { status } = req.body;

    const result = await updateAlertStatusInDb(id, status);

    if (!result.configured) {
      return res.status(200).json({
        success: true,
        message: 'Firebase not configured. Alert state unchanged.',
        updated: false,
      });
    }

    if (result.notFound) {
      return res.status(404).json({
        success: false,
        message: `Alert with ID '${id}' not found`,
      });
    }

    res.status(200).json({
      success: true,
      message: `Alert '${id}' updated to status '${status.toUpperCase()}'`,
    });
  } catch (err) {
    next(err);
  }
};

/**
 * POST /api/alerts/acknowledge
 * Acknowledge / resolve all active alerts
 */
export const acknowledgeAllAlertsController = async (req, res, next) => {
  try {
    await acknowledgeAllAlertsInDb();

    res.status(200).json({
      success: true,
      message: 'All active alerts acknowledged successfully in Firebase',
    });
  } catch (err) {
    next(err);
  }
};
