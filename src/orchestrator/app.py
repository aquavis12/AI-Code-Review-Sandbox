"""
Orchestrator Lambda — Receives review requests, manages MicroVM lifecycle.

Flow:
1. Receive POST /review with repo_url
2. Spawn a Lambda MicroVM
3. Execute review steps (clone, install, scan)
4. Collect results → send to Bedrock for AI analysis
5. Store report in S3
6. Destroy MicroVM
7. Return review report
"""

import json
import os
import uuid
import time

import boto3
from microvm_client import MicroVMClient
from reviewer import analyze_findings

s3 = boto3.client('s3')
RESULTS_BUCKET = os.environ['RESULTS_BUCKET']
MICROVM_MEMORY = int(os.environ.get('MICROVM_BASELINE_MEMORY', 1024))
MICROVM_CPU = int(os.environ.get('MICROVM_BASELINE_CPU', 1))


def handler(event, context):
    """API Gateway entry point."""
    method = event['httpMethod']
    path = event['path']

    if method == 'POST' and '/review' in path:
        return handle_review(event)
    elif method == 'GET' and '/review/' in path:
        return handle_status(event)
    else:
        return response(404, {"error": "Not found"})


def handle_review(event):
    """Execute a full code review in an isolated MicroVM."""
    body = json.loads(event.get('body', '{}'))

    repo_url = body.get('repo_url')
    branch = body.get('branch', 'main')
    checks = body.get('checks', ['security', 'quality'])

    if not repo_url:
        return response(400, {"error": "repo_url is required"})

    review_id = f"rv-{uuid.uuid4().hex[:8]}"
    start_time = time.time()

    # Build the review steps based on requested checks
    steps = build_review_steps(repo_url, branch, checks)

    # Spawn MicroVM and execute
    try:
        with MicroVMClient(MICROVM_MEMORY, MICROVM_CPU) as vm:
            print(f"MicroVM spawned for review {review_id}")

            # Execute all steps (state persists between them!)
            scan_results = vm.execute_steps(steps)

            # Collect report files if they exist
            for result in scan_results:
                if 'report' in result.get('step_name', '').lower():
                    report_content = vm.read_file(f"/tmp/{result['step_name']}.json")
                    if report_content:
                        result['report_data'] = report_content

    except Exception as e:
        return response(500, {
            "error": f"MicroVM execution failed: {str(e)}",
            "review_id": review_id
        })

    # AI analysis with Bedrock
    ai_report = analyze_findings(repo_url, scan_results)

    # Build final report
    duration_ms = round((time.time() - start_time) * 1000)
    report = {
        "review_id": review_id,
        "repo_url": repo_url,
        "branch": branch,
        "checks": checks,
        "duration_ms": duration_ms,
        "scan_results": scan_results,
        "ai_analysis": ai_report,
        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    }

    # Store in S3
    s3.put_object(
        Bucket=RESULTS_BUCKET,
        Key=f"reviews/{review_id}.json",
        Body=json.dumps(report, indent=2),
        ContentType='application/json'
    )

    # Return summary (not full scan output)
    return response(200, {
        "review_id": review_id,
        "repo": repo_url,
        "duration_ms": duration_ms,
        "findings": ai_report.get('findings', {}),
        "risk_level": ai_report.get('risk_level', 'unknown'),
        "ai_summary": ai_report.get('summary', ''),
        "recommendations": ai_report.get('recommendations', [])
    })


def handle_status(event):
    """Get a previous review report by ID."""
    review_id = event['pathParameters']['review_id']

    try:
        obj = s3.get_object(Bucket=RESULTS_BUCKET, Key=f"reviews/{review_id}.json")
        report = json.loads(obj['Body'].read())
        return response(200, report)
    except s3.exceptions.NoSuchKey:
        return response(404, {"error": f"Review {review_id} not found"})


def build_review_steps(repo_url: str, branch: str, checks: list) -> list[dict]:
    """Build the list of commands to execute in the MicroVM."""
    steps = [
        {
            "name": "clone",
            "command": f"git clone --depth 1 --branch {branch} {repo_url} /workspace && ls /workspace",
            "timeout": 30,
            "abort_on_fail": True
        },
        {
            "name": "detect_language",
            "command": "cd /workspace && ls *.py requirements.txt setup.py pyproject.toml 2>/dev/null && echo 'PYTHON' || (ls package.json 2>/dev/null && echo 'NODE') || echo 'UNKNOWN'",
            "timeout": 5
        },
        {
            "name": "install_deps",
            "command": "cd /workspace && ([ -f requirements.txt ] && pip install -r requirements.txt 2>&1 | tail -5) || ([ -f package.json ] && npm install 2>&1 | tail -5) || echo 'No deps file found'",
            "timeout": 60
        }
    ]

    if 'security' in checks:
        steps.extend([
            {
                "name": "security_bandit",
                "command": "pip install bandit -q && cd /workspace && bandit -r . -f json --severity-level medium 2>/dev/null || true",
                "timeout": 45
            },
            {
                "name": "security_safety",
                "command": "pip install safety -q && cd /workspace && safety check --json 2>/dev/null || true",
                "timeout": 30
            }
        ])

    if 'quality' in checks:
        steps.extend([
            {
                "name": "quality_ruff",
                "command": "pip install ruff -q && cd /workspace && ruff check . --output-format json 2>/dev/null || true",
                "timeout": 30
            }
        ])

    if 'tests' in checks:
        steps.append({
            "name": "run_tests",
            "command": "cd /workspace && pip install pytest -q && pytest --tb=short -q 2>&1 | tail -20 || true",
            "timeout": 60
        })

    return steps


def response(status_code: int, body: dict) -> dict:
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Requested-With',
            'Access-Control-Allow-Methods': 'POST,GET,OPTIONS'
        },
        'body': json.dumps(body)
    }
