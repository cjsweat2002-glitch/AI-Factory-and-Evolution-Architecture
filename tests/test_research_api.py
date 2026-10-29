import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.autonomy_store import (
    create_agent_cycle,
    evaluate_agent_authority,
    record_agent_memory_usage,
)
from src.research_api import router


def test_native_research_memory_requires_review_before_reuse(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path))
    cycle = create_agent_cycle("Research a measurable improvement", "main", 1.0)
    authority = cycle["authorities"][0]
    response_body = {
        "claim": "Measured conductivity changed after controlled humidity exposure.",
        "evidence_type": "published_measurement",
        "observation": "The cited source reports a conductivity change after exposure.",
        "interpretation": "Water uptake may influence charge transport.",
        "competing_explanation": "Temperature drift could explain part of the change.",
        "discriminating_test": "Track temperature and water uptake on held-out samples.",
        "limitations": "The supplied material covers one device configuration.",
    }
    prompts = []

    def fake_run_native_agent(role, objective, **kwargs):
        prompts.append((role, objective, kwargs))
        return json.dumps(response_body)

    monkeypatch.setattr("src.research_api.run_native_agent", fake_run_native_agent)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    payload = {
        "objective": "Assess humidity-dependent conductivity",
        "domain": "materials",
        "source_ref": "https://example.test/paper",
        "source_material": "The paper reports conductivity at controlled temperature and humidity.",
    }

    generated = client.post(
        f"/autonomy/agent-authorities/{authority['id']}/research",
        json=payload,
    )
    assert generated.status_code == 200
    finding = generated.json()["finding"]
    assert finding["status"] == "draft"
    assert prompts[0][0] == "researcher"
    assert "Do not invent citations" in prompts[0][1]

    before_review = client.get(
        "/autonomy/research/memory",
        params={"objective": payload["objective"]},
    )
    assert before_review.status_code == 200
    assert before_review.json()["metrics"]["verified_findings"] == 0

    reviewed = client.post(
        f"/autonomy/research/findings/{finding['id']}/review",
        json={
            "decision": "verified",
            "reviewer_note": "The source supports this observation under the given conditions.",
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["finding"]["status"] == "verified"

    after_review = client.get(
        "/autonomy/research/memory",
        params={"objective": payload["objective"]},
    )
    assert after_review.status_code == 200
    memory = after_review.json()
    assert memory["metrics"]["verified_findings"] == 1
    assert '"s":"https://example.test/paper"' in memory["context"]
    assert prompts[0][2]["evidence"].startswith("Source reference:")


def test_native_research_rejects_non_active_or_missing_authorities(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/autonomy/agent-authorities/missing/research",
        json={
            "objective": "Assess a source claim",
            "domain": "materials",
            "source_ref": "https://example.test/paper",
            "source_material": "A source passage to analyze.",
        },
    )

    assert response.status_code == 404


def test_research_metrics_report_longitudinal_prompt_compression(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path))
    record_agent_memory_usage(
        "researcher",
        {
            "verified_findings": 4,
            "selected_findings": 2,
            "compact_chars": 600,
            "verbose_chars": 1000,
            "estimated_tokens": 150,
        },
    )
    app = FastAPI()
    app.include_router(router)
    metrics = TestClient(app).get("/autonomy/research/metrics")

    assert metrics.status_code == 200
    result = metrics.json()
    assert result["calls"] == 1
    assert result["space_savings_percent"] == 40
    assert result["mean_selected_findings"] == 2


def test_public_search_runs_only_for_reviewed_relevant_successes(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        "AI_FACTORY_RESEARCH_SEARCH_URL",
        "https://search.example.test/search",
    )
    cycle = create_agent_cycle("Improve a verified worker capability", "main", 1.0)
    authority = cycle["authorities"][0]
    evaluate_agent_authority(
        authority["id"],
        tests_passed=True,
        reviewer_approved=True,
        evidence="Independent tests passed and the measured result improved.",
        actual_gain=0.4,
    )
    response_body = {
        "novelty_score": 0.8,
        "public_relevance_score": 0.9,
        "rationale": "The verified result could generalize to other worker-pool systems.",
        "search_queries": ["verified adaptive worker pool scheduling"],
    }
    search_calls = []
    monkeypatch.setattr(
        "src.research_api.run_native_agent",
        lambda *args, **kwargs: json.dumps(response_body),
    )

    def fake_search(query):
        search_calls.append(query)
        return [
            {
                "title": "Related public result",
                "url": "https://example.test/related",
                "snippet": "An unverified search lead.",
                "engine": "test",
            }
        ]

    monkeypatch.setattr("src.research_api.search_public_web", fake_search)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        f"/autonomy/agent-authorities/{authority['id']}/search-success"
    )

    assert response.status_code == 200
    assert response.json()["run"]["search_triggered"] is True
    assert response.json()["search_leads_are_verified_evidence"] is False
    assert search_calls == response_body["search_queries"]
    run_id = response.json()["run"]["id"]
    leads = client.get(
        "/autonomy/research/search-leads", params={"run_id": run_id}
    ).json()["leads"]
    assert leads[0]["url"] == "https://example.test/related"


