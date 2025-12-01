FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y cron bash && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/plex-curator

COPY src/ ./src/
COPY tests/ ./tests/
COPY templates/ ./templates/
COPY themes/ ./themes/
COPY data/ ./data/

ENV PYTHONPATH=/opt/plex-curator/src:/opt/plex-curator

COPY requirements.txt /opt/plex-curator/

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000

CMD ["python3", "-m", "src.webui"]
