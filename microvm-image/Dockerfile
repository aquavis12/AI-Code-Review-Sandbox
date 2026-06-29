# MicroVM Image for Code Review Sandbox
# Supports: PyPI, npm, Maven, and Git repo scanning

FROM python:3.11-slim

# Install system tools + Node.js + Maven/JDK
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    jq \
    nodejs \
    npm \
    default-jdk-headless \
    maven \
    && rm -rf /var/lib/apt/lists/*

# Pre-install Python security/quality tools
RUN pip install --no-cache-dir \
    bandit \
    safety \
    ruff \
    pytest \
    pip-audit \
    pipdeptree

# Create workspace
RUN mkdir -p /workspace

WORKDIR /app

# Copy the executor HTTP server
COPY server.py .

EXPOSE 8080

CMD ["python", "server.py"]
