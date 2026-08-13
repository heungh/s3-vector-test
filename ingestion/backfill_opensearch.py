"""Copy a subset of vectors from S3 Vectors into the OpenSearch hot tier (no re-embedding).

    python backfill_opensearch.py --hot 200
"""
import argparse
import boto3
from opensearchpy import helpers

import config
from embed_and_ingest import get_opensearch_client, ensure_os_index

s3v = boto3.client("s3vectors", region_name=config.REGION)


def list_all(limit):
    out, token = [], None
    while len(out) < limit:
        kw = dict(vectorBucketName=config.VECTOR_BUCKET, indexName=config.VECTOR_INDEX,
                  returnData=True, returnMetadata=True, maxResults=min(500, limit - len(out)))
        if token:
            kw["nextToken"] = token
        r = s3v.list_vectors(**kw)
        out.extend(r.get("vectors", []))
        token = r.get("nextToken")
        if not token:
            break
    return out[:limit]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hot", type=int, default=200)
    args = ap.parse_args()

    client = get_opensearch_client()
    ensure_os_index(client)

    vectors = list_all(args.hot)
    print(f"[s3vectors] fetched {len(vectors)} vectors")

    actions = []
    for v in vectors:
        md = v.get("metadata", {}) or {}
        vec = v.get("data", {}).get("float32")
        if not vec:
            continue
        actions.append({
            "_index": config.OS_INDEX,
            "_id": v["key"],
            "_source": {
                "vector": vec, "image_id": v["key"],
                "title": md.get("title", ""), "keywords": md.get("keywords", ""),
                "category": md.get("category", ""),
                "thumb_url": md.get("thumb_url", ""),
                "preview_url": md.get("preview_url", ""),
            },
        })
    ok, errors = helpers.bulk(client, actions, stats_only=False)
    print(f"[opensearch] indexed {ok} docs into {config.OS_INDEX}; errors={len(errors) if isinstance(errors, list) else errors}")
    client.indices.refresh(index=config.OS_INDEX)
    print("[opensearch] refreshed")


if __name__ == "__main__":
    main()
