# Installation Guide

## 1. Prerequisites

- An AWS account with permissions to create IAM roles, CloudFormation stacks, Lambda,
  API Gateway, OpenSearch, S3, and CloudFront.
- **Amazon Bedrock model access enabled** for `cohere.embed-v4:0` in your region
  (Bedrock console → Model access).
- **Amazon S3 Vectors** available in your region (default `us-east-1`).
- Local tooling:
  - AWS CLI v2, configured (`aws configure` or SSO) — the deploy uses your credential chain.
  - Python 3.11+ and `pip`
  - Node.js 18+ and `npm`
  - `zip`, `openssl` (present on macOS/Linux by default)

## 2. Configure

```bash
cp .env.sample .env
```
Edit `.env`:

| Variable | Meaning |
|----------|---------|
| `AWS_REGION` | Region to deploy into (needs Bedrock + S3 Vectors). |
| `PROJECT_NAME` | Prefix for all resource names. |
| `OPENSEARCH_INSTANCE_TYPE` | `r6g.large.search` (recommended for k-NN), `m6g.large.search`, or `t3.small.search` (dev). |
| `EMBED_MODEL_ID` / `EMBED_DIM` | Embedding model + dimension (`cohere.embed-v4:0` / `1024`). |
| `INGEST_LIMIT` | How many images to embed into S3 Vectors (the full catalog). |
| `HOT_PCT` | Top X% (by popularity) copied into OpenSearch (hot tier), no re-embedding. |
| `INGEST_EMBED_MODEL_ID` | Bulk-embed model; `us.cohere.embed-v4:0` (cross-region profile) for higher throughput. |
| `ORIGIN_SECRET` | Leave blank to auto-generate. |
| `DATA_DIR` | Optional — path to your own JSONL dataset (defaults to the bundled sample). |

> **No credentials in `.env`.** Access keys come from your AWS CLI/SSO/environment.
> Account ID, ARNs, and endpoints are resolved automatically — nothing sensitive is stored.

## 3. Deploy (one click)

```bash
bash infra/deploy.sh
```
This will:
1. Package the Lambda and upload it to a deploy bucket.
2. Create the S3 Vectors bucket + index.
3. Deploy the CloudFormation stack (OpenSearch, Lambda, API Gateway, CloudFront, S3).
4. Embed images **once** (multi-region for throughput) into S3 Vectors (full catalog), then copy
   the top `HOT_PCT`% by popularity into OpenSearch — **without re-embedding**.
5. Build the Next.js app (static export) and upload it; invalidate CloudFront.

⏱️ The OpenSearch domain takes ~10–20 minutes to become active on first deploy.
When finished, the script prints the **CloudFront URL**.

## 4. Use your own dataset (optional)

The dataset is JSONL — one JSON object per line — with at least an image URL. The loader
(`ingestion/common.py`) reads `image_id`, `title`, `keywords`, and CDN URL fields
(`etc1`/`etc2`/`etc3`). Point `DATA_DIR` at a folder of `*.json` (JSONL) files and raise
`INGEST_LIMIT` / `HOT_LIMIT`.

## 5. Teardown

```bash
bash infra/teardown.sh
```
Deletes the stack (OpenSearch, Lambda, API Gateway, CloudFront, web bucket), the S3 Vectors
store, and the deploy bucket — stopping all ongoing cost.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `AccessDeniedException` invoking model | Enable `cohere.embed-v4:0` in Bedrock model access. |
| OpenSearch results empty | Domain may still be initializing; re-run `ingestion/backfill_opensearch.py`. |
| `/api/search` returns 403 | CloudFront still propagating, or `ORIGIN_SECRET` mismatch — redeploy. |
| S3 Vectors `ValidationException` on dim | Index dim must equal `EMBED_DIM` (1024). |
