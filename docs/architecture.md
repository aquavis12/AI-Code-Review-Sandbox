# Architecture

## High-Level Flow

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

## Scan Flow (Sequence)

```
User                Function URL       Orchestrator       MicroVM              Bedrock        S3
 │                      │                  │                 │                    │            │
 │── POST /scan ──────>│                  │                 │                    │            │
 │                      │── Invoke ──────>│                 │                    │            │
 │                      │                  │── RunMicroVM ─>│                    │            │
 │                      │                  │<── endpoint ───│                    │            │
 │                      │                  │── AuthToken ──>│                    │            │
 │                      │                  │<── token ──────│                    │            │
 │                      │                  │                 │                    │            │
 │                      │                  │── pip install ─>│                    │            │
 │                      │                  │── pip-audit ───>│                    │            │
 │                      │                  │── bandit ──────>│                    │            │
 │                      │                  │── ruff ────────>│                    │            │
 │                      │                  │<── results ────│                    │            │
 │                      │                  │                 │                    │            │
 │                      │                  │── Terminate ──>│ [Destroyed]        │            │
 │                      │                  │                                     │            │
 │                      │                  │── Converse API ────────────────────>│            │
 │                      │                  │<── AI analysis ────────────────────│            │
 │                      │                  │                                                  │
 │                      │                  │── Store report ────────────────────────────────>│
 │                      │<── JSON ────────│                                                  │
 │<── response ────────│                  │                                                  │
```

## MicroVM Lifecycle

```
[Start] ──> PENDING ──> RUNNING ──> TERMINATING ──> TERMINATED ──> [End]
                           │                            ^
                           │── Execute scan commands    │
                           │── Install packages        │
                           │── Run security tools      │
                           └── TerminateMicroVM ───────┘

States:
  PENDING      - RunMicroVM called, provisioning (~1s)
  RUNNING      - Full filesystem access, HTTP API on port 8080
  SUSPENDED    - Idle timeout (auto-resume on request)
  TERMINATED   - Destroyed, zero residual state
```

## Network Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Internet                                                               │
│  ┌──────────┐                                                           │
│  │  User    │                                                           │
│  └────┬─────┘                                                           │
└───────┼─────────────────────────────────────────────────────────────────┘
        │ HTTPS
┌───────┼─────────────────────────────────────────────────────────────────┐
│  AWS  │                                                                 │
│       v                                                                 │
│  ┌─────────────────┐     ┌─────────────────┐                           │
│  │ CloudFront CDN  │     │ Function URL    │                           │
│  │ (frontend)      │     │ AUTH_TYPE=NONE  │                           │
│  └─────────────────┘     └────────┬────────┘                           │
│                                   v                                     │
│                          ┌─────────────────┐                            │
│                          │  Orchestrator   │                            │
│                          └───┬─────────┬───┘                            │
│                              │         │                                │
│          Lambda MicroVMs API │         │ Bedrock Converse API           │
│                              v         v                                │
│  ┌───────────────────────────┐    ┌─────────────────┐                  │
│  │  MicroVM Endpoint         │    │  Bedrock         │                  │
│  │  mvm-xxx.lambda-microvm   │    │  Kimi K2.5       │                  │
│  │                           │    └─────────────────┘                  │
│  │  Ingress: ALL_INGRESS     │                                         │
│  │  Egress: INTERNET_EGRESS  │──> PyPI / npm / GitHub                  │
│  └───────────────────────────┘                                         │
│                                                                         │
│  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐      │
│  │  S3 (Frontend)  │   │  S3 (Reports)   │   │  IAM + STS      │      │
│  └─────────────────┘   └─────────────────┘   └─────────────────┘      │
└─────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Service | Role |
|-----------|---------|------|
| **Frontend** | S3 + CloudFront | Web UI, scan submission |
| **API Endpoint** | Lambda Function URL | Public HTTPS, no auth, handles CORS |
| **Orchestrator** | Lambda (Python 3.11) | Routes scans, manages MicroVM lifecycle |
| **Lambda Layer** | Lambda Layer | Provides requests + boto3 (MicroVMs API) |
| **MicroVM** | Lambda MicroVMs | Isolated execution of security tools |
| **AI Reviewer** | Bedrock (Kimi K2.5) | Analyzes scan results, generates report |
| **Reports** | S3 | Stores scan results as JSON |
| **Auth** | IAM + STS | Service-to-service authentication |

## Security Model

```
Threat: Malicious Package (reverse shell, data exfil, etc.)
         │
         v
┌────────────────────────────────────────┐
│  Containment: Lambda MicroVM           │
│                                        │
│  • Firecracker hardware isolation      │
│  • Separate network namespace          │
│  • Ephemeral filesystem                │
│  • Max 5 min lifetime                  │
│  • Controlled egress (INTERNET_EGRESS) │
└────────────────────┬───────────────────┘
                     │
                     v
┌────────────────────────────────────────┐
│  Outcome                               │
│                                        │
│  • VM terminated after scan            │
│  • Zero state leakage                  │
│  • Other scans completely unaffected   │
│  • No persistent access gained         │
└────────────────────────────────────────┘
```

## IAM Roles

### Lambda Execution Role: `ai-code-review-sandbox-lambda-role`

**Trust:** lambda.amazonaws.com

**Permissions:**
- `lambda-microvms:RunMicrovm`, `GetMicrovm`, `TerminateMicrovm`, `CreateMicrovmAuthToken`
- `bedrock:InvokeModel`, `InvokeModelWithResponseStream`
- `s3:PutObject`, `GetObject`, `DeleteObject` (results bucket)

### MicroVM Build Role: `ai-code-review-sandbox-microvm-build`

**Trust:** lambda.amazonaws.com (with `sts:TagSession`)

**Permissions:**
- `s3:GetObject` (artifacts bucket)
- `logs:CreateLogGroup`, `CreateLogStream`, `PutLogEvents`
