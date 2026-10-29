import json
import hashlib
import math
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse


METRIC_DIRECTIONS = {
    "quality": 1,
    "adoption": 1,
    "reusable_contribution": 1,
    "time_saved": 1,
    "cost_saved": 1,
    "maintenance_cost": -1,
    "negative_impact": -1,
}

ADVANCEMENT_AXES = {
    "revenue",
    "adoption",
    "quality",
    "reliability",
    "security",
    "research",
    "reusable_contribution",
    "time_saved",
    "cost_saved",
    "maintenance_cost",
    "negative_impact",
}

GENOME_CAPABILITIES = {
    "global_skills",
    "research",
    "code_development",
    "engine_development",
    "web_research",
}

_GENOME_NAME_PREFIXES = {
    "global_skills": "Atlas",
    "research": "Scholar",
    "code_development": "Forge",
    "engine_development": "Architect",
    "web_research": "Pathfinder",
}


def _database_path() -> Path:
    data_dir = Path(os.getenv("AI_FACTORY_DATA_DIR", "data/runtime"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "autonomy.sqlite3"


def _genome_name(authority_id: str, capabilities: List[str]) -> str:
    if not capabilities:
        prefix = "Seed"
    else:
        prefix = "-".join(
            _GENOME_NAME_PREFIXES[capability] for capability in sorted(capabilities)
        )
    return f"{prefix}-{authority_id[:6]}"


def _ensure_agent_genome(
    connection: sqlite3.Connection,
    authority_id: str,
    seen: set[str] | None = None,
) -> None:
    if connection.execute(
        "SELECT 1 FROM agent_genomes WHERE authority_id = ?", (authority_id,)
    ).fetchone():
        return
    seen = seen or set()
    if authority_id in seen:
        raise RuntimeError("agent authority lineage contains a cycle")
    seen.add(authority_id)

    authority = connection.execute(
        "SELECT parent_id FROM agent_authorities WHERE id = ?", (authority_id,)
    ).fetchone()
    if authority is None:
        return

    parent_genome = None
    inherited_capabilities: List[str] = []
    parent_version_id = None
    if authority["parent_id"]:
        parent = connection.execute(
            "SELECT id FROM agent_authorities WHERE id = ?", (authority["parent_id"],)
        ).fetchone()
        if parent:
            _ensure_agent_genome(connection, parent["id"], seen)
            parent_genome = connection.execute(
                """
                SELECT g.id, g.current_version, v.id AS version_id, v.capabilities_json
                FROM agent_genomes g
                JOIN agent_genome_versions v
                  ON v.genome_id = g.id AND v.version = g.current_version
                WHERE g.authority_id = ?
                """,
                (authority["parent_id"],),
            ).fetchone()
            if parent_genome:
                inherited_capabilities = json.loads(parent_genome["capabilities_json"])
                parent_version_id = parent_genome["version_id"]
    else:
        inherited_capabilities = [
            row["capability"]
            for row in connection.execute(
                """
                SELECT capability FROM agent_universal_genome_changes
                ORDER BY created_at, change_key
                """
            ).fetchall()
        ]
        inherited_capabilities = sorted(set(inherited_capabilities))

    genome_id = uuid.uuid4().hex
    version_id = uuid.uuid4().hex
    capabilities_json = json.dumps(sorted(inherited_capabilities))
    name = _genome_name(authority_id, sorted(inherited_capabilities))
    connection.execute(
        """
        INSERT INTO agent_genomes
            (id, authority_id, parent_genome_id, current_version, current_name)
        VALUES (?, ?, ?, 1, ?)
        """,
        (
            genome_id,
            authority_id,
            parent_genome["id"] if parent_genome else None,
            name,
        ),
    )
    connection.execute(
        """
        INSERT INTO agent_genome_versions
            (id, genome_id, version, display_name, capabilities_json,
             evidence, introspective_path, change_scope, universal_change_id,
             parent_version_id)
        VALUES (?, ?, 1, ?, ?, ?, ?, 'branch_fork', NULL, ?)
        """,
        (
            version_id,
            genome_id,
            name,
            capabilities_json,
            (
                (
                    "Initial branch genome; capability profile inherited from "
                    "its parent authority."
                    if parent_genome
                    else (
                        "Initial authority genome; capabilities derive only from "
                        "recorded universal changes."
                        if inherited_capabilities
                        else "Initial authority genome; no capabilities are presumed."
                    )
                )
            ),
            (
                f"Forked from parent genome version {parent_version_id}."
                if parent_version_id
                else (
                    "Created as a root genome from system universal-change records."
                    if inherited_capabilities
                    else "Created as the root genome for this authority."
                )
            ),
            parent_version_id,
        ),
    )


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_database_path(), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS outcomes (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            contributor_id TEXT NOT NULL,
            metric TEXT NOT NULL,
            baseline REAL NOT NULL,
            observed REAL NOT NULL,
            unit TEXT NOT NULL,
            evidence TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            review_note TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            verified_at TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            endpoint TEXT PRIMARY KEY,
            subscription_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS autonomy_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_cycles (
            id TEXT PRIMARY KEY,
            objective TEXT NOT NULL,
            base_branch TEXT NOT NULL,
            budget_total REAL NOT NULL,
            budget_remaining REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'exploring',
            source_issue TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_authorities (
            id TEXT PRIMARY KEY,
            cycle_id TEXT NOT NULL REFERENCES agent_cycles(id),
            parent_id TEXT REFERENCES agent_authorities(id),
            role TEXT NOT NULL,
            axis TEXT NOT NULL,
            objective TEXT NOT NULL,
            branch_ref TEXT NOT NULL,
            proposal_evidence TEXT,
            projected_gain REAL NOT NULL,
            confidence REAL NOT NULL,
            estimated_cost REAL NOT NULL,
            net_score REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            gate_evidence TEXT,
            actual_gain REAL,
            worktree_path TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_genomes (
            id TEXT PRIMARY KEY,
            authority_id TEXT NOT NULL UNIQUE REFERENCES agent_authorities(id),
            parent_genome_id TEXT REFERENCES agent_genomes(id),
            current_version INTEGER NOT NULL,
            current_name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_genome_versions (
            id TEXT PRIMARY KEY,
            genome_id TEXT NOT NULL REFERENCES agent_genomes(id),
            version INTEGER NOT NULL,
            display_name TEXT NOT NULL,
            capabilities_json TEXT NOT NULL,
            evidence TEXT NOT NULL,
            introspective_path TEXT NOT NULL,
            change_scope TEXT NOT NULL,
            universal_change_id TEXT,
            parent_version_id TEXT REFERENCES agent_genome_versions(id),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(genome_id, version)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_innovation_library (
            id TEXT PRIMARY KEY,
            genome_id TEXT NOT NULL REFERENCES agent_genomes(id),
            version INTEGER NOT NULL,
            frozen_name TEXT NOT NULL,
            frozen_genome_json TEXT NOT NULL,
            introspective_path TEXT NOT NULL,
            transition_evidence TEXT NOT NULL,
            change_scope TEXT NOT NULL,
            universal_change_id TEXT,
            frozen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(genome_id, version)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_universal_genome_changes (
            change_key TEXT PRIMARY KEY,
            capability TEXT NOT NULL,
            evidence TEXT NOT NULL,
            introspective_path TEXT NOT NULL,
            affected_genomes INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_issue_drafts (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            axis TEXT NOT NULL,
            evidence TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_research_findings (
            id TEXT PRIMARY KEY,
            cycle_id TEXT NOT NULL REFERENCES agent_cycles(id),
            authority_id TEXT NOT NULL REFERENCES agent_authorities(id),
            domain TEXT NOT NULL,
            claim TEXT NOT NULL,
            evidence_type TEXT NOT NULL,
            source_ref TEXT NOT NULL,
            observation TEXT NOT NULL,
            interpretation TEXT NOT NULL,
            competing_explanation TEXT NOT NULL,
            discriminating_test TEXT NOT NULL,
            limitations TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            reviewer_note TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_memory_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            verified_findings INTEGER NOT NULL,
            selected_findings INTEGER NOT NULL,
            compact_chars INTEGER NOT NULL,
            verbose_chars INTEGER NOT NULL,
            estimated_tokens INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_signal_graph_snapshots (
            id TEXT PRIMARY KEY,
            fingerprint TEXT NOT NULL UNIQUE,
            node_count INTEGER NOT NULL,
            edge_count INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_signal_graph_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            snapshot_id TEXT NOT NULL REFERENCES agent_signal_graph_snapshots(id),
            changed_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_signal_nodes (
            id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            cycle_id TEXT,
            authority_id TEXT,
            domain TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            salience REAL NOT NULL,
            summary TEXT NOT NULL,
            source_ref TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(source_type, source_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_signal_edges (
            source_id TEXT NOT NULL REFERENCES agent_signal_nodes(id),
            target_id TEXT NOT NULL REFERENCES agent_signal_nodes(id),
            relation TEXT NOT NULL,
            weight REAL NOT NULL,
            PRIMARY KEY(source_id, target_id, relation)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_intent_qa_suites (
            id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL UNIQUE
                REFERENCES agent_signal_graph_snapshots(id),
            cases_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_discovery_runs (
            id TEXT PRIMARY KEY,
            authority_id TEXT NOT NULL REFERENCES agent_authorities(id),
            novelty_score REAL NOT NULL,
            public_relevance_score REAL NOT NULL,
            rationale TEXT NOT NULL,
            search_triggered INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_search_leads (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES agent_discovery_runs(id),
            query TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            snippet TEXT NOT NULL,
            engine TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(run_id, query, url)
        )
        """
    )
    authority_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(agent_authorities)")
    }
    if "worktree_path" not in authority_columns:
        connection.execute("ALTER TABLE agent_authorities ADD COLUMN worktree_path TEXT")
    if "proposal_evidence" not in authority_columns:
        connection.execute("ALTER TABLE agent_authorities ADD COLUMN proposal_evidence TEXT")
    authority_ids = connection.execute(
        "SELECT id FROM agent_authorities ORDER BY created_at, id"
    ).fetchall()
    for row in authority_ids:
        _ensure_agent_genome(connection, row["id"])
    connection.commit()
    return connection


@contextmanager
def _connection():
    connection = _connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def create_outcome(
    *,
    agent_id: str,
    contributor_id: str,
    metric: str,
    baseline: float,
    observed: float,
    unit: str,
    evidence: str,
) -> Dict[str, Any]:
    if metric not in METRIC_DIRECTIONS:
        raise ValueError(f"unsupported metric: {metric}")
    outcome_id = uuid.uuid4().hex
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO outcomes
                (id, agent_id, contributor_id, metric, baseline, observed, unit, evidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                outcome_id,
                agent_id,
                contributor_id,
                metric,
                baseline,
                observed,
                unit,
                evidence,
            ),
        )
        row = connection.execute(
            "SELECT * FROM outcomes WHERE id = ?", (outcome_id,)
        ).fetchone()
    return _outcome_dict(row)


def _outcome_dict(row: sqlite3.Row) -> Dict[str, Any]:
    outcome = dict(row)
    outcome["net_deviation_percent"] = (
        METRIC_DIRECTIONS[outcome["metric"]]
        * (outcome["observed"] - outcome["baseline"])
        / max(abs(outcome["baseline"]), 1.0)
        * 100
    )
    return outcome


def list_outcomes(agent_id: str | None = None) -> List[Dict[str, Any]]:
    with _connection() as connection:
        if agent_id is None:
            rows = connection.execute(
                "SELECT * FROM outcomes ORDER BY created_at DESC"
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM outcomes WHERE agent_id = ? ORDER BY created_at DESC",
                (agent_id,),
            ).fetchall()
    return [_outcome_dict(row) for row in rows]


def verify_outcome(outcome_id: str, review_note: str) -> Dict[str, Any] | None:
    with _connection() as connection:
        cursor = connection.execute(
            """
            UPDATE outcomes
            SET status = 'verified', review_note = ?, verified_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'pending'
            """,
            (review_note, outcome_id),
        )
        if cursor.rowcount == 0:
            return None
        row = connection.execute(
            "SELECT * FROM outcomes WHERE id = ?", (outcome_id,)
        ).fetchone()
    return _outcome_dict(row)


def verified_outcome_summary(agent_id: str) -> List[Dict[str, Any]]:
    return [
        {
            "metric": outcome["metric"],
            "baseline": outcome["baseline"],
            "observed": outcome["observed"],
            "unit": outcome["unit"],
            "net_deviation_percent": round(outcome["net_deviation_percent"], 2),
        }
        for outcome in list_outcomes(agent_id)
        if outcome["status"] == "verified"
    ]


def agent_net_deviation(agent_id: str) -> Dict[str, Any]:
    outcomes = verified_outcome_summary(agent_id)
    if not outcomes:
        return {
            "agent_id": agent_id,
            "verified_outcomes": 0,
            "net_deviation_index": None,
            "metrics": {},
        }
    grouped: Dict[str, List[float]] = {}
    for outcome in outcomes:
        grouped.setdefault(outcome["metric"], []).append(
            outcome["net_deviation_percent"]
        )
    by_metric = {
        metric: round(sum(values) / len(values), 2)
        for metric, values in sorted(grouped.items())
    }
    return {
        "agent_id": agent_id,
        "verified_outcomes": len(outcomes),
        "net_deviation_index": round(
            sum(by_metric.values()) / len(by_metric), 2
        ),
        "index_unit": "normalized percentage points; not currency",
        "metrics": by_metric,
    }


def set_shared_learning_opt_in(enabled: bool) -> None:
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO autonomy_settings (key, value) VALUES ('shared_learning_opt_in', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (json.dumps(enabled),),
        )


def get_shared_learning_opt_in() -> bool:
    with _connection() as connection:
        row = connection.execute(
            "SELECT value FROM autonomy_settings WHERE key = 'shared_learning_opt_in'"
        ).fetchone()
    return json.loads(row["value"]) if row else False


def save_push_subscription(subscription: Dict[str, Any]) -> None:
    endpoint = subscription.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
        raise ValueError("push endpoint must be an HTTPS URL")
    keys = subscription.get("keys")
    if not isinstance(keys, dict) or not all(
        isinstance(keys.get(key), str) and keys[key]
        for key in ("p256dh", "auth")
    ):
        raise ValueError("push subscription must contain p256dh and auth keys")
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO push_subscriptions (endpoint, subscription_json)
            VALUES (?, ?)
            ON CONFLICT(endpoint) DO UPDATE SET
                subscription_json = excluded.subscription_json
            """,
            (endpoint, json.dumps(subscription)),
        )


def list_push_subscriptions() -> List[Dict[str, Any]]:
    with _connection() as connection:
        rows = connection.execute(
            "SELECT subscription_json FROM push_subscriptions"
        ).fetchall()
    return [json.loads(row["subscription_json"]) for row in rows]


def delete_push_subscription(endpoint: str) -> None:
    with _connection() as connection:
        connection.execute(
            "DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,)
        )


def create_agent_cycle(
    objective: str,
    base_branch: str,
    resource_budget: float,
    source_issue: str | None = None,
) -> Dict[str, Any]:
    if not isinstance(objective, str) or not objective.strip():
        raise ValueError("objective and base branch are required")
    if not isinstance(base_branch, str) or not base_branch.strip():
        raise ValueError("objective and base branch are required")
    if (
        isinstance(resource_budget, bool)
        or not isinstance(resource_budget, (int, float))
        or not math.isfinite(resource_budget)
        or resource_budget <= 0
    ):
        raise ValueError("resource budget must be a positive finite number")

    cycle_id = uuid.uuid4().hex
    root_id = uuid.uuid4().hex
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO agent_cycles (id, objective, base_branch, budget_total, budget_remaining, source_issue)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (cycle_id, objective.strip(), base_branch.strip(), resource_budget, resource_budget, source_issue),
        )
        connection.execute(
            """
            INSERT INTO agent_authorities
                (id, cycle_id, role, axis, objective, branch_ref,
                 projected_gain, confidence, estimated_cost, net_score)
            VALUES (?, ?, 'main_watcher', 'overall', ?, ?, 0, 1, 0, 0)
            """,
            (root_id, cycle_id, objective.strip(), base_branch.strip()),
        )
        _ensure_agent_genome(connection, root_id)
    cycle = get_agent_cycle(cycle_id)
    if cycle is None:
        raise RuntimeError("created agent cycle could not be read back")
    return cycle


def create_agent_issue_draft(
    *,
    title: str,
    body: str,
    axis: str,
    evidence: str,
) -> Dict[str, Any]:
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ValueError("issue title must contain 1 to 200 characters")
    if not isinstance(body, str) or len(body.strip()) < 20 or len(body) > 10000:
        raise ValueError("issue body must contain 20 to 10000 characters")
    if not isinstance(axis, str) or axis not in ADVANCEMENT_AXES:
        raise ValueError(f"unsupported advancement axis: {axis}")
    if not isinstance(evidence, str) or len(evidence.strip()) < 10:
        raise ValueError("issue evidence must be at least 10 characters")

    issue_id = uuid.uuid4().hex
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO agent_issue_drafts (id, title, body, axis, evidence)
            VALUES (?, ?, ?, ?, ?)
            """,
            (issue_id, title.strip(), body.strip(), axis, evidence.strip()),
        )
        row = connection.execute(
            "SELECT * FROM agent_issue_drafts WHERE id = ?", (issue_id,)
        ).fetchone()
    return dict(row)


def list_agent_issue_drafts() -> List[Dict[str, Any]]:
    with _connection() as connection:
        rows = connection.execute(
            "SELECT * FROM agent_issue_drafts ORDER BY created_at DESC, id"
        ).fetchall()
    return [dict(row) for row in rows]


def list_agent_cycles(limit: int = 1000) -> List[Dict[str, Any]]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 5000:
        raise ValueError("agent cycle limit must be between 1 and 5000")
    with _connection() as connection:
        rows = connection.execute(
            "SELECT * FROM agent_cycles ORDER BY created_at DESC, id LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_agent_cycle(cycle_id: str) -> Dict[str, Any] | None:
    with _connection() as connection:
        cycle = connection.execute(
            "SELECT * FROM agent_cycles WHERE id = ?", (cycle_id,)
        ).fetchone()
        if cycle is None:
            return None
        authorities = connection.execute(
            "SELECT * FROM agent_authorities WHERE cycle_id = ? ORDER BY created_at, id",
            (cycle_id,),
        ).fetchall()
    return {"cycle": dict(cycle), "authorities": [dict(row) for row in authorities]}


def get_agent_authority(authority_id: str) -> Dict[str, Any] | None:
    with _connection() as connection:
        row = connection.execute(
            "SELECT * FROM agent_authorities WHERE id = ?", (authority_id,)
        ).fetchone()
    return dict(row) if row is not None else None


def _genome_profile(
    connection: sqlite3.Connection, authority_id: str
) -> Dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT g.id AS genome_id, g.authority_id, a.branch_ref, a.parent_id,
               g.parent_genome_id, g.current_version, g.current_name,
               v.id AS version_id,
               v.capabilities_json, v.evidence, v.introspective_path,
               v.change_scope, v.universal_change_id, v.created_at
        FROM agent_genomes g
        JOIN agent_authorities a ON a.id = g.authority_id
        JOIN agent_genome_versions v
          ON v.genome_id = g.id AND v.version = g.current_version
        WHERE g.authority_id = ?
        """,
        (authority_id,),
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["capabilities"] = json.loads(result.pop("capabilities_json"))
    return result


def get_agent_genome(authority_id: str) -> Dict[str, Any] | None:
    with _connection() as connection:
        genome = _genome_profile(connection, authority_id)
        if genome is None:
            return None
        versions = connection.execute(
            """
            SELECT * FROM agent_genome_versions
            WHERE genome_id = ? ORDER BY version
            """,
            (genome["genome_id"],),
        ).fetchall()
        library = connection.execute(
            """
            SELECT * FROM agent_innovation_library
            WHERE genome_id = ? ORDER BY version
            """,
            (genome["genome_id"],),
        ).fetchall()
    parsed_versions = [dict(row) for row in versions]
    for version in parsed_versions:
        version["capabilities"] = json.loads(version.pop("capabilities_json"))
    return {
        "current": genome,
        "versions": parsed_versions,
        "innovation_library": [
            {
                **dict(row),
                "frozen_genome": json.loads(row["frozen_genome_json"]),
            }
            for row in library
        ],
    }


def _list_agent_genomes(
    connection: sqlite3.Connection,
) -> List[Dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT g.authority_id FROM agent_genomes g
        JOIN agent_authorities a ON a.id = g.authority_id
        ORDER BY a.created_at, a.id
        """
    ).fetchall()
    return [
        profile
        for row in rows
        if (profile := _genome_profile(connection, row["authority_id"])) is not None
    ]


def list_agent_genomes() -> List[Dict[str, Any]]:
    with _connection() as connection:
        return _list_agent_genomes(connection)


def _evolve_genome_in_transaction(
    connection: sqlite3.Connection,
    profile: Dict[str, Any],
    *,
    capability: str,
    evidence: str,
    introspective_path: str,
    change_scope: str,
    universal_change_id: str | None,
) -> Dict[str, Any]:
    previous_version = profile["current_version"]
    previous_capabilities = profile["capabilities"]
    frozen_genome = {
        "authority_id": profile["authority_id"],
        "genome_id": profile["genome_id"],
        "version": previous_version,
        "name": profile["current_name"],
        "capabilities": previous_capabilities,
        "evidence": profile["evidence"],
        "introspective_path": profile["introspective_path"],
    }
    connection.execute(
        """
        INSERT OR IGNORE INTO agent_innovation_library
            (id, genome_id, version, frozen_name, frozen_genome_json,
             introspective_path, transition_evidence, change_scope,
             universal_change_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            uuid.uuid4().hex,
            profile["genome_id"],
            previous_version,
            profile["current_name"],
            json.dumps(frozen_genome, sort_keys=True),
            introspective_path.strip(),
            evidence.strip(),
            change_scope,
            universal_change_id,
        ),
    )
    next_capabilities = sorted(set(previous_capabilities) | {capability})
    next_version = previous_version + 1
    next_name = _genome_name(profile["authority_id"], next_capabilities)
    version_id = uuid.uuid4().hex
    connection.execute(
        """
        INSERT INTO agent_genome_versions
            (id, genome_id, version, display_name, capabilities_json,
             evidence, introspective_path, change_scope, universal_change_id,
             parent_version_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            version_id,
            profile["genome_id"],
            next_version,
            next_name,
            json.dumps(next_capabilities),
            evidence.strip(),
            introspective_path.strip(),
            change_scope,
            universal_change_id,
            profile["version_id"],
        ),
    )
    connection.execute(
        """
        UPDATE agent_genomes
        SET current_version = ?, current_name = ? WHERE id = ?
        """,
        (next_version, next_name, profile["genome_id"]),
    )
    evolved = _genome_profile(connection, profile["authority_id"])
    if evolved is None:
        raise RuntimeError("evolved authority genome could not be loaded")
    return evolved


def evolve_agent_genome(
    authority_id: str,
    *,
    capability: str,
    evidence: str,
    introspective_path: str,
) -> Dict[str, Any]:
    if capability not in GENOME_CAPABILITIES:
        raise ValueError(f"unsupported genome capability: {capability}")
    if not isinstance(evidence, str) or not 10 <= len(evidence.strip()) <= 4000:
        raise ValueError("capability evidence must contain 10 to 4000 characters")
    if (
        not isinstance(introspective_path, str)
        or not 20 <= len(introspective_path.strip()) <= 4000
    ):
        raise ValueError("introspective path must contain 20 to 4000 characters")
    with _connection() as connection:
        authority = connection.execute(
            "SELECT status, actual_gain FROM agent_authorities WHERE id = ?",
            (authority_id,),
        ).fetchone()
        if authority is None:
            raise ValueError("agent authority not found")
        if authority["status"] != "promotion_ready" or authority["actual_gain"] is None or authority["actual_gain"] <= 0:
            raise ValueError(
                "local genome evolution requires a tested, reviewed authority with positive measured gain"
            )
        profile = _genome_profile(connection, authority_id)
        if profile is None:
            raise RuntimeError("authority genome is missing")
        if capability in profile["capabilities"]:
            raise ValueError("authority genome already has this capability")
        return _evolve_genome_in_transaction(
            connection,
            profile,
            capability=capability,
            evidence=evidence,
            introspective_path=introspective_path,
            change_scope="local",
            universal_change_id=None,
        )


def apply_universal_genome_change(
    *,
    change_key: str,
    capability: str,
    evidence: str,
    introspective_path: str,
) -> Dict[str, Any]:
    if (
        not isinstance(change_key, str)
        or not 1 <= len(change_key.strip()) <= 120
    ):
        raise ValueError("universal genome change key must contain 1 to 120 characters")
    if capability not in GENOME_CAPABILITIES:
        raise ValueError(f"unsupported genome capability: {capability}")
    if not isinstance(evidence, str) or not 10 <= len(evidence.strip()) <= 4000:
        raise ValueError("capability evidence must contain 10 to 4000 characters")
    if (
        not isinstance(introspective_path, str)
        or not 20 <= len(introspective_path.strip()) <= 4000
    ):
        raise ValueError("introspective path must contain 20 to 4000 characters")

    normalized_key = change_key.strip()
    with _connection() as connection:
        existing = connection.execute(
            "SELECT * FROM agent_universal_genome_changes WHERE change_key = ?",
            (normalized_key,),
        ).fetchone()
        if existing:
            if (
                existing["capability"] != capability
                or existing["evidence"] != evidence.strip()
                or existing["introspective_path"] != introspective_path.strip()
            ):
                raise ValueError(
                    "universal change key already exists with different content"
                )
            return {
                "change": dict(existing),
                "genomes": _list_agent_genomes(connection),
                "already_applied": True,
            }
        profiles = _list_agent_genomes(connection)
        for profile in profiles:
            _evolve_genome_in_transaction(
                connection,
                profile,
                capability=capability,
                evidence=evidence,
                introspective_path=introspective_path,
                change_scope="universal",
                universal_change_id=normalized_key,
            )
        connection.execute(
            """
            INSERT INTO agent_universal_genome_changes
                (change_key, capability, evidence, introspective_path,
                 affected_genomes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                normalized_key,
                capability,
                evidence.strip(),
                introspective_path.strip(),
                len(profiles),
            ),
        )
        change = connection.execute(
            "SELECT * FROM agent_universal_genome_changes WHERE change_key = ?",
            (normalized_key,),
        ).fetchone()
        updated = _list_agent_genomes(connection)
    return {
        "change": dict(change),
        "genomes": updated,
        "already_applied": False,
    }


def attach_authority_worktree(authority_id: str, worktree_path: str) -> Dict[str, Any]:
    if not isinstance(worktree_path, str) or not worktree_path.strip():
        raise ValueError("authority worktree path is required")
    with _connection() as connection:
        cursor = connection.execute(
            """
            UPDATE agent_authorities
            SET worktree_path = ?
            WHERE id = ? AND status = 'active' AND worktree_path IS NULL
            """,
            (worktree_path, authority_id),
        )
        if cursor.rowcount == 0:
            row = connection.execute(
                "SELECT * FROM agent_authorities WHERE id = ?", (authority_id,)
            ).fetchone()
            if row is None:
                raise ValueError("authority not found")
            if row["worktree_path"]:
                raise ValueError("authority already has a worktree")
            raise ValueError("only active authorities can receive a worktree")
        row = connection.execute(
            "SELECT * FROM agent_authorities WHERE id = ?", (authority_id,)
        ).fetchone()
    return dict(row)


def expand_agent_authorities(
    cycle_id: str,
    parent_id: str,
    proposals: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    prepared = []
    for proposal in proposals:
        if not isinstance(proposal, dict):
            raise ValueError("each authority proposal must be an object")
        axis = proposal.get("axis")
        role = proposal.get("role", "explorer")
        objective = proposal.get("objective")
        evidence = proposal.get("evidence")
        projected_gain = proposal.get("projected_gain")
        confidence = proposal.get("confidence")
        estimated_cost = proposal.get("estimated_cost")
        if not isinstance(axis, str) or axis not in ADVANCEMENT_AXES:
            raise ValueError(f"unsupported advancement axis: {axis}")
        if not isinstance(objective, str) or not objective.strip():
            raise ValueError("authority objective is required")
        if not isinstance(evidence, str) or len(evidence.strip()) < 10:
            raise ValueError("evidence must be at least 10 characters")
        if not isinstance(role, str) or role not in {
            "explorer",
            "researcher",
            "planner",
            "builder",
            "reviewer",
            "intent_mapper",
            "novelty_analyst",
        }:
            raise ValueError(f"unsupported authority role: {role}")
        values = (projected_gain, confidence, estimated_cost)
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in values
        ):
            raise ValueError("projected gain, confidence, and cost must be finite numbers")
        if not 0 <= projected_gain <= 1 or not 0 <= confidence <= 1:
            raise ValueError("projected gain and confidence must be between 0 and 1")
        if not 0 < estimated_cost <= 1:
            raise ValueError("estimated cost must be greater than 0 and at most 1")
        net_score = projected_gain * confidence - estimated_cost
        if net_score > 0:
            prepared.append(
                {
                    "id": uuid.uuid4().hex,
                    "axis": axis,
                    "role": role,
                    "objective": objective.strip(),
                    "evidence": evidence.strip(),
                    "projected_gain": float(projected_gain),
                    "confidence": float(confidence),
                    "estimated_cost": float(estimated_cost),
                    "net_score": net_score,
                }
            )

    prepared.sort(key=lambda item: item["net_score"], reverse=True)
    created: List[Dict[str, Any]] = []
    with _connection() as connection:
        cycle = connection.execute(
            "SELECT * FROM agent_cycles WHERE id = ?", (cycle_id,)
        ).fetchone()
        parent = connection.execute(
            "SELECT * FROM agent_authorities WHERE id = ? AND cycle_id = ?",
            (parent_id, cycle_id),
        ).fetchone()
        if cycle is None or parent is None:
            raise ValueError("agent cycle or parent authority not found")
        if cycle["status"] != "exploring" or parent["status"] != "active":
            raise ValueError("authority can expand only while its cycle and parent are active")

        remaining = cycle["budget_remaining"]
        for item in prepared:
            if item["estimated_cost"] > remaining:
                continue
            duplicate = connection.execute(
                """
                SELECT 1 FROM agent_authorities
                WHERE cycle_id = ? AND parent_id = ? AND axis = ? AND objective = ?
                """,
                (cycle_id, parent_id, item["axis"], item["objective"]),
            ).fetchone()
            if duplicate:
                continue
            branch_ref = f"agents/{cycle_id}/{item['id']}"
            connection.execute(
                """
                INSERT INTO agent_authorities
                    (id, cycle_id, parent_id, role, axis, objective, branch_ref,
                     proposal_evidence, projected_gain, confidence, estimated_cost, net_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["id"],
                    cycle_id,
                    parent_id,
                    item["role"],
                    item["axis"],
                    item["objective"],
                    branch_ref,
                    item["evidence"],
                    item["projected_gain"],
                    item["confidence"],
                    item["estimated_cost"],
                    item["net_score"],
                ),
            )
            _ensure_agent_genome(connection, item["id"])
            remaining -= item["estimated_cost"]
            created.append({**item, "branch_ref": branch_ref, "status": "active"})
        connection.execute(
            "UPDATE agent_cycles SET budget_remaining = ? WHERE id = ?",
            (remaining, cycle_id),
        )
    return created


def evaluate_agent_authority(
    authority_id: str,
    *,
    tests_passed: bool,
    reviewer_approved: bool,
    evidence: str,
    actual_gain: float,
) -> Dict[str, Any] | None:
    if (
        not isinstance(tests_passed, bool)
        or not isinstance(reviewer_approved, bool)
        or not isinstance(evidence, str)
        or not evidence.strip()
        or isinstance(actual_gain, bool)
        or not isinstance(actual_gain, (int, float))
        or not math.isfinite(actual_gain)
    ):
        raise ValueError("gate evidence and a finite measured gain are required")
    status = "promotion_ready" if tests_passed and reviewer_approved else "rejected"
    with _connection() as connection:
        authority = connection.execute(
            "SELECT * FROM agent_authorities WHERE id = ?", (authority_id,)
        ).fetchone()
        if authority is None:
            return None
        if authority["status"] != "active":
            raise ValueError("only active authorities can be evaluated")
        connection.execute(
            """
            UPDATE agent_authorities
            SET status = ?, gate_evidence = ?, actual_gain = ?
            WHERE id = ?
            """,
            (status, evidence.strip(), actual_gain, authority_id),
        )
        row = connection.execute(
            "SELECT * FROM agent_authorities WHERE id = ?", (authority_id,)
        ).fetchone()
    return dict(row)


def create_agent_research_finding(
    authority_id: str,
    *,
    domain: str,
    claim: str,
    evidence_type: str,
    source_ref: str,
    observation: str,
    interpretation: str,
    competing_explanation: str,
    discriminating_test: str,
    limitations: str,
) -> Dict[str, Any]:
    fields = {
        "domain": domain,
        "claim": claim,
        "source_ref": source_ref,
        "observation": observation,
        "interpretation": interpretation,
        "competing_explanation": competing_explanation,
        "discriminating_test": discriminating_test,
        "limitations": limitations,
    }
    if any(not isinstance(value, str) or not value.strip() for value in fields.values()):
        raise ValueError("all research finding fields are required")
    limits = {
        "domain": 120,
        "claim": 1000,
        "source_ref": 1000,
        "observation": 2000,
        "interpretation": 2000,
        "competing_explanation": 2000,
        "discriminating_test": 2000,
        "limitations": 2000,
    }
    if any(len(fields[name].strip()) > limit for name, limit in limits.items()):
        raise ValueError("research finding field exceeds its maximum length")
    if evidence_type not in {
        "published_measurement",
        "reproduced_result",
        "calculation",
        "model_result",
        "interpretation",
        "hypothesis",
    }:
        raise ValueError(f"unsupported research evidence type: {evidence_type}")

    finding_id = uuid.uuid4().hex
    with _connection() as connection:
        authority = connection.execute(
            "SELECT cycle_id FROM agent_authorities WHERE id = ?",
            (authority_id,),
        ).fetchone()
        if authority is None:
            raise ValueError("research finding authority not found")
        connection.execute(
            """
            INSERT INTO agent_research_findings
                (id, cycle_id, authority_id, domain, claim, evidence_type,
                 source_ref, observation, interpretation, competing_explanation,
                 discriminating_test, limitations)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding_id,
                authority["cycle_id"],
                authority_id,
                *(fields[name].strip() for name in (
                    "domain",
                    "claim",
                )),
                evidence_type,
                *(fields[name].strip() for name in (
                    "source_ref",
                    "observation",
                    "interpretation",
                    "competing_explanation",
                    "discriminating_test",
                    "limitations",
                )),
            ),
        )
        row = connection.execute(
            "SELECT * FROM agent_research_findings WHERE id = ?",
            (finding_id,),
        ).fetchone()
    return dict(row)


def review_agent_research_finding(
    finding_id: str, *, decision: str, reviewer_note: str
) -> Dict[str, Any] | None:
    if decision not in {"verified", "contradicted"}:
        raise ValueError("research finding decision must be verified or contradicted")
    if not isinstance(reviewer_note, str) or len(reviewer_note.strip()) < 10:
        raise ValueError("reviewer note must contain at least 10 characters")
    if len(reviewer_note) > 2000:
        raise ValueError("reviewer note must not exceed 2000 characters")

    with _connection() as connection:
        row = connection.execute(
            "SELECT * FROM agent_research_findings WHERE id = ?",
            (finding_id,),
        ).fetchone()
        if row is None:
            return None
        if row["status"] != "draft":
            raise ValueError("only draft research findings can be reviewed")
        connection.execute(
            """
            UPDATE agent_research_findings
            SET status = ?, reviewer_note = ?, reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'draft'
            """,
            (decision, reviewer_note.strip(), finding_id),
        )
        reviewed = connection.execute(
            "SELECT * FROM agent_research_findings WHERE id = ?",
            (finding_id,),
        ).fetchone()
    return dict(reviewed)


def list_agent_research_findings(
    *, status: str | None = None, limit: int = 500
) -> List[Dict[str, Any]]:
    if status is not None and status not in {"draft", "verified", "contradicted"}:
        raise ValueError(f"unsupported research finding status: {status}")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("research finding limit must be between 1 and 1000")
    with _connection() as connection:
        if status is None:
            rows = connection.execute(
                """
                SELECT * FROM agent_research_findings
                ORDER BY created_at DESC, id LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT * FROM agent_research_findings
                WHERE status = ?
                ORDER BY created_at DESC, id LIMIT ?
                """,
                (status, limit),
            ).fetchall()
    return [dict(row) for row in rows]


def record_agent_memory_usage(role: str, metrics: Dict[str, Any]) -> Dict[str, Any]:
    if role not in {
        "main_watcher",
        "scout",
        "explorer",
        "researcher",
        "planner",
        "builder",
        "reviewer",
        "intent_mapper",
        "novelty_analyst",
    }:
        raise ValueError(f"unsupported native agent role: {role}")
    metric_fields = {
        "verified_findings": metrics.get("verified_findings"),
        "selected_findings": metrics.get("selected_findings"),
        "compact_chars": metrics.get("compact_chars"),
        "verbose_chars": metrics.get("verbose_chars"),
        "estimated_tokens": metrics.get("estimated_tokens"),
    }
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in metric_fields.values()
    ):
        raise ValueError("memory usage metrics must be non-negative integers")
    if metric_fields["selected_findings"] > metric_fields["verified_findings"]:
        raise ValueError("selected finding count cannot exceed verified finding count")
    with _connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO agent_memory_usage
                (role, verified_findings, selected_findings, compact_chars,
                 verbose_chars, estimated_tokens)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                role,
                metric_fields["verified_findings"],
                metric_fields["selected_findings"],
                metric_fields["compact_chars"],
                metric_fields["verbose_chars"],
                metric_fields["estimated_tokens"],
            ),
        )
        row = connection.execute(
            "SELECT * FROM agent_memory_usage WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return dict(row)


def list_agent_memory_usage(limit: int = 100) -> List[Dict[str, Any]]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("memory usage limit must be between 1 and 1000")
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM agent_memory_usage
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_agent_authorities(limit: int = 1000) -> List[Dict[str, Any]]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 5000:
        raise ValueError("authority limit must be between 1 and 5000")
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM agent_authorities
            ORDER BY created_at DESC, id LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def persist_agent_signal_graph(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    *,
    stability_seconds: int,
) -> Dict[str, Any]:
    if (
        isinstance(stability_seconds, bool)
        or not isinstance(stability_seconds, int)
        or not 0 <= stability_seconds <= 86400
    ):
        raise ValueError("graph stability interval must be between 0 and 86400 seconds")
    if len(nodes) > 5000 or len(edges) > 20000:
        raise ValueError("signal graph exceeds its bounded node or edge capacity")

    required_node_fields = (
        "id",
        "source_type",
        "source_id",
        "domain",
        "signal_type",
        "summary",
        "source_ref",
        "created_at",
    )
    node_ids = set()
    for node in nodes:
        if not isinstance(node, dict) or any(
            not isinstance(node.get(field), str) or not node[field].strip()
            for field in required_node_fields
        ):
            raise ValueError("signal graph nodes are missing required text fields")
        salience = node.get("salience")
        if (
            isinstance(salience, bool)
            or not isinstance(salience, (int, float))
            or not math.isfinite(salience)
            or not 0 <= salience <= 1
        ):
            raise ValueError("signal graph salience must be between 0 and 1")
        if len(node["summary"]) > 4000 or len(node["source_ref"]) > 1000:
            raise ValueError("signal graph node text exceeds its size limit")
        if node["id"] in node_ids:
            raise ValueError("signal graph node IDs must be unique")
        node_ids.add(node["id"])

    for edge in edges:
        if not isinstance(edge, dict):
            raise ValueError("signal graph edges must be objects")
        if edge.get("source_id") not in node_ids or edge.get("target_id") not in node_ids:
            raise ValueError("signal graph edge references an unknown node")
        if edge.get("source_id") == edge.get("target_id"):
            raise ValueError("signal graph self-edges are not allowed")
        if not isinstance(edge.get("relation"), str) or not edge["relation"].strip():
            raise ValueError("signal graph edge relation is required")
        weight = edge.get("weight")
        if (
            isinstance(weight, bool)
            or not isinstance(weight, (int, float))
            or not math.isfinite(weight)
            or not 0 <= weight <= 1
        ):
            raise ValueError("signal graph edge weight must be between 0 and 1")

    normalized_nodes = sorted(nodes, key=lambda node: node["id"])
    normalized_edges = sorted(
        edges,
        key=lambda edge: (
            edge["source_id"],
            edge["target_id"],
            edge["relation"],
        ),
    )
    fingerprint = hashlib.sha256(
        json.dumps(
            {"nodes": normalized_nodes, "edges": normalized_edges},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    now = datetime.now(timezone.utc)
    with _connection() as connection:
        state = connection.execute(
            "SELECT snapshot_id, changed_at FROM agent_signal_graph_state WHERE id = 1"
        ).fetchone()
        if state is None or state["snapshot_id"] is None:
            snapshot_id = uuid.uuid4().hex
            changed_at = now.isoformat()
            connection.execute(
                """
                INSERT INTO agent_signal_graph_snapshots
                    (id, fingerprint, node_count, edge_count, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (snapshot_id, fingerprint, len(nodes), len(edges), changed_at),
            )
            connection.execute(
                """
                INSERT INTO agent_signal_graph_state (id, snapshot_id, changed_at)
                VALUES (1, ?, ?)
                """,
                (snapshot_id, changed_at),
            )
        else:
            current_snapshot = connection.execute(
                "SELECT fingerprint FROM agent_signal_graph_snapshots WHERE id = ?",
                (state["snapshot_id"],),
            ).fetchone()
            if current_snapshot is None:
                raise RuntimeError("signal graph state references a missing snapshot")
            snapshot_id = state["snapshot_id"]
            changed_at = state["changed_at"]
            if current_snapshot["fingerprint"] != fingerprint:
                changed_at = now.isoformat()
                existing_snapshot = connection.execute(
                    "SELECT id FROM agent_signal_graph_snapshots WHERE fingerprint = ?",
                    (fingerprint,),
                ).fetchone()
                if existing_snapshot is None:
                    snapshot_id = uuid.uuid4().hex
                    connection.execute(
                        """
                        INSERT INTO agent_signal_graph_snapshots
                            (id, fingerprint, node_count, edge_count, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (snapshot_id, fingerprint, len(nodes), len(edges), changed_at),
                    )
                else:
                    snapshot_id = existing_snapshot["id"]
                connection.execute(
                    """
                    UPDATE agent_signal_graph_state
                    SET snapshot_id = ?, changed_at = ?
                    WHERE id = 1
                    """,
                    (snapshot_id, changed_at),
                )

        connection.execute("DELETE FROM agent_signal_edges")
        connection.execute("DELETE FROM agent_signal_nodes")
        connection.executemany(
            """
            INSERT INTO agent_signal_nodes
                (id, source_type, source_id, cycle_id, authority_id, domain,
                 signal_type, salience, summary, source_ref, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    node["id"],
                    node["source_type"],
                    node["source_id"],
                    node.get("cycle_id"),
                    node.get("authority_id"),
                    node["domain"],
                    node["signal_type"],
                    float(node["salience"]),
                    node["summary"],
                    node["source_ref"],
                    node["created_at"],
                )
                for node in nodes
            ],
        )
        connection.executemany(
            """
            INSERT INTO agent_signal_edges (source_id, target_id, relation, weight)
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    edge["source_id"],
                    edge["target_id"],
                    edge["relation"],
                    float(edge["weight"]),
                )
                for edge in edges
            ],
        )
        suite = connection.execute(
            "SELECT id FROM agent_intent_qa_suites WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()

    stable_since = datetime.fromisoformat(changed_at)
    stable_seconds = max(0, (now - stable_since).total_seconds())
    return {
        "snapshot_id": snapshot_id,
        "fingerprint": fingerprint,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "stable_since": changed_at,
        "stable_for_seconds": stable_seconds,
        "inquiry_due": (
            bool(nodes)
            and stable_seconds >= stability_seconds
            and suite is None
        ),
    }


def get_agent_signal_graph() -> Dict[str, Any]:
    with _connection() as connection:
        state = connection.execute(
            """
            SELECT state.snapshot_id, state.changed_at, snapshot.fingerprint,
                   snapshot.node_count, snapshot.edge_count
            FROM agent_signal_graph_state AS state
            JOIN agent_signal_graph_snapshots AS snapshot
                ON snapshot.id = state.snapshot_id
            WHERE state.id = 1
            """
        ).fetchone()
        nodes = connection.execute(
            "SELECT * FROM agent_signal_nodes ORDER BY created_at, id"
        ).fetchall()
        edges = connection.execute(
            "SELECT * FROM agent_signal_edges ORDER BY source_id, target_id, relation"
        ).fetchall()
        suites = connection.execute(
            "SELECT * FROM agent_intent_qa_suites ORDER BY created_at DESC, id"
        ).fetchall()
    return {
        "snapshot": dict(state) if state is not None else None,
        "nodes": [dict(row) for row in nodes],
        "edges": [dict(row) for row in edges],
        "intent_qa_suites": [
            {
                **dict(row),
                "cases": json.loads(row["cases_json"]),
            }
            for row in suites
        ],
    }


def create_agent_intent_qa_suite(
    snapshot_id: str,
    cases: List[Dict[str, Any]],
    *,
    stability_seconds: int,
) -> Dict[str, Any]:
    if (
        isinstance(stability_seconds, bool)
        or not isinstance(stability_seconds, int)
        or not 0 <= stability_seconds <= 86400
    ):
        raise ValueError("graph stability interval must be between 0 and 86400 seconds")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 100:
        raise ValueError("intent QA suite must contain between 1 and 100 cases")

    node_ids = set()
    normalized_cases = []
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("intent QA cases must be objects")
        for field in ("title", "intent", "preconditions", "assertions"):
            if (
                not isinstance(case.get(field), str)
                or not case[field].strip()
                or len(case[field]) > 2000
            ):
                raise ValueError(f"intent QA case requires bounded {field} text")
        signal_ids = case.get("signal_ids")
        if (
            not isinstance(signal_ids, list)
            or not signal_ids
            or any(not isinstance(item, str) for item in signal_ids)
        ):
            raise ValueError("intent QA case must reference its supporting signal nodes")
        normalized_cases.append(
            {
                field: case[field].strip()
                for field in ("title", "intent", "preconditions", "assertions")
            }
            | {"signal_ids": signal_ids}
        )

    now = datetime.now(timezone.utc)
    with _connection() as connection:
        state = connection.execute(
            """
            SELECT state.snapshot_id, state.changed_at
            FROM agent_signal_graph_state AS state
            WHERE state.id = 1
            """
        ).fetchone()
        if state is None or state["snapshot_id"] != snapshot_id:
            raise ValueError("intent QA must target the current graph snapshot")
        if (now - datetime.fromisoformat(state["changed_at"])).total_seconds() < stability_seconds:
            raise ValueError("signal graph has not remained stable for the required interval")
        if connection.execute(
            "SELECT 1 FROM agent_intent_qa_suites WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone():
            raise ValueError("an intent QA suite already exists for this graph snapshot")
        node_ids = {
            row["id"]
            for row in connection.execute("SELECT id FROM agent_signal_nodes")
        }
        for case in normalized_cases:
            if any(signal_id not in node_ids for signal_id in case["signal_ids"]):
                raise ValueError("intent QA case references a missing signal node")
        suite_id = uuid.uuid4().hex
        connection.execute(
            """
            INSERT INTO agent_intent_qa_suites
                (id, snapshot_id, cases_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                suite_id,
                snapshot_id,
                json.dumps(normalized_cases, ensure_ascii=False),
                now.isoformat(),
            ),
        )
    return {
        "id": suite_id,
        "snapshot_id": snapshot_id,
        "cases": normalized_cases,
        "status": "draft",
        "created_at": now.isoformat(),
    }


def list_agent_intent_qa_suites() -> List[Dict[str, Any]]:
    with _connection() as connection:
        rows = connection.execute(
            "SELECT * FROM agent_intent_qa_suites ORDER BY created_at DESC, id"
        ).fetchall()
    return [
        {
            **dict(row),
            "cases": json.loads(row["cases_json"]),
        }
        for row in rows
    ]


def count_agent_discovery_runs_since(authority_id: str, since: str) -> int:
    with _connection() as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM agent_discovery_runs
            WHERE authority_id = ? AND created_at >= ?
            """,
            (authority_id, since),
        ).fetchone()
    return int(row["count"])


def record_agent_discovery_run(
    authority_id: str,
    *,
    novelty_score: float,
    public_relevance_score: float,
    rationale: str,
    searches: List[Dict[str, Any]],
) -> Dict[str, Any]:
    scores = (novelty_score, public_relevance_score)
    if any(
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not math.isfinite(score)
        or not 0 <= score <= 1
        for score in scores
    ):
        raise ValueError("discovery scores must be finite values between 0 and 1")
    if not isinstance(rationale, str) or not 1 <= len(rationale.strip()) <= 2000:
        raise ValueError("discovery rationale must contain 1 to 2000 characters")
    if not isinstance(searches, list) or len(searches) > 3:
        raise ValueError("a discovery run may contain at most three searches")
    for search in searches:
        if not isinstance(search, dict):
            raise ValueError("search records must be objects")
        query = search.get("query")
        results = search.get("results")
        if not isinstance(query, str) or not 3 <= len(query.strip()) <= 200:
            raise ValueError("search query must contain 3 to 200 characters")
        if not isinstance(results, list) or len(results) > 5:
            raise ValueError("each search may contain at most five result leads")
        for result in results:
            if not isinstance(result, dict):
                raise ValueError("search result leads must be objects")
            title = result.get("title")
            url = result.get("url")
            snippet = result.get("snippet", "")
            engine = result.get("engine", "search")
            parsed_url = urlparse(url) if isinstance(url, str) else None
            if (
                not isinstance(title, str)
                or not title.strip()
                or len(title) > 300
                or parsed_url is None
                or parsed_url.scheme != "https"
                or len(url) > 2048
                or not parsed_url.hostname
                or parsed_url.username
                or parsed_url.password
                or parsed_url.hostname.lower() in {"localhost"}
                or parsed_url.hostname.lower().endswith((".local", ".internal"))
                or not isinstance(snippet, str)
                or len(snippet) > 1500
                or not isinstance(engine, str)
                or len(engine) > 80
            ):
                raise ValueError("search result lead is invalid")

    run_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    search_triggered = bool(searches)
    with _connection() as connection:
        authority = connection.execute(
            """
            SELECT status, actual_gain FROM agent_authorities WHERE id = ?
            """,
            (authority_id,),
        ).fetchone()
        if authority is None:
            raise ValueError("discovery authority not found")
        if authority["status"] != "promotion_ready" or authority["actual_gain"] <= 0:
            raise ValueError("web discovery requires a positive, reviewed authority success")
        connection.execute(
            """
            INSERT INTO agent_discovery_runs
                (id, authority_id, novelty_score, public_relevance_score,
                 rationale, search_triggered, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                authority_id,
                float(novelty_score),
                float(public_relevance_score),
                rationale.strip(),
                int(search_triggered),
                now,
            ),
        )
        for search in searches:
            for result in search["results"]:
                connection.execute(
                    """
                    INSERT INTO agent_search_leads
                        (id, run_id, query, title, url, snippet, engine, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uuid.uuid4().hex,
                        run_id,
                        search["query"].strip(),
                        result["title"].strip(),
                        result["url"],
                        result.get("snippet", "").strip(),
                        result.get("engine", "search").strip(),
                        now,
                    ),
                )
        run = connection.execute(
            "SELECT * FROM agent_discovery_runs WHERE id = ?", (run_id,)
        ).fetchone()
        leads = connection.execute(
            "SELECT * FROM agent_search_leads WHERE run_id = ? ORDER BY query, id",
            (run_id,),
        ).fetchall()
    run_result = dict(run)
    run_result["search_triggered"] = bool(run_result["search_triggered"])
    return {"run": run_result, "leads": [dict(row) for row in leads]}


def list_agent_discovery_runs(limit: int = 100) -> List[Dict[str, Any]]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("discovery run limit must be between 1 and 1000")
    with _connection() as connection:
        rows = connection.execute(
            "SELECT * FROM agent_discovery_runs ORDER BY created_at DESC, id LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            **dict(row),
            "search_triggered": bool(row["search_triggered"]),
        }
        for row in rows
    ]


def list_agent_search_leads(
    *, run_id: str | None = None, limit: int = 100
) -> List[Dict[str, Any]]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("search lead limit must be between 1 and 1000")
    with _connection() as connection:
        if run_id is None:
            rows = connection.execute(
                """
                SELECT * FROM agent_search_leads
                ORDER BY created_at DESC, id LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT * FROM agent_search_leads
                WHERE run_id = ?
                ORDER BY query, id LIMIT ?
                """,
                (run_id, limit),
            ).fetchall()
    return [dict(row) for row in rows]
