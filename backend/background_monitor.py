import time
import requests
import json
import os
from datetime import datetime
import zoneinfo

_IST = zoneinfo.ZoneInfo("Asia/Kolkata")
BACKEND_URL = "http://127.0.0.1:8003"
LOG_FILE = "paper_session_telemetry.json"

def log_snapshot():
    try:
        status = requests.get(f"{BACKEND_URL}/api/paper/status", timeout=5).json()
        metrics = requests.get(f"{BACKEND_URL}/api/paper/metrics", timeout=5).json()
        
        snapshot = {
            "timestamp": datetime.now(_IST).isoformat(),
            "status": status,
            "metrics": metrics
        }
        
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(snapshot) + "\n")
            
        print(f"[{datetime.now(_IST).strftime('%H:%M:%S')}] Snapshot logged. Candles: {status.get('candles_processed')} | Ticks: {status.get('ticks_received')}")
        
    except Exception as e:
        with open("monitor_errors.log", "a") as f:
            f.write(f"[{datetime.now(_IST)}] Error: {str(e)}\n")
        print(f"Error polling backend: {e}")

if __name__ == "__main__":
    print(f"Paper Session Monitor Started. Tracking {BACKEND_URL}...")
    while True:
        # Check if it's past session end (15:35 IST to be safe)
        now = datetime.now(_IST)
        if now.time() > datetime.strptime("15:40", "%H:%M").time():
            print("Session End reached. Monitor exiting.")
            break
            
        log_snapshot()
        time.sleep(300) # Every 5 minutes
