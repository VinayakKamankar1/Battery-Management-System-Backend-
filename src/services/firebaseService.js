import { getDb, isFirebaseConfigured } from '../config/firebase.js';
import { broadcastSse } from './sseService.js';
import { checkProtectionThresholds, createAlertRecord } from './alertService.js';

let listening = false;
let lastFanState = null;
let lastBuzzerState = null;
let cachedLatestTelemetry = null;

/**
 * Normalizes raw payload into standard BMS telemetry schema
 */
export const normalizeTelemetry = (val) => {
  if (!val || typeof val !== 'object') return null;

  const v = typeof val.voltage === 'number' ? val.voltage : (typeof val.packVoltage === 'number' ? val.packVoltage : null);
  const c = typeof val.current === 'number' ? val.current : null;
  const p = typeof val.power === 'number' ? val.power : ((v !== null && c !== null) ? parseFloat((v * c).toFixed(2)) : null);
  const t = typeof val.temperature === 'number' ? val.temperature : (typeof val.temp === 'number' ? val.temp : null);
  
  const fan = val.fanStatus ? String(val.fanStatus).toUpperCase() : (val.fan === true ? 'ON' : val.fan === false ? 'OFF' : 'OFF');
  const buzzer = val.buzzerStatus ? String(val.buzzerStatus).toUpperCase() : (val.buzzer === true ? 'ON' : val.buzzer === false ? 'OFF' : 'OFF');
  
  const updatedAtMs = typeof val.updatedAt === 'number' 
    ? val.updatedAt 
    : (val.timestamp ? new Date(val.timestamp).getTime() : Date.now());
  const isStale = (Date.now() - updatedAtMs) > 60000;
  const status = isStale ? 'STALE_DATA' : (val.status || 'ONLINE');

  return {
    status,
    voltage: v,
    current: c,
    power: p,
    temperature: t,
    fanStatus: fan,
    buzzerStatus: buzzer,
    flameDetected: Boolean(val.flameDetected),
    pumpStatus: val.pumpStatus || 'OFF',
    soc: typeof val.soc === 'number' ? val.soc : null,
    soh: typeof val.soh === 'number' ? val.soh : null,
    cycleCount: typeof val.cycleCount === 'number' ? val.cycleCount : null,
    minCellVoltage: val.minCellVoltage || null,
    maxCellVoltage: val.maxCellVoltage || null,
    avgCellVoltage: val.avgCellVoltage || null,
    cellCount: val.cellCount || null,
    timestamp: new Date(updatedAtMs).toISOString(),
    rawTimestamp: updatedAtMs,
    updatedAt: updatedAtMs,
    firmwareVersion: val.firmwareVersion || 'ESP-BMS-v1.4.2',
    rssi: val.rssi ?? -58,
    sensorHealth: val.sensorHealth || {
      ina219: v !== null ? 'OK' : 'DISCONNECTED',
      dht11: t !== null ? 'OK' : 'DISCONNECTED',
      l298n: 'OK',
      buzzer: 'OK',
      oled: 'OK',
    },
  };
};

/**
 * Persists an Actuator State Change Event into Firebase RTDB
 */
export const recordActuatorEvent = async ({
  actuator,
  state,
  previousState = null,
  triggeredBy = 'manual',
  ambientTemperature = null,
  packVoltage = null,
}) => {
  const eventRecord = {
    id: `ACT-${Date.now().toString().slice(-6)}`,
    actuator, // 'fan' | 'buzzer'
    state: String(state).toUpperCase(),
    previousState: previousState ? String(previousState).toUpperCase() : null,
    triggeredBy,
    ambientTemperature,
    packVoltage,
    timestamp: new Date().toISOString(),
    rawTimestamp: Date.now(),
  };

  if (!isFirebaseConfigured()) {
    console.log('[Actuator Log (Local)]', eventRecord);
    return { configured: false, stored: true, data: eventRecord };
  }

  try {
    const db = getDb();
    const ref = db.ref('actuator_events').push();
    await ref.set(eventRecord);
    return { configured: true, stored: true, id: ref.key, data: eventRecord };
  } catch (err) {
    console.error('[Firebase Error] Failed to store actuator event:', err.message);
    return { configured: true, stored: false, error: err.message };
  }
};

