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
        elif isinstance(parsed, dict):
            all_values = []
            for v in parsed.values():
                if isinstance(v, list):
                    all_values.extend([str(x).strip() for x in v])
            return all_values
    except json.JSONDecodeError:
        pass

    array_pattern = r'\[([^\]]+)\]'
    arrays = re.findall(array_pattern, resp_text)
    
    keywords = []
    for array_content in arrays:
        items = array_content.split(',')
        for item in items:
            cleaned = re.sub(r'["\'\[\]]', '', item).strip()
            if cleaned and len(cleaned) > 2:
                keywords.append(cleaned)
    
    if keywords:
        return keywords[:10]
    
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
    prompt = f'List exactly 7 keywords for the movie collection "{collection_name}". Return ONLY a simple JSON array of single-word keywords, like ["ThemeOne", "ThemeTwo", "ThemeThree", "ThemeEtc"]. No explanations, no categories, just the array.'
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
