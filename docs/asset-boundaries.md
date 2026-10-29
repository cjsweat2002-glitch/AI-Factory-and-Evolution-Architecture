# Asset boundaries and handling

This document defines repository handling defaults for the AI Factory. It is
an operational security guide, not a license, contract, or legal opinion.

## Asset classes

| Class | Examples | Default handling |
| --- | --- | --- |
| Source code | Engines, orchestration, workers, and front-end runtimes | Keep in reviewed source control. Apply the repository's actual license; do not assume a directory name creates a separate license boundary. |
| Restricted model artifacts | Weights, checkpoints, embeddings, and learned tensors | Keep out of Git. Store in a private artifact service with encryption at rest, managed keys, access controls, and audit logs. |
| Private generated data | User-specific brand genomes, evaluations, and checkpoints | Keep in the user's private runtime storage. Do not publish or aggregate across users without explicit opt-in and suitable de-identification. |
| Credentials | API tokens, signing keys, and storage credentials | Supply through a deployment secret manager or local environment; never put them in source, config examples, logs, or generated artifacts. |
| Shared contribution records | Reviewed contribution and outcome metadata | Record provenance and verification status. Keep attribution separate from financial valuation or claims of ownership. |

## Repository safeguards

- `.gitignore` excludes common model-weight formats, credentials, and private
  keys. `storage/vault/` is a placeholder for deployment integration, not a
  secure vault; its contents must remain outside source control.
- Generated factory output under `memory/brand_factory/` is ignored by default.
  Review and share selected artifacts through an explicitly approved,
  access-controlled channel rather than committing private outputs.
- Runtime user data is stored under `AI_FACTORY_DATA_DIR` (default:
  `data/runtime/`), which is ignored by Git. Deployments must provide durable,
  access-controlled storage and backups appropriate to the data.
- Git ignore rules reduce accidental commits only. They do not encrypt files,
  protect a running host, or remove information already committed. Git LFS is
  storage, not encryption.
- Keep user learning isolated by default. Only verified outcomes should affect
  that user's agent. Shared learning requires explicit opt-in; do not include
  identifying user content in shared signals.
- Treat net-deviation and contribution records as operational evidence, not
  money, equity, ownership, or a guaranteed return. Attribute only verified
  incremental outcomes against a stated baseline, including costs and
  maintenance burden.

## Not implemented by these safeguards

This repository does not yet provide encrypted model-artifact storage, a
multi-tenant vault, a cross-user learning pipeline, contributor license
agreements, or commercial usage terms. Do not represent these as enforced
protections. License, patent, trade-secret, copyright, and ownership questions
depend on facts and jurisdiction and require qualified legal review.
