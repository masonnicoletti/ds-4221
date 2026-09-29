"""microdb · part 1 — the disk & file layer. REFERENCE IMPLEMENTATION.

Shipped with Lab 6 so every lower layer behaves identically. Do not edit.

Byte-layout spec (the contract every later lab depends on):

    int     4 bytes, little-endian, signed          struct format '<i'
    bytes   4-byte length prefix (an int, as above), then the raw bytes
    string  UTF-8 encode, then store like bytes

    bytes needed for a string s:   4 + len(s.encode('utf-8'))
    byte range of block k on disk: [k * block_size, (k+1) * block_size)
"""

from __future__ import annotations

import os
import struct


class BlockId:
    """Names block number `blknum` of file `filename`. Immutable + hashable."""

    def __init__(self, filename: str, blknum: int):
        self.filename = filename
        self.blknum = blknum

    def __eq__(self, other):
        return (isinstance(other, BlockId)
                and self.filename == other.filename
                and self.blknum == other.blknum)

    def __hash__(self):
        return hash((self.filename, self.blknum))

    def __repr__(self):
        return f"BlockId({self.filename!r}, {self.blknum})"


class Page:
    """A block-sized region of memory with typed reads and writes."""

    def __init__(self, block_size: int):
        self._data = bytearray(block_size)

    def get_int(self, offset: int) -> int:
        return struct.unpack_from("<i", self._data, offset)[0]

    def set_int(self, offset: int, val: int) -> None:
        struct.pack_into("<i", self._data, offset, val)

    def get_bytes(self, offset: int) -> bytes:
        length = self.get_int(offset)
        start = offset + 4
        return bytes(self._data[start:start + length])

    def set_bytes(self, offset: int, data: bytes) -> None:
        self.set_int(offset, len(data))
        start = offset + 4
        self._data[start:start + len(data)] = data

    def get_string(self, offset: int) -> str:
        return self.get_bytes(offset).decode("utf-8")

    def set_string(self, offset: int, s: str) -> None:
        self.set_bytes(offset, s.encode("utf-8"))

    def contents(self) -> bytearray:
        return self._data


class FileManager:
    """Moves whole blocks between disk files and Pages."""

    def __init__(self, db_dir: str, block_size: int = 4096):
        self.db_dir = db_dir
        self.block_size = block_size
        self._files: dict = {}
        os.makedirs(db_dir, exist_ok=True)

    def _file(self, filename: str):
        f = self._files.get(filename)
        if f is None:
            path = os.path.join(self.db_dir, filename)
            if not os.path.exists(path):
                open(path, "wb").close()          # create empty, never truncate
            f = open(path, "r+b")
            self._files[filename] = f
        return f

    def read(self, block: BlockId, page: Page) -> None:
        if block.blknum >= self.length(block.filename):
            raise ValueError(
                f"block {block.blknum} is past the end of {block.filename!r} "
                f"({self.length(block.filename)} blocks)")
        f = self._file(block.filename)
        f.seek(block.blknum * self.block_size)
        data = f.read(self.block_size)
        page.contents()[:] = data.ljust(self.block_size, b"\x00")

    def write(self, block: BlockId, page: Page, sync: bool = True) -> None:
        f = self._file(block.filename)
        f.seek(block.blknum * self.block_size)
        f.write(page.contents())
        f.flush()
        if sync:
            os.fsync(f.fileno())

    def append(self, filename: str) -> BlockId:
        blknum = self.length(filename)
        f = self._file(filename)
        f.seek(blknum * self.block_size)
        f.write(bytes(self.block_size))
        f.flush()
        return BlockId(filename, blknum)

    def length(self, filename: str) -> int:
        f = self._file(filename)
        return os.fstat(f.fileno()).st_size // self.block_size

    def close(self) -> None:
        for f in self._files.values():
            f.close()
        self._files.clear()
