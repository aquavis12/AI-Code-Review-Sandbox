#!/bin/bash
# Setup: Build the Lambda MicroVM image (one-time setup)
#
# This creates the snapshot image that all review MicroVMs boot from.
# Run this ONCE. After that, every `run-microvm` starts in <1 second.

set -e

REGION="${1:-us-east-1}"
BUCKET_NAME="${2:-ai-code-review-sandbox-artifacts}"
IMAGE_NAME="code-review-sandbox"
BUILD_ROLE_ARN="${3}"  # Pass as 3rd argument

if [ -z "$BUILD_ROLE_ARN" ]; then
  echo "Usage: ./setup-microvm-image.sh <region> <s3-bucket> <build-role-arn>"
  echo ""
  echo "Example:"
  echo "  ./setup-microvm-image.sh us-east-1 my-bucket arn:aws:iam::123456789012:role/MicrovmBuildRole"
  exit 1
fi

echo "🔧 Step 1: Package microvm-image/ into zip..."
cd microvm-image
zip -r ../microvm-image.zip Dockerfile server.py
cd ..

echo "📤 Step 2: Upload to S3..."
aws s3 cp microvm-image.zip "s3://${BUCKET_NAME}/microvm-image.zip" --region "$REGION"

echo "🏗️  Step 3: Create MicroVM image (this takes 1-3 minutes)..."
aws lambda-microvms create-microvm-image \
  --name "$IMAGE_NAME" \
  --code-artifact "uri=s3://${BUCKET_NAME}/microvm-image.zip" \
  --base-image-arn "arn:aws:lambda:${REGION}:aws:microvm-image:al2023-1" \
  --build-role-arn "$BUILD_ROLE_ARN" \
  --region "$REGION"

echo ""
echo "⏳ Step 4: Waiting for image to be CREATED..."
while true; do
  STATE=$(aws lambda-microvms get-microvm-image \
    --image-identifier "$IMAGE_NAME" \
    --region "$REGION" \
    --query 'state' --output text)
  
  echo "   State: $STATE"
  
  if [ "$STATE" = "CREATED" ]; then
    echo ""
    echo "✅ MicroVM image ready: $IMAGE_NAME"
    echo ""
    echo "You can now deploy the backend:"
    echo "  sam build && sam deploy --guided"
    break
  elif [ "$STATE" = "CREATE_FAILED" ]; then
    echo "❌ Image build failed! Check CloudWatch logs:"
    echo "   /aws/lambda/microvms/${IMAGE_NAME}"
    exit 1
  fi
  
  sleep 5
done

# Cleanup
rm -f microvm-image.zip
