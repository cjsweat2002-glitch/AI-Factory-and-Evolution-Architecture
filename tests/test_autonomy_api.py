from fastapi.testclient import TestClient

from src.autonomy_store import list_push_subscriptions
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
