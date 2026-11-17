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
- Every thing has an ordered table of the things it contains (`cells` in
  SQLite, `into` events in the log). Where a thing appears is the same table
  read by item. Do not add a separate structure for relationships.
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
