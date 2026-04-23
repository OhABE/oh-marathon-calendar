import requests
from bs4 import BeautifulSoup
from datetime import datetime
import sqlite3
import os
import time
import re
import json
from urllib.parse import quote

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'marathon.db')

CHUGOKU_PREFS = {'鳥取': '31', '島根': '32', '岡山': '33', '広島': '34', '山口': '35'}
KYUSHU_PREFS  = {'福岡': '40', '佐賀': '41', '長崎': '42', '熊本': '43', '大分': '44', '宮崎': '45', '鹿児島': '46', '沖縄': '47'}
ALL_PREFS = {**CHUGOKU_PREFS, **KYUSHU_PREFS}

WHEELCHAIR_KEYWORDS = ['車いす', '車椅子', 'wheelchair', 'チェア', 'ウォーク', 'ウオーク', '歩こう']
TRAIL_KEYWORDS = ['トレイル', 'trail', 'Trail', 'TRAIL', '山岳', '縦走']
ULTRA_KEYWORDS = ['ウルトラ', 'ultra', 'Ultra', 'ULTRA']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'ja,en;q=0.9',
}

def is_excluded(name):
    return any(kw in name for kw in WHEELCHAIR_KEYWORDS)

def is_trail(name):
    return any(kw in name for kw in TRAIL_KEYWORDS)

def is_ultra(name):
    return any(kw in name for kw in ULTRA_KEYWORDS) or bool(re.search(r'[6-9]\d\s*km|[1-9]\d{2}\s*km', name, re.IGNORECASE))

def is_trail_or_ultra(name):
    return is_trail(name) or is_ultra(name)

def detect_distance(name):
    if is_trail(name):
        return 'トレイル'
    if is_ultra(name):
        return 'ウルトラ'
    if 'ハーフ' in name:
        return 'ハーフ'
    return 'フル'

def is_confirmed(ev):
    """必須項目が揃っていて要確認でないイベントのみ確定とする"""
    required = ['name', 'date', 'fee', 'time_limit']
    for field in required:
        val = ev.get(field, '')
        if not val or '要確認' in str(val) or val.strip() == '':
            return False
    return True

