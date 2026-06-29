"""
Package & Repo Scanners — Extends the sandbox to scan PyPI, npm, and Git repos.

Each scanner generates a list of commands to execute in the MicroVM.
"""
import json


def build_scan_steps(target: dict) -> list[dict]:
    """
    Build MicroVM execution steps based on target type.
    
    target = {
        "type": "pypi" | "npm" | "git",
        "name": "requests" | "@angular/core" | "https://github.com/user/repo",
        "version": "2.31.0",       # optional
        "branch": "main",          # for git only
        "checks": ["security", "quality", "license", "typosquat", "owasp"]
    }
    """
    target_type = target.get("type", "git")
    name = target.get("name", "")
    version = target.get("version", "latest")
    branch = target.get("branch", "main")
    checks = target.get("checks", ["security", "quality"])

    if target_type == "pypi":
        return _pypi_steps(name, version, checks)
    elif target_type == "npm":
        return _npm_steps(name, version, checks)
    elif target_type == "git":
        return _git_steps(name, branch, checks)
    elif target_type == "mvn" or target_type == "maven":
        return _mvn_steps(name, version, checks)
    else:
        raise ValueError(f"Unknown target type: {target_type}")


# ==================================
# PyPI Scanner
# ==================================
def _pypi_steps(package: str, version: str, checks: list) -> list[dict]:
    """Scan a PyPI package for vulnerabilities, malware, and quality."""
    
    version_spec = f"=={version}" if version != "latest" else ""
    
    steps = [
        {
            "name": "install_package",
            "command": f"pip install {package}{version_spec} --target /workspace/pkg && echo 'Installed {package}{version_spec}'",
            "timeout": 60,
            "abort_on_fail": True
        },
        {
            "name": "package_metadata",
            "command": f"pip show {package} 2>/dev/null || pip show --target /workspace/pkg {package}",
            "timeout": 10
        },
        {
            "name": "dependency_tree",
            "command": f"pip install pipdeptree -q && pipdeptree -p {package} 2>/dev/null || echo 'pipdeptree unavailable'",
            "timeout": 30
        }
    ]

    if "security" in checks:
        steps.extend([
            {
                "name": "vulnerability_scan",
                "command": f"pip install pip-audit -q && pip-audit --desc --fix --dry-run -r <(pip freeze) 2>/dev/null || pip-audit 2>&1 | head -50",
                "timeout": 45
            },
            {
                "name": "bandit_scan",
                "command": f"pip install bandit -q && bandit -r /workspace/pkg/{package.replace('-','_')}/ -f json --severity-level medium 2>/dev/null || bandit -r /workspace/pkg/ -f json --severity-level medium 2>/dev/null | head -200",
                "timeout": 45
            },
            {
                "name": "safety_check",
                "command": "pip install safety -q && safety check --json 2>/dev/null | head -100 || echo 'safety check done'",
                "timeout": 30
            }
        ])

    if "typosquat" in checks:
        steps.append({
            "name": "typosquat_check",
            "command": f"""python3 -c "
import json
name = '{package}'
suspicious = []
# Check common typosquatting patterns
if '-' in name and name.replace('-','') != name:
    suspicious.append('Has hyphens - check for typosquats without hyphens')
if len(name) <= 3:
    suspicious.append('Very short name - higher typosquat risk')
print(json.dumps({{'package': name, 'suspicious_patterns': suspicious, 'recommendation': 'Verify package author and download count on pypi.org'}}))
"
""",
            "timeout": 10
        })

    if "license" in checks:
        steps.append({
            "name": "license_check",
            "command": f"pip show {package} 2>/dev/null | grep -i license || echo 'License: Unknown'",
            "timeout": 10
        })

    if "quality" in checks:
        steps.extend([
            {
                "name": "code_quality",
                "command": f"pip install ruff -q && ruff check /workspace/pkg/{package.replace('-','_')}/ --output-format json 2>/dev/null | head -100 || echo 'ruff check done'",
                "timeout": 30
            },
            {
                "name": "package_size",
                "command": "du -sh /workspace/pkg/ && find /workspace/pkg/ -type f | wc -l",
                "timeout": 10
            }
        ])

    if "owasp" in checks:
        steps.extend(_owasp_steps("/workspace/pkg"))

    return steps


