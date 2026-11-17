"""Legacy Lab 11 practice checks — run: python3 test_sparkray.py

Three groups, one per part:

    OFFLINE — Part A's micro-mapreduce, pure stdlib, always runs
    SPARK   — Part B, runs only if pyspark + Java are installed
    RAY     — Part C, runs only if ray is installed

Skipped groups print [SKIP] and do not count toward the practice total.
These MapReduce, Spark, and neighbor-search exercises are ungraded.
The required Ray image assignment uses test_ray_images.py instead.

    python3 test_sparkray.py --list
    python3 test_sparkray.py --unit shuffle
    python3 test_sparkray.py --unit word_counts
    python3 test_sparkray.py --unit

Unit checks isolate functions with small fixtures, including optional Parts
B/C without Spark, Java, or Ray installed. They provide practice feedback.
Run without options for the original integration groups and optional engines.
"""

import argparse
import importlib.util
import re
import sys
import traceback
import types
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from collections import Counter

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


def skip(group, why):
    print(f"  [SKIP] {group}: {why}")


def expect(cond, why):
    if not cond:
        raise AssertionError(why)


def true_counts():
    """The obviously-right reference: one Counter, no phases."""
    load_integration()
    c = Counter()
    for _, text in records():
        c.update(re.findall(r"[a-z]+", text.lower()))
    return c


# ---------------- OFFLINE group (Part A) ----------------

def test_map_contract():
    load_integration()
    pairs = map_words("wal", "The log, the log, THE LOG!")
    expect(pairs == [("the", 1), ("log", 1), ("the", 1), ("log", 1),
                     ("the", 1), ("log", 1)],
           f"map emits one (word, 1) per occurrence, in order — no counting "
           f"in map; got {pairs}")


def test_partition_deterministic_and_in_range():
    load_integration()
    for word in ("wal", "buffer", "tree", "shuffle", "a"):
        p1, p2 = partition_for(word, 4), partition_for(word, 4)
        expect(p1 == p2, f"same key must always route the same way "
                         f"({word!r}: {p1} then {p2})")
        expect(0 <= p1 < 4, f"partition must be in [0, 4), got {p1}")


def test_shuffle_loses_nothing():
    load_integration()
    pairs = [("a", 1), ("b", 1), ("a", 1), ("c", 1), ("b", 1), ("a", 1)]
    parts = shuffle(pairs, 3)
    expect(len(parts) == 3, f"asked for 3 partitions, got {len(parts)}")
    total = sum(len(vals) for p in parts for vals in p.values())
    expect(total == 6, f"every pair lands in exactly one partition "
                       f"(6 in, {total} out)")
    a_vals = [p["a"] for p in parts if "a" in p]
    expect(a_vals == [[1, 1, 1]],
           f"all of a key's values must be grouped in ONE partition, "
           f"got {a_vals}")


def test_shuffle_routes_by_hash():
    load_integration()
    pairs = [(w, 1) for w in ("wal", "buffer", "tree", "wal", "probe")]
    parts = shuffle(pairs, 4)
    for i, part in enumerate(parts):
        for key in part:
            expect(partition_for(key, 4) == i,
                   f"key {key!r} sits in partition {i} but hashes to "
                   f"{partition_for(key, 4)} — shuffle must route BY "
                   f"partition_for, not round-robin")


def test_reduce():
    load_integration()
    expect(reduce_counts("wal", [1, 1, 1]) == ("wal", 3),
           "reduce collapses ('wal', [1,1,1]) to ('wal', 3)")


def test_end_to_end():
    load_integration()
    got = dict(run_mapreduce(records(), map_words, reduce_counts))
    want = true_counts()
    expect(len(got) == len(want),
           f"distinct words: got {len(got)}, expected {len(want)}")
    for word in ("the", "index", "database", "log"):
        expect(got.get(word) == want[word],
               f"count for {word!r}: got {got.get(word)}, "
               f"expected {want[word]}")


def test_partition_count_does_not_change_answer():
    load_integration()
    base = sorted(run_mapreduce(records(), map_words, reduce_counts, 1))
    for n in (2, 7):
        other = sorted(run_mapreduce(records(), map_words, reduce_counts, n))
        expect(other == base,
               f"the answer must not depend on partition count "
               f"(n={n} differs from n=1) — grouping is broken")


