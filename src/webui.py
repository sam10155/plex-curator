#!/usr/bin/env python3
from flask import (Flask, render_template, request, redirect, url_for, flash,
                   jsonify, abort, Response)
import hmac
import os
import re
import yaml
import config
import scheduler

app = Flask(__name__, template_folder=config.TEMPLATES_DIR)
# Use a stable secret key from env so sessions survive container restarts
app.secret_key = os.getenv("SECRET_KEY") or os.urandom(24)
# templates/ is bind-mounted — pick up edits without a restart
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Optional HTTP basic auth: set WEB_PASSWORD (and optionally WEB_USERNAME)
WEB_PASSWORD = os.getenv("WEB_PASSWORD")
WEB_USERNAME = os.getenv("WEB_USERNAME", "admin")


@app.before_request
def _require_auth():
    if not WEB_PASSWORD:
        return
    auth = request.authorization
    if (auth and auth.username == WEB_USERNAME
            and hmac.compare_digest(auth.password or "", WEB_PASSWORD)):
        return
    return Response("Authentication required", 401,
                    {"WWW-Authenticate": 'Basic realm="Plex Curator"'})


def _job_view(job_id, schedules, status):
    """Combine schedule + status for one job into a template-friendly dict."""
    entry = schedules.get(job_id, {})
    st = status.get(job_id, {})
    cron = entry.get('cron', '')
    return {
        'job_id': job_id,
        'cron': cron,
        'cron_text': scheduler.describe_cron(cron) if cron else '',
        'enabled': entry.get('enabled', False),
        'description': entry.get('description', ''),
        'last_run': st.get('last_run'),
        'last_status': st.get('last_status'),
        'last_error': st.get('last_error'),
        'next_run': scheduler.next_run(cron) if entry.get('enabled') and cron else None,
    }


# ---------------------------------------------------------
# Movies (collections)
# ---------------------------------------------------------
def get_all_curations():
    curations = []
    if os.path.exists(config.THEMES_DIR):
        for filename in os.listdir(config.THEMES_DIR):
            if filename.endswith('.yaml'):
                filepath = os.path.join(config.THEMES_DIR, filename)
                with open(filepath, 'r') as f:
                    data = yaml.safe_load(f) or {}
                curations.append({
                    'filename': filename,
                    'name': filename[:-5],
                    'collection_name': data.get('playlist_name', 'N/A'),
                    'keywords': data.get('keywords', []),
                    'min_rating': data.get('filters', {}).get('min_rating', 0),
                    'max_items': data.get('max_items', config.DEFAULT_COLLECTION_SIZE),
                    'has_prompt': bool(data.get('prompt', '').strip())
                })
    return sorted(curations, key=lambda x: x['name'])


@app.route('/')
def index():
    curations = get_all_curations()
    schedules = scheduler.load_schedules()
    status = scheduler.get_status()
    for c in curations:
        c['job'] = _job_view(f"movie:{c['name']}", schedules, status)
    monthly_job = _job_view('movie:monthly', schedules, status)
    return render_template('index.html', curations=curations, monthly_job=monthly_job)


@app.route('/curation/new')
def new_curation():
    return render_template('edit_curation.html', curation=None)


@app.route('/curation/edit/<filename>')
def edit_curation(filename):
    filename = os.path.basename(filename)
    filepath = os.path.join(config.THEMES_DIR, filename)
    if not os.path.exists(filepath):
        flash('Curation not found', 'error')
        return redirect(url_for('index'))

    with open(filepath, 'r') as f:
        data = yaml.safe_load(f) or {}

    name = filename[:-5]
    job = scheduler.load_schedules().get(f"movie:{name}", {})
    discover = data.get('tmdb_discover') or {}
    genres = discover.get('genres', [])
    curation = {
        'filename': filename,
        'name': name,
        'collection_name': data.get('playlist_name', ''),
        'keywords': ', '.join(data.get('keywords', [])),
        'prompt': data.get('prompt', ''),
        'min_rating': data.get('filters', {}).get('min_rating', 6.0),
        'max_items': data.get('max_items', config.DEFAULT_COLLECTION_SIZE),
        'use_ai': bool(data.get('prompt', '').strip()),
        'requirements': data.get('requirements', ''),
        'promote_to_home': data.get('promote_to_home', True),
        'library_section': data.get('library_section', ''),
        'origin_country': discover.get('origin_country', discover.get('with_origin_country', '')),
        'tmdb_language': discover.get('language', ''),
        'tmdb_genres': ', '.join(genres) if isinstance(genres, list) else genres,
        'tmdb_year_from': discover.get('year_from', ''),
        'tmdb_year_to': discover.get('year_to', ''),
        'schedule_cron': job.get('cron', '0 0 1 * *'),
        'schedule_enabled': job.get('enabled', False),
    }

    return render_template('edit_curation.html', curation=curation)


