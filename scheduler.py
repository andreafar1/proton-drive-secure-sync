"""Persistent, single-process scheduler for conservative one-way Rclone copy jobs.

Jobs never delete or intentionally overwrite destination files. They are not
bidirectional sync, and --ignore-existing is not an atomic remote lock.
"""
import json
import os
import re
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from secure_sync.core import validate_remote, validate_path, SyncError

DB = Path(os.environ.get('PDSS_DB', '/data/schedules.sqlite3'))
LOCAL_ROOT = Path(os.environ.get('PDSS_SYNC_ROOT', '/sync'))
REMOTE = validate_remote(os.environ.get('PDSS_REMOTE', 'proton:'))
INTERVALS = (0, 15, 30, 60, 360, 720, 1440)
MAX_JOBS = 25
MAX_RUNTIME = 3600
JOB_NAME = re.compile(r'^[\w .()-]{1,80}$', re.UNICODE)

def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA busy_timeout=15000')
    db.execute('''CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, direction TEXT NOT NULL,
        local_path TEXT NOT NULL, remote_path TEXT NOT NULL,
        interval_minutes INTEGER NOT NULL, enabled INTEGER NOT NULL DEFAULT 0,
        next_run REAL, last_run REAL, last_status TEXT NOT NULL DEFAULT 'Mai eseguito',
        running INTEGER NOT NULL DEFAULT 0, run_requested INTEGER NOT NULL DEFAULT 0
    )''')
    db.execute('CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY, job_name TEXT NOT NULL, started REAL NOT NULL, finished REAL NOT NULL, status TEXT NOT NULL)')
    db.commit()
    return db

def local_path(relative):
    if not isinstance(relative, str) or relative.startswith('/') or '\\' in relative or '\x00' in relative:
        raise ValueError('Percorso locale non valido')
    if relative not in ('', '.'):
        validate_path(relative)
    root = LOCAL_ROOT.resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Cartella /sync non disponibile')
    target = (root / ('' if relative == '.' else relative)).resolve(strict=True)
    if not target.is_dir() or not target.is_relative_to(root):
        raise ValueError('Cartella locale inesistente o esterna a /sync')
    return target

def check_job(data):
    name = str(data.get('name', '')).strip()
    if not JOB_NAME.fullmatch(name):
        raise ValueError('Nome non valido (massimo 80 caratteri)')
    direction = data.get('direction')
    if direction not in ('upload', 'download'):
        raise ValueError('Direzione non valida')
    local = data.get('local_path', '')
    if not isinstance(local, str):
        raise ValueError('Percorso locale non valido')
    local_path(local)
    remote = data.get('remote_path', '')
    if not isinstance(remote, str):
        raise ValueError('Percorso remoto non valido')
    if remote:
        validate_path(remote)
    interval = data.get('interval_minutes')
    if type(interval) is not int or interval not in INTERVALS:
        raise ValueError('Intervallo non valido')
    return name, direction, local, remote, interval

def list_jobs():
    with connect() as db:
        return [dict(row) for row in db.execute('SELECT * FROM jobs ORDER BY id DESC')]

def add_job(data):
    name, direction, local, remote, interval = check_job(data)
    with connect() as db:
        if db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] >= MAX_JOBS:
            raise ValueError('Limite massimo di 25 attività')
        cur = db.execute('''INSERT INTO jobs(name,direction,local_path,remote_path,
            interval_minutes,enabled,next_run) VALUES(?,?,?,?,?,0,NULL)''',
            (name,direction,local,remote,interval))
        return cur.lastrowid

