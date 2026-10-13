#!/usr/bin/env python3
import sys
import os
import json
import datetime
import tempfile

# Point config at a temp dir BEFORE importing it so scheduler file paths
# never touch /opt/plex-curator during tests.
_TMP = tempfile.mkdtemp(prefix="plex-curator-test-")
os.makedirs(os.path.join(_TMP, "data"), exist_ok=True)
os.environ["CURATOR_BASE_DIR"] = _TMP

if not os.path.exists("/opt/plex-curator/src"):
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import config
import scheduler


def test_due_detection():
    schedules = {
        "movie:monthly": {"cron": "0 0 1 * *", "enabled": True},
        "channel:cartoons": {"cron": "0 5 * * 6", "enabled": True},
    }
    # Window crossing midnight on the 1st: monthly fires, cartoons doesn't
    last = datetime.datetime(2026, 9, 30, 23, 59)
    now = datetime.datetime(2026, 10, 1, 0, 1)
    due = scheduler.due_jobs(schedules, last, now)
    assert due == ["movie:monthly"], f"got {due}"
    print("✓ Due detection test passed")


def test_due_fires_once_per_occurrence():
    schedules = {"job": {"cron": "0 5 * * 6", "enabled": True}}
    # Sat 2026-10-03 05:00
    before = datetime.datetime(2026, 10, 3, 4, 59)
    at = datetime.datetime(2026, 10, 3, 5, 0, 30)
    later = datetime.datetime(2026, 10, 3, 5, 1)
    assert scheduler.due_jobs(schedules, before, at) == ["job"]
    # next window starts after the firing — must not fire again
    assert scheduler.due_jobs(schedules, at, later) == []
    print("✓ Fires once per occurrence test passed")


def test_disabled_and_invalid_skipped():
    schedules = {
        "disabled": {"cron": "* * * * *", "enabled": False},
        "invalid": {"cron": "not a cron", "enabled": True},
        "blank": {"cron": "", "enabled": True},
    }
    last = datetime.datetime(2026, 10, 1, 0, 0)
    now = datetime.datetime(2026, 10, 1, 0, 5)
    assert scheduler.due_jobs(schedules, last, now) == []
    print("✓ Disabled/invalid schedule skip test passed")


def test_saturday_morning_cron():
    nxt = scheduler.next_run("0 5 * * 6", datetime.datetime(2026, 10, 12, 12, 0))
    # 2026-10-12 is a Monday; next Saturday is the 17th
    assert nxt == "2026-10-17T05:00:00", f"got {nxt}"
    print("✓ Saturday-morning cron math test passed")


def test_legacy_migration():
    legacy = config.LEGACY_CRON_SCHEDULE_FILE
    for path in (legacy, f"{legacy}.bak", config.SCHEDULES_FILE):
        if os.path.exists(path):
            os.remove(path)
    with open(legacy, "w") as f:
        json.dump({"october.yaml": {"cron": "0 0 1 10 *", "description": "Spooky"}}, f)

    scheduler.migrate_legacy_schedule()

    schedules = scheduler.load_schedules()
    assert "movie:october" in schedules, f"got {schedules}"
    assert schedules["movie:october"]["cron"] == "0 0 1 10 *"
    assert schedules["movie:october"]["enabled"] is True
    assert not os.path.exists(legacy), "legacy file should be renamed"
    assert os.path.exists(f"{legacy}.bak")
    print("✓ Legacy cron_schedule.json migration test passed")


def test_seed_defaults():
    if os.path.exists(config.SCHEDULES_FILE):
        os.remove(config.SCHEDULES_FILE)
    os.makedirs(config.CHANNELS_DIR, exist_ok=True)
    with open(os.path.join(config.CHANNELS_DIR, "cartoons.yaml"), "w") as f:
        f.write("playlist_name: Cartoons\ndefault_schedule: '0 5 * * 6'\n")

    scheduler.seed_default_schedules()

    schedules = scheduler.load_schedules()
    assert "movie:monthly" in schedules
    assert schedules["movie:monthly"]["cron"] == "0 0 1 * *"
    assert "channel:cartoons" in schedules
    assert schedules["channel:cartoons"]["cron"] == "0 5 * * 6"
    # Seeding again must not clobber user edits
    schedules["channel:cartoons"]["cron"] = "0 6 * * 6"
    scheduler.save_schedules(schedules)
    scheduler.seed_default_schedules()
    assert scheduler.load_schedules()["channel:cartoons"]["cron"] == "0 6 * * 6"
    print("✓ Default schedule seeding test passed")


def test_status_roundtrip():
    if os.path.exists(config.JOB_STATUS_FILE):
        os.remove(config.JOB_STATUS_FILE)
    scheduler._set_status("movie:october", last_status="success", last_error=None)
    scheduler._set_status("movie:october", last_run="2026-10-01T00:00:00")
    status = scheduler.get_status()
    assert status["movie:october"]["last_status"] == "success"
    assert status["movie:october"]["last_run"] == "2026-10-01T00:00:00"
    print("✓ Status round-trip test passed")


def test_describe_cron():
    cases = {
        "0 0 * * *": "Daily at 00:00",
        "30 5 * * 6": "Weekly on Saturday at 05:30",
        "0 5 * * 0": "Weekly on Sunday at 05:00",
        "0 0 1 * *": "Monthly on day 1 at 00:00",
        "0 6 1 10 *": "Yearly on October 1 at 06:00",
        "*/5 * * * *": "*/5 * * * *",       # fancy -> raw passthrough
        "not a cron": "not a cron",
    }
    for cron, expected in cases.items():
        got = scheduler.describe_cron(cron)
        assert got == expected, f"{cron!r}: got {got!r}, want {expected!r}"
    print("✓ describe_cron test passed")


def run_all_tests():
    print("\nRunning scheduler tests...")
    print("=" * 50)
    tests = [
        test_describe_cron,
        test_due_detection,
        test_due_fires_once_per_occurrence,
        test_disabled_and_invalid_skipped,
        test_saturday_morning_cron,
        test_legacy_migration,
        test_seed_defaults,
        test_status_roundtrip,
    ]
    failed = 0
    for test in tests:
        try:
            test()
        except AssertionError as e:
            print(f"✗ {test.__name__} failed: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__} errored: {e}")
            failed += 1
    print("=" * 50)
    if failed == 0:
        print(f"✓ All {len(tests)} scheduler tests passed!")
        return True
    print(f"✗ {failed}/{len(tests)} tests failed")
    return False


if __name__ == "__main__":
    sys.exit(0 if run_all_tests() else 1)
