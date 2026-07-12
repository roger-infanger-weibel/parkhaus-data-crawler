# Use lightweight Python base image
FROM python:3.11-slim

# Install minimal dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Environment
ENV PYTHONUNBUFFERED=1

# Expose HTTP port
EXPOSE 80

# Run scheduler in background and web server in foreground
CMD ["/bin/bash", "-c", "python -u scheduler.py & python -u web_server.py"]