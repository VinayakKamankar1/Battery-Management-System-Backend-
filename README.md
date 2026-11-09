# Smart BMS Backend Service ⚡

Lightweight, modular Node.js + Express backend service for the **Smart Battery Management System (BMS)**, powered by **Firebase Realtime Database** and **Server-Sent Events (SSE)**.

---

## 🏗️ System Architecture

```
ESP32 Hardware Sensors
       │
       ▼
Firebase Realtime Database
       │
       ▼
Node.js + Express Backend Service
  ├── REST APIs (Battery, Alerts, Device, Reports)
  └── SSE Real-time Streaming (/api/battery/stream)
       │
       ▼
Existing React BMS Frontend & Future AI Agent
```

---

## 🛠️ Tech Stack & Features

- **Node.js & Express**: ES Module based lightweight REST API framework.
- **Firebase Admin SDK**: Real-time synchronization with Firebase Realtime Database.
- **Server-Sent Events (SSE)**: Low-latency push notifications for telemetry and automated protection alerts.
- **Automated Protection Alert Monitoring**: Automatically checks for:
  - Over-voltage Protection (OVP) (`> 54.0V`)
  - Under-voltage Protection (UVP) (`< 40.0V`)
  - Over-current Protection (OCP) (`> 40.0A`)
  - Overheating Protection (OTP) (`> 45.0°C`)
- **Input Validation**: `express-validator` middleware for payload sanity.
- **Graceful Fault Tolerance**: Operates cleanly without crashing if Firebase credentials are missing or empty, returning clear `"No data available in Firebase"` responses.

---

## 📁 Directory Structure

```
backend/
├── src/
│   ├── config/
│   │   └── firebase.js          # Firebase Admin SDK initialization & fallback logic
│   ├── services/
│   │   ├── firebaseService.js   # DB queries for telemetry, history, alerts, reports
│   │   ├── alertService.js      # Automated protection threshold monitor & alert generator
│   │   └── sseService.js        # Server-Sent Events client manager & broadcaster
│   ├── middleware/
│   │   ├── validation.js        # Request body validators
│   │   └── errorHandler.js      # Global error and 404 handlers
│   ├── controllers/
│   │   ├── batteryController.js # Battery current, history, health, & stream controllers
│   │   ├── alertController.js   # Alert management controllers
│   │   ├── deviceController.js  # Device status controller
│   │   └── reportController.js  # Report generation controllers
│   ├── routes/
│   │   ├── batteryRoutes.js     # /api/battery/* endpoints
│   │   ├── alertRoutes.js       # /api/alerts/* endpoints
│   │   ├── deviceRoutes.js      # /api/device/* endpoints
│   │   └── reportRoutes.js      # /api/reports/* endpoints
│   └── server.js                # Express app entrypoint & route setup
├── .env.example                 # Template for environment variables
├── .env                         # Local environment variables (do not commit)
├── .gitignore                   # Git ignore patterns
├── package.json                 # Dependencies and scripts
└── README.md                    # Setup and documentation
```

---

## 🔑 Firebase Setup Guide

