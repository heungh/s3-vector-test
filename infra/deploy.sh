#!/usr/bin/env bash
#
# One-click deploy: packages the Lambda, creates the S3 Vectors store, deploys the
# CloudFormation stack (OpenSearch + Lambda + API Gateway + CloudFront), ingests sample
# images, and uploads the web app. Reads configuration from ../.env
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"

# ---- load config ----
if [ -f "$ROOT/.env" ]; then set -a; source "$ROOT/.env"; set +a; fi
AWS_REGION="${AWS_REGION:-us-east-1}"
PROJECT_NAME="${PROJECT_NAME:-s3-vector-demo}"
STACK_NAME="${STACK_NAME:-$PROJECT_NAME}"
OPENSEARCH_INSTANCE_TYPE="${OPENSEARCH_INSTANCE_TYPE:-r6g.large.search}"
EMBED_MODEL_ID="${EMBED_MODEL_ID:-cohere.embed-v4:0}"
EMBED_DIM="${EMBED_DIM:-1024}"
VECTOR_INDEX="${VECTOR_INDEX:-image-embeddings}"
OPENSEARCH_INDEX="${OPENSEARCH_INDEX:-images-hot}"
INGEST_LIMIT="${INGEST_LIMIT:-300}"
HOT_PCT="${HOT_PCT:-20}"
# For bulk ingestion throughput, use the US cross-region inference profile (spreads embedding
# load across multiple regions). Falls back to the direct model if you prefer single-region.
INGEST_EMBED_MODEL_ID="${INGEST_EMBED_MODEL_ID:-us.cohere.embed-v4:0}"
export AWS_REGION

ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
DEPLOY_BUCKET="${PROJECT_NAME}-${ACCOUNT}-deploy"
VECTOR_BUCKET="${PROJECT_NAME}-${ACCOUNT}-vectors"
WEB_BUCKET="${PROJECT_NAME}-${ACCOUNT}-web"
ORIGIN_SECRET="${ORIGIN_SECRET:-$(openssl rand -hex 24)}"

echo "== account=$ACCOUNT region=$AWS_REGION project=$PROJECT_NAME =="

# ---- 1. deploy bucket + package Lambda ----
aws s3api head-bucket --bucket "$DEPLOY_BUCKET" 2>/dev/null || \
  aws s3 mb "s3://$DEPLOY_BUCKET" --region "$AWS_REGION"

echo "== packaging Lambda =="
rm -rf "$ROOT/backend/build" "$ROOT/backend/function.zip"
python3 -m pip install -q -r "$ROOT/backend/requirements.txt" -t "$ROOT/backend/build"
cp "$ROOT/backend/handler.py" "$ROOT/backend/build/"
( cd "$ROOT/backend/build" && zip -qr ../function.zip . )
aws s3 cp "$ROOT/backend/function.zip" "s3://$DEPLOY_BUCKET/lambda/function.zip" --region "$AWS_REGION"

# ---- 2. S3 Vectors bucket + index (not a CloudFormation resource) ----
echo "== creating S3 Vectors store =="
export VECTOR_BUCKET VECTOR_INDEX EMBED_DIM EMBED_MODEL_ID
export OS_DOMAIN="${PROJECT_NAME}-os" OS_INDEX="$OPENSEARCH_INDEX"
python3 "$ROOT/ingestion/setup_s3vectors.py"

# ---- 3. CloudFormation ----
echo "== deploying CloudFormation stack: $STACK_NAME =="
aws cloudformation deploy \
  --stack-name "$STACK_NAME" \
  --template-file "$HERE/cloudformation.yaml" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "$AWS_REGION" \
  --parameter-overrides \
    ProjectName="$PROJECT_NAME" \
    VectorBucketName="$VECTOR_BUCKET" \
    VectorIndexName="$VECTOR_INDEX" \
    OpenSearchIndexName="$OPENSEARCH_INDEX" \
    OpenSearchInstanceType="$OPENSEARCH_INSTANCE_TYPE" \
    EmbedModelId="$EMBED_MODEL_ID" \
    EmbedDim="$EMBED_DIM" \
    OriginSecret="$ORIGIN_SECRET" \
    LambdaCodeBucket="$DEPLOY_BUCKET" \
    LambdaCodeKey="lambda/function.zip"

get_output () {
  aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}
CF_URL="$(get_output CloudFrontURL)"
DIST_ID="$(get_output DistributionId)"

# ---- 4. ingest images ----
# Embed ONCE and store the FULL set in S3 Vectors (source of truth), then copy the top
# HOT_PCT% (by popularity) into OpenSearch WITHOUT re-embedding (hot tier).
echo "== embedding (multi-region) + ingesting into S3 Vectors =="
EMBED_MODEL_ID="$INGEST_EMBED_MODEL_ID" python3 "$ROOT/ingestion/parallel_ingest.py" \
  --limit "$INGEST_LIMIT" --dl-workers 48 --embed-batch 12 --embed-workers 24 --put-batch 300
echo "== copying hot ${HOT_PCT}% into OpenSearch (no re-embedding) =="
python3 "$ROOT/ingestion/backfill_hot.py" --pct "$HOT_PCT"

# ---- 5. build + upload web ----
echo "== building web app =="
# vendored Mermaid (for the architecture modal) is fetched at build time, not committed
MERMAID="$ROOT/web/public/vendor/mermaid.min.js"
if [ ! -f "$MERMAID" ]; then
  mkdir -p "$(dirname "$MERMAID")"
  curl -sL "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js" -o "$MERMAID"
fi
( cd "$ROOT/web" && npm install && npm run build:static )
aws s3 sync "$ROOT/web/out" "s3://$WEB_BUCKET/demo/" --region "$AWS_REGION" --delete
if [ -d "$HERE/site-root" ]; then
  aws s3 sync "$HERE/site-root" "s3://$WEB_BUCKET/" --region "$AWS_REGION"
fi
aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "/*" >/dev/null

echo ""
echo "============================================================"
echo "  Deployed!  ${CF_URL}"
echo "  Demo:      ${CF_URL}demo/"
echo "  (CloudFront 전파에 수 분 소요될 수 있습니다)"
echo "============================================================"
