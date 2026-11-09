import admin from 'firebase-admin';
import fs from 'fs';
import path from 'path';
import dotenv from 'dotenv';

dotenv.config();

let db = null;
let initialized = false;

class FirebaseRestDbRef {
  constructor(baseUrl, authSecret, pathStr = '') {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.authSecret = authSecret || '';
    this.pathStr = pathStr.replace(/^\//, '');
  }

  getUrl(params = {}) {
    const cleanPath = this.pathStr ? `/${this.pathStr}.json` : '/.json';
    const url = new URL(`${this.baseUrl}${cleanPath}`);
    if (this.authSecret) {
      url.searchParams.set('auth', this.authSecret);
    }
    Object.keys(params).forEach((k) => url.searchParams.set(k, params[k]));
    return url.toString();
  }

  async once(eventType = 'value') {
    const res = await fetch(this.getUrl(), { signal: AbortSignal.timeout(5000) });
    if (!res.ok) throw new Error(`Firebase REST HTTP Error ${res.status}`);
    const data = await res.json();
    return {
      val: () => data,
    };
  }

  on(eventType = 'value', callback, errorCb) {
    let active = true;
    const poll = async () => {
      if (!active) return;
      try {
        const snap = await this.once(eventType);
        callback(snap);
      } catch (err) {
        if (errorCb) errorCb(err);
      }
    };
    poll();
    const interval = setInterval(poll, 4000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }

  async update(data) {
    const res = await fetch(this.getUrl(), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(`Firebase REST PATCH Error ${res.status}`);
    return res.json();
  }

  async set(data) {
    const res = await fetch(this.getUrl(), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(`Firebase REST PUT Error ${res.status}`);
    return res.json();
  }

  push() {
    const newKey = '-K' + Date.now().toString(36) + Math.random().toString(36).substring(2, 7);
    const childRef = new FirebaseRestDbRef(this.baseUrl, this.authSecret, `${this.pathStr}/${newKey}`);
    return {
      key: newKey,
      set: (data) => childRef.set(data),
    };
  }

  orderByChild(child) {
    return this;
  }

  limitToLast(limit) {
    return this;
  }
}

class FirebaseRestDb {
  constructor(baseUrl, authSecret) {
    this.baseUrl = baseUrl;
    this.authSecret = authSecret;
  }

  ref(pathStr = '') {
    return new FirebaseRestDbRef(this.baseUrl, this.authSecret, pathStr);
  }
}

try {
  const dbUrl = process.env.FIREBASE_DATABASE_URL;
  const authSecret = process.env.FIREBASE_AUTH_SECRET;
  const serviceAccountPath = process.env.FIREBASE_SERVICE_ACCOUNT_PATH;

  let credential = null;

  if (serviceAccountPath && fs.existsSync(path.resolve(serviceAccountPath))) {
    const rawKey = fs.readFileSync(path.resolve(serviceAccountPath), 'utf8');
    const serviceAccount = JSON.parse(rawKey);
    credential = admin.credential.cert(serviceAccount);
  } else if (
    process.env.FIREBASE_PROJECT_ID &&
    process.env.FIREBASE_CLIENT_EMAIL &&
    process.env.FIREBASE_PRIVATE_KEY
  ) {
    credential = admin.credential.cert({
      projectId: process.env.FIREBASE_PROJECT_ID,
      clientEmail: process.env.FIREBASE_CLIENT_EMAIL,
      privateKey: process.env.FIREBASE_PRIVATE_KEY.replace(/\\n/g, '\n'),
    });
  }

  if (credential && dbUrl) {
    if (!admin.apps.length) {
      admin.initializeApp({
        credential,
        databaseURL: dbUrl,
      });
    }
    db = admin.database();
    initialized = true;
    console.log('[Firebase] Connected to Firebase Realtime Database via Admin SDK.');
  } else if (dbUrl) {
    db = new FirebaseRestDb(dbUrl, authSecret);
    initialized = true;
    console.log('[Firebase] Connected to Firebase Realtime Database via REST Auth Key.');
  } else {
    console.warn(
      '[Firebase Warning] Missing Firebase credentials or database URL in .env. Service operating in unconfigured mode.'
    );
  }
} catch (error) {
  console.error('[Firebase Error] Failed to initialize Firebase:', error.message);
}

export const getDb = () => db;
export const isFirebaseConfigured = () => initialized;
export default admin;
