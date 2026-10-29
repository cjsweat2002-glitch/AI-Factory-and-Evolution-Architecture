# Native research and evidence memory

The native autonomy worker can analyze source material supplied by the owner and
turn it into a compact, reviewable evidence card. It does not crawl the web or
verify a publication automatically; the supplied source reference is retained
so a person can check the original.

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
