"""Lab 3 test harness — run:  python3 test_records.py

Four groups, mirroring the lab page:

    LAYOUT  — Schema → byte offsets → slot size
    RECORD  — get/set within slots, insert_after/next_after/delete flags
    SCAN    — TableScan across block boundaries, deletes and updates
    CATALOG — the provided catalog works iff your record layer does

Pure stdlib; no pytest. The Gradescope autograder runs this same harness.
"""

import shutil
import sys
import tempfile
import traceback

from file_manager import BlockId, FileManager
from buffer_manager import BufferManager
from record_manager import Schema, Layout, RecordPage, TableScan
from catalog import Catalog

BLOCK_SIZE = 128          # students slot = 24 bytes -> 5 slots per block
RESULTS = []


def students_schema():
    return (Schema().add_int_field("id")
                    .add_string_field("name", 8)
                    .add_int_field("gpa"))


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


def fresh(num_buffers=8):
    d = tempfile.mkdtemp(prefix="microdb-l3-")
    fm = FileManager(d, BLOCK_SIZE)
    return d, fm, BufferManager(fm, num_buffers)


def cleanup(d, fm):
    fm.close()
    shutil.rmtree(d, ignore_errors=True)


# ---------------- LAYOUT group ----------------

def test_layout_offsets():
    lay = Layout(students_schema())
    expect(lay.offset("id") == 4,   f"id should start at 4 (after the flag), got {lay.offset('id')}")
    expect(lay.offset("name") == 8, f"name should start at 8, got {lay.offset('name')}")
    expect(lay.offset("gpa") == 20, f"gpa should start at 20 (name takes 4+8), got {lay.offset('gpa')}")
    expect(lay.slot_size == 24,     f"slot_size should be 24, got {lay.slot_size}")


def test_slots_per_block():
    d, fm, bm = fresh()
    try:
        lay = Layout(students_schema())
        blk = fm.append("t.tbl")
        rp = RecordPage(bm, blk, lay)
        expect(rp.slot_count() == BLOCK_SIZE // 24,
               f"128-byte block / 24-byte slot = 5 slots, got {rp.slot_count()}")
        rp.close()
    finally:
        cleanup(d, fm)


# ---------------- RECORD group ----------------

def test_field_roundtrip():
    d, fm, bm = fresh()
    try:
        lay = Layout(students_schema())
        rp = RecordPage(bm, fm.append("t.tbl"), lay)
        rp.set_int(0, "id", 1); rp.set_string(0, "name", "ada"); rp.set_int(0, "gpa", 39)
        rp.set_int(1, "id", 2); rp.set_string(1, "name", "ben"); rp.set_int(1, "gpa", 31)
        expect(rp.get_int(0, "id") == 1 and rp.get_string(0, "name") == "ada"
               and rp.get_int(0, "gpa") == 39, "slot 0 (ada) came back wrong")
        expect(rp.get_int(1, "id") == 2 and rp.get_string(1, "name") == "ben"
               and rp.get_int(1, "gpa") == 31,
               "slot 1 (ben) came back wrong — is _field_pos adding slot*slot_size?")
        rp.close()
    finally:
        cleanup(d, fm)


def test_insert_after_flags():
    d, fm, bm = fresh()
    try:
        lay = Layout(students_schema())
        rp = RecordPage(bm, fm.append("t.tbl"), lay)
        s0 = rp.insert_after(-1)
        s1 = rp.insert_after(s0)
        expect((s0, s1) == (0, 1), f"fresh page inserts should land in slots 0,1 — got {s0},{s1}")
        expect(rp.is_used(0) and rp.is_used(1) and not rp.is_used(2),
               "insert_after must flip the USED flag of exactly the returned slot")
        for s in (2, 3, 4):
            rp.insert_after(s - 1)
        expect(rp.insert_after(4) == -1, "a full page must return -1, not raise or wrap")
        rp.close()
    finally:
        cleanup(d, fm)


def test_delete_and_reuse():
    d, fm, bm = fresh()
    try:
        lay = Layout(students_schema())
        rp = RecordPage(bm, fm.append("t.tbl"), lay)
        for s in range(3):
            rp.insert_after(s - 1)
        rp.delete(1)
        expect(not rp.is_used(1), "delete must clear the flag")
        expect(rp.next_after(0) == 2, "next_after must skip the deleted slot 1")
        expect(rp.insert_after(-1) == 1, "insert_after must reuse the freed slot 1")
        rp.close()
    finally:
        cleanup(d, fm)


# ---------------- SCAN group ----------------

def fill(ts, n):
    for i in range(n):
        ts.insert()
        ts.set_int("id", i)
        ts.set_string("name", f"s{i}")
        ts.set_int("gpa", 30 + i % 10)


def test_scan_all_rows():
    d, fm, bm = fresh()
    try:
        lay = Layout(students_schema())
        ts = TableScan(bm, fm, "students", lay)
        fill(ts, 12)                                  # 5 per block -> 3 blocks
        ts.before_first()
        ids = []
        while ts.next():
            ids.append(ts.get_int("id"))
        ts.close()
        expect(ids == list(range(12)),
               f"expected ids 0..11 in order, got {ids} — does next() cross blocks?")
    finally:
        cleanup(d, fm)