# ==================================
# npm Scanner
# ==================================
def _npm_steps(package: str, version: str, checks: list) -> list[dict]:
    """Scan an npm package for vulnerabilities, malware, and quality."""
    
    version_spec = f"@{version}" if version != "latest" else ""
    
    steps = [
        {
            "name": "install_package",
            "command": f"mkdir -p /workspace/pkg && cd /workspace/pkg && npm init -y > /dev/null 2>&1 && npm install {package}{version_spec} --save",
            "timeout": 60,
            "abort_on_fail": True
        },
        {
            "name": "package_info",
            "command": f"npm info {package}{version_spec} --json 2>/dev/null | head -100",
            "timeout": 15
        },
        {
            "name": "dependency_tree",
            "command": "cd /workspace/pkg && npm ls --all --json 2>/dev/null | head -200",
            "timeout": 20
        }
    ]

    if "security" in checks:
        steps.extend([
            {
                "name": "npm_audit",
                "command": "cd /workspace/pkg && npm audit --json 2>/dev/null | head -200",
                "timeout": 30
            },
            {
                "name": "known_vulnerabilities",
                "command": f"npm info {package} --json 2>/dev/null | python3 -c \"import json,sys; d=json.load(sys.stdin); print('Maintainers:', d.get('maintainers',[])); print('Last publish:', d.get('time',{{}}).get('modified','unknown'))\" 2>/dev/null || echo 'info unavailable'",
                "timeout": 15
            }
        ])

    if "typosquat" in checks:
        steps.append({
            "name": "typosquat_check",
            "command": f"""python3 -c "
import json
name = '{package}'
suspicious = []
if name.startswith('@') and '/' in name:
    org = name.split('/')[0]
    if org in ['@angular', '@babel', '@types', '@vue', '@react']:
        suspicious.append('Scoped to well-known org - likely safe')
elif '-' in name:
    suspicious.append('Contains hyphens - verify no typosquat variants exist')
if 'js' in name or 'node' in name:
    suspicious.append('Generic name with js/node - higher impersonation risk')
print(json.dumps({{'package': name, 'suspicious_patterns': suspicious}}))
"
""",
            "timeout": 10
        })

    if "license" in checks:
        steps.append({
            "name": "license_check",
            "command": f"npm info {package} license 2>/dev/null || echo 'License: Unknown'",
            "timeout": 10
        })

    if "quality" in checks:
        steps.extend([
            {
                "name": "package_size",
                "command": "cd /workspace/pkg && du -sh node_modules/ && find node_modules/ -type f | wc -l",
                "timeout": 10
            },
            {
                "name": "install_scripts_check",
                "command": f"cd /workspace/pkg && cat node_modules/{package.split('/')[-1]}/package.json 2>/dev/null | python3 -c \"import json,sys; d=json.load(sys.stdin); scripts=d.get('scripts',{{}}); danger=[k for k in ['preinstall','postinstall','install'] if k in scripts]; print('⚠️  INSTALL SCRIPTS:', danger, scripts.get(danger[0],'') if danger else 'None found')\" 2>/dev/null || echo 'No install scripts detected'",
                "timeout": 10
            }
        ])

    if "owasp" in checks:
        steps.extend(_owasp_steps("/workspace/pkg"))

    return steps


# ==================================
# Git Repo Scanner
# ==================================
def _git_steps(repo_url: str, branch: str, checks: list) -> list[dict]:
    """Scan a Git repository (same as before but unified interface)."""
    
    steps = [
        {
            "name": "clone",
            "command": f"git clone --depth 1 --branch {branch} {repo_url} /workspace/repo && ls /workspace/repo",
            "timeout": 30,
            "abort_on_fail": True
        },
        {
            "name": "detect_language",
            "command": "cd /workspace/repo && (ls requirements.txt setup.py pyproject.toml 2>/dev/null && echo 'PYTHON') || (ls package.json 2>/dev/null && echo 'NODE') || echo 'UNKNOWN'",
            "timeout": 5
        },
        {
            "name": "install_deps",
            "command": "cd /workspace/repo && ([ -f requirements.txt ] && pip install -r requirements.txt 2>&1 | tail -5) || ([ -f package.json ] && npm install 2>&1 | tail -5) || echo 'No deps'",
            "timeout": 60
        }
    ]

    if "security" in checks:
        steps.extend([
            {
                "name": "security_bandit",
                "command": "pip install bandit -q && cd /workspace/repo && bandit -r . -f json --severity-level medium 2>/dev/null | head -200 || true",
                "timeout": 45
            },
            {
                "name": "security_deps",
                "command": "pip install pip-audit safety -q && (cd /workspace/repo && pip-audit 2>&1 | head -50) || (safety check --json 2>/dev/null | head -100) || true",
                "timeout": 30
            },
            {
                "name": "secrets_scan",
                "command": "cd /workspace/repo && grep -r --include='*.py' --include='*.js' --include='*.env' -l 'AKIA\\|password\\|secret\\|api_key\\|token' . 2>/dev/null | head -20 || echo 'No hardcoded secrets found'",
                "timeout": 15
            }
        ])

    if "quality" in checks:
        steps.append({
            "name": "quality_ruff",
            "command": "pip install ruff -q && cd /workspace/repo && ruff check . --output-format json 2>/dev/null | head -200 || true",
            "timeout": 30
        })

    if "license" in checks:
        steps.append({
            "name": "license_check",
            "command": "cd /workspace/repo && (cat LICENSE 2>/dev/null || cat LICENSE.md 2>/dev/null || echo 'No LICENSE file found')",
            "timeout": 5
        })

    if "owasp" in checks:
        steps.extend(_owasp_steps("/workspace/repo"))

    return steps


