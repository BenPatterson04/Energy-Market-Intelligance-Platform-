"""
GridWise Version 4 - Data Persistence Layer
=============================================

Lightweight SQLite store used for:
  - i-SEM / EirGrid historical snapshots (powers the Plotly historical charts)
  - Watchlist items (markets / metrics a user wants pinned)
  - Alerts (threshold rules) and the log of when they fired

SQLite is intentionally used here rather than Postgres for now - it needs
zero infrastructure, ships with Python, and is more than enough for a
single-dyno Flask deployment. When membership/accounts land in a later
version and data volume grows, this module is the seam to swap in Postgres
(e.g. via SQLAlchemy) without touching the rest of the app.
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

DB_PATH = os.getenv(
    "GRIDWISE_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "gridwise_history.db"),
)


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist yet. Safe to call on every boot."""

    with get_db() as conn:

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS isem_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at TEXT NOT NULL,
                region TEXT NOT NULL,
                demand_mw REAL,
                wind_mw REAL,
                wind_percent REAL,
                co2_intensity REAL,
                system_price_eur REAL,
                frequency_hz REAL
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_isem_recorded_at
            ON isem_snapshots (recorded_at)
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_key TEXT NOT NULL UNIQUE,
                label TEXT NOT NULL,
                category TEXT NOT NULL,
                added_at TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric TEXT NOT NULL,
                label TEXT NOT NULL,
                condition TEXT NOT NULL,
                threshold REAL NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alert_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id INTEGER NOT NULL,
                triggered_at TEXT NOT NULL,
                metric_value REAL,
                message TEXT,
                FOREIGN KEY (alert_id) REFERENCES alerts (id)
            )
            """
        )


# ---------------------------------------------------------------
# i-SEM snapshots
# ---------------------------------------------------------------

def record_isem_snapshot(region, demand_mw=None, wind_mw=None, wind_percent=None,
                          co2_intensity=None, system_price_eur=None, frequency_hz=None):

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO isem_snapshots
                (recorded_at, region, demand_mw, wind_mw, wind_percent,
                 co2_intensity, system_price_eur, frequency_hz)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.utcnow().isoformat(timespec="minutes"),
                region,
                demand_mw,
                wind_mw,
                wind_percent,
                co2_intensity,
                system_price_eur,
                frequency_hz,
            ),
        )


def get_isem_history(region="ALL", hours=24):
    """Return snapshots for the last `hours` hours, oldest first."""

    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat(timespec="minutes")

    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT recorded_at, demand_mw, wind_mw, wind_percent,
                   co2_intensity, system_price_eur, frequency_hz
            FROM isem_snapshots
            WHERE region = ? AND recorded_at >= ?
            ORDER BY recorded_at ASC
            """,
            (region, cutoff),
        ).fetchall()

    return [dict(row) for row in rows]


def prune_old_snapshots(days=90):
    """Housekeeping - keep the DB from growing forever on long-lived deploys."""

    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat(timespec="minutes")

    with get_db() as conn:
        conn.execute("DELETE FROM isem_snapshots WHERE recorded_at < ?", (cutoff,))


# ---------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------

def get_watchlist():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM watchlist ORDER BY added_at ASC"
        ).fetchall()
    return [dict(row) for row in rows]


def add_watchlist_item(item_key, label, category):
    with get_db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO watchlist (item_key, label, category, added_at)
            VALUES (?, ?, ?, ?)
            """,
            (item_key, label, category, datetime.utcnow().isoformat(timespec="minutes")),
        )


def remove_watchlist_item(item_key):
    with get_db() as conn:
        conn.execute("DELETE FROM watchlist WHERE item_key = ?", (item_key,))


# ---------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------

def get_alerts(active_only=False):
    query = "SELECT * FROM alerts"
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY created_at DESC"

    with get_db() as conn:
        rows = conn.execute(query).fetchall()
    return [dict(row) for row in rows]


def add_alert(metric, label, condition, threshold):
    """condition is one of: 'above', 'below'"""

    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO alerts (metric, label, condition, threshold, active, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (metric, label, condition, threshold, datetime.utcnow().isoformat(timespec="minutes")),
        )
        return cursor.lastrowid


def deactivate_alert(alert_id):
    with get_db() as conn:
        conn.execute("UPDATE alerts SET active = 0 WHERE id = ?", (alert_id,))


def log_alert_trigger(alert_id, metric_value, message):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO alert_log (alert_id, triggered_at, metric_value, message)
            VALUES (?, ?, ?, ?)
            """,
            (alert_id, datetime.utcnow().isoformat(timespec="minutes"), metric_value, message),
        )


def get_recent_alert_log(limit=20):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT alert_log.*, alerts.label, alerts.metric
            FROM alert_log
            JOIN alerts ON alerts.id = alert_log.alert_id
            ORDER BY alert_log.triggered_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def check_alerts(current_values):
    """
    current_values: dict mapping metric name -> current numeric value
    e.g. {"brent": 82.4, "isem_system_price": 145.2, "carbon_intensity": 210}

    Returns a list of newly-triggered alerts (also logs them).
    """

    triggered = []

    with get_db() as conn:
        rows = conn.execute("SELECT * FROM alerts WHERE active = 1").fetchall()

    for alert in rows:
        value = current_values.get(alert["metric"])

        if value is None:
            continue

        fired = False

        if alert["condition"] == "above" and value > alert["threshold"]:
            fired = True
        elif alert["condition"] == "below" and value < alert["threshold"]:
            fired = True

        if fired:
            message = f'{alert["label"]} is {alert["condition"]} {alert["threshold"]} (currently {value})'
            log_alert_trigger(alert["id"], value, message)
            triggered.append({
                "alert_id": alert["id"],
                "metric": alert["metric"],
                "label": alert["label"],
                "message": message,
                "value": value,
            })

    return triggered
