import ray
import ray.data


def process_image(row):
    return {"processed_image": 255 - row["image"], "original_id": row["path"]}


if __name__ == "__main__":
    ray.init(address="auto")
    try:
        ds = ray.data.read_images("s3://YOUR-BUCKET/raw-images", include_paths=True)
        processed_ds = ds.map(process_image)
        processed_ds.write_parquet("s3://YOUR-BUCKET/processed-images")
    finally:
        ray.shutdown()