/**
 * Retrieves list of past actuator events
 */
export const getActuatorEvents = async (limit = 50) => {
  if (!isFirebaseConfigured()) {
    return { configured: false, data: [] };
  }

  try {
    const db = getDb();
    const snapshot = await db.ref('actuator_events').limitToLast(limit).once('value');
    const val = snapshot.val();
    if (!val) return { configured: true, data: [] };

    const list = Object.keys(val).map((k) => ({
      key: k,
      ...val[k],
    }));

    return { configured: true, data: list.reverse() };
  } catch (err) {
    console.error('[Firebase Error] Failed to get actuator events:', err.message);
    return { configured: true, data: [], error: err.message };
  }
};

/**
 * Ingests a new battery reading from NodeMCU ESP8266 or simulated hardware
 * Performs persistence to telemetry/current and telemetry/history, evaluates alerts,
 * logs actuator state changes, and broadcasts via SSE.
 */
export const ingestBatteryReading = async (rawPayload) => {
  const normalized = normalizeTelemetry(rawPayload);
  if (!normalized) {
    throw new Error('Invalid telemetry payload structure');
  }

  let stored = false;
  let historyKey = null;

  if (isFirebaseConfigured()) {
    const db = getDb();

    // 1. Update latest reading at smart_bms/latest and legacy telemetry/current
    await db.ref('smart_bms/latest').set(normalized);
    await db.ref('telemetry/current').set(normalized);

    // 2. Append to smart_bms/readings and legacy telemetry/history
    const smartBmsHistoryRef = db.ref('smart_bms/readings').push();
    await smartBmsHistoryRef.set(normalized);
    const historyRef = db.ref('telemetry/history').push();
    await historyRef.set(normalized);
    historyKey = smartBmsHistoryRef.key || historyRef.key;
    stored = true;
  } else {
    // In local unconfigured mode, memory cache holds it
    stored = true;
  }

  cachedLatestTelemetry = normalized;

  // 3. Actuator event tracking on state changes
  if (lastFanState !== null && lastFanState !== normalized.fanStatus) {
    await recordActuatorEvent({
      actuator: 'fan',
      state: normalized.fanStatus,
      previousState: lastFanState,
      triggeredBy: normalized.temperature >= 35.0 ? 'auto_thermal' : 'telemetry_stream',
      ambientTemperature: normalized.temperature,
      packVoltage: normalized.voltage,
    });
  }
  lastFanState = normalized.fanStatus;

  if (lastBuzzerState !== null && lastBuzzerState !== normalized.buzzerStatus) {
    await recordActuatorEvent({
      actuator: 'buzzer',
      state: normalized.buzzerStatus,
      previousState: lastBuzzerState,
      triggeredBy: 'protection_interlock',
      ambientTemperature: normalized.temperature,
      packVoltage: normalized.voltage,
    });
  }
  lastBuzzerState = normalized.buzzerStatus;

  // 4. Protection threshold check
  await checkProtectionThresholds(normalized);

  // 5. Broadcast to connected clients over SSE
  broadcastSse('telemetry', normalized);

  return {
    success: true,
    stored,
    id: historyKey || `LOC-${Date.now().toString().slice(-6)}`,
    data: normalized,
    timestamp: normalized.timestamp,
  };
};

/**
 * Handles incoming real telemetry updates from Firebase listeners
 */
