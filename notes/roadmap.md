# Roadmap

Rough order of work. Revised as the owner describes more.

1. **Core index.** Create a thing, give it an ID, attach properties, look it
   up. SQLite store. Everything else sits on this.
2. **Ingestion: throw it at the wall.** One entry point that accepts raw
   input (text, link, file) and makes a thing with an ID and its
   precomputable properties.
3. **Connectors** that pull existing things in, each recording source and
   external ID as properties:
   - Gmail
   - Google Calendar
   - Google Docs
   - Apple Notes / Reminders (export-based, since Apple has no cloud API)
   - AI conversations (exports)
   - Are.na
   - Obsidian (Markdown folder)
4. **Gathering.** Ways for things to accumulate other things around them
   and grow: links, properties, indexes.
5. **Views and tools.** Small tools on top of the index (to-dos, calendar,
   finances, habits, decisions), all reading the same things.

See notes/things.md for the founding idea.