# ---------------- SPARK group (Part B) ----------------

def spark_tests():
    load_integration()
    try:
        from pyspark import SparkContext
    except ImportError:
        skip("SPARK", "pyspark not installed; Part B tested by running "
                      "spark_wordcount.py yourself")
        return
    import shutil
    if shutil.which("java") is None:
        skip("SPARK", "Java is not installed; install a compatible JDK for Part B")
        return
    from spark_wordcount import word_counts
    sc = SparkContext("local[2]", "lab11-tests")
    sc.setLogLevel("ERROR")
    try:
        def test_spark_matches_reference():
            lines = sc.parallelize(
                [t + " " + x for _, t, x in DOCS], numSlices=4)
            got = dict(word_counts(sc, lines).collect())
            want = true_counts()
            expect(got == dict(want),
                   f"Spark's counts must equal the reference "
                   f"({len(got)} words vs {len(want)})")
        check("SPARK", "word_counts matches the reference", test_spark_matches_reference)
    finally:
        sc.stop()


# ---------------- RAY group (Part C) ----------------

def ray_tests():
    load_integration()
    try:
        import ray
    except ImportError:
        skip("RAY", "ray not installed; Part C tested by running "
                    "ray_speedup.py yourself")
        return
    import logging
    from ray_speedup import knn_all_parallel, knn_all_serial
    ray.init(num_cpus=4, include_dashboard=False,
             logging_level=logging.ERROR, log_to_driver=False)
    try:
        docs = list(range(48))            # 48 documents: ~1 s serial, enough to time

        def test_ray_identical():
            expect(knn_all_parallel(docs) == knn_all_serial(docs),
                   "parallel results must equal serial exactly "
                   "(same order; ray.get preserves it)")
        check("RAY", "parallel results identical to serial", test_ray_identical)

        def test_ray_launches_before_waiting():
            from unittest.mock import patch
            import ray_speedup
            launched = []
            expected = [[doc] for doc in docs]

            class Remote:
                def remote(self, doc):
                    launched.append(doc)
                    return ("future", doc)

            def gather(refs):
                expect(launched == docs, "launch every task before calling ray.get")
                expect(refs == [("future", doc) for doc in docs],
                       "gather every future in input order")
                return expected

            with patch.object(ray_speedup, "knn_remote", Remote()), \
                    patch.object(ray_speedup.ray, "get", side_effect=gather) as get:
                got = knn_all_parallel(docs)
                expect(got == expected, "return the gathered results")
                expect(get.call_count == 1, "gather once after launching all tasks")
        check("RAY", "all tasks launch before the wait", test_ray_launches_before_waiting)
    finally:
        ray.shutdown()


# ---------------- isolated function checks (ungraded) ----------------
# Imports run in a temporary fixture environment. Unit checks do not load the
# arXiv corpus, embeddings, Spark, Java, or Ray. Every replacement is restored.

@contextmanager
def fixture_module(name, ray=None):
    corpus = types.ModuleType("corpus")
    corpus.DOCS = []
    replacements = {"corpus": corpus}
    if ray is not None:
        embeddings = types.ModuleType("embeddings")
        embeddings.load = lambda: []
        replacements.update(ray=ray, embeddings=embeddings)
    path = Path(__file__).resolve().with_name(name + ".py")
    spec = importlib.util.spec_from_file_location("_unit_" + name, path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, replacements):
        spec.loader.exec_module(module)
        yield module


def unit_map_words():
    with fixture_module("mapreduce") as student:
        for text, want in (
            ("The log, the LOG! 123", [("the", 1), ("log", 1), ("the", 1), ("log", 1)]),
            ("B-tree's page_2", [("b", 1), ("tree", 1), ("s", 1), ("page", 1)]),
            ("! 123", []), ("", []),
        ):
            expect(student.map_words("doc", text) == want,
                   "emit lowercase alphabetic words in order, one (word, 1) per occurrence")


def unit_partition_for():
    with fixture_module("mapreduce") as student:
        for n in (1, 3, 7):
            for key in ("wal", "buffer", "tree", "a", ""):
                expect(student.partition_for(key, n) == hash(key) % n,
                       "route with Python's hash(key) modulo n_partitions")


