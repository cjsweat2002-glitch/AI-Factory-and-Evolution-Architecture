# Native research and evidence memory

The native autonomy worker can analyze source material supplied by the owner and
turn it into a compact, reviewable evidence card. It does not crawl source
pages or verify a publication automatically; the supplied source reference is
retained so a person can check the original.

## Workflow

1. Start an agent cycle and create an authority through the existing
   `/autonomy/agent-cycles` endpoints.
2. Submit source material to
   `POST /autonomy/agent-authorities/{authority_id}/research`. The worker
   returns a draft with an observation, interpretation, competing explanation,
   discriminating test, and limitations.
3. Check the citation and claim against the original source. Promote the card
   with `POST /autonomy/research/findings/{finding_id}/review` and a decision
   of `verified` or `contradicted`, explaining the decision.
4. Inspect the private evidence ledger at `GET /autonomy/research/findings`.
   Only verified findings are eligible for reuse through
   `GET /autonomy/research/memory?objective=...`.

Draft and contradicted findings remain auditable but are excluded from learning
context. Research input is treated as untrusted data; it cannot change the
agent's role or permissions. Current memory is owner-private and is not shared
with other users.

## Compression and growth measurements

Verified cards preserve their domain, claim, evidence class, source reference,
observation, interpretation, alternative explanation, test, limitations, and
review note. Prompt context serializes those fields using compact keys and
retrieves relevant cards within a character budget. It does not discard the
source reference or merge unlike scientific and business metrics.

The memory endpoint reports:

- `verified_findings`, `selected_findings`, and `omitted_findings`;
- `verbose_chars` versus `compact_chars` and their ratio; and
- an approximate token count (`characters / 4`).

These are prompt-size and retrieval measures, not proof that model capability
or business value is growing exponentially. Evaluate useful growth separately
with verified findings, independently tested predictions, accepted
improvements, and their measured costs.

Successful native-worker calls also record only role and memory-size counts
(not prompts, objectives, or source text). `GET /autonomy/research/metrics`
summarizes the most recent 1,000 calls so compression and verified-finding
density can be compared over time.

## Observable signal graph and stable-state inquiries

The autonomy graph is built from observable project records, not subjective
awareness: active authority confidence and intent, reviewed research findings,
verified measured outcomes, reviewed successes or rejected changes, and issue
drafts. Nodes retain their evidence source; edges connect shared project
dimensions, cycles, and evidence-to-authority relationships. A new graph
fingerprint resets its stability clock. `POST /autonomy/graph/refresh` accepts a
`stability_seconds` interval (default 3,600; maximum 86,400) and returns the
current graph, stable duration, and whether a new inquiry is due.

When due, `POST /autonomy/graph/inquiry` asks an intent-mapper to create a
declarative QA inquiry suite tied to graph node IDs. The generated cases are
stored as drafts; they are not executable code and are not run automatically.
An external self-hosted scheduler can call the refresh/inquiry endpoints to
check for stillness over time. `GET /autonomy/graph` and
`GET /autonomy/graph/intent-suites` expose the current graph and generated
drafts. The graph is bounded to 5,000 nodes and 20,000 edges per snapshot.

## Success-triggered public research

`POST /autonomy/agent-authorities/{authority_id}/search-success` is available
only after an authority has a positive measured gain and has passed the
owner-supplied test and independent-review gates. A native novelty analyst
assesses whether the result merits public comparison. Only scores of at least
0.65 for both novelty and public relevance trigger search, with up to three
queries, five leads per query, and a one-megabyte response limit. The service
requires an administrator-configured SearXNG endpoint in
`AI_FACTORY_RESEARCH_SEARCH_URL`; it does not fetch result pages.

Returned pages are stored as unverified search leads, not research findings.
They cannot enter verified memory until their source and claims are reviewed
through the evidence-card workflow. Public queries contain the success
description, not repository credentials. `GET /autonomy/research/discovery-runs`
and `GET /autonomy/research/search-leads` provide the private audit trail.
Each authority is limited to three discovery assessments per 24 hours.

Compact-memory token estimates indicate potential prompt-efficiency gains;
they are not measured end-to-end latency improvements and are not shared across
users. This release does not claim global learning or global capability growth.

## Authority genome lineage

Every authority has its own versioned genome and display name. A child starts
from the parent's capability profile at fork time; its later local changes do
not retroactively alter siblings or ancestors. Genome prompts contain the
current authority ID, name, version, and capabilities as identity metadata
only. This metadata grants no access or execution permissions.

An owner may add one capability locally only after the authority has passed
the recorded test and independent-review gates with positive measured gain.
Evidence and an introspective development path are required. The previous
name and genome snapshot are frozen in that authority's innovation library
before the new version is recorded. Names are deterministically generated
from the capability profile, so they change when the profile changes.

An owner-keyed universal genome change is applied transactionally to the
existing authority set. The key makes exact retries idempotent and conflicting
reuse is rejected. Future root genomes incorporate recorded universal
capabilities, and new descendants inherit those from their parent. "Universal"
means all authorities in this owner-private coordinator, not shared learning
across users. Genome labels do not establish legal ownership, equity, or
financial valuation; contribution value must remain separately tied to
reviewed evidence and measured outcomes.
