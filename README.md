# 🛡️ AI Code Review Sandbox

**Scan PyPI packages, npm packages, Maven artifacts, and Git repos for vulnerabilities — in isolated Lambda MicroVMs.**

Each scan runs in its own Firecracker VM. Install packages, run security tools, detect supply chain attacks — all isolated, all destroyed after.

Built on [AWS Lambda MicroVMs](https://aws.amazon.com/lambda/lambda-microvms/) + **Bedrock Kimi K2.5** for AI analysis.

---

## What It Scans

| Target | Command | What It Checks |
|--------|---------|----------------|
| 🐍 **PyPI** | `POST /scan` | Vulnerabilities, malicious code, typosquatting, license, OWASP |
| 📦 **npm** | `POST /scan` | npm audit, install scripts, dependency tree, CVEs, OWASP |
| ☕ **Maven** | `POST /scan` | OWASP dependency-check, NVD CVE lookup, transitive deps, license |
| 🔗 **Git repo** | `POST /scan` | Security (bandit), quality (ruff), secrets, deps, OWASP |

---

## Usage

### Scan a PyPI package
```bash
curl -X POST https://YOUR_API/scan \
  -H 'Content-Type: application/json' \
  -d '{
    "target": {
      "type": "pypi",
      "name": "requests",
      "version": "2.31.0",
      "checks": ["security", "quality", "license", "typosquat", "owasp"]
    }
  }'
```

### Scan an npm package
```bash
curl -X POST https://YOUR_API/scan \
  -H 'Content-Type: application/json' \
  -d '{
    "target": {
      "type": "npm",
      "name": "express",
      "version": "4.18.2",
      "checks": ["security", "quality", "license"]
    }
  }'
```

### Scan a Maven artifact
```bash
curl -X POST https://YOUR_API/scan \
  -H 'Content-Type: application/json' \
  -d '{
    "target": {
      "type": "mvn",
      "name": "org.apache.logging.log4j:log4j-core",
      "version": "2.17.1",
      "checks": ["security", "quality", "license", "owasp"]
    }
  }'
```

### Scan a Git repo
```bash
curl -X POST https://YOUR_API/scan \
  -H 'Content-Type: application/json' \
  -d '{
    "target": {
      "type": "git",
      "name": "https://github.com/psf/requests",
      "branch": "main",
      "checks": ["security", "quality", "license"]
    }
  }'
```

### Response
```json
{
  "scan_id": "scan-abc123",
  "target": { "type": "pypi", "name": "requests", "version": "2.31.0" },
  "duration_ms": 5200,
  "risk_level": "low",
  "ai_summary": "Package is well-maintained with no known vulnerabilities...",
  "findings": {
    "security": { "critical": 0, "high": 0, "medium": 1, "low": 3 },
    "quality": { "score": "A", "issues": 5 }
  },
  "recommendations": [
    "Pin urllib3 dependency to avoid CVE-2023-45803",
    "Consider adding py.typed marker"
  ]
}
```

---

## Architecture

```
POST /scan { type: "pypi", name: "requests" }
      │
      ▼
┌──────────────────┐        ┌──────────────────────────┐
│  Orchestrator    │ spawn  │  Lambda MicroVM           │
│  (Lambda)        │───────▶│                          │
│                  │        │  pip install requests     │
│                  │        │  pip-audit               │
│                  │        │  bandit -r /pkg/         │
│                  │        │  safety check            │
│                  │◀───────│  ruff check              │
└────────┬─────────┘        └──────────────────────────┘
         │                           (terminated)
         ▼
┌──────────────────┐
│  Bedrock Kimi K2.5│
│  AI Analysis     │
└────────┬─────────┘
         │
         ▼
   JSON Report + S3
```

---

## Why Lambda MicroVMs

- **`pip install malicious-pkg`** → only poisons its own VM, dies after scan
- **Install scripts** → can't escape the MicroVM sandbox
- **50 packages scanned simultaneously** → 50 isolated VMs, zero interference
- **Full filesystem** → install real tools (bandit, npm audit, pipdeptree)
- **Destroyed after** → no leftover state from previous scans

---

## Project Structure

```
AI-Code-Review-Sandbox/
├── terraform/              # All infrastructure
│   ├── main.tf
│   ├── variables.tf
│   ├── iam.tf
│   ├── lambda.tf
│   ├── api_gateway.tf
│   ├── s3.tf
│   ├── cloudfront.tf
│   └── outputs.tf
├── microvm-image/          # What runs INSIDE the MicroVM
│   ├── Dockerfile
│   └── server.py
├── src/orchestrator/       # Lambda orchestrator code
│   ├── app.py              # API handler
│   ├── scanners.py         # PyPI / npm / Git scan steps
│   ├── microvm_client.py   # MicroVM lifecycle
│   ├── reviewer.py         # Bedrock AI analysis
│   └── requirements.txt
├── frontend/
│   └── index.html
├── scripts/
│   ├── deploy.sh
│   └── test-review.sh
├── .gitignore
├── README.md
├── WHY.md
└── IDEAS.md
```

---

## Deploy

```bash
# 1. Deploy infra
cd terraform
terraform init
terraform apply

# 2. Build MicroVM image (one-time)
cd ../microvm-image
zip ../microvm-image.zip Dockerfile server.py
cd ..
aws s3 cp microvm-image.zip s3://$(cd terraform && terraform output -raw artifacts_bucket)/
aws lambda-microvms create-microvm-image \
  --name code-review-sandbox \
  --code-artifact uri=s3://$(cd terraform && terraform output -raw artifacts_bucket)/microvm-image.zip \
  --base-image-arn arn:aws:lambda:us-east-1:aws:microvm-image:al2023-1 \
  --build-role-arn $(cd terraform && terraform output -raw microvm_build_role_arn)

# 3. Deploy frontend
./scripts/deploy.sh
```

---

## Cost

| Scan Type | Cost |
|-----------|------|
| PyPI package | ~$0.006 |
| npm package | ~$0.006 |
| Git repo | ~$0.008 |
| AI analysis (Kimi K2.5) | ~$0.003 |

---

## License

MIT
