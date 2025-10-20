#!/usr/bin/env python3
"""
Monthly curation runner - automatically runs the curation for the current month
This is useful for monthly YAML files named after months (january.yaml, february.yaml, etc.)

Usage:
    python3 monthly.py              # Run current month
    python3 monthly.py october      # Force specific month
"""
import os
import sys
import datetime
from curator import run_single_curation
from core.utils import log

def get_month_name():
    """Get current month name in lowercase"""
    return datetime.datetime.now().strftime("%B").lower()

def run_monthly():
    """Run curation for current month or specified month"""
    if len(sys.argv) > 1:
        # Force specific month: python3 monthly.py october
        month = sys.argv[1].lower()
        log(f"[-] Forced month: {month}")
    else:
        # Use current month
        month = get_month_name()
        log(f"[-] Current month: {month}")
    
    # Check if month YAML exists
    from config import THEMES_DIR
    month_file = os.path.join(THEMES_DIR, f"{month}.yaml")
    
    if not os.path.exists(month_file):
        log(f"[X] No curation found for month: {month}")
        log(f"    Expected file: {month_file}")
        log("")
        log("[-] Available monthly curations:")
        
        months = [
            'january', 'february', 'march', 'april', 'may', 'june',
            'july', 'august', 'september', 'october', 'november', 'december'
        ]
        
        for m in months:
            mfile = os.path.join(THEMES_DIR, f"{m}.yaml")
            if os.path.exists(mfile):
                log(f"    ✓ {m}")
            else:
                log(f"    ✗ {m}")
        return False
    
    # Run the curation
    success = run_single_curation(month)
    return success

if __name__ == "__main__":
    try:
        success = run_monthly()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        log("\n[X] Interrupted by user")
        sys.exit(1)
    except Exception as e:
        log(f"\n[X] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)