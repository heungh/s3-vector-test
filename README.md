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

## Data tiering: S3 Vectors (full) + OpenSearch (hot 20%)

The two stores are **not** disjoint partitions. Images are **embedded once**, and the vector is
written to both stores — you never pay to embed the same image twice.

- **S3 Vectors = 100% of the catalog** — the single source of truth (serverless, ~90% cheaper).
- **OpenSearch = the top ~`HOT_PCT`% (by popularity) copied from S3 Vectors** — the low-latency
  "hot" tier. `ingestion/backfill_hot.py` reads the ingest manifest, picks the most popular
  vectors, and **copies them (no re-embedding)** into OpenSearch.

Because OpenSearch holds only a hot subset, the hybrid search naturally demonstrates the
**"not in OpenSearch → served by S3 Vectors"** fallback:

| Query type | Where results come from (hybrid mode) |
|------------|----------------------------------------|
| Common / popular | mostly **OpenSearch** (hot tier, sub-second) |
| Long-tail / niche | mostly **S3 Vectors** (the items OpenSearch doesn't have) |

The API returns each result's `tier` (`opensearch` or `s3vectors`), and the UI colors them
(green = OpenSearch, purple = S3 Vectors), so the fallback is visible per result. Scores from both
engines are normalized to a common cosine similarity before fusion so ranking is fair across tiers.

## Multi-region embedding (throughput)

Embedding is the slow/expensive step (download image → Bedrock call), and a single region is
capped by that region's Bedrock throughput quota. To go faster, the bulk ingester
(`ingestion/parallel_ingest.py`) does **concurrent downloads + batched, concurrent Cohere Embed v4
calls + batched `put_vectors`**, and by default uses the **US cross-region inference profile**
`us.cohere.embed-v4:0` (set via `INGEST_EMBED_MODEL_ID`), which spreads embedding load across
multiple US regions — the AWS-native way to exceed a single region's quota.

Measured on this project's data:

| Approach | Throughput | 851,485 images |
|----------|-----------|----------------|
| Sequential, 1 image/call | ~2.3 vec/s | ~110 h |
| Parallel + batched, 1 region | ~53 vec/s | ~4.5 h |
| Parallel + batched, **cross-region profile** | ~75–90 vec/s | ~3 h |

`put_vectors` and image downloads are **not** the bottleneck — the embedding quota is. Raising the
Bedrock quota (or fanning the pipeline out to per-region workers) scales throughput further.
Multi-region only reduces wall-clock time; the embedding **cost is the same** (one call per image).

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
