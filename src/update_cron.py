#!/usr/bin/env python3
"""
Updates cron jobs based on the schedule configuration.
Run this after saving schedule in web UI.
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

    cron_entries = [
        "# Plex Curator - auto-generated cron jobs",
        "# Format: schedule username command",
        "",
    ]

    # Add individual curation jobs from the saved schedule
    for filename, job_config in schedule.items():
        curation_name = filename.replace('.yaml', '')
        cron_pattern = job_config.get('cron', '0 0 1 * *')
        description = job_config.get('description', 'Curation job')

        cron_entries.append(f"# {description} - {curation_name}")
        cron_entries.append(
            f"{cron_pattern} root . /etc/environment; "
            f"cd {config.BASE_DIR} && python3 src/curator.py {curation_name} "
            f">> /var/log/plex-curator-{curation_name}.log 2>&1"
        )
        cron_entries.append("")

    # Write to /etc/cron.d/ — cron daemon picks this up automatically,
    # no need to call `crontab` on it.
    with open(CRONTAB_FILE, 'w') as f:
        f.write("\n".join(cron_entries) + "\n")

    os.system(f"chmod 0644 {CRONTAB_FILE}")

    print(f"Updated {len(schedule)} cron job(s) in {CRONTAB_FILE}")

if __name__ == "__main__":
    update_cron_jobs()
