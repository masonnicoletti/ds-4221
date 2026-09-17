"""Lab 4: follow SQL's intent down to catalog records, slots, and scans.

Run from this directory:
    python3 sql_walkthrough.py            # CREATE, INSERT, DELETE: provided code
    python3 sql_walkthrough.py --queries  # also SELECT/JOIN: finish Lab 4 first

SQL in the comments explains the intent. This script calls Python APIs;
it does not parse SQL. The SQL front end begins in Lab 5. Every run uses a
fresh temporary database and removes it when finished.
"""

import argparse
from tempfile import TemporaryDirectory

from file_manager import FileManager
from buffer_manager import BufferManager
from record_manager import Schema, TableScan
from catalog import Catalog
from query_engine import F, Predicate, SelectScan, ProjectScan, ProductScan


def create_tables(catalog):
    # CREATE TABLE students (sid INT, name VARCHAR(8), gpa INT, mid INT);
    schema = (Schema().add_int_field("sid")
                      .add_string_field("name", 8)
                      .add_int_field("gpa")
                      .add_int_field("mid"))
    catalog.create_table("students", schema)
    # Look it up again: the catalog reconstructs the layout from its own rows.
    students_layout = catalog.get_layout("students")

    # CREATE TABLE majors (mid2 INT, dept VARCHAR(8));
    schema = Schema().add_int_field("mid2").add_string_field("dept", 8)
    catalog.create_table("majors", schema)
    majors_layout = catalog.get_layout("majors")

    offsets = {f: students_layout.offset(f) for f in students_layout.schema.fields()}
    assert offsets == {"sid": 4, "name": 8, "gpa": 20, "mid": 24}
    assert students_layout.slot_size == 28
    print("CREATE students: offsets", offsets, "slot size", students_layout.slot_size)
    return students_layout, majors_layout


def insert_rows(bm, fm, students_layout, majors_layout):
    # INSERT INTO students (sid, name, gpa, mid) VALUES
    # (1, 'ada', 39, 1), (2, 'ben', 31, 2), (3, 'cyd', 37, 1),
    # (4, 'dee', 28, 3), (5, 'eli', 36, 2), (6, 'fay', 34, 1),
    # (7, 'temp', 40, 1);
    rows = [(1, "ada", 39, 1), (2, "ben", 31, 2), (3, "cyd", 37, 1),
            (4, "dee", 28, 3), (5, "eli", 36, 2), (6, "fay", 34, 1),
            (7, "temp", 40, 1)]
    students = TableScan(bm, fm, "students", students_layout)
    try:
        for sid, name, gpa, mid in rows:
            students.insert()                 # reserve a free slot; flag becomes USED
            students.set_int("sid", sid)       # fill that slot using layout offsets
            students.set_string("name", name)
            students.set_int("gpa", gpa)
            students.set_int("mid", mid)
            print("INSERT", name, "at (block, slot)", students.rid())
    finally:
        students.close()

    # INSERT INTO majors (mid2, dept) VALUES (1, 'ds'), (2, 'stat'), (3, 'econ');
    majors = TableScan(bm, fm, "majors", majors_layout)
    try:
        for mid2, dept in [(1, "ds"), (2, "stat"), (3, "econ")]:
            majors.insert()
            majors.set_int("mid2", mid2)
            majors.set_string("dept", dept)
    finally:
        majors.close()


def delete_row(bm, fm, students_layout):
    # DELETE FROM students WHERE sid = 7;
    students = TableScan(bm, fm, "students", students_layout)
    try:
        students.before_first()
        while students.next():
            if students.get_int("sid") == 7:
                rid = students.rid()
                students.delete()             # flag becomes EMPTY; bytes are not shifted
                print("DELETE sid 7 at (block, slot)", rid)
        students.before_first()
        remaining = []
        while students.next():
            remaining.append(students.get_int("sid"))
        assert remaining == [1, 2, 3, 4, 5, 6]
        print("Live student IDs:", remaining)
    finally:
        students.close()


def run_queries(bm, fm, students_layout, majors_layout):
    # SELECT name FROM students WHERE gpa > 35;
    source = TableScan(bm, fm, "students", students_layout)
    selected = SelectScan(source, Predicate(("gpa", ">", 35)))
    plan = ProjectScan(selected, ["name"])
    try:
        plan.before_first()
        names = []
        while plan.next():                    # pull at the root, read its current row
            names.append(plan.get_val("name"))
        assert names == ["ada", "cyd", "eli"]
        print("SELECT:", names)
    finally:
        plan.close()                         # closes the underlying TableScan too

    # SELECT name, dept FROM students JOIN majors ON mid = mid2 WHERE gpa > 35;
    students = TableScan(bm, fm, "students", students_layout)
    majors = TableScan(bm, fm, "majors", majors_layout)
    pairs = ProductScan(students, majors)
    matched = SelectScan(pairs, Predicate(("mid", "=", F("mid2")),
                                          ("gpa", ">", 35)))
    plan = ProjectScan(matched, ["name", "dept"])
    try:
        plan.before_first()                  # positions both sides of the product
        rows = []
        while plan.next():
            rows.append((plan.get_val("name"), plan.get_val("dept")))
        assert rows == [("ada", "ds"), ("cyd", "ds"), ("eli", "stat")]
        print("JOIN:", rows)
    finally:
        plan.close()                         # recursively closes BOTH table scans


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", action="store_true",
                        help="also run SELECT and JOIN with your completed operators")
    args = parser.parse_args()
    with TemporaryDirectory(prefix="microdb-sql-") as directory:
        fm = FileManager(directory, block_size=128)
        bm = BufferManager(fm, num_buffers=8)
        try:
            catalog = Catalog(bm, fm)
            students_layout, majors_layout = create_tables(catalog)
            insert_rows(bm, fm, students_layout, majors_layout)
            delete_row(bm, fm, students_layout)
            if args.queries:
                try:
                    run_queries(bm, fm, students_layout, majors_layout)
                except NotImplementedError:
                    parser.exit(1, "SELECT/JOIN need your Lab 4 operators. "
                                   "Complete query_engine.py, then rerun with --queries.\n")
            else:
                print("Add --queries after completing the Lab 4 scan operators.")
            assert not any(buffer.is_pinned() for buffer in bm.pool)
            print("All scans closed; no buffer pins remain.")
        finally:
            try:
                bm.flush_all()               # close() releases pins; flushing writes dirty pages
            finally:
                fm.close()


if __name__ == "__main__":
    main()
