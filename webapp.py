"""Container web UI for cautious manual Rclone transfers (experimental)."""
import hmac
import os
import secrets
import tempfile
from pathlib import Path
from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.exceptions import RequestEntityTooLarge
from secure_sync.core import RcloneClient, SyncError, validate_path

app = Flask(__name__, template_folder='web/templates', static_folder='web/static')
secret = os.environ.get('PDSS_SESSION_SECRET', '')
password = os.environ.get('PDSS_PASSWORD', '')
if len(secret) < 32 or len(password) < 16:
    raise RuntimeError('Set PDSS_SESSION_SECRET (32+ chars) and PDSS_PASSWORD (16+ chars)')
app.secret_key = secret
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict',
                  SESSION_COOKIE_SECURE=os.environ.get('PDSS_HTTPS', '0') == '1',
                  MAX_CONTENT_LENGTH=int(os.environ.get('PDSS_MAX_UPLOAD_MB', '100')) * 1024 * 1024)
REMOTE = os.environ.get('PDSS_REMOTE', 'proton:')
WORK = Path(os.environ.get('PDSS_WORKDIR', '/data'))
WORK.mkdir(mode=0o700, parents=True, exist_ok=True)

@app.after_request
def headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    return response

def authenticated():
    return session.get('authenticated') is True

def csrf():
    return session.setdefault('csrf', secrets.token_urlsafe(32))

def require_auth():
    if not authenticated():
        abort(401)

def require_csrf():
    if not hmac.compare_digest(str(request.headers.get('X-CSRF-Token', '')), str(session.get('csrf', ''))):
        abort(403)

@app.get('/health')
def health():
    return jsonify(status='ok')

@app.get('/')
def index():
    if not authenticated():
        return render_template('login.html')
    return render_template('index.html', csrf=csrf(), remote=REMOTE)

@app.post('/login')
def login():
    supplied = request.form.get('password', '')
    if not hmac.compare_digest(supplied.encode('utf-8'), password.encode('utf-8')):
        return render_template('login.html', error='Password non valida'), 401
    session.clear()
    session['authenticated'] = True
    csrf()
    return redirect(url_for('index'))

@app.post('/logout')
def logout():
    require_auth()
    require_csrf()
    session.clear()
    return jsonify(ok=True)

@app.get('/api/files')
def files():
    require_auth()
    try:
        return jsonify(files=RcloneClient(REMOTE).list_entries())
    except SyncError:
        return jsonify(error='Impossibile leggere il remoto Rclone'), 502

@app.post('/api/upload')
def upload():
    require_auth()
    require_csrf()
    file = request.files.get('file')
    if file is None or not file.filename:
        return jsonify(error='Seleziona un file'), 400
    # No path components from browser-supplied filename.
    filename = file.filename
    if filename != Path(filename).name or '/' in filename or '\\' in filename or filename in ('.', '..'):
        return jsonify(error='Nome file non valido'), 400
    from secure_sync.core import validate_name
    try:
        validate_name(filename)
        with tempfile.TemporaryDirectory(prefix='pdss-upload-', dir=WORK) as folder:
            target = Path(folder) / filename
            file.save(target)
            RcloneClient(REMOTE).upload(target)
        return jsonify(ok=True, name=filename)
    except SyncError:
        return jsonify(error='Caricamento non riuscito o file già presente'), 409

@app.post('/api/download')
def download():
    require_auth()
    require_csrf()
    data = request.get_json(silent=True) or {}
    try:
        path = validate_path(data.get('path', ''))
    except SyncError:
        return jsonify(error='Percorso non valido'), 400
    # Stream via a temporary directory, cleaned after the response closes.
    folder = tempfile.TemporaryDirectory(prefix='pdss-download-', dir=WORK)
    try:
        result = RcloneClient(REMOTE).download(path, Path(folder.name))
        response = send_file(result, as_attachment=True, download_name=result.name,
                             mimetype='application/octet-stream')
        response.call_on_close(folder.cleanup)
        return response
    except SyncError:
        folder.cleanup()
        return jsonify(error='Download non riuscito'), 502
    except Exception:
        folder.cleanup()
        raise

@app.errorhandler(RequestEntityTooLarge)
def too_large(error):
    return jsonify(error='File troppo grande per il limite configurato'), 413

if __name__ == '__main__':
    raise SystemExit('Use gunicorn: gunicorn -w 2 -b 0.0.0.0:8080 webapp:app')
