import time

import ray


def process_image(image):
    time.sleep(1)
    return 255 - image


@ray.remote
def process_image_task(image):
    return process_image(image)


def process_parallel(images):
    refs = [process_image_task.remote(image) for image in images]
    return ray.get(refs)


@ray.remote
class PixelCounter:
    def __init__(self):
        self.total = 0

    def add(self, count):
        self.total += count

    def get_total(self):
        return self.total


@ray.remote
def process_and_count(image, counter):
    processed = process_image(image)
    ray.get(counter.add.remote(image.shape[0] * image.shape[1]))
    return processed


def process_row(row):
    return {**row, "image": process_image(row["image"])}
