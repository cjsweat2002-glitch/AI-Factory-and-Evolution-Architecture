# AI Pool Coordinator

A lightweight, modular, and containerized AI worker pool gateway and load balancer.

## Terminal Access

Open a terminal in the repository root and use the commands below:

```bash
cd /workspaces/AI-Factory-and-Evolution-Architecture
python3 -m venv .venv
. .venv/bin/activate
pip install -q -e . pytest
python -m pytest -q
uvicorn src.coordinator:app --host 0.0.0.0 --port 8000 --reload
```

You can also use the VS Code task menu to run the project tasks directly from the repo root terminal.

## Architecture

This coordinator intercepts requests aimed at standard LLM APIs, health-checks a registry of local or remote workers (e.g., local machines running Ollama), and routes request traffic across them in a round-robin cycle.

## Directory Layout
- `config/nodes.yaml`: Registry listing backend node URLs and their available model weights.
- `src/coordinator.py`: FastAPI-based API routing hub supporting streaming and static request proxies.
- `src/health.py`: Node status tracker pinging active worker endpoints.
- `src/proxy.py`: Translation module for bridging API formats.
- `src/automorphic_engine_core.py`: Hyperbolic geometry, fractional-memory, sheaf-consensus, resource-scheduling, and complexity-anchor utilities.
- `src/autonomous_brand_agent.py`: Brand entity and specialized product, evaluation, and artifact-generation workers.
- `src/run_autopoietic_factory.py`: Bounded CLI orchestrator that writes reviewable checkpoints and metrics to `memory/brand_factory/`.
- `src/sheaf_neurosymbolic_multiverse_engine.py`: Sheaf Laplacian, hyperbolic maps, Caputo memory, BDM anchoring, and stable HJB-controlled simulation.
- `src/run_sheaf_multiverse.py`: CSV-exporting SAM-H5 simulation runner.
- `tests/`: Basic routing and schema unit tests

## Brand factory

Run a deterministic, bounded brand-factory simulation with:

```bash
python -m src.run_autopoietic_factory --generations 20
```

The runner writes JSON checkpoints, illustrative product specs and generated script examples, plus a CSV metrics file under `memory/brand_factory/`. These are simulated metrics, not market research or real financial valuations. Generated scripts are saved for review and are never executed by the factory. The runner does not commit changes or schedule itself; inspect and validate generated artifacts before using them.

The supplied SAM-H5 reference data is retained at `data/sam_h5_reference_dataset.csv` for comparison. It does not show the convergence claimed in its accompanying materials: obstruction reaches 13.01 by generation 3 and remains 11.66 at generation 100; the reported learning rate is saturated at 0.5 in all 100 rows; and reported Poincare norms exceed the unit-ball boundary after generation 2. Quality is pinned at 0.85 throughout. The integrated simulation uses a spectral stability bound, validates the Poincare-ball invariant, and labels all computed values as synthetic diagnostics. Run it with `python -m src.run_sheaf_multiverse --steps 100`.

## Private autonomous-agent features

The dashboard supports a **single owner**. Configure `AI_FACTORY_ACCESS_TOKEN` with a randomly generated secret of at least 32 characters before exposing the service; all API routes other than the dashboard/PWA assets, `/auth/config`, and `/healthz` require its Bearer token. Keep this secret private and rotate it if exposed.

The owner can record outcomes against a baseline and submit evidence. Outcomes remain pending until explicitly reviewed and verified; only verified outcomes are included in private agent learning context. The net-deviation index is an equal-weighted average of normalized percentage-point changes by metric, not currency, and should not be interpreted as a financial valuation. The shared-learning preference is saved locally, but cross-user aggregation is not implemented and no outcome data is transmitted to a shared service.

Phone notifications use Web Push. Configure `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, and `VAPID_CLAIMS_EMAIL` using a VAPID key pair and keep the private key in the deployment platform's secret store. Browser push requires HTTPS and owner permission. Notifications contain generic job status only; a push-delivery failure is logged and does not change the job result.

SQLite data and push subscriptions are stored under `AI_FACTORY_DATA_DIR` (default: `data/runtime`). The included Render configuration does not provision persistent storage, so this local database may be lost on redeploy or instance replacement. Configure a durable mounted volume and point `AI_FACTORY_DATA_DIR` to it before relying on stored outcomes or subscriptions.

### Native agent issue and authority cycles

The owner-only native-agent API uses an OpenAI-compatible worker from `config/nodes.yaml`, or `AI_FACTORY_WORKER_URL` and `AI_FACTORY_MODEL`. An optional `AI_FACTORY_WORKER_TOKEN` is sent only as the worker request's authorization header; it is not included in the model prompt. Set `AI_FACTORY_REPOSITORY_PATH` when the service does not start in the repository root. Agent context is assembled from a small, fixed set of project documentation and Python files.

`POST /autonomy/agent-issues/generate` asks a scout to draft an evidence-backed issue and stores it locally as `draft`. It does not publish to GitHub. `GET /autonomy/agent-issues` lists saved drafts. To explore a draft, start a cycle with its local draft ID as `source_issue`:

```json
{
  "objective": "Measure worker retry behavior",
  "base_branch": "main",
  "resource_budget": 1.0,
  "source_issue": "<local-draft-id>"
}
```

Send that object to `POST /autonomy/agent-cycles`, then call `POST /autonomy/agent-cycles/{cycle_id}/authorities/{authority_id}/expand` for the root or any active child authority. The planner can propose any number of distinct children; each must have positive projected gain after estimated cost, and the cycle stops expanding when its finite budget cannot cover another child. Gain, confidence, cost, and budget are unitless prioritization estimates, not measured money or guaranteed outcomes.

Create a child branch worktree with `POST /autonomy/agent-authorities/{authority_id}/workspace`. Worktrees are created outside the repository by default, beside it, or under the path configured by `AI_FACTORY_WORKTREE_DIR`. Create the parent worktree before materializing grandchildren. A `builder` authority can use `POST /autonomy/agent-authorities/{authority_id}/implement` to request and apply a unified diff on its isolated branch. Patches are restricted to `src/`, `tests/`, `docs/`, and the root README; generated code is not executed and tests are not run by this endpoint. `POST /autonomy/agent-authorities/{authority_id}/evaluate` records an owner-supplied test result, independent-review decision, evidence, and measured gain; it does not run tests itself. No agent writes directly to `main`, pushes branches, files GitHub issues, or merges code. CI execution, credential-scoped publishing, unattended issue-to-branch execution, and promotion remain future work.

The native authority endpoints require the same `AI_FACTORY_ACCESS_TOKEN` owner authentication as other private API routes. Run the coordinator inside the worker network for access to private Ollama-style workers; hosted CI runners cannot reach the local/private addresses in the sample worker registry.
