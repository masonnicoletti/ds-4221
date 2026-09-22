"""Lab 5 test harness — run:  python3 test_sql.py

Inspect one supplied function at a time:
    python3 test_sql.py --list
    python3 test_sql.py --unit Class.method
    python3 test_sql.py --unit
Unit checks supply the other functions as test fixtures. The target always
runs the supplied implementation. The default command still runs the full integration suite.


Three groups, mirroring the lab page:

    PARSE — SQL text becomes the right QueryData (and bad SQL dies well)
    PLAN  — QueryData becomes the right scan tree
    SQL   — end to end: CREATE, INSERT, SELECT through Database.execute

Pure stdlib; no pytest. These are setup and regression checks, not the Lab 5 grade.
"""

import shutil
import sys
import tempfile
import traceback

from file_manager import FileManager
from buffer_manager import BufferManager
from catalog import Catalog
from query_engine import F
from sql_frontend import Parser, ParseError, Database, QueryData

BLOCK_SIZE = 512
RESULTS = []


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


def fresh_db():
    d = tempfile.mkdtemp(prefix="microdb-l5-")
    fm = FileManager(d, BLOCK_SIZE)
    bm = BufferManager(fm, 8)
    return d, fm, Database(fm, bm, Catalog(bm, fm))


def cleanup(d, fm):
    fm.close()
    shutil.rmtree(d, ignore_errors=True)


PINNED = [(1, "ada", 39, 1), (2, "ben", 31, 2), (3, "cyd", 37, 1),
          (4, "dee", 28, 3), (5, "eli", 36, 2), (6, "fay", 34, 1)]


def load_school(db):
    db.execute("CREATE TABLE students (sid INT, name VARCHAR(8), gpa INT, mid INT)")
    db.execute("CREATE TABLE majors (mid2 INT, dept VARCHAR(8))")
    for sid, name, gpa, mid in PINNED:
        db.execute(f"INSERT INTO students VALUES ({sid}, '{name}', {gpa}, {mid})")
    for mid, dept in [(1, "ds"), (2, "stat"), (3, "econ")]:
        db.execute(f"INSERT INTO majors VALUES ({mid}, '{dept}')")


# ---------------- PARSE group ----------------

def test_parse_simple_query():
    q = Parser("SELECT name, gpa FROM students").parse()
    expect(isinstance(q, QueryData), "SELECT must return a QueryData")
    expect(q.fields == ["name", "gpa"], f"fields wrong: {q.fields}")
    expect(q.tables == ["students"], f"tables wrong: {q.tables}")
    expect(q.predicate is None, "no WHERE means predicate None")


def test_parse_star_and_where():
    q = Parser("SELECT * FROM students WHERE gpa > 35 AND mid = 1").parse()
    expect(q.fields == ["*"], f"star select should record ['*'], got {q.fields}")
    expect(len(q.predicate.terms) == 2, "two AND-ed terms expected")
    expect(q.predicate.terms[0] == ("gpa", ">", 35), f"first term wrong: {q.predicate.terms[0]}")


def test_parse_join_term():
    q = Parser("SELECT name FROM students, majors WHERE mid = mid2").parse()
    expect(q.tables == ["students", "majors"], f"tables wrong: {q.tables}")
    field, op, rhs = q.predicate.terms[0]
    expect(field == "mid" and op == "=", "join term lhs/op wrong")
    expect(isinstance(rhs, F) and rhs.name == "mid2",
           "an ID on the right-hand side must become F('mid2'), not a string literal")


def test_parse_string_literal():
    q = Parser("SELECT sid FROM students WHERE name = 'ada'").parse()
    expect(q.predicate.terms[0] == ("name", "=", "ada"),
           "'ada' must parse as the literal string ada")


def test_parse_errors_help():
    for bad in ["SELECT name students", "SELECT FROM students",
                "SELECT name FROM students WHERE gpa >"]:
        try:
            Parser(bad).parse()
        except ParseError:
            continue
        raise AssertionError(f"bad SQL must raise ParseError: {bad!r}")


