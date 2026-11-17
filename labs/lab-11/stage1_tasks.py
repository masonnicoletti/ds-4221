import time

import numpy as np
import ray

@ray.remote
def process_image(image):
    time.sleep(1)
    return 255 - image


if __name__ == "__main__":
    ray.init()
    try:
        images = [np.random.randint(0, 255, (10, 10, 3)) for _ in range(8)]
        start_time = time.time()
        result_refs = [process_image.remote(image) for image in images]
        results = ray.get(result_refs)
        print(f"Processed {len(results)} images in {time.time() - start_time:.2f} seconds.")
    finally:
        ray.shutdown()
