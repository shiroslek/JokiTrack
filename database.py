"""
Database layer — PostgreSQL jika DATABASE_URL tersedia, fallback ke SQLite.
"""
import os
import sqlite3
from datetime import datetime
import pytz

WITA = pytz.timezone('Asia/Makassar')

def now_wita():
    return datetime.now(tz=WITA).replace(tzinfo=None)

_DB_URL = os.environ.get('DATABASE_URL', '')
if _DB_URL.startswith('postgres://'):
    _DB_URL = _DB_URL.replace('postgres://', 'postgresql://', 1)

USE_PG  = bool(_DB_URL)
DB_PATH = os.environ.get('DB_PATH', 'joki_tracker.db')

if USE_PG:
    import psycopg2
    import psycopg2.extras

PH = '%s' if USE_PG else '?'

_ID_COL = 'id SERIAL PRIMARY KEY' if USE_PG else 'id INTEGER PRIMARY KEY AUTOINCREMENT'

_CREATE_SQL = f"""
    CREATE TABLE IF NOT EXISTS jobs (
        {_ID_COL},
        hunter_name       TEXT    NOT NULL,
        group_name        TEXT    NOT NULL,
        job_desc          TEXT    NOT NULL,
        fee               INTEGER NOT NULL,
        deadline          TEXT    NOT NULL,
        status            TEXT    NOT NULL DEFAULT 'on_proses',
        revision_deadline TEXT,
        created_at        TEXT    NOT NULL,
        done_at           TEXT,
        is_archived       INTEGER NOT NULL DEFAULT 0
    )
"""


def _get_conn():
    if USE_PG:
        return psycopg2.connect(_DB_URL)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _cursor(conn):
    if USE_PG:
        return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    return conn.cursor()


def init_db():
    conn = _get_conn()
    try:
        cur = _cursor(conn)
        cur.execute(_CREATE_SQL)
        conn.commit()
    finally:
        conn.close()


def add_job(hunter_name, group_name, job_desc, fee, deadline) -> int:
    conn = _get_conn()
    try:
        cur = _cursor(conn)
        now = now_wita().strftime('%d/%m/%Y %H:%M')
        if USE_PG:
            cur.execute(
                """INSERT INTO jobs
                   (hunter_name, group_name, job_desc, fee, deadline, status, created_at)
                   VALUES (%s,%s,%s,%s,%s,'on_proses',%s) RETURNING id""",
                (hunter_name, group_name, job_desc, fee, deadline, now)
            )
            job_id = cur.fetchone()['id']
        else:
            cur.execute(
                """INSERT INTO jobs
                   (hunter_name, group_name, job_desc, fee, deadline, status, created_at)
                   VALUES (?,?,?,?,?,'on_proses',?)""",
                (hunter_name, group_name, job_desc, fee, deadline, now)
            )
            job_id = cur.lastrowid
        conn.commit()
        return job_id
    finally:
        conn.close()


def get_active_jobs() -> list:
    conn = _get_conn()
    try:
        cur = _cursor(conn)
        cur.execute('SELECT * FROM jobs WHERE is_archived = 0 ORDER BY deadline ASC')
        return cur.fetchall()
    finally:
        conn.close()


def get_job(job_id: int):
    conn = _get_conn()
    try:
        cur = _cursor(conn)
        cur.execute(f'SELECT * FROM jobs WHERE id = {PH}', (job_id,))
        return cur.fetchone()
    finally:
        conn.close()


def update_status(job_id: int, status: str,
                  revision_deadline: str = None, done_at: str = None):
    conn = _get_conn()
    try:
        cur = _cursor(conn)
        if revision_deadline:
            cur.execute(
                f'UPDATE jobs SET status={PH}, revision_deadline={PH} WHERE id={PH}',
                (status, revision_deadline, job_id)
            )
        elif done_at:
            cur.execute(
                f'UPDATE jobs SET status={PH}, done_at={PH} WHERE id={PH}',
                (status, done_at, job_id)
            )
        else:
            cur.execute(f'UPDATE jobs SET status={PH} WHERE id={PH}', (status, job_id))
        conn.commit()
    finally:
        conn.close()


def _reset_id_if_empty(conn, cur):
    """Reset auto-increment ID ke 1 jika tidak ada job aktif.
    Sekalian hapus semua arsip agar tidak ada konflik ID."""
    cur.execute("SELECT COUNT(*) FROM jobs WHERE is_archived = 0")
    row = cur.fetchone()
    active = row[0] if not USE_PG else row['count']
    if active == 0:
        # Hapus semua arsip dulu
        cur.execute("DELETE FROM jobs")
        # Reset sequence
        if USE_PG:
            cur.execute("ALTER SEQUENCE jobs_id_seq RESTART WITH 1")
        else:
            cur.execute("DELETE FROM sqlite_sequence WHERE name='jobs'")


def archive_job(job_id: int):
    conn = _get_conn()
    try:
        cur = _cursor(conn)
        cur.execute(f'UPDATE jobs SET is_archived=1 WHERE id={PH}', (job_id,))
        _reset_id_if_empty(conn, cur)
        conn.commit()
    finally:
        conn.close()


def delete_job(job_id: int):
    """Hapus permanen dari database."""
    conn = _get_conn()
    try:
        cur = _cursor(conn)
        cur.execute(f'DELETE FROM jobs WHERE id={PH}', (job_id,))
        _reset_id_if_empty(conn, cur)
        conn.commit()
    finally:
        conn.close()


def get_near_deadline_jobs(hours: int = 3) -> list:
    now = now_wita()
    result = []
    for job in get_active_jobs():
        if job['status'] == 'menunggu_payment':
            continue
        try:
            dl_str = (
                job['revision_deadline']
                if job['status'] == 'sedang_direvisi' and job['revision_deadline']
                else job['deadline']
            )
            diff = (datetime.strptime(dl_str, '%d/%m/%Y %H:%M') - now).total_seconds()
            if 0 < diff <= hours * 3600:
                result.append((job, diff))
        except Exception:
            pass
    return result
