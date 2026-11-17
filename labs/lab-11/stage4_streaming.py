from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image
import pyarrow.parquet as pq
import ray
import ray.data


def process_image(row):
    return {"processed_image": 255 - row["image"], "original_id": row["path"]}


if __name__ == "__main__":
    with TemporaryDirectory() as directory:
        source = Path(directory) / "images"
        output = Path(directory) / "processed"
        source.mkdir()
        for i in range(8):
            image = np.random.randint(0, 255, (10, 10, 3), dtype=np.uint8)
            Image.fromarray(image).save(source / f"{i}.png")
        ray.init()
        try:
            ds = ray.data.read_images(str(source), include_paths=True)
            processed_ds = ds.map(process_image)
            processed_ds.explain()
            processed_ds.write_parquet(str(output))
            rows = sum(pq.read_metadata(file).num_rows for file in output.glob("*.parquet"))
            print("written rows:", rows)
        finally:
            ray.shutdown()
