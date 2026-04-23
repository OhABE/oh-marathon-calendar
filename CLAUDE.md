# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run dev server (with auto-reload)
./run.sh
# or directly:
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Deploy target: Render.com (render.yaml defines build/start commands)
```

No test suite is configured. Manual testing via browser at `http://localhost:8000`.

## Architecture

**FastAPI web app** (`app/main.py`) — single-file server with:
- Jinja2 HTML templates (`templates/index.html`) + static assets (`static/`)
- SQLite database at `data/marathon.db` (persisted on Render's disk)
- APScheduler for daily cron jobs at midnight (scrape) and 00:30 (YouTube links)

**Data flow:**
1. On first startup, `seed_confirmed_data()` inserts ~15 hand-curated events (`scraper.py`)
2. Daily cron calls `run_scrape()` → scrapes RunNet + スポーツエントリー for Chugoku (中国) and Kyushu (九州) prefectures, half and full marathons only
3. `update_youtube_links()` searches YouTube for race recap videos via `ytInitialData` JSON embedded in search HTML (no API key required); results are locked if manually set by admin

**Database schema** (`database.py`):
- `events`: race data. `confirmed=1` means shown publicly. `source='manual'` for seeded data, `'runnet'`/`'sportsentry'` for scraped. `youtube_locked=1` prevents auto-overwrite of manually set URLs.
- `user_progress`: per-event status/memo/finish_time for the single user. `by_admin=1` marks admin-entered records.

**Admin system:** Cookie-based PIN auth (`ADMIN_PIN` env var, default `0427`). Admin can add events manually, trigger scrapes, set YouTube URLs, and update progress. No user accounts — single-user personal tool.

**Entry status logic** (`get_entry_status` in `main.py`): computed at query time from `entry_start`/`entry_end`/`date` vs. today → `open | upcoming | closed | finished | unknown`.

## Key details

- Scraper filters out wheelchair/walk events via `WHEELCHAIR_KEYWORDS`
- `is_confirmed()` requires `name`, `date`, `fee`, `time_limit` all non-empty and not containing `要確認`
- YouTube search parses `ytInitialData` from raw HTML; priority channels are defined in `PRIORITY_CHANNELS` (アベ, KITAKYUSHU WALKERER, BOBO JAPAN, 走るから揚げや)
- DB migrations for new columns are done inline in `init_db()` with try/except ALTER TABLE
- `ADMIN_PIN` default `0427` = 佐伯番匠の日 (the owner's local race)
