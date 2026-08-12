"""SQLite persistence: mapping profiles, snapshots, opportunities.

Snapshots are append-only — never mutate a prior snapshot; week-over-week
deltas depend on that. All functions take db_path (defaults to
<repo>/data/agents.db, anchored to this file, never the cwd).
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "data" / "agents.db"

# Column order for the opportunities table (canonical + _raw + stage_bucket).
OPP_COLUMNS = [
    "account_name", "account_name_raw", "opportunity_name", "opportunity_id",
    "stage", "stage_bucket", "amount", "close_date", "owner", "owner_raw",
    "forecast_category", "probability", "last_activity_date", "product",
    "sub_vertical", "exec_sponsor", "created_date",
]

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS mapping_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    mapping_json TEXT NOT NULL,
    stage_map_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    imported_at TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    profile_id INTEGER,
    label TEXT NOT NULL,
    file_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS opportunities (
    snapshot_id INTEGER NOT NULL,
    {", ".join(f"{c} {'REAL' if c in ('amount', 'probability') else 'TEXT'}" for c in OPP_COLUMNS)}
);
CREATE INDEX IF NOT EXISTS idx_opps_snapshot ON opportunities(snapshot_id);
CREATE TABLE IF NOT EXISTS account_facts (
    account_name TEXT PRIMARY KEY,
    account_name_raw TEXT,
    sub_vertical TEXT,
    annual_spend REAL,
    agreement_end_date TEXT,
    install_base TEXT,
    incumbent_tools TEXT,
    known_gaps TEXT,
    exec_contacts TEXT,
    regulatory_scope TEXT,
    updated_at TEXT NOT NULL
);
"""

ACCOUNT_COLUMNS = [
    "account_name", "account_name_raw", "sub_vertical", "annual_spend",
    "agreement_end_date", "install_base", "incumbent_tools", "known_gaps",
    "exec_contacts", "regulatory_scope",
]


def _connect(db_path=None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    return con


def save_profile(name, mapping, stage_assignments, date_format, db_path=None) -> int:
    payload = json.dumps({"fields": mapping, "date_format": date_format})
    stages = json.dumps(stage_assignments)
    with _connect(db_path) as con:
        con.execute(
            """INSERT INTO mapping_profiles(name, created_at, mapping_json, stage_map_json)
               VALUES(?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE
               SET mapping_json = excluded.mapping_json,
                   stage_map_json = excluded.stage_map_json""",
            (name, dt.datetime.now().isoformat(timespec="seconds"), payload, stages),
        )
        row = con.execute("SELECT id FROM mapping_profiles WHERE name = ?", (name,)).fetchone()
        return row["id"]


def load_profiles(db_path=None) -> dict[str, dict]:
    with _connect(db_path) as con:
        rows = con.execute("SELECT * FROM mapping_profiles ORDER BY name").fetchall()
    profiles = {}
    for r in rows:
        payload = json.loads(r["mapping_json"])
        profiles[r["name"]] = {
            "id": r["id"],
            "mapping": payload["fields"],
            "date_format": payload.get("date_format", "auto"),
            "stage_assignments": json.loads(r["stage_map_json"]),
        }
    return profiles


def find_snapshot_by_hash(file_sha256: str, db_path=None):
    with _connect(db_path) as con:
        row = con.execute(
            "SELECT * FROM snapshots WHERE file_sha256 = ? ORDER BY id DESC LIMIT 1",
            (file_sha256,),
        ).fetchone()
    return dict(row) if row else None


def create_snapshot(label, as_of_date, profile_id, file_sha256, db_path=None) -> int:
    with _connect(db_path) as con:
        cur = con.execute(
            """INSERT INTO snapshots(imported_at, as_of_date, profile_id, label, file_sha256)
               VALUES(?, ?, ?, ?, ?)""",
            (
                dt.datetime.now().isoformat(timespec="seconds"),
                str(as_of_date),
                profile_id,
                label,
                file_sha256,
            ),
        )
        return cur.lastrowid


def _opp_rows(snapshot_id: int, df: pd.DataFrame) -> list[list]:
    rows = []
    for _, r in df.iterrows():
        values = [snapshot_id]
        for col in OPP_COLUMNS:
            v = r.get(col)
            values.append(None if v is None or pd.isna(v) else v)
        rows.append(values)
    return rows


_OPP_INSERT = (
    f"INSERT INTO opportunities(snapshot_id, {', '.join(OPP_COLUMNS)}) "
    f"VALUES({', '.join('?' for _ in range(len(OPP_COLUMNS) + 1))})"
)


def insert_opportunities(snapshot_id: int, df: pd.DataFrame, db_path=None) -> int:
    rows = _opp_rows(snapshot_id, df)
    with _connect(db_path) as con:
        con.executemany(_OPP_INSERT, rows)
    return len(rows)


def write_snapshot(
    label, as_of_date, profile_id, file_sha256, df: pd.DataFrame, db_path=None
) -> int:
    """Snapshot row + opportunity rows in ONE transaction — a failed import
    writes nothing, so its hash can never poison the duplicate guard."""
    with _connect(db_path) as con:
        cur = con.execute(
            """INSERT INTO snapshots(imported_at, as_of_date, profile_id, label, file_sha256)
               VALUES(?, ?, ?, ?, ?)""",
            (
                dt.datetime.now().isoformat(timespec="seconds"),
                str(as_of_date),
                profile_id,
                label,
                file_sha256,
            ),
        )
        snapshot_id = cur.lastrowid
        con.executemany(_OPP_INSERT, _opp_rows(snapshot_id, df))
        return snapshot_id


def upsert_account_facts(df: pd.DataFrame, db_path=None) -> int:
    """Replace-latest-by-account semantics: facts are current state, not
    history — a re-import of an account overwrites its previous row."""
    now = dt.datetime.now().isoformat(timespec="seconds")
    rows = []
    for _, r in df.iterrows():
        values = []
        for col in ACCOUNT_COLUMNS:
            v = r.get(col)
            values.append(None if v is None or pd.isna(v) else v)
        values.append(now)
        rows.append(values)
    with _connect(db_path) as con:
        con.executemany(
            f"INSERT OR REPLACE INTO account_facts({', '.join(ACCOUNT_COLUMNS)}, updated_at) "
            f"VALUES({', '.join('?' for _ in range(len(ACCOUNT_COLUMNS) + 1))})",
            rows,
        )
    return len(rows)


def load_account_facts(db_path=None) -> pd.DataFrame:
    with _connect(db_path) as con:
        rows = con.execute(
            "SELECT * FROM account_facts ORDER BY account_name"
        ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def list_snapshots(db_path=None) -> pd.DataFrame:
    with _connect(db_path) as con:
        rows = con.execute(
            """SELECT s.*, COUNT(o.snapshot_id) AS n_rows
               FROM snapshots s LEFT JOIN opportunities o ON o.snapshot_id = s.id
               GROUP BY s.id ORDER BY s.as_of_date DESC, s.id DESC"""
        ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def get_opportunities(snapshot_id: int, db_path=None) -> pd.DataFrame:
    with _connect(db_path) as con:
        rows = con.execute(
            "SELECT * FROM opportunities WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchall()
    if not rows:
        # A zero-row snapshot must still carry its columns, else every
        # df["stage_bucket"] access downstream raises KeyError.
        return pd.DataFrame(columns=["snapshot_id", *OPP_COLUMNS])
    return pd.DataFrame([dict(r) for r in rows])
