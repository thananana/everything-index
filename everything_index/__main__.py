"""Command line for the everything index.

    python3 -m everything_index ingest "some text"
    python3 -m everything_index ingest "some text" --name idea
    python3 -m everything_index ingest --file photo.jpg
    python3 -m everything_index ingest -          (reads text you pipe in)
    python3 -m everything_index new projects      (an empty named index)
    python3 -m everything_index put idea projects (put one thing in another)
    python3 -m everything_index put idea projects --as drafts
    python3 -m everything_index show idea
    python3 -m everything_index show idea.words.1
    python3 -m everything_index show '#3'             (the number three)
    python3 -m everything_index find characters '#3'  (things with both)
    python3 -m everything_index name 12 idea
    python3 -m everything_index list

A code reads thing.property.position and is made only of IDs, such as
12.20.1. You may write a name in place of any ID, such as idea.words.1.
Positions start at 0. A number as a thing is written with #, so #3 is the
number three while 3 is the ID 3. Put quotes around anything with # in it.
"""

import argparse
import sys

from .store import Index

SHOWN = 30  # most rows printed for any one table


def preview(thing: dict, width: int = 60) -> str:
    if thing["kind"] == "text":
        line = " ".join(thing["text"].split()) or repr(thing["text"])
        return line if len(line) <= width else line[: width - 1] + "…"
    if thing["kind"] == "index":
        return "<index>"
    label = thing["source"] or "unnamed file"
    return f"<{thing['kind']}: {label}, {thing['size']} bytes>"


def labelled(index: Index, thing_id: int) -> str:
    thing = index.get(thing_id)
    names = f"  [{', '.join(thing['names'])}]" if thing["names"] else ""
    return f"{preview(thing)}{names}"


def spoken(index: Index, thing_id: int) -> str:
    """How to say a thing: its name, or else its own text in quotes."""
    thing = index.get(thing_id)
    if thing["names"]:
        return thing["names"][0]
    if thing["kind"] == "text":
        return f'"{preview(thing, 28)}"'
    return preview(thing, 28)


def find(index: Index, address: str) -> int:
    thing_id = index.resolve(address)
    if thing_id is None:
        raise ValueError(f"nothing is identified by {address!r}")
    return thing_id


def line(code: str, reading: str):
    print(f"  {code:<14} {reading}")


