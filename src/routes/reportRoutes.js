import express from 'express';
import { getReports, getReportById, createReport } from '../controllers/reportController.js';
import { validateCreateReport } from '../middleware/validation.js';

const router = express.Router();

router.get('/', getReports);
router.get('/:id', getReportById);
router.post('/', validateCreateReport, createReport);

export default router;
