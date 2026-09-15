"""microdb · part 4 — the query engine: scans that stack.

Lab 4 of Advanced Databases for Data Science (DS 6XXX, Fall 2026).
Runs on Labs 1-3 (reference implementations ship in this folder). The
reference TableScan gained two small methods for this lab — get_val()
and has_field() — so every scan in the pipeline speaks one interface.

THE SCAN INTERFACE (duck-typed; every operator implements it):

    before_first()        rewind to before the first row
    next() -> bool        advance to the next row; False when exhausted
    get_val(fld)          value of a field in the current row
    has_field(fld) -> bool
    close()               release everything underneath (pins!)

Because the interface is uniform, operators wrap each other freely:

    ts  = TableScan(bm, fm, "students", layout)          # rows of a table
    sel = SelectScan(ts, Predicate(("gpa", ">", 35)))    # ...that pass a test
    prj = ProjectScan(sel, ["name"])                     # ...only some fields
    while prj.next():
        print(prj.get_val("name"))
    prj.close()

That stack IS a query plan. Rows flow up on demand — nothing is copied,
nothing is materialized, and a terabyte scan still uses one pinned block.

Run the tests any time:   python3 test_scans.py
Run the measurement:      python3 measure_pipeline.py   (after tests pass)
"""

from __future__ import annotations


class F:
    """Marks a predicate's right-hand side as a FIELD, not a literal.

        ("gpa", ">", 35)          gpa greater than the number 35
        ("sid", "=", F("mid"))    field sid equals field mid  (a join!)
    """

    def __init__(self, name: str):
        self.name = name


class Predicate:
    """A conjunction (AND) of simple comparisons. Provided complete.

        Predicate(("gpa", ">", 35))
        Predicate(("gpa", ">", 30), ("name", "=", "ada"))
        Predicate(("sid", "=", F("mid")))          # join condition
    """

    OPS = {
        "=":  lambda a, b: a == b,
        ">":  lambda a, b: a > b,
        "<":  lambda a, b: a < b,
    }

    def __init__(self, *terms):
        self.terms = terms

    def is_satisfied(self, scan) -> bool:
        """True iff the scan's current row passes every term."""
        for field, op, rhs in self.terms:
            lhs_val = scan.get_val(field)
            rhs_val = scan.get_val(rhs.name) if isinstance(rhs, F) else rhs
            if not self.OPS[op](lhs_val, rhs_val):
                return False
        return True


class SelectScan:
    """Rows of the underlying scan that satisfy a predicate.   (WHERE)"""

    def __init__(self, scan, predicate: Predicate):
        self.scan = scan
        self.predicate = predicate

    # ---------------- YOUR JOB starts here. ----------------

    def next(self) -> bool:
        """Advance the underlying scan until a row satisfies the
        predicate. False when the underlying scan runs out."""
        # TODO: loop scan.next(); return True on the first row where
        #       self.predicate.is_satisfied(self.scan).
        raise NotImplementedError

    # ---------------- YOUR JOB ends here. ----------------

    # Everything else passes straight through (selection changes which
    # rows appear, not what a row looks like).
    def before_first(self) -> None: self.scan.before_first()
    def get_val(self, fld): return self.scan.get_val(fld)
    def has_field(self, fld) -> bool: return self.scan.has_field(fld)
    def close(self) -> None: self.scan.close()


class ProjectScan:
    """The underlying scan restricted to some fields.   (the SELECT list)"""

    def __init__(self, scan, fields: list[str]):
        self.scan = scan
        self.fields = fields

    # ---------------- YOUR JOB starts here. ----------------

    def get_val(self, fld):
        """Answer only for projected fields; otherwise raise ValueError
        (asking for a projected-away field is always a caller bug)."""
        # TODO
        raise NotImplementedError

    def has_field(self, fld) -> bool:
        # TODO: a field exists here only if the projection kept it.
        raise NotImplementedError

    # ---------------- YOUR JOB ends here. ----------------

    # Projection changes what a row looks like, not which rows appear.
    def before_first(self) -> None: self.scan.before_first()
    def next(self) -> bool: return self.scan.next()
    def close(self) -> None: self.scan.close()


class ProductScan:
    """Every row of `left` paired with every row of `right`.   (JOIN's engine)

    The nested loop: for each left row, run through ALL of right, then
    advance left one row and rewind right. A join is this product with a
    SelectScan on top testing the join condition.
    """

    def __init__(self, left, right):
        self.left = left
        self.right = right
        self._left_ready = False  # shared cursor state for before_first() and next()

    # ---------------- YOUR JOB starts here. ----------------

    def before_first(self) -> None:
        """Position for the first pair: left on its FIRST row (rewind,
        then one next()), right before its first. Store the result of left.next()
        in self._left_ready so next() knows whether a left row exists."""
        # TODO
        raise NotImplementedError

    def next(self) -> bool:
        """Advance right; when right runs out, rewind it and advance
        left. Use self._left_ready to track whether a left row exists. Return
        False if either input is empty, and set self._left_ready to False
        when exhausted until before_first() is called."""
        # TODO: handle empty inputs as well as the normal rollover.
        raise NotImplementedError

    def get_val(self, fld):
        """Ask whichever side has the field (left wins ties)."""
        # TODO: use has_field.
        raise NotImplementedError

    def has_field(self, fld) -> bool:
        # TODO: either side.
        raise NotImplementedError

    # ---------------- YOUR JOB ends here. ----------------

    def close(self) -> None:
        self.left.close()
        self.right.close()


class CountingScan:
    """Wraps any scan and counts the rows that flow through it. Provided —
    measure_pipeline.py uses it to make 'rows examined' visible."""

    def __init__(self, scan):
        self.scan = scan
        self.rows = 0

    def next(self) -> bool:
        advanced = self.scan.next()
        if advanced:
            self.rows += 1
        return advanced

    def before_first(self) -> None: self.scan.before_first()
    def get_val(self, fld): return self.scan.get_val(fld)
    def has_field(self, fld) -> bool: return self.scan.has_field(fld)
    def close(self) -> None: self.scan.close()
