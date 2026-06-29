# 🛡️ AI Code Review Sandbox

**Spawn an isolated Lambda MicroVM → clone any repo → run security + quality scans → AI analysis with Bedrock Kimi K2.5 → structured report in seconds.**

Built on [AWS Lambda MicroVMs](https://aws.amazon.com/lambda/lambda-microvms/) — each review runs in its own Firecracker VM. Uses **Kimi K2.5** (Moonshot AI) via Bedrock for fast, cheap AI analysis.

---

## Architecture

```
┌────────────┐        ┌──────────────────┐        ┌──────────────────┐
│  Client /  │ POST   │   Orchestrator   │ spawn  │  Lambda MicroVM  │
│  GitHub    │───────▶│   (Lambda fn)    │───────▶│                  │
│  Webhook   │        │                  │        │  • git clone     │
└────────────┘        │  1. Spawn MicroVM│        │  • pip install   │
                      │  2. Send commands│        │  • bandit (sec)  │
                      │  3. Collect output│       │  • ruff (quality)│
                      │  4. AI analysis  │        │  • pytest        │
                      └────────┬─────────┘        └──────────────────┘
                               │
                               ▼
                      ┌──────────────────┐
                      │  Bedrock Kimi K2.5│
                      │  (moonshotai.     │
                      │   kimi-k2.5)     │
                      └──────────────────┘
```

## Why Lambda MicroVMs

| Need | Why MicroVMs |
|------|-------------|
| `git clone` + `pip install` + run tools | Multi-step, stateful — regular Lambda resets |
| Full filesystem with packages | MicroVM has persistent disk |
| Install arbitrary packages safely | VM-level isolation prevents escapes |
| Parallel reviews | Each = own VM, zero cross-contamination |

## Why Kimi K2.5

- ⚡ Fast inference — great for code analysis
- 💰 Cheap — much lower cost than Claude/GPT
- 📄 256K context — can handle large scan outputs
- 🧠 Good at code understanding without being overkill

---

## Project Structure

```
AI-Code-Review-Sandbox/
├── README.md
├── template.yaml                  # SAM IaC
├── samconfig.toml                 # Deploy config
├── .gitignore
├── src/
│   └── orchestrator/
│   └── orchestrator/
│       ├── app.py                 # Main handler — review flow
│       ├── microvm_client.py      # MicroVM lifecycle wrapper
│       ├── reviewer.py            # Bedrock Kimi K2.5 analysis
│       └── requirements.txt
├── frontend/
│   └── index.html                 # Single-file UI (no build step)
├── scripts/
│   └── deploy.sh                  # Deploys backend + frontend
└── examples/
    └── test_review.sh
```

---

## Quick Start

### Prerequisites

- AWS CLI configured
- SAM CLI installed
- Python 3.11+
- Lambda MicroVMs access enabled

### Deploy

```bash
# Create venv
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Deploy everything (backend + frontend to S3/CloudFront)
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

Or step by step:
```bash
sam build
sam deploy --guided   # First time
# Then upload frontend:
aws s3 cp frontend/index.html s3://YOUR_FRONTEND_BUCKET/index.html --content-type "text/html"
```

### Test

```bash
# Review a public repo
curl -X POST https://YOUR_API/review \
  -H 'Content-Type: application/json' \
  -d '{
    "repo_url": "https://github.com/psf/requests",
    "branch": "main",
    "checks": ["security", "quality"]
  }'
```

### Response

```json
{
  "review_id": "rv-abc123",
  "repo": "psf/requests",
  "duration_ms": 4200,
  "risk_level": "medium",
  "findings": {
    "security": { "critical": 0, "high": 0, "medium": 2, "low": 5 },
    "quality": { "score": "A-", "issues": 12 }
  },
  "ai_summary": "Well-maintained codebase. Two medium-severity dependency CVEs found...",
  "recommendations": [
    "Upgrade urllib3 to ≥2.0.7 (CVE-2023-45803)",
    "Add type hints to public API functions",
    "Replace deprecated ssl.wrap_socket() calls"
  ]
}
```

---

## What The MicroVM Executes

```bash
# Step 1: Clone (state persists between all steps!)
git clone --depth 1 --branch main https://github.com/user/repo.git /workspace

# Step 2: Install dependencies
cd /workspace && pip install -r requirements.txt

# Step 3: Security scan
pip install bandit safety
bandit -r . -f json --severity-level medium
safety check --json

# Step 4: Quality check
pip install ruff
ruff check . --output-format json

# Step 5: Tests (optional)
pip install pytest
pytest --tb=short -q
```

---

## Cost Estimate

| Component | Cost per review |
|-----------|----------------|
| Lambda MicroVM (30s) | ~$0.002 |
| Bedrock Kimi K2.5 | ~$0.003 |
| **Total** | **~$0.005** |

---

## Frontend

Hosted on **S3 + CloudFront** (HTTPS, edge-cached, global CDN).

- Deployed automatically via `scripts/deploy.sh`
- API URL is injected at deploy time — no manual config
- Or open `frontend/index.html` locally for development
---

## Configuration

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `BEDROCK_MODEL_ID` | `moonshotai.kimi-k2.5` | Bedrock model for analysis |
| `MICROVM_BASELINE_MEMORY` | `1024` | MicroVM memory (MB) |
| `MICROVM_BASELINE_CPU` | `1` | MicroVM vCPUs |
| `RESULTS_BUCKET` | (auto-created) | S3 bucket for reports |

---

## License

MIT
