"""Parallel + batched ingestion for benchmarking throughput into S3 Vectors.

Pipeline per chunk:
  concurrent image downloads -> batched Cohere Embed v4 calls (concurrent) -> batched put_vectors
Streaming by chunk to bound memory.

    python parallel_ingest.py --limit 1000 --dl-workers 24 --embed-batch 8 --embed-workers 8 --put-batch 200
"""
import argparse
import base64
import concurrent.futures as cf
import json
import time

import boto3
from botocore.config import Config

import common
import config

_cfg = Config(retries={"max_attempts": 8, "mode": "adaptive"}, max_pool_connections=50)
_br = boto3.client("bedrock-runtime", region_name=config.REGION, config=_cfg)
_s3v = boto3.client("s3vectors", region_name=config.REGION, config=_cfg)


def download(rec):
    try:
        img = common.download_image(rec["thumb_url"])
        rec["_b64"] = "data:image/jpeg;base64," + base64.b64encode(img).decode()
        return rec
    except Exception:
        return None


def embed_batch(recs):
    uris = [r["_b64"] for r in recs]
    body = {"images": uris, "input_type": "image",
            "output_dimension": config.EMBED_DIM, "embedding_types": ["float"]}
    resp = _br.invoke_model(modelId=config.EMBED_MODEL_ID, body=json.dumps(body))
    vecs = json.loads(resp["body"].read())["embeddings"]["float"]
    for r, v in zip(recs, vecs):
        r["_vec"] = v
    return recs


def put_batch(recs):
    vectors = [{
        "key": r["image_id"],
        "data": {"float32": r["_vec"]},
        "metadata": {
            "title": r["title"][:512], "keywords": r["keywords"][:2000],
            "category": r["category"], "thumb_url": r["thumb_url"],
            "preview_url": r["preview_url"],
        },
    } for r in recs if r.get("_vec")]
    if vectors:
        _s3v.put_vectors(vectorBucketName=config.VECTOR_BUCKET,
                         indexName=config.VECTOR_INDEX, vectors=vectors)
    return len(vectors)


def chunks(it, n):
    buf = []
    for x in it:
        buf.append(x)
        if len(buf) >= n:
            yield buf
            buf = []
    if buf:
        yield buf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--dl-workers", type=int, default=24)
    ap.add_argument("--embed-batch", type=int, default=8)
    ap.add_argument("--embed-workers", type=int, default=8)
    ap.add_argument("--put-batch", type=int, default=200)
    ap.add_argument("--chunk", type=int, default=2000)
    a = ap.parse_args()

    t0 = time.time()
    done = 0
    manifest = []  # (image_id, sales_count) for hot-tier selection
    for chunk in chunks(common.iter_records(limit=a.limit), a.chunk):
        # 1) concurrent downloads
        with cf.ThreadPoolExecutor(max_workers=a.dl_workers) as ex:
            downloaded = [r for r in ex.map(download, chunk) if r]

        # 2) batched + concurrent embedding
        batches = [downloaded[i:i + a.embed_batch] for i in range(0, len(downloaded), a.embed_batch)]
        embedded = []
        with cf.ThreadPoolExecutor(max_workers=a.embed_workers) as ex:
            for res in ex.map(lambda b: _safe_embed(b), batches):
                embedded.extend(res)

        # 3) batched + concurrent put_vectors
        pbatches = [embedded[i:i + a.put_batch] for i in range(0, len(embedded), a.put_batch)]
        with cf.ThreadPoolExecutor(max_workers=8) as ex:
            for n in ex.map(put_batch, pbatches):
                done += n
        for r in embedded:
            if r.get("_vec"):
                manifest.append((r["image_id"], r.get("sales_count", 0)))

        rate = done / (time.time() - t0)
        print(f"  ingested {done} | {rate:.1f} vec/s")

    with open("ingest_manifest.json", "w") as f:
        json.dump({"ids": manifest}, f)
    print(f"  wrote manifest ({len(manifest)} ids)")

    dt = time.time() - t0
    rate = done / dt if dt else 0
    print(f"\nDONE: {done} vectors in {dt:.1f}s = {rate:.1f} vec/s")
    print(f"extrapolate 851,485 -> {851485 / rate / 60:.1f} min ({851485 / rate / 3600:.2f} h)" if rate else "")


def _safe_embed(b):
    try:
        return embed_batch(b)
    except Exception as e:
        print("  embed error:", str(e)[:120])
        return []


if __name__ == "__main__":
    main()
