import express from 'express';
import {
  getDeviceStatus,
  updateDeviceStatus,
  getDeviceControl,
  getActuatorEventsHistory,
  updateMessage,
  updateBuzzer,
  updateFan,
} from '../controllers/deviceController.js';
import { validateDeviceStatus } from '../middleware/validation.js';

const router = express.Router();

router.get('/status', getDeviceStatus);
router.post('/status', validateDeviceStatus, updateDeviceStatus);
router.patch('/status', validateDeviceStatus, updateDeviceStatus);

router.get('/control', getDeviceControl);
router.get('/actuators', getActuatorEventsHistory);
router.get('/actuator-events', getActuatorEventsHistory);

router.post('/message', updateMessage);
router.post('/buzzer', updateBuzzer);
router.post('/fan', updateFan);

export default router;
