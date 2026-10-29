# AI Factory & Evolution Architecture

A research architecture for creating original AI agents that learn from evidence,
share useful methods, and improve across fields—starting with the knowledge and
skills people study in colleges around the world.

## Vision

This project aims to give birth to a growing family of AI agents: systems that
can teach one another useful methods, learn from improving algorithms, and
combine knowledge from different disciplines to solve problems in new ways.
Its mathematical point of view is to treat knowledge as structured data
topologies: concepts, methods, evidence, and outcomes connected across domains.
The factory should discover which structures are useful, test how they can be
transformed or recombined, and measure whether those transformations transfer
to new tasks.

The ambition is not simply to make another general-purpose model or to claim
that this repository is already ahead of global AI progress. It is to build a
measurable system for creating specialized, original agents from reusable
learning processes—and to make those agents useful enough to compete as
products alongside existing models.

## Learning thesis

College disciplines are a practical map of what people around the world train
to understand and do. Curricula, textbooks, open educational resources,
research, and professional standards can help identify important concepts,
prerequisites, problem types, and assessment methods. The factory can represent
those as source-linked knowledge graphs and use them to shape agents with
distinct roles, domain expertise, and ways to collaborate.

The intended learning loop is:

1. Gather permitted, provenance-tracked source material and curriculum
   structures across disciplines.
2. Represent concepts, prerequisites, methods, evidence, and assessments as
   connected topologies.
3. Generate specialized agents and cross-domain hypotheses from those
   structures, preserving uncertainty and source attribution.
4. Evaluate them on held-out tasks and shared, clearly defined measures.
5. Let agents exchange tested methods—not unverified claims—and retain changes
   only when they improve useful outcomes without unacceptable regressions.

“Teach each other” means exchanging inspectable methods, evidence, and
evaluations. It does not imply consciousness or that one agent's generated
claim is reliable merely because another agent repeats it.

## What “getting ahead” should mean

Progress must be demonstrated against named baselines, not inferred from agent
count, graph size, self-assigned capabilities, or synthetic simulations. The
long-term research goal is to compare agents on meaningful tasks across
domains and, where appropriate, languages and educational contexts. Track
task success and transfer alongside reliability, latency, compute cost,
regressions, provenance, and human review. Keep unlike measures separate and
publish the benchmark definitions and limitations so results can be
reproduced.

## Original agents and product potential

The factory is intended to help create useful, differentiated agents that
could become commercial products. Potential value comes from solving a
specific user problem better, more reliably, or more affordably—not from
claiming ownership of a curriculum, a model's output, or an agent's “genome.”
Educational materials have different licenses and rights: record provenance
and usage terms, prefer openly licensed or otherwise authorized sources, and
review the applicable rights before using material for training or
distribution. Build original agent behavior from validated methods and
appropriately licensed inputs; do not present this project as legal advice or
as proof of exclusivity.

## What this repository does today

Today, this repository is an early, owner-operated foundation: a modular
FastAPI worker-pool gateway plus bounded simulations and native workflows for
drafting issues, isolating proposed code changes, recording reviewed research,
and tracking authority lineage. It can store evidence-linked signals and
generate QA inquiry drafts, but it does not yet run a global curriculum
pipeline, let agents teach across users, autonomously evaluate and promote
changes, or demonstrate universal cross-domain performance. Those are research
and engineering goals—not shipped capabilities.

## Getting started

Open a terminal in the repository root and use:

```bash
cd /workspaces/AI-Factory-and-Evolution-Architecture
python3 -m venv .venv
. .venv/bin/activate
pip install -q -e . pytest
python -m pytest -q
uvicorn src.coordinator:app --host 0.0.0.0 --port 8000 --reload
```

You can also use the VS Code task menu to run the project tasks directly from the repo root terminal.

## Current architecture

The coordinator intercepts requests aimed at standard LLM APIs, health-checks
workers listed in a registry (for example, local Ollama machines), and routes
traffic across available workers. This pool is the infrastructure foundation
for the longer-term learning factory; it is not itself a globally trained
model.

Core modules include `src/coordinator.py` (API gateway), `src/health.py`
(worker health checks), and `src/proxy.py` (request translation).
`src/automorphic_engine_core.py` and
`src/sheaf_neurosymbolic_multiverse_engine.py` provide mathematical and
simulation utilities; their metrics are experimental unless independently
validated against real tasks. The brand factory and simulation runners produce
reviewable artifacts, not market evidence or proof of agent capability.

