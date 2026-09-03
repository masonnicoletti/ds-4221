"""microdb · part 2 — the buffer manager.

Lab 2 of Advanced Databases for Data Science (DS 6XXX, Fall 2026).
Runs on top of Lab 1's file manager (a reference implementation ships in
this folder — use it even if your own Lab 1 passed, so everyone's layer 1
behaves identically).

The buffer manager owns a fixed pool of memory frames (Buffer objects),
each able to hold one disk block. All page access now goes through it:

    buf = bm.pin(BlockId("students.tbl", 0))   # block is now in memory
    buf.contents().get_int(0)                   # read through the buffer
    buf.contents().set_int(0, 99)               # write through the buffer
    buf.set_modified()                          # tell the pool it's dirty
    bm.unpin(buf)                               # done — eviction allowed

THE CONTRACT (what every later lab relies on):

    pin(block)   returns a Buffer holding that block. A hit if the block is
                 already in some frame; otherwise a miss: choose a victim
                 frame (unpinned, least recently used), flush it if dirty,
                 and read the requested block into it. If every frame is
                 pinned, raise BufferAbortError.
    unpin(buf)   decrements the pin count. A frame may be evicted only
                 when its pin count is 0.
    LRU SPEC     every successful pin sets buffer.last_used to a fresh
                 tick from self._tick (a monotonically increasing int).
                 The victim is the UNPINNED frame with the SMALLEST
                 last_used. Never evict a pinned frame.
    dirty pages  a frame whose page was modified (set_modified) must be
                 written back to disk before its frame is reused.

Run the tests any time:   python3 test_buffermanager.py
Run the measurement:      python3 measure_hits.py     (after tests pass)
"""

from __future__ import annotations

from file_manager import BlockId, Page, FileManager


class BufferAbortError(Exception):
    """Raised by pin() when every frame in the pool is pinned."""


class Buffer:
    """One frame of the pool: a page, plus bookkeeping. Provided complete."""

    def __init__(self, fm: FileManager):
        self._fm = fm
        self.page = Page(fm.block_size)
        self.block: BlockId | None = None   # which disk block this frame holds
        self.pins = 0                       # >0 means in use; never evict
        self.dirty = False                  # page modified since load?
        self.last_used = 0                  # tick of the most recent pin

    def contents(self) -> Page:
        return self.page

    def is_pinned(self) -> bool:
        return self.pins > 0

    def set_modified(self) -> None:
        """Callers must invoke this after writing to contents()."""
        self.dirty = True

    def flush(self) -> None:
        """Write this frame back to disk if it holds modified data."""
        if self.dirty and self.block is not None:
            self._fm.write(self.block, self.page)
            self.dirty = False

    def assign_to_block(self, block: BlockId) -> None:
        """Point this frame at `block`: flush the old contents if dirty,
        then read the new block from disk. Provided for you — pin() should
        call it on the chosen victim."""
        self.flush()
        self._fm.read(block, self.page)
        self.block = block
        self.dirty = False

    def __repr__(self):
        return f"Buffer({self.block}, pins={self.pins}, dirty={self.dirty})"


class BufferManager:
    """A fixed pool of Buffers with LRU replacement. You implement the
    four methods marked YOUR JOB; everything they need exists above."""

    def __init__(self, fm: FileManager, num_buffers: int):
        self.fm = fm
        self.pool = [Buffer(fm) for _ in range(num_buffers)]
        self.hits = 0
        self.misses = 0
        self._tick = 0          # monotonic clock for the LRU spec

    # ---------------- YOUR JOB starts here. ----------------

    def _find_existing(self, block: BlockId):
        """Return the Buffer already holding `block`, or None."""
        # TODO: scan self.pool comparing buffer.block to block.
        raise NotImplementedError

    def _choose_victim(self):
        """Return the unpinned Buffer with the smallest last_used,
        or None if every frame is pinned."""
        # TODO: filter unpinned frames; min() by last_used.
        raise NotImplementedError

    def pin(self, block: BlockId) -> Buffer:
        """Make `block` resident and pinned; return its Buffer.

        Hit:  the block is already in a frame -> count a hit.
        Miss: choose a victim (raise BufferAbortError if none), load the
              block into it with assign_to_block, count a miss.
        Either way: increment the frame's pins and stamp last_used with a
        fresh tick (increment self._tick first, then assign it)."""
        # TODO: implement exactly the spec above — the tests check the
        #       hit/miss counters and the LRU order.
        raise NotImplementedError

    def unpin(self, buf: Buffer) -> None:
        """Release one pin on `buf`. Raise ValueError if pins is already 0
        (that's always a caller bug worth catching loudly)."""
        # TODO
        raise NotImplementedError

    # ---------------- YOUR JOB ends here. ----------------

    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def flush_all(self) -> None:
        """Write every dirty frame back to disk (used at shutdown)."""
        for b in self.pool:
            b.flush()
