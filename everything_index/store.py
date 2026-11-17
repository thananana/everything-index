"""The master index.

Every thing gets the next integer, in order of ingestion. That integer is
its ID and never changes.

There are two ways a thing comes to exist:

- By content. Text or a file is ingested. It is identified by its raw
  bytes, so the same content always returns the same ID.
- By naming. An empty index is created as an anchor. Its ID and name stay
  fixed while what it contains is free to change.

Every thing has a table. Each row of the table is one property, and a
property is itself a thing, such as the index named "characters". Under a
property sit the items, in order. So the word "cat" has the property
"characters", and under it c, a, t at positions 0, 1, 2.

Where a thing appears in other tables is the same information read the
other way round, so it is never stored separately.

A code is read left to right, separated by periods: a thing, then a
property, then a position, and so on. Things and properties are written as
their IDs, so a code is nothing but integers, for example 12.20.1. For
people, a name may stand in for any ID: cat.characters.1 is the letter a.

Digits come first. The very first things in the master index are the index
named "digits" and the ten digits 0 to 9. Each digit sits at its own
position in that index: 0 at position 0, up to 9 at position 9. That is
the list that indexes itself, and it is why positions everywhere start
at 0.

Every other number is digits in places, read left to right as in text.
305 has the characters 3, 0, 5 at places 0, 1, 2. The same ten digits are
reused at every place, and zero holds a place like any other digit.

A number is written #305 so it is not confused with the ID 305. IDs only
record order of ingestion and have nothing to do with numbers. Whenever
the system uses a number, as a position or as a count, that number is made
a thing if it is not one already.

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
SCHEMA = 3  # raise this when the tables below change; the database rebuilds


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
        self._counted = None  # highest n with 0..n all things; found when needed
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
                property INTEGER NOT NULL,
                position INTEGER NOT NULL,
                item     INTEGER NOT NULL,
                PRIMARY KEY (thing, property, position)
            );
            CREATE INDEX cells_by_item ON cells (item);
            CREATE INDEX cells_by_property ON cells (property, thing);
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
            taken = self.db.execute(
                "SELECT COUNT(*) FROM cells WHERE thing = ? AND property = ?",
                (event["into"], event["as"]),
            ).fetchone()[0]
            self.db.executemany(
                "INSERT INTO cells VALUES (?, ?, ?, ?)",
                [
                    (event["into"], event["as"], taken + n, item)
                    for n, item in enumerate(event["items"])
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
            if self.count() == 0:
                self._seed_digits()
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
            self._counted = None
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

    def _property(self, name: str) -> int:
        """The index with this name, created the first time it is needed."""
        row = self.db.execute(
            "SELECT id FROM names WHERE name = ?", (name,)
        ).fetchone()
        if row:
            return row["id"]
        self._check_name(name, None)
        thing_id = self._mint("index")
        self._name(thing_id, name)
        return thing_id

    def _into(self, thing_id: int, property_id: int, items: list[int]):
        """Add items to a thing under a property, in order."""
        self._record({
            "into": thing_id, "as": property_id, "items": items, "time": now(),
        })
        # The row now uses the positions 0..n-1 and has the count n, so
        # each of those numbers has been expressed and must be a thing.
        self._count_to(self._length(thing_id, property_id))

    def _length(self, thing_id: int, property_id: int) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM cells WHERE thing = ? AND property = ?",
            (thing_id, property_id),
        ).fetchone()[0]

    def _seed_digits(self):
        """Start an empty index with the digits, each at its own position."""
        digits = self._mint("index")
        self._name(digits, "digits")
        items = []
        for digit in "0123456789":
            data = digit.encode("utf-8")
            items.append(self._mint(
                "text", sha256=hashlib.sha256(data).hexdigest(),
                size=len(data), text=digit,
            ))
        self._record({
            "into": digits, "as": digits, "items": items, "time": now(),
        })

    def _count_to(self, n: int):
        """Make sure every number from 0 to n is a thing."""
        if self._counted is None:
            k = 0
            while self.number(k) is not None:
                k += 1
            self._counted = k - 1
        while self._counted < n:
            self._counted += 1  # raise first: making "12" uses places 0 and 1
            self._text_thing(str(self._counted))

    def number(self, n: int) -> int | None:
        """The thing that is the number n, if it exists yet."""
        sha = hashlib.sha256(str(int(n)).encode("utf-8")).hexdigest()
        return self._by_content(sha)

    def as_number(self, thing_id: int) -> int | None:
        """The number a thing is, or None if it is not a number."""
        thing = self.get(thing_id)
        text = thing["text"] if thing and thing["kind"] == "text" else None
        if text and text.isascii() and text.isdigit() and str(int(text)) == text:
            return int(text)
        return None

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
        kind_of_part, parts = text_parts.parts(text)
        if parts:
            property_id = self._property(kind_of_part)
            items = [self._text_thing(part)[0] for part in parts]
            self._into(thing_id, property_id, items)
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

    def put(self, item: int, into: int, as_property: int | str = "things") -> str:
        """Put a thing into another thing, under a property.

        The property says what the item is to the thing that holds it. It
        can be an ID, or a name, which is created if it does not exist yet.
        Returns the item's new address.
        """
        for thing_id in (item, into):
            if self.get(thing_id) is None:
                raise ValueError(f"there is no thing {thing_id}")
        with self._writing():
            if isinstance(as_property, str):
                as_property = self._property(as_property)
            elif self.get(as_property) is None:
                raise ValueError(f"there is no thing {as_property}")
            self._into(into, as_property, [item])
        return f"{into}.{as_property}.{len(self.row(into, as_property)) - 1}"

    # --- naming -----------------------------------------------------------

    def _check_name(self, name: str, thing_id: int | None) -> bool:
        if not name.strip() or name != name.strip():
            raise ValueError("a name cannot be empty or padded with spaces")
        if name.isdigit():
            raise ValueError("a name cannot be only digits; those are IDs")
        if "." in name:
            raise ValueError("a name cannot contain a period; periods separate addresses")
        if name.startswith("#"):
            raise ValueError("a name cannot start with #; that marks a number")
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

    def _id_or_name(self, word: str) -> int | None:
        if word.startswith("#"):
            return self.number(word[1:]) if word[1:].isdigit() else None
        if word.isdigit():
            return int(word) if self.get(int(word)) else None
        row = self.db.execute(
            "SELECT id FROM names WHERE name = ?", (word,)
        ).fetchone()
        return row["id"] if row else None

    def resolve(self, address: str) -> int | None:
        """Turn a code, or the same thing written with names, into an ID.

        The first part is a thing, as an ID or a name. After that the parts
        come in pairs: a property, then a position under that property.
        """
        first, *steps = str(address).split(".")
        thing_id = self._id_or_name(first)
        if len(steps) % 2:
            return None  # stops on a property, with no position after it
        for property_word, position in zip(steps[::2], steps[1::2]):
            property_id = self._id_or_name(property_word)
            if thing_id is None or property_id is None or not position.isdigit():
                return None
            row = self.db.execute(
                "SELECT item FROM cells"
                " WHERE thing = ? AND property = ? AND position = ?",
                (thing_id, property_id, int(position)),
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

    def properties(self, thing_id: int) -> list[tuple[int, int]]:
        """A thing's properties, as (property, how many items under it)."""
        return [
            (r["property"], r["n"]) for r in self.db.execute(
                "SELECT property, COUNT(*) AS n FROM cells WHERE thing = ?"
                " GROUP BY property ORDER BY MIN(rowid)",
                (thing_id,),
            )
        ]

    def row(self, thing_id: int, property_id: int | str) -> list[int]:
        """The items a thing holds under one property, in order."""
        if isinstance(property_id, str):
            property_id = self._id_or_name(property_id)
        return [
            r["item"] for r in self.db.execute(
                "SELECT item FROM cells WHERE thing = ? AND property = ?"
                " ORDER BY position",
                (thing_id, property_id),
            )
        ]

    def instances(self, thing_id: int, limit: int | None = None) -> list[tuple[int, int, int]]:
        """Everywhere a thing appears, as (holder, property, position)."""
        query = (
            "SELECT thing, property, position FROM cells WHERE item = ?"
            " ORDER BY thing, property, position"
        )
        if limit:
            query += f" LIMIT {int(limit)}"
        return [
            (r["thing"], r["property"], r["position"])
            for r in self.db.execute(query, (thing_id,))
        ]

    def instance_count(self, thing_id: int) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM cells WHERE item = ?", (thing_id,)
        ).fetchone()[0]

    def holders(self, property_id: int, limit: int | None = None) -> list[int]:
        """The things that have this thing as a property."""
        query = "SELECT DISTINCT thing FROM cells WHERE property = ? ORDER BY thing"
        if limit:
            query += f" LIMIT {int(limit)}"
        return [r["thing"] for r in self.db.execute(query, (property_id,))]

    def holder_count(self, property_id: int) -> int:
        return self.db.execute(
            "SELECT COUNT(DISTINCT thing) FROM cells WHERE property = ?",
            (property_id,),
        ).fetchone()[0]

    # --- numbers read backwards -------------------------------------------

    def counted_by(self, n: int, limit: int | None = None) -> list[tuple[int, int]]:
        """Every (thing, property) that has exactly n items."""
        query = (
            "SELECT thing, property FROM cells GROUP BY thing, property"
            " HAVING COUNT(*) = ? ORDER BY thing, property"
        )
        if limit:
            query += f" LIMIT {int(limit)}"
        return [(r["thing"], r["property"]) for r in self.db.execute(query, (n,))]

    def positioned_at(self, n: int, limit: int | None = None) -> list[tuple[int, int, int]]:
        """Every (thing, property, item) where the item sits at position n."""
        query = (
            "SELECT thing, property, item FROM cells WHERE position = ?"
            " ORDER BY thing, property"
        )
        if limit:
            query += f" LIMIT {int(limit)}"
        return [
            (r["thing"], r["property"], r["item"])
            for r in self.db.execute(query, (n,))
        ]

    # --- intersection -----------------------------------------------------

    def having(self, property_id: int) -> set[int]:
        """Every thing that has this thing as a property.

        A thing has a property when the property labels one of its rows,
        sits in one of its rows, or is the number of items in one of its rows.
        """
        found = {
            r[0] for r in self.db.execute(
                "SELECT thing FROM cells WHERE property = ?1 OR item = ?1",
                (property_id,),
            )
        }
        n = self.as_number(property_id)
        if n is not None:
            found.update(thing for thing, _ in self.counted_by(n))
        return found

    def intersect(self, property_ids: list[int]) -> list[int]:
        """The things that have every one of these properties."""
        sets = [self.having(p) for p in property_ids]
        return sorted(set.intersection(*sets)) if sets else []

    def recent(self, limit: int = 20) -> list[dict]:
        ids = self.db.execute(
            "SELECT id FROM things ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self.get(r["id"]) for r in reversed(ids)]
