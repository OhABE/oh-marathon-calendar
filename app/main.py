from fastapi import FastAPI, Request, Form, Cookie
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.background import BackgroundScheduler
import os
import re
import sqlite3
import uuid
from collections import defaultdict
from datetime import datetime

from .database import init_db, get_db
from .scraper import run_scrape, seed_confirmed_data, update_youtube_links

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
ADMIN_PIN = os.environ.get('ADMIN_PIN', '0427')  # デフォルトは佐伯番匠の日

def is_admin(request: Request) -> bool:
    return request.cookies.get('admin_token') == ADMIN_PIN

app = FastAPI(title='Oh!マラソンカレンダー')
app.mount('/static', StaticFiles(directory=os.path.join(BASE_DIR, 'static')), name='static')
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, 'templates'))

scheduler = BackgroundScheduler()

def get_entry_status(entry_start, entry_end, event_date, today):
    if event_date and event_date < today:
        return 'finished'
    if entry_end and entry_end < today:
        return 'closed'
    if entry_start and entry_end and entry_start <= today <= entry_end:
        return 'open'
    if entry_start and today < entry_start:
        return 'upcoming'
    return 'unknown'

def cleanup_old_editions():
    """次回大会が登録済みの場合、前回大会（過去日程）を自動削除する"""
    db = get_db()
    today = datetime.now().strftime('%Y-%m-%d')
    events = db.execute(
        'SELECT id, name, prefecture, distance, date FROM events WHERE confirmed=1'
    ).fetchall()

    def base_name(name):
        # 年号(2024〜2029)・回数表記を除去して大会名を正規化
        name = re.sub(r'[（(（]?\s*\'?\s*20[2-9]\d\s*[）)）]?', '', name)
        name = re.sub(r'第\s*\d+\s*回', '', name)
        return name.strip()

    groups = defaultdict(list)
    for ev in events:
        key = (ev['prefecture'], ev['distance'], base_name(ev['name']))
        groups[key].append({'id': ev['id'], 'date': ev['date']})

    deleted = 0
    for evs in groups.values():
        if len(evs) <= 1:
            continue
        future = [e for e in evs if e['date'] >= today]
        past   = [e for e in evs if e['date'] <  today]
        if future and past:
            for old in past:
                db.execute('DELETE FROM user_progress WHERE event_id = ?', (old['id'],))
                db.execute('DELETE FROM events WHERE id = ?', (old['id'],))
                deleted += 1

    db.commit()
    db.close()
    print(f'[cleanup] 旧大会 {deleted} 件を削除しました')
    return deleted

@app.on_event('startup')
def startup():
    init_db()
    db = get_db()
    count = db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
    db.close()
    if count == 0:
        seed_confirmed_data()
    scheduler.add_job(run_scrape,          'cron', hour=0, minute=0)
    scheduler.add_job(cleanup_old_editions,'cron', hour=0, minute=10)
    scheduler.add_job(update_youtube_links,'cron', hour=0, minute=30)
    scheduler.add_job(update_youtube_links, 'date', run_date=datetime.now())
    scheduler.start()

@app.on_event('shutdown')
def shutdown():
    scheduler.shutdown()

