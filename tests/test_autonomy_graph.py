import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.autonomy_graph import refresh_autonomy_signal_graph
from src.autonomy_graph_api import router
from src.autonomy_store import (
    create_agent_cycle,
    create_agent_issue_draft,
    create_agent_research_finding,
    create_outcome,
    evaluate_agent_authority,
    review_agent_research_finding,
    verify_outcome,
)


def _verified_research_finding(authority_id):
    finding = create_agent_research_finding(
        authority_id,
        domain="reliability",
        claim="Bounded retry attempts reduce duplicate worker submissions.",
        evidence_type="reproduced_result",
        source_ref="https://example.test/retry-study",
        observation="The controlled test showed fewer duplicate submissions.",
        interpretation="The retry bound may reduce duplicate work.",
        competing_explanation="The test scheduler may have affected the result.",
        discriminating_test="Repeat with a randomized scheduler and workload.",
        limitations="Only one worker topology was tested.",
    )
    return review_agent_research_finding(
        finding["id"],
        decision="verified",
        reviewer_note="The test data and stated limitation were checked.",
    )


def test_signal_graph_links_only_verified_success_and_evidence(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path))
    issue = create_agent_issue_draft(
        title="Measure retry behavior",
        body="Measure retries and add acceptance criteria for duplicate submission tests.",
        axis="reliability",
        evidence="The coordinator does not record retry outcomes today.",
    )
    cycle = create_agent_cycle(
        "Improve worker reliability",
        "main",
        1.0,
        source_issue=issue["id"],
    )
    authority = cycle["authorities"][0]
    verified = _verified_research_finding(authority["id"])
    outcome = create_outcome(
        agent_id="worker-pool",
        contributor_id="owner",
        metric="quality",
        baseline=0.5,
        observed=0.8,
        unit="score",
        evidence="Controlled run comparing the baseline and updated worker flow.",
    )
    verify_outcome(outcome["id"], "The run logs confirm the paired comparison.")
    evaluate_agent_authority(
        authority["id"],
        tests_passed=True,
        reviewer_approved=True,
        evidence="Independent suite passed and reviewer confirmed the retry fix.",
        actual_gain=0.3,
    )

    graph = refresh_autonomy_signal_graph(stability_seconds=0)

    assert graph["node_count"] == 4
    assert graph["edge_count"] >= 2
    assert graph["inquiry_due"] is True
    assert any(node["signal_type"] == "validated_success" for node in graph["nodes"])
    assert any(
        edge["relation"] == "evidence_for"
        and edge["source_id"]
        == next(node["id"] for node in graph["nodes"] if node["source_id"] == verified["id"])
        for edge in graph["edges"]
    )
    assert any(edge["relation"] == "intent_source" for edge in graph["edges"])


def test_graph_stability_clock_resets_when_evidence_changes(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path))
    create_agent_cycle("Observe a reliability issue", "main", 1.0)

    first = refresh_autonomy_signal_graph(stability_seconds=0)
    stable = refresh_autonomy_signal_graph(stability_seconds=0)
    create_agent_issue_draft(
        title="Measure worker latency",
        body="Record latency percentiles and add acceptance tests for worker response timing.",
        axis="reliability",
        evidence="The worker API currently has no latency outcome metric.",
    )
    changed = refresh_autonomy_signal_graph(stability_seconds=0)

    assert stable["snapshot_id"] == first["snapshot_id"]
    assert stable["stable_for_seconds"] >= 0
    assert changed["snapshot_id"] != first["snapshot_id"]
    assert changed["stable_for_seconds"] == 0


def test_contradicted_research_is_not_rendered_as_unverified(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path))
    authority = create_agent_cycle("Investigate a reliability claim", "main", 1.0)[
        "authorities"
    ][0]
    finding = create_agent_research_finding(
        authority["id"],
        domain="reliability",
        claim="Retries always reduce duplicate submissions.",
        evidence_type="hypothesis",
        source_ref="https://example.test/retry-claim",
        observation="The supplied sample contained duplicate submissions.",
        interpretation="The retry policy may affect duplicates.",
        competing_explanation="The sample may be biased.",
        discriminating_test="Compare randomized runs with and without retries.",
        limitations="Only one workload was supplied.",
    )
    review_agent_research_finding(
        finding["id"],
        decision="contradicted",
        reviewer_note="The independent reproduction did not support the claim.",
    )

    graph = refresh_autonomy_signal_graph(stability_seconds=0)

    research_node = next(
        node for node in graph["nodes"] if node["source_id"] == finding["id"]
    )
    assert research_node["signal_type"] == "contradicted_claim"
    assert research_node["summary"].startswith("Contradicted:")


def test_stable_signal_graph_generates_non_executable_qa_inquiries(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path))
    create_agent_cycle("Improve worker reliability", "main", 1.0)
    node_id = refresh_autonomy_signal_graph(stability_seconds=0)["nodes"][0]["id"]
    response = {
        "cases": [
            {
                "title": "Keep branch changes isolated",
                "intent": "Ensure generated changes cannot alter the base branch.",
                "preconditions": "A builder authority has a dedicated worktree.",
                "assertions": "The current branch is the authority branch and main is unchanged.",
                "signal_ids": [node_id],
            }
        ]
    }
    calls = []

    def fake_agent(role, objective, **kwargs):
        calls.append((role, objective, kwargs))
        return json.dumps(response)

    monkeypatch.setattr("src.autonomy_graph_api.run_native_agent", fake_agent)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    generated = client.post(
        "/autonomy/graph/inquiry",
        json={"stability_seconds": 0},
    )

    assert generated.status_code == 200
    assert generated.json()["executed"] is False
    assert generated.json()["suite"]["status"] == "draft"
    assert calls[0][0] == "intent_mapper"

    repeated = client.post(
        "/autonomy/graph/inquiry",
        json={"stability_seconds": 0},
    )
    assert repeated.status_code == 409
