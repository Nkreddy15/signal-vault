"""Authenticated cloud wrapper around the existing Signal Vault dashboard."""
import hmac
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'dashboard'))
import app as dashboard
from flask import Response, request

password = os.environ.get('V11_DASHBOARD_PASSWORD', '')
if len(password) < 32:
    raise RuntimeError('Private dashboard password is required.')
username = os.environ.get('V11_DASHBOARD_USER', 'nikhil')
dashboard.paper_v11_view.ROOT = Path(os.environ.get('PAPER_V11_STATE_DIR', '/data/paper-v11-500'))
dashboard.FREQTRADE_BASE = 'http://127.0.0.1:1/api/v1'
dashboard.FREQ_USER = dashboard.FREQ_PASS = dashboard.ALPACA_KEY = dashboard.ALPACA_SECRET = ''
app = dashboard.app


@app.before_request
def private_owner_view():
    if request.path == '/healthz' and request.method in ('GET', 'HEAD'):
        return None  # Liveness only; exposes no account data.
    auth = request.authorization
    if not auth or not hmac.compare_digest(auth.username or '', username) or not hmac.compare_digest(auth.password or '', password):
        return Response('Owner login required.', 401, {'WWW-Authenticate': 'Basic realm="Signal Vault"'})
    if request.method not in ('GET', 'HEAD'):
        return Response('Read-only dashboard.', 405)
    if request.path not in ('/', '/api/snapshot', '/api/paper-v11', '/api/candles') and not request.path.startswith('/static/'):
        return Response('This cloud service exposes only V11.', 404)
    if request.args.get('engine') not in (None, 'v11'):
        return Response('This cloud service exposes only V11.', 400)


@app.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response