@app.get('/', response_class=HTMLResponse)
def index(request: Request, region: str = '', distance: str = '', pref: str = ''):
    # 訪問者IDの取得（管理者は常に'admin'）
    if is_admin(request):
        visitor_id = 'admin'
        new_visitor_id = None
    else:
        visitor_id = request.cookies.get('visitor_id')
        if not visitor_id:
            visitor_id = str(uuid.uuid4())
            new_visitor_id = visitor_id
        else:
            new_visitor_id = None

    db = get_db()
    today = datetime.now().strftime('%Y-%m-%d')

    # 訪問者ログを記録（管理者は除外）
    if visitor_id != 'admin':
        try:
            db.execute('INSERT OR IGNORE INTO visitor_log (date, visitor_id) VALUES (?, ?)', (today, visitor_id))
            db.commit()
        except Exception:
            pass
    total_visitors = db.execute('SELECT COUNT(*) FROM visitor_log').fetchone()[0]
    today_visitors = db.execute('SELECT COUNT(*) FROM visitor_log WHERE date = ?', (today,)).fetchone()[0]

    query = '''
        SELECT e.*,
            ap.status as admin_status, ap.finish_time as admin_finish_time,
            vp.status as visitor_status, vp.memo as visitor_memo,
            vp.finish_time as visitor_finish_time, vp.id as progress_id
        FROM events e
        LEFT JOIN user_progress ap ON e.id = ap.event_id AND ap.visitor_id = 'admin'
        LEFT JOIN user_progress vp ON e.id = vp.event_id AND vp.visitor_id = ?
        WHERE e.confirmed = 1
        AND e.date >= date('now', '-1 year', 'localtime')
    '''
    params = [visitor_id]
    if region:
        query += ' AND e.region = ?'
        params.append(region)
    if distance:
        if distance == 'その他':
            query += " AND e.distance NOT IN ('フル', 'ハーフ')"
        else:
            query += ' AND e.distance = ?'
            params.append(distance)
    if pref:
        query += ' AND e.prefecture = ?'
        params.append(pref)
    query += ' ORDER BY e.date ASC'
    events_raw = db.execute(query, params).fetchall()
    prefs = db.execute('SELECT DISTINCT prefecture, region FROM events ORDER BY region, prefecture').fetchall()

    def gcal_url(ev):
        date = (ev.get('date') or '').replace('-', '')
        if not date:
            return '#'
        name = ev.get('name', '')
        loc = ev.get('venue') or ev.get('prefecture') or ''
        details = f"距離: {ev.get('distance','')} / 参加費: {ev.get('fee','')} / 制限時間: {ev.get('time_limit','')}"
        from urllib.parse import quote
        return (
            f"https://calendar.google.com/calendar/render?action=TEMPLATE"
            f"&text={quote(name)}"
            f"&dates={date}/{date}"
            f"&location={quote(loc)}"
            f"&details={quote(details)}"
        )

    events = []
    for ev in events_raw:
        ev_dict = dict(ev)
        ev_dict['entry_status'] = get_entry_status(
            ev_dict.get('entry_start', ''),
            ev_dict.get('entry_end', ''),
            ev_dict.get('date', ''),
            today
        )
        events.append(ev_dict)

    db.close()
    response = templates.TemplateResponse('index.html', {
        'request': request,
        'events': events,
        'prefs': prefs,
        'selected_region': region,
        'selected_distance': distance,
        'selected_pref': pref,
        'today': today,
        'gcal_url': gcal_url,
        'is_admin': is_admin(request),
        'total_visitors': total_visitors,
        'today_visitors': today_visitors,
    })
    if new_visitor_id:
        response.set_cookie('visitor_id', new_visitor_id, max_age=60*60*24*365*10, httponly=True)
    return response

def make_ical(events, title='Oh!マラソンカレンダー'):
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//Oh!マラソンカレンダー//JP',
        f'X-WR-CALNAME:{title}',
        'X-WR-TIMEZONE:Asia/Tokyo',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
    ]
    for ev in events:
        date = ev['date'].replace('-', '') if ev.get('date') else ''
        if not date:
            continue
        uid = f"marathon-{ev['id']}@oh-marathon-calendar"
        summary = ev['name']
        location = ev.get('venue') or ev.get('prefecture') or ''
        desc_parts = []
        if ev.get('distance'):   desc_parts.append(f"距離: {ev['distance']}")
        if ev.get('fee'):        desc_parts.append(f"参加費: {ev['fee']}")
        if ev.get('time_limit'): desc_parts.append(f"制限時間: {ev['time_limit']}")
        if ev.get('entry_end'):  desc_parts.append(f"エントリー締切: {ev['entry_end']}")
        if ev.get('url'):        desc_parts.append(f"公式サイト: {ev['url']}")
        description = '\\n'.join(desc_parts)
        now = datetime.now().strftime('%Y%m%dT%H%M%SZ')
        lines += [
            'BEGIN:VEVENT',
            f'UID:{uid}',
            f'DTSTAMP:{now}',
            f'DTSTART;VALUE=DATE:{date}',
            f'DTEND;VALUE=DATE:{date}',
            f'SUMMARY:{summary}',
            f'LOCATION:{location}',
            f'DESCRIPTION:{description}',
            'END:VEVENT',
        ]
    lines.append('END:VCALENDAR')
    return '\r\n'.join(lines)

@app.get('/calendar.ics')
def calendar_ics():
    """全確定大会のiCalフィード"""
    db = get_db()
    events = [dict(r) for r in db.execute(
        'SELECT * FROM events WHERE confirmed=1 ORDER BY date ASC'
    ).fetchall()]
    db.close()
    content = make_ical(events, 'Oh!マラソンカレンダー（全大会）')
    return Response(content=content, media_type='text/calendar; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename=marathon.ics'})

@app.get('/my-calendar.ics')
def my_calendar_ics():
    """参加予定・エントリー済みの大会のみのiCalフィード"""
    db = get_db()
    events = [dict(r) for r in db.execute('''
        SELECT e.* FROM events e
        JOIN user_progress p ON e.id = p.event_id
        WHERE e.confirmed=1 AND p.status IN ('entered','planning','running','finished')
        ORDER BY e.date ASC
    ''').fetchall()]
    db.close()
    content = make_ical(events, 'Oh!マイマラソン（参加予定）')
    return Response(content=content, media_type='text/calendar; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename=my-marathon.ics'})

