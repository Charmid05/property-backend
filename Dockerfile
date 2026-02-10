FROM python:3.13.3-slim-bookworm as builder

WORKDIR /app

COPY requirements.txt .
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y \
    build-essential \
    libcurl4-openssl-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN uv pip install -r requirements.txt --system
# RUN uv pip install pycurl

FROM python:3.13.3-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy only application files (not everything)
COPY manage.py .
COPY a_core/ ./a_core/
# Add other specific directories you need

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]