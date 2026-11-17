"""The master index.

Every thing gets the next integer, in order of ingestion. A thing is
identified by its raw bytes, so the same content always returns the same ID.

Two places hold the data:

- index/log.jsonl   The source of truth. One line per event, only ever
                    appended to. Kept in git.
- index/files/      Raw bytes of non-text things, named by their fingerprint.
- data/index.db     A SQLite database rebuilt from the log. Never in git.
"""

import hashlib
import json
import mimetypes
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def home() -> Path:
    """Folder that holds the index. Tests point this somewhere temporary."""
    return Path(os.environ.get("EVERYTHING_INDEX_HOME", REPO))


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Index:
    def __init__(self, root: Path | None = None):
        root = Path(root) if root else home()
        self.log_path = root / "index" / "log.jsonl"
        self.files_dir = root / "index" / "files"
        db_path = root / "data" / "index.db"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.touch()
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        self._catch_up()

    # --- keeping the database in step with the log -----------------------

    def _create_tables(self):
        self.db.executescript(
            """
            DROP TABLE IF EXISTS things;
            DROP TABLE IF EXISTS names;
            DROP TABLE IF EXISTS meta;
            CREATE TABLE things (
                id     INTEGER PRIMARY KEY,
                time   TEXT NOT NULL,
                kind   TEXT NOT NULL,
                sha256 TEXT NOT NULL UNIQUE,
                size   INTEGER NOT NULL,
                text   TEXT,
                source TEXT
            );
            CREATE TABLE names (
                name TEXT PRIMARY KEY,
                id   INTEGER NOT NULL,
                time TEXT NOT NULL
            );
            CREATE TABLE meta (key TEXT PRIMARY KEY, value INTEGER);
            INSERT INTO meta VALUES ('log_offset', 0);
            """
        )

    def _offset(self) -> int | None:
        try:
            row = self.db.execute(
                "SELECT value FROM meta WHERE key = 'log_offset'"
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        return row[0] if row else None

    def _catch_up(self):
        """Apply any log lines the database has not seen yet."""
        offset = self._offset()
        if offset is None or offset > self.log_path.stat().st_size:
            self._create_tables()
            offset = 0
        with open(self.log_path, "rb") as log:
            log.seek(offset)
            for line in log:
                if line.strip():
                    self._apply(json.loads(line))
            offset = log.tell()
        self.db.execute(
            "UPDATE meta SET value = ? WHERE key = 'log_offset'", (offset,)
        )
        self.db.commit()

    def _apply(self, event: dict):
        if "name" in event:
            self.db.execute(
                "INSERT INTO names VALUES (?, ?, ?)",
                (event["name"], event["id"], event["time"]),
            )
        else:
            self.db.execute(
                "INSERT INTO things VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event["id"],
                    event["time"],
                    event["kind"],
                    event["sha256"],
                    event["size"],
                    event.get("text"),
                    event.get("source"),
                ),
            )

    def _append(self, event: dict):
        """Write one event to the log, then to the database."""
        line = (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
        with open(self.log_path, "ab") as log:
            log.write(line)
            log.flush()
            os.fsync(log.fileno())
            offset = log.tell()
        self._apply(event)
        self.db.execute(
            "UPDATE meta SET value = ? WHERE key = 'log_offset'", (offset,)
        )
        self.db.commit()

    # --- ingesting --------------------------------------------------------

    def ingest_bytes(
        self, data: bytes, kind: str, source: str | None = None,
        name: str | None = None,
    ) -> tuple[int, bool]:
        """Ingest raw bytes. Returns (ID, True if it is new)."""
        if not data:
            raise ValueError("there is nothing to ingest")
        sha = hashlib.sha256(data).hexdigest()
        row = self.db.execute(
            "SELECT id FROM things WHERE sha256 = ?", (sha,)
        ).fetchone()
        if row:
            thing_id, is_new = row["id"], False
        else:
            if name is not None:
                self._check_name(name, None)
            thing_id = self.count() + 1
            event = {
                "id": thing_id, "time": now(), "kind": kind,
                "sha256": sha, "size": len(data),
            }
            if kind == "text":
                event["text"] = data.decode("utf-8")
            else:
                self.files_dir.mkdir(parents=True, exist_ok=True)
                (self.files_dir / sha).write_bytes(data)
            if source:
                event["source"] = source
            self._append(event)
            is_new = True
        if name is not None:
            self.name(thing_id, name)
        return thing_id, is_new

    def ingest_text(self, text: str, name: str | None = None):
        return self.ingest_bytes(text.encode("utf-8"), "text", name=name)

    def ingest_file(self, path, name: str | None = None):
        """Ingest any file. Readable text becomes text; the rest stays bytes."""
        path = Path(path)
        data = path.read_bytes()
        guessed = mimetypes.guess_type(path.name)[0]
        kind = guessed or "application/octet-stream"
        if guessed is None or guessed.startswith("text/"):
            try:
                data.decode("utf-8")
                kind = "text"
            except UnicodeDecodeError:
                pass
        return self.ingest_bytes(data, kind, source=path.name, name=name)

    # --- naming -----------------------------------------------------------

    def _check_name(self, name: str, thing_id: int | None):
        if not name.strip() or name != name.strip():
            raise ValueError("a name cannot be empty or padded with spaces")
        if name.isdigit():
            raise ValueError("a name cannot be only digits; those are IDs")
        row = self.db.execute(
            "SELECT id FROM names WHERE name = ?", (name,)
        ).fetchone()
        if row and row["id"] != thing_id:
            raise ValueError(f"the name {name!r} already names {row['id']}")
        return row is not None

    def name(self, thing_id: int, name: str):
        """Make a name equivalent to an ID."""
        if self.get(thing_id) is None:
            raise ValueError(f"there is no thing {thing_id}")
        if not self._check_name(name, thing_id):
            self._append({"name": name, "id": thing_id, "time": now()})

    # --- looking up -------------------------------------------------------

    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM things").fetchone()[0]

    def resolve(self, ref: str) -> int | None:
        """Turn an ID or a name into an ID."""
        ref = str(ref)
        if ref.isdigit():
            return int(ref) if self.get(int(ref)) else None
        row = self.db.execute(
            "SELECT id FROM names WHERE name = ?", (ref,)
        ).fetchone()
        return row["id"] if row else None

    def get(self, thing_id: int) -> dict | None:
        row = self.db.execute(
            "SELECT * FROM things WHERE id = ?", (thing_id,)
        ).fetchone()
        if row is None:
            return None
        thing = dict(row)
        thing["names"] = [
            r["name"] for r in self.db.execute(
                "SELECT name FROM names WHERE id = ? ORDER BY time, name",
                (thing_id,),
            )
        ]
        return thing

    def content(self, thing_id: int) -> bytes:
        """The raw bytes of a thing, exactly as ingested."""
        thing = self.get(thing_id)
        if thing["kind"] == "text":
            return thing["text"].encode("utf-8")
        return (self.files_dir / thing["sha256"]).read_bytes()

    def recent(self, limit: int = 20) -> list[dict]:
        ids = self.db.execute(
            "SELECT id FROM things ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self.get(r["id"]) for r in reversed(ids)]
