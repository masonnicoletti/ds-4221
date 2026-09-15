"""Lab 4 test harness — run:  python3 test_scans.py

Build one function at a time:
    python3 test_scans.py --list
    python3 test_scans.py --unit Class.method
    python3 test_scans.py --unit
Unit checks supply the other functions as test fixtures. The target always
runs your code. The default command still runs the full integration suite.


Three groups, mirroring the lab page:

    SELECT  — filtering, multi-term predicates, chained selects
    PROJECT — field restriction and its fence
    PRODUCT — the nested loop, join queries, rewind, pin hygiene

Pure stdlib; no pytest. The Gradescope autograder runs this same harness.
"""

import shutil
import sys
import tempfile
import traceback

from file_manager import FileManager
from buffer_manager import BufferManager
from record_manager import Schema, Layout, TableScan
from query_engine import Predicate, F, SelectScan, ProjectScan, ProductScan

BLOCK_SIZE = 128
RESULTS = []

# The pinned toy rows, now with a major id for joining.
STUDENTS = [  # (sid, name, gpa, mid)
    (1, "ada", 39, 1), (2, "ben", 31, 2), (3, "cyd", 37, 1),
    (4, "dee", 28, 3), (5, "eli", 36, 2), (6, "fay", 34, 1),
]
MAJORS = [(1, "ds"), (2, "stat"), (3, "econ")]  # (mid, dept)


def check(group, name, fn):
    try:
        fn()
        RESULTS.append(True)
        print(f"  [PASS] {group}: {name}")
    except Exception as e:
        RESULTS.append(False)
        if isinstance(e, NotImplementedError):
            print(f"  [FAIL] {group}: {name} — not implemented yet")
        else:
            print(f"  [FAIL] {group}: {name} — {type(e).__name__}: {e}")
            if "-v" in sys.argv:
                traceback.print_exc()


def expect(cond, why):
    if not cond:
        raise AssertionError(why)


def fresh():
    """A temp database with the students and majors tables loaded."""
    d = tempfile.mkdtemp(prefix="microdb-l4-")
    fm = FileManager(d, BLOCK_SIZE)
    bm = BufferManager(fm, 8)
    s_lay = Layout(Schema().add_int_field("sid").add_string_field("name", 8)
                           .add_int_field("gpa").add_int_field("mid"))
    ts = TableScan(bm, fm, "students", s_lay)
    for sid, name, gpa, mid in STUDENTS:
        ts.insert()
        ts.set_int("sid", sid); ts.set_string("name", name)
        ts.set_int("gpa", gpa); ts.set_int("mid", mid)
    ts.close()
    m_lay = Layout(Schema().add_int_field("mid2").add_string_field("dept", 8))
    ts = TableScan(bm, fm, "majors", m_lay)
    for mid, dept in MAJORS:
        ts.insert()
        ts.set_int("mid2", mid); ts.set_string("dept", dept)
    ts.close()
    return d, fm, bm, s_lay, m_lay


def cleanup(d, fm):
    fm.close()
    shutil.rmtree(d, ignore_errors=True)


def collect(scan, fld):
    scan.before_first()
    out = []
    while scan.next():
        out.append(scan.get_val(fld))
    return out


# ---------------- SELECT group ----------------

def test_select_filters():
    d, fm, bm, s_lay, _ = fresh()
    try:
        sel = SelectScan(TableScan(bm, fm, "students", s_lay),
                         Predicate(("gpa", ">", 35)))
        expect(collect(sel, "name") == ["ada", "cyd", "eli"],
               f"gpa > 35 should keep ada, cyd, eli — got {collect(sel, 'name')}")
        sel.close()
    finally:
        cleanup(d, fm)


def test_select_equality():
    d, fm, bm, s_lay, _ = fresh()
    try:
        sel = SelectScan(TableScan(bm, fm, "students", s_lay),
                         Predicate(("name", "=", "ada")))
        expect(collect(sel, "gpa") == [39], "name = 'ada' should find exactly her gpa 39")
        sel.close()
    finally:
        cleanup(d, fm)


