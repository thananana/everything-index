"""Command line for the everything index.

    python3 -m everything_index ingest "some text"
    python3 -m everything_index ingest "some text" --name idea
    python3 -m everything_index ingest --file photo.jpg
    python3 -m everything_index ingest -          (reads text you pipe in)
    python3 -m everything_index show 1            (or: show idea)
    python3 -m everything_index name 1 idea
    python3 -m everything_index list
"""

import argparse
import sys

from .store import Index


def preview(thing: dict, width: int = 60) -> str:
    if thing["kind"] == "text":
        line = " ".join(thing["text"].split())
        return line if len(line) <= width else line[: width - 1] + "…"
    label = thing["source"] or "unnamed file"
    return f"<{thing['kind']}: {label}, {thing['size']} bytes>"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="everything_index")
    commands = parser.add_subparsers(dest="command")

    p = commands.add_parser("ingest", help="give something an ID")
    p.add_argument("text", nargs="?", help='text, or "-" to read piped text')
    p.add_argument("--file", help="ingest a file of any kind")
    p.add_argument("--name", help="a name equivalent to the new ID")

    p = commands.add_parser("show", help="show one thing")
    p.add_argument("ref", help="an ID or a name")

    p = commands.add_parser("name", help="give a thing a name")
    p.add_argument("ref", help="an ID or an existing name")
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

        elif args.command == "show":
            thing_id = index.resolve(args.ref)
            if thing_id is None:
                raise ValueError(f"nothing is identified by {args.ref!r}")
            thing = index.get(thing_id)
            print(f"id       {thing['id']}")
            print(f"names    {', '.join(thing['names']) or '-'}")
            print(f"kind     {thing['kind']}")
            print(f"created  {thing['time']}")
            print(f"size     {thing['size']} bytes")
            if thing["source"]:
                print(f"source   {thing['source']}")
            if thing["kind"] == "text":
                print()
                print(thing["text"])

        elif args.command == "name":
            thing_id = index.resolve(args.ref)
            if thing_id is None:
                raise ValueError(f"nothing is identified by {args.ref!r}")
            index.name(thing_id, args.new_name)
            print(f"{args.new_name} = {thing_id}")

        elif args.command == "list":
            for thing in index.recent(args.n):
                names = f"  [{', '.join(thing['names'])}]" if thing["names"] else ""
                print(f"{thing['id']:>6}  {preview(thing)}{names}")
            print(f"{index.count()} things in the index")
    except (ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
