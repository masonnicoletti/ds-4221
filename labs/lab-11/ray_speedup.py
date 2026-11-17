import time

import ray

import embeddings

VECTORS = embeddings.load()
K = 10
N_DOCS = 200


def neighbors(doc: int) -> list[int]:
    query = VECTORS[doc]
    scored = []
    for neighbor, vector in enumerate(VECTORS):
        if neighbor != doc:
            scored.append((sum(a * b for a, b in zip(query, vector)), neighbor))
    scored.sort(reverse=True)
    return [neighbor for _, neighbor in scored[:K]]


def knn_all_serial(docs: list[int]) -> list[list[int]]:
    return [neighbors(doc) for doc in docs]


@ray.remote
def knn_remote(doc: int) -> list[int]:
    raise NotImplementedError


def knn_all_parallel(docs: list[int]) -> list[list[int]]:
    raise NotImplementedError


if __name__ == "__main__":
    from corpus import DOCS

    ray.init(num_cpus=None, include_dashboard=False,
             logging_level="error", log_to_driver=False)
    docs = list(range(N_DOCS))

    start = time.perf_counter()
    serial = knn_all_serial(docs)
    serial_time = time.perf_counter() - start

    start = time.perf_counter()
    parallel = knn_all_parallel(docs)
    parallel_time = time.perf_counter() - start

    print(f"{len(docs)} documents, 10 nearest neighbors each, brute force over {len(VECTORS):,} vectors")
    print(f"serial:    {serial_time:6.2f} s")
    print(f"parallel:  {parallel_time:6.2f} s     speedup: {serial_time / parallel_time:.1f}x")
    print(f"identical results: {serial == parallel}")
    print(f"\nneighbors of [{DOCS[docs[0]][1][:60]}]:")
    for neighbor in serial[0][:3]:
        print(f"   {DOCS[neighbor][1][:70]}")
    ray.shutdown()
