FROM python:3.12-slim

WORKDIR /app

# Install ffmpeg for audio processing (required by pydub)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create directories for data and normalized cache
RUN mkdir -p /app/data /app/normalized

# Expose port
EXPOSE 5000

# Use gunicorn for production
RUN pip install --no-cache-dir gunicorn

# Run with gunicorn (4 workers, adjust based on CPU cores)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]
