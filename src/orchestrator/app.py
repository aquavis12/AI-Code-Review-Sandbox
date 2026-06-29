"""
Orchestrator Lambda — Receives scan requests, manages MicroVM lifecycle.

Supports:
- POST /scan         → Scan PyPI package, npm package, or Git repo
- POST /review       → Legacy (same as /scan)
- GET  /review/{id}  → Get a previous scan report

Uses Lambda Function URL (no 30s timeout limit).
"""

import json
import os
import uuid
import time

import boto3


# Lazy imports for modules that may have heavy dependencies
_microvm_client = None
_reviewer = None
_scanners = None


def _get_microvm_client():
    global _microvm_client
    if _microvm_client is None:
        from microvm_client import MicroVMClient
        _microvm_client = MicroVMClient
    return _microvm_client


def _get_reviewer():
    global _reviewer
    if _reviewer is None:
        from reviewer import analyze_findings
        _reviewer = analyze_findings
    return _reviewer


def _get_scanners():
    global _scanners
    if _scanners is None:
        from scanners import build_scan_steps
        _scanners = build_scan_steps
    return _scanners


s3 = boto3.client('s3')
RESULTS_BUCKET = os.environ.get('RESULTS_BUCKET', '')


def handler(event, context):
    """Lambda Function URL entry point."""

    method = event.get('requestContext', {}).get('http', {}).get('method', '')
    path = event.get('rawPath', '')

    if method == 'POST' and ('/scan' in path or '/review' in path):
        return handle_scan(event)
    elif method == 'GET' and '/review/' in path:
        return handle_status(event)
    elif method == 'GET' and '/download/' in path:
        return handle_download(event)
    else:
        return response(404, {"error": "Not found"})


def handle_scan(event):
    """Execute a scan synchronously — Function URL allows up to 15 min."""
    raw_body = event.get('body', '{}')

    if event.get('isBase64Encoded', False):
        import base64
        raw_body = base64.b64decode(raw_body).decode('utf-8')

    try:
        body = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError:
        return response(400, {"error": "Invalid JSON body"})

    # Support both new format (target) and legacy (repo_url)
    if 'target' in body:
        target = body['target']
    elif 'repo_url' in body:
        target = {
            "type": "git",
            "name": body['repo_url'],
            "branch": body.get('branch', 'main'),
            "checks": body.get('checks', ['security', 'quality'])
        }
    else:
        return response(400, {"error": "Provide 'target' object or 'repo_url'"})

    if not target.get('name'):
        return response(400, {"error": "target.name is required"})

    scan_id = f"scan-{uuid.uuid4().hex[:8]}"
    start_time = time.time()

    # Build scan steps
    try:
        build_scan_steps = _get_scanners()
        steps = build_scan_steps(target)
    except ValueError as e:
        return response(400, {"error": str(e)})

    # Spawn MicroVM and execute
    try:
        MicroVMClient = _get_microvm_client()
        with MicroVMClient() as vm:
            print(f"MicroVM spawned for scan {scan_id} ({target['type']}: {target['name']})")
            scan_results = vm.execute_steps(steps)
    except Exception as e:
        return response(500, {
            "error": f"MicroVM execution failed: {str(e)}",
            "scan_id": scan_id
        })

    # AI analysis with Bedrock
    analyze_findings = _get_reviewer()
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

    # Generate presigned download URL (valid for 1 hour)
    report_url = ''
    try:
        report_url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': RESULTS_BUCKET, 'Key': f"scans/{scan_id}.json"},
            ExpiresIn=3600
        )
    except Exception:
        pass

    # Return summary
    return response(200, {
        "scan_id": scan_id,
        "target": target,
        "duration_ms": duration_ms,
        "risk_level": ai_report.get('risk_level', 'unknown'),
        "ai_summary": ai_report.get('summary', ''),
        "findings": ai_report.get('findings', {}),
        "recommendations": ai_report.get('recommendations', []),
        "report_url": report_url
    })


def handle_status(event):
    """Get a previous scan report by ID."""
    path_params = event.get('pathParameters', {})
    scan_id = path_params.get('review_id', '')

    # Function URL doesn't have pathParameters, parse from rawPath
    if not scan_id:
        path = event.get('rawPath', '')
        # /review/scan-abc123
        parts = path.strip('/').split('/')
        if len(parts) >= 2:
            scan_id = parts[-1]

    for prefix in ['scans/', 'reviews/']:
        try:
            obj = s3.get_object(Bucket=RESULTS_BUCKET, Key=f"{prefix}{scan_id}.json")
            report = json.loads(obj['Body'].read())
            return response(200, report)
        except Exception:
            continue

    return response(404, {"error": f"Scan {scan_id} not found"})


def handle_download(event):
    """Generate a presigned S3 URL for downloading a scan report."""
    path = event.get('rawPath', '')
    # /download/scan-abc123
    parts = path.strip('/').split('/')
    scan_id = parts[-1] if len(parts) >= 2 else ''

    if not scan_id:
        return response(400, {"error": "Scan ID required"})

    # Check if report exists
    key = f"scans/{scan_id}.json"
    try:
        s3.head_object(Bucket=RESULTS_BUCKET, Key=key)
    except Exception:
        return response(404, {"error": f"Report {scan_id} not found"})

    # Generate presigned URL (1 hour expiry)
    try:
        url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': RESULTS_BUCKET, 'Key': key},
            ExpiresIn=3600
        )
        return response(200, {"download_url": url, "scan_id": scan_id, "expires_in": 3600})
    except Exception as e:
        return response(500, {"error": f"Failed to generate download URL: {str(e)}"})


def response(status_code: int, body: dict) -> dict:
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json'
        },
        'body': json.dumps(body)
    }
