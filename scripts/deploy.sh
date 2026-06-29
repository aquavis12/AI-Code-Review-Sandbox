#!/usr/bin/env bash
# Deploy everything with Terraform + upload frontend

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🏗️  Step 1: Terraform init + apply..."
cd "$PROJECT_DIR/terraform"
terraform init
terraform apply -auto-approve

# Get outputs
API_URL=$(terraform output -raw api_url)
FRONTEND_BUCKET=$(terraform output -raw frontend_bucket)
FRONTEND_URL=$(terraform output -raw frontend_url)
ARTIFACTS_BUCKET=$(terraform output -raw artifacts_bucket)
BUILD_ROLE_ARN=$(terraform output -raw microvm_build_role_arn)

cd "$PROJECT_DIR"

echo ""
echo "🎨 Step 2: Deploy frontend to S3..."
sed "s|const API_URL = '';|const API_URL = '${API_URL}';|g" frontend/index.html > /tmp/index.html
aws s3 cp /tmp/index.html "s3://${FRONTEND_BUCKET}/index.html" --content-type "text/html"
rm /tmp/index.html

echo ""
echo "============================================"
echo "✅ Deployment complete!"
echo "============================================"
echo ""
echo "📍 API:          ${API_URL}"
echo "🌐 Frontend:     ${FRONTEND_URL}"
echo "📦 Artifacts:    ${ARTIFACTS_BUCKET}"
echo "🔑 Build Role:   ${BUILD_ROLE_ARN}"
