import time

import numpy as np
import ray


@ray.remote
class PixelCounter:
    def __init__(self):
        self.total_pixels = 0

    def add(self, num_pixels):
        self.total_pixels += num_pixels

    def get_total(self):
        return self.total_pixels


@ray.remote
def process_image_with_actor(image, counter_actor):
    ray.get(counter_actor.add.remote(image.shape[0] * image.shape[1]))
    time.sleep(1)
    return 255 - image


if __name__ == "__main__":
    ray.init()
    try:
        images = [np.random.randint(0, 255, (10, 10, 3)) for _ in range(8)]
        counter = PixelCounter.remote()
        task_refs = [process_image_with_actor.remote(image, counter) for image in images]
        results = ray.get(task_refs)
        expected_total = sum(image.shape[0] * image.shape[1] for image in images)
        final_total = ray.get(counter.get_total.remote())
        print(f"Expected total pixels: {expected_total}")
        print(f"Actual total from actor: {final_total}")
    finally:
        ray.shutdown()
