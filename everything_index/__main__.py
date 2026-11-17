"""Command line for the everything index.

    python3 -m everything_index ingest "some text"
    python3 -m everything_index ingest "some text" --name idea
    python3 -m everything_index ingest --file photo.jpg
    python3 -m everything_index ingest -          (reads text you pipe in)
    python3 -m everything_index new projects      (an empty named index)
    python3 -m everything_index put idea projects (put one thing in another)
    python3 -m everything_index show 1            (or: show idea, show 1.2)
    python3 -m everything_index name 1 idea
    python3 -m everything_index list

Anywhere a thing is asked for you can give an ID, a name, or an address
such as 5.2, meaning whatever is at position 2 of thing 5.
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


def find(index: Index, address: str) -> int:
    thing_id = index.resolve(address)
    if thing_id is None:
        raise ValueError(f"nothing is identified by {address!r}")
    return thing_id


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

    contents = index.contents(thing_id)
    if contents:
        print(f"\ncontains {len(contents)}")
        for position, item in enumerate(contents[:SHOWN], start=1):
            address = f"{thing_id}.{position}"
            print(f"  {address:<10} {item:>6}  {labelled(index, item)}")
        if len(contents) > SHOWN:
            print(f"  … and {len(contents) - SHOWN} more")

    total = index.instance_count(thing_id)
    if total:
        print(f"\nappears in {total} place{'' if total == 1 else 's'}")
        for container, position in index.instances(thing_id, SHOWN):
            address = f"{container}.{position}"
            print(f"  {address:<10} in  {labelled(index, container)}")
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

    p = commands.add_parser("show", help="show one thing")
    p.add_argument("address", help="an ID, a name, or an address like 5.2")

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
            address = index.put(find(index, args.item), find(index, args.into))
            print(f"now at {address}")

        elif args.command == "show":
            show(index, find(index, args.address))

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
