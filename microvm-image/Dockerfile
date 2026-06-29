# MicroVM Image for Code Review Sandbox
# This runs INSIDE the Lambda MicroVM — handles exec requests via HTTP

FROM python:3.11-slim

# Install system tools needed for code review
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Pre-install common security/quality tools
RUN pip install --no-cache-dir \
    bandit \
    safety \
    ruff \
    pytest \
    pip-audit

WORKDIR /app

# Copy the executor HTTP server
COPY server.py .

EXPOSE 8080

CMD ["python", "server.py"]
