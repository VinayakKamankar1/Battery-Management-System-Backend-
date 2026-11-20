"""
Firebase Authentication & REST Client Helper for Smart BMS
Provides secure anonymous authentication to access Firebase Realtime Database
when security rules enforce 'auth != null'.
"""

import os
import time
from typing import Optional
import requests
from dotenv import load_dotenv

load_dotenv()

FIREBASE_API_KEY = os.getenv("FIREBASE_WEB_API_KEY", "AIzaSyAqt7DgRPy-cJuaT9qVIvtlht1Ki1JCPro")
FIREBASE_DB_URL = os.getenv("FIREBASE_DATABASE_URL", "https://solar-80062-default-rtdb.firebaseio.com/").rstrip("/")

_cached_token: Optional[str] = None
_token_expiry_epoch: float = 0.0


def get_firebase_id_token(force_refresh: bool = False) -> Optional[str]:
    """
    Retrieve a valid Firebase ID token using anonymous sign-in via Google Identity Toolkit.
    Caches token in-memory and automatically refreshes before expiration.
    """
    global _cached_token, _token_expiry_epoch

    now = time.time()
    # If cached token is valid for at least 60 more seconds, reuse it
    if not force_refresh and _cached_token and now < (_token_expiry_epoch - 60):
        return _cached_token

    try:
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
        resp = requests.post(url, json={"returnSecureToken": True}, timeout=6.0)
        if resp.ok:
            data = resp.json()
            _cached_token = data.get("idToken")
            expires_in = float(data.get("expiresIn", 3600))
            _token_expiry_epoch = now + expires_in
            return _cached_token
        else:
            print(f"[FirebaseAuth] Anonymous sign-in warning: HTTP {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"[FirebaseAuth] Anonymous sign-in exception: {e}")

    return _cached_token


def get_authenticated_rtdb_url(path: str) -> str:
    """
    Constructs a full Realtime Database URL with ?auth=<token> parameter.
    path should be e.g. 'smart_bms/latest.json'
    """
    clean_path = path.lstrip("/")
    base_url = f"{FIREBASE_DB_URL}/{clean_path}"
    token = get_firebase_id_token()
    if token:
        delimiter = "&" if "?" in base_url else "?"
        return f"{base_url}{delimiter}auth={token}"
    return base_url
