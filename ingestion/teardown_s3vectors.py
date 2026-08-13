"""Delete the S3 Vectors index + bucket."""
import boto3
import config

c = boto3.client("s3vectors", region_name=config.REGION)

try:
    c.delete_index(vectorBucketName=config.VECTOR_BUCKET, indexName=config.VECTOR_INDEX)
    print("[s3vectors] index deleted")
except Exception as e:
    print(f"[s3vectors] index: {e}")

try:
    c.delete_vector_bucket(vectorBucketName=config.VECTOR_BUCKET)
    print("[s3vectors] bucket deleted")
except Exception as e:
    print(f"[s3vectors] bucket: {e}")
