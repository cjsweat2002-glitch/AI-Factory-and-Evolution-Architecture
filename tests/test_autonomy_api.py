import json

from fastapi.testclient import TestClient

from src.autonomy_store import list_push_subscriptions
import src.coordinator as coordinator
from src.coordinator import app


TOKEN = "test-owner-access-token-32-characters"


def test_private_endpoints_require_owner_token(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_FACTORY_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path))
    client = TestClient(app)

    assert client.get("/").status_code == 200
    assert client.get("/healthz").status_code == 200
    assert client.get("/factory/status").status_code == 401
    assert client.get(
        "/factory/status", headers={"Authorization": f"Bearer {TOKEN}"}
    ).status_code == 200


def test_private_api_fails_closed_when_owner_token_is_unconfigured(monkeypatch):
    monkeypatch.delenv("AI_FACTORY_ACCESS_TOKEN", raising=False)

    response = TestClient(app).get("/factory/status")

    assert response.status_code == 503


def test_only_owner_reviewed_outcomes_affect_private_agent_learning(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_FACTORY_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path))
    client = TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"})
    outcome_payload = {
        "agent_id": "agent-a",
        "contributor_id": "owner",
        "metric": "time_saved",
        "baseline": 10,
        "observed": 15,
        "unit": "hours",
        "evidence": "Time log comparing the previous and current task workflow.",
    }

    submitted = client.post("/autonomy/outcomes", json=outcome_payload)
    outcome = submitted.json()["outcome"]
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "pending_review"
    assert client.get("/autonomy/agents/agent-a/net-deviation").json()[
        "verified_outcomes"
    ] == 0

    verified = client.post(
        f"/autonomy/outcomes/{outcome['id']}/verify",
        json={"review_note": "I reviewed the source time log and confirmed the comparison."},
    )
    assert verified.status_code == 200
    summary = client.get("/autonomy/agents/agent-a/net-deviation").json()
    assert summary["verified_outcomes"] == 1
    assert summary["net_deviation_index"] == 50
    assert summary["index_unit"] == "normalized percentage points; not currency"

    other_agent = client.get("/autonomy/agents/agent-b/net-deviation").json()
    assert other_agent["verified_outcomes"] == 0


def test_shared_learning_opt_in_does_not_send_single_user_data(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_FACTORY_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path))
    client = TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"})

    response = client.put("/autonomy/shared-learning", json={"opted_in": True})

    assert response.status_code == 200
    assert response.json()["opted_in"] is True
    assert response.json()["shared_aggregation_active"] is False
    assert "no outcome data is sent" in response.json()["notice"]
    assert client.get("/autonomy/shared-learning").json()["opted_in"] is True


def test_push_subscriptions_are_owner_only_and_persist(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_FACTORY_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path))
    subscription = {
        "endpoint": "https://push.example.test/subscription",
        "keys": {"p256dh": "public-key", "auth": "auth-secret"},
    }
    client = TestClient(app)

    assert client.post(
        "/notifications/subscribe", json={"subscription": subscription}
    ).status_code == 401

    owner_client = TestClient(app, headers={"Authorization": "Bearer " + TOKEN})
    assert owner_client.headers["authorization"] == f"Bearer {TOKEN}"
    assert owner_client.post(
        "/notifications/subscribe", json={"subscription": subscription}
    ).status_code == 200
    assert list_push_subscriptions() == [subscription]

    deleted = owner_client.request(
        "DELETE",
        "/notifications/subscribe",
        json={"endpoint": subscription["endpoint"]},
    )
    assert deleted.status_code == 200
    assert list_push_subscriptions() == []


def test_push_subscriptions_reject_non_https_endpoints(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_FACTORY_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path))
    client = TestClient(app, headers={"Authorization": "Bearer " + TOKEN})

    response = client.post(
        "/notifications/subscribe",
        json={
            "subscription": {
                "endpoint": "http://push.example.test/subscription",
                "keys": {"p256dh": "public-key", "auth": "auth-secret"},
            }
        },
    )

    assert response.status_code == 400


def test_agent_cycle_endpoints_require_owner_auth(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_FACTORY_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path))
    payload = {
        "objective": "Find evidence-backed improvements",
        "base_branch": "main",
        "resource_budget": 1.0,
    }

    assert TestClient(app).post("/autonomy/agent-cycles", json=payload).status_code == 401
    response = TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}).post(
        "/autonomy/agent-cycles", json=payload
    )
    assert response.status_code == 200
    assert response.json()["cycle"]["objective"] == payload["objective"]


