"""
Context Skills — Provides Bedrock with awareness of what's being scanned.

Before the AI reviewer analyzes scan results, context skills inject relevant
background knowledge so the model understands:
- What the package/repo does
- Known vulnerability patterns for that ecosystem
- Common attack vectors for that category of software
- Historical CVE patterns for similar packages

This makes the AI review significantly more accurate and specific.
"""

import json
import os


# Ecosystem-level context skills
ECOSYSTEM_SKILLS = {
    "pypi": {
        "name": "Python/PyPI Security Context",
        "context": """
## Python/PyPI Ecosystem Knowledge

### Common Attack Vectors
- setup.py / pyproject.toml install hooks executing arbitrary code
- Native C extensions hiding malicious code in binary wheels
- Typosquatting (e.g. `reqeusts`, `python-dateutil` vs `dateutil`)
- Dependency confusion (internal package names on public PyPI)
- Data exfiltration via requests/urllib/socket during install

### High-Risk Patterns to Flag
- `os.system()`, `subprocess.Popen()`, `eval()`, `exec()` in setup.py
- Network calls during package installation
- Base64 encoded payloads in source files
- Accessing environment variables (AWS keys, tokens)
- Writing to /etc/, ~/.ssh/, or other sensitive paths

### Known Vulnerable Libraries (check versions)
- urllib3 < 2.0.7 (CVE-2023-45803, CVE-2023-43804)
- requests < 2.31.0 (CVE-2023-32681)
- cryptography < 41.0.4 (multiple CVEs)
- pillow < 10.0.1 (CVE-2023-44271)
- django < 4.2.8 (multiple CVEs)
- flask < 2.3.3 (CVE-2023-30861)
"""
    },
    "npm": {
        "name": "Node.js/npm Security Context",
        "context": """
## Node.js/npm Ecosystem Knowledge

### Common Attack Vectors
- preinstall/postinstall scripts in package.json
- eval() / Function() constructor for code execution
- process.env access to steal credentials
- child_process.exec/spawn for command injection
- Prototype pollution via deep merge utilities
- ReDoS (Regular Expression Denial of Service)

### High-Risk Patterns to Flag
- Scripts field in package.json (preinstall, postinstall, prepare)
- require('child_process'), require('net'), require('http')
- Buffer.from() with 'base64' encoding (obfuscation)
- process.env reading AWS_ACCESS_KEY, DATABASE_URL, etc.
- Dynamic require() or import() with user-controlled paths
- Extremely deep dependency trees (>5 levels = higher supply chain risk)

### Known Vulnerable Libraries (check versions)
- lodash < 4.17.21 (prototype pollution)
- express < 4.18.2 (multiple CVEs)
- jsonwebtoken < 9.0.0 (CVE-2022-23529)
- axios < 1.6.0 (SSRF, CVE-2023-45857)
- minimatch < 3.0.5 (ReDoS)
- semver < 7.5.2 (ReDoS)
"""
    },
    "mvn": {
        "name": "Java/Maven Security Context",
        "context": """
## Java/Maven Ecosystem Knowledge

### Common Attack Vectors
- Deserialization vulnerabilities (ObjectInputStream)
- Log injection (log4j, logback)
- XML External Entity (XXE) processing
- SQL injection via JDBC string concatenation
- Classpath manipulation via transitive dependencies

### High-Risk Patterns to Flag
- ObjectInputStream.readObject() without validation
- Runtime.getRuntime().exec() for command execution
- XMLInputFactory without disabling external entities
- String concatenation in SQL queries (not PreparedStatement)
- Reflection-based method invocation (invoke())
- Shaded/relocated dependencies hiding vulnerable versions

### Known Vulnerable Libraries (check versions)
- log4j-core < 2.17.1 (CVE-2021-44228, Log4Shell)
- jackson-databind < 2.14.0 (deserialization CVEs)
- commons-text < 1.10.0 (CVE-2022-42889, Text4Shell)
- spring-core < 5.3.18 (CVE-2022-22965, Spring4Shell)
- commons-collections < 3.2.2 (deserialization gadgets)
- snakeyaml < 2.0 (CVE-2022-1471, RCE via YAML deserialization)
"""
    },
    "git": {
        "name": "Source Repository Security Context",
        "context": """
## Source Repository Security Knowledge

### Common Vulnerability Categories
- Hardcoded secrets (API keys, passwords, tokens in source)
- SQL injection patterns (string formatting in queries)
- Command injection (os.system, subprocess with user input)
- Path traversal (../../../etc/passwd patterns)
- SSRF (Server-Side Request Forgery via user-controlled URLs)
- Insecure deserialization (pickle, yaml.load, JSON.parse of untrusted)
- Missing authentication/authorization checks
- Sensitive data exposure (PII in logs, debug endpoints)

### Files to Prioritize
- .env, .env.local, config files (secrets)
- Dockerfile, docker-compose.yml (exposed ports, base images)
- CI/CD configs (.github/workflows/, Jenkinsfile)
- Authentication/authorization modules
- Database migration files
- API route handlers (input validation)

### Patterns That Indicate High Quality
- Input validation on all external data
- Parameterized queries (not string interpolation)
- Proper error handling (no stack traces to users)
- Dependency pinning (exact versions in lockfile)
- Security headers in HTTP responses
- Rate limiting on authentication endpoints
"""
    }
}


