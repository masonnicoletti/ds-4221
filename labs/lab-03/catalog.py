"""microdb · part 3 — the system catalog. Provided complete (do not edit).

The database describes itself: two ordinary tables, scanned with your
TableScan, record every table's schema and layout.

    table_catalog(tblname varchar(16), slotsize int)
    field_catalog(tblname varchar(16), fldname varchar(16),
                  fldtype varchar(8), length int, offset int)

The bootstrap trick: the catalog tables' OWN layouts can't be read from the
catalog (chicken and egg), so they are hardcoded below — computed by your
Layout class at import time. Everything else about them is ordinary.

Note what this file is: the first *customer* of your Lab 3 code. It does
nothing but construct Schemas and drive TableScans — if your record layer
is correct, the catalog simply works.
"""

from __future__ import annotations

from record_manager import Schema, Layout, TableScan, INT, STR


def _table_catalog_schema() -> Schema:
    return Schema().add_string_field("tblname", 16).add_int_field("slotsize")


def _field_catalog_schema() -> Schema:
    return (Schema()
            .add_string_field("tblname", 16)
            .add_string_field("fldname", 16)
            .add_string_field("fldtype", 8)
            .add_int_field("length")
            .add_int_field("offset"))


class Catalog:
    def __init__(self, bm, fm):
        self.bm = bm
        self.fm = fm
        # Bootstrap: the catalog's own layouts are computed, not looked up.
        self.tcat_layout = Layout(_table_catalog_schema())
        self.fcat_layout = Layout(_field_catalog_schema())

    def create_table(self, tblname: str, schema: Schema) -> Layout:
        """Record `tblname`'s schema in the catalog; return its Layout."""
        layout = Layout(schema)
        ts = TableScan(self.bm, self.fm, "table_catalog", self.tcat_layout)
        ts.insert()
        ts.set_string("tblname", tblname)
        ts.set_int("slotsize", layout.slot_size)
        ts.close()
        ts = TableScan(self.bm, self.fm, "field_catalog", self.fcat_layout)
        for fld in schema.fields():
            ts.insert()
            ts.set_string("tblname", tblname)
            ts.set_string("fldname", fld)
            ts.set_string("fldtype", schema.type_of(fld))
            ts.set_int("length", schema.length_of(fld))
            ts.set_int("offset", layout.offset(fld))
        ts.close()
        return layout

    def get_layout(self, tblname: str) -> Layout:
        """Rebuild `tblname`'s Layout from the catalog tables."""
        slot_size = -1
        ts = TableScan(self.bm, self.fm, "table_catalog", self.tcat_layout)
        while ts.next():
            if ts.get_string("tblname") == tblname:
                slot_size = ts.get_int("slotsize")
        ts.close()
        if slot_size < 0:
            raise KeyError(f"no such table in catalog: {tblname!r}")
        schema, offsets = Schema(), {}
        rows = []
        ts = TableScan(self.bm, self.fm, "field_catalog", self.fcat_layout)
        while ts.next():
            if ts.get_string("tblname") == tblname:
                rows.append((ts.get_int("offset"), ts.get_string("fldname"),
                             ts.get_string("fldtype"), ts.get_int("length")))
        ts.close()
        for off, fld, ftype, length in sorted(rows):
            if ftype == INT:
                schema.add_int_field(fld)
            else:
                schema.add_string_field(fld, length)
            offsets[fld] = off
        return Layout.from_metadata(schema, offsets, slot_size)
