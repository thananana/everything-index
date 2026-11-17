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

## Anchors and changing identity

If a thing is how it addresses and is addressed, its identity seems to
move whenever its surroundings do. The resolution used in the code:

- The **integer ID is the anchor.** It is a position in the master index
  and never changes.
- A thing made **by content** (text, a file) is fixed: same bytes, same ID.
- A thing made **by naming** (an empty index) has no content of its own.
  Its ID and name hold still while what it contains changes freely. This
  is the box you drag things into.
- So a name maps to exactly one ID, but what that name gathers is many
  things and is not fixed.

## Tables have rows, and a row is a property

A thing does not hold a flat list. It holds properties, and under each
property a sequence of items. The word "cat" has the property
"characters", and under it c, a, t. Saying "cat has 3" is incomplete:
it has 3 characters, and "characters" is itself a thing in the index.

- The property says what kind of thing the items are to their holder.
  At scale a thing has many kinds: characters, words, a description, a
  source, drafts, and so on.
- A property is an ordinary thing, usually an index made by naming. It is
  created the first time it is needed.
- The count under a property is read off the table, never stored.
- Read the other way, a property is the index of every thing that has it.
  "characters" lists everything that has characters.

So one cell is: holder, property, position, item. Parent and child is
holder and item. Sequence is position. Kind is property.

## Addresses

Periods separate the steps: thing, property, position, and so on.
`cat.characters.2` is the letter a. `story.sentences.2.words.1` goes two
levels down. A thing or a property can be written as an ID or a name.
Names therefore cannot contain periods.

Putting a thing into a box without saying what it is uses the general
property `things`.

## Everything is a property

Thing, property, and index are roles, not kinds. Any thing can play any of
them depending on the direction of reading. "cat" has the property
"characters" and the property 3, and those two describe each other: 3 of
what, and how many characters. A thing is located by where its properties
intersect.

Whatever the system uses to express a thing has thereby been expressed, so
it is indexed too. Nothing is invisible machinery. A thing is addressable
as soon as it is expressible, and gets an ID when it is actually expressed.

## Numbers

- IDs are integers only because integers keep the order of ingestion and
  are always unique. They have no connection to numbers as things.
- A number is a thing: the thing whose text is its numeral. It is written
  `#3` so it is not confused with the ID 3. A numeral met in ingested text
  is the same thing as the number.
- When the system uses a number, as a position or a count, the number
  becomes a thing if it is not one yet.
- Numbers index themselves: the index named `numbers` holds number n at
  position n, so `numbers.numbers.7` is `#7`.
- A number is made of digits, which are numbers: `#12` has the characters
  `#1` and `#2`. This falls out of the ordinary text rules.
- Read backwards, a number shows what it counts and what sits at it.
  Those are read off the tables, not stored.

## Intersection

`find` takes several properties and returns the things that have all of
them. A thing has a property if the property labels one of its rows, sits
in one of its rows, or is the count of one of its rows. `find characters
#3` gives every thing with three characters.

Open point: the terms are checked independently, so a box with 3 drafts
and some characters elsewhere would also match. Tighten if it matters.

## How text is broken up

A text gets one property, the largest level that gives more than one part:
paragraphs, then sentences, then words, then characters. Deeper levels are
reached by walking down, so a paragraph's words are found through its
sentences. Punctuation marks sit in the words row so the sequence stays
exact. Spaces are not kept as things. Sentence detection is simple and will misjudge
abbreviations such as "e.g."; the rules live in `everything_index/text.py`.
Parts are decided once, at ingestion, and written to the log, so changing
the rules later never disturbs existing IDs.

## Long-term shape

- Standalone: usable without Claude and without depending on other apps.
  The core is plain Python and plain files for that reason.
- A visual interface where dragging a thing into a box puts it in that
  index. The `put` operation is that gesture without the picture.

## Syntax

Ingestion uses one canonical syntax. Brackets identify text. A frame
identifies whatever it contains. Exact notation still to be specified by
the owner.

## Open questions

- Is "The" the same word as "the"? Default for now: exact match only.
- Exact bracket and frame notation, and how a name is written.
- What counts as the same image or file. Default: identical bytes.
