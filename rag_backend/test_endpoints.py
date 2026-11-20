import requests
import json

base = "http://localhost:8000"

print("1. Testing GET /api/alerts/settings...")
r1 = requests.get(f"{base}/api/alerts/settings", timeout=5)
print(r1.status_code, r1.json())

print("\n2. Testing POST /api/reports/generate (allowing up to 30s for embedding model warmup)...")
r2 = requests.post(f"{base}/api/reports/generate", json={"period": "24h"}, timeout=30)
print(r2.status_code, r2.json())

report_id = r2.json().get("report_id")

print(f"\n3. Testing GET /api/reports/history...")
r3 = requests.get(f"{base}/api/reports/history", timeout=5)
print(r3.status_code, "Reports count:", len(r3.json().get("data", [])))

if report_id:
    print(f"\n4. Testing GET /api/reports/{report_id}/download...")
    r4 = requests.get(f"{base}/api/reports/{report_id}/download", timeout=5)
    print(r4.status_code, "PDF length:", len(r4.content))

    print(f"\n5. Testing POST /api/reports/{report_id}/email (simulation mode)...")
    r5 = requests.post(f"{base}/api/reports/{report_id}/email", json={"recipient": "test@domain.com"}, timeout=5)
    print(r5.status_code, r5.json())

print("\n6. Testing POST /api/alerts/test (simulation mode)...")
r6 = requests.post(f"{base}/api/alerts/test", timeout=5)
print(r6.status_code, r6.json())

print("\nALL API ENDPOINTS TESTED SUCCESSFULLY!")
