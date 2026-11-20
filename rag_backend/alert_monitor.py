"""
Automatic Critical Ambient Temperature Email Alert Daemon
Monitors real Firebase sensor readings independently of browser sessions.
Implements:
- Configurable recipient, threshold (°C), cooldown, and recovery notifications.
- DHT11 ambient air thermal warning trigger with hysteresis.
- Deduplication and cooldown to prevent email flooding.
- Stale or disconnected sensor detection.
- Persistent configuration and event logs.
"""

import os
import json
import time
import asyncio
from typing import Dict, Any, List, Optional
import requests
from dotenv import load_dotenv

from email_service import get_email_service
from firebase_auth import get_authenticated_rtdb_url

load_dotenv()

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "alert_settings.json")
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "alert_history.json")


class TemperatureAlertDaemon:
    """
    Background daemon for monitoring Firebase ambient temperature readings
    and triggering automated email alerts with deduplication and cooldown.
    """

    DEFAULT_SETTINGS = {
        "recipient_email": "admin@smartbms.local",
        "threshold_c": 45.0,
        "is_threshold_verified": False,  # Strict rule: Initially require user verification
        "threshold_source": "Provisional Bench Envelope (Battery Chemistry Unverified)",
        "enabled": True,
        "cooldown_minutes": 15,
        "recovery_notification": True,
        "hysteresis_c": 2.0,
        "check_interval_seconds": 6,
    }

    def __init__(self):
        self.settings = self._load_settings()
        self.history = self._load_history()
        self.email_service = get_email_service()
        
        # Runtime state
        self.is_running = False
        self.is_in_alarm = False
        self.last_alert_epoch = 0.0
        self.last_reading: Optional[Dict[str, Any]] = None
        self.sensor_status = "AWAITING_TELEMETRY"
        self._task = None

    def _load_settings(self) -> Dict[str, Any]:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    return {**self.DEFAULT_SETTINGS, **data}
            except Exception as e:
                print(f"[AlertDaemon] Error reading config: {e}")
        return dict(self.DEFAULT_SETTINGS)

    def _save_settings(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"[AlertDaemon] Error saving config: {e}")

    def _load_history(self) -> List[Dict[str, Any]]:
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save_history(self):
        try:
            # Keep latest 100 events
            with open(HISTORY_FILE, "w") as f:
                json.dump(self.history[-100:], f, indent=2)
        except Exception as e:
            print(f"[AlertDaemon] Error saving history: {e}")

    def get_settings(self) -> Dict[str, Any]:
        return {
            **self.settings,
            "daemon_running": self.is_running,
            "is_in_alarm": self.is_in_alarm,
            "sensor_status": self.sensor_status,
            "last_reading": self.last_reading,
            "smtp_configured": self.email_service.is_configured(),
        }

    def update_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        allowed_keys = [
            "recipient_email", "threshold_c", "is_threshold_verified",
            "threshold_source", "enabled", "cooldown_minutes",
            "recovery_notification", "hysteresis_c"
        ]
        for k in allowed_keys:
            if k in updates:
                self.settings[k] = updates[k]
        self._save_settings()
        return self.get_settings()

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return list(reversed(self.history[-limit:]))

    def fetch_latest_firebase(self) -> Optional[Dict[str, Any]]:
        """Fetch latest sensor readings from Firebase Realtime Database."""
        try:
            target = get_authenticated_rtdb_url("smart_bms/latest.json")
            resp = requests.get(target, timeout=3.5)
            if resp.ok and resp.json():
                data = resp.json()
                temp = data.get("temperature_C") if data.get("temperature_C") is not None else data.get("temperature")
                v = data.get("voltage_V") if data.get("voltage_V") is not None else data.get("voltage")
                c = data.get("current_A") if data.get("current_A") is not None else data.get("current")
                p = data.get("power_W") if data.get("power_W") is not None else data.get("power")
                epoch = data.get("timestamp_epoch") or data.get("rawTimestamp") or data.get("updatedAt") or (time.time() * 1000 if data.get("uptime_ms") else None)
                
                return {
                    "temperature": float(temp) if temp is not None else None,
                    "voltage": float(v) if v is not None else None,
                    "current": float(c) if c is not None else None,
                    "power": float(p) if p is not None else None,
                    "fanStatus": data.get("fan_state") or data.get("fanStatus") or "OFF",
                    "buzzerStatus": data.get("buzzer_state") or data.get("buzzerStatus") or "OFF",
                    "epoch": epoch,
                    "raw": data
                }
        except Exception as e:
            pass
        return None

    async def run_loop(self):
        """Main background loop checking Firebase telemetry at regular intervals."""
        self.is_running = True
        print("[AlertDaemon] Ambient Temperature Email Alert Daemon STARTED.")

        while self.is_running:
            try:
                if self.settings.get("enabled"):
                    data = self.fetch_latest_firebase()
                    self.last_reading = data

                    if data is None:
                        self.sensor_status = "FIREBASE_OFFLINE"
                    else:
                        temp = data.get("temperature")
                        epoch = data.get("epoch")
                        now = time.time()

                        # Stale data check (greater than 90 seconds old)
                        is_stale = False
                        if epoch:
                            # Handle both second and millisecond timestamps
                            ts_sec = epoch / 1000.0 if epoch > 1e11 else float(epoch)
                            if (now - ts_sec) > 90.0:
                                is_stale = True

                        if temp is None or is_stale:
                            self.sensor_status = "STALE_OR_DISCONNECTED"
                        else:
                            self.sensor_status = "LIVE_OK"
                            threshold = float(self.settings.get("threshold_c", 45.0))
                            hysteresis = float(self.settings.get("hysteresis_c", 2.0))
                            cooldown_sec = float(self.settings.get("cooldown_minutes", 15)) * 60.0

                            # --- CONDITION 1: THRESHOLD CROSSED ---
                            if temp >= threshold:
                                should_send = False
                                if not self.is_in_alarm:
                                    # Newly triggered alarm event
                                    should_send = True
                                    self.is_in_alarm = True
                                elif (now - self.last_alert_epoch) >= cooldown_sec:
                                    # Cooldown period elapsed while condition persists
                                    should_send = True

                                if should_send:
                                    self.last_alert_epoch = now
                                    print(f"[AlertDaemon] CRITICAL TEMPERATURE EVENT: {temp:.1f}°C >= {threshold:.1f}°C")
                                    dispatch_res = self.email_service.send_temperature_alert(
                                        recipient=self.settings.get("recipient_email"),
                                        temperature_c=temp,
                                        threshold_c=threshold,
                                        telemetry=data,
                                        is_threshold_verified=self.settings.get("is_threshold_verified", False)
                                    )
                                    
                                    event_record = {
                                        "id": f"EVT-{int(now)}",
                                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(now)),
                                        "type": "CRITICAL_ALERT",
                                        "temperature": temp,
                                        "threshold": threshold,
                                        "recipient": self.settings.get("recipient_email"),
                                        "delivery_status": dispatch_res.get("status"),
                                        "error": dispatch_res.get("error"),
                                        "note": "Ambient air warning (DHT11 adjacent to battery)"
                                    }
                                    self.history.append(event_record)
                                    self._save_history()

                            # --- CONDITION 2: RECOVERY HYSTERESIS ---
                            elif self.is_in_alarm and temp <= (threshold - hysteresis):
                                print(f"[AlertDaemon] TEMPERATURE RECOVERED: {temp:.1f}°C <= {threshold - hysteresis:.1f}°C")
                                self.is_in_alarm = False
                                
                                if self.settings.get("recovery_notification"):
                                    rec_res = self.email_service.send_temperature_recovery(
                                        recipient=self.settings.get("recipient_email"),
                                        temperature_c=temp,
                                        threshold_c=threshold
                                    )
                                    event_record = {
                                        "id": f"REC-{int(now)}",
                                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(now)),
                                        "type": "RECOVERY",
                                        "temperature": temp,
                                        "threshold": threshold,
                                        "recipient": self.settings.get("recipient_email"),
                                        "delivery_status": rec_res.get("status"),
                                        "note": "Ambient air returned to safe envelope"
                                    }
                                    self.history.append(event_record)
                                    self._save_history()

            except Exception as e:
                print(f"[AlertDaemon] Loop exception: {e}")

            interval = max(3, int(self.settings.get("check_interval_seconds", 6)))
            await asyncio.sleep(interval)

    def trigger_test_alert(self, custom_temp: float = 48.5) -> Dict[str, Any]:
        """Manually trigger a test alert email to verify recipient and email configuration."""
        data = self.last_reading or {
            "voltage": 12.35,
            "current": 0.85,
            "power": 10.5,
            "fanStatus": "ON (Test Trigger)",
        }
        res = self.email_service.send_temperature_alert(
            recipient=self.settings.get("recipient_email"),
            temperature_c=custom_temp,
            threshold_c=float(self.settings.get("threshold_c", 45.0)),
            telemetry=data,
            is_threshold_verified=self.settings.get("is_threshold_verified", False)
        )
        test_event = {
            "id": f"TEST-{int(time.time())}",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "type": "TEST_ALERT",
            "temperature": custom_temp,
            "threshold": float(self.settings.get("threshold_c", 45.0)),
            "recipient": self.settings.get("recipient_email"),
            "delivery_status": res.get("status"),
            "error": res.get("error"),
            "note": "Manual test alert triggered by user"
        }
        self.history.append(test_event)
        self._save_history()
        return res


_alert_daemon = None

def get_alert_daemon() -> TemperatureAlertDaemon:
    global _alert_daemon
    if _alert_daemon is None:
        _alert_daemon = TemperatureAlertDaemon()
    return _alert_daemon
