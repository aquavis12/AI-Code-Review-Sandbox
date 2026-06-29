#!/bin/bash
# Quick test: Submit a code review via the API

set -e

STACK_NAME="${1:-ai-code-review-sandbox}"
REGION="${2:-us-east-1}"

# Get API URL from CloudFormation outputs
API_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text)

echo "🔍 Submitting code review..."
echo "   API: $API_URL"
echo ""

RESPONSE=$(curl -s -X POST "${API_URL}review" \
  -H 'Content-Type: application/json' \
  -d '{
    "repo_url": "https://github.com/psf/requests",
    "branch": "main",
    "checks": ["security", "quality"]
  }')

echo "$RESPONSE" | python3 -m json.tool

echo ""
echo "---"
REVIEW_ID=$(echo "$RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('review_id',''))" 2>/dev/null || echo "")

if [ -n "$REVIEW_ID" ]; then
  echo "📋 Review ID: $REVIEW_ID"
  echo ""
  echo "Fetch full report:"
  echo "  curl ${API_URL}review/${REVIEW_ID} | python3 -m json.tool"
fi