def show(index: Index, thing_id: int):
    thing = index.get(thing_id)
    print(f"id       {thing['id']}")
    print(f"names    {', '.join(thing['names']) or '-'}")
    print(f"kind     {thing['kind']}")
    print(f"created  {thing['time']}")
    if thing["kind"] != "index":
        print(f"size     {thing['size']} bytes")
    if thing["source"]:
        print(f"source   {thing['source']}")
    if thing["kind"] == "text":
        print()
        print(thing["text"])

    for property_id, count in index.properties(thing_id):
        print(f"\nhas {count} {spoken(index, property_id)}   (property {property_id})")
        items = index.row(thing_id, property_id)
        for position, item in enumerate(items[:SHOWN]):
            line(f"{thing_id}.{property_id}.{position}", labelled(index, item))
        if count > SHOWN:
            print(f"  … and {count - SHOWN} more")

    total = index.instance_count(thing_id)
    if total:
        print(f"\nappears in {total} place{'' if total == 1 else 's'}")
        for holder, property_id, position in index.instances(thing_id, SHOWN):
            line(
                f"{holder}.{property_id}.{position}",
                f"in {spoken(index, holder)}, under "
                f"{spoken(index, property_id)}, at {position}",
            )
        if total > SHOWN:
            print(f"  … and {total - SHOWN} more")

    n = index.as_number(thing_id)
    if n is not None:
        rows = index.counted_by(n, SHOWN + 1)
        if rows:
            print(f"\nis how many")
            for holder, property_id in rows[:SHOWN]:
                line(
                    f"{holder}.{property_id}",
                    f"{spoken(index, holder)} has {n} {spoken(index, property_id)}",
                )
            if len(rows) > SHOWN:
                print("  … and more")
        cells = index.positioned_at(n, SHOWN + 1)
        if cells:
            print(f"\nis the position of")
            for holder, property_id, item in cells[:SHOWN]:
                line(
                    f"{holder}.{property_id}.{n}",
                    f"{spoken(index, item)}, in {spoken(index, holder)}, "
                    f"under {spoken(index, property_id)}",
                )
            if len(cells) > SHOWN:
                print("  … and more")

    total = index.holder_count(thing_id)
    if total:
        print(f"\nis a property of {total} thing{'' if total == 1 else 's'}")
        for holder in index.holders(thing_id, SHOWN):
            count = len(index.row(holder, thing_id))
            line(f"{holder}.{thing_id}", f"{spoken(index, holder)} has {count}")
        if total > SHOWN:
            print(f"  … and {total - SHOWN} more")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="everything_index")
    commands = parser.add_subparsers(dest="command")

    p = commands.add_parser("ingest", help="give something an ID")
    p.add_argument("text", nargs="?", help='text, or "-" to read piped text')
    p.add_argument("--file", help="ingest a file of any kind")
    p.add_argument("--name", help="a name equivalent to the new ID")

    p = commands.add_parser("new", help="create an empty index")
    p.add_argument("name", nargs="?")

    p = commands.add_parser("put", help="put one thing into another")
    p.add_argument("item")
    p.add_argument("into")
    p.add_argument("--as", dest="as_property", default="things",
                   help="what the item is to its holder (default: things)")

    p = commands.add_parser("show", help="show one thing")
    p.add_argument("address", help="an ID, a name, or a code like cat.characters.1")

    p = commands.add_parser("find", help="things that have all the given properties")
    p.add_argument("properties", nargs="+")

    p = commands.add_parser("name", help="give a thing a name")
    p.add_argument("address")
    p.add_argument("new_name")

    p = commands.add_parser("list", help="show the latest things")
    p.add_argument("-n", type=int, default=20)

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    index = Index()
    try:
        if args.command == "ingest":
            if args.file and args.text:
                raise ValueError("give either text or --file, not both")
            if args.file:
                thing_id, is_new = index.ingest_file(args.file, args.name)
            elif args.text == "-":
                piped = sys.stdin.read().removesuffix("\n")  # drop the terminal's line break
                thing_id, is_new = index.ingest_text(piped, args.name)
            elif args.text:
                thing_id, is_new = index.ingest_text(args.text, args.name)
            else:
                raise ValueError("give some text or --file")
            print(f"{thing_id}  {'new' if is_new else 'already in the index'}")

        elif args.command == "new":
            thing_id = index.new_index(args.name)
            print(f"{thing_id}  new index")

        elif args.command == "put":
            item, into = find(index, args.item), find(index, args.into)
            known = index.resolve(args.as_property)
            index.put(item, into, known if known else args.as_property)
            property_id = index.resolve(args.as_property)
            position = len(index.row(into, property_id)) - 1
            print(
                f"{into}.{property_id}.{position}  in {spoken(index, into)}, "
                f"under {spoken(index, property_id)}, at {position}"
            )

        elif args.command == "show":
            show(index, find(index, args.address))

        elif args.command == "find":
            found = index.intersect([find(index, a) for a in args.properties])
            for thing_id in found[:SHOWN]:
                print(f"{thing_id:>6}  {labelled(index, thing_id)}")
            if len(found) > SHOWN:
                print(f"     … and {len(found) - SHOWN} more")
            print(f"{len(found)} thing{'' if len(found) == 1 else 's'}")

        elif args.command == "name":
            thing_id = find(index, args.address)
            index.name(thing_id, args.new_name)
            print(f"{args.new_name} = {thing_id}")

        elif args.command == "list":
            for thing in index.recent(args.n):
                print(f"{thing['id']:>6}  {labelled(index, thing['id'])}")
            print(f"{index.count()} things in the index")
    except (ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
