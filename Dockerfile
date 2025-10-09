FROM python:3.11-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    cron \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/plex-curator

# Copy application files
COPY . .

# Python
RUN pip install --no-cache-dir \
    plexapi \
    tmdbsimple \
    requests \
    pyyaml

# Make scripts executable
RUN chmod +x /opt/plex-curator/plex-curator.py

# Default command (will be overridden by docker-compose)
CMD ["python3", "/opt/plex-curator/plex-curator.py"]