def test_agent_authority_expansion_uses_native_planner_and_persists_evidence(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("AI_FACTORY_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AI_FACTORY_REPOSITORY_PATH", str(tmp_path / "repo"))
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "README.md").write_text("Repository context.\n", encoding="utf-8")
    proposal = {
        "axis": "reliability",
        "role": "explorer",
        "objective": "Measure worker timeout failure rate",
        "evidence": "Existing worker retry behavior is not measured by a test.",
        "projected_gain": 0.8,
        "confidence": 0.9,
        "estimated_cost": 0.2,
    }
    planner_calls = []

    def fake_planner(role, objective, **kwargs):
        planner_calls.append((role, objective, kwargs))
        return json.dumps({"proposals": [proposal]})

    monkeypatch.setattr(coordinator, "run_native_agent", fake_planner)
    client = TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"})
    created = client.post(
        "/autonomy/agent-cycles",
        json={
            "objective": "Find evidence-backed improvements",
            "base_branch": "main",
            "resource_budget": 1.0,
        },
    ).json()
    cycle_id = created["cycle"]["id"]
    root_id = created["authorities"][0]["id"]

    response = client.post(
        f"/autonomy/agent-cycles/{cycle_id}/authorities/{root_id}/expand"
    )

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert planner_calls[0][0:2] == ("planner", "Find evidence-backed improvements")
    assert planner_calls[0][2]["branch_ref"] == "main"
    refreshed = client.get(f"/autonomy/agent-cycles/{cycle_id}").json()
    child = next(
        authority
        for authority in refreshed["authorities"]
        if authority["id"] != root_id
    )
    assert child["proposal_evidence"] == proposal["evidence"]


def test_native_scout_creates_a_local_issue_draft_only(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_FACTORY_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AI_FACTORY_REPOSITORY_PATH", str(tmp_path / "repo"))
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "README.md").write_text("Repository context.\n", encoding="utf-8")
    issue = {
        "title": "Measure worker retry behavior",
        "body": "Describe the missing metric and add acceptance criteria for a deterministic retry test.",
        "axis": "reliability",
        "evidence": "The worker module has retry behavior but no corresponding counter.",
    }
    monkeypatch.setattr(
        coordinator,
        "run_native_agent",
        lambda *args, **kwargs: json.dumps(issue),
    )
    client = TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"})

    generated = client.post(
        "/autonomy/agent-issues/generate",
        json={"focus": "Find a reliability improvement"},
    )

    assert generated.status_code == 200
    assert generated.json()["issue"]["status"] == "draft"
    assert generated.json()["issue"]["title"] == issue["title"]
    drafts = client.get("/autonomy/agent-issues").json()["issues"]
    assert drafts[0]["id"] == generated.json()["issue"]["id"]


def test_authority_workspace_is_created_and_persisted(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_FACTORY_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AI_FACTORY_REPOSITORY_PATH", str(tmp_path / "repo"))
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "README.md").write_text("Repository context.\n", encoding="utf-8")
    proposal = {
        "axis": "reliability",
        "role": "builder",
        "objective": "Measure worker timeout failure rate",
        "evidence": "Existing worker retry behavior is not measured by a test.",
        "projected_gain": 0.8,
        "confidence": 0.9,
        "estimated_cost": 0.2,
    }
    agent_calls = []

    def fake_agent(role, objective, **kwargs):
        agent_calls.append((role, objective, kwargs))
        if role == "planner":
            return json.dumps({"proposals": [proposal]})
        return "diff --git a/README.md b/README.md\n..."

    monkeypatch.setattr(coordinator, "run_native_agent", fake_agent)
    worktree_path = tmp_path / "authorities" / "child"
    worktree_path.mkdir(parents=True)
    (worktree_path / "README.md").write_text("Isolated authority context.\n", encoding="utf-8")
    calls = []

    def fake_worktree(**kwargs):
        calls.append(kwargs)
        return {
            "branch_ref": f"agents/{kwargs['cycle_id']}/{kwargs['authority_id']}",
            "worktree_path": str(worktree_path),
        }

    monkeypatch.setattr(coordinator, "create_authority_worktree", fake_worktree)
    monkeypatch.setattr(
        coordinator,
        "apply_authority_patch",
        lambda worktree, patch, **kwargs: "README.md | 1 +",
    )
    client = TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"})
    created = client.post(
        "/autonomy/agent-cycles",
        json={
            "objective": "Find evidence-backed improvements",
            "base_branch": "main",
            "resource_budget": 1.0,
        },
    ).json()
    cycle_id = created["cycle"]["id"]
    root_id = created["authorities"][0]["id"]
    expansion = client.post(
        f"/autonomy/agent-cycles/{cycle_id}/authorities/{root_id}/expand"
    ).json()
    child_id = expansion["authorities"][0]["id"]

    workspace = client.post(
        f"/autonomy/agent-authorities/{child_id}/workspace"
    )

    assert workspace.status_code == 200
    assert workspace.json()["authority"]["worktree_path"] == str(worktree_path)
    assert calls[0]["base_branch"] == "main"
    assert client.post(
        f"/autonomy/agent-authorities/{child_id}/workspace"
    ).json()["worktree_path"] == str(worktree_path)
    assert len(calls) == 1
    implementation = client.post(
        f"/autonomy/agent-authorities/{child_id}/implement"
    )
    assert implementation.status_code == 200
    assert implementation.json()["tests_executed"] is False
    assert agent_calls[-1][0] == "builder"
    assert agent_calls[-1][2]["branch_ref"] == expansion["authorities"][0]["branch_ref"]