def update_job(job_id, data):
    name, direction, local, remote, interval = check_job(data)
    with connect() as db:
        row = db.execute('SELECT running FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not row: raise ValueError('Attività non trovata')
        if row['running']: raise ValueError('Attività in esecuzione')
        db.execute('''UPDATE jobs SET name=?,direction=?,local_path=?,remote_path=?,
            interval_minutes=?,enabled=0,next_run=NULL,run_requested=0 WHERE id=?''',
            (name,direction,local,remote,interval,job_id))

def toggle_job(job_id, enabled):
    if type(enabled) is not bool: raise ValueError('Valore non valido')
    with connect() as db:
        row = db.execute('SELECT running,interval_minutes FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not row: raise ValueError('Attività non trovata')
        if enabled and row['interval_minutes'] == 0:
            raise ValueError('Le attività manuali non possono essere programmate')
        db.execute('UPDATE jobs SET enabled=?,next_run=? WHERE id=?',
                   (int(enabled), time.time() + row['interval_minutes']*60 if enabled else None, job_id))

def request_run(job_id):
    with connect() as db:
        row = db.execute('SELECT id FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not row: raise ValueError('Attività non trovata')
        db.execute('UPDATE jobs SET run_requested=1 WHERE id=?', (job_id,))

def delete_job(job_id):
    with connect() as db:
        row = db.execute('SELECT running FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not row: raise ValueError('Attività non trovata')
        if row['running']: raise ValueError('Attività in esecuzione')
        db.execute('DELETE FROM jobs WHERE id=?', (job_id,))

def pause_jobs_for_account_change():
    """Prevent old scheduled jobs from running against another Proton account."""
    with connect() as db:
        if db.execute('SELECT COUNT(*) FROM jobs WHERE running=1').fetchone()[0]:
            raise ValueError('Attendi che le sincronizzazioni in corso siano terminate')
        db.execute("""UPDATE jobs SET enabled=0, next_run=NULL, run_requested=0,
                      last_status='Disattivata: account Proton modificato'""")

def run_job(row):
    try:
        local = local_path(row['local_path'])
        remote = REMOTE + row['remote_path']
        if row['direction'] == 'upload':
            source, dest = str(local), remote
        else:
            source, dest = remote, str(local)
        # Rclone copy is intentionally non-deleting; ignore-existing prevents
        # intentional overwrites, but does not offer transactional guarantees.
        command = ['rclone', 'copy', source, dest, '--ignore-existing',
                   '--retries', '1', '--checkers', '2', '--transfers', '1',
                   '--log-level', 'ERROR']
        result = subprocess.run(command, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=MAX_RUNTIME, check=False,
                                env={**os.environ, 'RCLONE_ASK_PASSWORD': 'false'})
        return 'Completato' if result.returncode == 0 else 'Errore Rclone (codice '+str(result.returncode)+')'
    except subprocess.TimeoutExpired:
        return 'Timeout (1 ora)'
    except (OSError, ValueError, SyncError):
        return 'Errore di configurazione o esecuzione'

def tick():
    now = time.time()
    with connect() as db:
        row = db.execute('''SELECT * FROM jobs WHERE running=0 AND
            (run_requested=1 OR (enabled=1 AND next_run IS NOT NULL AND next_run<=?))
            ORDER BY run_requested DESC, next_run ASC LIMIT 1''', (now,)).fetchone()
        if row is None: return False
        db.execute('UPDATE jobs SET running=1,run_requested=0 WHERE id=?', (row['id'],))
    started = time.time()
    status = run_job(row)
    with connect() as db:
        db.execute('INSERT INTO history(job_name,started,finished,status) VALUES(?,?,?,?)', (row['name'], started, time.time(), status))
        current = db.execute('SELECT interval_minutes,enabled FROM jobs WHERE id=?', (row['id'],)).fetchone()
        if current:
            next_run = time.time()+current['interval_minutes']*60 if current['enabled'] and current['interval_minutes'] else None
            db.execute('''UPDATE jobs SET running=0,last_run=?,last_status=?,next_run=?
                          WHERE id=?''', (time.time(), status, next_run, row['id']))
    return True

def main():
    with connect() as db:
        db.execute('UPDATE jobs SET running=0,last_status=? WHERE running=1',
                   ('Interrotto dal riavvio',))
    while True:
        try:
            if not tick(): time.sleep(5)
        except (sqlite3.Error, OSError):
            time.sleep(10)

if __name__ == '__main__':
    main()
