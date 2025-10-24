#!/usr/bin/env python3
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import os
import yaml
import json
import config

app = Flask(__name__, template_folder=config.TEMPLATES_DIR)
app.secret_key = os.urandom(24)

SCHEDULE_FILE = os.path.join(config.DATA_DIR, "schedule.json")

def load_schedule():
    """Load enhanced schedule configuration"""
    if os.path.exists(SCHEDULE_FILE):
        with open(SCHEDULE_FILE, 'r') as f:
            return json.load(f)
    return {
        "monthly_auto": {"enabled": True, "cron": "0 0 1 * *", "description": "Auto-run current month"},
        "individual": {},
        "recurring": {}
    }

def save_schedule(schedule):
    """Save enhanced schedule configuration"""
    with open(SCHEDULE_FILE, 'w') as f:
        json.dump(schedule, f, indent=2)

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
    cron_schedule = load_cron_schedule()
    return render_template('index.html', curations=curations, cron_schedule=cron_schedule)

@app.route('/curation/new')
def new_curation():
    return render_template('edit_curation.html', curation=None, months=get_month_list())

@app.route('/curation/edit/<filename>')
def edit_curation(filename):
    filepath = os.path.join(config.THEMES_DIR, filename)
    if not os.path.exists(filepath):
        flash('Curation not found', 'error')
        return redirect(url_for('index'))
    
    with open(filepath, 'r') as f:
        data = yaml.safe_load(f)
    
    filters = data.get('filters', {})
    year_range = filters.get('year_range', [])
    runtime_range = filters.get('runtime_range', [])
    
    curation = {
        'filename': filename,
        'name': filename[:-5],
        'collection_name': data.get('playlist_name', ''),
        'keywords': ', '.join(data.get('keywords', [])),
        'prompt': data.get('prompt', ''),
        'min_rating': filters.get('min_rating', 6.0),
        'max_items': data.get('max_items', config.DEFAULT_COLLECTION_SIZE),
        'use_ai': bool(data.get('prompt', '').strip()),
        # Advanced fields
        'summary': data.get('summary', ''),
        'sort_title': data.get('sort_title', ''),
        'max_rating': filters.get('max_rating', ''),
        'min_votes': filters.get('min_votes', ''),
        'year_start': year_range[0] if len(year_range) > 0 else '',
        'year_end': year_range[1] if len(year_range) > 1 else '',
        'runtime_min': runtime_range[0] if len(runtime_range) > 0 else '',
        'runtime_max': runtime_range[1] if len(runtime_range) > 1 else '',
        'content_rating': ', '.join(filters.get('content_rating', [])) if isinstance(filters.get('content_rating'), list) else filters.get('content_rating', ''),
        'language': filters.get('language', ''),
        'include_genres': ', '.join(filters.get('include_genres', [])) if isinstance(filters.get('include_genres'), list) else '',
        'exclude_genres': ', '.join(filters.get('exclude_genres', [])) if isinstance(filters.get('exclude_genres'), list) else '',
        'promote_to_home': data.get('promote_to_home', True),
        'poster_url': data.get('poster_url', ''),
        'prioritize': data.get('prioritize', '')
    }
    
    return render_template('edit_curation.html', curation=curation, months=get_month_list())

