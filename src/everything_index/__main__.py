"""Entry point. Run with: python3 -m everything_index"""

import sqlite3
import sys


def main() -> int:
    print("everything-index")
    print(f"python {sys.version.split()[0]}, sqlite {sqlite3.sqlite_version}")
    print("nothing is indexed yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
