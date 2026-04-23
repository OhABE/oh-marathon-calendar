from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.background import BackgroundScheduler
import os
import uuid
import sqlite3
from datetime import datetime

from .database import init_db, get_db
from .scraper import run_scrape, seed_sample_data

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

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
        seed_sample_data()
    scheduler.add_job(run_scrape, 'cron', hour=3, minute=0)
    scheduler.start()

@app.on_event('shutdown')
def shutdown():
    scheduler.shutdown()

@app.get('/', response_class=HTMLResponse)
def index(request: Request, region: str = '', distance: str = '', pref: str = ''):
    db = get_db()
    query = '''
        SELECT e.*, p.status, p.memo, p.finish_time, p.id as progress_id
        FROM events e
        LEFT JOIN user_progress p ON e.id = p.event_id
        WHERE 1=1
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

    events = []
    for ev in events_raw:
        ev_dict = dict(ev)
        ev_dict['entry_status'] = get_entry_status(
            ev_dict.get('entry_start', ''),
            ev_dict.get('entry_end', ''),
            ev_dict.get('date', ''),
            today
        )
        photos = db.execute('SELECT * FROM event_photos WHERE event_id = ? ORDER BY uploaded_at DESC', (ev_dict['id'],)).fetchall()
        ev_dict['photos'] = [dict(p) for p in photos]
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
    })

@app.post('/progress/{event_id}')
def update_progress(event_id: int, status: str = Form(''), memo: str = Form(''), finish_time: str = Form('')):
    db = get_db()
    existing = db.execute('SELECT id FROM user_progress WHERE event_id = ?', (event_id,)).fetchone()
    if existing:
        db.execute('''
            UPDATE user_progress SET status=?, memo=?, finish_time=?, updated_at=datetime('now','localtime')
            WHERE event_id=?
        ''', (status, memo, finish_time, event_id))
    else:
        db.execute('INSERT INTO user_progress (event_id, status, memo, finish_time) VALUES (?, ?, ?, ?)',
                   (event_id, status, memo, finish_time))
    db.commit()
    db.close()
    return RedirectResponse('/', status_code=303)

@app.post('/photos/upload/{event_id}')
async def upload_photo(event_id: int, file: UploadFile = File(...), caption: str = Form('')):
    ext = os.path.splitext(file.filename or '')[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return JSONResponse({'error': '画像ファイル（JPG/PNG/GIF）のみアップロードできます'}, status_code=400)
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        return JSONResponse({'error': 'ファイルサイズは5MB以内にしてください'}, status_code=400)
    filename = f'{event_id}_{uuid.uuid4().hex}{ext}'
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, 'wb') as f:
        f.write(content)
    db = get_db()
    db.execute('INSERT INTO event_photos (event_id, filename, caption) VALUES (?, ?, ?)',
               (event_id, filename, caption))
    db.commit()
    db.close()
    return RedirectResponse('/', status_code=303)

@app.post('/photos/delete/{photo_id}')
def delete_photo(photo_id: int):
    db = get_db()
    photo = db.execute('SELECT filename FROM event_photos WHERE id = ?', (photo_id,)).fetchone()
    if photo:
        filepath = os.path.join(UPLOAD_DIR, photo['filename'])
        if os.path.exists(filepath):
            os.remove(filepath)
        db.execute('DELETE FROM event_photos WHERE id = ?', (photo_id,))
        db.commit()
    db.close()
    return RedirectResponse('/', status_code=303)

@app.post('/events/add')
def add_event(
    name: str = Form(...), date: str = Form(...), prefecture: str = Form(...),
    region: str = Form(...), distance: str = Form(...), venue: str = Form(''),
    entry_start: str = Form(''), entry_end: str = Form(''),
    fee: str = Form(''), time_limit: str = Form(''), url: str = Form(''),
    entry_url: str = Form(''), entry_site: str = Form('')
):
    db = get_db()
    db.execute('''
        INSERT INTO events (name, date, prefecture, region, distance, venue, entry_start, entry_end, fee, time_limit, url, entry_url, entry_site, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual')
    ''', (name, date, prefecture, region, distance, venue, entry_start, entry_end, fee, time_limit, url, entry_url, entry_site))
    db.commit()
    db.close()
    return RedirectResponse('/', status_code=303)

@app.post('/scrape')
def manual_scrape():
    saved = run_scrape()
    return JSONResponse({'message': f'{saved}件の新しい大会を取得しました'})
