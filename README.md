# AI Code Review Sandbox

Scan **PyPI, npm, Maven & Git repos** for vulnerabilities — each scan runs in its own isolated Firecracker MicroVM. Install packages, run security tools, get AI-powered analysis — all destroyed after.

[![AWS](https://img.shields.io/badge/AWS-Lambda%20MicroVMs-FF9900?logo=amazonaws)](https://docs.aws.amazon.com/lambda/latest/dg/lambda-microvms-guide.html) [![Bedrock](https://img.shields.io/badge/AI-Kimi%20K2.5-7950F2)](https://aws.amazon.com/bedrock/) [![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Architecture

```
┌──────────┐     ┌─────────────────┐     ┌──────────────────────────────┐
│  Browser │────>│  Lambda Function│────>│  Lambda Orchestrator         │
│  or CLI  │     │  URL (HTTPS)    │     │  (Python 3.11, 512MB)        │
└──────────┘     └─────────────────┘     └──────────┬───────────────────┘
                                                    │
                                    ┌───────────────┼───────────────┐
                                    v                               v
                    ┌───────────────────────────┐    ┌─────────────────────┐
                    │  Lambda MicroVM            │    │  Bedrock Kimi K2.5   │
                    │  (Firecracker isolation)   │    │  (AI Analysis)       │
                    │                           │    └──────────┬──────────┘
                    │  • pip install / npm i     │               │
                    │  • bandit, pip-audit       │               v
                    │  • ruff, npm audit         │    ┌─────────────────────┐
                    │  • OWASP dependency-check  │    │  S3 (Reports)        │
                    │                           │    └─────────────────────┘
                    │  [Terminated after scan]   │
                    └───────────────────────────┘
```

**Flow:** `User > Function URL > Orchestrator > Spawn MicroVM > Run Scans > Terminate VM > AI Review > Return Report`

> **Lambda Layer** provides `requests` + latest `boto3` (with MicroVMs API support) to the orchestrator — keeps the deployment zip lean and dependencies reusable.

---

## What It Scans

| Target | Checks |
|--------|--------|
| **PyPI** | Vulnerabilities, malicious code, typosquatting, license, OWASP |
| **npm** | npm audit, install scripts, dependency tree, CVEs |
| **Maven** | OWASP dependency-check, NVD CVE lookup, transitive deps |
| **Git repo** | bandit, ruff, secrets detection, dependency audit |

---

## Quick Start

```bash
curl -X POST https://YOUR_FUNCTION_URL/scan \
  -H 'Content-Type: application/json' \
  -d '{"target": {"type": "pypi", "name": "requests", "checks": ["security", "owasp"]}}'
```

**Response:**
```json
{
  "risk_level": "low",
  "ai_summary": "Package is well-maintained with no known vulnerabilities...",
  "findings": { "security": { "critical": 0, "high": 0, "medium": 1 } },
  "recommendations": ["Pin urllib3 to avoid CVE-2023-45803"]
}
```

---

## Why Lambda MicroVMs

| Without Isolation | With MicroVMs |
|-------------------|---------------|
| Malicious pkg infects shared runtime | Contained in its own VM |
| Install scripts can escape | Firecracker sandbox boundary |
| Cross-contamination between scans | Each scan = fresh VM, destroyed after |

---

## Project Structure

```
├── frontend/index.html          # Web UI
├── microvm-image/
│   ├── Dockerfile               # MicroVM image (Python + Node + Maven)
│   └── server.py                # HTTP exec server inside VM
├── src/orchestrator/
│   ├── app.py                   # Lambda handler (/scan, /review)
│   ├── scanners.py              # Scan steps per package type
│   ├── microvm_client.py        # MicroVM lifecycle (spawn/exec/terminate)
│   └── reviewer.py              # Bedrock Kimi K2.5 integration
├── docs/
│   ├── architecture.md          # Detailed diagrams
│   ├── architecture-diagram.png # Visual architecture
│   └── MANUAL-SETUP-GUIDE.md    # Step-by-step AWS Console setup
└── scripts/                     # Deploy & test scripts
```

---

## Deploy

```bash
# 1. Create Lambda Layer (requests + latest boto3)
pip install requests boto3 -t python/lib/python3.11/site-packages
zip -r layer.zip python/
aws lambda publish-layer-version --layer-name code-review-deps \
  --zip-file fileb://layer.zip --compatible-runtimes python3.11

# 2. Deploy orchestrator
cd src/orchestrator && zip -r ../../lambda.zip *.py && cd ../..
aws lambda update-function-code --function-name ai-code-review-sandbox-orchestrator \
  --zip-file fileb://lambda.zip

# 3. Build MicroVM image
aws lambda-microvms create-microvm-image --name code-review-sandbox \
  --code-artifact uri=s3://ARTIFACTS_BUCKET/microvm-image.zip \
  --base-image-arn arn:aws:lambda:us-east-1:aws:microvm-image:al2023-1
```

> Full console walkthrough: [`docs/MANUAL-SETUP-GUIDE.md`](docs/MANUAL-SETUP-GUIDE.md)

---

## Cost

~**$0.01 per scan** (MicroVM compute + AI analysis combined)

---

## Author

Built by [Vishnu](https://github.com/aquavis12) — AWS Community Builder (Security) | 14x AWS Certified

## License

MIT