def test_select_multi_term():
    d, fm, bm, s_lay, _ = fresh()
    try:
        sel = SelectScan(TableScan(bm, fm, "students", s_lay),
                         Predicate(("gpa", ">", 30), ("gpa", "<", 37)))
        expect(sorted(collect(sel, "name")) == ["ben", "eli", "fay"],
               "30 < gpa < 37 should keep ben, eli, fay")
        sel.close()
    finally:
        cleanup(d, fm)


def test_select_stacks():
    d, fm, bm, s_lay, _ = fresh()
    try:
        inner = SelectScan(TableScan(bm, fm, "students", s_lay),
                           Predicate(("gpa", ">", 30)))
        outer = SelectScan(inner, Predicate(("mid", "=", 1)))
        expect(sorted(collect(outer, "name")) == ["ada", "cyd", "fay"],
               "select over select must compose like AND")
        outer.close()
    finally:
        cleanup(d, fm)


# ---------------- PROJECT group ----------------

def test_project_restricts():
    d, fm, bm, s_lay, _ = fresh()
    try:
        prj = ProjectScan(TableScan(bm, fm, "students", s_lay), ["name"])
        expect(collect(prj, "name")[:2] == ["ada", "ben"], "projection should still see name")
        prj.before_first(); prj.next()
        try:
            prj.get_val("gpa")
        except ValueError:
            prj.close(); return
        raise AssertionError("get_val('gpa') through a name-only projection must raise ValueError")
    finally:
        cleanup(d, fm)


def test_project_over_select():
    d, fm, bm, s_lay, _ = fresh()
    try:
        plan = ProjectScan(
            SelectScan(TableScan(bm, fm, "students", s_lay),
                       Predicate(("gpa", ">", 35))),
            ["name"])
        expect(collect(plan, "name") == ["ada", "cyd", "eli"],
               "the lecture-1 demo query, now real: Project(Select(Scan))")
        expect(not plan.has_field("gpa"), "has_field must respect the projection")
        plan.close()
    finally:
        cleanup(d, fm)


# ---------------- PRODUCT group ----------------

def test_product_cardinality():
    d, fm, bm, s_lay, m_lay = fresh()
    try:
        prod = ProductScan(TableScan(bm, fm, "students", s_lay),
                           TableScan(bm, fm, "majors", m_lay))
        expect(len(collect(prod, "sid")) == 18,
               "6 students x 3 majors must yield 18 pairs — check before_first/next order")
        prod.close()
    finally:
        cleanup(d, fm)


def test_product_order():
    d, fm, bm, s_lay, m_lay = fresh()
    try:
        prod = ProductScan(TableScan(bm, fm, "students", s_lay),
                           TableScan(bm, fm, "majors", m_lay))
        prod.before_first()
        pairs = []
        for _ in range(4):
            prod.next()
            pairs.append((prod.get_val("sid"), prod.get_val("mid2")))
        expect(pairs == [(1, 1), (1, 2), (1, 3), (2, 1)],
               f"nested loop order: all of right per left row — got {pairs}")
        prod.close()
    finally:
        cleanup(d, fm)


def test_join_query():
    d, fm, bm, s_lay, m_lay = fresh()
    try:
        # SELECT name, dept FROM students, majors
        #  WHERE mid = mid2 AND gpa > 35        — the course's first join
        plan = ProjectScan(
            SelectScan(
                ProductScan(TableScan(bm, fm, "students", s_lay),
                            TableScan(bm, fm, "majors", m_lay)),
                Predicate(("mid", "=", F("mid2")), ("gpa", ">", 35))),
            ["name", "dept"])
        plan.before_first()
        rows = []
        while plan.next():
            rows.append((plan.get_val("name"), plan.get_val("dept")))
        plan.close()
        expect(rows == [("ada", "ds"), ("cyd", "ds"), ("eli", "stat")],
               f"the join should match each honors student to their dept — got {rows}")
    finally:
        cleanup(d, fm)


def test_rewind_repeats():
    d, fm, bm, s_lay, m_lay = fresh()
    try:
        prod = ProductScan(TableScan(bm, fm, "students", s_lay),
                           TableScan(bm, fm, "majors", m_lay))
        first = collect(prod, "sid")
        second = collect(prod, "sid")               # collect() rewinds
        expect(first == second and len(second) == 18,
               "before_first must fully reset the product (right side too)")
        prod.close()
    finally:
        cleanup(d, fm)


