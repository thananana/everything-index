# everything-index

A personal operating system: one central index that connects notes, plans,
research, to-dos, events, goals, knowledge, deadlines, finances, decisions,
habits, and systems. A "digital zero space" that everything branches from.

## Core idea

There is one primitive data model, used for everything:

- A **thing** is anything that can be identified.
- A **property** is a thing that describes another thing.
- An **index** is a thing that collects other things.

So everything is at once a thing, a property, and an index, and every one of
them gets a **stable, unique ID**. The first act of caring about anything,
in any environment, is to identify it and give it a new ID in the
everything index. The process selects for the smallest set of names (an ID
equal to what it identifies) needed to uniquely and stably identify
something.

The long-term goal is that position, identity, and function share a single
substrate, giving maximum expressive capacity with minimum friction. This
also serves a multimedia art system in which all things can be connected the
way they are encountered or imagined.

## Stack

- **Python 3.13** for all logic and tooling.
- **SQLite** (built into Python) for the index itself.
- **Markdown** files for human-readable notes, kept in git.
- **git / GitHub** as the permanent store. Each cloud session is temporary;
  anything worth keeping is committed and pushed.

## Layout

```
src/everything_index/   Python package (the system itself)
tests/                  tests
notes/                  Markdown notes and thinking
data/                   local databases and generated files (ignored by git)
```

## Running

```bash
python3 -m everything_index
```
