"""
MicroVM Client — Real AWS Lambda MicroVMs API.

Uses: aws lambda-microvms CLI / boto3
Flow: create-microvm-image → run-microvm → create-auth-token → send commands → terminate
"""

import json
import time
import os
import requests
import boto3


REGION = os.environ.get('AWS_REGION', 'us-east-1')
IMAGE_NAME = os.environ.get('MICROVM_IMAGE_NAME', 'code-review-sandbox')
ACCOUNT_ID = None


def _get_account_id():
    """Get AWS account ID (cached)."""
    global ACCOUNT_ID
    if ACCOUNT_ID is None:
        sts = boto3.client('sts', region_name=REGION)
        ACCOUNT_ID = sts.get_caller_identity()['Account']
    return ACCOUNT_ID


def _get_image_arn():
    """Build full ARN for the MicroVM image."""
    name = IMAGE_NAME
    # If already a full ARN, use as-is
    if name.startswith('arn:'):
        return name
    # Otherwise build it
    account_id = _get_account_id()
    return f'arn:aws:lambda:{REGION}:{account_id}:microvm-image:{name}'


class MicroVMClient:
    """Manages a Lambda MicroVM lifecycle for code review."""

    def __init__(self):
        self.client = boto3.client('lambda-microvms', region_name=REGION)
        self.microvm_id = None
        self.endpoint = None
        self.auth_token = None

    def spawn(self) -> str:
        """Run a new MicroVM from the pre-built image. Returns the endpoint URL."""

        response = self.client.run_microvm(
            imageIdentifier=_get_image_arn(),
            ingressNetworkConnectors=[
                f'arn:aws:lambda:{REGION}:aws:network-connector:aws-network-connector:ALL_INGRESS'
            ],
            egressNetworkConnectors=[
                f'arn:aws:lambda:{REGION}:aws:network-connector:aws-network-connector:INTERNET_EGRESS'
            ],
            idlePolicy={
                'autoResumeEnabled': True,
                'maxIdleDurationSeconds': 300,
                'suspendedDurationSeconds': 60
            }
        )

        self.microvm_id = response['microvmId']
        self.endpoint = f"https://{response['endpoint']}"

        # Wait for RUNNING state
        self._wait_for_running()

        # Generate auth token
        token_response = self.client.create_microvm_auth_token(
            microvmIdentifier=self.microvm_id,
            expirationInMinutes=10,
            allowedPorts=[{'allPorts': {}}]
        )
        # Token may be a string or a dict with header name as key
        token = token_response['authToken']
        if isinstance(token, dict):
            # Extract the token value from the dict
            self.auth_token = list(token.values())[0]
        else:
            self.auth_token = token

        print(f"MicroVM running: {self.microvm_id}")
        print(f"Endpoint: {self.endpoint}")
        return self.endpoint

    def execute(self, command: str, timeout: int = 60) -> dict:
        """Execute a shell command in the running MicroVM via its HTTP API."""

        response = requests.post(
            f"{self.endpoint}/exec",
            headers={
                'X-aws-proxy-auth': self.auth_token,
                'Content-Type': 'application/json'
            },
            json={
                'command': command,
                'timeout': timeout
            },
            timeout=timeout + 10
        )

        if response.status_code != 200:
            return {
                'stdout': '',
                'stderr': f'MicroVM returned {response.status_code}: {response.text}',
                'exit_code': -1,
                'duration_ms': 0
            }

        result = response.json()
        return {
            'stdout': result.get('stdout', ''),
            'stderr': result.get('stderr', ''),
            'exit_code': result.get('exitCode', -1),
            'duration_ms': result.get('durationMs', 0)
        }

    def execute_steps(self, steps: list[dict]) -> list[dict]:
        """Execute multiple commands sequentially. State persists between steps."""
        results = []
        for step in steps:
            print(f"  → {step['name']}: {step['command'][:80]}...")
            result = self.execute(
                step['command'],
                timeout=step.get('timeout', 60)
            )
            result['step_name'] = step['name']
            results.append(result)

            # Abort on critical failure if configured
            if step.get('abort_on_fail') and result['exit_code'] != 0:
                print(f"  ✗ Step '{step['name']}' failed, aborting")
                break

        return results

    def read_file(self, path: str) -> str:
        """Read a file from the MicroVM filesystem."""
        result = self.execute(f"cat {path}")
        if result['exit_code'] == 0:
            return result['stdout']
        return ""

    def terminate(self):
        """Terminate the MicroVM."""
        if self.microvm_id:
            try:
                self.client.terminate_microvm(microvmIdentifier=self.microvm_id)
                print(f"MicroVM terminated: {self.microvm_id}")
            except Exception as e:
                print(f"Warning: Failed to terminate MicroVM {self.microvm_id}: {e}")
            self.microvm_id = None
            self.endpoint = None

    def _wait_for_running(self, max_wait: int = 30):
        """Poll until MicroVM reaches RUNNING state."""
        start = time.time()
        while time.time() - start < max_wait:
            response = self.client.get_microvm(microvmIdentifier=self.microvm_id)
            state = response.get('state', '')
            if state == 'RUNNING':
                return
            elif state in ('FAILED', 'TERMINATED'):
                raise RuntimeError(f"MicroVM failed to start: {state}")
            time.sleep(1)
        raise TimeoutError(f"MicroVM {self.microvm_id} not RUNNING after {max_wait}s")

    def __enter__(self):
        self.spawn()
        return self

    def __exit__(self, *args):
        self.terminate()
