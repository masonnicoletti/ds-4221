"""Lab 1 test harness. Run:  python3 test_filemanager.py

Two groups, mirroring the lab page:

    PAGE  : Page get/set round-trips (no disk involved)
    FILE  : FileManager read/write/append/length + durability across reopen

Every test prints PASS or FAIL with a reason. The Gradescope autograder
runs this same harness, so green here is the grade.
Pure stdlib; no pytest needed.
"""

import os
import shutil
import sys
import tempfile
import traceback

from file_manager import BlockId, Page, FileManager

BLOCK_SIZE = 128          # small on purpose: failures are easier to hexdump
RESULTS = []


def check(group, name, fn):
    try:
        fn()
        RESULTS.append(True)
        print(f"  [PASS] {group}: {name}")
    except Exception as e:
        RESULTS.append(False)
        kind = type(e).__name__
        msg = str(e) or "(no message)"
        if isinstance(e, NotImplementedError):
            print(f"  [FAIL] {group}: {name} - not implemented yet")
        else:
            print(f"  [FAIL] {group}: {name} - {kind}: {msg}")
            if "-v" in sys.argv:
                traceback.print_exc()


def expect(cond, why):
    if not cond:
        raise AssertionError(why)


# ---------------- PAGE group ----------------

def test_int_roundtrip():
    p = Page(BLOCK_SIZE)
    for off, val in [(0, 1), (4, 39), (60, -7), (100, 2**31 - 1)]:
        p.set_int(off, val)
    for off, val in [(0, 1), (4, 39), (60, -7), (100, 2**31 - 1)]:
        got = p.get_int(off)
        expect(got == val, f"get_int({off}) returned {got}, expected {val}")


def test_bytes_roundtrip():
    p = Page(BLOCK_SIZE)
    payload = bytes([0, 255, 42, 7])
    p.set_bytes(10, payload)
    got = p.get_bytes(10)
    expect(got == payload, f"get_bytes returned {got!r}, expected {payload!r}")


def test_string_roundtrip():
    p = Page(BLOCK_SIZE)
    for off, s in [(0, "ada"), (20, "héllo wörld"), (60, "")]:
        p.set_string(off, s)
        got = p.get_string(off)
        expect(got == s, f"get_string({off}) returned {got!r}, expected {s!r}")


def test_adjacent_values():
    # The pinned toy row from lecture: id=1, name='ada', gpa×10=39.
    # Layout: int at 0 (4 bytes) · string at 4 (4+3 bytes) · int at 11.
    p = Page(BLOCK_SIZE)
    p.set_int(0, 1)
    p.set_string(4, "ada")
    p.set_int(11, 39)
    expect(p.get_int(0) == 1, "id clobbered. Did set_string write outside its range?")
    expect(p.get_string(4) == "ada", "name clobbered. Check the offsets in set_int.")
    expect(p.get_int(11) == 39, "gpa clobbered. Is the string length prefix wrong?")


# ---------------- FILE group ----------------

def in_tmpdir(fn):
    d = tempfile.mkdtemp(prefix="microdb-test-")
    try:
        fn(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_append_grows_length():
    def go(d):
        fm = FileManager(d, BLOCK_SIZE)
        expect(fm.length("t.tbl") == 0, "new file should have length 0")
        b0 = fm.append("t.tbl")
        expect(b0.blknum == 0, f"first append returned block {b0.blknum}, expected 0")
        expect(fm.length("t.tbl") == 1, "length should be 1 after one append")
        b1 = fm.append("t.tbl")
        expect(b1.blknum == 1, f"second append returned block {b1.blknum}, expected 1")
        expect(fm.length("t.tbl") == 2, "length should be 2 after two appends")
        fm.close()
    in_tmpdir(go)


def test_write_read_roundtrip():
    def go(d):
        fm = FileManager(d, BLOCK_SIZE)
        blk = fm.append("t.tbl")
        p = Page(BLOCK_SIZE)
        p.set_int(0, 1); p.set_string(4, "ada"); p.set_int(11, 39)
        fm.write(blk, p)
        q = Page(BLOCK_SIZE)
        fm.read(blk, q)
        expect(q.get_int(0) == 1 and q.get_string(4) == "ada" and q.get_int(11) == 39,
               "block read back differs from what was written")
        fm.close()
    in_tmpdir(go)


def test_block_independence():
    def go(d):
        fm = FileManager(d, BLOCK_SIZE)
        b0, b1 = fm.append("t.tbl"), fm.append("t.tbl")
        p0, p1 = Page(BLOCK_SIZE), Page(BLOCK_SIZE)
        p0.set_string(0, "block zero")
        p1.set_string(0, "block one")
        fm.write(b0, p0); fm.write(b1, p1)
        q = Page(BLOCK_SIZE)
        fm.read(b0, q)
        expect(q.get_string(0) == "block zero", "writing block 1 clobbered block 0. Check your seek offsets.")
        fm.read(b1, q)
        expect(q.get_string(0) == "block one", "block 1 read back wrong")
        fm.close()
    in_tmpdir(go)


def test_read_past_end_raises():
    def go(d):
        fm = FileManager(d, BLOCK_SIZE)
        fm.append("t.tbl")
        try:
            fm.read(BlockId("t.tbl", 5), Page(BLOCK_SIZE))
        except ValueError:
            fm.close(); return
        fm.close()
        raise AssertionError("reading block 5 of a 1-block file should raise ValueError")
    in_tmpdir(go)


def test_durability_across_reopen():
    def go(d):
        fm = FileManager(d, BLOCK_SIZE)
        blk = fm.append("t.tbl")
        p = Page(BLOCK_SIZE)
        p.set_string(0, "survives")
        fm.write(blk, p)
        fm.close()                       # simulate the process ending
        fm2 = FileManager(d, BLOCK_SIZE)  # …and a fresh process starting
        q = Page(BLOCK_SIZE)
        fm2.read(BlockId("t.tbl", 0), q)
        expect(q.get_string(0) == "survives",
               "data did not survive close + reopen. Is write() actually writing?")
        fm2.close()
    in_tmpdir(go)


if __name__ == "__main__":
    print("PAGE group")
    check("PAGE", "int round-trip (incl. negative, INT_MAX)", test_int_roundtrip)
    check("PAGE", "bytes round-trip (length-prefixed)",       test_bytes_roundtrip)
    check("PAGE", "string round-trip (UTF-8, incl. empty)",   test_string_roundtrip)
    check("PAGE", "adjacent values don't clobber (ada row)",  test_adjacent_values)
    print("FILE group")
    check("FILE", "append grows length 0 → 1 → 2",            test_append_grows_length)
    check("FILE", "write/read round-trip",                    test_write_read_roundtrip)
    check("FILE", "blocks are independent",                   test_block_independence)
    check("FILE", "read past end raises ValueError",          test_read_past_end_raises)
    check("FILE", "data survives close + reopen",             test_durability_across_reopen)
    n_pass = sum(RESULTS)
    print(f"\n{n_pass}/{len(RESULTS)} tests passed")
    sys.exit(0 if n_pass == len(RESULTS) else 1)
