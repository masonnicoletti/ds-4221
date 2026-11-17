import time

import numpy as np
import ray

total_pixels_processed = 0


@ray.remote
def process_image_and_count(image):
    global total_pixels_processed
    num_pixels = image.shape[0] * image.shape[1]
    total_pixels_processed += num_pixels
    print(f"Task processing {num_pixels} pixels. Local total: {total_pixels_processed}")
    time.sleep(1)
    return 255 - image


if __name__ == "__main__":
    ray.init()
    try:
        images = [np.random.randint(0, 255, (10, 10, 3)) for _ in range(4)]
        ray.get([process_image_and_count.remote(image) for image in images])
        expected_total = sum(image.shape[0] * image.shape[1] for image in images)
        print(f"Expected total pixels: {expected_total}")
        print(f"Actual total pixels in main script: {total_pixels_processed}")
    finally:
        ray.shutdown()
