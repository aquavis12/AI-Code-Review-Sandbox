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


def analyze_findings(repo_url: str, scan_results: list[dict]) -> dict:
    """Send scan results to Bedrock Kimi K2.5 for AI analysis."""

    # Build context from scan results
    findings_text = ""
    for result in scan_results:
        findings_text += f"\n### {result['step_name']}\n"
        findings_text += f"Exit code: {result['exit_code']}\n"
        if result.get('stdout'):
            findings_text += f"Output:\n```\n{result['stdout'][:3000]}\n```\n"
        if result.get('stderr'):
            findings_text += f"Errors:\n```\n{result['stderr'][:1000]}\n```\n"

    prompt = f"""You are a senior security engineer reviewing code scan results.

Repository: {repo_url}

## Scan Results
{findings_text}

## Your Task
Analyze these results and provide:
1. **Summary** — 2-3 sentence overview of code health
2. **Critical Findings** — anything that needs immediate attention
3. **Security Issues** — vulnerabilities found by bandit/safety
4. **Quality Issues** — code style, complexity, maintainability
5. **Recommendations** — top 5 actionable improvements, prioritized

Respond in JSON format:
{{
  "summary": "...",
  "risk_level": "low|medium|high|critical",
  "findings": {{
    "security": {{ "critical": N, "high": N, "medium": N, "low": N, "details": [...] }},
    "quality": {{ "issues": N, "score": "A-F", "details": [...] }}
  }},
  "recommendations": ["...", "...", "..."],
  "estimated_fix_time": "Xh"
}}"""

    # Use Converse API — works with Kimi K2.5
    response = bedrock.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[
            {"role": "user", "content": [{"text": prompt}]}
        ],
        inferenceConfig={
            "maxTokens": 2000,
            "temperature": 0.3
        }
    )

    ai_text = response['output']['message']['content'][0]['text']

    # Parse JSON from response
    try:
        # Handle case where model wraps in ```json blocks
        if '```json' in ai_text:
            ai_text = ai_text.split('```json')[1].split('```')[0]
        return json.loads(ai_text)
    except json.JSONDecodeError:
        return {
            "summary": ai_text[:500],
            "risk_level": "unknown",
            "findings": {},
            "recommendations": [],
            "raw_response": ai_text
        }
