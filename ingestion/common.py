"""Shared helpers: Cohere Embed v4 calls + dataset iteration."""
import base64
import glob
import json
import os

import boto3
import requests

import config

_bedrock = boto3.client("bedrock-runtime", region_name=config.REGION)
_HEADERS = {"User-Agent": "Mozilla/5.0 (S3VectorsDemo)"}


def embed_texts(texts, input_type="search_query"):
    """Return a list of 1024-d float vectors for the given texts."""
    body = {
        "texts": texts,
        "input_type": input_type,
        "output_dimension": config.EMBED_DIM,
        "embedding_types": ["float"],
    }
    resp = _bedrock.invoke_model(modelId=config.EMBED_MODEL_ID, body=json.dumps(body))
    return json.loads(resp["body"].read())["embeddings"]["float"]


def embed_query(text):
    """Embed a single search query."""
    return embed_texts([text], input_type="search_query")[0]


def embed_image_bytes(img_bytes, media_type="image/jpeg"):
    """Embed a single image given raw bytes."""
    b64 = base64.b64encode(img_bytes).decode()
    data_uri = f"data:{media_type};base64,{b64}"
    body = {
        "images": [data_uri],
        "input_type": "image",
        "output_dimension": config.EMBED_DIM,
        "embedding_types": ["float"],
    }
    resp = _bedrock.invoke_model(modelId=config.EMBED_MODEL_ID, body=json.dumps(body))
    return json.loads(resp["body"].read())["embeddings"]["float"][0]


def download_image(url, timeout=20):
    r = requests.get(url, headers=_HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.content


def iter_records(limit=None):
    """Yield normalized image records from the Getty ImagesBank JSONL sample."""
    files = sorted(glob.glob(os.path.join(config.DATA_DIR, "*.json")))
    count = 0
    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                thumb = rec.get("etc3") or rec.get("etc2") or rec.get("etc1")
                preview = rec.get("etc1") or rec.get("etc2") or rec.get("etc3")
                if not preview:
                    continue
                yield {
                    "image_id": rec.get("image_id") or rec.get("id"),
                    "title": (rec.get("title") or "").strip(),
                    "keywords": rec.get("keywords") or "",
                    "category": rec.get("category") or "",
                    "colors": rec.get("colors") or "",
                    "artist_name": rec.get("artist_name") or "",
                    "sales_count": int(rec.get("sales_count") or 0),
                    "upload_date": rec.get("upload_date") or "",
                    "thumb_url": thumb,
                    "preview_url": preview,
                }
                count += 1
                if limit and count >= limit:
                    return
