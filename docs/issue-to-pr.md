# Human-reviewed issue-to-draft-PR workflow

`.github/workflows/issue-to-pr.yml` is a manually dispatched, single-cycle
workflow. It only runs when dispatched from `main`. The selected issue must be
open, have the `agent-candidate` label, not have `needs-triage`, and not already
be referenced by an open pull request. The issue form adds `needs-triage` by
default; a maintainer must review the scope and acceptance criteria before
removing that label. To start a run, select **Actions > Human-reviewed issue to
draft PR > Run workflow** and enter the issue number. A label by itself never
triggers execution.

## Job boundaries

1. **Prepare** uses a read-only GitHub token to fetch the issue and check open
   pull requests. It records the issue, actor, workflow URL, and base commit.
   This job does not contact a model worker.
2. **Generate** runs once on a dedicated Linux self-hosted runner. Checkout has
   only `contents: read` and does not persist its credential; the agent step
   explicitly has empty `GH_TOKEN` and `GITHUB_TOKEN` values. It receives the
   issue artifact and worker configuration. The native builder proposes one
   patch in an external Git worktree; generated code is not executed here. The
   patch validator permits only regular text files under `src/`, `tests/`,
   `docs/`, and root `README.md`.
3. **Validate** runs on an ephemeral GitHub-hosted runner with no GitHub
   permissions. It reapplies and rechecks the patch from the recorded base,
   downloads dependencies from that trusted base, then runs `pytest` in a
   read-only, resource-limited Docker container with no network or credentials.
4. **Publish** runs only after successful validation and required environment
   approval. It rechecks the patch and validation digest, pushes a new branch,
   and opens a draft PR. The PR links the source issue and records the base
   commit, cycle and agent IDs, patch digest, validation status, and workflow
   run. It does not merge or approve the PR.

Request, patch, validation, and publication manifests are uploaded as
30-day-retention workflow artifacts. A failed validation or publication is
recorded in its manifest; a failed validation prevents the publish job from
running. Same-issue runs are serialized, and a later run is rejected if an
open PR already references the issue.

## Required maintainer configuration

Before enabling this workflow:

- Register a dedicated Linux x64 self-hosted runner with the `issue-agent`
  label. Use a disposable/ephemeral VM or equivalent clean runner group
  restricted to this repository and workflow. Do not mount production data,
  persist workspaces between jobs, or expose deployment/publishing credentials
  to the runner. Permit only the network access needed for the configured model
  worker, GitHub Actions checkout/artifact services, and trusted dependency
  installation (or provide an approved dependency cache).
- Set the `AI_FACTORY_WORKER_URL` Actions secret and `AI_FACTORY_MODEL`
  Actions variable. Set `AI_FACTORY_WORKER_TOKEN` only if the model endpoint
  requires it. This worker token authenticates only to the model endpoint; no
  GitHub token is passed to the model worker, and the agent step receives no
  publishing credential. Verify the runner can reach the worker. GitHub-hosted
  runners cannot reach a local Ollama endpoint by default.
- Create the `issue-to-pr-publish` GitHub Actions environment. Require
  maintainer reviewers, prevent self-review where available, and restrict
  deployments to the default branch. The publish job uses the repository
  `GITHUB_TOKEN` with only `contents: write` and `pull-requests: write`.
  Repository or organization policy must allow these job-level permissions.
- Restrict who can dispatch workflows using repository access controls.
  Dispatching from a non-`main` ref is not supported. Maintainers should
  inspect the issue and ensure it has meaningful acceptance tests before
  dispatch.

This repository cannot configure runner registration, runner-group access,
environment reviewers, or organization permission policy. The workflow is
therefore implemented but cannot publish until those settings are configured.
No automatically triggered issue-label workflow, persistent cross-run ledger,
or auto-merge path is provided.
