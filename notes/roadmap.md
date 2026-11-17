# Roadmap

Each step ends with something that runs and is pushed.

0. **Privacy.** The repository is public. Before any personal content is
   ingested, make it private or move data to a separate private repository.
1. **Master index.** Ingest a piece of text, get the next integer. Optional
   name. Time created recorded automatically. Same content returns the
   same ID. Stored as an append-only log in plain text, in git.
2. **Text decomposition.** Ingested text is broken into sentences, words,
   characters. Each distinct one is a thing. Each thing's table lists its
   contents by position. Looking up a word shows all its instances.
3. **Syntax.** Parser for brackets, frames, and names.
4. **Viewing.** Show a thing, what it contains, where it appears. Switch
   properties on and off.
5. **Non-text things.** Images, files, links, with automatic properties and
   descriptions that connect through their words.
6. **Capture from the phone.** A way to throw things in without opening a
   coding session. Then connectors: Gmail, Calendar, Google Docs, exports
   from Apple Notes, Reminders, AI conversations, Are.na, Obsidian.
7. **Tools.** To-dos, deadlines, habits, finances, decisions as named
   indexes over the same things.

## Storage decision

The append-only ingestion log and the raw ingested files are the source of
truth and live in git. The SQLite database is rebuilt from them and is
never committed. Everything derivable is recomputable.