def unit_shuffle():
    with fixture_module("mapreduce") as student:
        # partition_for may still be a TODO; replace only that sibling.
        with patch.object(student, "partition_for", lambda key, n: hash(key) % n):
            pairs = [("wal", 2), ("page", 7), ("wal", -1), ("tree", 0), ("page", 3)]
            for n in (1, 3, 7):
                original = list(pairs)
                parts = student.shuffle(pairs, n)
                expect(len(parts) == n, "return exactly n_partitions dictionaries")
                want = [{} for _ in range(n)]
                for key, value in pairs:
                    want[hash(key) % n].setdefault(key, []).append(value)
                expect(parts == want, "route and group every original value, preserving occurrence order")
                expect(pairs == original, "shuffle must not change its input pairs")
                expect(student.shuffle([], n) == [{} for _ in range(n)],
                       "empty input still returns n empty partitions")


def unit_reduce_counts():
    with fixture_module("mapreduce") as student:
        for word, values, total in (("wal", [1, 1, 1], 3), ("page", [4, -2, 7], 9),
                                     ("empty", [], 0)):
            expect(student.reduce_counts(word, values) == (word, total),
                   "return the original key and the sum of its values")


class FixtureRDD:
    """Small lazy RDD for the documented word-count transformations.

    This checks tokenization, counts, and returning a lazy RDD. Real Spark
    execution remains a separate optional integration check.
    """
    def __init__(self, evaluate, context):
        self._evaluate = evaluate
        self.context = context

    def flatMap(self, fn):
        return FixtureRDD(lambda: [y for x in self._evaluate() for y in fn(x)], self.context)

    def map(self, fn):
        return FixtureRDD(lambda: [fn(x) for x in self._evaluate()], self.context)

    def reduceByKey(self, fn, numPartitions=None):
        def evaluate():
            grouped = {}
            for key, value in self._evaluate():
                grouped[key] = fn(grouped[key], value) if key in grouped else value
            return list(grouped.items())
        return FixtureRDD(evaluate, self.context)

    def groupByKey(self, numPartitions=None):
        def evaluate():
            grouped = {}
            for key, value in self._evaluate():
                grouped.setdefault(key, []).append(value)
            return list(grouped.items())
        return FixtureRDD(evaluate, self.context)

    def mapValues(self, fn):
        return self.map(lambda pair: (pair[0], fn(pair[1])))

    def filter(self, fn):
        return FixtureRDD(lambda: [x for x in self._evaluate() if fn(x)], self.context)

    def collect(self):
        expect(self.context.allow_actions, "word_counts must return a lazy RDD without calling collect()")
        return self._evaluate()

    def count(self):
        return len(self.collect())


class FixtureSparkContext:
    def __init__(self):
        self.allow_actions = False

    def parallelize(self, values, numSlices=None):
        values = list(values)
        return FixtureRDD(lambda: list(values), self)


def unit_word_counts():
    with fixture_module("spark_wordcount") as student:
        for texts in (["The log, the LOG!", "B-tree's 123 log"], [], ["", "123"]):
            sc = FixtureSparkContext()
            result = student.word_counts(sc, sc.parallelize(texts))
            expect(isinstance(result, FixtureRDD), "return the final RDD, not collected Python results")
            sc.allow_actions = True
            got = result.collect()
            want = Counter(re.findall(r"[a-z]+", " ".join(texts).lower()))
            expect(len(got) == len(want) and dict(got) == dict(want),
                   "Spark transformations must produce one correct count per word")


class FixtureFuture:
    def __init__(self, value):
        self.value = value


class FixtureRay(types.ModuleType):
    """Remote-call and gather protocol only; no Ray worker or vector data."""
    def __init__(self):
        super().__init__("ray")
        self.launched = []
        self.gathers = []

    def remote(self, fn=None, **options):
        if fn is None:
            return lambda fn: self.remote(fn, **options)
        runtime = self

        class Remote:
            def remote(self, *args, **kwargs):
                runtime.launched.append((args, kwargs))
                return FixtureFuture(fn(*args, **kwargs))

            def options(self, **options):
                return self

        return Remote()

    def get(self, refs):
        self.gathers.append(list(self.launched))
        if isinstance(refs, FixtureFuture):
            return refs.value
        expect(all(isinstance(ref, FixtureFuture) for ref in refs), "gather the returned task futures")
        return [ref.value for ref in refs]