# ---------------- PLAN group ----------------

def test_plan_shapes():
    d, fm, db = fresh_db()
    try:
        load_school(db)
        plan = db.plan_query(Parser("SELECT name FROM students WHERE gpa > 35").parse())
        names = [type(s).__name__ for s in walk(plan)]
        expect(names == ["ProjectScan", "SelectScan", "TableScan"],
               f"expected Project<-Select<-Table, got {names}")
        plan.close()
        plan = db.plan_query(Parser("SELECT * FROM students").parse())
        expect(type(plan).__name__ == "TableScan",
               "SELECT * with no WHERE should be a bare TableScan — no useless wrappers")
        plan.close()
    finally:
        cleanup(d, fm)


def test_plan_join_shape():
    d, fm, db = fresh_db()
    try:
        load_school(db)
        plan = db.plan_query(
            Parser("SELECT name FROM students, majors WHERE mid = mid2").parse())
        names = [type(s).__name__ for s in walk(plan)]
        expect(names == ["ProjectScan", "SelectScan", "ProductScan",
                         "TableScan", "TableScan"],
               f"join plan shape wrong: {names}")
        plan.close()
    finally:
        cleanup(d, fm)


def walk(scan):
    yield scan
    if hasattr(scan, "left"):
        yield from walk(scan.left)
        yield from walk(scan.right)
    elif hasattr(scan, "scan"):
        yield from walk(scan.scan)


# ---------------- SQL group (end to end) ----------------

def test_sql_filter():
    d, fm, db = fresh_db()
    try:
        load_school(db)
        rows = db.execute("SELECT name FROM students WHERE gpa > 35")
        expect([r["name"] for r in rows] == ["ada", "cyd", "eli"],
               f"honors query wrong: {rows}")
    finally:
        cleanup(d, fm)


def test_sql_star():
    d, fm, db = fresh_db()
    try:
        load_school(db)
        rows = db.execute("SELECT * FROM majors")
        expect(rows == [{"mid2": 1, "dept": "ds"}, {"mid2": 2, "dept": "stat"},
                        {"mid2": 3, "dept": "econ"}],
               f"SELECT * should return every field of every row: {rows}")
    finally:
        cleanup(d, fm)


def test_sql_join():
    d, fm, db = fresh_db()
    try:
        load_school(db)
        rows = db.execute("SELECT name, dept FROM students, majors "
                          "WHERE mid = mid2 AND gpa > 35")
        expect(rows == [{"name": "ada", "dept": "ds"},
                        {"name": "cyd", "dept": "ds"},
                        {"name": "eli", "dept": "stat"}],
               f"the SQL join must match Lab 4's hand-built one: {rows}")
    finally:
        cleanup(d, fm)


def test_sql_string_where():
    d, fm, db = fresh_db()
    try:
        load_school(db)
        rows = db.execute("SELECT gpa FROM students WHERE name = 'fay'")
        expect(rows == [{"gpa": 34}], f"string WHERE wrong: {rows}")
    finally:
        cleanup(d, fm)


def test_sql_no_pins_leak():
    d, fm, db = fresh_db()
    try:
        load_school(db)
        db.execute("SELECT name, dept FROM students, majors WHERE mid = mid2")
        pinned = [b for b in db.bm.pool if b.is_pinned()]
        expect(not pinned, f"execute() must close its plan — leaked: {pinned}")
    finally:
        cleanup(d, fm)


# ---------------- function-level checks ----------------
from contextlib import ExitStack
from unittest.mock import patch
from query_engine import Predicate, SelectScan, ProjectScan, ProductScan


def _fixture_term(parser):
    field = parser.lex.expect("ID")
    op = parser.lex.expect("PUNCT")
    if op not in ("=", "<", ">"):
        raise ParseError("expected comparison operator")
    if parser.lex.match("ID"):
        rhs = F(parser.lex.next()[1])
    else:
        rhs = parser._parse_literal()
    return field, op, rhs


