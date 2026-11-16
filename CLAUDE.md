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

## Commands

- Run: `python3 -m everything_index`
- Test: `python3 -m pytest` (once tests exist) or `python3 -m unittest`
