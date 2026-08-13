# Test Guide

After `infra/deploy.sh` finishes, grab the CloudFront URL (also in the CloudFormation stack
outputs `CloudFrontURL`).

```bash
CF_URL=$(aws cloudformation describe-stacks --stack-name "$PROJECT_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontURL'].OutputValue" --output text)
echo "$CF_URL"
```

## 1. UI smoke test (browser)

Open `${CF_URL}demo/` and:
- The header shows **“S3 Vectors × OpenSearch — 하이브리드 이미지 검색”** and a `LIVE · 하이브리드` badge.
- Click an example chip (e.g. **💧 물 마시는 사람**) or type a description and press **검색**.
- You should get a grid of relevant images with similarity scores and tier dots
  (green = OpenSearch, purple = S3 Vectors).
- Try each mode: **⚡ 빠른 검색**, **🗄️ 전체 검색**, **🔀 하이브리드**.
- Click **🏗 아키텍처** to see the Mermaid architecture diagram.

## 2. API test (through CloudFront)

The API is same-origin under `/api/*`. It expects `GET` with a query string.

```bash
# comprehensive (S3 Vectors only)
curl -s "${CF_URL}api/search?q=person%20drinking%20water&mode=comprehensive&topK=5" | python3 -m json.tool

# fast (OpenSearch only)
curl -s "${CF_URL}api/search?q=recycling%20symbol&mode=fast&topK=5" | python3 -m json.tool

# hybrid (both tiers, fused)
curl -s "${CF_URL}api/search?q=%ED%8C%80%EC%9B%8C%ED%81%AC&mode=hybrid&topK=5" | python3 -m json.tool
```

Expected response shape:
```json
{
  "query": "person drinking water",
  "mode": "comprehensive",
  "results": [
    { "image_id": "...", "title": "...", "keywords": "...",
      "thumb_url": "...", "preview_url": "...", "score": 0.43, "tier": "s3vectors" }
  ],
  "timings": { "embed_ms": 130, "s3vectors_ms": 60, "total_ms": 200 },
  "tiersQueried": ["s3vectors"]
}
```
- `fast` → `tiersQueried: ["opensearch"]`, results tagged `opensearch`.
- `hybrid` → `tiersQueried: ["opensearch","s3vectors"]`, mixed tiers.
- Korean and English queries both work (multilingual embedding).

## 3. Security check (API is private)

Direct access to API Gateway (without CloudFront's secret header) must be denied:

```bash
API=$(aws cloudformation describe-stacks --stack-name "$PROJECT_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" --output text)
curl -s -o /dev/null -w "%{http_code}\n" "$API/api/search?q=test"   # expect 403
```
There is **no public Lambda function URL** — the Lambda is only invokable by API Gateway.

## 4. Relevance sanity

| Query (KO / EN) | Expected top result theme |
|-----------------|---------------------------|
| 물 마시는 사람 / person drinking water | person drinking / holding a glass |
| 재활용 심볼 / recycling symbol | recycling / environment icon |
| 음악 듣기 / listening to music | person with headphones |

## 5. Notes on latency
At this small demo scale (hundreds of vectors), timings are dominated by fixed overhead
(HTTP, warm-up), so they are **not** a fair engine benchmark. OpenSearch’s low-latency advantage
appears at large scale under warm, concurrent load; S3 Vectors trades some latency for ~90% cost
savings on the full catalog.
