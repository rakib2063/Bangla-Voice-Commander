"""SQLite storage: settings, command history, custom commands."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

from .paths import data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, heard TEXT, intent TEXT,
    params TEXT, ok INTEGER, detail TEXT);
CREATE TABLE IF NOT EXISTS custom_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phrases TEXT NOT NULL,
    steps TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1);
"""


class Database:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else data_dir() / "bvc.sqlite3"
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    # ---- settings -------------------------------------------------------
    def all_settings(self) -> dict:
        with self._lock:
            rows = self._conn.execute("SELECT key, value FROM settings").fetchall()
        out = {}
        for r in rows:
            try:
                out[r["key"]] = json.loads(r["value"])
            except ValueError:
                pass
        return out

    def set_setting(self, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)",
                               (key, json.dumps(value, ensure_ascii=False)))
            self._conn.commit()

    # ---- history --------------------------------------------------------
    def add_history(self, heard: str, intent: str, params: dict, ok: bool, detail: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO history(ts, heard, intent, params, ok, detail) VALUES(?,?,?,?,?,?)",
                (time.time(), heard, intent, json.dumps(params, ensure_ascii=False), int(ok), detail))
            self._conn.commit()

    def recent_history(self, limit: int = 200) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def clear_history(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM history")
            self._conn.commit()

    def purge_history_older_than(self, days: int) -> None:
        cutoff = time.time() - days * 86400
        with self._lock:
            self._conn.execute("DELETE FROM history WHERE ts < ?", (cutoff,))
            self._conn.commit()

    # ---- custom commands ------------------------------------------------
    def list_custom(self, only_enabled: bool = False) -> list[dict]:
        q = "SELECT * FROM custom_commands" + (" WHERE enabled=1" if only_enabled else "") + " ORDER BY id"
        with self._lock:
            rows = self._conn.execute(q).fetchall()
        out = []
        for r in rows:
            out.append({"id": r["id"], "name": r["name"], "phrases": json.loads(r["phrases"]),
                        "steps": json.loads(r["steps"]), "enabled": bool(r["enabled"])})
        return out

    def save_custom(self, cid: Optional[int], name: str, phrases: list, steps: list,
                    enabled: bool = True) -> int:
        with self._lock:
            if cid:
                self._conn.execute(
                    "UPDATE custom_commands SET name=?, phrases=?, steps=?, enabled=? WHERE id=?",
                    (name, json.dumps(phrases, ensure_ascii=False), json.dumps(steps, ensure_ascii=False),
                     int(enabled), cid))
                self._conn.commit()
                return cid
            cur = self._conn.execute(
                "INSERT INTO custom_commands(name, phrases, steps, enabled) VALUES(?,?,?,?)",
                (name, json.dumps(phrases, ensure_ascii=False), json.dumps(steps, ensure_ascii=False),
                 int(enabled)))
            self._conn.commit()
            return int(cur.lastrowid)

    def delete_custom(self, cid: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM custom_commands WHERE id=?", (cid,))
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
