# 🌱 Seed Worker

A lightweight, self-contained AI worker for testing and developing the AI Factory locally. The Seed Worker mimics Ollama-compatible AI service behavior without requiring external dependencies.

## Quick Start

### 1. Start the Seed Worker (Terminal 1)
```bash
. .venv/bin/activate
python3 -m uvicorn src.seed_worker:app --host 0.0.0.0 --port 11434 --reload
```

Or use the VS Code task: **AI Pool: Start seed worker**

### 2. Start the Coordinator (Terminal 2)
```bash
. .venv/bin/activate
uvicorn src.coordinator:app --host 0.0.0.0 --port 8000 --reload
```

Or use the VS Code task: **AI Pool: Start app**

### 3. Open the Dashboard
Navigate to `http://localhost:8000` in your browser.

## Features

### 🎯 Smart Responses
The seed worker provides domain-aware responses based on prompt keywords:

- **"curiosity/research/improve"** → Suggests repository improvements
- **"validation/input"** → Proposes input validation strategies
- **"health/check/resilience"** → Recommends health check enhancements
- **"routing/load"** → Discusses load balancing improvements
- **"github/push/commit"** → Suggests GitHub integration enhancements

### 📡 OpenAI-Compatible API
```bash
POST /v1/chat/completions
GET /v1/models
GET /health
```

### 🔄 Streaming Support
```python
{
  "model": "seed-llama3",
  "messages": [{"role": "user", "content": "..."}],
  "stream": true  # Enable Server-Sent Events
}
```

## Architecture

```
┌──────────────────┐
│  Dashboard       │  http://localhost:8000
│  (browser)       │
└────────┬─────────┘
         │
┌────────▼──────────────────────┐
│  AI Pool Coordinator (8000)    │  Orchestrates AI tasks
│  - Routes requests             │  - Manages curiosity jobs
│  - Loads worker config         │  - Tracks background tasks
│  - Proxies to workers          │
└────────┬──────────────────────┘
         │
         │ Round-robin
         │ routing
    ┌────▼────────────────┐
    │                     │
┌───▼────────┐     ┌──────▼──────┐
│ Seed       │     │ Remote      │
│ Worker     │     │ Workers     │
│ (11434)    │     │ (optional)  │
└────────────┘     └─────────────┘
```

## Configuration

The seed worker is configured in `config/nodes.yaml` as the primary local worker:

```yaml
nodes:
  - name: seed-worker-local
    url: http://localhost:11434
    models:
      - seed-llama3
      - seed-reasoning
```

To use only the seed worker locally, comment out the other nodes in `config/nodes.yaml`.

## Usage Example

### Train the AI via Dashboard
1. Open http://localhost:8000
2. Scroll to **"Launch curiosity"** section
3. Enter topic: `"add request validation to all endpoints"`
4. Click **"Start"**
5. The seed worker will respond with improvement suggestions

### Test via curl
```bash
curl -X POST http://localhost:8000/factory/curiosity \
  -H "Content-Type: application/json" \
  -d '{"topic": "improve error handling", "model": "seed-llama3"}'
```

### Check Job Status
```bash
curl http://localhost:8000/factory/status | jq '.background_jobs | .[-1]'
```

## Running Tests

```bash
# All tests
pytest -q

# Only seed worker tests
pytest tests/test_router.py -v -k curiosity
```

## Seed Worker Response Examples

### Input: "How can we improve routing?"
```
Routing and load balancing enhancements:
- Track worker response times and adjust weights
- Implement least-connections strategy
- Add affinity for streaming responses
- Monitor queue depth per worker
- Balance between round-robin and weighted selection

This improves request distribution efficiency.
```

### Input: "Validation suggestions"
```
Input validation improvements:
- Add Pydantic models for request payload validation
- Implement rate limiting per worker
- Validate notebook content before import
- Add JSON schema validation for all endpoints
- Log validation failures for debugging

This prevents malformed requests from reaching workers.
```

## Extending the Seed Worker

Edit `src/seed_worker.py` to:
1. Add more keyword-based response logic in `generate_response()`
2. Implement custom models for specific domains
3. Add streaming response variations
4. Mock more complex behaviors

## Troubleshooting

### "Connection refused" on http://localhost:11434
- Ensure seed worker is running in Terminal 1
- Check port 11434 is not in use: `lsof -i :11434`

### Dashboard shows "No workers discovered"
- Verify seed worker is running and healthy
- Check `GET http://localhost:11434/health` returns 200
- Ensure `config/nodes.yaml` includes seed worker

### Curiosity jobs show "failed" status
- Check seed worker logs for errors
- Verify network connectivity between coordinator (8000) and worker (11434)
- Ensure firewall allows localhost:11434

## Next Steps

Once seed worker works locally:
1. Test curiosity system with "Launch curiosity" feature
2. Try "Train the AI" chat feature
3. Test notebook imports with the guard
4. Deploy to Render with actual Ollama workers

---

The seed worker is meant for local development and testing. For production, use actual Ollama instances or other OpenAI-compatible AI services.
