import math
import struct
from pathlib import Path

DIM = 64
DATA = Path(__file__).with_name("data") / "arxiv_4000.f16"


def load() -> list[list[float]]:
    raw = DATA.read_bytes()
    count = len(raw) // (2 * DIM)
    values = struct.unpack(f"<{count * DIM}e", raw)
    vectors = []
    for i in range(count):
        vector = values[i * DIM:(i + 1) * DIM]
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        vectors.append([x / norm for x in vector])
    return vectors