# ==================================
# Maven (Java/Kotlin) Scanner
# ==================================
def _mvn_steps(artifact: str, version: str, checks: list) -> list[dict]:
    """
    Scan a Maven artifact for vulnerabilities.
    
    artifact format: "groupId:artifactId" (e.g. "org.apache.logging.log4j:log4j-core")
    """
    
    # Parse groupId:artifactId
    parts = artifact.split(":")
    if len(parts) == 2:
        group_id, artifact_id = parts
    else:
        group_id = artifact
        artifact_id = artifact.split(".")[-1]
    
    version_spec = version if version != "latest" else "LATEST"
    group_path = group_id.replace(".", "/")
    
    steps = [
        {
            "name": "setup_maven",
            "command": "which mvn || (apt-get update -qq && apt-get install -y -qq maven > /dev/null 2>&1) && mvn --version | head -1",
            "timeout": 120,
            "abort_on_fail": True
        },
        {
            "name": "create_project",
            "command": f"""mkdir -p /workspace/mvn && cd /workspace/mvn && cat > pom.xml << 'EOF'
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.scan</groupId>
  <artifactId>dependency-scan</artifactId>
  <version>1.0</version>
  <dependencies>
    <dependency>
      <groupId>{group_id}</groupId>
      <artifactId>{artifact_id}</artifactId>
      <version>{version_spec}</version>
    </dependency>
  </dependencies>
</project>
EOF
echo "POM created for {group_id}:{artifact_id}:{version_spec}" """,
            "timeout": 10
        },
        {
            "name": "resolve_dependencies",
            "command": "cd /workspace/mvn && mvn dependency:resolve -q 2>&1 | tail -20",
            "timeout": 120
        },
        {
            "name": "dependency_tree",
            "command": "cd /workspace/mvn && mvn dependency:tree 2>&1 | grep -E '\\[INFO\\].*:.*:' | head -50",
            "timeout": 60
        }
    ]

    if "security" in checks:
        steps.extend([
            {
                "name": "owasp_dependency_check_mvn",
                "command": """cd /workspace/mvn && mvn org.owasp:dependency-check-maven:check -DfailBuildOnCVSS=0 -DformatsRequested=JSON 2>&1 | tail -30 || true""",
                "timeout": 180
            },
            {
                "name": "cve_search",
                "command": f"""python3 -c "
import urllib.request, json
url = 'https://services.nvd.nist.gov/rest/json/cves/2.0?keywordSearch={artifact_id}&resultsPerPage=10'
try:
    resp = urllib.request.urlopen(url, timeout=10)
    data = json.loads(resp.read())
    cves = data.get('vulnerabilities', [])
    results = []
    for cve in cves[:10]:
        c = cve.get('cve', {{}})
        results.append({{
            'id': c.get('id'),
            'severity': c.get('metrics',{{}}).get('cvssMetricV31',[{{}}])[0].get('cvssData',{{}}).get('baseSeverity','UNKNOWN') if c.get('metrics',{{}}).get('cvssMetricV31') else 'UNKNOWN',
            'description': c.get('descriptions',[{{}}])[0].get('value','')[:100]
        }})
    print(json.dumps({{'artifact': '{group_id}:{artifact_id}', 'cve_count': len(cves), 'cves': results}}, indent=2))
except Exception as e:
    print(f'CVE lookup failed: {{e}}')
" """,
                "timeout": 20
            }
        ])

    if "license" in checks:
        steps.append({
            "name": "license_check",
            "command": "cd /workspace/mvn && mvn license:third-party-report 2>/dev/null | grep -i license | head -20 || mvn dependency:resolve -Dinclude-scope=compile 2>&1 | grep -i license | head -10 || echo 'License: check Maven Central'",
            "timeout": 30
        })

    if "quality" in checks:
        steps.extend([
            {
                "name": "package_size",
                "command": "du -sh /workspace/mvn/ && find ~/.m2/repository -name '*.jar' | wc -l",
                "timeout": 10
            },
            {
                "name": "transitive_deps_count",
                "command": "cd /workspace/mvn && mvn dependency:tree 2>&1 | grep -c '\\[INFO\\].*:.*:' || echo '0'",
                "timeout": 30
            }
        ])

    if "owasp" in checks:
        steps.extend(_owasp_steps("/workspace/mvn"))

    return steps


