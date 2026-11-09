import express from 'express';
import { getDb, isFirebaseConfigured } from '../config/firebase.js';

const router = express.Router();
const RAG_SERVICE_URL = process.env.RAG_SERVICE_URL || 'http://127.0.0.1:8000';

/**
 * Helper to fetch from Python RAG FastAPI service
 */
async function fetchFromRagService(endpoint, options = {}) {
  const url = `${RAG_SERVICE_URL}${endpoint}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    signal: AbortSignal.timeout(15000),
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`RAG Service Error ${res.status}: ${errorText}`);
  }
  return await res.json();
}

/**
 * GET /api/rag/health
 */
router.get('/health', async (req, res, next) => {
  try {
    const data = await fetchFromRagService('/health');
    res.status(200).json(data);
  } catch (err) {
    res.status(503).json({
      status: 'DEGRADED',
      ragService: 'UNAVAILABLE',
      error: err.message,
    });
  }
});

/**
 * GET /api/rag/battery-specs
 */
router.get('/battery-specs', async (req, res, next) => {
  try {
    const data = await fetchFromRagService('/api/battery-specs');
    res.status(200).json(data);
  } catch (err) {
    next(err);
  }
});

/**
 * POST /api/rag/battery-specs/select
 */
router.post('/battery-specs/select', async (req, res, next) => {
  try {
    const data = await fetchFromRagService('/api/battery-specs/select', {
      method: 'POST',
      body: JSON.stringify(req.body),
    });
    res.status(200).json(data);
  } catch (err) {
    next(err);
  }
});

/**
 * POST /api/rag/battery-specs/custom
 */
router.post('/battery-specs/custom', async (req, res, next) => {
  try {
    const data = await fetchFromRagService('/api/battery-specs/custom', {
      method: 'POST',
      body: JSON.stringify(req.body),
    });
    res.status(200).json(data);
  } catch (err) {
    next(err);
  }
});

/**
 * POST /api/rag/analyze
 * Executes RAG analysis and optionally persists to Firebase RTDB (/smart_bms/rag_analysis)
 */
router.post('/analyze', async (req, res, next) => {
  try {
    const ragResponse = await fetchFromRagService('/api/rag/analyze', {
      method: 'POST',
      body: JSON.stringify(req.body || {}),
    });

    // Optionally persist to Firebase RTDB
    if (isFirebaseConfigured() && ragResponse.data) {
      try {
        const db = getDb();
        await db.ref('smart_bms/rag_analysis').set(ragResponse.data);
      } catch (fbErr) {
        console.warn('[Firebase RTDB] Failed to cache RAG analysis:', fbErr.message);
      }
    }

    res.status(200).json(ragResponse);
  } catch (err) {
    next(err);
  }
});

/**
 * GET /api/rag/latest
 */
router.get('/latest', async (req, res, next) => {
  try {
    const data = await fetchFromRagService('/api/rag/latest');
    res.status(200).json(data);
  } catch (err) {
    next(err);
  }
});

/**
 * GET /api/rag/knowledge-base
 */
router.get('/knowledge-base', async (req, res, next) => {
  try {
    const query = req.query.query ? `?query=${encodeURIComponent(req.query.query)}` : '';
    const data = await fetchFromRagService(`/api/rag/knowledge-base${query}`);
    res.status(200).json(data);
  } catch (err) {
    next(err);
  }
});

/**
 * POST /api/rag/query
 */
router.post('/query', async (req, res, next) => {
  try {
    const data = await fetchFromRagService('/api/rag/query', {
      method: 'POST',
      body: JSON.stringify(req.body || {}),
    });
    res.status(200).json(data);
  } catch (err) {
    next(err);
  }
});

// =========================================================================
// REPORTS & PDF GENERATION PROXY ROUTES
// =========================================================================

/**
 * POST /api/rag/reports/generate
 */
router.post('/reports/generate', async (req, res, next) => {
  try {
    const data = await fetchFromRagService('/api/reports/generate', {
      method: 'POST',
      body: JSON.stringify(req.body || {}),
    });
    res.status(200).json(data);
  } catch (err) {
    next(err);
  }
});

/**
 * GET /api/rag/reports/history
 */
router.get('/reports/history', async (req, res, next) => {
  try {
    const data = await fetchFromRagService('/api/reports/history');
    res.status(200).json(data);
  } catch (err) {
    next(err);
  }
});

/**
 * GET /api/rag/reports/:id/download
 */
router.get('/reports/:id/download', async (req, res, next) => {
  try {
    const url = `${RAG_SERVICE_URL}/api/reports/${encodeURIComponent(req.params.id)}/download`;
    const backendRes = await fetch(url);
    if (!backendRes.ok) {
      return res.status(backendRes.status).send(await backendRes.text());
    }
    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Disposition', `attachment; filename="${req.params.id}.pdf"`);
    const buffer = await backendRes.arrayBuffer();
    res.send(Buffer.from(buffer));
  } catch (err) {
    next(err);
  }
});

/**
 * GET /api/rag/reports/:id/preview
 */
router.get('/reports/:id/preview', async (req, res, next) => {
  try {
    const url = `${RAG_SERVICE_URL}/api/reports/${encodeURIComponent(req.params.id)}/preview`;
    const backendRes = await fetch(url);
    if (!backendRes.ok) {
      return res.status(backendRes.status).send(await backendRes.text());
    }
    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Disposition', 'inline');
    const buffer = await backendRes.arrayBuffer();
    res.send(Buffer.from(buffer));
  } catch (err) {
    next(err);
  }
});

/**
 * POST /api/rag/reports/:id/email
 */
router.post('/reports/:id/email', async (req, res, next) => {
  try {
    const data = await fetchFromRagService(`/api/reports/${encodeURIComponent(req.params.id)}/email`, {
      method: 'POST',
      body: JSON.stringify(req.body || {}),
    });
    res.status(200).json(data);
  } catch (err) {
    next(err);
  }
});

// =========================================================================
// ALERT SETTINGS & DAEMON PROXY ROUTES
// =========================================================================

/**
 * GET /api/rag/alerts/settings
 */
router.get('/alerts/settings', async (req, res, next) => {
  try {
    const data = await fetchFromRagService('/api/alerts/settings');
    res.status(200).json(data);
  } catch (err) {
    next(err);
  }
});

/**
 * POST /api/rag/alerts/settings
 */
router.post('/alerts/settings', async (req, res, next) => {
  try {
    const data = await fetchFromRagService('/api/alerts/settings', {
      method: 'POST',
      body: JSON.stringify(req.body || {}),
    });
    res.status(200).json(data);
  } catch (err) {
    next(err);
  }
});

/**
 * GET /api/rag/alerts/history
 */
router.get('/alerts/history', async (req, res, next) => {
  try {
    const data = await fetchFromRagService('/api/alerts/history');
    res.status(200).json(data);
  } catch (err) {
    next(err);
  }
});

/**
 * POST /api/rag/alerts/test
 */
router.post('/alerts/test', async (req, res, next) => {
  try {
    const data = await fetchFromRagService('/api/alerts/test', {
      method: 'POST',
      body: JSON.stringify(req.body || {}),
    });
    res.status(200).json(data);
  } catch (err) {
    next(err);
  }
});

export default router;