# Package-specific context (popular packages with known history)
PACKAGE_CONTEXT = {
    "requests": "Popular HTTP library. Check urllib3 transitive dep for CVEs. Historically safe but often typosquatted.",
    "flask": "Micro web framework. Check for debug mode enabled, secret key exposure, SSTI vulnerabilities.",
    "django": "Full web framework. Check for ALLOWED_HOSTS, DEBUG=True, SECRET_KEY exposure, SQL injection in raw queries.",
    "express": "Node.js web framework. Check for missing helmet, CORS misconfiguration, body-parser limits.",
    "lodash": "Utility library. Historical prototype pollution issues. Check version is >= 4.17.21.",
    "axios": "HTTP client. Check for SSRF via baseURL manipulation. Version < 1.6.0 has CVE-2023-45857.",
    "log4j-core": "CRITICAL HISTORY: Log4Shell (CVE-2021-44228). Any version < 2.17.1 is vulnerable to RCE.",
    "jackson-databind": "JSON serialization. Long history of deserialization CVEs. Check for polymorphic type handling.",
    "numpy": "Numerical computing. Generally safe. Check native C extensions for buffer overflows.",
    "pandas": "Data analysis. Generally safe. Watch for pickle deserialization of untrusted data.",
    "fastapi": "Modern web framework. Check for missing input validation, exposed docs endpoint in production.",
    "jsonwebtoken": "JWT library. Version < 9.0.0 has algorithm confusion vulnerability.",
    "webpack": "Build tool. Check for prototype pollution in loaders, eval usage in dev server.",
    "next": "React framework. Check for SSRF in image optimization, exposed _next/data endpoints.",
}


# User-uploaded custom skills directory
CUSTOM_SKILLS_DIR = os.environ.get('CUSTOM_SKILLS_DIR', '/tmp/context_skills')


def get_context_skill(target_type: str, target_name: str) -> str:
    """
    Build a context skill string for the AI reviewer.
    
    Returns ecosystem knowledge + package-specific context that gets
    prepended to the scan results before sending to Bedrock.
    """
    context_parts = []

    # Ecosystem skill
    ecosystem = ECOSYSTEM_SKILLS.get(target_type)
    if ecosystem:
        context_parts.append(f"## Context Skill: {ecosystem['name']}")
        context_parts.append(ecosystem['context'])

    # Package-specific context
    pkg_name = target_name.split('/')[-1].split(':')[-1].lower()  # normalize
    if pkg_name in PACKAGE_CONTEXT:
        context_parts.append(f"\n## Package Intelligence: {pkg_name}")
        context_parts.append(PACKAGE_CONTEXT[pkg_name])

    # User-uploaded custom skills (.md files)
    custom_context = _load_custom_skills(target_type, pkg_name)
    if custom_context:
        context_parts.append("\n## Custom Context (User-Provided)")
        context_parts.append(custom_context)

    return "\n".join(context_parts) if context_parts else ""


def _load_custom_skills(target_type: str, target_name: str) -> str:
    """
    Load user-uploaded .md skill files from S3 (synced to /tmp/context_skills/).
    
    Users can upload markdown files with extra context:
      - context_skills/{target_type}.md  (ecosystem-level override)
      - context_skills/{package_name}.md (package-specific context)
      - context_skills/global.md         (applies to all scans)
    """
    if not os.path.isdir(CUSTOM_SKILLS_DIR):
        return ""

    content_parts = []

    # Load order: global → ecosystem → package-specific
    for filename in ['global.md', f'{target_type}.md', f'{target_name}.md']:
        filepath = os.path.join(CUSTOM_SKILLS_DIR, filename)
        if os.path.isfile(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content_parts.append(f.read().strip())
            except Exception:
                pass

    return "\n\n".join(content_parts) if content_parts else ""


def list_skills() -> list[dict]:
    """List all available context skills (for API/UI display)."""
    skills = []
    for key, skill in ECOSYSTEM_SKILLS.items():
        skills.append({
            "id": key,
            "name": skill["name"],
            "type": "ecosystem"
        })
    return skills
