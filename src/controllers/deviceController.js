import {
  getDeviceStatusFromDb,
  updateDeviceStatusInDb,
  getCurrentTelemetry,
  getDeviceControlStateFromDb,
  updateDeviceMessageInDb,
  updateDeviceBuzzerInDb,
  updateDeviceFanInDb,
  getActuatorEvents,
} from '../services/firebaseService.js';

/**
 * GET /api/device/status
 * Get device status, connectivity, sensor health, and firmware version
 */
export const getDeviceStatus = async (req, res, next) => {
  try {
    const result = await getDeviceStatusFromDb();

    if (!result.data) {
      const telemetryRes = await getCurrentTelemetry();
      if (telemetryRes.data) {
        return res.status(200).json({
          success: true,
          data: {
            status: telemetryRes.data.status || 'ONLINE',
            lastSeen: telemetryRes.data.timestamp || new Date().toISOString(),
            firmwareVersion: telemetryRes.data.firmwareVersion || 'ESP-BMS-v1.4.2',
            rssi: telemetryRes.data.rssi ?? -58,
            sensorHealth: telemetryRes.data.sensorHealth || {
              ina219: 'OK',
              dht11: 'OK',
              l298n: 'OK',
              buzzer: 'OK',
              oled: 'OK',
            },
          },
        });
      }

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
 * POST /api/device/status
 * Update device connection state, last seen, and sensor health
 */
export const updateDeviceStatus = async (req, res, next) => {
  try {
    const result = await updateDeviceStatusInDb(req.body);

    res.status(200).json({
      success: true,
      message: 'Device status and sensor health updated successfully',
      data: result.data,
    });
  } catch (err) {
    next(err);
  }
};

/**
 * GET /api/device/control
 * Get current fan, buzzer state, OLED message, and connectivity
 */
export const getDeviceControl = async (req, res, next) => {
  try {
    const result = await getDeviceControlStateFromDb();
    res.status(200).json({
      success: true,
      configured: result.configured,
      data: result.data,
    });
  } catch (err) {
    next(err);
  }
};

/**
 * GET /api/device/actuators
 * Get actuator events history (fan and buzzer state changes)
 */
export const getActuatorEventsHistory = async (req, res, next) => {
  try {
    const limit = parseInt(req.query.limit || '50', 10);
    const result = await getActuatorEvents(limit);

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
 * POST /api/device/fan
 * Toggle fan state ('ON' / 'OFF')
 */
export const updateFan = async (req, res, next) => {
  try {
    const { fan, state } = req.body;
    const targetState = typeof fan !== 'undefined' ? fan : state;

    if (typeof targetState === 'undefined') {
      return res.status(400).json({ success: false, error: 'Fan boolean or ON/OFF payload required' });
    }

    const result = await updateDeviceFanInDb(targetState, req.body.triggeredBy || 'manual_override');
    res.status(200).json({
      success: true,
      configured: result.configured,
      message: `Cooling fan set to ${result.fan} successfully`,
      data: { fan: result.fan },
    });
  } catch (err) {
    next(err);
  }
};

/**
 * POST /api/device/buzzer
 * Update device/buzzer (true/false or 'ON'/'OFF') in Firebase
 */
export const updateBuzzer = async (req, res, next) => {
  try {
    const { buzzer, state } = req.body;
    const targetState = typeof buzzer !== 'undefined' ? buzzer : state;

    if (typeof targetState === 'undefined') {
      return res.status(400).json({ success: false, error: 'Buzzer boolean payload required' });
    }

    const result = await updateDeviceBuzzerInDb(targetState, req.body.triggeredBy || 'manual_override');
    res.status(200).json({
      success: true,
      configured: result.configured,
      message: `Buzzer turned ${result.buzzer} successfully`,
      data: { buzzer: result.buzzer },
    });
  } catch (err) {
    next(err);
  }
};

/**
 * POST /api/device/message
 * Update device/message in Firebase
 */
export const updateMessage = async (req, res, next) => {
  try {
    const { message } = req.body;
    if (typeof message === 'undefined') {
      return res.status(400).json({ success: false, error: 'Message payload required' });
    }

    const result = await updateDeviceMessageInDb(message);
    res.status(200).json({
      success: true,
      configured: result.configured,
      message: 'OLED message updated successfully',
      data: { message },
    });
  } catch (err) {
    next(err);
  }
};
