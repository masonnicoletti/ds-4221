import re

from corpus import DOCS


def word_counts(sc, lines):
    raise NotImplementedError


def main():
    from pyspark import SparkContext

    sc = SparkContext("local[*]", "microdb-wordcount")
    sc.setLogLevel("ERROR")

    texts = [title + " " + text for _, title, text in DOCS]
    lines = sc.parallelize(texts, numSlices=4)
    counts = word_counts(sc, lines)

    print("=== the DAG (read bottom-up; the stage break is the shuffle) ===")
    print(counts.toDebugString().decode())

    print("\n=== top 15 (collect() finally runs the plan) ===")
    for word, count in sorted(counts.collect(), key=lambda item: (-item[1], item[0]))[:15]:
        print(f"{count:4}  {word}")
    sc.stop()


if __name__ == "__main__":
    main()
