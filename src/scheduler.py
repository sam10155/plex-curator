#!/usr/bin/env python3
"""
In-app job scheduler. Replaces the old cron-in-container setup, which
silently failed (sourcing /etc/environment never exported env vars, and
/etc/cron.d entries written by the UI vanished on container restart).

Schedules live in data/schedules.json, keyed by job id:
    movie:monthly  -> run the current month's theme (replaces monthly.py)
    movie:<name>   -> run themes/<name>.yaml
    channel:<name> -> run channels/<name>.yaml

Job status (last run, success/failure, error) is persisted to
data/job_status.json and surfaced in the web UI. Occurrences missed while
the app was down are skipped, same as cron would.
"""
import datetime
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback

import config
from core.utils import log, load_json_file

RUN_HISTORY_LIMIT = 20

_started = False
_run_lock = threading.Lock()
_running_jobs = {}
_status_lock = threading.Lock()


def _atomic_write_json(path, data):
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------
# Schedules
# ---------------------------------------------------------
def load_schedules():
    return load_json_file(config.SCHEDULES_FILE)


def save_schedules(schedules):
    _atomic_write_json(config.SCHEDULES_FILE, schedules)


def migrate_legacy_schedule():
    """One-time conversion of the old cron_schedule.json (keyed by theme
    filename) into schedules.json (keyed by job id)."""
    legacy = config.LEGACY_CRON_SCHEDULE_FILE
    if not os.path.exists(legacy) or os.path.exists(config.SCHEDULES_FILE):
        return
    old = load_json_file(legacy)
    schedules = {}
    for filename, entry in old.items():
        name = filename.replace(".yaml", "")
        schedules[f"movie:{name}"] = {
            "cron": entry.get("cron", "0 0 1 * *"),
            "enabled": True,
            "description": entry.get("description", ""),
        }
    save_schedules(schedules)
    os.replace(legacy, f"{legacy}.bak")
    log(f"[-] Migrated {len(schedules)} legacy cron schedule(s) to {config.SCHEDULES_FILE}")


def seed_default_schedules():
    """Ensure the built-in monthly movie job and one job per channel YAML
    exist (channels seed from their default_schedule, enabled)."""
    import yaml
    schedules = load_schedules()
    changed = False

    if "movie:monthly" not in schedules:
        schedules["movie:monthly"] = {
            "cron": "0 0 1 * *",
            "enabled": True,
            "description": "Current month's movie theme",
        }
        changed = True

    if os.path.isdir(config.CHANNELS_DIR):
        for filename in sorted(os.listdir(config.CHANNELS_DIR)):
            if not filename.endswith(".yaml"):
                continue
            job_id = f"channel:{filename[:-5]}"
            if job_id in schedules:
                continue
            with open(os.path.join(config.CHANNELS_DIR, filename)) as f:
                cfg = yaml.safe_load(f) or {}
            schedules[job_id] = {
                "cron": cfg.get("default_schedule", "0 5 * * 6"),
                "enabled": True,
                "description": "Weekly channel refresh",
            }
            changed = True

    if changed:
        save_schedules(schedules)


# ---------------------------------------------------------
# Status
# ---------------------------------------------------------
def get_status():
    return load_json_file(config.JOB_STATUS_FILE)


def _set_status(job_id, **fields):
    with _status_lock:
        status = load_json_file(config.JOB_STATUS_FILE)
        entry = status.setdefault(job_id, {})
        entry.update(fields)
        try:
            _atomic_write_json(config.JOB_STATUS_FILE, status)
        except OSError as e:
            log(f"[X] Could not write job status: {e}")


def next_run(cron, base=None):
    """ISO timestamp of the next firing of a cron expression, or None."""
    try:
        from croniter import croniter
        nxt = croniter(cron, base or datetime.datetime.now()).get_next(datetime.datetime)
        return nxt.isoformat(timespec="seconds")
    except Exception:
        return None


_DOW_NAMES = {0: "Sunday", 1: "Monday", 2: "Tuesday", 3: "Wednesday",
              4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}
_MONTH_NAMES = {1: "January", 2: "February", 3: "March", 4: "April",
                5: "May", 6: "June", 7: "July", 8: "August",
                9: "September", 10: "October", 11: "November", 12: "December"}


def describe_cron(cron):
    """Human-readable recurrence for the simple cron shapes the schedule
    picker produces (daily/weekly/monthly/yearly at a time). Anything
    fancier falls back to the raw expression."""
    try:
        minute, hour, dom, month, dow = cron.split()
        time = f"{int(hour):02d}:{int(minute):02d}"
    except (AttributeError, ValueError):
        return cron
    if dom == "*" and month == "*":
        if dow == "*":
            return f"Daily at {time}"
        if dow.isdigit() and int(dow) in _DOW_NAMES:
            return f"Weekly on {_DOW_NAMES[int(dow)]} at {time}"
    if dom.isdigit() and dow == "*":
        if month == "*":
            return f"Monthly on day {int(dom)} at {time}"
        if month.isdigit() and int(month) in _MONTH_NAMES:
            return f"Yearly on {_MONTH_NAMES[int(month)]} {int(dom)} at {time}"
    return cron


# ---------------------------------------------------------
# Job execution
# ---------------------------------------------------------
def log_path(job_id):
    safe = re.sub(r'[^A-Za-z0-9_.-]', '_', job_id)
    return os.path.join(config.LOG_DIR, f"{safe}.log")


