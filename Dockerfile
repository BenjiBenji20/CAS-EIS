# --- Stage 1: Build virtual environment with uv ---
FROM python:3.11-slim AS builder

# Install uv binary from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Copy project dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install 3rd-party dependencies (excluding root package build)
RUN uv sync --frozen --no-dev --no-install-project

# Copy source code and README required for setuptools package build
COPY README.md ./
COPY src/ ./src/

# Install root package into virtual environment
RUN uv sync --frozen --no-dev

# --- Stage 2: Final lightweight runtime image ---
FROM python:3.11-slim AS runner

WORKDIR /app

# Copy uv binary for execution inside runner stage
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy virtual environment from builder stage
COPY --from=builder /app/.venv /app/.venv

# Set environment paths and variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV PYTHONUNBUFFERED=1

# Copy application source code
COPY . /app

# Ensure entrypoint script is executable
RUN chmod +x /app/entrypoint.sh

# Expose FastAPI application port
EXPOSE 8000

# Set entrypoint to run migrations and start Uvicorn
ENTRYPOINT ["/app/entrypoint.sh"]
