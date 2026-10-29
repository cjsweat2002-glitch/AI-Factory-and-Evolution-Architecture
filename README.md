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
