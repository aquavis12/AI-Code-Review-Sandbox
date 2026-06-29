# AI Code Review Sandbox — Manual AWS Console Setup Guide

## Overview

This guide walks you through setting up the AI Code Review Sandbox entirely via the AWS Console. The application scans PyPI, npm, Maven packages and Git repos for vulnerabilities using isolated Lambda MicroVMs and Bedrock Kimi K2.5 for AI analysis.

---

## Architecture Summary

```
Frontend (S3 + CloudFront)
        │
        ▼
API Gateway (HTTP API)
        │
        ▼
Lambda (Orchestrator)  →  Lambda MicroVM (isolated scan)
        │
        ▼
Bedrock Kimi K2.5 (AI analysis)  →  S3 (results storage)
```

---

## Prerequisites

- AWS Account with access to:
  - Lambda, Lambda MicroVMs, API Gateway, S3, CloudFront, IAM, Bedrock
- Bedrock model access enabled for **Kimi K2.5** (moonshotai.kimi-k2.5) in us-east-1
- AWS CLI installed locally (for MicroVM image build)

---

## Step 1: Create S3 Buckets

### 1.1 Results Bucket

1. Go to **S3 Console** → **Create bucket**
2. Bucket name: `ai-code-review-sandbox-results-<YOUR_ACCOUNT_ID>`
3. Region: `us-east-1`
4. Keep defaults, click **Create bucket**
5. After creation, go to **Management** tab → **Create lifecycle rule**:
   - Rule name: `cleanup-old-reviews`
   - Apply to all objects
   - Expiration: **30 days**

### 1.2 Artifacts Bucket (for MicroVM image)

1. **Create bucket**
2. Bucket name: `ai-code-review-sandbox-artifacts-<YOUR_ACCOUNT_ID>`
3. Region: `us-east-1`
4. Keep defaults, click **Create bucket**

### 1.3 Frontend Bucket

1. **Create bucket**
2. Bucket name: `ai-code-review-sandbox-frontend-<YOUR_ACCOUNT_ID>`
3. Region: `us-east-1`
4. **Block all public access**: ON (CloudFront will access it via OAC)
5. Click **Create bucket**

---

## Step 2: Create IAM Roles

### 2.1 Lambda Execution Role

