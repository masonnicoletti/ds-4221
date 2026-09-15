"""microdb · part 3 — records, slots, and the table scan. REFERENCE IMPLEMENTATION.

Shipped with Lab 4. Do not edit — but DO read the two methods added at the
bottom of TableScan for this lab: get_val() and has_field() let every query
operator treat a TableScan exactly like any other scan.

Slot layout: [4-byte in-use flag][field bytes, schema order].
int = 4 bytes; varchar(n) = 4 + n bytes. slot k starts at k * slot_size.
"""

from __future__ import annotations

from file_manager import BlockId, FileManager
from buffer_manager import BufferManager

INT, STR = "int", "varchar"
EMPTY, USED = 0, 1


class Schema:
    def __init__(self):
        self._fields: list[tuple[str, str, int]] = []

    def add_int_field(self, name: str) -> "Schema":
        self._fields.append((name, INT, 0))
        return self

    def add_string_field(self, name: str, max_chars: int) -> "Schema":
        """Reserve max_chars UTF-8 bytes (parameter name retained for the lab API)."""
        self._fields.append((name, STR, max_chars))
        return self

    def fields(self) -> list[str]:
        return [f[0] for f in self._fields]

    def type_of(self, name: str) -> str:
        return next(f[1] for f in self._fields if f[0] == name)

    def length_of(self, name: str) -> int:
        return next(f[2] for f in self._fields if f[0] == name)


class Layout:
    def __init__(self, schema: Schema):
        self.schema = schema
        self._offsets: dict[str, int] = {}
        pos = 4                                        # bytes [0,4) = in-use flag
        for name in schema.fields():
            self._offsets[name] = pos
            if schema.type_of(name) == INT:
                pos += 4
            else:
                pos += 4 + schema.length_of(name)
        self.slot_size = pos

    @classmethod
    def from_metadata(cls, schema: Schema, offsets: dict[str, int],
                      slot_size: int) -> "Layout":
        lay = cls.__new__(cls)
        lay.schema = schema
        lay._offsets = dict(offsets)
        lay.slot_size = slot_size
        return lay

    def offset(self, name: str) -> int:
        return self._offsets[name]


class RecordPage:
    def __init__(self, bm: BufferManager, block: BlockId, layout: Layout):
        self.bm = bm
        self.block = block
        self.layout = layout
        self._buf = bm.pin(block)

    def slot_count(self) -> int:
        return self.bm.fm.block_size // self.layout.slot_size

    def close(self) -> None:
        self.bm.unpin(self._buf)

    def _slot_pos(self, slot: int) -> int:
        return slot * self.layout.slot_size

    def is_used(self, slot: int) -> bool:
        return self._buf.contents().get_int(self._slot_pos(slot)) == USED

    def _set_flag(self, slot: int, flag: int) -> None:
        self._buf.contents().set_int(self._slot_pos(slot), flag)
        self._buf.set_modified()

    def _field_pos(self, slot: int, fldname: str) -> int:
        return self._slot_pos(slot) + self.layout.offset(fldname)

    def get_int(self, slot: int, fldname: str) -> int:
        return self._buf.contents().get_int(self._field_pos(slot, fldname))

    def set_int(self, slot: int, fldname: str, val: int) -> None:
        self._buf.contents().set_int(self._field_pos(slot, fldname), val)
        self._buf.set_modified()

    def get_string(self, slot: int, fldname: str) -> str:
        return self._buf.contents().get_string(self._field_pos(slot, fldname))

    def set_string(self, slot: int, fldname: str, val: str) -> None:
        if len(val.encode("utf-8")) > self.layout.schema.length_of(fldname):
            raise ValueError(f"UTF-8 value exceeds capacity of {fldname!r}")
        self._buf.contents().set_string(self._field_pos(slot, fldname), val)
        self._buf.set_modified()

    def insert_after(self, slot: int) -> int:
        for s in range(slot + 1, self.slot_count()):
            if not self.is_used(s):
                self._set_flag(s, USED)
                return s
        return -1

    def next_after(self, slot: int) -> int:
        for s in range(slot + 1, self.slot_count()):
            if self.is_used(s):
                return s
        return -1

    def delete(self, slot: int) -> None:
        self._set_flag(slot, EMPTY)


class TableScan:
    def __init__(self, bm: BufferManager, fm: FileManager,
                 tblname: str, layout: Layout):
        self.bm = bm
        self.fm = fm
        self.filename = tblname + ".tbl"
        self.layout = layout
        self.rp: RecordPage | None = None
        if fm.length(self.filename) == 0:
            fm.append(self.filename)
        self._move_to_block(0)

    def _move_to_block(self, blknum: int) -> None:
        if self.rp is not None:
            self.rp.close()
        self.rp = RecordPage(self.bm, BlockId(self.filename, blknum), self.layout)
        self.current_slot = -1

    def _at_last_block(self) -> bool:
        return self.rp.block.blknum == self.fm.length(self.filename) - 1

    def _append_new_block(self) -> None:
        blk = self.fm.append(self.filename)
        self._move_to_block(blk.blknum)

    def before_first(self) -> None:
        self._move_to_block(0)

    def close(self) -> None:
        if self.rp is not None:
            self.rp.close()
            self.rp = None

    def get_int(self, fld: str) -> int: return self.rp.get_int(self.current_slot, fld)
    def get_string(self, fld: str) -> str: return self.rp.get_string(self.current_slot, fld)
    def set_int(self, fld: str, v: int) -> None: self.rp.set_int(self.current_slot, fld, v)
    def set_string(self, fld: str, v: str) -> None: self.rp.set_string(self.current_slot, fld, v)
    def delete(self) -> None: self.rp.delete(self.current_slot)
    def rid(self) -> tuple[int, int]: return (self.rp.block.blknum, self.current_slot)

    def next(self) -> bool:
        self.current_slot = self.rp.next_after(self.current_slot)
        while self.current_slot < 0:
            if self._at_last_block():
                return False
            self._move_to_block(self.rp.block.blknum + 1)
            self.current_slot = self.rp.next_after(-1)
        return True

    def insert(self) -> None:
        slot = self.rp.insert_after(self.current_slot)
        while slot < 0:
            if self._at_last_block():
                self._append_new_block()
            else:
                self._move_to_block(self.rp.block.blknum + 1)
            slot = self.rp.insert_after(-1)
        self.current_slot = slot

    # ---- added for Lab 4: the uniform scan interface ----

    def get_val(self, fld: str):
        """Schema-aware read: int fields via get_int, strings via get_string."""
        if self.layout.schema.type_of(fld) == INT:
            return self.get_int(fld)
        return self.get_string(fld)

    def has_field(self, fld: str) -> bool:
        return fld in self.layout.schema.fields()
