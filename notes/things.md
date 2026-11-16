# Things

Design notes. Distilled, not verbatim.

## Why

The owner's things are scattered across many apps. The goal is one place
where anything can be thrown in and ingested, and ingestion gives it an ID.

## What a thing is

- A thing is whatever is worth recognizing and naming at all.
- Things gather other things around them and grow, like planets.
- A thing's properties are themselves things.
- Many properties are precomputable from the raw material at ingestion.

## Language is a precomputable property

Every character, word, sentence, paragraph, heading, and document is a
thing. A word is an index of all its instances. Each instance is the context
in which the word appears, and that context is both semantic (its meaning
there) and computational (its position in a document, its neighbors).

Technically this is an inverted index with positions, which is well
understood. The design twist is that the entries are first-class things with
stable IDs rather than internal bookkeeping.

## Implication for IDs

If every character and word occurrence is a thing, the index cannot store a
row for each one up front. Derived things should have deterministic IDs
(computable from the parent thing and the position) so they are identified
without being stored until something attaches to them. This is how position
and identity share a substrate.

## Open questions

- Smallest act of ingestion: pasted text, link, photo, forwarded email?
- Which properties compute at ingestion versus later, on demand?
