#!/usr/bin/env python3
import json
import re
import requests
from core.utils import log
import config

def parse_ollama_response(resp_text):
    resp_text = resp_text.strip()
    if not resp_text:
        return []

    try:
        parsed = json.loads(resp_text)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except json.JSONDecodeError:
        pass

    resp_text = resp_text.strip("{}[]\n ")
    
    candidates = []
    if "\n" in resp_text:
        for line in resp_text.splitlines():
            line = line.strip("-• \t\"")
            if line:
                candidates.append(line)
    elif "," in resp_text:
        for part in resp_text.split(","):
            part = part.strip("\" ")
            if part:
                candidates.append(part)
    else:
        candidates.append(resp_text)

    cleaned = []
    for c in candidates:
        c = re.sub(r'^\d+\.\s*', '', c)
        c = c.strip()
        if c and c not in cleaned:
            cleaned.append(c)
    return cleaned

def ai_request(prompt):
    try:
        resp = requests.post(
            config.AI_API_URL,
            json={"model": config.AI_MODEL, "prompt": prompt},
            stream=True,
            timeout=config.AI_TIMEOUT
        )
        response_text = ""
        for line in resp.iter_lines(decode_unicode=True):
            if line:
                try:
                    data = json.loads(line)
                    if "response" in data:
                        response_text += data["response"]
                except json.JSONDecodeError:
                    response_text += line
        
        cleaned_list = parse_ollama_response(response_text)
        log(f"[DEBUG] AI response ({len(cleaned_list)} items): {cleaned_list[:5]}...")
        return cleaned_list
    except Exception as e:
        log(f"[X] AI request failed: {e}")
        return []

def generate_keywords(collection_name):
    prompt = f"Keywords for '{collection_name}': Return exactly 7 genre/theme words as JSON array."
    keywords = ai_request(prompt)
    if not keywords:
        keywords = list(set(re.findall(r'\w+', collection_name.lower())))
    return keywords

def suggest_movies(theme_prompt, max_suggestions):
    prompt = f"{theme_prompt}\n\nSuggest up to {max_suggestions} well-known movie titles that best fit this theme. Return ONLY a JSON list of movie titles (no years, no descriptions, no explanations)."
    suggested_titles = ai_request(prompt)
    
    cleaned_titles = []
    for title in suggested_titles:
        title = re.sub(r'\s*[-:(].*$', '', title)
        title = title.strip('"\'')
        if title and len(title) > 2 and not title.startswith(("It seems", "Here", "From", "Sure", "I'd", "Based")):
            cleaned_titles.append(title)
    
    return cleaned_titles