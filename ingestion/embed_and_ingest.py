"""Bolt B2 — embed sample images with Cohere Embed v4 and load both tiers.

    python embed_and_ingest.py --limit 300 --hot 60

- All embedded images -> S3 Vectors (full/cold catalog).
- The "hot" subset (highest sales_count) -> OpenSearch Serverless (fast tier).
Idempotent: put_vectors / OpenSearch upsert overwrite by key.
"""
import argparse
import json

import boto3
from tqdm import tqdm

import common
import config

s3vectors = boto3.client("s3vectors", region_name=config.REGION)


def put_s3_vectors(batch):
    vectors = [{
        "key": r["image_id"],
        "data": {"float32": r["vector"]},
        "metadata": {
            "title": r["title"][:512],
            "keywords": r["keywords"][:2000],
            "category": r["category"],
            "colors": r["colors"][:256],
            "artist_name": r["artist_name"][:256],
            "upload_date": r["upload_date"],
            "thumb_url": r["thumb_url"],
            "preview_url": r["preview_url"],
        },
    } for r in batch]
    s3vectors.put_vectors(
        vectorBucketName=config.VECTOR_BUCKET,
        indexName=config.VECTOR_INDEX,
        vectors=vectors,
    )


def get_opensearch_client():
    from opensearchpy import OpenSearch, RequestsHttpConnection
    from requests_aws4auth import AWS4Auth

    esc = boto3.client("opensearch", region_name=config.REGION)
    d = esc.describe_domain(DomainName=config.OS_DOMAIN)["DomainStatus"]
    endpoint = d.get("Endpoint")
    if not endpoint:
        raise RuntimeError("OpenSearch domain endpoint not ready; run deploy_opensearch.py --status --wait")
    creds = boto3.Session().get_credentials()
    auth = AWS4Auth(creds.access_key, creds.secret_key, config.REGION, "es",
                    session_token=creds.token)
    client = OpenSearch(
        hosts=[{"host": endpoint, "port": 443}],
        http_auth=auth, use_ssl=True, verify_certs=True,
        connection_class=RequestsHttpConnection, timeout=60,
    )
    return client


def ensure_os_index(client):
    if client.indices.exists(index=config.OS_INDEX):
        return
    client.indices.create(index=config.OS_INDEX, body={
        "settings": {"index": {"knn": True}},
        "mappings": {"properties": {
            "vector": {"type": "knn_vector", "dimension": config.EMBED_DIM,
                       "method": {"engine": "lucene", "name": "hnsw",
                                  "space_type": "cosinesimil"}},
            "image_id": {"type": "keyword"},
            "title": {"type": "text"},
            "keywords": {"type": "text"},
            "category": {"type": "keyword"},
            "thumb_url": {"type": "keyword"},
            "preview_url": {"type": "keyword"},
        }},
    })
    print(f"[opensearch] created index {config.OS_INDEX}")


def index_opensearch(client, batch):
    from opensearchpy import helpers
    actions = [{
        "_index": config.OS_INDEX,
        "_source": {
            "vector": r["vector"],
            "image_id": r["image_id"],
            "title": r["title"],
            "keywords": r["keywords"],
            "category": r["category"],
            "thumb_url": r["thumb_url"],
            "preview_url": r["preview_url"],
        },
    } for r in batch]
    helpers.bulk(client, actions)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=300, help="total images to embed -> S3 Vectors")
    ap.add_argument("--hot", type=int, default=60, help="top-N by sales_count -> OpenSearch")
    ap.add_argument("--no-opensearch", action="store_true")
    ap.add_argument("--batch", type=int, default=25)
    args = ap.parse_args()

    print(f"Embedding up to {args.limit} images with {config.EMBED_MODEL_ID} ...")
    embedded = []
    batch = []
    for rec in tqdm(common.iter_records(limit=args.limit), total=args.limit):
        try:
            img = common.download_image(rec["thumb_url"])
            rec["vector"] = common.embed_image_bytes(img)
        except Exception as e:
            tqdm.write(f"skip {rec['image_id']}: {e}")
            continue
        embedded.append(rec)
        batch.append(rec)
        if len(batch) >= args.batch:
            put_s3_vectors(batch)
            batch = []
    if batch:
        put_s3_vectors(batch)
    print(f"[s3vectors] ingested {len(embedded)} vectors into {config.VECTOR_INDEX}")

    if not args.no_opensearch and args.hot > 0:
        hot = sorted(embedded, key=lambda r: r["sales_count"], reverse=True)[: args.hot]
        try:
            client = get_opensearch_client()
            ensure_os_index(client)
            index_opensearch(client, hot)
            print(f"[opensearch] indexed {len(hot)} hot images into {config.OS_INDEX}")
        except Exception as e:
            print(f"[opensearch] skipped ({e})")

    # persist a manifest for export/debug
    with open("ingest_manifest.json", "w", encoding="utf-8") as f:
        json.dump({"count": len(embedded),
                   "image_ids": [r["image_id"] for r in embedded]}, f)
    print("done.")


if __name__ == "__main__":
    main()