def _fixture_predicate(parser):
    terms = [_fixture_term(parser)]
    while parser.lex.match("KEYWORD", "and"):
        parser.lex.next()
        terms.append(_fixture_term(parser))
    return Predicate(*terms)


def _fixture_query(parser):
    parser.lex.expect("KEYWORD", "select")
    if parser.lex.match("PUNCT", "*"):
        parser.lex.next()
        fields = ["*"]
    else:
        fields = [parser.lex.expect("ID")]
        while parser.lex.match("PUNCT", ","):
            parser.lex.next()
            fields.append(parser.lex.expect("ID"))
    parser.lex.expect("KEYWORD", "from")
    tables = [parser.lex.expect("ID")]
    while parser.lex.match("PUNCT", ","):
        parser.lex.next()
        tables.append(parser.lex.expect("ID"))
    predicate = None
    if parser.lex.match("KEYWORD", "where"):
        parser.lex.next()
        predicate = _fixture_predicate(parser)
    return QueryData(fields, tables, predicate)


_UNIT_PARSER_DEPENDENCIES = {"parse_query": _fixture_query,
                             "_parse_predicate": _fixture_predicate,
                             "_parse_term": _fixture_term}


def _terms_as_values(predicate):
    return [(field, op, ("field", rhs.name) if isinstance(rhs, F) else rhs)
            for field, op, rhs in predicate.terms]


def _unit_parser(method):
    with ExitStack() as stack:
        for name, implementation in _UNIT_PARSER_DEPENDENCIES.items():
            if name != method:
                stack.enter_context(patch.object(Parser, name, implementation))
        if method == "parse_query":
            for text, fields, tables, terms in [
                ("SELECT name, gpa FROM students", ["name", "gpa"], ["students"], None),
                ("select * from students where gpa > 35 AND name = 'Ada'", ["*"], ["students"],
                 [("gpa", ">", 35), ("name", "=", "Ada")]),
                ("SELECT name FROM students, majors WHERE mid = mid2", ["name"], ["students", "majors"],
                 [("mid", "=", ("field", "mid2"))]),
            ]:
                parser = Parser(text)
                got = parser.parse_query()
                expect(isinstance(got, QueryData) and got.fields == fields and got.tables == tables,
                       "parse_query must preserve selected fields and table order")
                expect((None if got.predicate is None else _terms_as_values(got.predicate)) == terms,
                       "parse the optional WHERE; absent WHERE means None")
                expect(parser.lex.peek()[0] == "EOF", "consume exactly the complete query")
            bad = ["SELECT name students", "SELECT FROM students", "SELECT name FROM", "SELECT * FROM students WHERE"]
        elif method == "_parse_predicate":
            for text, terms in [
                ("gpa > 35", [("gpa", ">", 35)]),
                ("gpa > 30 AND name = 'Ada' AND mid = mid2",
                 [("gpa", ">", 30), ("name", "=", "Ada"), ("mid", "=", ("field", "mid2"))]),
            ]:
                parser = Parser(text + ")")
                got = parser._parse_predicate()
                expect(isinstance(got, Predicate) and _terms_as_values(got) == terms,
                       "collect one or more AND-ed terms in order")
                expect(parser.lex.peek() == ("PUNCT", ")"), "leave the token after the predicate unconsumed")
            bad = ["", "gpa > 30 AND"]
        else:
            for text, expected in [
                ("gpa > 35", ("gpa", ">", 35)), ("gpa < 0", ("gpa", "<", 0)),
                ("name = 'Ada'", ("name", "=", "Ada")),
                ("mid = mid2", ("mid", "=", ("field", "mid2"))),
            ]:
                parser = Parser(text + " AND more = 1")
                got = parser._parse_term()
                expect(_terms_as_values(Predicate(got)) == [expected],
                       "parse field, comparison and literal or F(field) right-hand side")
                expect(parser.lex.peek() == ("KEYWORD", "and"), "consume only one term")
            bad = ["gpa >", "35 > gpa", "gpa name 2", "gpa , 2"]
        for text in bad:
            try:
                getattr(Parser(text), method)()
            except ParseError:
                pass
            else:
                raise AssertionError(f"malformed input must raise ParseError: {text!r}")


