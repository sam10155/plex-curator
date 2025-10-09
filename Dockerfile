FROM python:3.11-slim

WORKDIR /opt/plex-curator
COPY . .

RUN pip install --no-cache-dir plexapi tmdbsimple requests pyyaml schedule

CMD ["python3", "/opt/plex-curator/plex-curator.py"]
