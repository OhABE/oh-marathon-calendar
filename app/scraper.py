import requests
from bs4 import BeautifulSoup
from datetime import datetime
import sqlite3
import os
import time

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'marathon.db')

CHUGOKU_PREFS = {'鳥取': '31', '島根': '32', '岡山': '33', '広島': '34', '山口': '35'}
KYUSHU_PREFS = {'福岡': '40', '佐賀': '41', '長崎': '42', '熊本': '43', '大分': '44', '宮崎': '45', '鹿児島': '46', '沖縄': '47'}
ALL_PREFS = {**CHUGOKU_PREFS, **KYUSHU_PREFS}

WHEELCHAIR_KEYWORDS = ['車いす', '車椅子', 'wheelchair', 'チェア']

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}

def is_wheelchair_event(name):
    return any(kw in name for kw in WHEELCHAIR_KEYWORDS)

def scrape_runnet():
    events = []
    for pref_name, pref_code in ALL_PREFS.items():
        region = '中国' if pref_name in CHUGOKU_PREFS else '九州'
        for distance_label, distance_code in [('フル', '1'), ('ハーフ', '2')]:
            url = f'https://runnet.jp/race/search?searchPref={pref_code}&searchDistanceFrom={distance_code}'
            try:
                res = requests.get(url, headers=HEADERS, timeout=10)
                soup = BeautifulSoup(res.text, 'html.parser')
                race_items = soup.select('.raceList__item, .race-item, li.race')
                for item in race_items:
                    try:
                        name_el = item.select_one('.raceList__title, .race-title, h3')
                        date_el = item.select_one('.raceList__date, .race-date, .date')
                        link_el = item.select_one('a')
                        if not name_el:
                            continue
                        name = name_el.get_text(strip=True)
                        if is_wheelchair_event(name):
                            continue
                        date_text = date_el.get_text(strip=True) if date_el else ''
                        race_url = 'https://runnet.jp' + link_el['href'] if link_el and link_el.get('href', '').startswith('/') else (link_el['href'] if link_el else '')
                        events.append({
                            'name': name, 'date': date_text,
                            'prefecture': pref_name, 'region': region,
                            'distance': distance_label, 'url': race_url,
                            'entry_url': race_url, 'entry_site': 'ランネット',
                            'source': 'runnet'
                        })
                    except Exception:
                        continue
                time.sleep(1)
            except Exception as e:
                print(f'[scraper] runnet error {pref_name}: {e}')
    return events

def save_events(events):
    conn = sqlite3.connect(DB_PATH)
    saved = 0
    for ev in events:
        if is_wheelchair_event(ev.get('name', '')):
            continue
        existing = conn.execute('SELECT id FROM events WHERE name=? AND date=?', (ev['name'], ev['date'])).fetchone()
        if not existing:
            conn.execute('''
                INSERT INTO events (name, date, prefecture, region, distance, venue, entry_start, entry_end, fee, time_limit, url, entry_url, entry_site, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                ev.get('name', ''), ev.get('date', ''), ev.get('prefecture', ''),
                ev.get('region', ''), ev.get('distance', ''), ev.get('venue', ''),
                ev.get('entry_start', ''), ev.get('entry_end', ''),
                ev.get('fee', ''), ev.get('time_limit', ''),
                ev.get('url', ''), ev.get('entry_url', ''), ev.get('entry_site', ''),
                ev.get('source', '')
            ))
            saved += 1
    conn.commit()
    conn.close()
    return saved

def seed_sample_data():
    sample_events = [
        {
            'name': '佐伯番匠健康マラソン', 'date': '2026-04-27',
            'prefecture': '大分', 'region': '九州', 'distance': 'ハーフ',
            'venue': '佐伯市番匠川河川公園', 'entry_start': '',
            'entry_end': '', 'fee': '3,500円', 'time_limit': '要確認',
            'url': 'https://banzyo.wixsite.com/marason',
            'entry_url': 'https://runnet.jp/entry/runtes/smp/racedetail.do?raceId=376394',
            'entry_site': 'ランネット', 'source': 'manual'
        },
        {
            'name': '福岡マラソン2026', 'date': '2026-11-08',
            'prefecture': '福岡', 'region': '九州', 'distance': 'フル',
            'venue': '福岡市', 'entry_start': '2026-04-21',
            'entry_end': '2026-05-20', 'fee': '16,000円', 'time_limit': '7時間',
            'url': 'https://www.f-marathon.jp/',
            'entry_url': 'https://www.f-marathon.jp/runner/apply.php',
            'entry_site': 'ランネット', 'source': 'manual'
        },
        {
            'name': '下関海響マラソン', 'date': '2026-11-01',
            'prefecture': '山口', 'region': '中国', 'distance': 'フル',
            'venue': '下関市', 'entry_start': '2026-05-01',
            'entry_end': '2026-07-15', 'fee': '要確認', 'time_limit': '要確認',
            'url': '', 'entry_url': 'https://runnet.jp', 'entry_site': 'ランネット', 'source': 'manual'
        },
        {
            'name': '別府大分毎日マラソン', 'date': '2027-02-07',
            'prefecture': '大分', 'region': '九州', 'distance': 'フル',
            'venue': '大分市', 'entry_start': '2026-09-01',
            'entry_end': '2026-10-31', 'fee': '要確認', 'time_limit': '要確認',
            'url': '', 'entry_url': 'https://www.sportsentry.ne.jp', 'entry_site': 'スポーツエントリー', 'source': 'manual'
        },
        {
            'name': '熊本城マラソン2027', 'date': '2027-02-21',
            'prefecture': '熊本', 'region': '九州', 'distance': 'フル',
            'venue': '熊本市', 'entry_start': '2026-08-01',
            'entry_end': '2026-09-30', 'fee': '要確認', 'time_limit': '要確認',
            'url': '', 'entry_url': 'https://runnet.jp', 'entry_site': 'ランネット', 'source': 'manual'
        },
        {
            'name': '鹿児島マラソン2027', 'date': '2027-03-07',
            'prefecture': '鹿児島', 'region': '九州', 'distance': 'フル',
            'venue': '鹿児島市', 'entry_start': '2026-09-01',
            'entry_end': '2026-10-31', 'fee': '要確認', 'time_limit': '要確認',
            'url': '', 'entry_url': 'https://www.sportsentry.ne.jp', 'entry_site': 'スポーツエントリー', 'source': 'manual'
        },
        {
            'name': '岡山マラソン2026', 'date': '2026-11-22',
            'prefecture': '岡山', 'region': '中国', 'distance': 'フル',
            'venue': '岡山市', 'entry_start': '2026-05-15',
            'entry_end': '2026-07-20', 'fee': '要確認', 'time_limit': '要確認',
            'url': '', 'entry_url': 'https://runnet.jp', 'entry_site': 'ランネット', 'source': 'manual'
        },
    ]
    return save_events(sample_events)

def run_scrape():
    print(f'[scraper] 開始: {datetime.now()}')
    events = scrape_runnet()
    saved = save_events(events)
    print(f'[scraper] 完了: {saved}件追加')
    return saved
