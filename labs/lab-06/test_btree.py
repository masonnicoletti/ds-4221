"""Lab 6 test harness — run:  python3 test_btree.py

Three groups, mirroring the lab page:

    TREE   — insert, split, and the shape invariants that keep O(log n)
    SEARCH — point lookups, duplicates, ranges across the leaf chain
    INDEX  — the tree over a real table: same answers as a scan, way less touching

Pure stdlib; no pytest. The Gradescope autograder runs this same harness.

Build one method at a time:
    python3 test_btree.py --list
    python3 test_btree.py --unit BPlusTree.search
    python3 test_btree.py --unit

Unit checks supply the other methods or construct nodes directly. The selected
method always runs your code; an unfinished method fails its own check.
Run without --unit for the original integration/grading checks.
"""

import argparse
import shutil
import sys
import tempfile
import traceback
from unittest.mock import patch

from file_manager import FileManager
from buffer_manager import BufferManager
from record_manager import Schema, Layout, TableScan
from query_engine import Predicate, SelectScan
from btree import BPlusTree, Node, ORDER, build_index, IndexSelectScan

BLOCK_SIZE = 512
RESULTS = []


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
            if "-v" in sys.argv:
                traceback.print_exc()


def expect(cond, why):
    if not cond:
        raise AssertionError(why)


def leaves_of(tree):
    node = tree.root
    while not node.leaf:
        node = node.children[0]
    out = []
    while node is not None:
        out.append(node)
        node = node.next
    return out


def all_leaf_keys(tree):
    return [k for leaf in leaves_of(tree) for k in leaf.keys]


def check_invariants(tree):
    """Every node within ORDER; leaf chain sorted; heights consistent."""
    def depth_of(node):
        d = 1
        while not node.leaf:
            node = node.children[0]
            d += 1
        return d
    keys = all_leaf_keys(tree)
    expect(keys == sorted(keys), f"leaf chain out of order: {keys[:20]}...")
    stack = [tree.root]
    while stack:
        n = stack.pop()
        expect(len(n.keys) <= ORDER, f"node holds {len(n.keys)} keys > ORDER={ORDER}")
        if not n.leaf:
            expect(len(n.children) == len(n.keys) + 1,
                   f"internal node: {len(n.keys)} keys need {len(n.keys)+1} children, "
                   f"has {len(n.children)}")
            stack.extend(n.children)
    expect(depth_of(tree.root) == tree.height,
           f"tree.height says {tree.height}, actual depth {depth_of(tree.root)}")


# ---------------- TREE group ----------------

def test_leaf_stays_sorted():
    t = BPlusTree()
    for k in [5, 2, 9, 1]:
        t.insert(k, ("r", k))
    expect(t.root.leaf and t.root.keys == [1, 2, 5, 9],
           f"4 keys fit in one leaf, sorted — got {t.root.keys}")
    expect(t.height == 1, "no split yet, height must still be 1")


def test_first_split_grows_root():
    t = BPlusTree()
    for k in [1, 2, 3, 4, 5]:               # ORDER=4: the 5th key splits
        t.insert(k, ("r", k))
    expect(not t.root.leaf, "after the first split the root must be internal")
    expect(t.height == 2, f"height must be 2, got {t.height}")
    expect(t.root.keys == [3], f"the middle key (3) is copied up — root has {t.root.keys}")
    expect(all_leaf_keys(t) == [1, 2, 3, 4, 5],
           "a LEAF split must keep every key in the leaves (copy up, not move up)")
    check_invariants(t)


def test_many_inserts_stay_legal():
    t = BPlusTree()
    for k in [37, 4, 91, 15, 60, 8, 42, 73, 1, 55, 29, 88, 12, 66, 23,
              50, 95, 3, 78, 34, 61, 17, 84, 45, 9]:
        t.insert(k, ("r", k))
    check_invariants(t)
    expect(t.height == 3, f"25 scattered keys at ORDER=4 should reach height 3, got {t.height}")


def test_logarithmic_height():
    t = BPlusTree()
    for k in range(500):
        t.insert(k, ("r", k))
    check_invariants(t)
    expect(t.height <= 6,
           f"500 sequential keys must stay shallow (<=6 at ORDER=4), got {t.height}")


# ---------------- SEARCH group ----------------