def _unit_plan():
    # Construct QueryData directly so this check isolates the supplied planner.
    layouts = {name: object() for name in ("students", "majors", "rooms")}
    manager, files = object(), object()
    class CatalogFixture:
        def get_layout(self, name):
            return layouts[name]
    class TableFixture:
        def __init__(self, bm, fm, name, layout):
            expect(bm is manager and fm is files, "pass the database's managers to each table scan")
            expect(layout is layouts[name], "look up each table's own layout")
            self.name = name
        def before_first(self):
            raise AssertionError("plan_query builds the plan; the runner positions it later")
        def has_field(self, field):
            return field in {"students": {"name", "gpa", "mid"},
                             "majors": {"mid2", "dept"}, "rooms": {"room"}}[self.name]
        def close(self):
            pass
    db = Database(files, manager, CatalogFixture())
    cases = [(["*"], ["students"], None),
             (["name"], ["students"], None),
             (["*"], ["students"], Predicate(("gpa", ">", 35))),
             (["name", "dept"], ["students", "majors", "rooms"], Predicate(("mid", "=", F("mid2"))))]
    with patch("sql_frontend.TableScan", TableFixture):
        for fields, tables, predicate in cases:
            plan = db.plan_query(QueryData(fields, tables, predicate))
            scan = plan
            try:
                if fields != ["*"]:
                    expect(isinstance(scan, ProjectScan) and scan.fields == fields, "projection must be outermost")
                    scan = scan.scan
                if predicate is not None:
                    expect(isinstance(scan, SelectScan) and scan.predicate is predicate, "apply the query predicate below projection")
                    scan = scan.scan
                for name in reversed(tables[1:]):
                    expect(isinstance(scan, ProductScan), "multiple tables require products folded left to right")
                    expect(isinstance(scan.right, TableFixture) and scan.right.name == name, "preserve table order")
                    scan = scan.left
                expect(isinstance(scan, TableFixture) and scan.name == tables[0],
                       "single-table or leftmost input must be the matching table scan, with no extra wrappers")
            finally:
                if plan is not None:
                    plan.close()


UNIT_TESTS = {f"Parser.{name}": (lambda name=name: _unit_parser(name))
              for name in _UNIT_PARSER_DEPENDENCIES}
UNIT_TESTS["Database.plan_query"] = _unit_plan


def run_integration():
    RESULTS.clear()
    print("PARSE group")
    check("PARSE", "SELECT fields FROM table",                 test_parse_simple_query)
    check("PARSE", "star select + AND-ed WHERE",               test_parse_star_and_where)
    check("PARSE", "an ID rhs becomes F (join term)",          test_parse_join_term)
    check("PARSE", "'strings' parse as literals",              test_parse_string_literal)
    check("PARSE", "bad SQL raises ParseError, not chaos",     test_parse_errors_help)
    print("PLAN group")
    check("PLAN", "plan shapes: no useless wrappers",          test_plan_shapes)
    check("PLAN", "join plan: products fold left to right",    test_plan_join_shape)
    print("SQL group")
    check("SQL", "the honors query, via text",                 test_sql_filter)
    check("SQL", "SELECT * returns all fields",                test_sql_star)
    check("SQL", "the Lab 4 join, via text",                   test_sql_join)
    check("SQL", "WHERE on a string field",                    test_sql_string_where)
    check("SQL", "execute() leaks no pins",                    test_sql_no_pins_leak)
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
        print("UNIT checks isolate each supplied method with known fixtures.")
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
