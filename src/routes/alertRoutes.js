import express from 'express';
import {
  getAlertsList,
  createAlert,
  updateAlert,
  acknowledgeAllAlertsController,
} from '../controllers/alertController.js';
import {
  validateCreateAlert,
  validateUpdateAlertStatus,
  validateAlertsQuery,
} from '../middleware/validation.js';

const router = express.Router();

router.get('/', validateAlertsQuery, getAlertsList);
router.post('/', validateCreateAlert, createAlert);
router.patch('/:id', validateUpdateAlertStatus, updateAlert);
router.post('/acknowledge', acknowledgeAllAlertsController);

export default router;
