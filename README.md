# Plex Curator with Web UI

AI-powered movie collection curator for Plex with a web interface for easy management.

## Features

- 🎨 **Web UI** - Manage curations through a beautiful web interface
- 🤖 **AI Curation** - Uses local AI (Ollama) to intelligently select movies
- 📅 **Flexible Scheduling** - Configure cron schedules for automatic runs
- 🎯 **TMDB Integration** - Searches The Movie Database for movie metadata
- ⚡ **Performance Optimized** - Parallel TMDB requests, caching, modular design
- 📊 **Keyword Fallback** - Falls back to keyword matching when AI suggestions don't match

## Project Structure

```
plex-curator/
├── src/
│   ├── config.py              # Configuration
│   ├── curator.py             # Main curation engine
│   ├── webui.py               # Flask web interface
│   ├── halloween_tv.py        # TV episode curator
│   ├── core/
│   │   ├── __init__.py
│   │   ├── ai.py              # AI integration
│   │   ├── tmdb.py            # TMDB API
│   │   ├── plex.py            # Plex API
│   │   └── utils.py           # Utilities
├── templates/                 # Flask HTML templates
│   ├── base.html
│   ├── index.html
│   └── edit_curation.html
├── themes/                    # YAML curation files
├── data/                      # Cache, state, and cron schedules
├── Dockerfile
└── docker-compose.yml
```

## Quick Start

### 1. Prerequisites

- Docker & Docker Compose
- Plex Media Server
- Ollama running with a model (e.g., `mistral:instruct`)
- TMDB API key

### 2. Setup

Create `data/.env`:
```env
PLEX_URL=http://your-plex-ip:32400
PLEX_TOKEN=your-plex-token
TMDB_KEY=your-tmdb-api-key
AI_API_URL=http://your-ollama-ip:11434/api/generate
```

### 3. Deploy

```bash
# Build and start
docker-compose up -d

# Check logs
docker logs -f plex-curator

# Access Web UI
# Open http://localhost:5000
```

## Using the Web UI

### Dashboard
- View all curations
- Run curations manually
- Configure cron schedules
- Edit or delete curations

### Creating a Curation

1. Click **"+ New Curation"**
2. Fill in the form:
   - **File Name**: `october`, `christmas`, `action-classics`, etc.
   - **Collection Name**: How it appears in Plex (e.g., "Spooky October")
   - **Keywords**: Comma-separated (e.g., "Horror, Thriller, Mystery")
   - **Min Rating**: Filter movies below this rating (0-10)
   - **Use AI**: Toggle AI curation on/off
   - **AI Prompt**: Instructions for AI (if enabled)
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

### Scheduling Curations

On the dashboard, configure cron schedules:

| Pattern | Description | When |
|---------|-------------|------|
| `0 0 1 * *` | Monthly | 1st of month at midnight |
| `0 0 * * 0` | Weekly | Every Sunday at midnight |
| `0 0 * * *` | Daily | Every day at midnight |
| `0 2 15 * *` | Mid-month | 15th at 2 AM |

## Running Curations

You have multiple ways to run curations:

### 1. Web UI (Recommended)
- Click **"Run Now"** button on any curation in the dashboard
- Runs immediately, shows result

### 2. Monthly Auto-Run
```bash
# Automatically runs on 1st of each month
# Runs the YAML matching current month (october.yaml in October)
docker exec plex-curator python3 /opt/plex-curator/monthly.py

# Force specific month
docker exec plex-curator python3 /opt/plex-curator/monthly.py december
```

### 3. Specific Curation
```bash
# Run any curation by name
docker exec plex-curator python3 /opt/plex-curator/curator.py october
docker exec plex-curator python3 /opt/plex-curator/curator.py action-classics
docker exec plex-curator python3 /opt/plex-curator/curator.py family-friendly
```

### 4. All Scheduled Curations
```bash
# Run all curations that have schedules enabled in Web UI
docker exec plex-curator python3 /opt/plex-curator/curator.py
```

### 5. Halloween TV Episodes
```bash
# Special: Create playlist of Halloween TV episodes
docker exec plex-curator python3 /opt/plex-curator/halloween_tv.py
```

## Default Cron Jobs

The system sets up these automatic runs:

| Schedule | Command | Description |
|----------|---------|-------------|
| `0 0 1 * *` | `monthly.py` | Run current month's curation on 1st |
| Custom | From Web UI | Individual curation schedules |

Configure additional schedules in the Web UI!

## Configuration Options

Edit `config.py` to customize:

```python
MAX_TMBD_CANDIDATES = 1000      # Max TMDB search results
MAX_AI_SELECTION = 40            # Max AI suggestions
MAX_COLLECTION_ITEMS = 15        # Movies per collection
TMDB_PARALLEL_REQUESTS = 10      # Concurrent TMDB requests
```

## How It Works

1. **Keyword Generation**: Extract or generate keywords from collection name
2. **TMDB Search**: Search TMDB with keywords (backup pool)
3. **AI Suggestions**: Ask AI to suggest movies for the theme
4. **TMDB Lookup**: Search TMDB for each AI suggestion (parallel)
5. **Plex Matching**: Match TMDB results to your Plex library
6. **Collection Creation**: Create collection in Plex, promote to home

## Troubleshooting

### Web UI not accessible
```bash
# Check if container is running
docker ps | grep plex-curator

# Check port mapping
docker port plex-curator

# View logs
docker logs plex-curator
```

### Curation not finding movies
- Check minimum rating isn't too high
- Verify keywords are relevant
- Ensure movies exist in your Plex library
- Try broader AI prompts

### AI not working
- Verify Ollama is running: `curl http://ollama-ip:11434/api/generate`
- Check AI_API_URL in `.env`
- Ensure model is pulled: `ollama pull mistral:instruct`

## Tips for Better Results

1. **Use specific keywords**: "Sci-Fi, Space Opera, Dystopian" vs "Movies"
2. **Adjust minimum rating**: Lower for niche genres, higher for quality
3. **Balance AI with keywords**: AI finds classics, keywords find variety
4. **Test prompts**: Use "Run Now" to test before scheduling
5. **Add keywords to YAML**: Skips AI keyword generation (faster)

## Monthly Theme Examples

**January - New Year Fresh Starts**
```yaml
Keywords: Drama, Inspiration, Self-improvement, Sports
AI Prompt: Select inspirational movies about new beginnings, personal growth, and achieving goals
```

**December - Holiday Classics**
```yaml
Keywords: Christmas, Holiday, Family, Winter, Comedy
AI Prompt: Select classic Christmas and holiday movies, both heartwarming and fun
```

**July - Action & Explosions**
```yaml
Keywords: Action, Thriller, Adventure, Military, Espionage
AI Prompt: Select high-octane action movies with explosions, car chases, and heroics
```

## API Endpoints

The Web UI exposes these endpoints:

- `GET /` - Dashboard
- `GET /curation/new` - Create new curation
- `GET /curation/edit/<filename>` - Edit curation
- `POST /curation/save` - Save curation
- `POST /curation/delete/<filename>` - Delete curation
- `POST /curation/run/<filename>` - Run curation manually
- `POST /schedule/save` - Save cron schedules

## Contributing

Feel free to extend the system:
- Add more AI models
- Integrate other metadata sources
- Create custom matching algorithms
- Build mobile app interface

## License

MIT License – See [LICENSE](LICENSE) file for details.
