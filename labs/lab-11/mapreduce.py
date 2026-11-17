import re

from corpus import DOCS

N_PARTITIONS = 4


def records() -> list[tuple[str, str]]:
    return [(doc_id, title + " " + text) for doc_id, title, text in DOCS]


def run_mapreduce(inputs, map_fn, reduce_fn, n_partitions=N_PARTITIONS):
    mapped = []
    for key, value in inputs:
        mapped.extend(map_fn(key, value))

    partitions = shuffle(mapped, n_partitions)

    results = []
    for partition in partitions:
        for key, values in sorted(partition.items()):
            results.append(reduce_fn(key, values))
    return results


def map_words(doc_id: str, text: str) -> list[tuple[str, int]]:
    raise NotImplementedError


def partition_for(key: str, n_partitions: int) -> int:
    raise NotImplementedError


def shuffle(pairs: list[tuple[str, int]],
            n_partitions: int) -> list[dict[str, list[int]]]:
    raise NotImplementedError


def reduce_counts(word: str, values: list[int]) -> tuple[str, int]:
    raise NotImplementedError


if __name__ == "__main__":
    counts = run_mapreduce(records(), map_words, reduce_counts)
    for word, count in sorted(counts, key=lambda item: (-item[1], item[0]))[:15]:
        print(f"{count:4}  {word}")
