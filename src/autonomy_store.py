import json
import math
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List


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


def _database_path() -> Path:
    data_dir = Path(os.getenv("AI_FACTORY_DATA_DIR", "data/runtime"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "autonomy.sqlite3"


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
    authority_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(agent_authorities)")
    }
    if "worktree_path" not in authority_columns:
        connection.execute("ALTER TABLE agent_authorities ADD COLUMN worktree_path TEXT")
    if "proposal_evidence" not in authority_columns:
        connection.execute("ALTER TABLE agent_authorities ADD COLUMN proposal_evidence TEXT")
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
