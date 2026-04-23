from fastapi import FastAPI, Request, Form, Cookie
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.background import BackgroundScheduler
import os
import sqlite3
from datetime import datetime

from .database import init_db, get_db
from .scraper import run_scrape, seed_confirmed_data

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

@app.on_event('startup')
def startup():
    init_db()
    db = get_db()
    count = db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
    db.close()
    if count == 0:
        seed_confirmed_data()
    scheduler.add_job(run_scrape, 'cron', hour=0, minute=0)
    scheduler.start()

@app.on_event('shutdown')
def shutdown():
    scheduler.shutdown()

@app.get('/', response_class=HTMLResponse)
def index(request: Request, region: str = '', distance: str = '', pref: str = ''):
    db = get_db()
    query = '''
        SELECT e.*, p.status, p.memo, p.finish_time, p.by_admin, p.id as progress_id
        FROM events e
        LEFT JOIN user_progress p ON e.id = p.event_id
        WHERE e.confirmed = 1
    '''
    params = []
    if region:
        query += ' AND e.region = ?'
        params.append(region)
    if distance:
        query += ' AND e.distance = ?'
        params.append(distance)
    if pref:
        query += ' AND e.prefecture = ?'
        params.append(pref)
    query += ' ORDER BY e.date ASC'
    events_raw = db.execute(query, params).fetchall()
    prefs = db.execute('SELECT DISTINCT prefecture, region FROM events ORDER BY region, prefecture').fetchall()

    today = datetime.now().strftime('%Y-%m-%d')

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
    return templates.TemplateResponse('index.html', {
        'request': request,
        'events': events,
        'prefs': prefs,
        'selected_region': region,
        'selected_distance': distance,
        'selected_pref': pref,
        'today': today,
        'gcal_url': gcal_url,
        'is_admin': is_admin(request),
    })

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
    admin = 1 if is_admin(request) else 0
    db = get_db()
    existing = db.execute('SELECT id, by_admin FROM user_progress WHERE event_id = ?', (event_id,)).fetchone()
    if existing:
        # 管理者は常に上書き。一般ユーザーは管理者が入力済みの場合はby_adminを維持
        new_by_admin = admin if admin else existing['by_admin']
        db.execute('''
            UPDATE user_progress SET status=?, memo=?, finish_time=?, by_admin=?, updated_at=datetime('now','localtime')
            WHERE event_id=?
        ''', (status, memo, finish_time, new_by_admin, event_id))
    else:
        db.execute('INSERT INTO user_progress (event_id, status, memo, finish_time, by_admin) VALUES (?, ?, ?, ?, ?)',
                   (event_id, status, memo, finish_time, admin))
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

@app.post('/scrape')
def manual_scrape(request: Request):
    if not is_admin(request):
        return JSONResponse({'error': '管理者のみ操作できます'}, status_code=403)
    saved = run_scrape()
    return JSONResponse({'message': f'{saved}件の新しい大会を取得しました'})