## GitHub issue development

Use the repository's issue forms to keep reports and proposals actionable:

- **Bug report** for reproducible failures.
- **Improvement proposal** for a focused capability or reliability change.
- **Curriculum or cross-domain research** for provenance-tracked learning
  material, knowledge topologies, and transfer evaluations.
- **Agent implementation candidate** for bounded work that may be suitable for
  an isolated agent branch.

Issues start as human-triaged proposals. Before an issue is marked
`agent-ready`, a maintainer should confirm its scope, acceptance tests, source
rights, and safety boundaries. The intended next stage is an explicitly
approved self-hosted agent run that produces a branch and pull request for
human review; it must not merge automatically. That runner integration is not
implemented yet: adding an issue label does not currently execute an agent.
The eventual workflow must keep model workers away from GitHub credentials,
run generated changes in an isolated environment, and require protected
approval before any publishing action.

The initial workflow roadmap is tracked in [#2](https://github.com/cjsweat2002-glitch/AI-Factory-and-Evolution-Architecture/issues/2)
(human-reviewed issue-to-PR pipeline), [#3](https://github.com/cjsweat2002-glitch/AI-Factory-and-Evolution-Architecture/issues/3)
(approval-gated self-hosted runs), and [#4](https://github.com/cjsweat2002-glitch/AI-Factory-and-Evolution-Architecture/issues/4)
(curriculum topology and transfer evaluation). The forms are intake, not
evidence that the planned agent automation or curriculum pipeline already
exists.

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

An active authority can analyze owner-supplied source material with `POST /autonomy/agent-authorities/{authority_id}/research`. The source reference is required; generated evidence cards remain drafts until the owner reviews them through `POST /autonomy/research/findings/{finding_id}/review`. Only verified cards are retrieved for later native-agent prompts. The compact memory preserves source links, observations, interpretations, alternatives, tests, and limitations; `GET /autonomy/research/memory?objective=...` reports context-size and compression metrics. `GET /autonomy/research/metrics` summarizes successful worker-call memory usage without storing prompts or source text.

The observable-signal graph treats uncertainty, intent, verified gains, regressions, rejected changes, and research as auditable telemetry—not subjective feelings. `POST /autonomy/graph/refresh` tracks a graph fingerprint and its unchanged duration; `POST /autonomy/graph/inquiry` can turn a sufficiently stable graph into declarative QA drafts. Defaults and limits are 3,600 and 86,400 seconds. These endpoints evaluate stability when called; no background scheduler runs them automatically, and generated QA drafts are not executable tests.

After an owner-reviewed authority success with positive measured gain, `POST /autonomy/agent-authorities/{authority_id}/search-success` asks a novelty analyst whether bounded public comparison is warranted. Configure `AI_FACTORY_RESEARCH_SEARCH_URL` with a SearXNG `/search` endpoint to enable it. Search results are unverified leads, not evidence; they must be checked and reviewed before they can enter research memory. The API limits searches and response size. Neither this workflow nor compact-memory metrics establish global sharing or measured end-to-end processing-speed gains. See `docs/research-evidence-memory.md`.

### Authority genomes and innovation library

Each authority has an independent, versioned genome with a stable identity, a display name, and earned capability labels (`global_skills`, `research`, `code_development`, `engine_development`, and `web_research`). Children inherit the parent's current capability profile when they are created. Native prompts receive the authority's current identity and capability metadata, which does not grant permissions or replace role-specific safeguards.

An owner can inspect a profile at `GET /autonomy/agent-authorities/{authority_id}/genome`. Local evolution through `POST /autonomy/agent-authorities/{authority_id}/genome/evolve` is allowed only after the authority has passed the test and independent-review gates with positive measured gain. Each change requires evidence and an introspective path. The authority is renamed deterministically as its capability profile changes; previous names and profiles are preserved as immutable versions and innovation-library entries.

`POST /autonomy/agent-genomes/universal-changes` applies a keyed, owner-recorded capability change to every existing authority genome in one transaction. Repeating an identical key is idempotent; reusing the key with different content is rejected. Future root authorities seed from recorded universal changes, and descendants inherit from their parent. This scope is limited to this coordinator's owner-private data; it does not create cross-user learning, legal ownership, equity, or a monetary company valuation. Capability evidence and measured contribution outcomes are auditable records, not financial worth.
