# Plex Curator with Web UI

AI-powered movie collection and TV channel curator for Plex with a web interface for easy management.

## Features

- 🎨 **Web UI** - Manage movie curations and TV channels through a web interface (Movies and TV Channels tabs)
- 🤖 **AI Curation** - Uses local AI (Ollama) to intelligently select movies and shows
- 📺 **TV Channels** - Weekly-regenerated episode playlists ("channels") with show rotation, no back-to-back episodes of the same series (multi-part episodes stay together), and per-channel memory so lineups change every week
- ⏰ **In-App Scheduler** - Jobs run on cron expressions inside the app itself (no container cron); last-run status and next-run times are shown in the UI
- 🎯 **TMDB Integration** - Movie metadata plus TV ratings/popularity to inform show selection (degrades gracefully without a key)
- ⚡ **Performance Optimized** - Parallel TMDB requests, caching, modular design
- 📊 **Keyword Fallback** - Falls back to keyword matching when AI suggestions don't match

## Project Structure

```
plex-curator/
├── src/
│   ├── config.py              # Configuration
│   ├── curator.py             # Movie curation engine
│   ├── channels.py            # TV channel engine
│   ├── scheduler.py           # In-app job scheduler (replaces cron)
│   ├── webui.py               # Flask web interface
│   ├── halloween_tv.py        # Standalone Halloween TV script
│   ├── core/
│   │   ├── ai.py              # AI integration (movies + shows)
│   │   ├── tmdb.py            # TMDB API (movies + TV enrichment)
│   │   ├── plex.py            # Plex movie library + collections
│   │   ├── tv.py              # Plex TV library + playlists
│   │   ├── blocks.py          # Episode block assembly (pure logic)
│   │   ├── history.py         # Channel rotation memory
│   │   └── utils.py           # Utilities
├── templates/                 # Flask HTML templates
├── themes/                    # Movie curation YAMLs
├── channels/                  # TV channel YAMLs
├── data/                      # State: schedules, job status, channel history
├── tests/                     # Offline unit tests (no Plex/TMDB needed)
├── Dockerfile
└── docker-compose.yml
```

## Quick Start

### 1. Prerequisites

- Docker & Docker Compose
- Plex Media Server
- Ollama running with a model (default `qwen3:8b`, override with `AI_MODEL`)
- TMDB API key (optional for TV channels, required for movie curation)

### 2. Setup

Create `data/.env`:
```env
PLEX_URL=http://your-plex-ip:32400
PLEX_TOKEN=your-plex-token
TMDB_KEY=your-tmdb-api-key
AI_API_URL=http://your-ollama-ip:11434/api/generate
# Optional:
TZ=America/New_York          # timezone for cron schedules (default UTC!)
WEB_PASSWORD=change-me       # enables HTTP basic auth (user: admin)
WEBHOOK_URL=https://ntfy.sh/your-topic   # POST on job failure
WEBHOOK_EVENTS=failed        # or: success, all
```

### 3. Deploy

```bash
# Build and start
docker-compose up -d --build

# Check logs
docker logs -f plex-curator

# Access Web UI (port 8088)
# Local:  http://localhost:8088
# Remote: ssh -L 8088:localhost:8088 user@server, then open http://localhost:8088
```

## TV Channels

A channel is a themed playlist of episodes (a 4–6 hour "block") rebuilt on a weekly schedule. Four templates ship in `channels/`:

| Channel | Playlist | Default schedule |
|---------|----------|------------------|
| `saturday_morning_cartoons` | Saturday Morning Cartoons | Sat 05:00 |
| `tv_drama` | TV Drama Channel | Sun 02:00 |
| `comedy_sitcoms` | Comedy & Sitcoms | Fri 03:00 |
| `history_documentary` | History & Documentaries | Mon 04:00 |
| `halloween_specials` | Halloween TV Specials | Oct 1, 06:00 (yearly) |

How a channel run works:

1. Shows are collected from your Plex TV libraries and pre-filtered by the channel's genre hints.
2. TMDB TV ratings/popularity are attached (skipped if no key).
3. The AI picks the shows that best fit the channel's theme prompt (picks not in your library are dropped).
4. Rotation history selects this week's lineup, preferring shows not used last week and least-recently used.
5. Episodes are interleaved round-robin: no series plays back-to-back, except multi-part episodes ("Part 1"/"Part 2", "(1)"/"(2)"), which always play together in order.
6. Each show resumes where it left off last time (per-channel cursors in `data/channel_history.json`), and recently played episodes are skipped until a show wraps around.
7. The Plex playlist is replaced; history is only advanced after the playlist is created successfully.

Channel YAML format (`channels/<name>.yaml`):

```yaml
channel_name: Saturday Morning Cartoons
playlist_name: "Saturday Morning Cartoons"
prompt: |
  Classic and modern animated series fitting a nostalgic
  Saturday-morning cartoon block...
target_hours: 4        # keep adding episodes until this length
max_hours: 5           # never exceed this
shows_per_block: 6     # how many series to interleave
genre_hints: [Animation, Children, Family]
default_schedule: "0 5 * * 6"   # cron, used to seed the scheduler
# library_section: "TV Shows"   # optional: limit to one Plex section
# prefer_unwatched: true        # deprioritize already-watched episodes
# episode_keywords: [halloween, spooky]  # boost matching episode titles
# episode_level_ai: false       # also let the AI pick specific episodes
```

Use the **Preview** button on the TV tab for a dry run: the proposed lineup
is written to the job log without creating the playlist or advancing
rotation history.

