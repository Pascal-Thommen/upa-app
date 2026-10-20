# Production Dockerfile for FastAPI Backend (UPA App Campus Platform)
FROM python:3.12-slim

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create non-root system user and group for security
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# Install dependencies first for optimal Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY src ./src

# Set proper file permissions for non-root execution
RUN chown -R appuser:appuser /app

# Switch to unprivileged user
USER appuser

EXPOSE 8000

# Healthcheck validating liveness via Python standard library
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

# Start Uvicorn ASGI server
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