const handleTelemetryUpdate = (rawVal) => {
  const telemetry = normalizeTelemetry(rawVal);
  if (!telemetry) return;

  cachedLatestTelemetry = telemetry;

  if (lastFanState !== null && lastFanState !== telemetry.fanStatus) {
    if (telemetry.fanStatus === 'ON') {
      createAlertRecord({
        type: 'Cooling Fan Activation',
        severity: 'Info',
        sensorValue: 'Fan: ON',
        message: 'Cooling fan engaged to lower hardware/battery thermal dissipation.',
        aiExplanation: 'Automated cooling fan triggered due to elevated temperature or manual override.',
      });
    }
  }
  lastFanState = telemetry.fanStatus;

  if (lastBuzzerState !== null && lastBuzzerState !== telemetry.buzzerStatus) {
    if (telemetry.buzzerStatus === 'ON') {
      createAlertRecord({
        type: 'Buzzer Alarm Activation',
        severity: 'Warning',
        sensorValue: 'Buzzer: ON',
        message: 'Safety buzzer sounded due to active protection threshold or trip warning.',
        aiExplanation: 'Audible alarm siren engaged to alert operators of active threshold state.',
      });
    }
  }
  lastBuzzerState = telemetry.buzzerStatus;

  broadcastSse('telemetry', telemetry);
  checkProtectionThresholds(telemetry);
};

export const setupRealtimeListeners = () => {
  if (listening) return;
  if (!isFirebaseConfigured()) {
    console.warn('[Firebase Service] Firebase not configured; running in passive waiting mode.');
    listening = true;
    return;
  }

  try {
    const db = getDb();

    // 1. Listen to smart_bms/latest (primary schema)
    const smartBmsLatestRef = db.ref('smart_bms/latest');
    smartBmsLatestRef.on(
      'value',
      (snapshot) => {
        const val = snapshot.val();
        if (val) handleTelemetryUpdate(val);
      },
      (error) => {
        console.error('[Firebase Listener Error] smart_bms/latest:', error.message);
      }
    );

    // 2. Listen to telemetry/current (fallback)
    const telemetryRef = db.ref('telemetry/current');
    telemetryRef.on(
      'value',
      (snapshot) => {
        const val = snapshot.val();
        if (val) handleTelemetryUpdate(val);
      },
      (error) => {
        console.error('[Firebase Listener Error] telemetry/current:', error.message);
      }
    );

    // 3. Listen to smart_home (for IoT / ESP32 fallback)
    const smartHomeRef = db.ref('smart_home');
    smartHomeRef.on(
      'value',
      (snapshot) => {
        const val = snapshot.val();
        if (val) handleTelemetryUpdate(val);
      },
      (error) => {
        console.error('[Firebase Listener Error] smart_home:', error.message);
      }
    );

    listening = true;
    console.log('[Firebase Service] Active listeners attached to smart_bms/latest, telemetry/current and smart_home.');
  } catch (err) {
    console.error('[Firebase Listener Error] Failed to attach listeners:', err.message);
  }
};

export const getCurrentTelemetry = async () => {
  if (!isFirebaseConfigured()) {
    return { configured: false, data: cachedLatestTelemetry };
  }

  const db = getDb();

  // Try telemetry/current first
  let snapshot = await db.ref('telemetry/current').once('value');
  let data = snapshot.val();

  // If absent, try smart_home
  if (!data) {
    snapshot = await db.ref('smart_home').once('value');
    data = snapshot.val();
  }

  if (!data) {
    return { configured: true, data: null };
  }

  const normalized = normalizeTelemetry(data);
  cachedLatestTelemetry = normalized;
  return { configured: true, data: normalized };
};

/**
 * Fetches historical readings with date/time filters and window ranges
 */