## Scheduling

Scheduling runs **inside the app** — a background thread checks `data/schedules.json` every 30 seconds and fires due jobs. No cron daemon, no `/etc/cron.d`, nothing lost on container restart. Occurrences missed while the container was down are skipped (same behavior as cron).

Job ids:

- `movie:monthly` — built-in: runs the theme matching the current month (october.yaml in October) on `0 0 1 * *`
- `movie:<name>` — a specific theme YAML on its own schedule
- `channel:<name>` — a TV channel (seeded automatically from each channel's `default_schedule`)

Edit schedules on the dashboard (Movies tab) or per-channel in the channel editor. Last run, status, and next run are shown in the UI; **click any status badge to open that job's full log** (`data/logs/<job>.log` — jobs run as subprocesses with all output captured) along with its last 20 runs. `GET /status` returns everything as JSON. On first start, any old `data/cron_schedule.json` is migrated automatically.

**Timezone:** schedules are evaluated in the container's timezone, which defaults to UTC — set `TZ=` in `data/.env` so "Saturday 5am" means your 5am.

## Running Things Manually

- **Web UI**: "Run Now" on any curation or channel (recommended)
- **CLI**:
```bash
# Movie curation by name
docker exec plex-curator python3 /opt/plex-curator/src/curator.py october

# TV channel by name
docker exec plex-curator python3 /opt/plex-curator/src/channels.py saturday_morning_cartoons
```

## Creating a Movie Curation

1. Click **"+ New Curation"** on the Movies tab
2. Fill in the form:
   - **File Name**: `october`, `christmas`, `action-classics`, etc.
   - **Collection Name**: How it appears in Plex (e.g., "Spooky October")
   - **Keywords**: Comma-separated (e.g., "Horror, Thriller, Mystery")
   - **Min Rating**: Filter movies below this rating (0-10)
   - **Use AI**: Toggle AI curation on/off, with a prompt
3. Click **"Save Curation"**

### Example: October Horror Collection

```yaml
File Name: october
Collection Name: Spooky October
Keywords: Horror, Thriller, Supernatural, Mystery, Gothic, Suspense, Halloween
Min Rating: 6.0
Use AI: ✓
AI Prompt: |
  You are an AI Plex curator. Select titles suitable for Halloween:
  - spooky, supernatural, mysterious, or horror themes
  - prioritize pre-2000 classics
  - include highly rated or cult favorites
  - range from family-friendly to genuinely scary
```

### Cron patterns

| Pattern | Description | When |
|---------|-------------|------|
| `0 0 1 * *` | Monthly | 1st of month at midnight |
| `0 5 * * 6` | Weekly | Every Saturday at 5 AM |
| `0 0 * * *` | Daily | Every day at midnight |

### TMDB Source Filters (Discover)

By default the candidate pool comes from TMDB keyword search. Set `tmdb_discover` in a theme YAML (or use the "TMDB Source Filters" section of the edit form) to pull a structured pool instead:

```yaml
tmdb_discover:
  origin_country: CA          # films made in a country
  language: fr                # original language
  genres: [War, History]      # any-of genre names (mapped to TMDB ids)
  year_from: 1970
  year_to: 1999
  min_votes: 100
  # any raw TMDB Discover key also passes through, e.g. with_runtime.gte: 90
```

Combine with `requirements:` (hard rules verified per-movie by the AI after Plex matching) for themes with strict criteria — e.g. July's "Oh Canada!" uses `origin_country: CA` plus a Canadian-connection requirement.

## How Movie Curation Works

1. **Keyword Generation**: Extract or generate keywords from collection name
2. **TMDB Search**: Search TMDB with keywords (backup pool)
3. **AI Suggestions**: Ask AI to suggest movies for the theme
4. **TMDB Lookup**: Search TMDB for each AI suggestion (parallel)
5. **Plex Matching**: Match TMDB results to your Plex library
6. **Collection Creation**: Create collection in Plex, promote to home

## Tests

The channel logic (block assembly, multi-part detection, rotation memory, scheduler math) is pure and runs offline:

```bash
PYTHONPATH=src python3 tests/blocks_test.py
PYTHONPATH=src python3 tests/rotation_test.py
PYTHONPATH=src python3 tests/scheduler_test.py
```

## Troubleshooting

### Web UI not accessible
```bash
docker ps | grep plex-curator
docker port plex-curator        # should show 8088
docker logs plex-curator
```

### Scheduled jobs not running
- Click the status badge on the dashboard — it opens the job's captured log and run history
- `curl http://localhost:8088/status` for raw job state

### Curation not finding movies
- Check minimum rating isn't too high
- Verify keywords are relevant
- Ensure movies exist in your Plex library

### AI not working
- Verify Ollama is running: `curl http://ollama-ip:11434/api/generate`
- Check AI_API_URL in `.env`
- Ensure the model is pulled (`AI_MODEL` env var, default `qwen3:8b`)

## API Endpoints

- `GET /` - Movies dashboard
- `GET /tv` - TV channels dashboard
- `GET|POST /curation/*` - Movie curation CRUD + run
- `GET|POST /channel/*` - TV channel CRUD + run
- `POST /channel/preview/<filename>` - Dry run a channel (no Plex writes)
- `GET /job/log/<job_id>` - View a job's captured log + run history
- `POST /schedule/save` - Save schedules (job-id keyed)
- `GET /status` - Job status JSON

## License

MIT License – See [LICENSE](LICENSE) file for details.