### 1. Create Firebase Realtime Database
1. Go to the [Firebase Console](https://console.firebase.google.com/).
2. Create a new project or select an existing one.
3. In the left navigation, open **Build** ➔ **Realtime Database**.
4. Click **Create Database**, select a region, and start in **Test mode** (or configure security rules).
5. Copy your Realtime Database URL (e.g., `https://your-project-id-default-rtdb.firebaseio.com`).

### 2. Generate Admin Service Account Credentials
1. In Firebase Console, go to **Project Settings** (gear icon) ➔ **Service accounts**.
2. Click **Generate new private key**. A `.json` file will download to your computer.
3. Save this JSON file inside the `backend/` directory as `serviceAccountKey.json`.

---

## ⚙️ Environment Variables Setup

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Update your `.env` file:

```env
PORT=5000
NODE_ENV=development

# Realtime Database URL
FIREBASE_DATABASE_URL=https://your-project-id-default-rtdb.firebaseio.com

# Path to service account key file
FIREBASE_SERVICE_ACCOUNT_PATH=./serviceAccountKey.json

# BMS Protection Alert Thresholds
OVP_THRESHOLD=54.0
UVP_THRESHOLD=40.0
OCP_THRESHOLD=40.0
OTP_THRESHOLD=45.0
```

---

## 🚀 Running the Backend

### 1. Install Dependencies
```bash
cd backend
npm install
```

### 2. Start Development Server
```bash
npm run dev
```
The server will start on `http://localhost:5000`.

---

## 📡 API Reference

### 1. Battery Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/battery/current` | `GET` | Returns latest real-time battery readings from `/telemetry/current` |
| `/api/battery/history` | `GET` | Returns historical telemetry readings (Query param: `?limit=50`) |
| `/api/battery/health` | `GET` | Returns calculated SOH, SOC, min/max/avg voltage and temp stats |
| `/api/battery/stream` | `GET` | **SSE Stream**: Pushes live `telemetry` and `alert` updates to clients |

#### Example Response (`GET /api/battery/current`)
```json
{
  "success": true,
  "data": {
    "soc": 87,
    "voltage": 48.24,
    "current": 12.5,
    "temperature": 31.4,
    "mode": "Charging",
    "status": "ONLINE",
    "timestamp": "2026-09-17T14:30:00.000Z"
  }
}
```

---

### 2. Alert Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/alerts` | `GET` | Returns alerts list (Query params: `?status=ACTIVE`, `?limit=50`) |
| `/api/alerts` | `POST` | Log a new alert |
| `/api/alerts/:id` | `PATCH` | Update alert status (`ACTIVE`, `RESOLVED`, `ACKNOWLEDGED`) |

#### Example Request (`POST /api/alerts`)
```json
{
  "type": "Overheating",
  "severity": "Warning",
  "sensorValue": "46.2 °C",
  "message": "Thermal threshold exceeded during charging"
}
```

---

### 3. Device & Report Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/device/status` | `GET` | Connection state, firmware version, RSSI, and last-seen timestamp |
| `/api/reports` | `GET` | Fetch list of generated summary reports |
| `/api/reports` | `POST` | Generate and save a summary report for a period (`1h`, `24h`, `7d`, `30d`) |

---

## 🔌 Connecting Existing Frontend to Backend

In your React frontend application:

### 1. Fetching REST Data
```javascript
// Fetch Current Battery Status
const response = await fetch('http://localhost:5000/api/battery/current');
const result = await response.json();
if (result.success && result.data) {
  setBatteryState(result.data);
}
```

### 2. Connecting Real-time SSE Stream
```javascript
useEffect(() => {
  const eventSource = new EventSource('http://localhost:5000/api/battery/stream');

  eventSource.addEventListener('telemetry', (event) => {
    const data = JSON.parse(event.data);
    setBatteryState(data);
  });

  eventSource.addEventListener('alert', (event) => {
    const newAlert = JSON.parse(event.data);
    setAlerts((prev) => [newAlert, ...prev]);
  });

  return () => eventSource.close();
}, []);
```

---

## 🗄️ Firebase Realtime Database Data Schema

For ESP32 hardware to write to Firebase:

### `/telemetry/current` (Single object)
```json
{
  "soc": 85,
  "voltage": 48.1,
  "current": 12.0,
  "temperature": 32.1,
  "mode": "Charging",
  "deviceStatus": "ONLINE",
  "timestamp": 1726563600000
}
```

### `/telemetry/history` (Pushed list)
```json
{
  "-Nxxx1": {
    "voltage": 48.1,
    "current": 12.0,
    "temperature": 32.1,
    "soc": 85,
    "mode": "Charging",
    "timestamp": 1726563600000
  }
}
```
