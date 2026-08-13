"""Shared configuration — everything is read from environment variables so that no
account IDs, ARNs, or resource names are hard-coded. See ../.env.sample."""
import os
import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
PROJECT = os.environ.get("PROJECT_NAME", "s3-vector-demo")

ACCOUNT_ID = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]

# Embedding model (Cohere Embed v4 on Bedrock — multimodal + multilingual)
EMBED_MODEL_ID = os.environ.get("EMBED_MODEL_ID", "cohere.embed-v4:0")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "1024"))

# S3 Vectors (full / cold catalog)
VECTOR_BUCKET = os.environ.get("VECTOR_BUCKET", f"{PROJECT}-{ACCOUNT_ID}-vectors")
VECTOR_INDEX = os.environ.get("VECTOR_INDEX", "image-embeddings")

# Managed OpenSearch domain (hot / fast tier)
OS_DOMAIN = os.environ.get("OS_DOMAIN", f"{PROJECT}-os")
OS_INDEX = os.environ.get("OS_INDEX", "images-hot")

# Dataset: JSONL files (one JSON object per line) with image metadata + CDN URLs.
# Defaults to the small bundled sample; point DATA_DIR at your own dataset to scale up.
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "sample_data"))

VECTOR_INDEX_ARN = (
    f"arn:aws:s3vectors:{REGION}:{ACCOUNT_ID}:bucket/{VECTOR_BUCKET}/index/{VECTOR_INDEX}"
)
