"""microdb — an interactive SQL terminal, provided complete for Lab 5.

    python3 microdb.py --demo   # start with the lab's students and majors
    python3 microdb.py          # create/query your own persistent tables

Type one SQL statement per line; a final semicolon is optional.
Use .help for examples, .tables to list tables, and .schema to see columns.
Demo data is temporary. Normal sessions save data in ./mydb between runs.
"""

import argparse
from contextlib import contextmanager
from pathlib import Path

try:
    import readline  # Enable line editing and session history where available.
except ImportError:
    readline = None

from file_manager import FileManager
from buffer_manager import BufferManager
from catalog import Catalog
from record_manager import TableScan
from sql_frontend import Database, ParseError

DB_DIR = "mydb"
BLOCK_SIZE = 4096
POOL_FRAMES = 8

HELP = """Type one SQL statement and press Enter. A final ; is optional.

  .tables          List the tables in this database
  .schema          Show all table names, columns, and types
  .schema students Show the columns of one table
  .help            Show these instructions
  exit             Leave the prompt (quit and .quit also work)

Normal mode saves changes in ./mydb; --demo discards them on exit.

Try these queries in --demo mode:
  SELECT * FROM majors;
  SELECT name, gpa FROM students WHERE gpa > 35;
  SELECT name, dept FROM students, majors WHERE mid = mid2 AND dept = 'ds';

Create your own data in either mode:
  CREATE TABLE readings (rid INT, label VARCHAR(12), value INT);
  INSERT INTO readings VALUES (1, 'north', 12);
  SELECT label FROM readings WHERE value > 10;

SQL supports SELECT, CREATE TABLE, INSERT, and AND with =, <, >.
Use single quotes for string values. Aliases, qualified names, OR,
ORDER BY, aggregates, UPDATE, and DELETE are outside this lab's grammar.
Use measure_sql.py for the lab's repeated performance measurements.
"""


def print_rows(rows: list[dict]) -> None:
    if not rows:
        print("(0 rows)")
        return
    fields = list(rows[0])
    widths = {f: max(len(f), *(len(str(r[f])) for r in rows)) for f in fields}
    print("  ".join(f.ljust(widths[f]) for f in fields))
    print("  ".join("-" * widths[f] for f in fields))
    for r in rows:
        print("  ".join(str(r[f]).ljust(widths[f]) for f in fields))
    print(f"({len(rows)} {'row' if len(rows) == 1 else 'rows'})")


def table_names(db) -> list[str]:
    scan = TableScan(db.bm, db.fm, "table_catalog", db.catalog.tcat_layout)
    try:
        names = []
        while scan.next():
            names.append(scan.get_string("tblname"))
        return sorted(names)
    finally:
        scan.close()


def show_schema(db, table: str = "") -> None:
    names = [table] if table else table_names(db)
    if not names:
        print("No tables yet. Type .help for a CREATE TABLE example.")
    for name in names:
        schema = db.catalog.get_layout(name).schema
        columns = []
        for field in schema.fields():
            kind = schema.type_of(field).upper()
            if kind == "VARCHAR":
                kind += f"({schema.length_of(field)})"
            columns.append(f"{field} {kind}")
        print(f"{name} ({', '.join(columns)})")


@contextmanager
def persistent_database():
    fm = FileManager(DB_DIR, BLOCK_SIZE)
    bm = BufferManager(fm, POOL_FRAMES)
    try:
        yield Database(fm, bm, Catalog(bm, fm))
    finally:
        try:
            bm.flush_all()
        finally:
            fm.close()


def run_prompt(db) -> None:
    print("Type SQL and press Enter. One statement per line; final ; optional.")
    print("Commands: .help  .tables  .schema  exit")
    if readline is not None:
        print("Use the Up/Down arrows to recall and edit this session's statements.")
    while True:
        try:
            sql = input("microdb> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not sql:
            continue
        command = sql.rstrip(";").strip().lower()
        if not command:
            continue
        if command in ("exit", "quit", ".quit", ".exit"):
            break
        try:
            if command in ("help", ".help"):
                print(HELP)
                continue
            if command == ".tables":
                names = table_names(db)
                if names:
                    print_rows([{"table": name} for name in names])
                else:
                    print("No tables yet. Type .help for a CREATE TABLE example.")
                continue
            parts = command.split()
            if parts[0] == ".schema" and len(parts) <= 2:
                show_schema(db, parts[1] if len(parts) == 2 else "")
                continue
            if command.startswith("."):
                print("Unknown command. Type .help for available commands.")
                continue
            result = db.execute(sql)
            print_rows(result) if isinstance(result, list) else print(result)
        except ParseError as e:
            print(f"query error: {e}")
        except KeyError as e:
            print(f"query error: {e.args[0]}")
        except Exception as e:
            print(f"error: {type(e).__name__}: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true",
                        help="use a temporary database with 300 students and three majors")
    args = parser.parse_args()
    if args.demo:
        from measure_sql import school
        print("microdb — Lab 5 demo: 300 students and 3 majors")
        print("This is the measurement fixture. Changes last only for this session.")
        with school() as db:
            show_schema(db)
            print("Try: SELECT * FROM majors;")
            run_prompt(db)
        print("bye — demo data removed")
    else:
        print(f"microdb — persistent database: {Path(DB_DIR).resolve()}")
        print("For ready-to-query lab data, start with: python3 microdb.py --demo")
        with persistent_database() as db:
            run_prompt(db)
        print("bye — changes saved in ./mydb")


if __name__ == "__main__":
    main()
