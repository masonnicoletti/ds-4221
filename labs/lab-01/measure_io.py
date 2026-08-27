"""Lab 1, Part 3: measure what fsync costs. Run:  python3 measure_io.py

Writes the same 4 KB block over and over through your FileManager, two ways:

    sync=True    every write is flushed AND fsync'd. The OS must promise
                 the bytes are on durable storage before write() returns
    sync=False   every write goes to the OS page cache and returns

Note all three printed numbers for class. Your absolute numbers
will differ from your neighbor's (different SSDs, different laptops). The
RATIO is the lesson.
"""

import shutil
import tempfile
import time

from file_manager import Page, FileManager

BLOCK_SIZE = 4096
N_SYNC = 200        # fsync'd writes are slow, so keep the count modest
N_NOSYNC = 5000


def bench(fm, blk, page, n, sync):
    t0 = time.perf_counter()
    for _ in range(n):
        fm.write(blk, page, sync=sync)
    dt = time.perf_counter() - t0
    return n / dt


def main():
    d = tempfile.mkdtemp(prefix="microdb-bench-")
    try:
        fm = FileManager(d, BLOCK_SIZE)
        blk = fm.append("bench.tbl")
        page = Page(BLOCK_SIZE)
        page.set_string(0, "measure me")

        rate_nosync = bench(fm, blk, page, N_NOSYNC, sync=False)
        rate_sync = bench(fm, blk, page, N_SYNC, sync=True)
        fm.close()

        print(f"buffered writes (sync=False): {rate_nosync:12,.0f} blocks/sec")
        print(f"durable  writes (sync=True):  {rate_sync:12,.0f} blocks/sec")
        print(f"ratio (buffered / durable):   {rate_nosync / rate_sync:12,.1f}x")
        print("\nNote these three numbers, then think about these for class:")
        print("  if every microdb operation fsync'd every page it touched,")
        print("  how many row-updates/sec could the engine ever reach?")
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    main()
