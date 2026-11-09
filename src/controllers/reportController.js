import {
  getReportsFromDb,
  getReportByIdFromDb,
  saveReportToDb,
  getTelemetryHistory,
  getAlerts,
} from '../services/firebaseService.js';

/**
 * GET /api/reports
 * Fetch list of generated reports from Firebase
 */
export const getReports = async (req, res, next) => {
  try {
    const limit = parseInt(req.query.limit || '20', 10);
    const result = await getReportsFromDb(limit);

    if (!result.data || result.data.length === 0) {
      return res.status(200).json({
        success: true,
        message: 'No reports found in Firebase',
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
 * GET /api/reports/:id
 * Fetch single report by ID
 */
export const getReportById = async (req, res, next) => {
  try {
    const { id } = req.params;
    const result = await getReportByIdFromDb(id);

    if (!result.data) {
      return res.status(404).json({
        success: false,
        message: `Report with ID '${id}' not found`,
      });
    }

    res.status(200).json({
      success: true,
      data: result.data,
    });
  } catch (err) {
    next(err);
  }
};

/**
 * POST /api/reports
 * Generate and store a summary report based on Firebase historical readings & associated alerts
 */
export const createReport = async (req, res, next) => {
  try {
    const period = req.body.period || '24h';
    const title = req.body.title || `BMS Performance & Diagnostics Report (${period.toUpperCase()})`;

    const historyRes = await getTelemetryHistory({ range: period, limit: 300 });
    const alertsRes = await getAlerts({ limit: 100 });

    const history = historyRes.data || [];
    const alerts = alertsRes.data || [];

    const voltages = history.map((h) => h.voltage).filter((v) => typeof v === 'number');
    const temperatures = history.map((h) => h.temperature).filter((t) => typeof t === 'number');
    const currents = history.map((h) => h.current).filter((c) => typeof c === 'number');
    const powers = history.map((h) => h.power).filter((p) => typeof p === 'number');

    const avgVoltage = voltages.length
      ? parseFloat((voltages.reduce((a, b) => a + b, 0) / voltages.length).toFixed(2))
      : null;
    const minVoltage = voltages.length ? Math.min(...voltages) : null;
    const maxVoltage = voltages.length ? Math.max(...voltages) : null;

    const maxTemp = temperatures.length ? Math.max(...temperatures) : null;
    const minTemp = temperatures.length ? Math.min(...temperatures) : null;
    const avgTemp = temperatures.length
      ? parseFloat((temperatures.reduce((a, b) => a + b, 0) / temperatures.length).toFixed(1))
      : null;

    const avgCurrent = currents.length
      ? parseFloat((currents.reduce((a, b) => a + b, 0) / currents.length).toFixed(2))
      : null;
    const maxCurrent = currents.length ? Math.max(...currents) : null;

    const avgPower = powers.length
      ? parseFloat((powers.reduce((a, b) => a + b, 0) / powers.length).toFixed(1))
      : null;

    const reportData = {
      id: `REP-${Date.now().toString().slice(-6)}`,
      title,
      period,
      reportingPeriod: period,
      generatedAt: new Date().toISOString(),
      summaryMetrics: {
        totalReadingsEvaluated: history.length,
        avgPackVoltage: avgVoltage,
        minPackVoltage: minVoltage,
        maxPackVoltage: maxVoltage,
        avgTemperature: avgTemp,
        maxTemperature: maxTemp,
        minTemperature: minTemp,
        avgCurrent: avgCurrent,
        maxCurrent: maxCurrent,
        avgPower: avgPower,
        totalAlertsTriggered: alerts.length,
        criticalAlertsCount: alerts.filter(
          (a) => a.severity && a.severity.toUpperCase() === 'CRITICAL'
        ).length,
      },
      associatedAlerts: alerts.slice(0, 10),
    };

    const saveRes = await saveReportToDb(reportData);

    res.status(201).json({
      success: true,
      message: saveRes.saved
        ? 'Report generated and persisted to Firebase successfully'
        : 'Report generated (local cache mode)',
      id: saveRes.key || reportData.id,
      data: reportData,
    });
  } catch (err) {
    next(err);
  }
};
