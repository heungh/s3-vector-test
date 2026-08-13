#!/usr/bin/env bash
# Remove everything created by deploy.sh (stops all ongoing cost incl. OpenSearch).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
if [ -f "$ROOT/.env" ]; then set -a; source "$ROOT/.env"; set +a; fi
AWS_REGION="${AWS_REGION:-us-east-1}"
PROJECT_NAME="${PROJECT_NAME:-s3-vector-demo}"
STACK_NAME="${STACK_NAME:-$PROJECT_NAME}"
VECTOR_INDEX="${VECTOR_INDEX:-image-embeddings}"
export AWS_REGION

ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
WEB_BUCKET="${PROJECT_NAME}-${ACCOUNT}-web"
DEPLOY_BUCKET="${PROJECT_NAME}-${ACCOUNT}-deploy"
VECTOR_BUCKET="${PROJECT_NAME}-${ACCOUNT}-vectors"

echo "== emptying + deleting buckets, stack, and S3 Vectors store =="
aws s3 rm "s3://$WEB_BUCKET" --recursive --region "$AWS_REGION" 2>/dev/null || true
aws cloudformation delete-stack --stack-name "$STACK_NAME" --region "$AWS_REGION"
aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME" --region "$AWS_REGION" || true

export VECTOR_BUCKET VECTOR_INDEX
python3 "$ROOT/ingestion/teardown_s3vectors.py" || true

aws s3 rb "s3://$DEPLOY_BUCKET" --force --region "$AWS_REGION" 2>/dev/null || true
echo "== done =="
