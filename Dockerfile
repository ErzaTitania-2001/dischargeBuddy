# Production Dockerfile for Google Cloud Run
FROM python:3.12-slim

# Set working directory & environment variables
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Generate sample PDF if not already present
RUN python scripts/generate_sample_pdf.py

# Create non-root user for security
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser:appuser /app
USER appuser

# Expose standard Cloud Run port
EXPOSE 8080

# Run uvicorn server binding to 0.0.0.0 and Cloud Run's dynamic $PORT
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
