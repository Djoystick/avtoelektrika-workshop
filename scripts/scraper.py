import os
import json
import re
import time
import hashlib
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

SOURCES = [
    {
        "name": "drive2",
        "base_url": "https://drive2.ru",
        "forum_url": "https://drive2.ru/forums/elektrooborudovanie.107/",
        "thread_selector": "div.structItem--thread",
        "title_selector": "div.structArg-title a",
        "link_selector": "div.structArg-title a",
    },
    {
        "name": "drom",
        "base_url": "https://www.drom.ru",
        "forum_url": "https://www.drom.ru/forum/elektrooborudovanie/",
        "thread_selector": "div.b-topic",
        "title_selector": "a.b-topic__title",
        "link_selector": "a.b-topic__title",
    },
    {
        "name": "don",
        "base_url": "https://forums.don.ru",
        "forum_url": "https://forums.don.ru/forumdisplay.php?f=30",
        "thread_selector": "tr.threadbit",
        "title_selector": "a.title",
        "link_selector": "a.title",
    }
]

KNOWN_BRANDS = [
    'ваз', 'лада', 'toyota', 'bmw', 'audi', 'ford', 'opel', 'renault',
    'kia', 'hyundai', 'volkswagen', 'skoda', 'chevrolet', 'nissan', 'mitsubishi'
]

SYMPTOM_KEYWORDS = [
    'не заводится', 'check engine', 'горит чек', 'утечка тока', 'нет зарядки',
    'троит', 'стучит', 'мертвый аккумулятор', 'короткое замыкание', 'обрыв',
    'модуль зажигания', 'датчик коленвала', 'генератор'
]

CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)

def get_cache_key(url):
    return hashlib.md5(url.encode()).hexdigest() + ".html"

def fetch_cached(url, cache_hours=24):
    cache_file = CACHE_DIR / get_cache_key(url)
    if cache_file.exists():
        mtime = cache_file.stat().st_mtime
        if time.time() - mtime < cache_hours * 3600:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return f.read()
    resp = requests.get(url, headers={'User-Agent': 'AutoElectroBot/1.0'})
    resp.raise_for_status()
    html = resp.text
    with open(cache_file, 'w', encoding='utf-8') as f:
        f.write(html)
    time.sleep(1)
    return html

def extract_error_codes(text):
    pattern = r'\b[PCBU]\d{4}\b'
    return list(set(re.findall(pattern, text, re.IGNORECASE)))

def scrape_forum(source):
    print(f"Парсинг: {source['name']}")
    try:
        html = fetch_cached(source['forum_url'])
        soup = BeautifulSoup(html, 'html.parser')
        threads = soup.select(source['thread_selector'])
        problems = []
        for thread in threads[:8]:
            title_elem = thread.select_one(source['title_selector'])
            link_elem = thread.select_one(source['link_selector'])
            if not title_elem or not link_elem:
                continue
            title = title_elem.get_text(strip=True)
            rel_link = link_elem['href']
            abs_link = urljoin(source['base_url'], rel_link)

            try:
                content_html = fetch_cached(abs_link, cache_hours=168)
                content_text = BeautifulSoup(content_html, 'html.parser').get_text()
                error_codes = extract_error_codes(content_text)
            except Exception as e:
                print(f"Ошибка при парсинге темы {abs_link}: {e}")
                error_codes = []

            brand = None
            for b in KNOWN_BRANDS:
                if b in title.lower():
                    brand = b.upper()
                    break

            symptoms = []
            for k in SYMPTOM_KEYWORDS:
                if k in title.lower() or k in content_text.lower():
                    symptoms.append(k)

            if symptoms or error_codes:
                problems.append({
                    "id": f"{source['name']}_{hash(abs_link)}",
                    "title": title,
                    "brand": brand,
                    "symptoms": symptoms,
                    "error_codes": error_codes,
                    "source_url": abs_link,
                    "date_added": time.strftime("%Y-%m-%d")
                })
        return problems
    except Exception as e:
        print(f"Ошибка при парсинге {source['name']}: {e}")
        return []

def load_existing():
    path = Path("db/problems.json")
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_problems(problems):
    db_dir = Path("db")
    db_dir.mkdir(exist_ok=True)
    
    json_path = db_dir / "problems.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(problems, f, ensure_ascii=False, indent=2)

    js_path = db_dir / "problems.js"
    with open(js_path, 'w', encoding='utf-8') as f:
        json_str = json.dumps(problems, ensure_ascii=False, indent=2)
        f.write(f"window.problems = {json_str};\n")

def main():
    existing = {p['id']: p for p in load_existing()}
    new_problems = []

    for src in SOURCES:
        new_problems.extend(scrape_forum(src))

    for p in new_problems:
        existing[p['id']] = p

    final_list = list(existing.values())
    save_problems(final_list)
    print(f"Обновлено. Всего записей: {len(final_list)}")

if __name__ == '__main__':
    main()