1. Go to **IAM Console** → **Roles** → **Create role**
2. Trusted entity: **AWS service** → **Lambda**
3. Attach managed policy: `AWSLambdaBasicExecutionRole`
4. Role name: `ai-code-review-sandbox-lambda-role`
5. Click **Create role**
6. Open the role → **Add inline policy** (JSON):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "MicroVMAccess",
      "Effect": "Allow",
      "Action": [
        "lambda-microvms:RunMicrovm",
        "lambda-microvms:GetMicrovm",
        "lambda-microvms:TerminateMicrovm",
        "lambda-microvms:CreateMicrovmAuthToken"
      ],
      "Resource": "*"
    },
    {
      "Sid": "BedrockAccess",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": "*"
    },
    {
      "Sid": "S3ResultsAccess",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::ai-code-review-sandbox-results-<YOUR_ACCOUNT_ID>/*"
    }
  ]
}
```

7. Policy name: `ai-code-review-sandbox-permissions`

### 2.2 MicroVM Build Role

1. **Create role** → Trusted entity: **AWS service** → **Lambda**
2. Role name: `ai-code-review-sandbox-microvm-build`
3. **Add inline policy** (JSON):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::ai-code-review-sandbox-artifacts-<YOUR_ACCOUNT_ID>/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
```

4. Edit the **Trust policy** to also allow `sts:TagSession`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "lambda.amazonaws.com" },
      "Action": ["sts:AssumeRole", "sts:TagSession"]
    }
  ]
}
```

---

## Step 3: Create the Lambda Function

### 3.1 Package the Code

On your local machine, create a deployment zip:

```bash
cd src/orchestrator
pip install requests -t .
zip -r ../../orchestrator.zip .
cd ../..
```

This includes:
- `app.py` — Main handler
- `scanners.py` — Scan step definitions
- `microvm_client.py` — MicroVM lifecycle management
- `reviewer.py` — Bedrock AI analysis
- `requests/` — HTTP library for MicroVM communication

### 3.2 Create Lambda in Console

1. Go to **Lambda Console** → **Create function**
2. Function name: `ai-code-review-sandbox-orchestrator`
3. Runtime: **Python 3.11**
4. Architecture: **x86_64**
5. Execution role: **Use an existing role** → `ai-code-review-sandbox-lambda-role`
6. Click **Create function**

### 3.3 Upload Code

1. In the function page → **Code** tab → **Upload from** → **.zip file**
2. Upload the `orchestrator.zip` created in step 3.1

### 3.4 Configure Settings

1. **Configuration** → **General configuration** → **Edit**:
   - Timeout: **2 minutes** (120 seconds)
   - Memory: **512 MB**
2. **Configuration** → **Environment variables** → **Edit**:

| Key | Value |
|-----|-------|
| `RESULTS_BUCKET` | `ai-code-review-sandbox-results-<YOUR_ACCOUNT_ID>` |
| `MICROVM_IMAGE_NAME` | `code-review-sandbox` |
| `BEDROCK_MODEL_ID` | `moonshotai.kimi-k2.5` |
| `AWS_REGION_NAME` | `us-east-1` |

3. **Runtime settings** → **Edit**:
   - Handler: `app.handler`

---

## Step 4: Create API Gateway (HTTP API)

### 4.1 Create the API

1. Go to **API Gateway Console** → **Create API** → **HTTP API** → **Build**
2. API name: `ai-code-review-sandbox-api`
3. Click **Next** (skip integrations for now)
4. Click **Next** (skip routes for now)
5. Stage name: `prod`, Auto-deploy: **ON**
6. Click **Create**

### 4.2 Configure CORS

1. In the API → left sidebar → **CORS**
2. Click **Configure**:
   - Access-Control-Allow-Origin: `*`
   - Access-Control-Allow-Headers: `Content-Type, Authorization, X-Requested-With`
   - Access-Control-Allow-Methods: `GET, POST, OPTIONS`
   - Access-Control-Expose-Headers: `*`
   - Access-Control-Max-Age: `300`
3. Click **Save**

### 4.3 Create Lambda Integration

1. Left sidebar → **Integrations** → **Create**
2. Integration type: **Lambda function**
3. Lambda function: `ai-code-review-sandbox-orchestrator`
4. Payload format version: **2.0**
5. Click **Create**

### 4.4 Create Routes

1. Left sidebar → **Routes** → **Create**
2. Create these routes (all pointing to the Lambda integration):

| Method | Path | Integration |
|--------|------|-------------|
| `POST` | `/scan` | ai-code-review-sandbox-orchestrator |
| `POST` | `/review` | ai-code-review-sandbox-orchestrator |
| `GET` | `/review/{review_id}` | ai-code-review-sandbox-orchestrator |

For each route:
- Click **Create**
- Click on the route → **Attach integration** → select the Lambda integration

### 4.5 Note Your API URL

Go to **Stages** → **prod** → copy the **Invoke URL**.
It looks like: `https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/prod`

---

## Step 5: Build the MicroVM Image

### 5.1 Upload the Image Code

```bash
# From the project root
cd microvm-image
zip ../microvm-image.zip Dockerfile server.py
cd ..

aws s3 cp microvm-image.zip s3://ai-code-review-sandbox-artifacts-<YOUR_ACCOUNT_ID>/
```

### 5.2 Create the MicroVM Image

```bash
aws lambda-microvms create-microvm-image \
  --name code-review-sandbox \
  --code-artifact uri=s3://ai-code-review-sandbox-artifacts-<YOUR_ACCOUNT_ID>/microvm-image.zip \
  --base-image-arn arn:aws:lambda:us-east-1:aws:microvm-image:al2023-1 \
  --build-role-arn arn:aws:iam::<YOUR_ACCOUNT_ID>:role/ai-code-review-sandbox-microvm-build \
  --region us-east-1
```

### 5.3 Verify Image Status

```bash
aws lambda-microvms get-microvm-image \
  --name code-review-sandbox \
  --region us-east-1
```

Wait until status is `ACTIVE` before testing.

---

## Step 6: Set Up CloudFront + Frontend

### 6.1 Create CloudFront Distribution

1. Go to **CloudFront Console** → **Create distribution**
2. **Origin 1 (S3 Frontend)**:
   - Origin domain: `ai-code-review-sandbox-frontend-<YOUR_ACCOUNT_ID>.s3.us-east-1.amazonaws.com`
   - Origin access: **Origin access control settings (OAC)**
   - Create new OAC: name `ai-code-review-sandbox-oac`, Sign requests: Yes
3. Default cache behavior:
   - Viewer protocol policy: **Redirect HTTP to HTTPS**
   - Allowed HTTP methods: **GET, HEAD**
   - Cache policy: **CachingOptimized**
4. Default root object: `index.html`
5. Click **Create distribution**

6. **IMPORTANT**: After creation, CloudFront shows a banner to update the S3 bucket policy. Click **Copy policy** and apply it to the frontend S3 bucket:
   - Go to the frontend S3 bucket → **Permissions** → **Bucket policy** → Paste and save

### 6.2 Add API Origin (Same-Origin Proxy)

1. In the CloudFront distribution → **Origins** tab → **Create origin**
2. Origin domain: `xxxxxxxxxx.execute-api.us-east-1.amazonaws.com` (your API Gateway domain, without `/prod`)
3. Protocol: **HTTPS only**
4. Origin name/ID: `APIOrigin`
5. Click **Create origin**

### 6.3 Add Cache Behavior for API

1. **Behaviors** tab → **Create behavior**
2. Path pattern: `/prod/*`
3. Origin: **APIOrigin**
4. Viewer protocol policy: **Redirect HTTP to HTTPS**
5. Allowed HTTP methods: **GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE**
6. Cache policy: **CachingDisabled**
7. Origin request policy: **AllViewerExceptHostHeader**
8. Click **Create behavior**

### 6.4 Upload Frontend

1. Edit `frontend/index.html` and set the API_URL:

```javascript
const API_URL = '/prod';
```

2. Upload to S3:

```bash
aws s3 cp frontend/index.html s3://ai-code-review-sandbox-frontend-<YOUR_ACCOUNT_ID>/index.html \
  --content-type "text/html"
```

### 6.5 Access the App

Your app is available at: `https://<distribution-id>.cloudfront.net`

---

## Step 7: Enable Bedrock Model Access

1. Go to **Bedrock Console** → **Model access** (left sidebar)
2. Click **Manage model access**
3. Find **Kimi K2.5** (Moonshot AI) → Check it → **Request model access**
4. Wait for status to become **Access granted**

---

## Step 8: Test

### Test via curl

```bash
# Test preflight
curl -v -X OPTIONS "https://<YOUR_CLOUDFRONT_DOMAIN>/prod/scan" \
  -H "Origin: https://<YOUR_CLOUDFRONT_DOMAIN>" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type"

# Test scan
curl -X POST "https://<YOUR_CLOUDFRONT_DOMAIN>/prod/scan" \
  -H "Content-Type: application/json" \
  -d '{
    "target": {
      "type": "pypi",
      "name": "requests",
      "version": "latest",
      "checks": ["security", "quality"]
    }
  }'
```

### Test via Browser

Open `https://<YOUR_CLOUDFRONT_DOMAIN>` and run a scan from the UI.

---

## Troubleshooting

### CORS Errors

Since the frontend and API are both served through CloudFront (same origin), CORS should not be an issue. If you see CORS errors:
- Verify the `/prod/*` cache behavior exists in CloudFront
- Verify the origin request policy is **AllViewerExceptHostHeader**
- Verify `API_URL = '/prod'` in the frontend (relative path, not absolute)

### Lambda 500 Errors

Check CloudWatch Logs:
1. Go to **CloudWatch** → **Log groups** → `/aws/lambda/ai-code-review-sandbox-orchestrator`
2. Check the latest log stream for errors

Common issues:
- Missing `requests` package → re-package the zip with `pip install requests -t .`
- Missing environment variables → verify all 4 env vars are set
- MicroVM image not ready → check image status is `ACTIVE`

### Lambda Timeout

- Default is 120 seconds. MicroVM scans with Maven can take longer.
- Increase timeout to 300 seconds if Maven scans timeout.

---

## Resource Summary

| Resource | Name/ID |
|----------|---------|
| S3 (Results) | `ai-code-review-sandbox-results-<ACCOUNT_ID>` |
| S3 (Artifacts) | `ai-code-review-sandbox-artifacts-<ACCOUNT_ID>` |
| S3 (Frontend) | `ai-code-review-sandbox-frontend-<ACCOUNT_ID>` |
| Lambda | `ai-code-review-sandbox-orchestrator` |
| IAM Role (Lambda) | `ai-code-review-sandbox-lambda-role` |
| IAM Role (Build) | `ai-code-review-sandbox-microvm-build` |
| API Gateway | `ai-code-review-sandbox-api` (HTTP API) |
| CloudFront | Distribution with S3 + API origins |
| MicroVM Image | `code-review-sandbox` |
| Bedrock Model | `moonshotai.kimi-k2.5` |

---

## Cleanup

To delete all resources:
1. Empty and delete all 3 S3 buckets
2. Delete the CloudFront distribution (disable first, wait, then delete)
3. Delete the API Gateway
4. Delete the Lambda function
5. Delete both IAM roles
6. Delete the MicroVM image: `aws lambda-microvms delete-microvm-image --name code-review-sandbox`
7. Delete CloudWatch log group: `/aws/lambda/ai-code-review-sandbox-orchestrator`