def read_log(job_id, max_bytes=100_000):
    """Tail of the job's last run log, for the web UI."""
    path = log_path(job_id)
    if not os.path.exists(path):
        return None
    try:
        size = os.path.getsize(path)
        with open(path, "r", errors="replace") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
            return f.read()
    except OSError as e:
        return f"Could not read log: {e}"


def _execute(job_id):
    """Run the job as a subprocess with stdout+stderr captured to its own
    log file in data/logs/ — the web UI serves that file. A subprocess
    (rather than an in-process call) captures output from worker threads
    too and isolates crashes from the web app."""
    kind, _, name = job_id.partition(":")
    if kind == "movie":
        if name == "monthly":
            name = datetime.datetime.now().strftime("%B").lower()
        cmd = [sys.executable, os.path.join(config.BASE_DIR, "src", "curator.py"), name]
    elif kind == "channel":
        cmd = [sys.executable, os.path.join(config.BASE_DIR, "src", "channels.py"), name]
    elif kind == "preview":
        cmd = [sys.executable, os.path.join(config.BASE_DIR, "src", "channels.py"), name, "--dry-run"]
    else:
        raise ValueError(f"Unknown job type in id: {job_id}")

    os.makedirs(config.LOG_DIR, exist_ok=True)
    with open(log_path(job_id), "w") as logfile:
        logfile.write(f"=== {job_id} started {_now_iso()} ===\n")
        logfile.flush()
        proc = subprocess.run(cmd, stdout=logfile, stderr=subprocess.STDOUT,
                              cwd=config.BASE_DIR)
        logfile.write(f"=== {job_id} finished {_now_iso()} (exit {proc.returncode}) ===\n")
    return proc.returncode == 0


def _append_history(job_id, record):
    with _status_lock:
        status = load_json_file(config.JOB_STATUS_FILE)
        entry = status.setdefault(job_id, {})
        history = entry.setdefault("history", [])
        history.append(record)
        entry["history"] = history[-RUN_HISTORY_LIMIT:]
        try:
            _atomic_write_json(config.JOB_STATUS_FILE, status)
        except OSError as e:
            log(f"[X] Could not write job status: {e}")


def _notify(job_id, status, error):
    """POST a JSON webhook on job completion. WEBHOOK_URL enables it;
    WEBHOOK_EVENTS is 'failed' (default), 'success', or 'all'."""
    url = os.getenv("WEBHOOK_URL")
    if not url:
        return
    events = os.getenv("WEBHOOK_EVENTS", "failed")
    if events != "all" and status != events:
        return
    try:
        import requests
        requests.post(url, json={
            "job": job_id,
            "status": status,
            "error": error,
            "time": _now_iso(),
        }, timeout=10)
        log(f"[-] Webhook sent for {job_id} ({status})")
    except Exception as e:
        log(f"[X] Webhook failed for {job_id}: {e}")


def _job_wrapper(job_id):
    started = _now_iso()
    _set_status(job_id, last_run=started, last_status="running", last_error=None)
    try:
        ok = _execute(job_id)
        status = "success" if ok else "failed"
        error = None if ok else "Run reported failure — see the job log"
    except Exception as e:
        log(f"[X] Job {job_id} failed: {e}")
        traceback.print_exc()
        status, error = "failed", str(e)[:500]
    _set_status(job_id, last_status=status, last_error=error)
    _append_history(job_id, {"started": started, "finished": _now_iso(),
                             "status": status, "error": error})
    _notify(job_id, status, error)


def run_job(job_id):
    """Dispatch a job in a background thread. Shared by the tick loop and
    the web UI's Run Now buttons. Returns (started, message)."""
    with _run_lock:
        existing = _running_jobs.get(job_id)
        if existing and existing.is_alive():
            return False, f"'{job_id}' is already running"
        thread = threading.Thread(target=_job_wrapper, args=(job_id,),
                                  daemon=True, name=f"job-{job_id}")
        _running_jobs[job_id] = thread
        thread.start()
    return True, f"'{job_id}' started"


# ---------------------------------------------------------
# Tick loop
# ---------------------------------------------------------
def due_jobs(schedules, last_checked, now):
    """Job ids whose cron fired in the (last_checked, now] window."""
    from croniter import croniter
    due = []
    for job_id, entry in schedules.items():
        if not entry.get("enabled"):
            continue
        cron = entry.get("cron", "").strip()
        if not cron:
            continue
        try:
            nxt = croniter(cron, last_checked).get_next(datetime.datetime)
        except Exception as e:
            log(f"[X] Invalid cron for {job_id}: '{cron}' ({e})")
            continue
        if nxt <= now:
            due.append(job_id)
    return due


def _tick_loop():
    last_checked = datetime.datetime.now()
    _set_status("_scheduler", started=_now_iso())
    while True:
        time.sleep(config.SCHEDULER_TICK_SECONDS)
        now = datetime.datetime.now()
        try:
            schedules = load_schedules()
            for job_id in due_jobs(schedules, last_checked, now):
                log(f"[-] Scheduler firing: {job_id}")
                run_job(job_id)
        except Exception as e:
            log(f"[X] Scheduler tick error: {e}")
            traceback.print_exc()
        last_checked = now


def start_scheduler():
    global _started
    if _started:
        return
    _started = True
    try:
        migrate_legacy_schedule()
        seed_default_schedules()
    except Exception as e:
        log(f"[X] Scheduler setup error: {e}")
    thread = threading.Thread(target=_tick_loop, daemon=True, name="scheduler")
    thread.start()
    log(f"[-] In-app scheduler started (tick every {config.SCHEDULER_TICK_SECONDS}s)")
