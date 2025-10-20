#!/usr/bin/env python3
"""
Updates cron jobs based on the schedule configuration
Run this after saving schedule in web UI
"""
import os
import json
import config

CRON_FILE = os.path.join(config.DATA_DIR, "cron_schedule.json")
CRONTAB_FILE = "/etc/cron.d/plex-curator"

def update_cron_jobs():
    if not os.path.exists(CRON_FILE):
        print("No schedule file found")
        return
    
    with open(CRON_FILE, 'r') as f:
        schedule = json.load(f)
    
    cron_entries = []
    
    # Add main scheduled run (runs all scheduled curations)
    cron_entries.append("# Run all scheduled curations")
    cron_entries.append(f"0 */6 * * * cd {config.BASE_DIR} && python3 curator.py >> /var/log/plex-curator.log 2>&1")
    cron_entries.append("")
    
    # Add individual curation jobs if needed
    for filename, job_config in schedule.items():
        curation_name = filename.replace('.yaml', '')
        cron_pattern = job_config.get('cron', '0 0 1 * *')
        description = job_config.get('description', 'Curation job')
        
        cron_entries.append(f"# {description} - {curation_name}")
        cron_entries.append(f"{cron_pattern} cd {config.BASE_DIR} && python3 curator.py {curation_name} >> /var/log/plex-curator-{curation_name}.log 2>&1")
        cron_entries.append("")
    
    # Write to crontab file
    with open(CRONTAB_FILE, 'w') as f:
        f.write("\n".join(cron_entries))
    
    # Reload cron
    os.system(f"chmod 0644 {CRONTAB_FILE}")
    os.system(f"crontab {CRONTAB_FILE}")
    
    print(f"Updated {len(schedule)} cron job(s)")

if __name__ == "__main__":
    update_cron_jobs()