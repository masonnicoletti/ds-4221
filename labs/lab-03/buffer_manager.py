"""microdb · part 2 — the buffer manager. REFERENCE IMPLEMENTATION.

Shipped with Lab 3 so every lower layer behaves identically. Do not edit."""

from __future__ import annotations

from file_manager import BlockId, Page, FileManager


class BufferAbortError(Exception):
    """Raised by pin() when every frame in the pool is pinned."""


class Buffer:
    """One frame of the pool: a page, plus bookkeeping."""

    def __init__(self, fm: FileManager):
        self._fm = fm
        self.page = Page(fm.block_size)
        self.block: BlockId | None = None
        self.pins = 0
        self.dirty = False
        self.last_used = 0

    def contents(self) -> Page:
        return self.page

    def is_pinned(self) -> bool:
        return self.pins > 0

    def set_modified(self) -> None:
        self.dirty = True

    def flush(self) -> None:
        if self.dirty and self.block is not None:
            self._fm.write(self.block, self.page)
            self.dirty = False

    def assign_to_block(self, block: BlockId) -> None:
        self.flush()
        self._fm.read(block, self.page)
        self.block = block
        self.dirty = False

    def __repr__(self):
        return f"Buffer({self.block}, pins={self.pins}, dirty={self.dirty})"


class BufferManager:
    """A fixed pool of Buffers with LRU replacement."""

    def __init__(self, fm: FileManager, num_buffers: int):
        self.fm = fm
        self.pool = [Buffer(fm) for _ in range(num_buffers)]
        self.hits = 0
        self.misses = 0
        self._tick = 0

    def _find_existing(self, block: BlockId):
        for b in self.pool:
            if b.block == block:
                return b
        return None

    def _choose_victim(self):
        candidates = [b for b in self.pool if not b.is_pinned()]
        if not candidates:
            return None
        return min(candidates, key=lambda b: b.last_used)

    def pin(self, block: BlockId) -> Buffer:
        self._tick += 1
        buf = self._find_existing(block)
        if buf is not None:
            self.hits += 1
        else:
            buf = self._choose_victim()
            if buf is None:
                raise BufferAbortError(f"cannot pin {block}: every frame is pinned")
            self.misses += 1
            buf.assign_to_block(block)
        buf.pins += 1
        buf.last_used = self._tick
        return buf

    def unpin(self, buf: Buffer) -> None:
        if buf.pins <= 0:
            raise ValueError("unpin called on a frame with no pins (caller bug)")
        buf.pins -= 1

    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def flush_all(self) -> None:
        for b in self.pool:
            b.flush()
