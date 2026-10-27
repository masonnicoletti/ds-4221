"""Lab 9 test harness — run:  python3 test_vector.py

Three groups, mirroring the lab page:

    EXACT — brute force finds the true neighbors (checked against a
            slow-but-obviously-right reference)
    IVF   — build assigns every vector once; probing works
    QUALITY — recall@10 clears the bar at probe 4, and comparisons
              actually drop vs brute force (the whole point)

Pure stdlib. The Gradescope autograder runs this same harness.

    python3 test_vector.py --list
    python3 test_vector.py --unit IVFIndex.search
    python3 test_vector.py --unit

Unit checks use tiny fixtures, so other methods can remain TODOs. Run the
command without options to check the complete pipeline on the real data.
"""

import argparse
import sys
import traceback
from unittest.mock import patch

from microvector import (BruteForceIndex, IVFIndex, dot, normalize,
                         recall_at_k)
import gen_embeddings

RESULTS = []
VERBOSE = False
_INTEGRATION_LOADED = False


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
            if VERBOSE:
                traceback.print_exc()


def expect(cond, why):
    if not cond:
        raise AssertionError(why)


def load_integration():
    """Load real data once, including when an individual test is imported."""
    global _INTEGRATION_LOADED, VECTORS, QUERIES
    if not _INTEGRATION_LOADED:
        vectors = gen_embeddings.load()
        queries = gen_embeddings.queries(vectors, n=10)
        VECTORS, QUERIES = vectors, queries
        _INTEGRATION_LOADED = True


def slow_truth(query, k):
    load_integration()
    scored = sorted(((dot(query, v), i) for i, v in enumerate(VECTORS)),
                    key=lambda t: (-t[0], t[1]))
    return scored[:k]


# ---------------- EXACT group ----------------

def test_brute_force_matches_truth():
    load_integration()
    idx = BruteForceIndex(VECTORS)
    for q in QUERIES[:3]:
        got = idx.search(q, 10)
        want = slow_truth(q, 10)
        expect([i for _, i in got] == [i for _, i in want],
               f"top-10 ids differ from the obviously-right reference: "
               f"{[i for _, i in got][:5]} vs {[i for _, i in want][:5]}")


def test_brute_force_counts():
    load_integration()
    idx = BruteForceIndex(VECTORS)
    idx.search(QUERIES[0], 5)
    expect(idx.comparisons == len(VECTORS),
           f"one exact search must compare against all {len(VECTORS)} vectors, "
           f"counted {idx.comparisons}")


def test_self_is_nearest():
    load_integration()
    idx = BruteForceIndex(VECTORS)
    sims = idx.search(VECTORS[123], 1)
    expect(sims[0][1] == 123, "a vector's nearest neighbor is itself")
    expect(abs(sims[0][0] - 1.0) < 1e-6, "…with similarity 1.0 (unit vectors)")


# ---------------- IVF group ----------------

def test_build_assigns_everything_once():
    load_integration()
    idx = IVFIndex(VECTORS, n_clusters=20)
    assigned = sorted(i for lst in idx.lists for i in lst)
    expect(assigned == list(range(len(VECTORS))),
           f"every vector id must appear in exactly one list "
           f"(got {len(assigned)} assignments)")


def test_probe_more_finds_more():
    load_integration()
    idx = IVFIndex(VECTORS, n_clusters=20)
    q = QUERIES[1]
    exact = slow_truth(q, 10)
    r1 = recall_at_k(idx.search(q, 10, probe=1), exact, 10)
    r8 = recall_at_k(idx.search(q, 10, probe=8), exact, 10)
    expect(r8 >= r1, f"probing more lists must not lower recall ({r1} -> {r8})")
    expect(r8 >= 0.8, f"probe=8 of 20 lists should find most of the truth, recall {r8}")


# ---------------- QUALITY group ----------------

def test_recall_bar():
    load_integration()
    idx = IVFIndex(VECTORS, n_clusters=20)
    total = 0.0
    for q in QUERIES:
        total += recall_at_k(idx.search(q, 10, probe=4), slow_truth(q, 10), 10)
    avg = total / len(QUERIES)
    expect(avg >= 0.75,
           f"average recall@10 at probe=4 should clear 0.75 on this data, got {avg:.2f}")


def test_comparisons_drop():
    load_integration()
    bf = BruteForceIndex(VECTORS)
    bf.search(QUERIES[0], 10)
    ivf = IVFIndex(VECTORS, n_clusters=20)
    ivf.comparisons = 0
    ivf.search(QUERIES[0], 10, probe=4)
    expect(ivf.comparisons < bf.comparisons / 2,
           f"IVF at probe=4 must do less than half the work "
           f"({ivf.comparisons} vs {bf.comparisons}) — are you searching "
           f"only the probed lists?")


# ---------------- isolated function checks (ungraded) ----------------
# These fixtures set up index state directly. They never replace the method
# under test, so a passing result belongs to the student's implementation.