def unit_knn_remote():
    ray = FixtureRay()
    with fixture_module("ray_speedup", ray) as student:
        remote = getattr(student, "knn_remote", None)
        expect(remote is not None and callable(getattr(remote, "remote", None)),
               "define knn_remote with @ray.remote above knn_all_parallel")
        calls = []

        def neighbors(doc):
            calls.append(doc)
            return [doc + 10, doc + 20]

        with patch.object(student, "neighbors", neighbors):
            for doc in (7, 2):
                expect(ray.get(remote.remote(doc)) == [doc + 10, doc + 20],
                       "the remote function must return neighbors(doc)")
        expect(calls == [7, 2], "delegate each document to the provided neighbors function")


def unit_knn_all_parallel():
    ray = FixtureRay()
    with fixture_module("ray_speedup", ray) as student:
        # The remote wrapper is another student step. Supply it here so only
        # knn_all_parallel is tested; --unit knn_remote tests the real wrapper.
        remote = ray.remote(lambda doc: [doc, doc + 100])
        with patch.object(student, "knn_remote", remote, create=True):
            for docs in ([7, 2, 7, 1], []):
                ray.launched.clear()
                ray.gathers.clear()
                original = list(docs)
                got = student.knn_all_parallel(docs)
                expected_calls = [((doc,), {}) for doc in docs]
                expect(ray.launched == expected_calls, "launch one task per document in input order")
                expect(got == [[doc, doc + 100] for doc in docs], "return all gathered results in input order")
                expect(docs == original, "keep the input document list unchanged")
                expect(all(snapshot == expected_calls for snapshot in ray.gathers),
                       "launch every task before the first ray.get; waiting inside the launch loop is serial")
                expect(len(ray.gathers) == 1 or (not docs and not ray.gathers),
                       "gather once after launching all tasks")


UNIT_TESTS = {
    "map_words": unit_map_words,
    "partition_for": unit_partition_for,
    "shuffle": unit_shuffle,
    "reduce_counts": unit_reduce_counts,
    "word_counts": unit_word_counts,
    "knn_remote": unit_knn_remote,
    "knn_all_parallel": unit_knn_all_parallel,
}
OPTIONAL_TARGETS = {"word_counts", "knn_remote", "knn_all_parallel"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list function targets and exit")
    parser.add_argument("--unit", nargs="?", const="all", choices=["all", *UNIT_TESTS],
                        metavar="TARGET", help="test functions independently using offline fixtures")
    parser.add_argument("-v", action="store_true", help="show failure tracebacks")
    args = parser.parse_args(argv)
    global VERBOSE
    VERBOSE = args.v
    if args.list:
        for name in UNIT_TESTS:
            suffix = " (optional part; unit check runs offline)" if name in OPTIONAL_TARGETS else ""
            print(name + suffix)
        return 0
    RESULTS.clear()
    if args.unit:
        print("UNIT checks — supplied siblings and offline Spark/Ray fixtures; these are not grading checks")
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


def load_integration():
    """Import real dependencies once, including for directly imported tests."""
    global _INTEGRATION_LOADED
    global DOCS, map_words, partition_for, records, reduce_counts, run_mapreduce, shuffle
    if _INTEGRATION_LOADED:
        return
    from corpus import DOCS
    from mapreduce import (map_words, partition_for, records, reduce_counts,
                           run_mapreduce, shuffle)
    _INTEGRATION_LOADED = True


def integration_tests():
    print("OFFLINE group (Part A)")
    check("OFFLINE", "map emits raw (word, 1) pairs",          test_map_contract)
    check("OFFLINE", "partitioning is deterministic, in range", test_partition_deterministic_and_in_range)
    check("OFFLINE", "shuffle loses nothing, groups keys",      test_shuffle_loses_nothing)
    check("OFFLINE", "shuffle routes by partition_for",         test_shuffle_routes_by_hash)
    check("OFFLINE", "reduce collapses values",                 test_reduce)
    check("OFFLINE", "end-to-end counts match the reference",   test_end_to_end)
    check("OFFLINE", "answer independent of partition count",   test_partition_count_does_not_change_answer)
    print("SPARK group (Part B)")
    spark_tests()
    print("RAY group (Part C)")
    ray_tests()


if __name__ == "__main__":
    sys.exit(main())
