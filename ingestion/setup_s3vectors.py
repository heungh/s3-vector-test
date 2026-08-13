"""Create the S3 Vectors bucket + index (idempotent). S3 Vectors is not yet a
CloudFormation resource type, so it is provisioned here."""
import boto3
import config

s3vectors = boto3.client("s3vectors", region_name=config.REGION)


def main():
    try:
        s3vectors.create_vector_bucket(
            vectorBucketName=config.VECTOR_BUCKET,
            encryptionConfiguration={"sseType": "AES256"},
        )
        print(f"[s3vectors] created bucket {config.VECTOR_BUCKET}")
    except Exception as e:
        if "AlreadyExists" in str(e) or "already exists" in str(e):
            print(f"[s3vectors] bucket exists {config.VECTOR_BUCKET}")
        else:
            raise

    try:
        s3vectors.create_index(
            vectorBucketName=config.VECTOR_BUCKET,
            indexName=config.VECTOR_INDEX,
            dimension=config.EMBED_DIM,
            distanceMetric="cosine",
            dataType="float32",
            metadataConfiguration={
                "nonFilterableMetadataKeys": [
                    "title", "keywords", "thumb_url", "preview_url",
                    "colors", "artist_name", "upload_date",
                ]
            },
        )
        print(f"[s3vectors] created index {config.VECTOR_INDEX} (dim={config.EMBED_DIM}, cosine)")
    except Exception as e:
        if "AlreadyExists" in str(e) or "already exists" in str(e):
            print(f"[s3vectors] index exists {config.VECTOR_INDEX}")
        else:
            raise


if __name__ == "__main__":
    main()
