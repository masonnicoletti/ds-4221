"""Lab 3, Part 3 — measure what layout costs. Run:  python3 measure_layout.py

Three schemas, one question: how many rows fit in a block, and what does
that do to a 10,000-row table? Then a real insert of 10,000 rows to prove
the arithmetic against the actual file — plus the scan hit rate through an
8-frame pool, which should look familiar from last week.

All numbers are deterministic: note them for class.
"""

import shutil
import tempfile

from file_manager import FileManager
from buffer_manager import BufferManager
from record_manager import Schema, Layout, TableScan

BLOCK_SIZE = 4096
N_ROWS = 10_000

SCHEMAS = {
    "students(id int, name vc(8), gpa int)":
        Schema().add_int_field("id").add_string_field("name", 8).add_int_field("gpa"),
    "wide   (id int, bio vc(200))":
        Schema().add_int_field("id").add_string_field("bio", 200),
    "skinny (id int, x int)":
        Schema().add_int_field("id").add_int_field("x"),
}


def arithmetic():
    print(f"{'schema':<38} | {'slot':>5} | {'rows/blk':>8} | {'waste/blk':>9} | {'blocks for 10k':>14}")
    print("-" * 88)
    for name, schema in SCHEMAS.items():
        lay = Layout(schema)
        per = BLOCK_SIZE // lay.slot_size
        waste = BLOCK_SIZE - per * lay.slot_size
        blocks = -(-N_ROWS // per)                     # ceil
        print(f"{name:<38} | {lay.slot_size:>5} | {per:>8} | {waste:>7} B | {blocks:>14}")


def prove_it():
    d = tempfile.mkdtemp(prefix="microdb-layout-")
    try:
        fm = FileManager(d, BLOCK_SIZE)
        bm = BufferManager(fm, 8)
        lay = Layout(SCHEMAS["students(id int, name vc(8), gpa int)"])
        ts = TableScan(bm, fm, "students", lay)
        for i in range(N_ROWS):
            ts.insert()
            ts.set_int("id", i)
            ts.set_string("name", f"s{i % 97}")
            ts.set_int("gpa", 20 + i % 20)
        ts.close()
        blocks = fm.length("students.tbl")
        print(f"\nactual file after inserting {N_ROWS:,} students rows: {blocks} blocks "
              f"({blocks * BLOCK_SIZE / 1024:.0f} KB)")
        bm.hits = bm.misses = 0
        ts = TableScan(bm, fm, "students", lay)
        n = 0
        ts.before_first()
        while ts.next():
            n += 1
        ts.close()
        print(f"full scan read back {n:,} rows through an 8-frame pool: "
              f"hit rate {bm.hit_rate():.1%} (remember the cliff?)")
        fm.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    arithmetic()
    prove_it()
    print("\nRecord the table and both numbers, then think about these for class:")
    print("  1. Where do the wasted bytes in the wide schema go, exactly?")
    print("  2. ada's name uses 3 of its 8 reserved chars. What % of her slot is air?")
    print("  3. Why is the scan's hit rate ~0% even though the pool held 8 blocks?")
