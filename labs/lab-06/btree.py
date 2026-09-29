"""microdb · part 6 — the B+ tree index.

Lab 6 of Advanced Databases for Data Science (DS 6XXX, Fall 2026).
Runs on Labs 1-5 (reference implementations ship in this folder; the
reference TableScan gained move_to_rid() for this lab).

AN INDEX IS A MAP FROM VALUES TO RIDS. This one is the classic:

    - leaves hold (key, rid) pairs in sorted order, linked left-to-right
    - internal nodes hold ordered keys that route a search downward
    - every node holds at most ORDER distinct keys; a fifth distinct key
      overflows a node when ORDER=4. A split copies a leaf separator or
      moves an internal separator into the parent. Only a root split
      adds a level, and it adds that level above every leaf.

    search(k)  descends height-many nodes:  O(log n)  vs a scan's O(n)
    range(lo, hi)  descends once, then walks the leaf chain

Honest scope note: real engines store each node in a disk page and split
pages (Sciore ch. 12 does it in full). Ours keeps nodes in memory and is
rebuilt at startup — the ALGORITHM is identical, and it indexes real rows
in your real heap file via their RIDs.

Run the tests any time:   python3 test_btree.py
Run the measurement:      python3 measure_index.py     (after tests pass)
"""

from __future__ import annotations

ORDER = 4          # max keys per node; a real page-sized node holds ~200


class Node:
    """One B+ tree node. Provided complete — read it before coding.

    Leaf:      keys = [5, 8, 12]   rids = [[(0,1)], [(2,0)], [(1,4)]]
               (rids[i] is a LIST: duplicate keys share one slot)
               next -> the right-hand sibling leaf (the range-scan chain)

    Internal:  keys = [10]         children = [left-subtree, right-subtree]
               child 0 holds keys < 10; child 1 holds keys >= 10.
               In general, m separators route to m+1 child subtrees.
    """

    def __init__(self, leaf: bool):
        self.leaf = leaf
        self.keys: list = []
        self.rids: list[list] = []      # leaves only
        self.children: list[Node] = []  # internal only
        self.next: Node | None = None   # leaves only

    def is_full(self) -> bool:
        """True when OVER capacity and a split is needed; four keys fit."""
        return len(self.keys) > ORDER

    def child_index_for(self, key) -> int:
        """Which child to descend into for `key`. Provided.
        Equality goes right: advance past every separator <= key."""
        i = 0
        while i < len(self.keys) and key >= self.keys[i]:
            i += 1
        return i


class BPlusTree:
    """The index. You write the four methods marked YOUR JOB."""

    def __init__(self):
        self.root = Node(leaf=True)
        self.height = 1                 # book-keeping the tests check
        self.nodes_touched = 0          # incremented by _descend, for Measure

    # ---- provided plumbing ----

    def _descend(self, key) -> list[Node]:
        """The path from root to the leaf where `key` belongs (inclusive).
        Provided — both search and insert start exactly this way."""
        path = [self.root]
        while not path[-1].leaf:
            node = path[-1]
            path.append(node.children[node.child_index_for(key)])
        self.nodes_touched += len(path)
        return path

    # ---------------- YOUR JOB starts here. ----------------

    def search(self, key) -> list:
        """All RIDs stored under `key` (a list — duplicates share a key),
        or [] if the key is absent.

        Sketch: _descend to the leaf; find the key in leaf.keys (list.index
        or a loop); return a COPY of its rid list."""
        # TODO
        raise NotImplementedError

    def insert(self, key, rid) -> None:
        """Insert (key, rid) at the right spot in the right leaf, keeping
        keys sorted; then repair any overfull nodes up the path.

        Sketch: _descend for the path. In the leaf: if the key exists,
        append the rid to its list; else insort the key and a fresh [rid]
        at the same position (the bisect module is your friend). Then,
        while the deepest overfull node exists, _split it into its parent
        (path[-2], or a brand-new root if it WAS the root)."""
        # TODO
        raise NotImplementedError

    def _split(self, node: Node, parent: Node | None) -> None:
        """Split an overfull `node`, hoisting its middle key into `parent`.

        mid = len(keys) // 2. Leaf split: right sibling takes keys[mid:]
        (and their rids); the middle key is COPIED up (leaves keep all
        data); fix the next-pointers: node -> sibling -> old next.
        Internal split: right sibling takes keys[mid+1:] and the matching
        children; the middle key MOVES up (internal keys are only guides).
        No parent? Make a new internal root holding just the hoisted key
        and the two halves, and bump self.height."""
        # TODO
        raise NotImplementedError

    def range(self, lo, hi) -> list:
        """All RIDs with lo <= key <= hi, in key order.

        Sketch: _descend to lo's leaf, then walk rightward — through the
        leaf and across .next links — collecting until a key exceeds hi."""
        # TODO
        raise NotImplementedError

    # ---------------- YOUR JOB ends here. ----------------


def build_index(bm, fm, tblname: str, layout, field: str) -> BPlusTree:
    """Index one field of an existing table: scan it once, insert every
    (value, rid) pair. Provided — this is how an engine backfills
    CREATE INDEX, and it is exactly one TableScan."""
    from record_manager import TableScan
    tree = BPlusTree()
    ts = TableScan(bm, fm, tblname, layout)
    ts.before_first()
    while ts.next():
        tree.insert(ts.get_val(field), ts.rid())
    ts.close()
    return tree


class IndexSelectScan:
    """A Lab-4-style scan that answers `field = key` via the index:
    jump straight to the matching rows, touching nothing else. Provided —
    it is nine lines, and it is why indexes exist."""

    def __init__(self, table_scan, tree: BPlusTree, key):
        self.ts = table_scan
        self.rids = tree.search(key)
        self.pos = -1

    def before_first(self) -> None:
        self.pos = -1

    def next(self) -> bool:
        self.pos += 1
        if self.pos >= len(self.rids):
            return False
        self.ts.move_to_rid(self.rids[self.pos])
        return True

    def get_val(self, fld): return self.ts.get_val(fld)
    def has_field(self, fld) -> bool: return self.ts.has_field(fld)
    def close(self) -> None: self.ts.close()
