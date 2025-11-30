import os
import json
import re
import time
import random
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

KNOWN_BRANDS = ['ваз', 'лада', 'toyota', 'bmw', 'audi', 'ford', 'opel', 'renault', 'kia', 'hyundai', 'volkswagen', 'skoda', 'chevrolet', 'nissan', 'mitsubishi']

# Упрощённый словарь для определения модели
BRAND_MODEL_MAP = {
    'ваз': ["2101", "2106", "2107", "2110", "2112", "2114", "Granta", "Kalina", "Largus", "Vesta", "XRAY"],
    'лада': ["2101", "2106", "2107", "2110", "2112", "2114", "Granta", "Kalina", "Largus", "Vesta", "XRAY"],
    'toyota': ["Corolla", "Camry", "RAV4", "Land Cruiser", "Hilux", "Prius", "Yaris", "Highlander", "Tacoma"],
    'bmw': ["3 Series", "5 Series", "7 Series", "X3", "X5", "X7", "Z4", "M3", "M5"],
    'audi': ["A3", "A4", "A5", "A6", "A7", "A8", "Q3", "Q5", "Q7", "TT", "R8"],
    'ford': ["Focus", "Fusion", "Escape", "Explorer", "Mustang", "F-150", "Bronco", "Edge"],
    'hyundai': ["Elantra", "Sonata", "Tucson", "Santa Fe", "Kona", "Venue", "Accent", "ioniq 5"],
    'kia': ["Rio", "Cerato", "Optima", "Sportage", "Sorento", "Seltos", "Stinger", "EV6"],
}

SYMPTOM_KEYWORDS = [
    'не заводится', 'check engine', 'горит чек', 'утечка тока', 'нет зарядки',
    'троит', 'стучит', 'мертвый аккумулятор', 'короткое замыкание', 'обрыв',
    'модуль зажигания', 'датчик коленвала', 'генератор'
]

CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)
MAX_PROBLEMS = 300

def get_cache_key(url):
    return hashlib.md5(url.encode()).hexdigest() + ".html"

def fetch_with_retry(url, max_retries=3, backoff_factor=1):
    for attempt in range(max_retries):
        try:
            resp = requests.get(
                url,
                headers={'User-Agent': 'AutoElectroBot/1.0 (open-source project)'},
                timeout=10
            )
            if resp.status_code == 200:
                return resp.text
            elif resp.status_code == 429:
                wait = backoff_factor * (2 ** attempt) + random.uniform(0, 1)
                print(f"⚠️ 429 Too Many Requests. Повтор через {wait:.1f} сек...")
                time.sleep(wait)
            elif resp.status_code >= 500:
                wait = backoff_factor * (2 ** attempt)
                print(f"⚠️ Серверная ошибка {resp.status_code}. Повтор через {wait:.1f} сек...")
                time.sleep(wait)
            else:
                resp.raise_for_status()
        except requests.RequestException as e:
            wait = backoff_factor * (2 ** attempt)
            print(f"⚠️ Ошибка запроса: {e}. Повтор через {wait:.1f} сек...")
            time.sleep(wait)
    raise Exception(f"Не удалось загрузить {url} после {max_retries} попыток")

def fetch_cached(url, cache_hours=24):
    cache_file = CACHE_DIR / get_cache_key(url)
    if cache_file.exists():
        mtime = cache_file.stat().st_mtime
        if time.time() - mtime < cache_hours * 3600:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return f.read()
    html = fetch_with_retry(url)
    with open(cache_file, 'w', encoding='utf-8') as f:
        f.write(html)
    time.sleep(1 + random.uniform(0, 0.5))
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
        for thread in threads[:10]:
            try:
                title_elem = thread.select_one(source['title_selector'])
                link_elem = thread.select_one(source['link_selector'])
                if not title_elem or not link_elem:
                    continue
                title = title_elem.get_text(strip=True)
                rel_link = link_elem['href']
                abs_link = urljoin(source['base_url'], rel_link)

                content_html = fetch_cached(abs_link, cache_hours=168)
                content_text = BeautifulSoup(content_html, 'html.parser').get_text()
                error_codes = extract_error_codes(content_text)

                brand = None
                model = None
                for b in KNOWN_BRANDS:
                    if b in title.lower():
                        brand = b.upper()
                        if b in BRAND_MODEL_MAP:
                            for m in BRAND_MODEL_MAP[b]:
                                if m.lower() in title.lower():
                                    model = m
                                    break
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
                        "model": model,
                        "symptoms": symptoms,
                        "error_codes": error_codes,
                        "source_url": abs_link,
                        "source": source['name'],
                        "date_added": time.strftime("%Y-%m-%d")
                    })
            except Exception as e:
                print(f"  Пропущена тема: {e}")
                continue
        return problems
    except Exception as e:
        print(f"❗ Ошибка при парсинге {source['name']}: {e}")
        return []

def load_existing():
    path = Path("db/problems.json")
    if path.exists():
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [p for p in data if isinstance(p, dict) and 'id' in p]
        except json.JSONDecodeError:
            print("⚠️ Битый JSON — сброшен.")
    return []

def save_problems(problems):
    problems = problems[:MAX_PROBLEMS]
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
    print(f"Всего записей: {len(final_list)}")
    save_problems(final_list)
    print("✅ Сохранено.")

if __name__ == '__main__':
    main()