@app.route('/curation/save', methods=['POST'])
def save_curation():
    name = request.form.get('name', '').strip()
    collection_name = request.form.get('collection_name', '').strip()
    keywords_str = request.form.get('keywords', '').strip()
    prompt = request.form.get('prompt', '').strip()
    min_rating = float(request.form.get('min_rating', 6.0))
    max_items = int(request.form.get('max_items', config.DEFAULT_COLLECTION_SIZE))
    use_ai = request.form.get('use_ai') == 'on'
    
    # Advanced fields
    summary = request.form.get('summary', '').strip()
    sort_title = request.form.get('sort_title', '').strip()
    max_rating = request.form.get('max_rating', '').strip()
    min_votes = request.form.get('min_votes', '').strip()
    year_start = request.form.get('year_start', '').strip()
    year_end = request.form.get('year_end', '').strip()
    runtime_min = request.form.get('runtime_min', '').strip()
    runtime_max = request.form.get('runtime_max', '').strip()
    content_rating = request.form.get('content_rating', '').strip()
    language = request.form.get('language', '').strip()
    include_genres = request.form.get('include_genres', '').strip()
    exclude_genres = request.form.get('exclude_genres', '').strip()
    promote_to_home = request.form.get('promote_to_home') == 'on'
    poster_url = request.form.get('poster_url', '').strip()
    prioritize = request.form.get('prioritize', '').strip()
    
    if not name or not collection_name:
        flash('Name and Collection Name are required', 'error')
        return redirect(url_for('new_curation'))
    
    keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
    
    # Build data structure
    data = {
        'playlist_name': collection_name,
        'max_items': max_items,
        'filters': {
            'min_rating': min_rating
        }
    }
    
    # Add optional metadata
    if summary:
        data['summary'] = summary
    if sort_title:
        data['sort_title'] = sort_title
    if poster_url:
        data['poster_url'] = poster_url
    
    # Add advanced filters
    if max_rating:
        data['filters']['max_rating'] = float(max_rating)
    if min_votes:
        data['filters']['min_votes'] = int(min_votes)
    if year_start and year_end:
        data['filters']['year_range'] = [int(year_start), int(year_end)]
    elif year_start:
        data['filters']['year_range'] = [int(year_start), 2030]
    if runtime_min and runtime_max:
        data['filters']['runtime_range'] = [int(runtime_min), int(runtime_max)]
    if content_rating:
        data['filters']['content_rating'] = [r.strip() for r in content_rating.split(',')]
    if language:
        data['filters']['language'] = language
    if include_genres:
        data['filters']['include_genres'] = [g.strip() for g in include_genres.split(',')]
    if exclude_genres:
        data['filters']['exclude_genres'] = [g.strip() for g in exclude_genres.split(',')]
    
    # Add display options
    data['promote_to_home'] = promote_to_home
    
    # Add AI options
    if prioritize:
        data['prioritize'] = prioritize
    
    if keywords:
        data['keywords'] = keywords
    
    if use_ai and prompt:
        data['prompt'] = prompt
    
    filename = f"{name}.yaml"
    filepath = os.path.join(config.THEMES_DIR, filename)
    
    with open(filepath, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    
    flash(f'Curation "{name}" saved successfully', 'success')
    return redirect(url_for('index'))

@app.route('/curation/delete/<filename>', methods=['POST'])
def delete_curation(filename):
    filepath = os.path.join(config.THEMES_DIR, filename)
    if os.path.exists(filepath):
        os.remove(filepath)
        flash(f'Curation deleted', 'success')
    else:
        flash('Curation not found', 'error')
    return redirect(url_for('index'))

@app.route('/curation/run/<filename>', methods=['POST'])
def run_curation_now(filename):
    curation_name = filename.replace('.yaml', '')
    
    try:
        from curator import run_single_curation
        success = run_single_curation(curation_name)
        
        if success:
            flash(f'Curation "{curation_name}" completed successfully', 'success')
        else:
            flash(f'Curation "{curation_name}" completed with errors', 'error')
    except Exception as e:
        flash(f'Error running curation: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/schedule/save', methods=['POST'])
def save_schedule():
    data = request.json
    cron_schedule = load_cron_schedule()
    
    for filename, schedule in data.items():
        if schedule['enabled']:
            cron_schedule[filename] = {
                'cron': schedule['cron'],
                'description': schedule['description']
            }
        elif filename in cron_schedule:
            del cron_schedule[filename]
    
    save_cron_schedule(cron_schedule)
    
    # Update actual cron jobs
    try:
        import subprocess
        subprocess.run(['python3', '/opt/plex-curator/update_cron.py'], check=True)
    except Exception as e:
        print(f"Error updating cron: {e}")
    
    return jsonify({'status': 'success'})

def get_month_list():
    return [
        'january', 'february', 'march', 'april', 'may', 'june',
        'july', 'august', 'september', 'october', 'november', 'december'
    ]

# Ensure directories exist on import
os.makedirs(config.DATA_DIR, exist_ok=True)
os.makedirs(config.THEMES_DIR, exist_ok=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)