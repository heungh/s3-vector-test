"""Copy the HOT subset (top X% by popularity) from S3 Vectors into OpenSearch — no re-embedding.

Reads ingest_manifest.json (image_id, sales_count) written by parallel_ingest.py, picks the
top `--pct` by sales_count, fetches those vectors from S3 Vectors (get_vectors), and bulk-indexes
them into the OpenSearch hot tier.

    python backfill_hot.py --pct 20
"""
import argparse
import json

import boto3
from opensearchpy import helpers

import config
from embed_and_ingest import get_opensearch_client, ensure_os_index

s3v = boto3.client("s3vectors", region_name=config.REGION)


def get_vectors(keys):
    out = []
    for i in range(0, len(keys), 100):
        batch = keys[i:i + 100]
        r = s3v.get_vectors(
            vectorBucketName=config.VECTOR_BUCKET, indexName=config.VECTOR_INDEX,
            keys=batch, returnData=True, returnMetadata=True,
        )
        out.extend(r.get("vectors", []))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pct", type=float, default=20.0, help="top %% by sales_count -> OpenSearch")
    ap.add_argument("--manifest", default="ingest_manifest.json")
    a = ap.parse_args()

    with open(a.manifest) as f:
        ids = json.load(f)["ids"]  # list of [image_id, sales_count]
    ids.sort(key=lambda x: x[1], reverse=True)
    n = max(1, int(len(ids) * a.pct / 100))
    hot_keys = [i[0] for i in ids[:n]]
    print(f"total={len(ids)}  hot(top {a.pct}%)={len(hot_keys)}")

    client = get_opensearch_client()
    ensure_os_index(client)

    vectors = get_vectors(hot_keys)
    print(f"fetched {len(vectors)} vectors from S3 Vectors")

    actions = []
    for v in vectors:
        md = v.get("metadata", {}) or {}
        vec = v.get("data", {}).get("float32")
        if not vec:
            continue
        actions.append({
            "_index": config.OS_INDEX, "_id": v["key"],
            "_source": {
                "vector": vec, "image_id": v["key"],
                "title": md.get("title", ""), "keywords": md.get("keywords", ""),
                "category": md.get("category", ""),
                "thumb_url": md.get("thumb_url", ""), "preview_url": md.get("preview_url", ""),
            },
        })
    ok, errors = helpers.bulk(client, actions, chunk_size=500, stats_only=False)
    client.indices.refresh(index=config.OS_INDEX)
    print(f"[opensearch] indexed {ok} hot docs; errors={len(errors) if isinstance(errors, list) else errors}")


if __name__ == "__main__":
    main()
