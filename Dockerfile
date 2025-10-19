FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    cron \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/plex-curator

COPY config.py .
COPY curator.py .
COPY halloween_tv.py .
COPY core/ ./core/

RUN pip install --no-cache-dir \
    plexapi \
    tmdbsimple \
    requests \
    pyyaml

RUN chmod +x /opt/plex-curator/curator.py
RUN chmod +x /opt/plex-curator/halloween_tv.py

CMD ["python3", "/opt/plex-curator/curator.py"]