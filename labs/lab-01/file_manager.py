"""microdb · part 1: the disk & file layer.

Lab 1 of Advanced Databases for Data Science (DS 6XXX, Fall 2026).

This is the bottom of the engine: everything microdb ever stores lives in
ordinary files, read and written one fixed-size block at a time. Three
classes make up the whole layer:

    BlockId      names one block: (filename, block number). Immutable.
    Page         a block-sized bytearray with typed get/set methods.
    FileManager  moves whole blocks between disk files and Pages.

BYTE-LAYOUT SPEC (the contract every later lab depends on; do not change):

    int     4 bytes, little-endian, signed          struct format '<i'
    bytes   4-byte length prefix (an int, as above), then the raw bytes
    string  UTF-8 encode, then store like bytes

    bytes needed for a string s:   4 + len(s.encode('utf-8'))
    byte range of block k on disk: [k * block_size, (k+1) * block_size)

INTERFACES (stable across all seven microdb labs):

    BlockId(filename: str, blknum: int)         .filename  .blknum
    Page(block_size: int)                       .get_int(off) -> int
                                                .set_int(off, val)
                                                .get_bytes(off) -> bytes
                                                .set_bytes(off, data)
                                                .get_string(off) -> str
                                                .set_string(off, s)
                                                .contents() -> bytearray
    FileManager(db_dir: str, block_size: int = 4096)
                                                .block_size
                                                .read(block, page)
                                                .write(block, page, sync=True)
                                                .append(filename) -> BlockId
                                                .length(filename) -> int   # in blocks
                                                .close()

Run the tests any time:   python3 test_filemanager.py
Run the measurement:      python3 measure_io.py       (after tests pass)
"""

from __future__ import annotations

import os
import struct


class BlockId:
    """Names block number `blknum` of file `filename`. Immutable + hashable:
    in Lab 2 the buffer pool will use BlockIds as dictionary keys."""

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
    """A block-sized region of memory with typed reads and writes.

    The page does not know what file (if any) it came from. It is just
    bytes plus the layout rules in the module docstring."""

    def __init__(self, block_size: int):
        self._data = bytearray(block_size)

    # ---------------- YOUR JOB starts here. ----------------
    # Implement the six methods below. Use the struct module for ints
    # ('<i' = 4-byte little-endian signed) and the spec in the docstring
    # for bytes/strings. test_filemanager.py checks every one of them.

    def get_int(self, offset: int) -> int:
        """Read the 4-byte little-endian int stored at `offset`."""
        # TODO: struct.unpack_from is your friend.
        raise NotImplementedError

    def set_int(self, offset: int, val: int) -> None:
        """Write `val` as a 4-byte little-endian int at `offset`."""
        # TODO: struct.pack_into is your friend.
        raise NotImplementedError

    def get_bytes(self, offset: int) -> bytes:
        """Read the length-prefixed byte string stored at `offset`."""
        # TODO: read the 4-byte length first, then that many raw bytes.
        raise NotImplementedError

    def set_bytes(self, offset: int, data: bytes) -> None:
        """Write `data` at `offset` as a 4-byte length followed by the bytes."""
        # TODO: length prefix, then the payload.
        raise NotImplementedError

    def get_string(self, offset: int) -> str:
        """Read the UTF-8 string stored at `offset`."""
        # TODO: one line once get_bytes works.
        raise NotImplementedError

    def set_string(self, offset: int, s: str) -> None:
        """Write `s` at `offset`: UTF-8 encode, then store like bytes."""
        # TODO: one line once set_bytes works.
        raise NotImplementedError

    # ---------------- YOUR JOB ends here. ----------------

    def contents(self) -> bytearray:
        """The raw underlying bytes (FileManager reads/writes these)."""
        return self._data


class FileManager:
    """Moves whole blocks between disk files and Pages.

    All files live inside `db_dir` (created if missing). File handles are
    opened on first use and cached in self._files until close()."""

    def __init__(self, db_dir: str, block_size: int = 4096):
        self.db_dir = db_dir
        self.block_size = block_size
        self._files: dict = {}
        os.makedirs(db_dir, exist_ok=True)

    def _file(self, filename: str):
        """Return the cached open file object for `filename`, opening
        (and creating on disk if necessary) on first use. Provided for you.
        Note the two-step create: 'w+b' would truncate an existing file."""
        f = self._files.get(filename)
        if f is None:
            path = os.path.join(self.db_dir, filename)
            if not os.path.exists(path):
                open(path, "wb").close()          # create empty, never truncate
            f = open(path, "r+b")
            self._files[filename] = f
        return f

    # ---------------- YOUR JOB starts here. ----------------
    #
    # Delete the `raise NotImplementedError` line when you fill in a
    # method. If it stays, the method does its work and then raises
    # anyway, and the harness reports "not implemented yet" for every
    # test that touches it.

    def read(self, block: BlockId, page: Page) -> None:
        """Fill `page` with the contents of `block` on disk.

        Raise ValueError if `block.blknum` is past the end of the file
        (i.e. >= self.length(block.filename))."""
        # TODO: bounds-check, seek to the block's byte offset, read
        #       block_size bytes into page.contents().
        #
        # Three mistakes that each cost a classmate an hour:
        #   1. Do the bounds check FIRST, before you seek. length() moves
        #      the cursor to the end of the file, so a seek that happens
        #      before it is silently undone.
        #   2. Compare block NUMBERS (block.blknum >= self.length(...)),
        #      not f.tell() against the file size. After reading the last
        #      valid block, tell() equals the file size, so that check
        #      raises on a perfectly good read.
        #   3. f.read(n) takes a byte COUNT, not a buffer. To fill the
        #      buffer the page already owns, use f.readinto(page.contents()).
        raise NotImplementedError

    def write(self, block: BlockId, page: Page, sync: bool = True) -> None:
        """Write `page` to `block` on disk.

        If `sync` is true, force the bytes to durable storage before
        returning (flush + os.fsync). This is the expensive promise you
        will measure in Part 3."""
        # TODO: seek, write page.contents(), flush, and fsync when sync.
        raise NotImplementedError

    def append(self, filename: str) -> BlockId:
        """Grow `filename` by one zeroed block; return the new block's BlockId."""
        # TODO: the new block number is the current length in blocks.
        #       Then actually grow the file: seek to the end, write
        #       block_size zero bytes (bytes(self.block_size)), and flush.
        #       Returning a BlockId by itself changes nothing on disk, and
        #       length() will still say 0.
        raise NotImplementedError

    def length(self, filename: str) -> int:
        """How many whole blocks `filename` currently holds."""
        # TODO: file size in bytes // block_size. os.fstat of the open
        #       file (or f.seek(0, 2); f.tell()) gives the size.
        raise NotImplementedError

    # ---------------- YOUR JOB ends here. ----------------

    def close(self) -> None:
        """Close every cached file handle (used by tests to reopen fresh)."""
        for f in self._files.values():
            f.close()
        self._files.clear()
