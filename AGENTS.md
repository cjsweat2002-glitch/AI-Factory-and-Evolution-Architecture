# Repository guidance for agent chat

This repo is the AI Pool Coordinator. Keep every change aligned with the project architecture and test flow.

- Use the repository context as the source of truth.
- Prefer defaulting to project files in `src/`, `config/`, and `tests/`.
- Validate with `pytest` when changing logic.
- Preserve the OpenAI-compatible gateway behavior and worker load-balancing pattern.
- Keep tasks visible in the editor without needing an extra terminal workflow.