def test_file_grows_by_blocks():
    d, fm, bm = fresh()
    try:
        lay = Layout(students_schema())
        ts = TableScan(bm, fm, "students", lay)
        fill(ts, 12)
        ts.close()
        expect(fm.length("students.tbl") == 3,
               f"12 rows at 5/block should occupy 3 blocks, file has {fm.length('students.tbl')} — "
               "does insert() fill every slot before appending?")
    finally:
        cleanup(d, fm)


def test_delete_during_scan():
    d, fm, bm = fresh()
    try:
        lay = Layout(students_schema())
        ts = TableScan(bm, fm, "students", lay)
        fill(ts, 12)
        ts.before_first()
        while ts.next():                              # delete gpa < 35
            if ts.get_int("gpa") < 35:
                ts.delete()
        ts.before_first()
        survivors = []
        while ts.next():
            survivors.append(ts.get_int("gpa"))
        ts.close()
        expect(survivors and all(g >= 35 for g in survivors),
               f"after deleting gpa<35, survivors were {survivors}")
        expect(len(survivors) == 5, f"expected 5 survivors (gpas 35-39), got {len(survivors)}")
    finally:
        cleanup(d, fm)


def test_update_during_scan():
    d, fm, bm = fresh()
    try:
        lay = Layout(students_schema())
        ts = TableScan(bm, fm, "students", lay)
        fill(ts, 7)
        ts.before_first()
        while ts.next():
            if ts.get_int("id") == 6:                 # lives in block 1
                ts.set_int("gpa", 40)
        ts.before_first()
        got = None
        while ts.next():
            if ts.get_int("id") == 6:
                got = ts.get_int("gpa")
        ts.close()
        bm.flush_all()
        expect(got == 40, f"updated gpa should read back 40, got {got}")
    finally:
        cleanup(d, fm)


def test_one_pin_at_a_time():
    d, fm, bm = fresh(num_buffers=2)                  # tiny pool: leaks abort fast
    try:
        lay = Layout(students_schema())
        ts = TableScan(bm, fm, "students", lay)
        fill(ts, 12)                                  # 3 blocks through 2 frames
        ts.before_first()
        n = 0
        while ts.next():
            n += 1
        ts.close()
        expect(n == 12, f"scan through a 2-frame pool should still see 12 rows, got {n}")
        pinned = [b for b in bm.pool if b.is_pinned()]
        expect(not pinned, f"after close(), no frame may stay pinned — leaked: {pinned}")
    finally:
        cleanup(d, fm)


# ---------------- CATALOG group ----------------

def test_catalog_roundtrip():
    d, fm, bm = fresh()
    try:
        cat = Catalog(bm, fm)
        cat.create_table("students", students_schema())
        lay = cat.get_layout("students")
        expect(lay.slot_size == 24, f"catalog slot_size should be 24, got {lay.slot_size}")
        expect(lay.offset("id") == 4 and lay.offset("name") == 8 and lay.offset("gpa") == 20,
               "offsets rebuilt from the catalog don't match the originals")
        expect(lay.schema.fields() == ["id", "name", "gpa"],
               f"schema fields should rebuild in offset order, got {lay.schema.fields()}")
    finally:
        cleanup(d, fm)


def test_catalog_rows():
    d, fm, bm = fresh()
    try:
        cat = Catalog(bm, fm)
        cat.create_table("students", students_schema())
        ts = TableScan(bm, fm, "field_catalog", cat.fcat_layout)
        rows = []
        while ts.next():
            if ts.get_string("tblname") == "students":
                rows.append((ts.get_string("fldname"), ts.get_int("offset")))
        ts.close()
        expect(sorted(rows) == [("gpa", 20), ("id", 4), ("name", 8)],
               f"field_catalog rows for students wrong: {sorted(rows)}")
    finally:
        cleanup(d, fm)


if __name__ == "__main__":
    print("LAYOUT group")
    check("LAYOUT", "students offsets are 4 / 8 / 20, slot 24", test_layout_offsets)
    check("LAYOUT", "slots per block arithmetic",               test_slots_per_block)
    print("RECORD group")
    check("RECORD", "fields round-trip in two slots",           test_field_roundtrip)
    check("RECORD", "insert_after flips flags in order",        test_insert_after_flags)
    check("RECORD", "delete frees, next skips, insert reuses",  test_delete_and_reuse)
    print("SCAN group")
    check("SCAN", "12 rows come back in order across blocks",   test_scan_all_rows)
    check("SCAN", "file grows to exactly 3 blocks",             test_file_grows_by_blocks)
    check("SCAN", "delete during scan",                         test_delete_during_scan)
    check("SCAN", "update during scan is durable",              test_update_during_scan)
    check("SCAN", "one pin at a time (2-frame pool, no leaks)", test_one_pin_at_a_time)
    print("CATALOG group")
    check("CATALOG", "create_table / get_layout round-trip",    test_catalog_roundtrip)
    check("CATALOG", "field_catalog rows are exactly right",    test_catalog_rows)
    n = sum(RESULTS)
    print(f"\n{n}/{len(RESULTS)} tests passed")
    sys.exit(0 if n == len(RESULTS) else 1)
