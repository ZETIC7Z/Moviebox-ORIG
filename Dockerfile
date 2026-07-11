FROM python:3.10-slim

WORKDIR /app

# Install dependencies with cache optimization
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose API port
EXPOSE 8000

# Health check so orchestrators know when the server is ready
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request, os; port = os.environ.get('PORT', '8000'); urllib.request.urlopen(f'http://localhost:{port}/').read()" || exit 1

# Run with dynamic port binding for cloud deployment compatibility (defaults to 8000)
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2 --timeout-keep-alive 75"]
