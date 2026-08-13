# S3 Vectors × OpenSearch — Hybrid Image Search

A one-click deployable demo of **semantic image search** on AWS that runs a **hybrid** vector
architecture:

- **Amazon S3 Vectors** stores the full image catalog as embeddings — serverless, 11-nines
  durable, and up to ~90% cheaper than an always-on vector DB (the *comprehensive* tier).
- **Amazon OpenSearch Service** (managed domain) holds a hot subset for low-latency interactive
  k-NN search (the *fast* tier).
- **Cohere Embed v4** on **Amazon Bedrock** embeds both the stored images and the query into one
  multimodal, multilingual space — so Korean/English text→image search works with no translation.
- A **chat UI** (Next.js + TypeScript) offers three modes: **fast** (OpenSearch), **comprehensive**
  (S3 Vectors), and **hybrid** (both queried in parallel and fused).

The search backend is a **private Lambda**: it has no public URL. CloudFront routes `/api/*` to
API Gateway with a secret header that only CloudFront injects and the Lambda verifies.

```
User (chat UI, CloudFront)
        │  /api/search?q=...&mode=...
        ▼
CloudFront ──(secret header)──► API Gateway ──► Lambda (private)
                                                   │  embed query (Cohere Embed v4)
                                        ┌──────────┴───────────┐
                                  OpenSearch (hot)       S3 Vectors (full)
                                        └──── fuse / re-rank ──┘
```

## Architecture as code

| Layer | Provisioned by |
|-------|----------------|
| IAM role, OpenSearch domain, Lambda, API Gateway, S3 web bucket, CloudFront (+OAC, function) | **CloudFormation** (`infra/cloudformation.yaml`) |
| S3 Vectors bucket + index | `ingestion/setup_s3vectors.py` (S3 Vectors is not yet a CFN resource) |
| Sample image ingestion (embeddings) | `ingestion/embed_and_ingest.py` + `backfill_opensearch.py` |
| Static web build + upload | `web/` (Next.js static export) |

All of the above is orchestrated by **`infra/deploy.sh`**.

## Quick start

```bash
cp .env.sample .env        # edit region / project name / instance type
bash infra/deploy.sh       # one-click: builds, deploys, ingests, uploads
```
The script prints the CloudFront URL when done. See **INSTALL.md** for details and **TEST.md**
for verification steps.

## Cost & teardown

The managed OpenSearch domain bills hourly (e.g. `r6g.large.search` ≈ $120/mo). CloudFront, Lambda,
API Gateway, and S3 Vectors are usage-based and cheap. **Tear everything down when finished:**

```bash
bash infra/teardown.sh
```

## Repo layout

```
infra/        CloudFormation template + deploy.sh / teardown.sh + landing page
backend/      search Lambda (handler.py) — embeds query, queries OpenSearch + S3 Vectors, fuses
ingestion/    S3 Vectors setup + image embedding + OpenSearch backfill (+ bundled sample data)
web/          Next.js + TypeScript chat UI (static export)
```

## Security notes
- No secrets, account IDs, ARNs, or endpoints are committed. All config is read from `.env`
  (git-ignored) or discovered at deploy time.
- The Lambda is private (no function URL). API Gateway is reachable only via CloudFront with a
  shared secret header, auto-generated on first deploy.
- Do not put AWS access keys in `.env`; use your standard AWS credential chain.
