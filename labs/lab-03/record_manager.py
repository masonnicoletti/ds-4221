"""microdb · part 3 — records, slots, and the table scan.

Lab 3 of Advanced Databases for Data Science (DS 6XXX, Fall 2026).
Runs on top of Lab 1's file manager and Lab 2's buffer manager (reference
implementations of both ship in this folder — use them).

This layer imposes meaning on pages: rows live in fixed-size SLOTS, a table
is a file of slotted blocks, and a TableScan walks every row of a table
through the buffer pool. After this lab, "the ada row" has an address.

SLOT LAYOUT (the contract; every later lab depends on it):

    A record slot is [ 4-byte in-use flag ][ field bytes, schema order ].
        flag: int 0 = EMPTY, 1 = USED (at slot offset 0)
        int field:        4 bytes
        varchar(n) field: 4 + n bytes  (length prefix + UTF-8 byte capacity)
    slot_size  = 4 + sum(field bytes)
    slot k of a block starts at byte  k * slot_size
    slots per block = block_size // slot_size   (leftover bytes are waste)

    Worked example — students(id int, name varchar(8), gpa int):
        flag@0  id@4  name@8 (12 bytes)  gpa@20   →  slot_size = 24

PIN DISCIPLINE (week 2's contract, honored here):
    RecordPage pins its block on construction and unpins on close().
    TableScan keeps exactly ONE block pinned at a time — moving to the
    next block closes (unpins) the previous RecordPage first.

Run the tests any time:   python3 test_records.py
Run the measurement:      python3 measure_layout.py    (after tests pass)
"""

from __future__ import annotations

from file_manager import BlockId, FileManager
from buffer_manager import BufferManager

INT, STR = "int", "varchar"
EMPTY, USED = 0, 1


class Schema:
    """Field names, types, and varchar capacities. Provided complete."""

    def __init__(self):
        self._fields: list[tuple[str, str, int]] = []   # (name, type, length)

    def add_int_field(self, name: str) -> "Schema":
        self._fields.append((name, INT, 0))
        return self

    def add_string_field(self, name: str, max_chars: int) -> "Schema":
        self._fields.append((name, STR, max_chars))
        return self

    def fields(self) -> list[str]:
        return [f[0] for f in self._fields]

    def type_of(self, name: str) -> str:
        return next(f[1] for f in self._fields if f[0] == name)

    def length_of(self, name: str) -> int:
        return next(f[2] for f in self._fields if f[0] == name)


class Layout:
    """Maps a Schema to byte offsets inside a slot."""

    def __init__(self, schema: Schema):
        self.schema = schema
        self._offsets: dict[str, int] = {}
        self.slot_size = 0
        position = 4
        for field in schema.fields():
            self._offsets[field] = position
            if schema.type_of(field) == INT:
                position += 4
            elif schema.type_of(field) == STR:
                position += 4 + schema.length_of(field)
        self.slot_size = position

        # ---------------- YOUR JOB ends here. ----------------

    @classmethod
    def from_metadata(cls, schema: Schema, offsets: dict[str, int],
                      slot_size: int) -> "Layout":
        """Rebuild a Layout from stored catalog rows (skips __init__)."""
        lay = cls.__new__(cls)
        lay.schema = schema
        lay._offsets = dict(offsets)
        lay.slot_size = slot_size
        return lay

    def offset(self, name: str) -> int:
        return self._offsets[name]