export const getTelemetryHistory = async (options = {}) => {
  const limit = parseInt(options.limit || '50', 10);
  const range = options.range ? options.range.toLowerCase() : null;
  const startDate = options.startDate || options.from || null;
  const endDate = options.endDate || options.to || null;

  if (!isFirebaseConfigured()) {
    return { configured: false, data: [], filterApplied: Boolean(startDate || endDate || range) };
  }

  const db = getDb();

  // 1. Fetch records from telemetry/history
  let snapshot = await db
    .ref('telemetry/history')
    .limitToLast(Math.max(limit, 200))
    .once('value');

  let val = snapshot.val();

  // 2. Fallback to smart_home/history
  if (!val) {
    const shSnap = await db.ref('smart_home/history').limitToLast(Math.max(limit, 200)).once('value');
    val = shSnap.val();
  }

  if (!val) return { configured: true, data: [], count: 0 };

  let history = Object.keys(val).map((key) => {
    const item = val[key];
    const timeMs = typeof item.rawTimestamp === 'number'
      ? item.rawTimestamp
      : (typeof item.timestamp === 'number' 
          ? item.timestamp 
          : (item.timestamp ? new Date(item.timestamp).getTime() : Date.now()));

    const v = typeof item.voltage === 'number' ? item.voltage : (typeof item.packVoltage === 'number' ? item.packVoltage : null);
    const c = typeof item.current === 'number' ? item.current : null;
    const p = typeof item.power === 'number' ? item.power : ((v !== null && c !== null) ? parseFloat((v * c).toFixed(2)) : null);
    const t = typeof item.temperature === 'number' ? item.temperature : (typeof item.temp === 'number' ? item.temp : null);

    return {
      key,
      id: key,
      timestamp: new Date(timeMs).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      isoTimestamp: new Date(timeMs).toISOString(),
      date: new Date(timeMs).toLocaleDateString(),
      rawTimestamp: timeMs,
      voltage: v,
      current: c,
      power: p,
      temperature: t,
      fanStatus: item.fanStatus || 'OFF',
      buzzerStatus: item.buzzerStatus || 'OFF',
      soc: typeof item.soc === 'number' ? item.soc : null,
      soh: typeof item.soh === 'number' ? item.soh : null,
      status: item.status || 'ONLINE',
    };
  });

  // Apply Date Range / Window Filters
  const now = Date.now();
  if (range && range !== 'all') {
    const durationMap = {
      '1m': 60 * 1000,
      '10m': 10 * 60 * 1000,
      '1h': 60 * 60 * 1000,
      '24h': 24 * 60 * 60 * 1000,
      '7d': 7 * 24 * 60 * 60 * 1000,
      '30d': 30 * 24 * 60 * 60 * 1000,
    };
    const windowMs = durationMap[range] || (60 * 60 * 1000);
    const cutoff = now - windowMs;
    history = history.filter((h) => h.rawTimestamp >= cutoff);
  } else if (startDate || endDate) {
    const startMs = startDate ? new Date(startDate).getTime() : 0;
    const endMs = endDate ? new Date(endDate).getTime() : Infinity;
    history = history.filter((h) => h.rawTimestamp >= startMs && h.rawTimestamp <= endMs);
  }

  // Sort newest first and apply limit
  const sorted = history.sort((a, b) => b.rawTimestamp - a.rawTimestamp).slice(0, limit);

  return {
    configured: true,
    count: sorted.length,
    data: sorted,
    range: range || 'custom',
    filterApplied: Boolean(startDate || endDate || (range && range !== 'all')),
  };
};

/**
 * Retrieves alerts with multi-dimensional filtering (status, severity, date)
 */
