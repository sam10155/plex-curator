#!/usr/bin/env python3
import json
import re
import requests
from core.utils import log, normalize_title
import config

def clean_movie_candidates(items):
    cleaned = []

    for item in items:
        item = item.strip()

        # remove numbering
        item = re.sub(r'^\d+[\.\)]\s*', '', item)

        # reject obvious non-title responses
        if len(item) < 2:
            continue

        cleaned.append(item)

    return list(dict.fromkeys(cleaned))

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
        return keywords[:50]
    
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
            json={
                "model": config.AI_MODEL,
                "prompt": prompt,
                "options": {
                    "temperature": 0.2
                },
                "think": False
                },
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

def suggest_movies(theme_prompt, max_suggestions, requirements=None):
    requirements_block = ""
    if requirements and requirements.strip():
        requirements_block = f"""
    HARD REQUIREMENTS — every single title MUST satisfy ALL of these:
    {requirements.strip()}
    Do not include any title that fails these requirements, even if it fits the theme.
    """
    prompt = f"""
    {theme_prompt}
    {requirements_block}
    You are selecting entries from a movie database.

    Return up to {max_suggestions} actual movie titles.

    Rules:
    - Every item must be a film title.
    - Do not return themes, topics, events, people, places, organizations, or keywords.
    - Do not return explanations.
    - Do not include years.
    - Do not include TV shows unless explicitly requested.

    Return ONLY valid JSON:
    ["Movie Title 1", "Movie Title 2"]
    """
    suggested_titles = ai_request(prompt)

    cleaned_titles = []
    for title in suggested_titles:
        title = re.sub(r'\s*[-:(].*$', '', title)
        title = title.strip('"\'')
        if title and len(title) > 2 and not title.startswith(("It seems", "Here", "From", "Sure", "I'd", "Based")):
            cleaned_titles.append(title)

    return list(dict.fromkeys(cleaned_titles))

def match_verification_response(returned, titles):
    """Map a verification response back to candidate indices (0-based).
    Accepts 1-based numbers ("3", 3) and/or titles; junk is ignored.
    Pure function so it can be unit-tested offline."""
    by_norm = {}
    for i, title in enumerate(titles):
        by_norm.setdefault(normalize_title(title), i)
    kept = set()
    for item in returned:
        item = str(item).strip().strip('"\'')
        m = re.match(r'^(\d+)[\.\):]?\s*', item)
        if m and item == m.group(0).strip():
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(titles):
                kept.add(idx)
            continue
        item = re.sub(r'^\d+[\.\)]\s*', '', item)
        item = re.sub(r'\s*\(\d{4}\)\s*$', '', item)
        idx = by_norm.get(normalize_title(item))
        if idx is not None:
            kept.add(idx)
    return kept


def verify_movies(requirements, movies, batch_size=40):
    """Second-pass gate: ask the LLM which already-matched movies actually
    satisfy the theme's hard requirements; everything else is dropped.
    Fails open — if the LLM errors or returns nothing usable for a batch,
    that whole batch is kept (an unfiltered collection beats an empty one).

    movies: objects with .title / .year / .summary (plexapi movies).
    Returns the list of kept indices into `movies`, in order."""
    kept = []
    for start in range(0, len(movies), batch_size):
        batch = movies[start:start + batch_size]
        titles = [m.title for m in batch]
        lines = []
        for i, m in enumerate(batch, 1):
            year = getattr(m, "year", None)
            summary = (getattr(m, "summary", "") or "")[:150].replace("\n", " ")
            lines.append(f"{i}. {m.title}" + (f" ({year})" if year else "") +
                         (f" — {summary}" if summary else ""))
        movie_list = "\n".join(lines)
        prompt = f"""You are verifying movies against hard requirements.

Requirements — a movie passes ONLY if it satisfies ALL of these:
{requirements.strip()}

Movies to verify:
{movie_list}

Return ONLY a valid JSON array with the numbers of the movies that PASS,
for example: [1, 4, 7]. If none pass, return [].
"""
        returned = ai_request(prompt)
        if not returned:
            log(f"[-] Verification batch returned nothing usable — keeping all {len(batch)} (fail open)")
            kept.extend(range(start, start + len(batch)))
            continue
        indices = match_verification_response(returned, titles)
        for i in range(len(batch)):
            if i in indices:
                kept.append(start + i)
            else:
                log(f"    [X] Dropped by requirements: {batch[i].title}")
    return kept


