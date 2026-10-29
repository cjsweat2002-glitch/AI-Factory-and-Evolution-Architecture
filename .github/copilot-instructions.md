# AI Factory & Evolution Architecture

This repository is an early, owner-operated research architecture for creating
specialized AI agents that learn from source-grounded evidence, share validated
methods, and improve across domains. The FastAPI worker-pool gateway is
infrastructure for that longer-term goal, not the whole product.

## Project goals
- Keep the coordinator small and modular.
- Treat the config registry in `config/nodes.yaml` as the source of truth for worker URLs and models.
- Prefer round-robin routing and health-aware worker selection.
- Maintain compatibility with OpenAI-like requests while proxying to Ollama-style workers.
- Represent knowledge as source-linked concepts, prerequisites, methods, evidence, and assessments.
- Treat curriculum and cross-domain learning as research goals; verify transfer on held-out tasks rather than claiming universal performance.
- Preserve the boundary between current capabilities and future research goals.
- Keep human review before changes are merged or learning records are promoted.

## Working conventions
- Use `pytest` for verification.
- Keep changes focused and additive.
- Prefer direct file edits over broad rewrites.
- If a bug appears, fix the root cause and validate with a targeted test.
- Never treat model-generated claims, search leads, or synthetic simulation metrics as verified evidence.
- Record provenance and usage rights for external educational or research material; do not assume public availability grants training or redistribution rights.
- Do not give model workers GitHub credentials. Generated patches are proposals and must remain isolated until validated and reviewed.

## Important files
- `src/coordinator.py` — API gateway and request proxy.
- `src/health.py` — worker health monitoring.
- `src/proxy.py` — OpenAI/Ollama translation helpers.
- `config/nodes.yaml` — node registry.
- `tests/test_router.py` — behavior verification.
- `docs/ai-factory-layout.md` — long-term factory architecture.
- `.github/ISSUE_TEMPLATE/` — structured GitHub issue intake for bugs, improvements, curriculum research, and agent candidates.

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
