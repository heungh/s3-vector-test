"""Hybrid search Lambda (behind API Gateway + CloudFront):
embed the query with Cohere Embed v4, then search S3 Vectors and/or a managed OpenSearch
domain in parallel and fuse the results.

modes:
  fast          -> OpenSearch (hot tier) only
  comprehensive -> S3 Vectors (full catalog) only
  hybrid        -> both, fused (default)
"""
import concurrent.futures
import json
import os
import time
import urllib.request

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

REGION = os.environ.get("AWS_REGION", "us-east-1")
MODEL = os.environ.get("EMBED_MODEL_ID", "cohere.embed-v4:0")
DIM = int(os.environ.get("EMBED_DIM", "1024"))
BUCKET = os.environ["VECTOR_BUCKET"]
INDEX = os.environ.get("VECTOR_INDEX", "image-embeddings")
OS_ENDPOINT = os.environ.get("OPENSEARCH_ENDPOINT", "").rstrip("/")  # https://...
OS_INDEX = os.environ.get("OPENSEARCH_INDEX", "images-hot")

_br = boto3.client("bedrock-runtime", region_name=REGION)
_s3v = boto3.client("s3vectors", region_name=REGION)
_session = boto3.Session()

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "content-type",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
}


def _resp(status, obj):
    return {
        "statusCode": status,
        "headers": {**CORS, "content-type": "application/json; charset=utf-8"},
        "body": json.dumps(obj, ensure_ascii=False),
    }


def _embed_query(text):
    body = {"texts": [text], "input_type": "search_query",
            "output_dimension": DIM, "embedding_types": ["float"]}
    r = _br.invoke_model(modelId=MODEL, body=json.dumps(body))
    return json.loads(r["body"].read())["embeddings"]["float"][0]


def _search_s3vectors(vec, topk):
    resp = _s3v.query_vectors(
        vectorBucketName=BUCKET, indexName=INDEX,
        queryVector={"float32": vec}, topK=topk,
        returnDistance=True, returnMetadata=True,
    )
    out = []
    for v in resp.get("vectors", []):
        md = v.get("metadata", {}) or {}
        out.append({
            "image_id": v.get("key"), "title": md.get("title", ""),
            "keywords": md.get("keywords", ""),
            "thumb_url": md.get("thumb_url", ""),
            "preview_url": md.get("preview_url") or md.get("thumb_url", ""),
            "score": max(0.0, 1.0 - float(v.get("distance", 1.0))),
            "tier": "s3vectors",
        })
    return out


def _search_opensearch(vec, topk):
    if not OS_ENDPOINT:
        return []
    url = f"{OS_ENDPOINT}/{OS_INDEX}/_search"
    payload = json.dumps({
        "size": topk,
        "query": {"knn": {"vector": {"vector": vec, "k": topk}}},
        "_source": ["image_id", "title", "keywords", "thumb_url", "preview_url"],
    })
    creds = _session.get_credentials().get_frozen_credentials()
    aws_req = AWSRequest(method="POST", url=url, data=payload,
                         headers={"Content-Type": "application/json"})
    SigV4Auth(creds, "es", REGION).add_auth(aws_req)
    req = urllib.request.Request(url, data=payload.encode("utf-8"),
                                 headers=dict(aws_req.headers), method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
    out = []
    for h in data.get("hits", {}).get("hits", []):
        s = h.get("_source", {})
        out.append({
            "image_id": s.get("image_id"), "title": s.get("title", ""),
            "keywords": s.get("keywords", ""),
            "thumb_url": s.get("thumb_url", ""),
            "preview_url": s.get("preview_url") or s.get("thumb_url", ""),
            "score": min(1.0, float(h.get("_score", 0.0))),
            "tier": "opensearch",
        })
    return out


def _fuse(lists, topk):
    best = {}
    for lst in lists:
        for r in lst:
            k = r["image_id"]
            if k not in best or r["score"] > best[k]["score"]:
                best[k] = r
    return sorted(best.values(), key=lambda x: x["score"], reverse=True)[:topk]


def handler(event, context):
    method = (event.get("requestContext", {}).get("http", {}).get("method")) or "GET"
    if method == "OPTIONS":
        return {"statusCode": 200, "headers": CORS, "body": ""}

    expected = os.environ.get("ORIGIN_SECRET")
    if expected:
        hdrs = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
        if hdrs.get("x-origin-secret") != expected:
            return _resp(403, {"error": "forbidden"})

    try:
        qs = event.get("queryStringParameters") or {}
        q = (qs.get("q") or "").strip()
        mode = (qs.get("mode") or "hybrid").lower()
        topk_raw = qs.get("topK")
        if not q and event.get("body"):
            body = json.loads(event.get("body") or "{}")
            q = (body.get("query") or "").strip()
            mode = (body.get("mode") or mode).lower()
            topk_raw = topk_raw or body.get("topK")
        if mode not in ("fast", "comprehensive", "hybrid"):
            mode = "hybrid"
        topk = min(int(topk_raw or 12), 30)
        if not q:
            return _resp(400, {"error": "query is required"})

        t0 = time.time()
        vec = _embed_query(q)
        embed_ms = int((time.time() - t0) * 1000)

        want_os = mode in ("fast", "hybrid")
        want_s3 = mode in ("comprehensive", "hybrid")
        timings = {"embed_ms": embed_ms}
        tiers = []
        lists = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            fut_os = ex.submit(_search_opensearch, vec, topk) if want_os else None
            fut_s3 = ex.submit(_search_s3vectors, vec, topk) if want_s3 else None
            if fut_os is not None:
                t = time.time()
                try:
                    r = fut_os.result()
                    lists.append(r)
                    tiers.append("opensearch")
                except Exception as e:
                    print("opensearch error:", e)
                timings["opensearch_ms"] = int((time.time() - t) * 1000)
            if fut_s3 is not None:
                t = time.time()
                r = fut_s3.result()
                lists.append(r)
                tiers.append("s3vectors")
                timings["s3vectors_ms"] = int((time.time() - t) * 1000)

        # fallback: if fast requested but OpenSearch empty/unavailable, use S3 Vectors
        if not any(lists):
            lists = [_search_s3vectors(vec, topk)]
            if "s3vectors" not in tiers:
                tiers.append("s3vectors")

        results = _fuse(lists, topk)
        timings["total_ms"] = int((time.time() - t0) * 1000)
        return _resp(200, {"query": q, "mode": mode, "results": results,
                           "timings": timings, "tiersQueried": tiers})
    except Exception as e:
        return _resp(500, {"error": str(e)})
