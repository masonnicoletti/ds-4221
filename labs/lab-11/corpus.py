import gzip
import json
from pathlib import Path

DATA = Path(__file__).with_name("data") / "arxiv_4000.jsonl.gz"


def _load() -> list[tuple[str, str, str]]:
    with gzip.open(DATA, "rt") as source:
        return [(doc["id"], doc["title"], doc["abstract"]) for doc in map(json.loads, source)]


DOCS = _load()
