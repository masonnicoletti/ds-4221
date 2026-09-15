"""Lab 4, Part 3 — measure what a plan's SHAPE costs. Run:  python3 measure_pipeline.py

Same query, two plan shapes, and a counter on every edge of the tree:

    Query: names of ds students with gpa > 35, from students x majors.

    Plan A (filter LATE):  Project <- Select(join AND gpa AND dept) <- Product
    Plan B (filter EARLY): Project <- Select(join) <- Product(Select(gpa) x Select(dept))

The CountingScan wrapper counts rows flowing through each edge. Record
both tables for class. All numbers are deterministic.
"""

import shutil
import tempfile

from file_manager import FileManager
from buffer_manager import BufferManager
from record_manager import Schema, Layout, TableScan
from query_engine import Predicate, F, SelectScan, ProjectScan, ProductScan, CountingScan

BLOCK_SIZE = 4096
N_STUDENTS = 300                  # 100 per major
N_MAJORS = 3
DEPTS = ["ds", "stat", "econ"]


def build(d):
    fm = FileManager(d, BLOCK_SIZE)
    bm = BufferManager(fm, 8)
    s_lay = Layout(Schema().add_int_field("sid").add_string_field("name", 8)
                           .add_int_field("gpa").add_int_field("mid"))
    ts = TableScan(bm, fm, "students", s_lay)
    for i in range(N_STUDENTS):
        ts.insert()
        ts.set_int("sid", i); ts.set_string("name", f"s{i}")
        ts.set_int("gpa", 20 + i % 20); ts.set_int("mid", 1 + i % N_MAJORS)
    ts.close()
    m_lay = Layout(Schema().add_int_field("mid2").add_string_field("dept", 8))
    ts = TableScan(bm, fm, "majors", m_lay)
    for mid, dept in enumerate(DEPTS, start=1):
        ts.insert()
        ts.set_int("mid2", mid); ts.set_string("dept", dept)
    ts.close()
    return fm, bm, s_lay, m_lay


def run(plan):
    plan.before_first()
    n = 0
    while plan.next():
        n += 1
    return n


def main():
    d = tempfile.mkdtemp(prefix="microdb-plan-")
    try:
        fm, bm, s_lay, m_lay = build(d)

        # ---- Plan A: product first, one big filter after ----
        pairs_a = CountingScan(
            ProductScan(TableScan(bm, fm, "students", s_lay),
                        TableScan(bm, fm, "majors", m_lay)))
        plan_a = ProjectScan(
            SelectScan(pairs_a, Predicate(("mid", "=", F("mid2")),
                                          ("gpa", ">", 35), ("dept", "=", "ds"))),
            ["name"])
        out_a = run(plan_a)
        plan_a.close()

        # ---- Plan B: filter each input before the product ----
        kept_s = CountingScan(
            SelectScan(TableScan(bm, fm, "students", s_lay),
                       Predicate(("gpa", ">", 35))))
        kept_m = CountingScan(
            SelectScan(TableScan(bm, fm, "majors", m_lay),
                       Predicate(("dept", "=", "ds"))))
        pairs_b = CountingScan(ProductScan(kept_s, kept_m))
        plan_b = ProjectScan(
            SelectScan(pairs_b, Predicate(("mid", "=", F("mid2")))),
            ["name"])
        out_b = run(plan_b)
        plan_b.close()

        print("same query, same answer, two shapes "
              f"({N_STUDENTS} students x {N_MAJORS} majors):\n")
        print(f"  Plan A (filter late):  pairs built: {pairs_a.rows:>6,}   rows out: {out_a}")
        print(f"  Plan B (filter early): pairs built: {pairs_b.rows:>6,}   rows out: {out_b}")
        print(f"                         students filter: kept {kept_s.rows} of {N_STUDENTS}, read once")
        print(f"                         majors filter: kept 1, but {kept_m.rows} rows flowed through it,")
        print(f"                         because the nested loop RE-RUNS its right input per left row")
        ratio = pairs_a.rows / max(pairs_b.rows, 1)
        print(f"\n  pair-building work ratio, A / B: {ratio:,.0f}x")
        fm.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("\nRecord both tables, then think about these for class:")
    print("  1. Where did Plan B's advantage come from, mechanically?")
    print("  2. The majors filter kept 1 row yet 60 flowed through it. Explain.")
    print("  3. Plans A and B return identical rows. Who should pick between")
    print("     them — the person writing SQL, or the machine? Why?")


if __name__ == "__main__":
    main()
