import express from 'express';
import {
  getCurrentBattery,
  getBatteryHistory,
  getBatteryHealth,
  streamBatteryData,
  ingestBatteryData,
} from '../controllers/batteryController.js';
import {
  validateIngestReading,
  validateHistoryQuery,
} from '../middleware/validation.js';

const router = express.Router();

// Data Ingestion Endpoints (NodeMCU ESP8266 & Web Simulators)
router.post('/ingest', validateIngestReading, ingestBatteryData);
router.post('/reading', validateIngestReading, ingestBatteryData);

// Retrieval Endpoints
router.get('/current', getCurrentBattery);
router.get('/telemetry', getCurrentBattery);
router.get('/history', validateHistoryQuery, getBatteryHistory);
router.get('/health', getBatteryHealth);
router.get('/stream', streamBatteryData);

export default router;
