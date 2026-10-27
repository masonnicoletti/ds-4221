"""Lab 9, Part 3 — the recall-vs-speed dial. Run:  python3 measure_recall.py

One table, the whole ANN trade: as `probe` grows, recall climbs toward
exact and the comparison count climbs toward brute force. Every vector
database you will ever configure exposes this dial under some name
(nprobe, ef_search, num_candidates).

Deterministic (seeded data + queries) — record the table.
"""

import sys

import gen_embeddings
from microvector import BruteForceIndex, IVFIndex, recall_at_k, dot

import os

if not os.path.exists("data/embeddings.txt"):
    gen_embeddings.main()
DIM = int(sys.argv[1]) if len(sys.argv) > 1 else gen_embeddings.DIM   # python3 measure_recall.py 384
VECTORS = gen_embeddings.load(dim=DIM)
QUERIES = gen_embeddings.queries(VECTORS, n=40, dim=DIM)   # 40 real questions, embedded like the docs
K = 10


def truth_for(q):
    scored = sorted(((dot(q, v), i) for i, v in enumerate(VECTORS)),
                    key=lambda t: (-t[0], t[1]))
    return scored[:K]


def show_titles(index, q_index: int, k: int = 3) -> None:
    """Print what a query actually retrieves: the payoff of real vectors."""
    q = gen_embeddings.queries(n=40, dim=DIM)[q_index]
    titles = gen_embeddings.titles()
    print(f"   Q: {gen_embeddings.question(q_index)}")
    for score, i in index.search(q, k):
        print(f"      {score:.3f}  {titles[i][:78]}")


def main():
    n = len(VECTORS)
    truths = [truth_for(q) for q in QUERIES]

    print(f"{len(VECTORS)} real arXiv abstracts as {len(VECTORS[0])}-d MiniLM vectors, {len(QUERIES)} real questions, top-{K}, 20 clusters\n")
    print("0. What a query returns (brute force, top-3 by cosine):")
    show_titles(BruteForceIndex(VECTORS), 2)
    show_titles(BruteForceIndex(VECTORS), 9)
    print()
    print(f"{'index':>12} | {'probe':>5} | {'avg recall@10':>13} | {'comparisons/query':>17} | {'vs exact':>8}")
    print("-" * 70)

    bf = BruteForceIndex(VECTORS)
    bf.search(QUERIES[0], K)
    exact_cost = bf.comparisons
    print(f"{'brute force':>12} | {'-':>5} | {1.0:>13.3f} | {exact_cost:>17,} | {'1.0x':>8}")

    ivf = IVFIndex(VECTORS, n_clusters=20)
    for probe in (1, 2, 4, 8, 16, 20):
        total_recall, total_cost = 0.0, 0
        for q, truth in zip(QUERIES, truths):
            ivf.comparisons = 0
            got = ivf.search(q, K, probe=probe)
            total_recall += recall_at_k(got, truth, K)
            total_cost += ivf.comparisons
        avg_r = total_recall / len(QUERIES)
        avg_c = total_cost // len(QUERIES)
        print(f"{'IVF':>12} | {probe:>5} | {avg_r:>13.3f} | {avg_c:>17,} | "
              f"{exact_cost / avg_c:>7.1f}x")

    print("\nRecord the table, then think about these for class:")
    print("  1. Between which two probe values does recall stop being worth")
    print("     the extra comparisons, for YOUR taste? Defend the cut.")
    print("  2. probe=20 probes every list. Why is its recall 1.0 by")
    print("     construction, and its cost slightly above brute force?")
    print("  3. Your RAG project will sit behind this exact dial. What recall")
    print("     would you demand for retrieved evidence, and why?")


if __name__ == "__main__":
    main()
