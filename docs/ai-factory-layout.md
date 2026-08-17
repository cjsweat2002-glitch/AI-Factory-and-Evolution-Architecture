# AI Factory Layout

## Goal

Build a self-improving AI system around the current coordinator architecture so it can:

- learn from public web inspiration,
- transform that inspiration into repo changes,
- validate improvements with tests and health checks,
- evolve the project over time without constant manual rewrites.

This should feel like a small factory: inputs go in, knowledge is stored, tasks are planned, code is generated, and the result is validated before it enters the repository.

## Core design

The current system already has the right shape for this:

- `src/coordinator.py` acts as the control plane and API router.
- `config/nodes.yaml` defines the worker pool and model registry.
- `src/health.py` monitors worker state.
- `src/proxy.py` translates OpenAI-like traffic into backend-specific calls.

The missing layer is a learning and evolution loop that turns inspiration into repository changes.

## Layered architecture

### 1. Ingestion layer

Purpose: collect web inspiration and normalize it.

Responsibilities:

- fetch documentation, tutorials, GitHub repos, blog posts, architectures, and design patterns,
- strip irrelevant noise,
- classify content by theme: architecture, API, agent loop, testing, deployment, security,
- store ranked ideas into a knowledge base.

Example modules:

- `src/factory/ingest.py` — fetch and normalize sources
- `src/factory/summarizer.py` — compress ideas into reusable learning units
- `src/factory/source_registry.py` — track source URLs, quality, and freshness

### 2. Memory layer

Purpose: hold learned patterns in a way the AI can reuse.

Responsibilities:

- store clean notes, architecture patterns, design principles, and anti-patterns,
- maintain a repo memory of what is already implemented,
- keep a living map of project decisions and trade-offs.

Suggested structure:

```text
memory/
  web_inspiration/
    architecture/
    tooling/
    patterns/
  repo_memory/
    decisions.md
    principles.md
    evolution_log.md
```

This keeps the AI from only memorizing code but also learning from external patterns and the project’s own history.

### 3. Planning layer

Purpose: decide what to build next.

Responsibilities:

- compare incoming inspiration with current repo state,
- identify gaps, opportunities, and missing features,
- turn ideas into focused tasks or repo changes,
- prioritize by risk, value, and testability.

Example modules:

- `src/factory/planner.py` — create tasks from research
- `src/factory/goal_router.py` — map tasks into repo areas
- `src/factory/priority_engine.py` — score tasks by impact and readiness

### 4. Builder layer

Purpose: convert plans into code and config changes.

Responsibilities:

- create/update files when a task is viable,
- implement small, testable improvements,
- follow repository conventions and keep patches modular,
- avoid broad rewrites when a focused change solves the root problem.

Example modules:

- `src/factory/repo_agent.py` — the code-generation worker
- `src/factory/patcher.py` — apply diffs safely
- `src/factory/style_guide.py` — enforce repo conventions

### 5. Validation layer

Purpose: prove the change is safe.

Responsibilities:

- run unit tests,
- validate API behavior,
- check routing, health checks, and config correctness,
- reject low-signal or untested ideas.

Example modules:

- `src/factory/validator.py` — orchestrate tests
- `src/factory/benchmark.py` — evaluate model performance or route quality
- `src/factory/rollback.py` — restore prior state on failed experiments

### 6. Evolution layer

Purpose: let the repo improve itself over time.

Responsibilities:

- maintain a changelog of learned improvements,
- keep a decision trail for each architectural change,
- periodically re-ingest external inspiration,
- compare results with prior versions and decide whether to keep or reject them.

Suggested output lifecycle:

```text
Web inspiration -> summarized knowledge -> task generation -> patch -> test -> approved -> repo memory update
```

## Recommended repo layout

```text
AI-Factory-and-Evolution-Architecture/
  config/
    nodes.yaml
  docs/
    ai-factory-layout.md
    architecture-notes/
  memory/
    web_inspiration/
    repo_memory/
  src/
    coordinator.py
    health.py
    proxy.py
    factory/
      ingest.py
      summarizer.py
      planner.py
      repo_agent.py
      validator.py
      evolution.py
  tests/
    test_router.py
    test_factory/
```

## How the AI learns from the web

The system should not blindly copy the internet. It should collect signals and convert them into repository-aligned principles.

A healthy loop looks like this:

1. Browse web inspiration sources.
2. Extract patterns and decisions.
3. Convert them to notes in the memory layer.
4. Connect them to repo goals and missing capabilities.
5. Generate a small implementation task.
6. Patch the repository.
7. Run validation.
8. Record the outcome in `repo_memory`.
9. Repeat in a controlled, evidence-based cycle.

## Governance rules

To keep the system useful and safe, the AI should follow a few rules:

- prefer small tasks over massive rewrites,
- validate every change with tests,
- do not treat web inspiration as direct truth; treat it as candidate design input,
- keep memory grounded in repo reality, not just external examples,
- preserve the OpenAI-compatible gateway behavior while improving the architecture.

## Why this fits this project

This repo already behaves like an orchestration layer:

- it balances workers,
- routes requests,
- monitors health,
- supports multiple model backends.

That makes it a strong base for a “factory” model where an AI system can:

- learn from the broader web,
- decide what new repository features matter,
- modify code in focused increments,
- monitor whether those changes improve the system.

## Practical first milestone

The first goal should be modest and workable:

- add a memory and inspiration layer,
- add a planner that turns web findings into backlog tasks,
- add a validation gate before code is merged into the repo,
- keep the coordinator as the system-of-record for routing and health.

This creates a repeatable loop without turning the repo into a chaotic autonomous system too early.

## Bottom line

The architecture should blend three things:

- a routing and orchestration brain,
- a memory system that stores learning and decisions,
- a disciplined build-and-validate loop that turns inspiration into real repository evolution.

That is the foundation for building a new AI that learns from the web and improves itself over time without losing control of the project.
