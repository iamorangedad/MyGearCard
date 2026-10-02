"""Small SQLite store for uploads, cards, and print orders."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone

from .config import DB_PATH, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS uploads (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    mime TEXT NOT NULL,
    relpath TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cards (
    id TEXT PRIMARY KEY,
    upload_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    prompt TEXT NOT NULL,
    relpath TEXT NOT NULL,
    mime TEXT NOT NULL,
    meta_json TEXT NOT NULL,
    copy_source TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    card_id TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price INTEGER NOT NULL,
    shipping_fee INTEGER NOT NULL,
    total INTEGER NOT NULL,
    status TEXT NOT NULL,
    carrier TEXT NOT NULL DEFAULT '',
    tracking_no TEXT NOT NULL DEFAULT '',
    contact_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_init_lock = threading.Lock()
_initialized = False


def connect() -> sqlite3.Connection:
    global _initialized
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if not _initialized:
        with _init_lock:
            if not _initialized:
                conn.executescript(SCHEMA)
                conn.commit()
                _initialized = True
    return conn


def init_db() -> None:
    with connect():
        return None


def insert_upload(upload_id: str, filename: str, mime: str, relpath: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO uploads (id, filename, mime, relpath, created_at) VALUES (?, ?, ?, ?, ?)",
            (upload_id, filename, mime, relpath, now()),
        )


def get_upload(upload_id: str):
    with connect() as conn:
        return conn.execute("SELECT * FROM uploads WHERE id = ?", (upload_id,)).fetchone()


def insert_card(row: dict) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO cards (
                id, upload_id, provider, name, category, prompt, relpath, mime,
                meta_json, copy_source, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["upload_id"],
                row["provider"],
                row["name"],
                row["category"],
                row["prompt"],
                row["relpath"],
                row["mime"],
                json.dumps(row["meta"], ensure_ascii=False),
                row["copy_source"],
                now(),
            ),
        )


def get_card(card_id: str):
    with connect() as conn:
        return conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()


def list_cards(limit: int = 12):
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM cards ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()


def insert_order(row: dict) -> None:
    stamp = now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO orders (
                id, card_id, quantity, unit_price, shipping_fee, total, status,
                carrier, tracking_no, contact_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, '', '', ?, ?, ?)
            """,
            (
                row["id"],
                row["card_id"],
                row["quantity"],
                row["unit_price"],
                row["shipping_fee"],
                row["total"],
                row["status"],
                json.dumps(row["contact"], ensure_ascii=False),
                stamp,
                stamp,
            ),
        )


def list_orders():
    with connect() as conn:
        return conn.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()


def get_order(order_id: str):
    with connect() as conn:
        return conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()


def update_order(order_id: str, status: str, carrier: str, tracking_no: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE orders
            SET status = ?, carrier = ?, tracking_no = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, carrier, tracking_no, now(), order_id),
        )
