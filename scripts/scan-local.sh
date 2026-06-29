#!/usr/bin/env bash
# Run a scan locally (no MicroVM, no AWS needed)
# Usage:
#   ./scripts/scan-local.sh pypi requests 2.31.0
#   ./scripts/scan-local.sh npm express 4.18.2
#   ./scripts/scan-local.sh mvn org.apache.logging.log4j:log4j-core 2.17.1
#   ./scripts/scan-local.sh git https://github.com/psf/requests main

set -e

TYPE="${1:-pypi}"
NAME="${2:-requests}"
VERSION="${3:-latest}"

echo "============================================"
echo "🛡️  AI Code Review Sandbox — Local Scan"
echo "============================================"
echo ""
echo "Target:  $TYPE"
echo "Package: $NAME"
echo "Version: $VERSION"
echo ""

WORKSPACE=$(mktemp -d)
echo "Workspace: $WORKSPACE"
echo ""

case "$TYPE" in
  pypi)
    echo "📦 Installing $NAME..."
    pip install "$NAME==$VERSION" --target "$WORKSPACE/pkg" -q 2>/dev/null || pip install "$NAME" --target "$WORKSPACE/pkg" -q
    echo ""

    echo "🔍 Security: pip-audit..."
    pip-audit 2>&1 | head -30 || true
    echo ""

    echo "🔍 Security: bandit..."
    PKGDIR=$(echo "$NAME" | tr '-' '_')
    bandit -r "$WORKSPACE/pkg/$PKGDIR/" -f json --severity-level medium 2>/dev/null | python3 -c "
import json,sys
try:
    data=json.load(sys.stdin)
    results=data.get('results',[])
    print(f'  Issues found: {len(results)}')
    for r in results[:5]:
        print(f'  - [{r[\"issue_severity\"]}] {r[\"issue_text\"]} ({r[\"filename\"].split(\"/\")[-1]}:{r[\"line_number\"]})')
except: print('  No issues or parse error')
" || echo "  bandit scan done"
    echo ""

    echo "🔍 Security: safety..."
    safety check 2>&1 | head -20 || true
    echo ""

    echo "🔍 Quality: ruff..."
    ruff check "$WORKSPACE/pkg/$PKGDIR/" 2>&1 | tail -10 || echo "  ruff check done"
    echo ""

    echo "🔍 OWASP: injection patterns..."
    grep -rn --include='*.py' -E '(exec\(|eval\(|os\.system|subprocess\.call)' "$WORKSPACE/pkg/$PKGDIR/" 2>/dev/null | head -10 || echo "  No injection patterns found"
    echo ""

    echo "🔍 OWASP: hardcoded secrets..."
    grep -rn --include='*.py' -E '(AKIA[0-9A-Z]{16}|password\s*=\s*["\x27][^"]+["\x27])' "$WORKSPACE/pkg/$PKGDIR/" 2>/dev/null | head -10 || echo "  No secrets found"
    ;;

  npm)
    echo "📦 Installing $NAME..."
    mkdir -p "$WORKSPACE/pkg" && cd "$WORKSPACE/pkg"
    npm init -y > /dev/null 2>&1
    npm install "$NAME@$VERSION" --save 2>&1 | tail -5
    echo ""

    echo "🔍 Security: npm audit..."
    npm audit 2>&1 | tail -20 || true
    echo ""

    echo "🔍 Dependency tree..."
    npm ls --all 2>&1 | head -30
    echo ""

    echo "🔍 Install scripts check..."
    PKGNAME=$(echo "$NAME" | sed 's/@.*\///')
    cat "node_modules/$PKGNAME/package.json" 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)
scripts=d.get('scripts',{})
danger=[k for k in ['preinstall','postinstall','install'] if k in scripts]
if danger:
    print(f'  ⚠️  DANGEROUS INSTALL SCRIPTS: {danger}')
    for k in danger: print(f'    {k}: {scripts[k]}')
else:
    print('  ✅ No install scripts')
" 2>/dev/null || echo "  Check done"
    ;;

  mvn|maven)
    echo "📦 Resolving $NAME:$VERSION..."
    mkdir -p "$WORKSPACE/mvn" && cd "$WORKSPACE/mvn"

    IFS=':' read -r GROUP_ID ARTIFACT_ID <<< "$NAME"
    cat > pom.xml << EOF
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.scan</groupId>
  <artifactId>dep-scan</artifactId>
  <version>1.0</version>
  <dependencies>
    <dependency>
      <groupId>$GROUP_ID</groupId>
      <artifactId>$ARTIFACT_ID</artifactId>
      <version>$VERSION</version>
    </dependency>
  </dependencies>
</project>
EOF

    echo "🔍 Dependency tree..."
    mvn dependency:tree 2>&1 | grep -E '\[INFO\].*:.*:' | head -30 || true
    echo ""

    echo "🔍 OWASP dependency-check..."
    mvn org.owasp:dependency-check-maven:check 2>&1 | grep -E '(CVE|vulnerability|CRITICAL|HIGH)' | head -20 || echo "  OWASP check done"
    echo ""

    echo "🔍 NVD CVE lookup..."
    python3 -c "
import urllib.request, json
try:
    url = 'https://services.nvd.nist.gov/rest/json/cves/2.0?keywordSearch=$ARTIFACT_ID&resultsPerPage=5'
    resp = urllib.request.urlopen(url, timeout=10)
    data = json.loads(resp.read())
    cves = data.get('vulnerabilities', [])
    print(f'  Found {len(cves)} CVEs for $ARTIFACT_ID:')
    for cve in cves[:5]:
        c = cve.get('cve', {})
        sev = 'UNKNOWN'
        metrics = c.get('metrics', {})
        if metrics.get('cvssMetricV31'):
            sev = metrics['cvssMetricV31'][0].get('cvssData', {}).get('baseSeverity', 'UNKNOWN')
        desc = c.get('descriptions', [{}])[0].get('value', '')[:80]
        print(f'  - {c.get(\"id\")} [{sev}] {desc}')
except Exception as e:
    print(f'  NVD lookup failed: {e}')
" || true
    ;;

  git)
    echo "📦 Cloning $NAME..."
    git clone --depth 1 --branch "$VERSION" "$NAME" "$WORKSPACE/repo" 2>&1 | tail -3
    cd "$WORKSPACE/repo"
    echo ""

    echo "🔍 Security: bandit..."
    bandit -r . -f json --severity-level medium 2>/dev/null | python3 -c "
import json,sys
try:
    data=json.load(sys.stdin)
    results=data.get('results',[])
    print(f'  Issues found: {len(results)}')
    for r in results[:10]:
        print(f'  - [{r[\"issue_severity\"]}] {r[\"issue_text\"]} ({r[\"filename\"].split(\"/\")[-1]}:{r[\"line_number\"]})')
except: print('  No issues')
" || echo "  bandit done"
    echo ""

    echo "🔍 Quality: ruff..."
    ruff check . 2>&1 | tail -10 || echo "  ruff done"
    echo ""

    echo "🔍 Secrets scan..."
    grep -rn --include='*.py' --include='*.js' --include='*.env' -E '(AKIA|password|secret|api_key|token)' . 2>/dev/null | head -10 || echo "  No secrets found"
    ;;

  *)
    echo "❌ Unknown type: $TYPE"
    echo "Usage: ./scripts/scan-local.sh [pypi|npm|mvn|git] <name> <version>"
    exit 1
    ;;
esac

echo ""
echo "============================================"
echo "✅ Scan complete!"
echo "============================================"
echo ""
echo "Workspace: $WORKSPACE"
echo "Clean up: rm -rf $WORKSPACE"
