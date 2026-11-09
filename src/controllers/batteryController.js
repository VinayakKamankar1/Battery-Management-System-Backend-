import {
  getCurrentTelemetry,
  getTelemetryHistory,
  ingestBatteryReading,
} from '../services/firebaseService.js';
import { addSseClient } from '../services/sseService.js';

/**
 * POST /api/battery/ingest
 * Ingest telemetry packet from NodeMCU ESP8266 or simulated hardware
 */
export const ingestBatteryData = async (req, res, next) => {
  try {
    const result = await ingestBatteryReading(req.body);

    res.status(201).json({
      success: true,
      stored: result.stored,
      message: result.stored 
        ? 'Telemetry reading persisted to Firebase Realtime Database' 
        : 'Telemetry reading processed (local cache mode)',
      id: result.id,
      timestamp: result.timestamp,
      data: result.data,
    });
  } catch (err) {
    next(err);
  }
};

/**
 * GET /api/battery/current
 * Fetch latest battery state from Firebase
 */
export const getCurrentBattery = async (req, res, next) => {
  try {
    const result = await getCurrentTelemetry();

    if (!result.data) {
      return res.status(200).json({
        success: true,
        message: 'No data available in Firebase',
        data: null,
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
 * GET /api/battery/history
 * Fetch historical readings from Firebase with optional date/time/range filters
 */
export const getBatteryHistory = async (req, res, next) => {
  try {
    const result = await getTelemetryHistory(req.query);

    if (!result.data || result.data.length === 0) {
      return res.status(200).json({
        success: true,
        message: 'No data available in Firebase for this period',
        count: 0,
        filterApplied: result.filterApplied || false,
        data: [],
      });
    }

    res.status(200).json({
      success: true,
      count: result.data.length,
      range: result.range || 'all',
      filterApplied: result.filterApplied || false,
      data: result.data,
    });
  } catch (err) {
    next(err);
  }
};

/**
 * GET /api/battery/health
 * Compute battery health analytics from real Firebase data
 */
export const getBatteryHealth = async (req, res, next) => {
  try {
    const currentRes = await getCurrentTelemetry();
    const historyRes = await getTelemetryHistory({ limit: 100 });

    if (!currentRes.data && historyRes.data.length === 0) {
      return res.status(200).json({
        success: true,
        message: 'No data available in Firebase to compute health metrics',
        data: null,
      });
    }

    const current = currentRes.data || {};
    const history = historyRes.data || [];

    // Compute metrics from actual telemetry readings
    const voltages = history.map((h) => h.voltage).filter((v) => typeof v === 'number');
    const temperatures = history.map((h) => h.temperature).filter((t) => typeof t === 'number');

    const avgVoltage = voltages.length
      ? parseFloat((voltages.reduce((a, b) => a + b, 0) / voltages.length).toFixed(2))
      : current.voltage || null;

    const maxTemp = temperatures.length ? Math.max(...temperatures) : current.temperature || null;
    const minTemp = temperatures.length ? Math.min(...temperatures) : current.temperature || null;

    const soh = current.soh ?? (current.soc ? Math.min(100, Math.round(current.soc * 1.1)) : null);
    const cycleCount = current.cycleCount ?? null;

    res.status(200).json({
      success: true,
      data: {
        soh,
        soc: current.soc ?? null,
        cycleCount,
        avgVoltage,
        maxTemperature: maxTemp,
        minTemperature: minTemp,
        currentVoltage: current.voltage ?? null,
        currentTemperature: current.temperature ?? null,
        deviceStatus: current.status || 'UNKNOWN',
        lastUpdated: current.timestamp || new Date().toISOString(),
      },
    });
  } catch (err) {
    next(err);
  }
};

/**
 * GET /api/battery/stream
 * SSE Stream endpoint
 */
export const streamBatteryData = (req, res) => {
  addSseClient(req, res);
};
