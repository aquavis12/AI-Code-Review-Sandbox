#!/bin/bash
# Test the AI Code Review Sandbox

set -e

API_URL="${1:-http://localhost:3000}"

echo "🔍 Submitting code review request..."
echo ""

RESPONSE=$(curl -s -X POST "${API_URL}/review" \
  -H 'Content-Type: application/json' \
  -d '{
    "repo_url": "https://github.com/psf/requests",
    "branch": "main",
    "checks": ["security", "quality"]
  }')

echo "$RESPONSE" | python3 -m json.tool

echo ""
echo "---"
REVIEW_ID=$(echo "$RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('review_id',''))")
echo "📋 Review ID: $REVIEW_ID"
echo ""
echo "Fetch full report:"
echo "  curl ${API_URL}/review/${REVIEW_ID}"