def unit_brute_force_search():
    vectors = [[1.0, 0.0], [0.0, 1.0], [1.0, 0.0], [-1.0, 0.0]]
    idx = BruteForceIndex(vectors)
    for query, k in (([1.0, 0.0], 2), ([0.0, 1.0], 9), ([-1.0, 0.0], 1)):
        before = idx.comparisons
        want = sorted(((dot(query, v), i) for i, v in enumerate(vectors)),
                      key=lambda pair: (-pair[0], pair[1]))[:k]
        expect(idx.search(query, k) == want,
               "return (score, id) pairs sorted by score descending, then id ascending")
        expect(idx.comparisons - before == len(vectors),
               "count every vector comparison, including repeated searches")
    expect(BruteForceIndex([]).search([1.0, 0.0], 3) == [],
           "an empty index has no neighbors")


def fixture_ivf():
    """Ready-to-build state; skips __init__ so _build can still be a TODO."""
    idx = IVFIndex.__new__(IVFIndex)
    idx.vectors = [[1.0, 0.0], [0.0, 1.0], [1.0, 0.0],
                   normalize([0.2, 0.9]), [-1.0, 0.0], normalize([0.9, -0.1])]
    idx.centroids = [[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]]
    idx.lists = [[], [], []]
    idx.comparisons = 0
    return idx


def fixture_exact_search(self, query, k):
    """Completed sibling for IVF implementations that reuse exact search."""
    self.comparisons += len(self.vectors)
    return sorted(((dot(query, v), i) for i, v in enumerate(self.vectors)),
                  key=lambda pair: (-pair[0], pair[1]))[:k]


@patch.object(BruteForceIndex, "search", fixture_exact_search)
def unit_ivf_build():
    idx = fixture_ivf()
    idx._build()                         # the student's method, unchanged
    expect(len(idx.lists) == len(idx.centroids), "keep one list per centroid")
    assigned = sorted(i for bucket in idx.lists for i in bucket)
    expect(assigned == list(range(len(idx.vectors))), "assign every vector exactly once")
    for c, bucket in enumerate(idx.lists):
        for i in bucket:
            scores = [dot(idx.vectors[i], centroid) for centroid in idx.centroids]
            expect(scores[c] == max(scores), "assign each vector to its nearest centroid")


@patch.object(BruteForceIndex, "search", fixture_exact_search)
def unit_ivf_search():
    idx = fixture_ivf()
    idx.lists = [[0, 2, 5], [1, 3], [4]]  # supplied build result, independent of _build
    for query, probe, k in (([1.0, 0.0], 1, 2), ([1.0, 0.0], 2, 9),
                            ([-1.0, 0.0], 1, 9), ([0.0, 1.0], 3, 4)):
        nearest = sorted(range(3), key=lambda c: (-dot(query, idx.centroids[c]), c))[:probe]
        ids = [i for c in nearest for i in idx.lists[c]]
        want = sorted(((dot(query, idx.vectors[i]), i) for i in ids),
                      key=lambda pair: (-pair[0], pair[1]))[:k]
        before = idx.comparisons
        expect(idx.search(query, k, probe=probe) == want,
               "search only the nearest probed lists; sort scores descending and tied ids ascending")
        expect(idx.comparisons - before == len(idx.centroids) + len(ids),
               "count centroid comparisons and candidate comparisons on every search")
    idx.lists = [[], [], []]
    expect(idx.search([1.0, 0.0], 3, probe=1) == [], "empty probed lists return no neighbors")


UNIT_TESTS = {
    "BruteForceIndex.search": unit_brute_force_search,
    "IVFIndex._build": unit_ivf_build,
    "IVFIndex.search": unit_ivf_search,
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list function targets and exit")
    parser.add_argument("--unit", nargs="?", const="all", choices=["all", *UNIT_TESTS],
                        metavar="TARGET", help="test one function, or all functions independently")
    parser.add_argument("-v", action="store_true", help="show failure tracebacks")
    args = parser.parse_args(argv)
    global VERBOSE
    VERBOSE = args.v
    if args.list:
        print("\n".join(UNIT_TESTS))
        return 0
    RESULTS.clear()
    if args.unit:
        print("UNIT checks — supplied index state isolates each function; these are not grading checks")
        selected = UNIT_TESTS if args.unit == "all" else {args.unit: UNIT_TESTS[args.unit]}
        for name, fn in selected.items():
            check("UNIT", name, fn)
    else:
        load_integration()
        integration_tests()
    n = sum(RESULTS)
    summary = "unit checks passed (not the grading score)" if args.unit else "tests passed"
    print(f"\n{n}/{len(RESULTS)} {summary}")
    return 0 if n == len(RESULTS) else 1


def integration_tests():
    print("EXACT group")
    check("EXACT", "brute force matches the reference",       test_brute_force_matches_truth)
    check("EXACT", "one search compares against everything",  test_brute_force_counts)
    check("EXACT", "a vector's nearest neighbor is itself",   test_self_is_nearest)
    print("IVF group")
    check("IVF", "build assigns every vector exactly once",   test_build_assigns_everything_once)
    check("IVF", "probing more lists never hurts recall",     test_probe_more_finds_more)
    print("QUALITY group")
    check("QUALITY", "recall@10 >= 0.75 at probe 4",          test_recall_bar)
    check("QUALITY", "comparisons drop by more than half",    test_comparisons_drop)


if __name__ == "__main__":
    sys.exit(main())
