# ---- base image ----
FROM python:3.12-slim AS base

# Prevents Python from writing .pyc files & buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps (curl just for debug/health checks; remove if you want)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---- install deps ----
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- copy project ----
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Default envs (override at runtime)
ENV PORT=8000

# Start API
CMD ["uvicorn", "apps.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
