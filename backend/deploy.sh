#!/usr/bin/env bash
# Push local backend code to the Lightsail server and restart it. Run from the Mac: ./deploy.sh
set -euo pipefail

KEY=~/Downloads/LightsailDefaultKey-ap-south-1.pem
HOST=ubuntu@13.200.209.203
cd "$(dirname "$0")"

# Excluded: server secrets (.env), databases, and files the server writes at runtime (learned weights, logs),
# so a deploy never overwrites live state with the Mac's copy.
rsync -avz \
  --exclude '.venv' --exclude 'venv' --exclude '__pycache__' --exclude 'logs' --exclude '*.log' \
  --exclude '.env' --exclude '*.db' \
  --exclude 'strategy_weights.json' --exclude 'strategy_params.json' --exclude 'learning_log_*.json' \
  --exclude 'portfolio.json' --exclude 'trades.json' --exclude 'stocks_cache.json' --exclude 'paper_session_telemetry.json' \
  --exclude 'tests' --exclude 'app/simulation' --exclude 'test_*.py' --exclude 'verify_*.py' --exclude 'init_db.py' \
  -e "ssh -i $KEY" ./ "$HOST:~/backend/"

ssh -i "$KEY" "$HOST" 'cd ~/backend && .venv/bin/pip install -q -r requirements.txt \
  && sudo systemctl restart trader-api trader-worker && sleep 20 \
  && systemctl is-active trader-api trader-worker \
  && journalctl -u trader-api --since "-30s" --no-pager | grep -iE "token|startup complete|error|traceback" | tail -15'
