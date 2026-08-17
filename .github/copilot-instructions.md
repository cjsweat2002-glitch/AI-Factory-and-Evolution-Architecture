# AI Pool Coordinator

This repository contains a FastAPI-based AI worker pool gateway and load balancer.

## Project goals
- Keep the coordinator small and modular.
- Treat the config registry in `config/nodes.yaml` as the source of truth for worker URLs and models.
- Prefer round-robin routing and health-aware worker selection.
- Maintain compatibility with OpenAI-like requests while proxying to Ollama-style workers.

## Working conventions
- Use `pytest` for verification.
- Keep changes focused and additive.
- Prefer direct file edits over broad rewrites.
- If a bug appears, fix the root cause and validate with a targeted test.

## Important files
- `src/coordinator.py` — API gateway and request proxy.
- `src/health.py` — worker health monitoring.
- `src/proxy.py` — OpenAI/Ollama translation helpers.
- `config/nodes.yaml` — node registry.
- `tests/test_router.py` — behavior verification.

## Run locally
```bash
cd /workspaces/AI-Factory-and-Evolution-Architecture
python3 -m venv .venv
. .venv/bin/activate
pip install -q pytest fastapi httpx pyyaml pydantic uvicorn
pytest -q
uvicorn src.coordinator:app --host 0.0.0.0 --port 8000 --reload
```

## Notes
- Keep the repo usable from the editor without requiring a separate terminal workflow when possible.
- Treat the repository as the active project context for coding and chat.
