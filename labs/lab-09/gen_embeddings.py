"""Lab 9: the embedding dataset. Provided complete; nothing to generate.

The vectors are real. They are sentence embeddings (all-MiniLM-L6-v2) of 4,000
arXiv abstracts, 800 each from cs.DB, cs.IR, cs.LG, stat.ML, and cs.DC, pulled
from the arXiv API in August 2026. The model produces 384 dimensions; the
shipped vectors are reduced to DIM dimensions by PCA and unit-normalized, so
that pure-Python k-means and brute-force search stay fast enough to run in a
loop. The 40 queries are real questions (data/queries.txt) embedded the same way.

    data/arxiv_4000.f16        4,000 x DIM little-endian float16, row-major
    data/arxiv_4000_384.f16    the same vectors at the model's full 384 dims
    data/arxiv_4000.jsonl.gz   one line per vector: id, title, cat, date, abstract
    data/queries.f16           40 x DIM query vectors;  data/queries.txt  their text
    data/queries_384.f16       the 40 queries at 384 dims

load()          -> list of 4,000 unit vectors (lists of floats)
queries(v, n)   -> the first n query vectors
titles()        -> list of 4,000 titles, aligned with load()
question(i)     -> the text of query i
"""

import gzip
import json
import math
import os
import struct

DIM = 64
N = 4000
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def _read_f16(path: str, dim: int) -> list[list[float]]:
    """Unpack float16 rows and re-normalize each to unit length (float16
    rounding leaves norms at 0.999x; exact unit vectors make dot = cosine)."""
    raw = open(path, "rb").read()
    n = len(raw) // (2 * dim)
    flat = struct.unpack(f"<{n * dim}e", raw)
    out = []
    for i in range(n):
        v = flat[i * dim:(i + 1) * dim]
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / norm for x in v])
    return out


FILES = {64: ("arxiv_4000.f16", "queries.f16"),          # shipped default: PCA-reduced, fast
         384: ("arxiv_4000_384.f16", "queries_384.f16")}  # the model's own width, 6x the work


def load(dim: int = DIM) -> list[list[float]]:
    """dim=64 (default, shipped for speed) or dim=384 (the model's own width)."""
    return _read_f16(os.path.join(DATA, FILES[dim][0]), dim)


def queries(vectors=None, n: int = 10, dim: int = DIM) -> list[list[float]]:
    return _read_f16(os.path.join(DATA, FILES[dim][1]), dim)[:n]


def meta() -> list[dict]:
    with gzip.open(os.path.join(DATA, "arxiv_4000.jsonl.gz"), "rt") as f:
        return [json.loads(line) for line in f]


def titles() -> list[str]:
    return [m["title"] for m in meta()]


def question(i: int) -> str:
    return [l.strip() for l in open(os.path.join(DATA, "queries.txt")) if l.strip()][i]


def main():
    missing = [f for f in ("arxiv_4000.f16", "arxiv_4000.jsonl.gz", "queries.f16", "queries.txt")
               if not os.path.exists(os.path.join(DATA, f))]
    if missing:
        raise SystemExit(f"data/ is missing {missing}; re-clone the lab folder")
    v = load()
    print(f"{len(v)} vectors x {len(v[0])} dims, {len(queries(n=40))} queries; first title: {titles()[0][:70]}")


if __name__ == "__main__":
    main()
