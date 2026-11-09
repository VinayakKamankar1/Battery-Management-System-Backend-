import { getDb, isFirebaseConfigured } from '../config/firebase.js';
import { broadcastSse } from './sseService.js';

// Cooldown map to avoid spamming duplicate alerts (key: alertType, value: lastTriggerTimestamp)
const alertCooldowns = new Map();
const COOLDOWN_MS = 60000; // 60 seconds cooldown per alert type

export const checkProtectionThresholds = async (telemetry) => {
  if (!telemetry) return;

  const ovpLimit = parseFloat(process.env.OVP_THRESHOLD || '54.0');
  const uvpLimit = parseFloat(process.env.UVP_THRESHOLD || '40.0');
  const ocpLimit = parseFloat(process.env.OCP_THRESHOLD || '40.0');
  const otpLimit = parseFloat(process.env.OTP_THRESHOLD || '45.0');

  const { voltage, current, temperature } = telemetry;
  const now = Date.now();

  const alertsToTrigger = [];

  // Check Over-voltage (OVP) only when real voltage reading is provided
  if (typeof voltage === 'number' && voltage > ovpLimit) {
    alertsToTrigger.push({
      type: 'Over-voltage',
      severity: 'Critical',
      sensorValue: `${voltage.toFixed(2)} V (Limit: ${ovpLimit.toFixed(1)} V)`,
      message: `Pack voltage reached ${voltage.toFixed(2)}V, exceeding OVP limit of ${ovpLimit.toFixed(1)}V.`,
      aiExplanation: 'High pack voltage detected. Shunt resistors or charge cutoff relay must be activated immediately to protect cell chemistry.',
    });
  }

  // Check Under-voltage (UVP) only when real voltage reading is provided (> 5V to avoid disconnected float)
  if (typeof voltage === 'number' && voltage < uvpLimit && voltage > 5.0) {
    alertsToTrigger.push({
      type: 'Under-voltage',
      severity: 'Warning',
      sensorValue: `${voltage.toFixed(2)} V (Limit: ${uvpLimit.toFixed(1)} V)`,
      message: `Pack voltage dropped to ${voltage.toFixed(2)}V, below UVP threshold of ${uvpLimit.toFixed(1)}V.`,
      aiExplanation: 'Deep discharge condition detected. Load disconnect circuit recommended to prevent copper dissolution in negative electrodes.',
    });
  }

  // Check Over-current (OCP) only when real current reading is provided
  if (typeof current === 'number' && Math.abs(current) > ocpLimit) {
    alertsToTrigger.push({
      type: 'Over-current',
      severity: 'Critical',
      sensorValue: `${Math.abs(current).toFixed(1)} A (Limit: ${ocpLimit.toFixed(1)} A)`,
      message: `Pack current surge detected at ${Math.abs(current).toFixed(1)}A, exceeding OCP limit of ${ocpLimit.toFixed(1)}A.`,
      aiExplanation: 'Rapid load spike or short-circuit tendency. Solid-state breaker tripping engaged to prevent thermal runaway.',
    });
  }

  // Check Overheating (OTP) only when real temperature reading is provided
  if (typeof temperature === 'number' && temperature > otpLimit) {
    alertsToTrigger.push({
      type: 'Overheating',
      severity: 'Critical',
      sensorValue: `${temperature.toFixed(1)} °C (Warning: ${otpLimit.toFixed(1)} °C)`,
      message: `Cell temperature elevated to ${temperature.toFixed(1)}°C, exceeding thermal safety threshold of ${otpLimit.toFixed(1)}°C.`,
      aiExplanation: 'Thermal dissipation capacity exceeded. Active forced cooling fan and current derating must be maintained.',
    });
  }

  for (const alertData of alertsToTrigger) {
    const lastTriggered = alertCooldowns.get(alertData.type) || 0;
    if (now - lastTriggered > COOLDOWN_MS) {
      alertCooldowns.set(alertData.type, now);
      await createAlertRecord(alertData);
    }
  }
};

export const createAlertRecord = async (alertData) => {
  const alertRecord = {
    id: `ALT-${Date.now().toString().slice(-6)}`,
    type: alertData.type,
    severity: alertData.severity || 'Warning',
    status: 'ACTIVE',
    timestamp: new Date().toISOString().replace('T', ' ').slice(0, 19),
    sensorValue: alertData.sensorValue,
    message: alertData.message,
    aiExplanation: alertData.aiExplanation || null,
  };

  if (isFirebaseConfigured()) {
    try {
      const db = getDb();
      // Write to primary smart_bms/alerts and fallback alerts
      const smartBmsAlertsRef = db.ref('smart_bms/alerts').push();
      await smartBmsAlertsRef.set(alertRecord);
      const alertsRef = db.ref('alerts').push();
      await alertsRef.set(alertRecord);
    } catch (err) {
      console.error('[AlertService] Failed to write alert to Firebase:', err.message);
    }
  }

  // Always broadcast via SSE
  broadcastSse('alert', alertRecord);
  return alertRecord;
};