class RecordPage:
    """Slotted records within ONE block, accessed through the buffer pool."""

    def __init__(self, bm: BufferManager, block: BlockId, layout: Layout):
        self.bm = bm
        self.block = block
        self.layout = layout
        self._buf = bm.pin(block)                      # pinned until close()

    def slot_count(self) -> int:
        return self.bm.fm.block_size // self.layout.slot_size

    def close(self) -> None:
        self.bm.unpin(self._buf)

    # ---- flag plumbing (provided) ----

    def _slot_pos(self, slot: int) -> int:
        return slot * self.layout.slot_size

    def is_used(self, slot: int) -> bool:
        return self._buf.contents().get_int(self._slot_pos(slot)) == USED

    def _set_flag(self, slot: int, flag: int) -> None:
        self._buf.contents().set_int(self._slot_pos(slot), flag)
        self._buf.set_modified()

    # ---------------- YOUR JOB starts here. ----------------

    def _field_pos(self, slot: int, fldname: str) -> int:
        """Absolute byte position of `fldname` inside `slot`."""
        # The field's position is the start of the slot + that field's offset
        return slot * self.layout.slot_size + self.layout.offset(fldname)

    def get_int(self, slot: int, fldname: str) -> int:
        pos = self._field_pos(slot, fldname)
        return self._buf.contents().get_int(pos)

    def set_int(self, slot: int, fldname: str, val: int) -> None:
        pos = self._field_pos(slot, fldname)
        self._buf.contents().set_int(pos, val)
        self._buf.set_modified()

    def get_string(self, slot: int, fldname: str) -> str:
        pos = self._field_pos(slot, fldname)
        return self._buf.contents().get_string(pos)

    def set_string(self, slot: int, fldname: str, val: str) -> None:
        # Reject if the encoded string is too long for the field
        maxlen = self.layout.schema.length_of(fldname)
        actual_len = len(val.encode("utf-8"))
        if actual_len > maxlen:
            raise ValueError(f"String too long for field '{fldname}': {actual_len} > {maxlen}")
        pos = self._field_pos(slot, fldname)
        self._buf.contents().set_string(pos, val)
        self._buf.set_modified()
 

    def insert_after(self, slot: int) -> int:
        """Find the first EMPTY slot with index > `slot`, mark it USED,
        and return its index. Return -1 if this block has none."""
        for i in range(slot + 1, self.slot_count()):
            if not self.is_used(i):
                self._set_flag(i, USED)
                return i
        return -1

    def next_after(self, slot: int) -> int:
        """Find the first USED slot with index > `slot`; -1 if none.
        (insert_after's read-only twin — the scan's stepping stone.)"""
        for i in range(slot + 1, self.slot_count()):
            if self.is_used(i):
                return i
        return -1

    def delete(self, slot: int) -> None:
        """Deletion is a bit flip: mark the slot EMPTY. Nothing moves."""
        self._set_flag(slot, EMPTY)


    # ---------------- YOUR JOB ends here. ----------------


class TableScan:
    """Iterate over every record of a table, one pinned block at a time.

    Usage:   ts = TableScan(bm, fm, "students", layout)
             ts.before_first()
             while ts.next():
                 print(ts.get_int("id"), ts.get_string("name"))
             ts.close()
    """

    def __init__(self, bm: BufferManager, fm: FileManager,
                 tblname: str, layout: Layout):
        self.bm = bm
        self.fm = fm
        self.filename = tblname + ".tbl"
        self.layout = layout
        self.rp: RecordPage | None = None
        if fm.length(self.filename) == 0:
            fm.append(self.filename)                   # zeroed = all EMPTY
        self._move_to_block(0)

    # ---- plumbing (provided) ----

    def _move_to_block(self, blknum: int) -> None:
        if self.rp is not None:
            self.rp.close()                            # unpin before moving on
        self.rp = RecordPage(self.bm, BlockId(self.filename, blknum), self.layout)
        self.current_slot = -1

    def _at_last_block(self) -> bool:
        return self.rp.block.blknum == self.fm.length(self.filename) - 1

    def _append_new_block(self) -> None:
        blk = self.fm.append(self.filename)            # fresh zeroed block
        self._move_to_block(blk.blknum)

    def before_first(self) -> None:
        self._move_to_block(0)

    def close(self) -> None:
        if self.rp is not None:
            self.rp.close()
            self.rp = None

    # current-row accessors (provided) — valid after next() or insert()
    def get_int(self, fld: str) -> int: return self.rp.get_int(self.current_slot, fld)
    def get_string(self, fld: str) -> str: return self.rp.get_string(self.current_slot, fld)
    def set_int(self, fld: str, v: int) -> None: self.rp.set_int(self.current_slot, fld, v)
    def set_string(self, fld: str, v: str) -> None: self.rp.set_string(self.current_slot, fld, v)
    def delete(self) -> None: self.rp.delete(self.current_slot)
    def rid(self) -> tuple[int, int]: return (self.rp.block.blknum, self.current_slot)

    # ---------------- YOUR JOB starts here. ----------------

    def next(self) -> bool:
        """Advance to the next USED record, crossing block boundaries.
        Return True positioned on a record, or False past the last one.

        Sketch: ask the current RecordPage for next_after(current_slot).
        While it says -1: if this is the last block, return False;
        otherwise move to the next block and ask again from slot -1."""
        # TODO
        self.current_slot = self.rp.next_after(self.current_slot)
        while self.current_slot < 0:
            if self._at_last_block():
                return False
            self._move_to_block(self.rp.block.blknum + 1)
            self.current_slot = self.rp.next_after(-1)
        return True

    def insert(self) -> None:
        """Move to a fresh USED slot, extending the file if every block is
        full. After this, the set_* methods write the new record's fields.

        Sketch: try insert_after(current_slot) on the current page. While
        it says -1: move to the next block — or append a brand-new zeroed
        block if this was the last — and try again from slot -1."""
        # TODO
        slot = self.rp.insert_after(self.current_slot)
        while slot < 0:
            if self._at_last_block():
                self._append_new_block()
            else:
                self._move_to_block(self.rp.block.blknum + 1)
            slot = self.rp.insert_after(-1)
        self.current_slot = slot

    # ---------------- YOUR JOB ends here. ----------------
