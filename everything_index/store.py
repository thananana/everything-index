"""The master index.

Every thing gets the next integer, in order of ingestion. That integer is
its ID and never changes.

There are two ways a thing comes to exist:

- By content. Text or a file is ingested. It is identified by its raw
  bytes, so the same content always returns the same ID.
- By naming. An empty index is created as an anchor. Its ID and name stay
  fixed while what it contains is free to change.

Every thing has a table: the ordered list of the things it contains.
Where a thing appears in other tables is the same information read the
other way round, so it is never stored separately.

An address is an ID or name followed by positions, separated by periods.
"5.2" is whatever sits at position 2 of thing 5. "5.2.1" goes one deeper.

Where the data lives:

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
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import text as text_parts

REPO = Path(__file__).resolve().parent.parent
SCHEMA = 2  # raise this when the tables below change; the database rebuilds


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
        self._batch = None
        self._catch_up()

    # --- keeping the database in step with the log -----------------------

    def _create_tables(self):
        self.db.executescript(
            f"""
            DROP TABLE IF EXISTS things;
            DROP TABLE IF EXISTS names;
            DROP TABLE IF EXISTS cells;
            DROP TABLE IF EXISTS meta;
            CREATE TABLE things (
                id     INTEGER PRIMARY KEY,
                time   TEXT NOT NULL,
                kind   TEXT NOT NULL,
                sha256 TEXT UNIQUE,
                size   INTEGER NOT NULL,
                text   TEXT,
                source TEXT
            );
            CREATE TABLE names (
                name TEXT PRIMARY KEY,
                id   INTEGER NOT NULL,
                time TEXT NOT NULL
            );
            -- One row per cell of every thing's table.
            CREATE TABLE cells (
                thing    INTEGER NOT NULL,
                position INTEGER NOT NULL,
                item     INTEGER NOT NULL,
                PRIMARY KEY (thing, position)
            );
            CREATE INDEX cells_by_item ON cells (item);
            CREATE TABLE meta (key TEXT PRIMARY KEY, value INTEGER);
            INSERT INTO meta VALUES ('log_offset', 0);
            INSERT INTO meta VALUES ('schema', {SCHEMA});
            """
        )

    def _meta(self, key: str) -> int | None:
        try:
            row = self.db.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        return row[0] if row else None

    def _set_offset(self, offset: int):
        self.db.execute(
            "UPDATE meta SET value = ? WHERE key = 'log_offset'", (offset,)
        )

    def _catch_up(self):
        """Apply any log lines the database has not seen yet."""
        offset = self._meta("log_offset")
        stale = self._meta("schema") != SCHEMA
        if stale or offset is None or offset > self.log_path.stat().st_size:
            self._create_tables()
            offset = 0
        with open(self.log_path, "rb") as log:
            log.seek(offset)
            for line in log:
                if line.strip():
                    self._apply(json.loads(line))
            offset = log.tell()
        self._set_offset(offset)
        self.db.commit()

    def _apply(self, event: dict):
        """Carry out one log event in the database."""
        if "name" in event:
            self.db.execute(
                "INSERT INTO names VALUES (?, ?, ?)",
                (event["name"], event["id"], event["time"]),
            )
        elif "into" in event:
            position = self.db.execute(
                "SELECT COALESCE(MAX(position), 0) FROM cells WHERE thing = ?",
                (event["into"],),
            ).fetchone()[0]
            self.db.executemany(
                "INSERT INTO cells VALUES (?, ?, ?)",
                [
                    (event["into"], position + n, item)
                    for n, item in enumerate(event["items"], start=1)
                ],
            )
        else:
            self.db.execute(
                "INSERT INTO things VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event["id"], event["time"], event["kind"],
                    event.get("sha256"), event.get("size", 0),
                    event.get("text"), event.get("source"),
                ),
            )

    @contextmanager
    def _writing(self):
        """Group events so they are saved together, or not at all."""
        self._batch = []
        try:
            yield
            if self._batch:
                lines = "".join(
                    json.dumps(e, ensure_ascii=False) + "\n" for e in self._batch
                ).encode("utf-8")
                with open(self.log_path, "ab") as log:
                    log.write(lines)
                    log.flush()
                    os.fsync(log.fileno())
                    self._set_offset(log.tell())
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        finally:
            self._batch = None

    def _record(self, event: dict):
        self._apply(event)
        self._batch.append(event)

    # --- ingesting --------------------------------------------------------

    def _by_content(self, sha: str) -> int | None:
        row = self.db.execute(
            "SELECT id FROM things WHERE sha256 = ?", (sha,)
        ).fetchone()
        return row["id"] if row else None

    def _mint(self, kind: str, **properties) -> int:
        """Give a new thing the next integer."""
        thing_id = self.count() + 1
        event = {"id": thing_id, "time": now(), "kind": kind}
        event.update({k: v for k, v in properties.items() if v is not None})
        self._record(event)
        return thing_id

    def _text_thing(self, text: str, source: str | None = None) -> tuple[int, bool]:
        """The thing for this exact text, creating it and its parts if new."""
        data = text.encode("utf-8")
        sha = hashlib.sha256(data).hexdigest()
        existing = self._by_content(sha)
        if existing:
            return existing, False
        thing_id = self._mint(
            "text", sha256=sha, size=len(data), text=text, source=source
        )
        items = [self._text_thing(part)[0] for part in text_parts.parts(text)]
        if items:
            self._record({"into": thing_id, "items": items, "time": now()})
        return thing_id, True

    def ingest_text(self, text: str, name: str | None = None,
                    source: str | None = None) -> tuple[int, bool]:
        """Ingest text. Returns (ID, True if it is new)."""
        if not text:
            raise ValueError("there is nothing to ingest")
        with self._writing():
            thing_id, is_new = self._text_thing(text, source)
            if name is not None:
                self._name(thing_id, name)
        return thing_id, is_new

    def ingest_bytes(self, data: bytes, kind: str, source: str | None = None,
                     name: str | None = None) -> tuple[int, bool]:
        """Ingest raw bytes of any kind. Returns (ID, True if it is new)."""
        if not data:
            raise ValueError("there is nothing to ingest")
        if kind == "text":
            return self.ingest_text(data.decode("utf-8"), name, source)
        sha = hashlib.sha256(data).hexdigest()
        with self._writing():
            thing_id, is_new = self._by_content(sha), False
            if thing_id is None:
                if name is not None:
                    self._check_name(name, None)
                self.files_dir.mkdir(parents=True, exist_ok=True)
                (self.files_dir / sha).write_bytes(data)
                thing_id = self._mint(
                    kind, sha256=sha, size=len(data), source=source
                )
                is_new = True
            if name is not None:
                self._name(thing_id, name)
        return thing_id, is_new

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

    def new_index(self, name: str | None = None) -> int:
        """Create an empty index: an anchor whose contents can change."""
        with self._writing():
            if name is not None:
                self._check_name(name, None)
            thing_id = self._mint("index")
            if name is not None:
                self._name(thing_id, name)
        return thing_id

    def put(self, item: int, into: int) -> str:
        """Put a thing into another thing's table. Returns its new address."""
        for thing_id in (item, into):
            if self.get(thing_id) is None:
                raise ValueError(f"there is no thing {thing_id}")
        with self._writing():
            self._record({"into": into, "items": [item], "time": now()})
        return f"{into}.{len(self.contents(into))}"

    # --- naming -----------------------------------------------------------

    def _check_name(self, name: str, thing_id: int | None) -> bool:
        if not name.strip() or name != name.strip():
            raise ValueError("a name cannot be empty or padded with spaces")
        if name.isdigit():
            raise ValueError("a name cannot be only digits; those are IDs")
        if "." in name:
            raise ValueError("a name cannot contain a period; periods separate addresses")
        row = self.db.execute(
            "SELECT id FROM names WHERE name = ?", (name,)
        ).fetchone()
        if row and row["id"] != thing_id:
            raise ValueError(f"the name {name!r} already names {row['id']}")
        return row is not None

    def _name(self, thing_id: int, name: str):
        if not self._check_name(name, thing_id):
            self._record({"name": name, "id": thing_id, "time": now()})

    def name(self, thing_id: int, name: str):
        """Make a name equivalent to an ID."""
        if self.get(thing_id) is None:
            raise ValueError(f"there is no thing {thing_id}")
        with self._writing():
            self._name(thing_id, name)

    # --- looking up -------------------------------------------------------

    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM things").fetchone()[0]

    def resolve(self, address: str) -> int | None:
        """Turn an address into an ID.

        The first part is an ID or a name. Each part after a period is a
        position in the table of the thing before it.
        """
        first, *positions = str(address).split(".")
        if first.isdigit():
            thing_id = int(first) if self.get(int(first)) else None
        else:
            row = self.db.execute(
                "SELECT id FROM names WHERE name = ?", (first,)
            ).fetchone()
            thing_id = row["id"] if row else None
        for position in positions:
            if thing_id is None or not position.isdigit():
                return None
            row = self.db.execute(
                "SELECT item FROM cells WHERE thing = ? AND position = ?",
                (thing_id, int(position)),
            ).fetchone()
            thing_id = row["item"] if row else None
        return thing_id

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
        if thing["sha256"] is None:
            return b""
        return (self.files_dir / thing["sha256"]).read_bytes()

    def contents(self, thing_id: int) -> list[int]:
        """A thing's table: the IDs it contains, in order."""
        return [
            r["item"] for r in self.db.execute(
                "SELECT item FROM cells WHERE thing = ? ORDER BY position",
                (thing_id,),
            )
        ]

    def instances(self, thing_id: int, limit: int | None = None) -> list[tuple[int, int]]:
        """Everywhere a thing appears, as (containing thing, position)."""
        query = "SELECT thing, position FROM cells WHERE item = ? ORDER BY thing, position"
        if limit:
            query += f" LIMIT {int(limit)}"
        return [(r["thing"], r["position"]) for r in self.db.execute(query, (thing_id,))]

    def instance_count(self, thing_id: int) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM cells WHERE item = ?", (thing_id,)
        ).fetchone()[0]

    def recent(self, limit: int = 20) -> list[dict]:
        ids = self.db.execute(
            "SELECT id FROM things ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self.get(r["id"]) for r in reversed(ids)]
