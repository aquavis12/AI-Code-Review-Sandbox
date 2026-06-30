# ADR-001: Context Skills for AI-Aware Security Scanning

**Status:** Accepted**Date:** 2026-06-30**Author:** Vishnu Rachapudi

---

## Context

The AI reviewer (Bedrock Kimi K2.5) analyzes raw scan output from security tools (bandit, pip-audit, npm audit, OWASP dependency-check). Without ecosystem-specific knowledge, the model produces generic recommendations and misses package-specific threat patterns.

For example:

- Scanning `log4j-core` without knowing Log4Shell history leads to incomplete risk assessment
- Scanning a PyPI package without awareness of typosquatting patterns misses supply chain signals
- Generic prompts don't account for ecosystem-specific attack vectors (npm install hooks vs. Python setup.py)

## Decision

Introduce **Context Skills** — a layered knowledge injection system that gives the AI reviewer awareness of what's being scanned before it analyzes results.

### Architecture

```
┌──────────────────────────────────────────────────┐
│                 Context Skills                     │
│                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────┐│
│  │ Ecosystem   │  │ Package     │  │ Custom   ││
│  │ Skills      │  │ Intelligence│  │ (.md)    ││
│  │ (built-in)  │  │ (built-in)  │  │ (user)   ││
│  └──────┬──────┘  └──────┬──────┘  └────┬─────┘│
│         └────────────┬───────────────────┘       │
│                      v                           │
│         ┌────────────────────────┐               │
│         │ Merged Context Prompt  │               │
│         └───────────┬────────────┘               │
└─────────────────────┼────────────────────────────┘
                      v
            ┌───────────────────┐
            │ Bedrock Kimi K2.5 │
            │ (AI Analysis)     │
            └───────────────────┘

```

### Skill Types

| Type | Source | Example |
| --- | --- | --- |
| **Ecosystem Skills** | Built-in (code) | PyPI attack vectors, npm install hook patterns, Maven deserialization risks |
| **Package Intelligence** | Built-in (code) | "log4j-core < 2.17.1 = Log4Shell RCE", "requests — check urllib3 transitive CVEs" |
| **Custom Skills** | User-uploaded .md | Organization-specific rules, internal package context, compliance requirements |

### Custom Skill Upload

Users upload `.md` files via `POST /skills`:

```json
{
  "name": "pypi",
  "content": "## Internal PyPI Rules\n\n- All packages must be from our approved vendor list..."
}

```

Naming convention:

- `global.md` — applies to all scans
- `{ecosystem}.md` — applies to all scans of that type (e.g. `pypi.md`)
- `{package_name}.md` — applies only when scanning that specific package

Load order: `global.md` → `{ecosystem}.md` → `{package}.md` (all concatenated)

### Storage

Custom skills stored in S3 (`context_skills/` prefix) and synced to Lambda `/tmp/` for low-latency reads during scan execution.

## Consequences

### Positive

- AI reviewer produces significantly more specific, actionable findings
- Users can inject domain knowledge (internal compliance rules, known-good packages, org-specific patterns)
- Extensible without code changes — just upload a new `.md` file
- Built-in skills cover 90% of common scanning scenarios out of the box

### Negative

- Larger prompt = more tokens = slightly higher Bedrock cost (~$0.001 more per scan)
- Custom skills must be maintained by users — stale context could produce incorrect recommendations
- Cold starts: first scan after upload may not pick up custom skill until /tmp is populated

### Risks

- Prompt injection via malicious skill content (mitigated: skills only provide context, not instructions)
- Token limit: if all skills combined exceed model context, truncation needed (mitigated: 256K context on Kimi K2.5 is very large)

## Alternatives Considered

| Alternative | Why Rejected |
| --- | --- |
| Fine-tune a model per ecosystem | Expensive, slow to update, overkill for this use case |
| RAG with vector DB | Over-engineered for ~4 ecosystem categories and ~20 known packages |
| Hardcode everything in the prompt | Not extensible, no user customization |
| No context at all | Generic results, misses ecosystem-specific threats |

## Related

- `src/orchestrator/context_skills.py` — implementation
- `src/orchestrator/reviewer.py` — consumer (injects context before Bedrock call)
- `POST /skills` — upload endpoint
- `GET /skills` — list endpoint