def test_close_releases_pins():
    d, fm, bm, s_lay, m_lay = fresh()
    try:
        plan = ProjectScan(
            SelectScan(
                ProductScan(TableScan(bm, fm, "students", s_lay),
                            TableScan(bm, fm, "majors", m_lay)),
                Predicate(("mid", "=", F("mid2")))),
            ["name"])
        collect(plan, "name")
        plan.close()
        pinned = [b for b in bm.pool if b.is_pinned()]
        expect(not pinned, f"close() must release the whole tree — leaked: {pinned}")
    finally:
        cleanup(d, fm)


# ---------------- function-level checks ----------------
from contextlib import ExitStack
from unittest.mock import patch


class _Rows:
    """An in-memory input scan: no records, pages, or other student operators."""
    def __init__(self, rows, fields):
        self.rows, self.fields, self.i = rows, fields, -1

    def before_first(self):
        self.i = -1

    def next(self):
        self.i += 1
        return self.i < len(self.rows)

    def get_val(self, field):
        expect(0 <= self.i < len(self.rows), "read only from a positioned input scan")
        return self.rows[self.i][field]

    def has_field(self, field):
        return field in self.fields

    def close(self):
        pass


def _fixture_select_next(scan):
    while scan.scan.next():
        if scan.predicate.is_satisfied(scan.scan):
            return True
    return False


def _fixture_project_get(scan, field):
    if field not in scan.fields:
        raise ValueError("projected away")
    return scan.scan.get_val(field)


def _fixture_product_before(scan):
    scan.left.before_first()
    scan._left_ready = scan.left.next()
    scan.right.before_first()


def _fixture_product_next(scan):
    if not scan._left_ready:
        return False
    if scan.right.next():
        return True
    scan.right.before_first()
    scan._left_ready = scan.left.next()
    if not scan._left_ready:
        return False
    if scan.right.next():
        return True
    scan._left_ready = False
    return False


_UNIT_DEPENDENCIES = {
    SelectScan: {"next": _fixture_select_next},
    ProjectScan: {"get_val": _fixture_project_get,
                  "has_field": lambda scan, field: field in scan.fields},
    ProductScan: {"before_first": _fixture_product_before, "next": _fixture_product_next,
                  "get_val": lambda scan, field: (scan.left if scan.left.has_field(field)
                                                   else scan.right).get_val(field),
                  "has_field": lambda scan, field: scan.left.has_field(field) or scan.right.has_field(field)},
}


