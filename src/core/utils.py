#!/usr/bin/env python3
import os
import json
import datetime
import unicodedata
import re

def log(msg):
    print(f"{datetime.datetime.now().isoformat()} - {msg}", flush=True)

def load_json_file(file_path):
    if not os.path.exists(file_path) or os.stat(file_path).st_size == 0:
        return {}
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        log(f"[X] JSON decode error in {file_path}, resetting file")
        return {}

def save_json_file(file_path, data):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)

def normalize_title(title):
    title = title.lower()
    title = re.sub(r"\(.*?\)", "", title)
    title = re.sub(r"[^\w\s]", "", title)
    title = unicodedata.normalize("NFKD", title)
    return title.strip()

def clean_keywords(keywords):
    return [re.sub(r'^\d+\.\s*', '', kw).strip() for kw in keywords if kw.strip()]