export const getAlerts = async (filters = {}) => {
  const { statusFilter = null, severityFilter = null, startDate = null, endDate = null, limit = 50 } = filters;

  if (!isFirebaseConfigured()) {
    return { configured: false, data: [] };
  }

  const db = getDb();
  const snapshot = await db
    .ref('alerts')
    .limitToLast(Math.max(limit, 100))
    .once('value');

  const val = snapshot.val();
  if (!val) return { configured: true, data: [] };

  let alertsList = Object.keys(val).map((key) => ({
    firebaseKey: key,
    ...val[key],
  }));

  // Status Filter
  if (statusFilter && statusFilter !== 'ALL') {
    alertsList = alertsList.filter(
      (a) => a.status && a.status.toUpperCase() === statusFilter.toUpperCase()
    );
  }

  // Severity Filter
  if (severityFilter && severityFilter !== 'ALL') {
    alertsList = alertsList.filter(
      (a) => a.severity && a.severity.toUpperCase() === severityFilter.toUpperCase()
    );
  }

  // Date Range Filter
  if (startDate || endDate) {
    const startMs = startDate ? new Date(startDate).getTime() : 0;
    const endMs = endDate ? new Date(endDate).getTime() : Infinity;
    alertsList = alertsList.filter((a) => {
      const timeMs = a.timestamp ? new Date(a.timestamp).getTime() : 0;
      return timeMs >= startMs && timeMs <= endMs;
    });
  }

  return { configured: true, count: alertsList.length, data: alertsList.reverse().slice(0, limit) };
};

export const updateAlertStatusInDb = async (alertId, newStatus) => {
  if (!isFirebaseConfigured()) {
    return { configured: false, updated: false, notFound: true };
  }

  const db = getDb();
  const snapshot = await db.ref('alerts').once('value');
  const val = snapshot.val();

  if (!val) return { configured: true, updated: false };

  let targetKey = null;
  Object.keys(val).forEach((key) => {
    if (val[key].id === alertId || key === alertId) {
      targetKey = key;
    }
  });

  if (!targetKey) {
    return { configured: true, updated: false, notFound: true };
  }

  await db.ref(`alerts/${targetKey}`).update({
    status: newStatus.toUpperCase(),
    updatedAt: new Date().toISOString(),
  });

  return { configured: true, updated: true, targetKey };
};

export const acknowledgeAllAlertsInDb = async () => {
  if (!isFirebaseConfigured()) {
    return { configured: false, updated: true };
  }

  const db = getDb();
  const snapshot = await db.ref('alerts').once('value');
  const val = snapshot.val();

  if (!val) return { configured: true, updated: true };

  const updates = {};
  Object.keys(val).forEach((key) => {
    if (val[key].status === 'ACTIVE') {
      updates[`alerts/${key}/status`] = 'RESOLVED';
      updates[`alerts/${key}/updatedAt`] = new Date().toISOString();
    }
  });

  if (Object.keys(updates).length > 0) {
    await db.ref().update(updates);
  }

  return { configured: true, updated: true };
};

export const getDeviceStatusFromDb = async () => {
  if (!isFirebaseConfigured()) {
    return {
      configured: false,
      data: cachedLatestTelemetry ? {
        status: cachedLatestTelemetry.status,
        lastSeen: cachedLatestTelemetry.timestamp,
        firmwareVersion: cachedLatestTelemetry.firmwareVersion,
        rssi: cachedLatestTelemetry.rssi,
        sensorHealth: cachedLatestTelemetry.sensorHealth,
      } : null,
    };
  }

  const db = getDb();
  const snapshot = await db.ref('device/status').once('value');
  const data = snapshot.val();

  if (data) {
    return {
      configured: true,
      data: {
        ...data,
        sensorHealth: data.sensorHealth || {
          ina219: 'OK',
          dht11: 'OK',
          l298n: 'OK',
          buzzer: 'OK',
          oled: 'OK',
        },
      },
    };
  }

  // Fallback to current telemetry
  const telemetryRes = await getCurrentTelemetry();
  if (telemetryRes.data) {
    return {
      configured: true,
      data: {
        status: telemetryRes.data.status,
        lastSeen: telemetryRes.data.timestamp,
        firmwareVersion: telemetryRes.data.firmwareVersion,
        rssi: telemetryRes.data.rssi,
        sensorHealth: telemetryRes.data.sensorHealth,
      },
    };
  }

  return { configured: true, data: null };
};

