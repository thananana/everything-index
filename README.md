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
everything_index/   Python package (the system itself)
index/log.jsonl     the master index: an append-only log, the source of truth
index/files/        raw bytes of ingested things that are not text
tests/              tests
notes/              design notes and roadmap
data/               SQLite database rebuilt from the log (ignored by git)
```

## Using it

Run these from the top folder of the repository.

```bash
python3 -m everything_index ingest "some text"
python3 -m everything_index ingest "some text" --name idea
python3 -m everything_index ingest --file photo.jpg
python3 -m everything_index new projects
python3 -m everything_index put idea projects
python3 -m everything_index put idea projects --as drafts
python3 -m everything_index show 1
python3 -m everything_index show idea
python3 -m everything_index show idea.words.2
python3 -m everything_index name 1 idea
python3 -m everything_index list
```

Ingesting prints the ID. The same content always gives the same ID.

Ingested text is broken into sentences, words, and characters. Each distinct
one is a thing, and `show` lists what a thing contains and everywhere it
appears. `new` makes an empty named index and `put` places a thing in it,
under a property you can choose with `--as`.

An address reads thing, property, position. `cat.characters.2` is the
second character of the thing named `cat`.

Numbers are things. Write `#3` for the number three, since a bare `3` is
the ID of the third thing ingested. Quote it on the command line.

```bash
python3 -m everything_index show '#3'
python3 -m everything_index find characters '#3'
```

`find` returns the things that have every property you list.

## Tests

```bash
python3 -m unittest
```
