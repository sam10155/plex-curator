#!/usr/bin/env python3
"""
Scheduling system for Plex Curator
Manages cron jobs for monthly auto-run, individual, and recurring curations
"""
import os
import json
import sys

# Add src to path
sys.path.insert(0, '/opt/plex-curator/src')
import config

SCHEDULE_FILE = os.path.join(config.DATA_DIR, "schedule.json")
CRONTAB_FILE = "/etc/cron.d/plex-curator"

def load_schedule():
    """Load schedule configuration"""
    if os.path.exists(SCHEDULE_FILE):
        with open(SCHEDULE_FILE, 'r') as f:
            return json.load(f)
    return {
        "monthly_auto": {"enabled": True, "cron": "0 0 1 * *", "description": "Auto-run current month"},
        "individual": {},
        "recurring": {}
    }

def generate_cron_entries():
    """Generate cron entries from schedule configuration"""
    schedule = load_schedule()
    entries = []
    
    entries.append("# Plex Curator - Auto-generated schedule")
    entries.append("# DO NOT EDIT MANUALLY - Changes will be overwritten")
    entries.append("")
    
    # Monthly auto-curator
    if schedule.get("monthly_auto", {}).get("enabled", False):
        cron = schedule["monthly_auto"]["cron"]
        desc = schedule["monthly_auto"].get("description", "Monthly Auto-Curator")
        entries.append(f"# {desc}")
        entries.append(f"{cron} cd {config.BASE_DIR} && python3 -m src.monthly >> /var/log/plex-curator-monthly.log 2>&1")
        entries.append("")
    
    # Individual scheduled curations
    individual = schedule.get("individual", {})
    if individual:
        entries.append("# Individual Scheduled Curations")
        for filename, settings in individual.items():
            curation_name = filename.replace('.yaml', '')
            cron = settings.get("cron", "0 0 1 * *")
            description = settings.get("description", f"Run {curation_name}")
            entries.append(f"# {description}")
            entries.append(f"{cron} cd {config.BASE_DIR} && python3 -m src.curator {curation_name} >> /var/log/plex-curator-{curation_name}.log 2>&1")
        entries.append("")
    
    # Recurring curations
    recurring = schedule.get("recurring", {})
    if recurring:
        entries.append("# Recurring Curations")
        for filename, settings in recurring.items():
            curation_name = filename.replace('.yaml', '')
            cron = settings.get("cron", "0 0 */14 * *")
            description = settings.get("description", f"Recurring: {curation_name}")
            entries.append(f"# {description}")
            entries.append(f"{cron} cd {config.BASE_DIR} && python3 -m src.curator {curation_name} >> /var/log/plex-curator-{curation_name}.log 2>&1")
        entries.append("")
    
    return "\n".join(entries)

def update_crontab():
    """Update system crontab with current schedule"""
    try:
        cron_content = generate_cron_entries()
        
        with open(CRONTAB_FILE, 'w') as f:
            f.write(cron_content)
        
        os.chmod(CRONTAB_FILE, 0o644)
        os.system(f"crontab {CRONTAB_FILE}")
        
        print("✓ Crontab updated successfully")
        print("\nActive schedules:")
        print(cron_content)
        return True
        
    except Exception as e:
        print(f"✗ Error updating crontab: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    success = update_crontab()
    sys.exit(0 if success else 1)