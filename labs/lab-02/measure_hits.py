"""Lab 2, Part 3 — measure the hit rate. Run:  python3 measure_hits.py

Two workloads over a 50-block file, at several pool sizes:

    scan     two full sequential passes over all 50 blocks — the classic
             analytics access pattern
    hot set  2,000 accesses where 90% go to 5 "hot" blocks and 10% are
             spread uniformly — the classic transactional pattern

Note the hit rates for class. Before running, predict: with a
49-frame pool and a 50-block file, what hit rate does the scan get?
"""

import random
import shutil
import tempfile

from file_manager import BlockId, Page, FileManager
from buffer_manager import BufferManager

BLOCK_SIZE = 128
FILE_BLOCKS = 50
POOL_SIZES = [5, 10, 25, 45, 49, 50, 55]


def build_file(d):
    fm = FileManager(d, BLOCK_SIZE)
    for k in range(FILE_BLOCKS):
        blk = fm.append("t.tbl")
        p = Page(BLOCK_SIZE)
        p.set_int(0, k)
        fm.write(blk, p, sync=False)
    return fm


def run(bm, blocks):
    for k in blocks:
        buf = bm.pin(BlockId("t.tbl", k))
        bm.unpin(buf)
    return bm.hit_rate()


def scan_workload():
    return list(range(FILE_BLOCKS)) * 2


def hotset_workload():
    rng = random.Random(6042)               # seeded: everyone sees the same numbers
    hot = list(range(5))
    out = []
    for _ in range(2000):
        if rng.random() < 0.9:
            out.append(rng.choice(hot))
        else:
            out.append(rng.randrange(FILE_BLOCKS))
    return out


def main():
    d = tempfile.mkdtemp(prefix="microdb-hits-")
    try:
        fm = build_file(d)
        scan, hot = scan_workload(), hotset_workload()
        print(f"{'pool size':>10} | {'scan hit rate':>14} | {'hot-set hit rate':>16}")
        print("-" * 48)
        for n in POOL_SIZES:
            r_scan = run(BufferManager(fm, n), scan)
            r_hot = run(BufferManager(fm, n), hot)
            print(f"{n:>10} | {r_scan:>13.1%} | {r_hot:>15.1%}")
        fm.close()
        print("\nRecord the table, then think about these for class:")
        print("  1. Why does the scan get ~0% until the pool fits the WHOLE file?")
        print("  2. Why does the hot set do fine with a pool a tenth that size?")
        print("  3. Which workload is your ML feature pipeline?")
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    main()
