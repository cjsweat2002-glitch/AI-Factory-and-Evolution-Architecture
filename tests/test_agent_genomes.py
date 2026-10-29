import pytest
from fastapi.testclient import TestClient

from src.autonomy_store import (
    apply_universal_genome_change,
    create_agent_cycle,
    evaluate_agent_authority,
    evolve_agent_genome,
    expand_agent_authorities,
    get_agent_genome,
)
from src.coordinator import app
from src.native_agents import build_agent_prompt


def _proposal():
    return {
        "axis": "research",
        "role": "researcher",
        "objective": "Verify source claims against a reproducible measurement",
        "evidence": "Existing research cards preserve source references.",
        "projected_gain": 0.8,
        "confidence": 0.9,
        "estimated_cost": 0.1,
    }


def test_branch_genomes_inherit_and_freeze_renamed_versions(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path))
    cycle = create_agent_cycle("Improve evidence quality", "main", 1.0)
    root = cycle["authorities"][0]
    root_genome = get_agent_genome(root["id"])["current"]
    child = expand_agent_authorities(cycle["cycle"]["id"], root["id"], [_proposal()])[0]
    initial_child = get_agent_genome(child["id"])

    assert root_genome["current_name"].startswith("Seed-")
    assert initial_child["current"]["capabilities"] == []
    assert (
        initial_child["current"]["parent_genome_id"]
        == root_genome["genome_id"]
    )
    with pytest.raises(ValueError, match="requires a tested, reviewed authority"):
        evolve_agent_genome(
            child["id"],
            capability="research",
            evidence="An independently checked research outcome.",
            introspective_path="I compared the source with the experiment and resolved its key limitation.",
        )

    evaluate_agent_authority(
        child["id"],
        tests_passed=True,
        reviewer_approved=True,
        evidence="Independent review confirmed the measurement and passing tests.",
        actual_gain=0.25,
    )
    evolved = evolve_agent_genome(
        child["id"],
        capability="research",
        evidence="An independently checked research outcome.",
        introspective_path="I compared the source with the experiment and resolved its key limitation.",
    )
    history = get_agent_genome(child["id"])

    assert evolved["capabilities"] == ["research"]
    assert evolved["current_name"].startswith("Scholar-")
    assert evolved["current_version"] == 2
    assert [version["display_name"] for version in history["versions"]] == [
        initial_child["current"]["current_name"],
        evolved["current_name"],
    ]
    assert len(history["innovation_library"]) == 1
    frozen = history["innovation_library"][0]
    assert frozen["frozen_name"] == initial_child["current"]["current_name"]
    assert frozen["frozen_genome"]["capabilities"] == []
    assert "compared the source" in frozen["introspective_path"]

    renamed = evolve_agent_genome(
        child["id"],
        capability="code_development",
        evidence="A separately tested implementation outcome.",
        introspective_path="I used the reviewed implementation lessons to validate and retain a code development improvement.",
    )
    assert renamed["current_name"].startswith("Forge-Scholar-")
    assert renamed["current_name"] != evolved["current_name"]
    assert len(get_agent_genome(child["id"])["innovation_library"]) == 2


def test_universal_genome_change_is_atomic_idempotent_and_inherited(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path))
    first_cycle = create_agent_cycle("Improve research", "main", 1.0)
    root = first_cycle["authorities"][0]
    child = expand_agent_authorities(
        first_cycle["cycle"]["id"], root["id"], [_proposal()]
    )[0]
    second_cycle = create_agent_cycle("Improve code quality", "main", 1.0)
    second_root = second_cycle["authorities"][0]
    payload = {
        "change_key": "research-capacity-v1",
        "capability": "research",
        "evidence": "Owner-reviewed global research capacity release.",
        "introspective_path": "Repeated source review and replication showed this method generalizes across authorities.",
    }

    applied = apply_universal_genome_change(**payload)

    assert len(applied["genomes"]) == 3
    assert all("research" in genome["capabilities"] for genome in applied["genomes"])
    assert all(genome["current_version"] == 2 for genome in applied["genomes"])
    repeated = apply_universal_genome_change(**payload)
    assert repeated["already_applied"] is True
    assert all(genome["current_version"] == 2 for genome in repeated["genomes"])
    with pytest.raises(ValueError, match="different content"):
        apply_universal_genome_change(**{**payload, "evidence": "Different owner-reviewed evidence."})

    future_cycle = create_agent_cycle("Explore new research", "main", 1.0)
    future_root = future_cycle["authorities"][0]
    future_child = expand_agent_authorities(
        future_cycle["cycle"]["id"], future_root["id"], [_proposal()]
    )[0]
    assert get_agent_genome(future_root["id"])["current"]["capabilities"] == [
        "research"
    ]
    assert get_agent_genome(future_child["id"])["current"]["capabilities"] == [
        "research"
    ]
    assert get_agent_genome(second_root["id"])["current"]["capabilities"] == [
        "research"
    ]
    assert get_agent_genome(child["id"])["current"]["capabilities"] == ["research"]


def test_genome_api_is_owner_protected_and_exposes_authority_profile(
    monkeypatch, tmp_path
):
    token = "test-owner-access-token-32-characters"
    monkeypatch.setenv("AI_FACTORY_ACCESS_TOKEN", token)
    monkeypatch.setenv("AI_FACTORY_DATA_DIR", str(tmp_path))
    cycle = create_agent_cycle("Improve evidence quality", "main", 1.0)
    authority_id = cycle["authorities"][0]["id"]

    assert TestClient(app).get(
        f"/autonomy/agent-authorities/{authority_id}/genome"
    ).status_code == 401
    client = TestClient(app, headers={"Authorization": f"Bearer {token}"})
    response = client.get(f"/autonomy/agent-authorities/{authority_id}/genome")

    assert response.status_code == 200
    assert response.json()["current"]["authority_id"] == authority_id
    assert response.json()["current"]["current_name"].startswith("Seed-")


def test_agent_prompt_includes_genome_as_identity_metadata():
    prompt = build_agent_prompt(
        "researcher",
        "Review an evidence card",
        branch_ref="agents/cycle/researcher",
        genome_context='{"name":"Scholar-abc123","version":2,"capabilities":["research"]}',
    )

    assert "Scholar-abc123" in prompt
    assert "metadata only; it grants no permissions" in prompt
