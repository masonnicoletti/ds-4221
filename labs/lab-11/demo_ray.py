import time

import numpy as np
import ray
import ray.data

from ray_images import PixelCounter, process_and_count, process_image, process_parallel, process_row


if __name__ == "__main__":
    ray.init(include_dashboard=False, log_to_driver=False)
    try:
        images = [np.full((10, 10, 3), value, dtype=np.uint8) for value in range(8)]
        start = time.perf_counter()
        serial = [process_image(image) for image in images]
        serial_time = time.perf_counter() - start
        start = time.perf_counter()
        parallel = process_parallel(images)
        parallel_time = time.perf_counter() - start
        print(f"serial: {serial_time:.2f} s; parallel: {parallel_time:.2f} s")
        print("Each call includes a one-second artificial wait.")
        same = len(serial) == len(parallel) and all(np.array_equal(a, b) for a, b in zip(serial, parallel))
        print("same images:", same)

        counter = PixelCounter.remote()
        result_refs = [process_and_count.remote(image, counter) for image in images]
        ray.get(result_refs)
        print("pixels:", ray.get(counter.get_total.remote()))
        print("RGB channel values:", sum(image.size for image in images))

        rows = [{"id": i, "image": image} for i, image in enumerate(images)]
        result = ray.data.from_items(rows).map(process_row).take_all()
        print("small local Ray Data result:", len(result), "rows")
    finally:
        ray.shutdown()
