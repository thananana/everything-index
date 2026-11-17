"""Breaking text into its parts.

A text is split at the largest level that gives more than one part:
paragraphs, then sentences, then words and punctuation marks, then
characters. Each part is split again the same way, down to single
characters, which have no parts.
"""

import re

WORD = re.compile(r"\w+(?:['’\-]\w+)*|[^\w\s]")


def paragraphs(text: str) -> list[str]:
    return re.split(r"\n\s*\n", text)


def sentences(text: str) -> list[str]:
    # A sentence ends at . ! or ? followed by a space, or at a line break.
    return re.split(r"(?<=[.!?])\s+|\n+", text)


def words(text: str) -> list[str]:
    return WORD.findall(text)


def characters(text: str) -> list[str]:
    return list(text) if len(text) > 1 else []


def parts(text: str) -> list[str]:
    """The parts of a text, in order. Empty for a single character."""
    for split in (paragraphs, sentences, words, characters):
        found = [p.strip() if split is not characters else p for p in split(text)]
        found = [p for p in found if p]
        if found and found != [text]:
            return found
    return []
