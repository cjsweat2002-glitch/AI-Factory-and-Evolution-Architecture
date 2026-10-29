from src.research_memory import build_research_memory_context
from src.autonomy_store import (
    create_agent_cycle,
    create_agent_research_finding,
    list_agent_memory_usage,
    list_agent_research_findings,
    review_agent_research_finding,
)
from src.native_agents import run_native_agent


def _finding(
    finding_id,
    *,
    status="verified",
    claim="Controlled humidity changes the conductivity response.",
    evidence_type="published_measurement",
):
    return {
        "id": finding_id,
        "status": status,
        "domain": "materials",
        "claim": claim,
        "evidence_type": evidence_type,
        "source_ref": "https://example.test/paper",
        "observation": "Conductivity changed after calibrated humidity exposure.",
        "interpretation": "Water uptake may affect charge transport.",
        "competing_explanation": "Temperature drift could explain part of the change.",
        "discriminating_test": "Measure temperature and water uptake on held-out samples.",
        "limitations": "One material and a limited humidity range were tested.",
        "reviewer_note": "Source and stated comparison were checked.",
        "created_at": "2026-01-01",
        "reviewed_at": "2026-01-02",
    }


def test_memory_context_excludes_unverified_claims_and_keeps_provenance():
    result = build_research_memory_context(
        "humidity conductivity",
        [
            _finding("verified"),
            _finding("draft", status="draft", claim="unreviewed hypothesis"),
            _finding("contradicted", status="contradicted"),
        ],
    )

    assert result["metrics"]["verified_findings"] == 1
    assert result["metrics"]["selected_findings"] == 1
    assert '"s":"https://example.test/paper"' in result["context"]
    assert "unreviewed hypothesis" not in result["context"]
    assert '"x":' in result["context"]
    assert '"t":' in result["context"]


def test_relevant_findings_rank_first_and_budget_never_splits_a_record():
    relevant = _finding("relevant")
    unrelated = _finding(
        "unrelated",
        claim="A completely separate networking topic uses routing tables.",
        evidence_type="hypothesis",
    )
    full = build_research_memory_context("humidity conductivity", [unrelated, relevant])
    first_line = full["context"].splitlines()[0]

    assert '"c":"Controlled humidity changes' in first_line

    truncated = build_research_memory_context(
        "humidity conductivity", [unrelated, relevant], max_chars=len(first_line)
    )
    assert truncated["context"] == first_line
    assert truncated["metrics"]["selected_findings"] == 1
    assert truncated["metrics"]["omitted_findings"] == 1


def test_compression_metrics_measure_exact_compact_context():
    result = build_research_memory_context(
        "humidity conductivity", [_finding("verified")]
    )

    metrics = result["metrics"]
    assert metrics["compact_chars"] == len(result["context"])
    assert metrics["verbose_chars"] > metrics["compact_chars"]
    assert metrics["compression_ratio"] < 1
    assert metrics["space_savings_percent"] > 0
    assert metrics["estimated_tokens"] >= metrics["compact_chars"] // 4
    assert metrics["findings_per_1000_chars"] > 0


def test_memory_context_rejects_empty_objectives_and_invalid_budgets():
    try:
        build_research_memory_context("", [])
    except ValueError as exc:
        assert "objective" in str(exc)
    else:
        raise AssertionError("empty objective should be rejected")

    try:
        build_research_memory_context("topic", [], max_chars=0)
    except ValueError as exc:
        assert "budget" in str(exc)
    else:
        raise AssertionError("non-positive budget should be rejected")


def test_research_findings_are_drafts_until_explicitly_reviewed(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path))
    cycle = create_agent_cycle("Research a measurable improvement", "main", 1.0)
    authority = cycle["authorities"][0]

    finding = create_agent_research_finding(
        authority["id"],
        domain="materials",
        claim="Water uptake changed alongside measured proton conductivity.",
        evidence_type="published_measurement",
        source_ref="https://example.test/paper",
        observation="Conductivity changed after calibrated humidity exposure.",
        interpretation="Water uptake may affect charge transport.",
        competing_explanation="Temperature drift could explain part of the change.",
        discriminating_test="Measure temperature and water uptake on held-out samples.",
        limitations="One material and a limited humidity range were tested.",
    )
    assert finding["status"] == "draft"

    verified = review_agent_research_finding(
        finding["id"],
        decision="verified",
        reviewer_note="The cited paper supports the stated observation and conditions.",
    )
    assert verified["status"] == "verified"
    assert list_agent_research_findings(status="verified") == [verified]

    try:
        review_agent_research_finding(
            finding["id"],
            decision="verified",
            reviewer_note="A second review is not allowed after a final decision.",
        )
    except ValueError as exc:
        assert "only draft" in str(exc)
    else:
        raise AssertionError("reviewed findings must be immutable")


def test_native_agents_receive_compact_verified_memory_only(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AI_FACTORY_WORKER_URL", "http://worker.internal")
    monkeypatch.setenv("AI_FACTORY_MODEL", "test-model")
    cycle = create_agent_cycle("Research a measurable improvement", "main", 1.0)
    authority = cycle["authorities"][0]
    verified = create_agent_research_finding(
        authority["id"],
        domain="materials",
        claim="Water uptake changed alongside measured proton conductivity.",
        evidence_type="published_measurement",
        source_ref="https://example.test/verified",
        observation="Conductivity changed after controlled humidity exposure.",
        interpretation="Water uptake may affect charge transport.",
        competing_explanation="Temperature drift could explain part of the change.",
        discriminating_test="Measure water uptake under matched temperature.",
        limitations="One material was tested.",
    )
    review_agent_research_finding(
        verified["id"],
        decision="verified",
        reviewer_note="The cited source supports this observation and conditions.",
    )
    draft = create_agent_research_finding(
        authority["id"],
        domain="materials",
        claim="An unreviewed finding should not be reused.",
        evidence_type="hypothesis",
        source_ref="https://example.test/draft",
        observation="This is an unreviewed observation.",
        interpretation="This is an unreviewed interpretation.",
        competing_explanation="There may be another explanation.",
        discriminating_test="Run a test before using this claim.",
        limitations="It has not been reviewed.",
    )
    requests = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "result"}}]}

    def fake_post(url, **kwargs):
        requests.append(kwargs)
        return FakeResponse()

    monkeypatch.setattr("src.native_agents.httpx.post", fake_post)
    run_native_agent(
        "planner",
        "Explore humidity conductivity",
        branch_ref="agents/cycle/child",
    )
    prompt = requests[0]["json"]["messages"][0]["content"]

    assert "https://example.test/verified" in prompt
    assert "https://example.test/draft" not in prompt
    assert "d=domain, c=claim" in prompt
    assert '"s":"https://example.test/verified"' in prompt
    usage = list_agent_memory_usage()
    assert len(usage) == 1
    assert usage[0]["role"] == "planner"
    assert usage[0]["selected_findings"] == 1
