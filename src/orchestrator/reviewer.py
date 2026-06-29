"""
AI Reviewer — Uses Bedrock Kimi K2.5 to analyze scan results and generate a report.

Kimi K2.5 (Moonshot AI) — lightweight, fast, 256K context.
Great for code analysis without heavy cost.
"""

import json
import boto3
import os

BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'moonshotai.kimi-k2.5')
REGION = os.environ.get('AWS_REGION_NAME', os.environ.get('AWS_REGION', 'us-east-1'))

bedrock = boto3.client('bedrock-runtime', region_name=REGION)



SYSTEM_PROMPT = """You are an elite application security engineer with expertise in:

- Supply chain security (dependency confusion, typosquatting, malicious install scripts)

- OWASP Top 10 2026 (A01-A10)

- CVE/NVD vulnerability analysis and CVSS scoring

- Static analysis (SAST) interpretation

- Software composition analysis (SCA)

- Code quality and maintainability metrics



Your reviews are used by engineering teams to make go/no-go decisions on dependencies.

Be precise. Be actionable. Never speculate — only report what the evidence shows.

When scan tools produce no output for a category, state that explicitly rather than assuming safety."""





def analyze_findings(target: str, scan_results: list[dict], target_type: str = "pypi") -> dict:
    """Send scan results to Bedrock Kimi K2.5 for AI analysis."""

    # Build context from scan results
    findings_text = ""
    for result in scan_results:
        findings_text += f"\n### Step: {result['step_name']}\n"
        findings_text += f"Exit code: {result['exit_code']}\n"
        if result.get('stdout'):
            findings_text += f"Output:\n```\n{result['stdout'][:4000]}\n```\n"
        if result.get('stderr'):
            findings_text += f"Stderr:\n```\n{result['stderr'][:2000]}\n```\n"

    prompt = f"""Analyze the following security scan results for a {target_type} package/repository.

## Target
- Name: {target}
- Type: {target_type}
- Ecosystem: {_ecosystem_context(target_type)}

## Raw Scan Results
{findings_text}

## Analysis Framework

Evaluate across these dimensions:

### 1. SECURITY VULNERABILITIES
- Known CVEs (from pip-audit, npm audit, OWASP dependency-check)
- Severity classification using CVSS v3.1:
  - Critical (9.0-10.0): Remote code execution, auth bypass, data exfil
  - High (7.0-8.9): Privilege escalation, significant data exposure
  - Medium (4.0-6.9): XSS, CSRF, limited information disclosure
  - Low (0.1-3.9): Minor info leaks, DOS under specific conditions
- For each CVE: ID, affected component, fixed version, exploitability

### 2. SUPPLY CHAIN RISKS
- Typosquatting indicators (similar names to popular packages)
- Suspicious install scripts (post-install hooks, network calls during install)
- Obfuscated code (base64 encoded payloads, exec/eval usage)
- Unexpected outbound network connections
- Unusual file system access patterns
- Package age vs download count anomalies

### 3. CODE QUALITY (from ruff/bandit/static analysis)
- Score A-F based on:
  - A: 0-2 issues, all style-only
  - B: 3-10 issues, no security-relevant
  - C: 11-25 issues or 1-2 low-severity security
  - D: 26-50 issues or medium-severity security issues
  - F: 50+ issues or any high/critical security issue
- Distinguish between style violations (cosmetic) and logic/security issues

### 4. DEPENDENCY HEALTH
- Total dependency count (deep vs shallow tree)
- Known-vulnerable transitive dependencies
- Unmaintained dependencies (last update >2 years)
- License compatibility issues (copyleft in proprietary context)

### 5. OWASP TOP 10 MAPPING
Map any findings to relevant OWASP categories:
- A01: Broken Access Control
- A02: Cryptographic Failures
- A03: Injection
- A04: Insecure Design
- A05: Security Misconfiguration
- A06: Vulnerable and Outdated Components
- A07: Identification and Authentication Failures
- A08: Software and Data Integrity Failures
- A09: Security Logging and Monitoring Failures
- A10: Server-Side Request Forgery

## Response Format (strict JSON)

```json
{{
  "summary": "2-3 sentence executive summary of overall health and risk posture",
  "risk_level": "low|medium|high|critical",
  "confidence": "high|medium|low",
  "findings": {{
    "security": {{
      "critical": 0,
      "high": 0,
      "medium": 0,
      "low": 0,
      "details": [
        {{
          "id": "CVE-XXXX-XXXXX or finding ID",
          "severity": "critical|high|medium|low",
          "component": "affected package or file",
          "description": "what the vulnerability is",
          "fix": "how to remediate",
          "owasp": "A01-A10 category if applicable"
        }}
      ]
    }},
    "supply_chain": {{
      "risk": "none|low|medium|high",
      "indicators": ["list of any suspicious indicators found"]
    }},
    "quality": {{
      "score": "A-F",
      "issues": 0,
      "details": ["list of significant quality issues"]
    }},
    "dependencies": {{
      "total": 0,
      "vulnerable": 0,
      "outdated": 0,
      "details": ["notable dependency concerns"]
    }}
  }},
  "recommendations": [
    {{
      "priority": 1,
      "action": "what to do",
      "reason": "why it matters",
      "effort": "low|medium|high"
    }}
  ],
  "safe_to_use": true,
  "conditions": ["any conditions for safe usage, e.g. 'pin to version X.Y.Z'"]
}}
```

IMPORTANT:
- If a scan tool produced no output or was not run, mark that category as "not_assessed" rather than assuming it passed.
- If exit code is non-zero but output is empty, flag as "scan_error" — do not treat as clean.
- Prioritize recommendations by risk reduction impact, not ease of fix.
- Be specific: "update package X from 1.2.3 to 1.2.4" not "update dependencies"."""

    response = bedrock.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[
            {"role": "user", "content": [{"text": prompt}]}
        ],
        system=[{"text": SYSTEM_PROMPT}],
        inferenceConfig={
            "maxTokens": 4000,
            "temperature": 0.2,
            "topP": 0.9
        }
    )

    ai_text = response['output']['message']['content'][0]['text']

    # Parse JSON from response
    try:
        if '```json' in ai_text:
            ai_text = ai_text.split('```json')[1].split('```')[0]
        elif '```' in ai_text:
            ai_text = ai_text.split('```')[1].split('```')[0]
        return json.loads(ai_text.strip())
    except json.JSONDecodeError:
        return {
            "summary": ai_text[:500],
            "risk_level": "unknown",
            "confidence": "low",
            "findings": {},
            "recommendations": [],
            "safe_to_use": None,
            "parse_error": True,
            "raw_response": ai_text
        }


def _ecosystem_context(target_type: str) -> str:
    """Return ecosystem-specific context for the prompt."""
    contexts = {
        "pypi": "Python Package Index. Check for: setup.py/pyproject.toml install hooks, "
                "native extensions with C code, data exfiltration via requests/urllib/socket.",
        "npm": "Node.js npm registry. Check for: preinstall/postinstall scripts, "
               "eval/Function constructor usage, process.env access, child_process spawning.",
        "mvn": "Maven Central (Java). Check for: vulnerable transitive dependencies via "
               "dependency tree, known CVEs in logging/serialization libraries (log4j, jackson, commons).",
        "git": "Source repository. Check for: hardcoded secrets/tokens, unsafe deserialization, "
               "SQL injection patterns, command injection, path traversal, SSRF indicators."
    }
    return contexts.get(target_type, "Unknown ecosystem.")
