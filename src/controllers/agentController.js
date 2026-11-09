import { 
  extractBackendFeatures, 
  runInference, 
  predictFromFirebaseTelemetry 
} from '../services/agentService.js';
import { 
  saveAiPredictionToDb, 
  getAiResultsFromDb 
} from '../services/firebaseService.js';

/**
 * POST /api/agent/predict
 * Receives feature vector or historical readings from client,
 * executes ML model, persists AI result to Firebase, and returns failure risk & recommendations.
 */
export const predictBatteryFailure = async (req, res, next) => {
  try {
    const { history, currentReading, features, rawMetrics } = req.body || {};

    let prediction;
    if (features && rawMetrics) {
      prediction = runInference({ features, rawMetrics });
    } else {
      const extracted = extractBackendFeatures(history || [], currentReading || null);
      prediction = runInference(extracted);
    }

    // Persist AI inference result to Firebase RTDB
    await saveAiPredictionToDb(prediction);

    res.status(200).json({
      success: true,
      data: prediction,
    });
  } catch (err) {
    next(err);
  }
};

/**
 * GET /api/agent/predict
 * Automatically pulls recent Firebase readings, executes ML prediction, and stores result
 */
export const predictFromFirebase = async (req, res, next) => {
  try {
    const prediction = await predictFromFirebaseTelemetry();

    // Persist AI inference result to Firebase RTDB
    await saveAiPredictionToDb(prediction);

    res.status(200).json({
      success: true,
      data: prediction,
    });
  } catch (err) {
    next(err);
  }
};

/**
 * GET /api/agent/results
 * GET /api/agent/history
 * Fetch historical AI diagnostic predictions from Firebase
 */
export const getAiResults = async (req, res, next) => {
  try {
    const limit = parseInt(req.query.limit || '20', 10);
    const result = await getAiResultsFromDb(limit);

    res.status(200).json({
      success: true,
      count: result.data.length,
      data: result.data,
    });
  } catch (err) {
    next(err);
  }
};