def test_search_hits_and_misses():
    t = BPlusTree()
    for k in range(0, 100, 2):              # even keys only
        t.insert(k, ("blk", k))
    expect(t.search(42) == [("blk", 42)], "present key must return its rid")
    expect(t.search(43) == [], "absent key must return [], not raise")


def test_duplicate_keys_share_a_slot():
    t = BPlusTree()
    t.insert(35, (0, 1))
    t.insert(35, (2, 4))
    t.insert(35, (1, 0))
    expect(sorted(t.search(35)) == [(0, 1), (1, 0), (2, 4)],
           "three rows with gpa 35 must all come back from one key")
    expect(all_leaf_keys(t) == [35], "duplicates share ONE key entry, not three")


def test_range_walks_the_chain():
    t = BPlusTree()
    for k in range(50):
        t.insert(k, ("r", k))
    got = [rid for rid in t.range(10, 20)]
    expect(got == [("r", k) for k in range(10, 21)],
           f"range(10,20) must return keys 10..20 inclusive, in order — got {got[:8]}...")
    expect(t.range(200, 300) == [], "an empty range returns []")


# ---------------- INDEX group (over a real table) ----------------

def fresh_school():
    d = tempfile.mkdtemp(prefix="microdb-l6-")
    fm = FileManager(d, BLOCK_SIZE)
    bm = BufferManager(fm, 8)
    lay = Layout(Schema().add_int_field("sid").add_string_field("name", 8)
                         .add_int_field("gpa"))
    ts = TableScan(bm, fm, "students", lay)
    for sid, name, gpa in [(1, "ada", 39), (2, "ben", 31), (3, "cyd", 37),
                           (4, "dee", 28), (5, "eli", 36), (6, "fay", 36)]:
        ts.insert()
        ts.set_int("sid", sid); ts.set_string("name", name); ts.set_int("gpa", gpa)
    ts.close()
    return d, fm, bm, lay


def test_index_matches_scan():
    d, fm, bm, lay = fresh_school()
    try:
        tree = build_index(bm, fm, "students", lay, "gpa")
        idx = IndexSelectScan(TableScan(bm, fm, "students", lay), tree, 36)
        idx.before_first()
        via_index = []
        while idx.next():
            via_index.append(idx.get_val("name"))
        idx.close()
        sel = SelectScan(TableScan(bm, fm, "students", lay),
                         Predicate(("gpa", "=", 36)))
        sel.before_first()
        via_scan = []
        while sel.next():
            via_scan.append(sel.get_val("name"))
        sel.close()
        expect(sorted(via_index) == sorted(via_scan) == ["eli", "fay"],
               f"index and scan must agree: index={via_index} scan={via_scan}")
    finally:
        fm.close(); shutil.rmtree(d, ignore_errors=True)


def test_index_touches_less():
    d, fm, bm, lay = fresh_school()
    try:
        tree = build_index(bm, fm, "students", lay, "gpa")
        tree.nodes_touched = 0
        tree.search(36)
        expect(tree.nodes_touched == tree.height,
               f"one search must touch exactly height ({tree.height}) nodes, "
               f"got {tree.nodes_touched}")
    finally:
        fm.close(); shutil.rmtree(d, ignore_errors=True)


# ---------------- Isolated function checks (not integration fixtures) ----------------

def _unit_leaf(keys):
    leaf = Node(leaf=True)
    leaf.keys = list(keys)
    leaf.rids = [[("row", k)] for k in keys]
    return leaf


def _unit_tree():
    """A three-level tree built without calling any student TODO."""
    leaves = [_unit_leaf(keys) for keys in ([1, 3], [5, 7], [9, 11], [13, 15])]
    leaves[1].rids[0].append(("duplicate", 5))
    for left, right in zip(leaves, leaves[1:]):
        left.next = right
    left, right, root = Node(False), Node(False), Node(False)
    left.keys, left.children = [5], leaves[:2]
    right.keys, right.children = [13], leaves[2:]
    root.keys, root.children = [9], [left, right]
    tree = BPlusTree()
    tree.root, tree.height = root, 3
    return tree, leaves


