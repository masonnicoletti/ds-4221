import time

import numpy as np

def process_image(image):
    time.sleep(1)
    return 255 - image


if __name__ == "__main__":
    images = [np.random.randint(0, 255, (10, 10, 3)) for _ in range(8)]
    start_time = time.time()
    results = [process_image(image) for image in images]
    print(f"Processed {len(results)} images in {time.time() - start_time:.2f} seconds.")
