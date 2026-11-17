# Project instructions for Claude

This is the owner's personal operating system. Read README.md first for the
core data model (thing / property / index, everything gets a stable ID).

## Working rules

- Language is Python 3.13. Use only the standard library unless a dependency
  is clearly worth it; ask before adding one.
- The index lives in SQLite. Human-readable notes live as Markdown in `notes/`.
- Keep the data model primitive. Do not add special-case tables or classes
  for notes, tasks, events, etc. They are all things with properties.
- The owner is new to coding and works from a library computer or phone,
  with no machine of their own. Explain what you did in plain language.
  Commit and push whenever a meaningful step is done so nothing is lost
  when the session ends.
- Prefer small, readable files over clever ones.

## How the data is stored

- `index/log.jsonl` is the source of truth: append-only, one event per line.
  Never rewrite or reorder it. IDs are integers in order of ingestion.
- `data/index.db` is SQLite, rebuilt from the log automatically. Never commit it.
- A thing is identified by its raw bytes (SHA-256). Same bytes, same ID.
- Every thing has a table: properties, and under each property an ordered
  row of items. One cell is holder, property, position, item (`cells` in
  SQLite; `into` / `as` / `items` events in the log). A property is itself
  a thing. Where a thing appears is the same table read by item. Do not add
  a separate structure for relationships.
- Codes read thing.property.position and are pure IDs, e.g. `12.13.2`.
  Names may replace any ID when a person types one. Positions start at 0.
  Display codes as IDs with a plain-language reading beside them.
- Numbers are things (the text of the numeral), written `#3`; a bare `3` is
  an ID. IDs and numbers are deliberately unrelated. Every index starts
  with the `digits` index and digits 0-9 at their own positions. Other
  numbers are digits in places, left to right. Any number the system uses
  as a position or count is minted. Counts and positions are read from
  `cells`, not stored again.
- Principle: everything is a property, and anything the system uses to
  express a thing must itself be a thing. Do not add hidden machinery.
- Text is split into parts once, at ingestion (`everything_index/text.py`),
  and the result is logged. Never re-split existing things.
- If the SQLite tables change, raise `SCHEMA` in `store.py` so it rebuilds.
- The repository is public unless the owner has changed it. Check before
  committing ingested personal content, and warn the owner if it is public.
- Design notes are in `notes/things.md`, the plan in `notes/roadmap.md`.
  Write notes as distilled design, not as transcripts of the owner's words.

## Commands

- Run: `python3 -m everything_index` (from the repository root)
- Test: `python3 -m unittest`