@app.route('/curation/save', methods=['POST'])
def save_curation():
    name = request.form.get('name', '').strip()
    collection_name = request.form.get('collection_name', '').strip()
    keywords_str = request.form.get('keywords', '').strip()
    prompt = request.form.get('prompt', '').strip()
    min_rating = float(request.form.get('min_rating', 6.0))
    max_items = int(request.form.get('max_items', config.DEFAULT_COLLECTION_SIZE))
    use_ai = request.form.get('use_ai') == 'on'
    requirements = request.form.get('requirements', '').strip()
    promote_to_home = request.form.get('promote_to_home') == 'on'
    library_section = request.form.get('library_section', '').strip()
    origin_country = request.form.get('origin_country', '').strip().upper()
    tmdb_language = request.form.get('tmdb_language', '').strip().lower()
    tmdb_genres = [g.strip() for g in request.form.get('tmdb_genres', '').split(',') if g.strip()]
    tmdb_year_from = request.form.get('tmdb_year_from', '').strip()
    tmdb_year_to = request.form.get('tmdb_year_to', '').strip()
    schedule_cron = request.form.get('schedule_cron', '').strip() or '0 0 1 * *'
    schedule_enabled = request.form.get('schedule_enabled') == 'on'

    if not name or not collection_name:
        flash('Name and Collection Name are required', 'error')
        filename = f"{name}.yaml" if name else None
        if filename and os.path.exists(os.path.join(config.THEMES_DIR, filename)):
            return redirect(url_for('edit_curation', filename=filename))
        return redirect(url_for('new_curation'))

    keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]

    data = {
        'playlist_name': collection_name,
        'max_items': max_items,
        'filters': {
            'min_rating': min_rating
        },
        'promote_to_home': promote_to_home,
    }
    if keywords:
        data['keywords'] = keywords
    if use_ai and prompt:
        data['prompt'] = prompt
    if requirements:
        data['requirements'] = requirements
    if library_section:
        data['library_section'] = library_section
    # Preserve hand-written Discover filters beyond the ones the form exposes
    existing_path = os.path.join(config.THEMES_DIR, os.path.basename(f"{name}.yaml"))
    existing_discover = {}
    if os.path.exists(existing_path):
        with open(existing_path, 'r') as f:
            existing_discover = (yaml.safe_load(f) or {}).get('tmdb_discover') or {}
    discover = {k: v for k, v in existing_discover.items()
                if k not in ('origin_country', 'with_origin_country', 'language',
                             'genres', 'year_from', 'year_to')}
    if origin_country:
        discover['origin_country'] = origin_country
    if tmdb_language:
        discover['language'] = tmdb_language
    if tmdb_genres:
        discover['genres'] = tmdb_genres
    if tmdb_year_from:
        discover['year_from'] = int(tmdb_year_from)
    if tmdb_year_to:
        discover['year_to'] = int(tmdb_year_to)
    if discover:
        data['tmdb_discover'] = discover

    filename = os.path.basename(f"{name}.yaml")
    filepath = os.path.join(config.THEMES_DIR, filename)

    with open(filepath, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    schedules = scheduler.load_schedules()
    schedules[f"movie:{name}"] = {
        'cron': schedule_cron,
        'enabled': schedule_enabled,
        'description': 'Movie curation',
    }
    scheduler.save_schedules(schedules)

    flash(f'Curation "{name}" saved successfully', 'success')
    return redirect(url_for('index'))


@app.route('/curation/delete/<filename>', methods=['POST'])
def delete_curation(filename):
    filename = os.path.basename(filename)
    filepath = os.path.join(config.THEMES_DIR, filename)
    if os.path.exists(filepath):
        os.remove(filepath)
        schedules = scheduler.load_schedules()
        schedules.pop(f"movie:{filename[:-5]}", None)
        scheduler.save_schedules(schedules)
        flash('Curation deleted', 'success')
    else:
        flash('Curation not found', 'error')
    return redirect(url_for('index'))


@app.route('/curation/run/<filename>', methods=['POST'])
def run_curation_now(filename):
    name = os.path.basename(filename).replace('.yaml', '')
    started, message = scheduler.run_job(f"movie:{name}")
    flash(message, 'success' if started else 'warning')
    return redirect(url_for('index'))


# ---------------------------------------------------------
# TV channels (playlists)
# ---------------------------------------------------------
def get_all_channels():
    channels = []
    if os.path.isdir(config.CHANNELS_DIR):
        for filename in sorted(os.listdir(config.CHANNELS_DIR)):
            if filename.endswith('.yaml'):
                filepath = os.path.join(config.CHANNELS_DIR, filename)
                with open(filepath, 'r') as f:
                    data = yaml.safe_load(f) or {}
                channels.append({
                    'filename': filename,
                    'name': filename[:-5],
                    'playlist_name': data.get('playlist_name', 'N/A'),
                    'target_hours': data.get('target_hours', config.DEFAULT_TARGET_HOURS),
                    'max_hours': data.get('max_hours', config.DEFAULT_MAX_HOURS),
                    'shows_per_block': data.get('shows_per_block', config.DEFAULT_SHOWS_PER_BLOCK),
                    'genre_hints': data.get('genre_hints', []),
                })
    return channels


@app.route('/tv')
def tv():
    channels = get_all_channels()
    schedules = scheduler.load_schedules()
    status = scheduler.get_status()
    for c in channels:
        c['job'] = _job_view(f"channel:{c['name']}", schedules, status)
    return render_template('tv.html', channels=channels)


@app.route('/channel/new')
def new_channel():
    return render_template('edit_channel.html', channel=None)


@app.route('/channel/edit/<filename>')
def edit_channel(filename):
    filename = os.path.basename(filename)
    filepath = os.path.join(config.CHANNELS_DIR, filename)
    if not os.path.exists(filepath):
        flash('Channel not found', 'error')
        return redirect(url_for('tv'))

    with open(filepath, 'r') as f:
        data = yaml.safe_load(f) or {}

    name = filename[:-5]
    job = scheduler.load_schedules().get(f"channel:{name}", {})
    channel = {
        'filename': filename,
        'name': name,
        'playlist_name': data.get('playlist_name', ''),
        'prompt': data.get('prompt', ''),
        'target_hours': data.get('target_hours', config.DEFAULT_TARGET_HOURS),
        'max_hours': data.get('max_hours', config.DEFAULT_MAX_HOURS),
        'shows_per_block': data.get('shows_per_block', config.DEFAULT_SHOWS_PER_BLOCK),
        'genre_hints': ', '.join(data.get('genre_hints', [])),
        'exclude_genres': ', '.join(data.get('exclude_genres', [])),
        'min_episodes': data.get('min_episodes', 0) or '',
        'exclude_single_season': data.get('exclude_single_season', False),
        'sequential': data.get('sequential', False),
        'episode_keywords': ', '.join(data.get('episode_keywords', [])),
        'prefer_unwatched': data.get('prefer_unwatched', True),
        'episode_level_ai': data.get('episode_level_ai', False),
        'schedule_cron': job.get('cron', data.get('default_schedule', '0 5 * * 6')),
        'schedule_enabled': job.get('enabled', True),
    }
    return render_template('edit_channel.html', channel=channel)


@app.route('/channel/save', methods=['POST'])
def save_channel():
    name = request.form.get('name', '').strip().lower().replace(' ', '_')
    playlist_name = request.form.get('playlist_name', '').strip()
    prompt = request.form.get('prompt', '').strip()
    schedule_cron = request.form.get('schedule_cron', '').strip() or '0 5 * * 6'
    schedule_enabled = request.form.get('schedule_enabled') == 'on'
    genre_hints = [g.strip() for g in request.form.get('genre_hints', '').split(',') if g.strip()]
    exclude_genres = [g.strip() for g in request.form.get('exclude_genres', '').split(',') if g.strip()]
    episode_keywords = [k.strip() for k in request.form.get('episode_keywords', '').split(',') if k.strip()]
    min_episodes = request.form.get('min_episodes', '').strip()

    if not name or not playlist_name:
        flash('Name and Playlist Name are required', 'error')
        return redirect(url_for('new_channel'))

    data = {
        'channel_name': playlist_name,
        'playlist_name': playlist_name,
        'prompt': prompt,
        'target_hours': float(request.form.get('target_hours', config.DEFAULT_TARGET_HOURS)),
        'max_hours': float(request.form.get('max_hours', config.DEFAULT_MAX_HOURS)),
        'shows_per_block': int(request.form.get('shows_per_block', config.DEFAULT_SHOWS_PER_BLOCK)),
        'genre_hints': genre_hints,
        'prefer_unwatched': request.form.get('prefer_unwatched') == 'on',
        'episode_level_ai': request.form.get('episode_level_ai') == 'on',
        'exclude_single_season': request.form.get('exclude_single_season') == 'on',
        'sequential': request.form.get('sequential') == 'on',
        'default_schedule': schedule_cron,
    }
    if exclude_genres:
        data['exclude_genres'] = exclude_genres
    if min_episodes:
        data['min_episodes'] = int(min_episodes)
    if episode_keywords:
        data['episode_keywords'] = episode_keywords

    os.makedirs(config.CHANNELS_DIR, exist_ok=True)
    filepath = os.path.join(config.CHANNELS_DIR, os.path.basename(f"{name}.yaml"))
    with open(filepath, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    schedules = scheduler.load_schedules()
    schedules[f"channel:{name}"] = {
        'cron': schedule_cron,
        'enabled': schedule_enabled,
        'description': 'Weekly channel refresh',
    }
    scheduler.save_schedules(schedules)

    flash(f'Channel "{name}" saved successfully', 'success')
    return redirect(url_for('tv'))


@app.route('/channel/delete/<filename>', methods=['POST'])
def delete_channel(filename):
    filename = os.path.basename(filename)
    filepath = os.path.join(config.CHANNELS_DIR, filename)
    if os.path.exists(filepath):
        os.remove(filepath)
        schedules = scheduler.load_schedules()
        schedules.pop(f"channel:{filename[:-5]}", None)
        scheduler.save_schedules(schedules)
        flash('Channel deleted', 'success')
    else:
        flash('Channel not found', 'error')
    return redirect(url_for('tv'))


@app.route('/channel/run/<filename>', methods=['POST'])
def run_channel_now(filename):
    name = os.path.basename(filename).replace('.yaml', '')
    started, message = scheduler.run_job(f"channel:{name}")
    flash(message, 'success' if started else 'warning')
    return redirect(url_for('tv'))


@app.route('/channel/preview/<filename>', methods=['POST'])
def preview_channel(filename):
    """Dry run: assembles and logs the block without touching Plex or
    advancing rotation history."""
    name = os.path.basename(filename).replace('.yaml', '')
    started, message = scheduler.run_job(f"preview:{name}")
    flash(message, 'success' if started else 'warning')
    return redirect(url_for('job_log', job_id=f"preview:{name}"))


# ---------------------------------------------------------
# Scheduling / status
# ---------------------------------------------------------
@app.route('/schedule/save', methods=['POST'])
def save_schedule():
    """Merge job-id-keyed entries into schedules.json. The in-app scheduler
    picks changes up on its next tick — no cron files involved."""
    data = request.json or {}
    schedules = scheduler.load_schedules()

    for job_id, entry in data.items():
        schedules[job_id] = {
            'cron': entry.get('cron', '').strip(),
            'enabled': bool(entry.get('enabled')),
            'description': entry.get('description', ''),
        }

    scheduler.save_schedules(schedules)
    return jsonify({'status': 'success'})


@app.route('/status')
def job_status():
    return jsonify(scheduler.get_status())


@app.route('/job/log/<path:job_id>')
def job_log(job_id):
    if not re.fullmatch(r'(movie|channel|preview):[A-Za-z0-9 _.-]+', job_id):
        abort(404)
    status = scheduler.get_status().get(job_id, {})
    content = scheduler.read_log(job_id)
    back_url = url_for('index') if job_id.startswith('movie:') else url_for('tv')
    return render_template('job_log.html', job_id=job_id, status=status,
                           content=content, back_url=back_url)


# Ensure directories exist on import
os.makedirs(config.DATA_DIR, exist_ok=True)
os.makedirs(config.THEMES_DIR, exist_ok=True)
os.makedirs(config.CHANNELS_DIR, exist_ok=True)

if __name__ == '__main__':
    debug = os.getenv('FLASK_DEBUG') == '1'
    # With the reloader active, only the child process should run jobs
    if not debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        scheduler.start_scheduler()
    if debug:
        app.run(host=config.WEB_HOST, port=config.WEB_PORT, debug=True)
    else:
        try:
            from waitress import serve
            print(f"Serving on http://{config.WEB_HOST}:{config.WEB_PORT} (waitress)")
            serve(app, host=config.WEB_HOST, port=config.WEB_PORT, threads=8)
        except ImportError:
            app.run(host=config.WEB_HOST, port=config.WEB_PORT)