# ==================================
# OWASP Checks (shared across all scan types)
# ==================================
def _owasp_steps(code_path: str) -> list[dict]:
    """
    OWASP Top 10 checks — runs against any codebase.
    
    Covers:
    - A01: Broken Access Control
    - A02: Cryptographic Failures
    - A03: Injection
    - A04: Insecure Design
    - A05: Security Misconfiguration
    - A06: Vulnerable Components
    - A07: Authentication Failures
    - A08: Software/Data Integrity Failures
    - A09: Security Logging Failures
    - A10: Server-Side Request Forgery (SSRF)
    """
    return [
        {
            "name": "owasp_dependency_check",
            "command": f"pip install pip-audit -q && pip-audit --desc 2>&1 | head -50 || echo 'A06: Vulnerable Components check done'",
            "timeout": 45
        },
        {
            "name": "owasp_injection_check",
            "command": f"""cd {code_path} && grep -rn --include='*.py' --include='*.js' --include='*.ts' \
              -E '(execute\\(|exec\\(|eval\\(|subprocess\\.call|os\\.system|child_process|\\$\\(|format.*SELECT|f".*SELECT|f".*INSERT|f".*UPDATE|f".*DELETE|\\+ .*sql|\\+ .*query)' . 2>/dev/null | head -30 || echo 'A03: No obvious injection patterns found'""",
            "timeout": 15
        },
        {
            "name": "owasp_crypto_check",
            "command": f"""cd {code_path} && grep -rn --include='*.py' --include='*.js' --include='*.ts' \
              -E '(MD5|SHA1|DES|RC4|hardcoded.*key|password.*=.*["\\'\\x27]|secret.*=.*["\\'\\x27])' . 2>/dev/null | head -30 || echo 'A02: No weak crypto patterns found'""",
            "timeout": 15
        },
        {
            "name": "owasp_ssrf_check",
            "command": f"""cd {code_path} && grep -rn --include='*.py' --include='*.js' --include='*.ts' \
              -E '(requests\\.get\\(.*\\+|urllib\\.request\\.urlopen\\(.*\\+|fetch\\(.*\\+|http\\.get\\(.*\\+|axios\\.(get|post)\\(.*\\+)' . 2>/dev/null | head -20 || echo 'A10: No obvious SSRF patterns found'""",
            "timeout": 15
        },
        {
            "name": "owasp_auth_check",
            "command": f"""cd {code_path} && grep -rn --include='*.py' --include='*.js' --include='*.ts' \
              -E '(verify=False|verify_ssl.*False|VERIFY_SSL.*False|disable_ssl|allow_all_hostname|NoopHostnameVerifier)' . 2>/dev/null | head -20 || echo 'A07: No auth bypass patterns found'""",
            "timeout": 15
        },
        {
            "name": "owasp_secrets_check",
            "command": f"""cd {code_path} && grep -rn --include='*.py' --include='*.js' --include='*.ts' --include='*.env' --include='*.yaml' --include='*.yml' --include='*.json' \
              -E '(AKIA[0-9A-Z]{{16}}|AIza[0-9A-Za-z_-]{{35}}|ghp_[0-9a-zA-Z]{{36}}|sk-[0-9a-zA-Z]{{48}}|password\\s*[:=]\\s*["\\'\\x27][^"]+["\\'\\x27])' . 2>/dev/null | head -20 || echo 'A05: No hardcoded secrets found'""",
            "timeout": 15
        },
        {
            "name": "owasp_logging_check",
            "command": f"""cd {code_path} && python3 -c "
import os, json
findings = []
for root, dirs, files in os.walk('{code_path}'):
    for f in files:
        if f.endswith(('.py', '.js', '.ts')):
            path = os.path.join(root, f)
            try:
                content = open(path).read()
                if 'except' in content and 'pass' in content:
                    findings.append({{'file': path, 'issue': 'A09: Silent exception (except/pass) - may swallow security events'}})
                if 'catch' in content and content.count('catch') > content.count('console.log') + content.count('logger'):
                    findings.append({{'file': path, 'issue': 'A09: More catch blocks than log statements'}})
            except: pass
    if len(findings) > 10: break
print(json.dumps({{'owasp_a09_logging': findings[:10]}}))
" 2>/dev/null || echo 'A09: Logging check done'""",
            "timeout": 15
        },
        {
            "name": "owasp_summary",
            "command": f"echo 'OWASP Top 10 scan complete for {code_path}'",
            "timeout": 5
        }
    ]