def test_public_search_is_not_available_for_unreviewed_work(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path))
    cycle = create_agent_cycle("Explore a possible improvement", "main", 1.0)
    authority = cycle["authorities"][0]
    searches = []
    monkeypatch.setattr(
        "src.research_api.search_public_web",
        lambda query: searches.append(query) or [],
    )
    app = FastAPI()
    app.include_router(router)

    response = TestClient(app).post(
        f"/autonomy/agent-authorities/{authority['id']}/search-success"
    )

    assert response.status_code == 409
    assert searches == []


def test_missing_search_provider_records_qualified_assessment_without_leads(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("AI_FACTORY_RESEARCH_SEARCH_URL", raising=False)
    authority = create_agent_cycle(
        "Improve a verified worker capability", "main", 1.0
    )["authorities"][0]
    evaluate_agent_authority(
        authority["id"],
        tests_passed=True,
        reviewer_approved=True,
        evidence="Independent tests passed and the measured result improved.",
        actual_gain=0.4,
    )
    assessment = {
        "novelty_score": 0.8,
        "public_relevance_score": 0.9,
        "rationale": "The result may generalize beyond this project.",
        "search_queries": ["verified adaptive worker pool scheduling"],
    }
    monkeypatch.setattr(
        "src.research_api.run_native_agent",
        lambda *args, **kwargs: json.dumps(assessment),
    )
    app = FastAPI()
    app.include_router(router)

    response = TestClient(app).post(
        f"/autonomy/agent-authorities/{authority['id']}/search-success"
    )

    assert response.status_code == 200
    assert response.json()["search_qualified"] is True
    assert response.json()["run"]["search_triggered"] is False
    assert "AI_FACTORY_RESEARCH_SEARCH_URL" in response.json()["search_notice"]


def test_failed_search_attempts_are_recorded_and_rate_limited(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        "AI_FACTORY_RESEARCH_SEARCH_URL",
        "https://search.example.test/search",
    )
    authority = create_agent_cycle(
        "Improve a verified worker capability", "main", 1.0
    )["authorities"][0]
    evaluate_agent_authority(
        authority["id"],
        tests_passed=True,
        reviewer_approved=True,
        evidence="Independent tests passed and the measured result improved.",
        actual_gain=0.4,
    )
    assessment = {
        "novelty_score": 0.8,
        "public_relevance_score": 0.9,
        "rationale": "The result may generalize beyond this project.",
        "search_queries": ["verified adaptive worker pool scheduling"],
    }
    monkeypatch.setattr(
        "src.research_api.run_native_agent",
        lambda *args, **kwargs: json.dumps(assessment),
    )

    def failed_search(_query):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        "src.research_api.search_public_web",
        failed_search,
    )
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    attempts = [
        client.post(
            f"/autonomy/agent-authorities/{authority['id']}/search-success"
        )
        for _ in range(3)
    ]
    limited = client.post(
        f"/autonomy/agent-authorities/{authority['id']}/search-success"
    )

    assert all(response.status_code == 502 for response in attempts)
    assert limited.status_code == 429
    assert len(client.get("/autonomy/research/discovery-runs").json()["runs"]) == 3
