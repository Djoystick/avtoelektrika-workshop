import os
import json
import re
import requests
from bs4 import BeautifulSoup

# Источник: последние темы drive2.ru (раздел "Электрооборудование")
URL = "https://drive2.ru/forums/elektrooborudovanie.107/"

def extract_problems():
    resp = requests.get(URL, headers={'User-Agent': 'Mozilla/5.0'})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')
    threads = soup.select('div.structItem--thread')

    problems = []
    for t in threads[:10]:  # последние 10 тем
        title_elem = t.select_one('div.structItem-title a')
        if not title_elem:
            continue
        title = title_elem.get_text(strip=True)
        link = 'https://drive2.ru' + title_elem['href']

        # Фильтр: только темы про типичные симптомы
        symptom_keywords = ['не заводится', 'check engine', 'утечка', 'нет зарядки', 'троит', 'стучит']
        symptoms = []
        for k in symptom_keywords:
            if k in title.lower():
                symptoms.append(k)

        if not symptoms:
            continue

        # Определяем марку по названию (очень упрощённо)
        brand = None
        known_brands = ['ваз', 'лада', 'toyota', 'bmw', 'audi', 'ford', 'opel', 'renault', 'kia', 'hyundai']
        for b in known_brands:
            if b in title.lower():
                brand = b.upper()
                break

        problems.append({
            "id": link,
            "title": title,
            "brand": brand,
            "symptoms": symptoms,
            "error_codes": [],  # можно расширить парсингом текста темы
            "source_url": link,
            "date_added": "2025-11-29"
        })
    return problems

def load_existing():
    path = os.path.join('_data', 'problems.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_problems(all_problems):
    # Удалить дубли по id
    seen = set()
    unique = []
    for p in all_problems:
        if p['id'] not in seen:
            unique.append(p)
            seen.add(p['id'])
    
    with open('_data/problems.json', 'w', encoding='utf-8') as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)

    # Генерация JS-файла
    with open('data/problems.js', 'w', encoding='utf-8') as f:
        json_str = json.dumps(unique, ensure_ascii=False, indent=2)
        f.write(f'window.problems = {json_str};\n')

if __name__ == '__main__':
    os.makedirs('_data', exist_ok=True)
    os.makedirs('data', exist_ok=True)
    
    existing = load_existing()
    new = extract_problems()
    
    # Объединить (новые в начало)
    combined = new + [p for p in existing if p['id'] not in {n['id'] for n in new}]
    
    save_problems(combined)
    print(f"Добавлено/обновлено. Всего решений: {len(combined)}")
