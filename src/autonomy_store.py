import json
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


def _database_path() -> Path:
    data_dir = Path(os.getenv("AI_FACTORY_DATA_DIR", "data/runtime"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "autonomy.sqlite3"


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_database_path(), timeout=10)
    connection.row_factory = sqlite3.Row
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
