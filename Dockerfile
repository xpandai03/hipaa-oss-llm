# Minimal Ubuntu base for HIPAA-compliant Ollama deployment
FROM ubuntu:22.04

# System dependencies - minimal installation
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# Create models directory for encrypted volume mount
RUN mkdir -p /models

# Environment configuration
ENV OLLAMA_MODELS=/models
ENV OLLAMA_HOST=0.0.0.0:11434
ENV OLLAMA_KEEP_ALIVE=24h
ENV OLLAMA_NUM_PARALLEL=1
ENV OLLAMA_MAX_LOADED_MODELS=1

# Pre-pull the model at build time to avoid runtime downloads
# Using llama3.1:8b-instruct for good balance of performance and quality
RUN /bin/bash -c "ollama serve & \
    sleep 5 && \
    ollama pull llama3.1:8b-instruct && \
    sleep 2 && \
    pkill ollama || true"

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:11434/api/tags || exit 1

EXPOSE 11434

# Run Ollama server
CMD ["ollama", "serve"]