def suggest_shows(theme_prompt, candidates, want):
    """Ask the LLM to pick TV shows for a channel theme from the library's
    candidate list. Returns the matching candidate records; anything the
    model returns that isn't actually in the list is dropped."""
    lines = []
    for i, c in enumerate(candidates, 1):
        parts = [c["title"] + (f" ({c['year']})" if c.get("year") else "")]
        if c.get("genres"):
            parts.append(", ".join(c["genres"][:4]))
        if c.get("content_rating"):
            parts.append(c["content_rating"])
        rating = c.get("tmdb_rating") or c.get("rating")
        if rating:
            parts.append(f"rating {rating}/10")
        if c.get("summary"):
            parts.append(c["summary"][:120].replace("\n", " "))
        lines.append(f"{i}. " + " | ".join(parts))

    show_list = "\n".join(lines)
    # The example array must show the full requested count — small models
    # copy the example's length (an example of 2 yields exactly 2 picks)
    example = json.dumps([f"Show Title {i}" for i in range(1, min(want, 8) + 1)])
    prompt = f"""{theme_prompt}

Below is a numbered list of TV shows available in the library.
Pick the {want} shows that best fit the theme above.

{show_list}

Rules:
- Return exactly {want} different shows. Return fewer ONLY if the list has fewer shows that fit the theme.
- Only choose shows from the list above, with titles exactly as written (omit the year and extra fields).
- Do not invent shows that are not in the list.
- Do not return explanations.

Return ONLY a valid JSON array of {want} titles, like:
{example}
"""
    returned = ai_request(prompt)
    log(f"[-] AI returned {len(returned)} items")

    by_norm = {normalize_title(c["title"]): c for c in candidates}
    picked = []
    seen = set()
    for title in returned:
        title = re.sub(r'^\d+[\.\)]\s*', '', title)
        title = re.sub(r'\s*\(\d{4}\)\s*$', '', title).strip('"\' ')
        norm = normalize_title(title)
        candidate = by_norm.get(norm)
        if candidate and norm not in seen:
            picked.append(candidate)
            seen.add(norm)
        elif title and not candidate:
            log(f"    [X] Dropping AI pick not in library: {title}")

    return picked[:want]

def suggest_episodes(theme_prompt, episodes, want=20):
    """Ask the LLM to pick specific episodes fitting a channel theme.
    Returns the set of episode keys whose titles the model picked; used as
    a soft preference boost in block assembly, so bad picks cost nothing."""
    lines = []
    for i, ep in enumerate(episodes, 1):
        lines.append(f"{i}. {ep['show_title']} - S{ep['season']:02d}E{ep['episode']:02d} - {ep['title']}")

    episode_list = "\n".join(lines)
    prompt = f"""{theme_prompt}

Below is a numbered list of TV episodes available in the library.
Pick up to {want} episode titles that best fit the theme above.

{episode_list}

Rules:
- Only choose episode titles exactly as written after the second dash.
- Do not invent episodes that are not in the list.
- Do not return explanations.

Return ONLY valid JSON:
["Episode Title 1", "Episode Title 2"]
"""
    returned = ai_request(prompt)

    by_norm = {}
    for ep in episodes:
        by_norm.setdefault(normalize_title(ep["title"]), []).append(ep["key"])

    keys = set()
    for title in returned:
        title = re.sub(r'^\d+[\.\)]\s*', '', title)
        # tolerate "Show - S01E02 - Title" echoes
        if " - " in title:
            title = title.split(" - ")[-1]
        norm = normalize_title(title.strip('"\' '))
        for key in by_norm.get(norm, []):
            keys.add(key)

    log(f"[-] AI episode boost: {len(keys)} episodes preferred")
    return keys
