#!/bin/bash
# Deploy the AI Code Review Sandbox — backend + frontend

STACK_NAME="${1:-ai-code-review-sandbox}"
REGION="${2:-us-east-1}"

echo "🚀 Building Lambda functions..."
sam build

echo "📦 Deploying stack: $STACK_NAME to $REGION..."
sam deploy \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --no-fail-on-empty-changeset

echo ""
echo "✅ Backend deployed!"
echo ""

# Get outputs
API_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text)

FRONTEND_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`FrontendBucket`].OutputValue' \
  --output text)

FRONTEND_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`FrontendUrl`].OutputValue' \
  --output text)

# Inject API URL into frontend before uploading
echo "🎨 Deploying frontend to S3 + CloudFront..."
TEMP_DIR=$(mktemp -d)
cp frontend/index.html "$TEMP_DIR/index.html"

# Replace the empty API_URL with the real one
sed -i "s|const API_URL = '';|const API_URL = '${API_URL}';|g" "$TEMP_DIR/index.html"

# Upload to S3
aws s3 cp "$TEMP_DIR/index.html" "s3://$FRONTEND_BUCKET/index.html" \
  --content-type "text/html" \
  --cache-control "max-age=300"

rm -rf "$TEMP_DIR"

# Invalidate CloudFront cache
DIST_ID=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`FrontendUrl`].OutputValue' \
  --output text | sed 's|https://||' | sed 's|.cloudfront.net||')

if [ -n "$DIST_ID" ]; then
  aws cloudfront create-invalidation \
    --distribution-id "$DIST_ID" \
    --paths "/*" > /dev/null 2>&1 || true
fi

echo ""
echo "============================================"
echo "✅ Deployment complete!"
echo "============================================"
echo ""
echo "📍 API:       $API_URL"
echo "🌐 Frontend:  $FRONTEND_URL"
echo ""
echo "Try it:"
echo "  open $FRONTEND_URL"
