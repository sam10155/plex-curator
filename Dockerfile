FROM python:3.11-slim

# Install cron and bash
RUN apt-get update && \
    apt-get install -y cron bash && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/plex-curator

# Copy sources and templates
COPY src/ ./src/
COPY templates/ ./templates/
COPY themes/ ./themes/
COPY data/ ./data/

ENV PYTHONPATH=/opt/plex-curator/src

RUN pip install --no-cache-dir \
    plexapi \
    tmdbsimple \
    requests \
    pyyaml \
    flask

EXPOSE 5000

CMD ["python3", "-m", "src.webui"]
