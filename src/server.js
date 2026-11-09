import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';

import batteryRoutes from './routes/batteryRoutes.js';
import alertRoutes from './routes/alertRoutes.js';
import deviceRoutes from './routes/deviceRoutes.js';
import reportRoutes from './routes/reportRoutes.js';
import agentRoutes from './routes/agentRoutes.js';
import ragRoutes from './routes/ragRoutes.js';

import { requestLogger } from './middleware/logger.js';
import { errorHandler, notFoundHandler } from './middleware/errorHandler.js';
import { setupRealtimeListeners } from './services/firebaseService.js';
import { isFirebaseConfigured } from './config/firebase.js';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 5000;

// Enable CORS
app.use(
  cors({
    origin: '*',
    methods: ['GET', 'POST', 'PATCH', 'PUT', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization'],
  })
);

// Body Parsers
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Structured Request Logger
app.use(requestLogger);

// Server API Status / Health Check
app.get('/api', (req, res) => {
  res.status(200).json({
    name: 'Smart BMS Backend API',
    version: '1.4.2',
    status: 'ONLINE',
    firebaseConnected: isFirebaseConfigured(),
    databaseType: 'Firebase Realtime Database',
    timestamp: new Date().toISOString(),
    endpoints: {
      ingestReading: 'POST /api/battery/ingest',
      latestReading: 'GET /api/battery/current',
      historicalReadings: 'GET /api/battery/history?range=1h&limit=50',
      deviceStatus: 'GET /api/device/status',
      actuatorEvents: 'GET /api/device/actuators',
      fanControl: 'POST /api/device/fan',
      buzzerControl: 'POST /api/device/buzzer',
      alertsList: 'GET /api/alerts?status=ACTIVE',
      reportsList: 'GET /api/reports',
      aiPredict: 'POST /api/agent/predict',
      aiHistory: 'GET /api/agent/results',
      sseStream: 'GET /api/battery/stream',
    },
  });
});

app.get('/api/health', (req, res) => {
  res.status(200).json({
    status: 'HEALTHY',
    firebase: isFirebaseConfigured() ? 'CONNECTED' : 'DISCONNECTED',
    uptimeSeconds: Math.floor(process.uptime()),
    timestamp: new Date().toISOString(),
  });
});

// API Routes
app.use('/api/battery', batteryRoutes);
app.use('/api/alerts', alertRoutes);
app.use('/api/device', deviceRoutes);
app.use('/api/reports', reportRoutes);
app.use('/api/agent', agentRoutes);
app.use('/api/rag', ragRoutes);

// Error Handling Middleware
app.use(notFoundHandler);
app.use(errorHandler);

// Start Server
app.listen(PORT, () => {
  console.log(`=================================================`);
  console.log(`⚡ Smart BMS Backend running on http://localhost:${PORT}`);
  console.log(`⚡ Firebase Realtime Database: ${isFirebaseConfigured() ? 'CONNECTED' : 'UNCONFIGURED'}`);
  console.log(`=================================================`);

  // Attach Firebase listeners if connected
  setupRealtimeListeners();
});