export const updateDeviceStatusInDb = async (statusData = {}) => {
  const payload = {
    status: statusData.status || 'ONLINE',
    lastSeen: new Date().toISOString(),
    firmwareVersion: statusData.firmwareVersion || 'ESP-BMS-v1.4.2',
    rssi: statusData.rssi ?? -58,
    ipAddress: statusData.ipAddress || '192.168.1.184',
    uptimeSeconds: statusData.uptimeSeconds || 84320,
    sensorHealth: statusData.sensorHealth || {
      ina219: 'OK',
      dht11: 'OK',
      l298n: 'OK',
      buzzer: 'OK',
      oled: 'OK',
    },
  };

  if (!isFirebaseConfigured()) {
    return { configured: false, updated: true, data: payload };
  }

  const db = getDb();
  await db.ref('device/status').set(payload);
  return { configured: true, updated: true, data: payload };
};

export const getDeviceControlStateFromDb = async () => {
  if (!isFirebaseConfigured()) {
    return {
      configured: false,
      data: {
        fan: 'OFF',
        buzzer: 'OFF',
        message: '',
        online: false,
        status: 'OFFLINE',
        lastSeen: null,
      },
    };
  }

  const db = getDb();
  const shSnap = await db.ref('smart_home').once('value');
  const shVal = shSnap.val() || {};

  const devSnap = await db.ref('device').once('value');
  const devVal = devSnap.val() || {};

  const fanStatus = shVal.fanStatus || (devVal.fan === true ? 'ON' : 'OFF');
  const buzzerStatus = shVal.buzzerStatus || (devVal.buzzer === true ? 'ON' : 'OFF');

  return {
    configured: true,
    data: {
      fan: fanStatus,
      buzzer: buzzerStatus,
      message: typeof devVal.message === 'string' ? devVal.message : '',
      online: Boolean(shVal.updatedAt || devVal.online),
      status: shVal.status || 'ONLINE',
      lastSeen: shVal.updatedAt ? new Date(shVal.updatedAt).toISOString() : devVal.lastSeen || null,
    },
  };
};

export const updateDeviceFanInDb = async (fanState, triggeredBy = 'manual') => {
  const fanStr = (fanState === true || fanState === 'ON' || fanState === '1') ? 'ON' : 'OFF';

  if (!isFirebaseConfigured()) {
    await recordActuatorEvent({ actuator: 'fan', state: fanStr, triggeredBy });
    return { configured: false, updated: true, fan: fanStr };
  }

  const db = getDb();
  await db.ref('smart_home').update({
    fanStatus: fanStr,
    fan: fanStr === 'ON',
    updatedAt: Date.now(),
  });

  await recordActuatorEvent({
    actuator: 'fan',
    state: fanStr,
    triggeredBy,
    ambientTemperature: cachedLatestTelemetry?.temperature ?? null,
    packVoltage: cachedLatestTelemetry?.voltage ?? null,
  });

  return { configured: true, updated: true, fan: fanStr };
};

export const updateDeviceBuzzerInDb = async (buzzerState, triggeredBy = 'manual') => {
  const buzzerStr = (buzzerState === true || buzzerState === 'ON' || buzzerState === '1') ? 'ON' : 'OFF';

  if (!isFirebaseConfigured()) {
    await recordActuatorEvent({ actuator: 'buzzer', state: buzzerStr, triggeredBy });
    return { configured: false, updated: true, buzzer: buzzerStr };
  }

  const db = getDb();
  await db.ref('smart_home').update({
    buzzerStatus: buzzerStr,
    buzzer: buzzerStr === 'ON',
    updatedAt: Date.now(),
  });

  await db.ref('device').update({
    buzzer: buzzerStr === 'ON',
    updatedAt: new Date().toISOString(),
  });

  await recordActuatorEvent({
    actuator: 'buzzer',
    state: buzzerStr,
    triggeredBy,
    ambientTemperature: cachedLatestTelemetry?.temperature ?? null,
    packVoltage: cachedLatestTelemetry?.voltage ?? null,
  });

  return { configured: true, updated: true, buzzer: buzzerStr };
};