def parse_date(text):
    """日付文字列をYYYY-MM-DD形式に変換"""
    if not text:
        return ''
    text = text.strip()
    # 2026年4月27日 → 2026-04-27
    m = re.search(r'(\d{4})[年/\-](\d{1,2})[月/\-](\d{1,2})', text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # すでにYYYY-MM-DD形式
    if re.match(r'\d{4}-\d{2}-\d{2}', text):
        return text[:10]
    return text

def scrape_runnet_detail(detail_url):
    """RunNETの大会詳細ページから情報を取得"""
    info = {}
    try:
        res = requests.get(detail_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')

        # テーブルから情報を抽出
        for row in soup.select('tr'):
            cells = row.select('th, td')
            if len(cells) < 2:
                continue
            key = cells[0].get_text(strip=True)
            val = cells[1].get_text(strip=True)

            if re.search(r'参加料|参加費|エントリー料', key):
                info['fee'] = val
            elif re.search(r'制限時間', key):
                info['time_limit'] = val
            elif re.search(r'エントリー.*開始|受付.*開始', key):
                info['entry_start'] = parse_date(val)
            elif re.search(r'エントリー.*締切|受付.*締切|申込.*締切', key):
                info['entry_end'] = parse_date(val)
            elif re.search(r'会場|開催場所|スタート地点', key):
                if not info.get('venue'):
                    info['venue'] = val
            elif re.search(r'開催日|大会日|レース日', key):
                if not info.get('date'):
                    info['date'] = parse_date(val)

        # 参加費の整形
        if 'fee' in info:
            m = re.search(r'[\d,]+円', info['fee'])
            if m:
                info['fee'] = m.group(0)

    except Exception as e:
        print(f'[scraper] detail error {detail_url}: {e}')
    return info

def _scrape_runnet_links(search_url, pref_name, pref_code, region, name_filter=None):
    """RunNET検索URLから大会リストを取得して返す"""
    events = []
    try:
        res = requests.get(search_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        race_links = soup.select('a[href*="raceId="], a[href*="race_id="]')
        seen = set()
        for link in race_links:
            href = link.get('href', '')
            name = link.get_text(strip=True)
            if not name or len(name) < 3:
                continue
            if is_excluded(name):
                continue
            if href in seen:
                continue
            if name_filter and not name_filter(name):
                continue
            seen.add(href)
            detail_url = href if href.startswith('http') else 'https://runnet.jp' + href
            detail = scrape_runnet_detail(detail_url)
            time.sleep(1.5)
            ev = {
                'name': name,
                'date': detail.get('date', ''),
                'prefecture': pref_name,
                'region': region,
                'distance': detect_distance(name),
                'venue': detail.get('venue', ''),
                'entry_start': detail.get('entry_start', ''),
                'entry_end': detail.get('entry_end', ''),
                'fee': detail.get('fee', ''),
                'time_limit': detail.get('time_limit', ''),
                'url': detail_url,
                'entry_url': detail_url,
                'entry_site': 'ランネット',
                'source': 'runnet',
            }
            events.append(ev)
        time.sleep(2)
    except Exception as e:
        print(f'[scraper] search error {pref_name}: {e}')
    return events


def scrape_runnet():
    events = []
    for pref_name, pref_code in ALL_PREFS.items():
        region = '中国' if pref_name in CHUGOKU_PREFS else '九州'

        # フル・ハーフ
        for dist_id in ['1', '2']:
            url = (
                f'https://runnet.jp/entry/runtes/user/pc/RaceSearchZZSDetailAction.do'
                f'?command=search&prefectureIds={pref_code}&distanceIds={dist_id}&statusIds=1&statusIds=2'
            )
            events += _scrape_runnet_links(url, pref_name, pref_code, region)

        # ウルトラ・トレイル（名称でフィルタ）
        trail_url = (
            f'https://runnet.jp/entry/runtes/user/pc/RaceSearchZZSDetailAction.do'
            f'?command=search&prefectureIds={pref_code}&flgTrailTagClicked=1&statusIds=1&statusIds=2'
        )
        events += _scrape_runnet_links(trail_url, pref_name, pref_code, region, name_filter=is_trail_or_ultra)

    return events

def scrape_sportsentry():
    """スポーツエントリーから中国・九州エリアの大会を取得"""
    events = []
    pref_codes = {
        '鳥取': 31, '島根': 32, '岡山': 33, '広島': 34, '山口': 35,
        '福岡': 40, '佐賀': 41, '長崎': 42, '熊本': 43, '大分': 44,
        '宮崎': 45, '鹿児島': 46, '沖縄': 47,
    }
    for pref_name, pref_code in pref_codes.items():
        region = '中国' if pref_name in CHUGOKU_PREFS else '九州'
        try:
            url = f'https://www.sportsentry.ne.jp/search/result?pref_cd={pref_code}&genre_cd=1'
            res = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            for item in soup.select('.event-list-item, .searchResultList li, .event_list li'):
                try:
                    name_el = item.select_one('.event-name, .title, h3, h4')
                    date_el = item.select_one('.event-date, .date')
                    link_el = item.select_one('a')
                    if not name_el:
                        continue
                    name = name_el.get_text(strip=True)
                    if is_excluded(name):
                        continue
                    if not any(kw in name for kw in ['マラソン', 'ランニング', 'ラン', 'トレイル', 'trail', 'Trail', 'ウルトラ']):
                        continue
                    distance = detect_distance(name)
                    date_text = parse_date(date_el.get_text(strip=True)) if date_el else ''
                    href = link_el.get('href', '') if link_el else ''
                    entry_url = href if href.startswith('http') else 'https://www.sportsentry.ne.jp' + href
                    events.append({
                        'name': name, 'date': date_text,
                        'prefecture': pref_name, 'region': region,
                        'distance': distance, 'venue': '', 'entry_start': '',
                        'entry_end': '', 'fee': '', 'time_limit': '',
                        'url': entry_url, 'entry_url': entry_url,
                        'entry_site': 'スポーツエントリー', 'source': 'sportsentry',
                    })
                except Exception:
                    continue
            time.sleep(2)
        except Exception as e:
            print(f'[scraper] sportsentry error {pref_name}: {e}')
    return events

def save_events(events):
    conn = sqlite3.connect(DB_PATH)
    saved = 0
    for ev in events:
        if is_excluded(ev.get('name', '')):
            continue
        # 手動データに confirmed キーがあればそれを優先
        confirmed = ev.get('confirmed', 1 if is_confirmed(ev) else 0)
        existing = conn.execute(
            'SELECT id, confirmed FROM events WHERE name=? AND date=?',
            (ev['name'], ev['date'])
        ).fetchone()
        if existing:
            # 既存レコードを情報更新（確定度が上がった場合）
            if confirmed and not existing['confirmed']:
                conn.execute('''
                    UPDATE events SET fee=?, time_limit=?, venue=?, entry_start=?, entry_end=?,
                    entry_url=?, entry_site=?, confirmed=1, updated_at=datetime('now','localtime')
                    WHERE id=?
                ''', (ev.get('fee',''), ev.get('time_limit',''), ev.get('venue',''),
                      ev.get('entry_start',''), ev.get('entry_end',''),
                      ev.get('entry_url',''), ev.get('entry_site',''), existing['id']))
        else:
            conn.execute('''
                INSERT INTO events
                (name,date,prefecture,region,distance,venue,entry_start,entry_end,fee,time_limit,url,entry_url,entry_site,confirmed,source)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''', (
                ev.get('name',''), ev.get('date',''), ev.get('prefecture',''),
                ev.get('region',''), ev.get('distance',''), ev.get('venue',''),
                ev.get('entry_start',''), ev.get('entry_end',''),
                ev.get('fee',''), ev.get('time_limit',''),
                ev.get('url',''), ev.get('entry_url',''), ev.get('entry_site',''),
                confirmed, ev.get('source','')
            ))
            saved += 1
    conn.commit()
    conn.close()
    return saved

def seed_confirmed_data():
    confirmed_events = [
        # ── 2026年1月 ──
        {'name': 'いぶすき菜の花マラソン2026', 'date': '2026-01-11',
         'prefecture': '鹿児島', 'region': '九州', 'distance': 'フル',
         'venue': '指宿市陸上競技場周辺', 'entry_start': '', 'entry_end': '',
         'fee': '例年12,000円前後', 'time_limit': '8時間',
         'url': 'https://ibusuki-nanohana.com/',
         'entry_url': 'https://www.sportsentry.ne.jp/event/t/101465',
         'entry_site': 'スポーツエントリー', 'source': 'manual', 'confirmed': 1},
        {'name': 'ゆくはしシーサイドハーフマラソン2026', 'date': '2026-01-25',
         'prefecture': '福岡', 'region': '九州', 'distance': 'ハーフ',
         'venue': '行橋市（今川河川敷周辺）', 'entry_start': '', 'entry_end': '',
         'fee': '要確認', 'time_limit': '要確認',
         'url': 'https://www.yukuhashi-marathon.jp/',
         'entry_url': 'https://runnet.jp/cgi-bin/?id=381176',
         'entry_site': 'ランネット', 'source': 'manual', 'confirmed': 1},
        # ── 2026年2月 ──
        {'name': '北九州マラソン2026', 'date': '2026-02-15',
         'prefecture': '福岡', 'region': '九州', 'distance': 'フル',
         'venue': '北九州市（北九州市役所前スタート）', 'entry_start': '', 'entry_end': '',
         'fee': '14,500円', 'time_limit': '6時間',
         'url': 'https://kitakyushu-marathon.jp/',
         'entry_url': 'https://runnet.jp/cgi-bin/?id=379259',
         'entry_site': 'ランネット', 'source': 'manual', 'confirmed': 1},
        # ── 2026年3月 ──
        {'name': '鹿児島マラソン2026', 'date': '2026-03-01',
         'prefecture': '鹿児島', 'region': '九州', 'distance': 'フル',
         'venue': '鹿児島市', 'entry_start': '', 'entry_end': '',
         'fee': '14,000円', 'time_limit': '7時間',
         'url': 'https://www.kagoshima-marathon.jp/',
         'entry_url': 'https://runnet.jp/cgi-bin/?id=379578',
         'entry_site': 'ランネット', 'source': 'manual', 'confirmed': 1},
        {'name': '福岡小郡ハーフマラソン2026', 'date': '2026-03-08',
         'prefecture': '福岡', 'region': '九州', 'distance': 'ハーフ',
         'venue': '小郡市（陸上競技場周辺）', 'entry_start': '', 'entry_end': '',
         'fee': '要確認', 'time_limit': '2時間20分',
         'url': 'http://fukuoka-ogori-half.com/',
         'entry_url': 'https://runnet.jp/cgi-bin/?id=382353',
         'entry_site': 'ランネット', 'source': 'manual', 'confirmed': 1},
        {'name': 'さが桜マラソン2026', 'date': '2026-03-22',
         'prefecture': '佐賀', 'region': '九州', 'distance': 'フル',
         'venue': '佐賀市（佐賀城本丸歴史館周辺）', 'entry_start': '', 'entry_end': '',
         'fee': '14,500円', 'time_limit': '6時間30分',
         'url': 'https://sagasakura-marathon.jp/',
         'entry_url': 'https://runnet.jp/cgi-bin/?id=380754',
         'entry_site': 'ランネット', 'source': 'manual', 'confirmed': 1},
        # ── 2026年4月 ──
        {'name': 'えびの京町温泉マラソン2026', 'date': '2026-04-19',
         'prefecture': '宮崎', 'region': '九州', 'distance': 'ハーフ',
         'venue': 'えびの市グリーンパークえびの', 'entry_start': '', 'entry_end': '2026-02-20',
         'fee': '5,800円', 'time_limit': '要確認',
         'url': 'https://www.ebino-marathon.com/',
         'entry_url': 'https://www.sportsentry.ne.jp/event/t/103200',
         'entry_site': 'スポーツエントリー', 'source': 'manual', 'confirmed': 1},
        {'name': '佐伯番匠健康マラソン2026', 'date': '2026-04-27',
         'prefecture': '大分', 'region': '九州', 'distance': 'ハーフ',
         'venue': '佐伯市番匠川河川公園', 'entry_start': '', 'entry_end': '',
         'fee': '3,500円', 'time_limit': '3時間',
         'url': 'https://banzyo.wixsite.com/marason',
         'entry_url': 'https://runnet.jp/entry/runtes/smp/racedetail.do?raceId=376394',
         'entry_site': 'ランネット', 'source': 'manual', 'confirmed': 1},
        # ── 2026年6月 ──
        {'name': '第10回 JAL向津具ダブルマラソン', 'date': '2026-06-14',
         'prefecture': '山口', 'region': '中国', 'distance': 'フル',
         'venue': '山口県長門市（向津具半島）', 'entry_start': '', 'entry_end': '2026-04-01',
         'fee': '6,000円', 'time_limit': '10時間',
         'url': 'https://www.mukatsuku-w-marathon.com/',
         'entry_url': 'https://runnet.jp/entry/runtes/user/pc/competitionDetailAction.do?raceId=382981',
         'entry_site': 'ランネット', 'source': 'manual', 'confirmed': 1},
        # ── 2026年11月 ──
        {'name': '下関海響マラソン2026', 'date': '2026-11-01',
         'prefecture': '山口', 'region': '中国', 'distance': 'フル',
         'venue': '下関市（海峡ゆめタワー周辺）', 'entry_start': '2026-05-15', 'entry_end': '',
         'fee': '例年13,000円前後', 'time_limit': '6時間',
         'url': 'https://kaikyomarathon.jp/',
         'entry_url': 'https://runnet.jp/cgi-bin/?id=374294',
         'entry_site': 'ランネット', 'source': 'manual', 'confirmed': 1},
        {'name': '福岡マラソン2026', 'date': '2026-11-08',
         'prefecture': '福岡', 'region': '九州', 'distance': 'フル',
         'venue': '福岡市', 'entry_start': '2026-04-21', 'entry_end': '2026-05-20',
         'fee': '16,000円', 'time_limit': '7時間',
         'url': 'https://www.f-marathon.jp/',
         'entry_url': 'https://www.f-marathon.jp/runner/apply.php',
         'entry_site': '公式サイト', 'source': 'manual', 'confirmed': 1},
        {'name': 'おかやまマラソン2026', 'date': '2026-11-08',
         'prefecture': '岡山', 'region': '中国', 'distance': 'フル',
         'venue': '岡山市（シティライトスタジアム周辺）', 'entry_start': '', 'entry_end': '',
         'fee': '14,000円', 'time_limit': '6時間',
         'url': 'https://www.okayamamarathon.jp/',
         'entry_url': 'https://do.l-tike.com/app/dss/race/detail?acd=P6_3yl_D_hr',
         'entry_site': 'ローソンスポーツ', 'source': 'manual', 'confirmed': 1},
        # ── 2027年1月 ──
        {'name': 'いぶすき菜の花マラソン2027', 'date': '2027-01-10',
         'prefecture': '鹿児島', 'region': '九州', 'distance': 'フル',
         'venue': '指宿市陸上競技場周辺', 'entry_start': '2026-08-01', 'entry_end': '',
         'fee': '例年12,000円前後', 'time_limit': '8時間',
         'url': 'https://ibusuki-nanohana.com/',
         'entry_url': 'https://www.sportsentry.ne.jp/',
         'entry_site': 'スポーツエントリー', 'source': 'manual', 'confirmed': 1},
        # ── 2027年2月 ──
        {'name': '第75回別府大分毎日マラソン', 'date': '2027-02-07',
         'prefecture': '大分', 'region': '九州', 'distance': 'フル',
         'venue': '別府市（別府北浜スタート〜大分市）', 'entry_start': '', 'entry_end': '',
         'fee': '例年10,000円前後', 'time_limit': '4時間',
         'url': 'https://www.betsudai.com/',
         'entry_url': 'https://www.betsudai.com/',
         'entry_site': '公式サイト', 'source': 'manual', 'confirmed': 1},
        {'name': '熊本城マラソン2027', 'date': '2027-02-21',
         'prefecture': '熊本', 'region': '九州', 'distance': 'フル',
         'venue': '熊本市（熊本城・花畑広場周辺）', 'entry_start': '2026-08-01', 'entry_end': '2026-09-15',
         'fee': '13,750円', 'time_limit': '6時間',
         'url': 'https://kumamotojyo-marathon.jp/',
         'entry_url': 'https://kumamotojyo-marathon.jp/entry.php',
         'entry_site': '公式サイト', 'source': 'manual', 'confirmed': 1},
        # ── 2027年3月 ──
        {'name': '鹿児島マラソン2027', 'date': '2027-03-07',
         'prefecture': '鹿児島', 'region': '九州', 'distance': 'フル',
         'venue': '鹿児島市', 'entry_start': '', 'entry_end': '',
         'fee': '例年14,000円前後', 'time_limit': '7時間',
         'url': 'https://www.kagoshima-marathon.jp/',
         'entry_url': 'https://runnet.jp/',
         'entry_site': 'ランネット', 'source': 'manual', 'confirmed': 1},
        {'name': 'さが桜マラソン2027', 'date': '2027-03-21',
         'prefecture': '佐賀', 'region': '九州', 'distance': 'フル',
         'venue': '佐賀市（佐賀城本丸歴史館周辺）', 'entry_start': '', 'entry_end': '',
         'fee': '例年14,500円前後', 'time_limit': '6時間30分',
         'url': 'https://sagasakura-marathon.jp/',
         'entry_url': 'https://runnet.jp/',
         'entry_site': 'ランネット', 'source': 'manual', 'confirmed': 1},
    ]
    return save_events(confirmed_events)

def run_scrape():
    print(f'[scraper] 自動取得開始: {datetime.now()}')
    all_events = []
    all_events += scrape_runnet()
    all_events += scrape_sportsentry()
    saved = save_events(all_events)
    print(f'[scraper] 完了: {saved}件追加')
    return saved


# ── YouTube連携 ──────────────────────────────────────────────

YT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Accept-Language': 'ja,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

# 優先チャンネル: (チャンネル名に含まれるキーワード, 検索クエリに使うチャンネル名)
PRIORITY_CHANNELS = [
    ('アベ',        'Oh!アベチャンネル'),
    ('KITAKYUSHU', 'KITAKYUSHU WALKERER'),
    ('BOBO',       'BOBO JAPAN'),
    ('揚げや',     '走るから揚げや'),
]


def _yt_base_name(event_name):
    """大会名から年号(4桁)と冒頭の"第N回"を除去して基本名を返す"""
    name = re.sub(r'第\d+回\s*', '', event_name)
    return re.sub(r'\d{4}', '', name).strip()


def _title_matches(event_name, video_title):
    """動画タイトルが大会に一致するか判定（厳密）"""
    base = _yt_base_name(event_name)

    # 完全一致（最優先）
    if base in video_title:
        return True

    # 大会名の地域部分を取り出す（"マラソン"/"ハーフマラソン" 前の部分）
    for suffix in ['シーサイドハーフマラソン', 'ハーフマラソン', '健康マラソン', '温泉マラソン', 'ウルトラマラソン', 'トレイルラン', 'トレイル', 'マラソン']:
        if suffix in base:
            prefix = base.split(suffix)[0].strip()
            # 3文字以上の固有部分のみ採用（"福岡"だけでは広すぎる）
            if len(prefix) >= 3 and prefix in video_title:
                return True
            break

    return False


def _yt_parse_results(text):
    """YouTube検索ページのHTMLからvideoRenderer一覧を返す"""
    marker = 'var ytInitialData = '
    idx = text.find(marker)
    if idx == -1:
        return []
    try:
        data, _ = json.JSONDecoder().raw_decode(text[idx + len(marker):])
    except json.JSONDecodeError:
        return []
    sections = (
        data.get('contents', {})
            .get('twoColumnSearchResultsRenderer', {})
            .get('primaryContents', {})
            .get('sectionListRenderer', {})
            .get('contents', [])
    )
    results = []
    for section in sections:
        for item in section.get('itemSectionRenderer', {}).get('contents', []):
            vr = item.get('videoRenderer', {})
            if vr:
                results.append(vr)
    return results


def _yt_search(query, ch_keyword, event_name):
    """クエリでYouTube検索し、チャンネル名 + タイトルが一致する動画URLを返す"""
    url = f'https://www.youtube.com/results?search_query={quote(query)}&sp=CAI%3D'
    try:
        r = requests.get(url, headers=YT_HEADERS, timeout=15)
        for vr in _yt_parse_results(r.text):
            vid = vr.get('videoId', '')
            if not vid:
                continue
            title = ''.join(x.get('text', '') for x in vr.get('title', {}).get('runs', []))
            owner = vr.get('ownerText', vr.get('longBylineText', {}))
            ch = ''.join(x.get('text', '') for x in owner.get('runs', []))
            if ch_keyword and ch_keyword not in ch:
                continue
            if _title_matches(event_name, title):
                video_url = f'https://www.youtube.com/watch?v={vid}'
                print(f'[YouTube] "{event_name}" ← [{ch}] {title}')
                return video_url
    except Exception as e:
        print(f'[YouTube] search error "{event_name}": {e}')
    return None


def fetch_youtube_url(event_name):
    """優先チャンネル順に検索し、最初に見つかった動画URLを返す（なければNone）"""
    base = _yt_base_name(event_name)

    # 優先チャンネルを順番に試す
    for ch_key, ch_name in PRIORITY_CHANNELS:
        result = _yt_search(f'{ch_name} {base}', ch_key, event_name)
        if result:
            return result
        time.sleep(1.5)

    # フォールバック: チャンネル不問で検索（タイトル一致のみ）
    result = _yt_search(f'マラソン {base}', None, event_name)
    if not result:
        print(f'[YouTube] no match for "{event_name}"')
    return result


def update_youtube_links():
    """確定大会のうちlocked=0のみYouTube動画URLを自動更新"""
    print(f'[YouTube] 更新開始: {datetime.now()}')
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    events = conn.execute(
        'SELECT id, name FROM events WHERE confirmed=1 AND (youtube_locked IS NULL OR youtube_locked=0)'
    ).fetchall()
    updated = 0
    for ev in events:
        url = fetch_youtube_url(ev['name'])
        conn.execute('UPDATE events SET youtube_url=? WHERE id=?', (url, ev['id']))
        if url:
            updated += 1
        time.sleep(2)
    conn.commit()
    conn.close()
    print(f'[YouTube] 完了: {updated}件動画リンクを設定')
    return updated