def _unit_reference_split(self, node, parent):
    """Dependency for insert only; never replaces the selected _split method."""
    mid = len(node.keys) // 2
    separator = node.keys[mid]
    sibling = Node(node.leaf)
    if node.leaf:
        sibling.keys, sibling.rids = node.keys[mid:], node.rids[mid:]
        node.keys, node.rids = node.keys[:mid], node.rids[:mid]
        sibling.next, node.next = node.next, sibling
    else:
        sibling.keys, sibling.children = node.keys[mid + 1:], node.children[mid + 1:]
        node.keys, node.children = node.keys[:mid], node.children[:mid + 1]
    if parent is None:
        parent = Node(False)
        parent.children = [node]
        self.root = parent
        self.height += 1
    position = parent.children.index(node)
    parent.keys.insert(position, separator)
    parent.children.insert(position + 1, sibling)


def _unit_reference_search(self, key):
    """Point lookup dependency for a range implementation that reuses search."""
    leaf = self._descend(key)[-1]
    if key in leaf.keys:
        return list(leaf.rids[leaf.keys.index(key)])
    return []


def _unit_reference_range(self, lo, hi):
    """Range dependency for a search implementation that reuses range(k, k)."""
    leaf = self._descend(lo)[-1]
    result = []
    while leaf is not None:
        for key, rids in zip(leaf.keys, leaf.rids):
            if key > hi:
                return result
            if key >= lo:
                result.extend(rids)
        leaf = leaf.next
    return result


@patch.object(BPlusTree, "range", _unit_reference_range)
def unit_search():
    tree, leaves = _unit_tree()
    for key in [1, 5, 9, 13, 15, -1, 6, 20]:
        expected = [rid for leaf in leaves for k, rids in zip(leaf.keys, leaf.rids)
                    if k == key for rid in rids]
        tree.nodes_touched = 0
        got = tree.search(key)
        expect(got == expected, f"search({key}) should return {expected}, got {got}")
        expect(tree.nodes_touched == tree.height,
               "a point lookup must descend exactly one root-to-leaf path")
    copy = tree.search(5)
    copy.append(("not stored", 5))
    expect(leaves[1].rids[0] == [("row", 5), ("duplicate", 5)],
           "search must return a copy, so callers cannot change stored RIDs")
    expect(BPlusTree().search(5) == [], "search in an empty tree returns []")


@patch.object(BPlusTree, "search", _unit_reference_search)
def unit_range():
    tree, leaves = _unit_tree()
    for lo, hi in [(3, 13), (5, 5), (6, 12), (-10, 100), (6, 6), (20, 30), (8, 2)]:
        expected = [rid for leaf in leaves for k, rids in zip(leaf.keys, leaf.rids)
                    if lo <= k <= hi for rid in rids]
        got = tree.range(lo, hi)
        expect(got == expected, f"range({lo}, {hi}) should return {expected}, got {got}")
    expect(BPlusTree().range(0, 10) == [], "range on an empty tree returns []")


def unit_insert():
    # Patch only the unfinished dependencies. Recursive insert calls still run
    # the student's insert, and the patch is removed even when a check fails.
    with patch.object(BPlusTree, "_split", _unit_reference_split), \
         patch.object(BPlusTree, "search", _unit_reference_search), \
         patch.object(BPlusTree, "range", _unit_reference_range):
        test_leaf_stays_sorted()
        test_first_split_grows_root()
        test_many_inserts_stay_legal()
        test_logarithmic_height()
        tree = BPlusTree()
        keys = [37, 4, 91, 15, 60, 8, 42, 73, 1, 55, 29, 88, 12, 66, 23,
                50, 95, 3, 78, 34, 61, 17, 84, 45, 9]
        for key in keys + [37, 1, 95]:
            tree.insert(key, ("row", key))
        actual = {key: rids for leaf in leaves_of(tree)
                  for key, rids in zip(leaf.keys, leaf.rids)}
        expected = {key: [("row", key)] * (2 if key in (37, 1, 95) else 1)
                    for key in keys}
        expect(actual == expected, "inserts must preserve every RID, including duplicates")
        expect(all_leaf_keys(tree) == sorted(keys), "duplicates must share one key slot")
        check_invariants(tree)