export const updateDeviceMessageInDb = async (message) => {
  if (!isFirebaseConfigured()) {
    return { configured: false, updated: true, message };
  }

  const db = getDb();
  await db.ref('device').update({
    message: String(message),
    updatedAt: new Date().toISOString(),
  });

  return { configured: true, updated: true, message };
};

/**
 * Persists an AI Diagnostics Prediction into Firebase RTDB
 */
export const saveAiPredictionToDb = async (predictionData) => {
  const aiRecord = {
    id: `AI-${Date.now().toString().slice(-6)}`,
    modelVersion: predictionData.modelMetadata?.version || 'v2.0.0',
    outputCategory: predictionData.riskLevel || 'Normal',
    riskLevel: predictionData.riskLevel || 'Normal',
    explanation: predictionData.mainDetectedReason || '',
    recommendedAction: predictionData.recommendedAction || '',
    confidence: predictionData.confidence ?? (predictionData.failureProbability ? parseFloat((1 - (predictionData.failureProbability / 200)).toFixed(2)) : 0.95),
    failureProbability: predictionData.failureProbability || 0,
    sohPercentage: predictionData.sohPercentage || null,
    risks: predictionData.risks || {},
    rawMetrics: predictionData.rawMetrics || {},
    timestamp: new Date().toISOString(),
    rawTimestamp: Date.now(),
  };

  if (!isFirebaseConfigured()) {
    return { configured: false, saved: true, data: aiRecord };
  }

  const db = getDb();
  const ref = db.ref('ai_results').push();
  await ref.set(aiRecord);
  await db.ref('ai_results/latest').set(aiRecord);

  return { configured: true, saved: true, id: ref.key, data: aiRecord };
};

/**
 * Retrieves past AI diagnostics prediction records
 */
export const getAiResultsFromDb = async (limit = 20) => {
  if (!isFirebaseConfigured()) {
    return { configured: false, data: [] };
  }

  const db = getDb();
  const snapshot = await db.ref('ai_results').limitToLast(limit).once('value');
  const val = snapshot.val();
  if (!val) return { configured: true, data: [] };

  const list = Object.keys(val)
    .filter((k) => k !== 'latest')
    .map((k) => ({
      key: k,
      ...val[k],
    }));

  return { configured: true, count: list.length, data: list.reverse() };
};

/**
 * Retrieves reports from Firebase
 */
export const getReportsFromDb = async (limit = 20) => {
  if (!isFirebaseConfigured()) {
    return { configured: false, data: [] };
  }

  const db = getDb();
  const snapshot = await db
    .ref('reports')
    .limitToLast(limit)
    .once('value');

  const val = snapshot.val();
  if (!val) return { configured: true, data: [] };

  const reportsList = Object.keys(val).map((key) => ({
    key,
    ...val[key],
  }));

  return { configured: true, count: reportsList.length, data: reportsList.reverse() };
};

/**
 * Retrieves single report by ID
 */
export const getReportByIdFromDb = async (reportId) => {
  if (!isFirebaseConfigured()) {
    return { configured: false, data: null };
  }

  const db = getDb();
  const snapshot = await db.ref('reports').once('value');
  const val = snapshot.val();
  if (!val) return { configured: true, data: null };

  let found = null;
  Object.keys(val).forEach((k) => {
    if (k === reportId || val[k].id === reportId) {
      found = { key: k, ...val[k] };
    }
  });

  return { configured: true, data: found };
};

export const saveReportToDb = async (reportData) => {
  if (!isFirebaseConfigured()) {
    return { configured: false, saved: true, key: reportData.id };
  }

  const db = getDb();
  const reportsRef = db.ref('reports');
  const newRef = reportsRef.push();
  await newRef.set(reportData);

  return { configured: true, saved: true, key: newRef.key };
};
