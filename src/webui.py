#!/usr/bin/env python3
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import os
import yaml
import json
import config

app = Flask(__name__, template_folder=config.TEMPLATES_DIR)
app.secret_key = os.urandom(24)

CRON_FILE = os.path.join(config.DATA_DIR, "cron_schedule.json")

def load_cron_schedule():
    if os.path.exists(CRON_FILE):
        with open(CRON_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_cron_schedule(schedule):
    with open(CRON_FILE, 'w') as f:
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
    
    curation = {
        'filename': filename,
        'name': filename[:-5],
        'collection_name': data.get('playlist_name', ''),
        'keywords': ', '.join(data.get('keywords', [])),
        'prompt': data.get('prompt', ''),
        'min_rating': data.get('filters', {}).get('min_rating', 6.0),
        'use_ai': bool(data.get('prompt', '').strip())
    }
    
    return render_template('edit_curation.html', curation=curation, months=get_month_list())

@app.route('/curation/save', methods=['POST'])
def save_curation():
    name = request.form.get('name', '').strip()
    collection_name = request.form.get('collection_name', '').strip()
    keywords_str = request.form.get('keywords', '').strip()
    prompt = request.form.get('prompt', '').strip()
    min_rating = float(request.form.get('min_rating', 6.0))
    use_ai = request.form.get('use_ai') == 'on'
    
    if not name or not collection_name:
        flash('Name and Collection Name are required', 'error')
        return redirect(url_for('new_curation'))
    
    keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
    
    data = {
        'playlist_name': collection_name,
        'filters': {
            'min_rating': min_rating
        }
    }
    
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

if __name__ == '__main__':
    os.makedirs(config.DATA_DIR, exist_ok=True)
    os.makedirs(config.THEMES_DIR, exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)