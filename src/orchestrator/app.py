"""
Orchestrator Lambda — Receives scan requests, manages MicroVM lifecycle.

Supports:
- POST /review       → Scan a Git repo (legacy)
- POST /scan         → Scan PyPI package, npm package, or Git repo
- GET  /review/{id}  → Get a previous scan report

Flow:
1. Receive request with target (pypi/npm/git)
2. Spawn a Lambda MicroVM
3. Execute scan steps (install, audit, analyze)
4. Collect results → send to Bedrock Kimi K2.5 for AI analysis
5. Store report in S3
6. Terminate MicroVM
7. Return scan report
"""

import json
import os
import uuid
import time

import boto3
from microvm_client import MicroVMClient
from reviewer import analyze_findings
from scanners import build_scan_steps

s3 = boto3.client('s3')
RESULTS_BUCKET = os.environ['RESULTS_BUCKET']


def handler(event, context):
    """API Gateway entry point."""
    
    # HTTP API v2 format
    route_key = event.get('routeKey', '')
    method = event.get('requestContext', {}).get('http', {}).get('method', '')
    path = event.get('rawPath', '')

    if method == 'POST' and ('/scan' in path or '/review' in path):
        return handle_scan(event)
    elif method == 'GET' and '/review/' in path:
        return handle_status(event)
    else:
        return response(404, {"error": "Not found"})


def handle_scan(event):
    """Execute a scan in an isolated MicroVM."""
    body = json.loads(event.get('body', '{}'))

    # Support both new format (target) and legacy (repo_url)
    if 'target' in body:
        target = body['target']
    elif 'repo_url' in body:
        # Legacy format
        target = {
            "type": "git",
            "name": body['repo_url'],
            "branch": body.get('branch', 'main'),
            "checks": body.get('checks', ['security', 'quality'])
        }
    else:
        return response(400, {"error": "Provide 'target' object or 'repo_url'"})

    # Validate
    if not target.get('name'):
        return response(400, {"error": "target.name is required"})

    scan_id = f"scan-{uuid.uuid4().hex[:8]}"
    start_time = time.time()

    # Build scan steps based on target type
    try:
        steps = build_scan_steps(target)
    except ValueError as e:
        return response(400, {"error": str(e)})

    # Spawn MicroVM and execute
    try:
        with MicroVMClient() as vm:
            print(f"MicroVM spawned for scan {scan_id} ({target['type']}: {target['name']})")
            scan_results = vm.execute_steps(steps)
    except Exception as e:
        return response(500, {
            "error": f"MicroVM execution failed: {str(e)}",
            "scan_id": scan_id
        })

    # AI analysis with Bedrock Kimi K2.5
    ai_report = analyze_findings(
        f"{target['type']}:{target['name']}",
        scan_results
    )

    # Build final report
    duration_ms = round((time.time() - start_time) * 1000)
    report = {
        "scan_id": scan_id,
        "target": target,
        "duration_ms": duration_ms,
        "scan_results": scan_results,
        "ai_analysis": ai_report,
        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    }

    # Store in S3
    s3.put_object(
        Bucket=RESULTS_BUCKET,
        Key=f"scans/{scan_id}.json",
        Body=json.dumps(report, indent=2),
        ContentType='application/json'
    )

    # Return summary
    return response(200, {
        "scan_id": scan_id,
        "target": target,
        "duration_ms": duration_ms,
        "risk_level": ai_report.get('risk_level', 'unknown'),
        "ai_summary": ai_report.get('summary', ''),
        "findings": ai_report.get('findings', {}),
        "recommendations": ai_report.get('recommendations', [])
    })


def handle_status(event):
    """Get a previous scan report by ID."""
    path_params = event.get('pathParameters', {})
    scan_id = path_params.get('review_id', '')

    # Try both prefixes
    for prefix in ['scans/', 'reviews/']:
        try:
            obj = s3.get_object(Bucket=RESULTS_BUCKET, Key=f"{prefix}{scan_id}.json")
            report = json.loads(obj['Body'].read())
            return response(200, report)
        except Exception:
            continue

    return response(404, {"error": f"Scan {scan_id} not found"})


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