def _unit_scan(target):
    with ExitStack() as stack:
        for cls, methods in _UNIT_DEPENDENCIES.items():
            for name, implementation in methods.items():
                if f"{cls.__name__}.{name}" != target:
                    stack.enter_context(patch.object(cls, name, implementation))
        if target == "SelectScan.next":
            for values in ([2, 7, 1, 9, 3], [], [0, 1], [7, 9]):
                source = _Rows([{"n": n} for n in values], ["n"])
                scan = SelectScan(source, Predicate(("n", ">", 3)))
                for _ in range(2):
                    scan.before_first()
                    got = []
                    for _ in range(len(values) + 1):
                        if not scan.next():
                            break
                        got.append(source.get_val("n"))
                    expect(got == [n for n in values if n > 3], "select preserves matching rows in order")
                    expect(not scan.next(), "an exhausted selection remains exhausted")
        elif target.startswith("ProjectScan."):
            source = _Rows([{"name": "ada", "gpa": 39}], ["name", "gpa"])
            source.next()
            scan = ProjectScan(source, ["name"])
            if target.endswith("get_val"):
                expect(scan.get_val("name") == "ada", "forward retained field to input scan")
                for field in ("gpa", "missing"):
                    try:
                        scan.get_val(field)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError("reading a projected-away field must raise ValueError")
            else:
                expect(scan.has_field("name"), "retained field must be visible")
                expect(not scan.has_field("gpa") and not scan.has_field("missing"),
                       "removed and absent fields must not be visible")
                expect(not ProjectScan(source, []).has_field("name"), "empty projection has no fields")
        elif target.endswith("get_val") or target.endswith("has_field"):
            left = _Rows([{"a": 11, "shared": "left"}], ["a", "shared"])
            right = _Rows([{"b": 22, "shared": "right"}], ["b", "shared"])
            left.next(); right.next()
            scan = ProductScan(left, right)
            if target.endswith("get_val"):
                expect(scan.get_val("a") == 11 and scan.get_val("b") == 22,
                       "get fields from either input")
                expect(scan.get_val("shared") == "left", "left input wins duplicate field names")
            else:
                expect(all(scan.has_field(f) for f in ("a", "b", "shared")), "include fields from both inputs")
                expect(not scan.has_field("missing"), "absent field returns False")
        else:
            for left_values, right_values in [([], []), ([], [1]), ([1], []), ([1, 2], [3, 4])]:
                left = _Rows([{"a": n} for n in left_values], ["a"])
                right = _Rows([{"b": n} for n in right_values], ["b"])
                scan = ProductScan(left, right)
                for _ in range(2):
                    if target.endswith("before_first"):
                        left.i, right.i = 99, 99
                        scan._left_ready = not bool(left_values)
                        scan.before_first()
                        expect(left.i == 0 and right.i == -1, "rewind left to its first row and right before first")
                        expect(scan._left_ready == bool(left_values),
                               "set _left_ready to whether the first left row exists")
                    else:
                        # before_first and next share the documented _left_ready flag.
                        scan.before_first()
                        got = []
                        for _ in range(len(left_values) * len(right_values) + 1):
                            if not scan.next():
                                break
                            got.append((left.get_val("a"), right.get_val("b")))
                        expect(got == [(a, b) for a in left_values for b in right_values],
                               "nested loop must produce every pair, left row first; empty inputs produce none")
                        expect(not scan.next() and not scan.next(), "exhausted product stays exhausted until rewind")


UNIT_TESTS = {f"{cls.__name__}.{name}": (lambda target=f"{cls.__name__}.{name}": _unit_scan(target))
              for cls, methods in _UNIT_DEPENDENCIES.items() for name in methods}


def run_integration():
    RESULTS.clear()
    print("SELECT group")
    check("SELECT", "predicate filters rows (gpa > 35)",       test_select_filters)
    check("SELECT", "equality on a string field",              test_select_equality)
    check("SELECT", "multi-term predicate is an AND",          test_select_multi_term)
    check("SELECT", "selects stack like AND",                  test_select_stacks)
    print("PROJECT group")
    check("PROJECT", "restricts fields, fences the rest",      test_project_restricts)
    check("PROJECT", "the lecture-1 query: Project(Select(Scan))", test_project_over_select)
    print("PRODUCT group")
    check("PRODUCT", "cardinality is |left| x |right|",        test_product_cardinality)
    check("PRODUCT", "nested-loop order (right spins fastest)", test_product_order)
    check("PRODUCT", "a real join: product + join predicate",  test_join_query)
    check("PRODUCT", "before_first rewinds the whole tree",    test_rewind_repeats)
    check("PRODUCT", "close releases every pin",               test_close_releases_pins)
    n = sum(RESULTS)
    print(f"\n{n}/{len(RESULTS)} tests passed")
    sys.exit(0 if n == len(RESULTS) else 1)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true", help="list function-level test targets")
    mode.add_argument("--unit", nargs="?", const="all", choices=["all", *UNIT_TESTS],
                      metavar="TARGET", help="test one function, or all functions if omitted")
    parser.add_argument("-v", action="store_true", help="show tracebacks for failures")
    args = parser.parse_args()
    if args.list:
        print("\n".join(UNIT_TESTS))
        return
    if args.unit is not None:
        RESULTS.clear()
        print("UNIT checks use test fixtures for unfinished dependencies.")
        print("Run without --unit to check the complete implementation together.")
        names = UNIT_TESTS if args.unit == "all" else [args.unit]
        for name in names:
            check("UNIT", name, UNIT_TESTS[name])
        n = sum(RESULTS)
        print(f"\n{n}/{len(RESULTS)} function checks passed")
        sys.exit(0 if n == len(RESULTS) else 1)
    run_integration()


if __name__ == "__main__":
    main()
