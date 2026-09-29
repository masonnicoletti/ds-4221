"""microdb · part 4 — the query engine. REFERENCE IMPLEMENTATION.

Shipped with Lab 6 so every lower layer behaves identically. Do not edit."""

from __future__ import annotations


class F:
    """Marks a predicate's right-hand side as a FIELD, not a literal."""

    def __init__(self, name: str):
        self.name = name


class Predicate:
    """A conjunction (AND) of simple comparisons."""

    OPS = {
        "=":  lambda a, b: a == b,
        ">":  lambda a, b: a > b,
        "<":  lambda a, b: a < b,
    }

    def __init__(self, *terms):
        self.terms = terms

    def is_satisfied(self, scan) -> bool:
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

    def next(self) -> bool:
        while self.scan.next():
            if self.predicate.is_satisfied(self.scan):
                return True
        return False

    def before_first(self) -> None: self.scan.before_first()
    def get_val(self, fld): return self.scan.get_val(fld)
    def has_field(self, fld) -> bool: return self.scan.has_field(fld)
    def close(self) -> None: self.scan.close()


class ProjectScan:
    """The underlying scan restricted to some fields.   (the SELECT list)"""

    def __init__(self, scan, fields: list[str]):
        self.scan = scan
        self.fields = fields

    def get_val(self, fld):
        if fld not in self.fields:
            raise ValueError(f"field {fld!r} was projected away")
        return self.scan.get_val(fld)

    def has_field(self, fld) -> bool:
        return fld in self.fields

    def before_first(self) -> None: self.scan.before_first()
    def next(self) -> bool: return self.scan.next()
    def close(self) -> None: self.scan.close()


class ProductScan:
    """Every row of `left` paired with every row of `right`."""

    def __init__(self, left, right):
        self.left = left
        self.right = right

    def before_first(self) -> None:
        self.left.before_first()
        self._left_ready = self.left.next()
        self.right.before_first()

    def next(self) -> bool:
        if not self._left_ready:
            return False
        if self.right.next():
            return True
        self.right.before_first()
        self._left_ready = self.left.next()
        if not self._left_ready:
            return False
        if self.right.next():
            return True
        self._left_ready = False
        return False

    def get_val(self, fld):
        if self.left.has_field(fld):
            return self.left.get_val(fld)
        return self.right.get_val(fld)

    def has_field(self, fld) -> bool:
        return self.left.has_field(fld) or self.right.has_field(fld)

    def close(self) -> None:
        self.left.close()
        self.right.close()


class CountingScan:
    """Wraps any scan and counts the rows that flow through it."""

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