@app.post('/progress/{event_id}')
def update_progress(request: Request, event_id: int, status: str = Form(''), memo: str = Form(''), finish_time: str = Form('')):
    if is_admin(request):
        visitor_id = 'admin'
        by_admin = 1
    else:
        visitor_id = request.cookies.get('visitor_id')
        if not visitor_id:
            return RedirectResponse('/', status_code=303)
        by_admin = 0
    db = get_db()
    existing = db.execute('SELECT id FROM user_progress WHERE event_id = ? AND visitor_id = ?', (event_id, visitor_id)).fetchone()
    if existing:
        db.execute('''
            UPDATE user_progress SET status=?, memo=?, finish_time=?, updated_at=datetime('now','localtime')
            WHERE event_id=? AND visitor_id=?
        ''', (status, memo, finish_time, event_id, visitor_id))
    else:
        db.execute('INSERT INTO user_progress (event_id, status, memo, finish_time, by_admin, visitor_id) VALUES (?, ?, ?, ?, ?, ?)',
                   (event_id, status, memo, finish_time, by_admin, visitor_id))
    db.commit()
    db.close()
    return RedirectResponse('/', status_code=303)


@app.post('/events/add')
def add_event(
    request: Request,
    name: str = Form(...), date: str = Form(...), prefecture: str = Form(...),
    region: str = Form(...), distance: str = Form(...), venue: str = Form(''),
    entry_start: str = Form(''), entry_end: str = Form(''),
    fee: str = Form(''), time_limit: str = Form(''), url: str = Form(''),
    entry_url: str = Form(''), entry_site: str = Form('')
):
    if not is_admin(request):
        return RedirectResponse('/', status_code=303)
    db = get_db()
    db.execute('''
        INSERT INTO events (name, date, prefecture, region, distance, venue, entry_start, entry_end, fee, time_limit, url, entry_url, entry_site, confirmed, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'manual')
    ''', (name, date, prefecture, region, distance, venue, entry_start, entry_end, fee, time_limit, url, entry_url, entry_site))
    db.commit()
    db.close()
    return RedirectResponse('/', status_code=303)

@app.post('/admin/login')
def admin_login(pin: str = Form(...)):
    if pin == ADMIN_PIN:
        res = RedirectResponse('/', status_code=303)
        res.set_cookie('admin_token', ADMIN_PIN, max_age=60*60*24*30, httponly=True)
        return res
    return RedirectResponse('/?error=pin', status_code=303)

@app.post('/admin/logout')
def admin_logout():
    res = RedirectResponse('/', status_code=303)
    res.delete_cookie('admin_token')
    return res

@app.post('/admin/events/{event_id}/youtube')
def set_youtube_url(request: Request, event_id: int, youtube_url: str = Form('')):
    if not is_admin(request):
        return RedirectResponse('/', status_code=303)
    db = get_db()
    if youtube_url.strip():
        # URLが入力された → 保存してロック（自動更新対象外）
        db.execute(
            'UPDATE events SET youtube_url=?, youtube_locked=1 WHERE id=?',
            (youtube_url.strip(), event_id)
        )
    else:
        # 空欄 → クリアしてアンロック（次回自動更新で再検索）
        db.execute(
            'UPDATE events SET youtube_url=NULL, youtube_locked=0 WHERE id=?',
            (event_id,)
        )
    db.commit()
    db.close()
    return RedirectResponse('/', status_code=303)


@app.post('/admin/events/{event_id}/edit')
def edit_event(
    request: Request,
    event_id: int,
    name: str = Form(...), date: str = Form(...), prefecture: str = Form(...),
    region: str = Form(...), distance: str = Form(...), venue: str = Form(''),
    entry_start: str = Form(''), entry_end: str = Form(''),
    fee: str = Form(''), time_limit: str = Form(''), url: str = Form(''),
    entry_url: str = Form(''), entry_site: str = Form(''),
    confirmed: str = Form('1')
):
    if not is_admin(request):
        return RedirectResponse('/', status_code=303)
    db = get_db()
    db.execute('''
        UPDATE events SET name=?, date=?, prefecture=?, region=?, distance=?, venue=?,
        entry_start=?, entry_end=?, fee=?, time_limit=?, url=?, entry_url=?, entry_site=?,
        confirmed=?
        WHERE id=?
    ''', (name, date, prefecture, region, distance, venue,
          entry_start or None, entry_end or None, fee, time_limit, url, entry_url, entry_site,
          1 if confirmed == '1' else 0,
          event_id))
    db.commit()
    db.close()
    return RedirectResponse('/', status_code=303)

@app.post('/admin/events/{event_id}/delete')
def delete_event(request: Request, event_id: int):
    if not is_admin(request):
        return RedirectResponse('/', status_code=303)
    db = get_db()
    db.execute('DELETE FROM user_progress WHERE event_id = ?', (event_id,))
    db.execute('DELETE FROM events WHERE id = ?', (event_id,))
    db.commit()
    db.close()
    return RedirectResponse('/', status_code=303)

@app.post('/scrape')
def manual_scrape(request: Request):
    if not is_admin(request):
        return JSONResponse({'error': '管理者のみ操作できます'}, status_code=403)
    saved = run_scrape()
    return JSONResponse({'message': f'{saved}件の新しい大会を取得しました'})
