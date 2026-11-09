import express from 'express';
import {
  predictBatteryFailure,
  predictFromFirebase,
  getAiResults,
} from '../controllers/agentController.js';

const router = express.Router();

router.post('/predict', predictBatteryFailure);
router.get('/predict', predictFromFirebase);
router.get('/results', getAiResults);
router.get('/history', getAiResults);

export default router;
