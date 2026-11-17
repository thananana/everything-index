# Things

Design notes. Distilled, not verbatim.

## Why

The owner's things are scattered across many apps. The goal is one place
where anything can be thrown in and ingested, and ingestion gives it an ID.

## The model

- **Master index.** Every identified thing gets the next integer, in order
  of ingestion. Position in the master index is the ID. It is a
  computational object and is not meant to be read by a person.
- **Names.** A thing may be named or left unnamed. A name is equivalent to
  the ID it names.
- **Every thing identifies a table.** The table lists what the thing
  contains, by position. Cells hold IDs. So an address is "name, position",
  and it resolves to another ID.
- **Properties are contents.** Anything specified about a thing becomes one
  of its properties, and a property is a thing listed in its table. Type,
  source, and time created are added automatically at ingestion.
- **Instances are the same fact read the other way.** If a thing appears in
  several tables, those appearances are its instances. A word is the index
  of everywhere it occurs. Nothing extra is stored for this.
- **Identity by sameness.** If the same content turns up twice, it is one
  thing with two instances, never two things.
- **Relationships are things.** To preserve a relationship, make it a thing
  that contains its participants. There are no triples and no edges.
- **Views.** Any property can be switched on or off in the environment
  where things are viewed.

## The math analogy

Numbers index themselves: n sits at position n. An expression such as
3 + 4 is an address: the table named "+", at the position given by 3 and 4.
Here, naming creates the tables, integers give the positions, and cells
hold integers. Identity, position, and function share one substrate.

## Language

Characters, words, sentences, paragraphs, headings, documents are things.
Only distinct ones get IDs. An occurrence is a position in a table, so it
is an address and costs nothing to identify. The dictionary is the index of
words.

## Syntax

Ingestion uses one canonical syntax. Brackets identify text. A frame
identifies whatever it contains. Exact notation still to be specified by
the owner.

## Open questions

- Is "The" the same word as "the"? Default for now: exact match only.
- Exact bracket and frame notation, and how a name is written.
- What counts as the same image or file. Default: identical bytes.
