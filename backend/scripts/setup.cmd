# Assignment 2 only: cwd must be Assignment_2/ so `src` is Assignment_2/src (not repo root src/).
# Run with: bash scripts/.cmd   (do not `source` this — dirname "$0" is wrong when sourced.)
cd "$(dirname "$0")/../Assignment_2" && export PYTHONPATH="$(pwd)" && \
uvicorn src.api.app:app --host 127.0.0.1 --port 8000

# Or:  bash Assignment_2/run_dev.sh


curl -sS -N -X POST http://127.0.0.1:8000/v1/chat \
-H 'Content-Type: application/json' \
-d '{
  "query":"can u teach me how to buy a coffee machine",
  "session_id":"euser-journey",
  "collaborative":true
}'




curl -N -X POST http://127.0.0.1:8000/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "i want you to analyse tax risks in my protfolio",
    "session_id": "vi21",
    "user_context": {
      "user_id": "icetea_001",
      "name": "Vishesh",
      "base_currency": "USD",
      "risk_profile": "aggressive",
      "collaborative":true,
      "positions": [
        {"ticker": "AAPL", "quantity": 60, "avg_cost": 142.30, "currency": "USD"},
        {"ticker": "NVDA", "quantity": 35, "avg_cost": 412.85, "currency": "USD"}
      ],
      "preferences": {"preferred_benchmark": "S&P 500"}
    }
  }'


