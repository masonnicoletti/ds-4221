import time

import numpy as np
import ray


@ray.remote
def stat_summary(values):
    time.sleep(2)
    stat_report = {
        "mean": np.mean(values).round(2),
        "std": np.std(values).round(2),
        "min": np.min(values),
        "max": np.max(values),
        "sum": np.sum(values),
        "count": len(values),
    }
    lines = "\n".join(f"{name}: {number}" for name, number in stat_report.items())
    return "Summary Statistics:\n" + lines


if __name__ == "__main__":
    ray.init()
    try:

        samples = [
            np.random.randint(0, 100, size=np.random.randint(1, 20))
            for _ in range(5)
        ]

        start_time = time.time()

        result_refs = [stat_summary.remote(sample) for sample in samples]
        results = ray.get(result_refs)
        
        for result in results:
            print(result)
            print()
        print(f"Processed {len(results)} lists in {time.time() - start_time:.2f} seconds.")
    
    finally:
        ray.shutdown()