def unit_split():
    for leaf in (True, False):
        for has_parent in (False, True):
            tree = BPlusTree()
            node = _unit_leaf([10, 20, 30, 40, 50]) if leaf else Node(False)
            children = [_unit_leaf([k]) for k in (1, 11, 21, 31, 41, 51)]
            if not leaf:
                node.keys, node.children = [10, 20, 30, 40, 50], children[:]
            following = _unit_leaf([90])
            node.next = following if leaf else None
            parent = None
            before, after = _unit_leaf([-10]), _unit_leaf([90])
            if not leaf:
                # Siblings must have the same height as the internal node.
                before, after = Node(False), Node(False)
                before.children, after.children = [_unit_leaf([-10])], [_unit_leaf([90])]
            if has_parent:
                parent = Node(False)
                parent.keys, parent.children = [0, 80], [before, node, after]
                tree.root = parent
            else:
                tree.root = node
            tree.height = (1 if leaf else 2) + int(has_parent)
            old_height = tree.height
            tree._split(node, parent)
            top = parent if has_parent else tree.root
            expect(top.keys == ([0, 30, 80] if has_parent else [30]),
                   "split must insert the middle separator at the right parent position")
            expect(not top.leaf, "a split's parent must be internal")
            index = 1 if has_parent else 0
            expect(top.children[index] is node, "keep the original node as the left half")
            expect(len(top.children) == len(top.keys) + 1, "parent needs one child per interval")
            if has_parent:
                expect(top.children[0] is before and top.children[-1] is after,
                       "splitting a middle child must preserve its neighbors")
            sibling = top.children[index + 1]
            expect(node.keys == [10, 20], "left half must keep keys before the midpoint")
            expect(sibling.keys == ([30, 40, 50] if leaf else [40, 50]),
                   "leaf splits copy the middle key up; internal splits move it up")
            expect(sibling.leaf == leaf, "the sibling must have the same node kind")
            if leaf:
                expect(node.rids == [[("row", 10)], [("row", 20)]] and
                       sibling.rids == [[("row", k)] for k in [30, 40, 50]],
                       "leaf RIDs must stay aligned with their keys")
                expect(node.next is sibling and sibling.next is following,
                       "splice the sibling into the existing leaf chain")
            else:
                expect(node.children == children[:3] and sibling.children == children[3:],
                       "internal splits must preserve all child pointers in order")
            expect(tree.height == old_height + (0 if has_parent else 1),
                   "only a new root increases tree height")


UNIT_TESTS = {
    "BPlusTree.search": unit_search,
    "BPlusTree.insert": unit_insert,
    "BPlusTree._split": unit_split,
    "BPlusTree.range": unit_range,
}


def run_units_from_cli():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--list", action="store_true", help="list isolated function targets")
    modes.add_argument("--unit", nargs="?", const="all", choices=["all", *UNIT_TESTS],
                       help="run all isolated checks, or one exact target")
    parser.add_argument("-v", action="store_true", help="show tracebacks for failures")
    args = parser.parse_args()
    if args.list:
        print("\n".join(UNIT_TESTS))
        sys.exit(0)
    if args.unit:
        targets = UNIT_TESTS if args.unit == "all" else {args.unit: UNIT_TESTS[args.unit]}
        for name, fn in targets.items():
            check("UNIT", name, fn)
        n = sum(RESULTS)
        print(f"\n{n}/{len(RESULTS)} isolated function checks passed")
        sys.exit(0 if n == len(RESULTS) else 1)


if __name__ == "__main__":
    run_units_from_cli()
    print("TREE group")
    check("TREE", "a leaf keeps its keys sorted",              test_leaf_stays_sorted)
    check("TREE", "the fifth key splits; the root grows",      test_first_split_grows_root)
    check("TREE", "25 scattered inserts keep every invariant", test_many_inserts_stay_legal)
    check("TREE", "500 keys, height stays logarithmic",        test_logarithmic_height)
    print("SEARCH group")
    check("SEARCH", "hits return rids, misses return []",      test_search_hits_and_misses)
    check("SEARCH", "duplicate keys share one slot",           test_duplicate_keys_share_a_slot)
    check("SEARCH", "range walks the leaf chain, inclusive",   test_range_walks_the_chain)
    print("INDEX group")
    check("INDEX", "IndexSelectScan agrees with SelectScan",   test_index_matches_scan)
    check("INDEX", "one lookup touches exactly height nodes",  test_index_touches_less)
    n = sum(RESULTS)
    print(f"\n{n}/{len(RESULTS)} tests passed")
    sys.exit(0 if n == len(RESULTS) else 1)
