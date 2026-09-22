"""Lab 5: predict query work, then measure the supplied plans.

    python3 measure_sql.py
    python3 measure_sql.py --sql "SELECT name FROM students WHERE gpa > 35"
    python3 measure_sql.py --queries queries.sql --students 600 --repeat 7
    python3 measure_sql.py --queries queries.sql --json > results.json

Each SELECT runs with the simple planner and a supplied early-filter alternative.
Counters and timings come from separate executions. Timings exclude fixture
creation, parsing, planning, and printing. No database server or extra package
is required; each invocation creates and removes its own temporary database.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import json
from pathlib import Path
from statistics import median
import tempfile
from time import perf_counter

from file_manager import FileManager
from buffer_manager import BufferManager
from catalog import Catalog
from record_manager import TableScan
from query_engine import CountingScan, F, Predicate, ProductScan, ProjectScan, SelectScan
from sql_frontend import Database, Parser, ParseError, QueryData, render_plan

BLOCK_SIZE = 4096
N_STUDENTS = 300
QUERIES = [
    "SELECT name FROM students WHERE gpa > 35",
    "SELECT * FROM majors",
    "SELECT name, dept FROM students, majors WHERE mid = mid2 AND gpa > 35 AND dept = 'ds'",
]


@contextmanager
def school(students=N_STUDENTS):
    """Reproducible data: GPA cycles 20..39; major IDs cycle 1..3."""
    with tempfile.TemporaryDirectory(prefix="microdb-l5m-") as directory:
        fm = FileManager(directory, BLOCK_SIZE)
        bm = BufferManager(fm, 8)
        db = Database(fm, bm, Catalog(bm, fm))
        try:
            db.execute("CREATE TABLE students (sid INT, name VARCHAR(16), gpa INT, mid INT)")
            db.execute("CREATE TABLE majors (mid2 INT, dept VARCHAR(8))")
            for i in range(students):
                db.execute(f"INSERT INTO students VALUES ({i}, 's{i}', {20 + i % 20}, {1 + i % 3})")
            for mid, dept in [(1, "ds"), (2, "stat"), (3, "econ")]:
                db.execute(f"INSERT INTO majors VALUES ({mid}, '{dept}')")
            bm.flush_all()
            yield db
        finally:
            fm.close()


def early_filter_plan(db, data):
    """Move each single-table AND term below the product; keep join terms above.

    This supplied alternative preserves inner-product semantics, including
    duplicates. It requires unique field names across the FROM tables. It does
    not choose join order or use indexes, statistics, materialization, or caching.
    """
    layouts = [db.catalog.get_layout(table) for table in data.tables]
    owners = {}
    for index, layout in enumerate(layouts):
        for field in layout.schema.fields():
            if field in owners:
                raise ValueError("early-filter comparison needs distinct field names across tables")
            owners[field] = index
    local = [[] for _ in layouts]
    remaining = []
    for term in data.predicate.terms if data.predicate else ():
        field, _, rhs = term
        names = [field] + ([rhs.name] if isinstance(rhs, F) else [])
        if any(name not in owners for name in names):
            raise ValueError(f"unknown predicate field in {term!r}")
        inputs = {owners[name] for name in names}
        if len(inputs) == 1:
            local[next(iter(inputs))].append(term)
        else:
            remaining.append(term)
    scans = []
    try:
        for table, layout, terms in zip(data.tables, layouts, local):
            scan = TableScan(db.bm, db.fm, table, layout)
            scans.append(SelectScan(scan, Predicate(*terms)) if terms else scan)
        plan = scans[0]
        for right in scans[1:]:
            plan = ProductScan(plan, right)
        if remaining:
            plan = SelectScan(plan, Predicate(*remaining))
        return ProjectScan(plan, data.fields) if data.fields != ["*"] else plan
    except Exception:
        for scan in scans:
            scan.close()
        raise


class MeasuredPredicate(Predicate):
    """Count comparisons actually evaluated, respecting AND short-circuiting."""
    def __init__(self, original, counts):
        super().__init__(*original.terms)
        self.counts = counts

    def is_satisfied(self, scan):
        for field, op, rhs in self.terms:
            self.counts["comparisons"] += 1
            value = scan.get_val(rhs.name) if isinstance(rhs, F) else rhs
            if not self.OPS[op](scan.get_val(field), value):
                return False
        return True


def instrument(scan, counts):
    """Count successful row advances at table and product boundaries."""
    if isinstance(scan, ProductScan):
        scan.left = instrument(scan.left, counts)
        scan.right = instrument(scan.right, counts)
        counter = CountingScan(scan)
        counts["products"].append(counter)
        return counter
    if isinstance(scan, TableScan):
        counter = CountingScan(scan)
        counts["tables"].append((scan.filename.removesuffix('.tbl'), counter))
        return counter
    if isinstance(scan, SelectScan):
        scan.predicate = MeasuredPredicate(scan.predicate, counts)
    scan.scan = instrument(scan.scan, counts)
    return scan


def pull(plan, fields):
    """The runner owns rewind and close; even a bad query releases its pins."""
    try:
        plan.before_first()
        rows = []
        while plan.next():
            rows.append({field: plan.get_val(field) for field in fields})
        return rows
    finally:
        plan.close()


def bag(rows):
    """Compare results without assuming an order; retain duplicate counts."""
    return Counter(tuple(sorted(row.items())) for row in rows)


def measure(db, data, mode, repeats=5):
    build = db.plan_query if mode == "simple" else lambda query: early_filter_plan(db, query)
    fields = data.fields if data.fields != ["*"] else [
        field for table in data.tables for field in db.catalog.get_layout(table).schema.fields()]
    counts = {"tables": [], "products": [], "comparisons": 0}
    plan = build(data)
    drawing = render_plan(plan)
    rows = pull(instrument(plan, counts), fields)
    # A separate uninstrumented warm-up precedes the uninstrumented samples.
    pull(build(data), fields)
    times = []
    for _ in range(repeats):
        plan = build(data)                 # catalog lookups and plan creation are not timed
        start = perf_counter()
        pull(plan, fields)                 # includes decoding/materializing output and close
        times.append((perf_counter() - start) * 1000)
    visits = Counter()
    for table, counter in counts["tables"]:
        visits[table] += counter.rows
    return {
        "mode": mode, "plan": drawing, "table_row_visits": dict(visits),
        "candidate_pairs": sum(counter.rows for counter in counts["products"]),
        "predicate_comparisons": counts["comparisons"],
        "rows_returned": len(rows), "output_cells": len(rows) * len(fields),
        "median_ms": median(times), "samples_ms": times,
    }, rows


def compare(db, sql, repeats=5):
    data = Parser(sql).parse()
    if not isinstance(data, QueryData):
        raise ValueError("The measurement runner accepts SELECT only; use microdb.py for CREATE and INSERT.")
    simple, left = measure(db, data, "simple", repeats)
    early, right = measure(db, data, "early-filter", repeats)
    equal = bag(left) == bag(right)
    if not equal:
        raise AssertionError("The two plans returned different result multisets")
    return {"sql": sql, "same_results": equal, "measurements": [simple, early]}


def read_queries(text):
    """One or more statements, separated by semicolons; allow -- comments.

    Match the teaching lexer's simple single-quoted strings: a semicolon or
    comment marker inside a string remains part of that string.
    """
    statements, current = [], []
    quoted = False
    i = 0
    while i < len(text):
        char = text[i]
        if not quoted and text[i:i + 2] == "--":
            end = text.find('\n', i)
            i = len(text) if end < 0 else end
            current.append(' ')
            continue
        if char == "'":
            quoted = not quoted
        if char == ';' and not quoted:
            if ''.join(current).strip():
                statements.append(''.join(current).strip())
            current = []
        else:
            current.append(char)
        i += 1
    if ''.join(current).strip():
        statements.append(''.join(current).strip())
    return statements


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("use a positive integer")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--sql', action='append', help='a SELECT statement; repeat the flag for several queries')
    source.add_argument('--queries', type=Path, help='your SQL file with semicolon-separated SELECT statements')
    parser.add_argument('--students', type=positive, default=N_STUDENTS)
    parser.add_argument('--repeat', type=positive, default=5, help='uninstrumented timing samples per plan (default 5)')
    parser.add_argument('--json', action='store_true', help='print machine-readable results, including all timing samples')
    args = parser.parse_args()
    try:
        queries = read_queries(args.queries.read_text()) if args.queries else args.sql or QUERIES
        if not queries:
            parser.error('No queries found. Add SELECT statements to your SQL file.')
        with school(args.students) as db:
            results = [compare(db, sql, args.repeat) for sql in queries]
    except (ParseError, ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"Query error: {error}\n")
    if args.json:
        print(json.dumps({"students": args.students, "majors": 3, "buffer_frames": 8,
                          "block_size": BLOCK_SIZE, "timing_scope": "execution only, repeated after warm-up; no cache reset",
                          "results": results}, indent=2))
        return
    print(f"Fixture: {args.students} students, 3 majors; 4096-byte blocks, 8 buffer frames.")
    print("Counters measure logical work, not disk reads. Timings are separate execution-only runs.")
    print("One warm-up precedes each plan's samples; caches are not reset. Compare medians, not one run.")
    for result in results:
        print('\nmicrodb> ' + result['sql'])
        for m in result['measurements']:
            print(f"\n{m['mode']} plan:\n{m['plan']}")
            print('  table row visits: ' + ', '.join(f'{table}={visits}' for table, visits in m['table_row_visits'].items()))
            print(f"  candidate pairs: {m['candidate_pairs']}; predicate comparisons: {m['predicate_comparisons']}")
            print(f"  rows returned: {m['rows_returned']}; output cells: {m['output_cells']}")
            print(f"  execution median: {m['median_ms']:.3f} ms ({len(m['samples_ms'])} samples)")
        print('  Same results, including duplicates: yes')
    print('\nExplain the counts first. A reduction in candidate pairs is not a guaranteed equal reduction in time.')


if __name__ == '__main__':
    main()
