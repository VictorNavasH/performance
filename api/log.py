from http.server import BaseHTTPRequestHandler
import json, os, ssl, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
MADRID_TZ = timezone(timedelta(hours=1))  # CET base, adjusted below


def madrid_now():
    """Get current Madrid time (handles CET/CEST)."""
    utc_now = datetime.now(timezone.utc)
    # Simple DST rule: last Sunday of March to last Sunday of October
    year = utc_now.year
    # Last Sunday of March
    mar31 = datetime(year, 3, 31, tzinfo=timezone.utc)
    dst_start = mar31 - timedelta(days=(mar31.weekday() + 1) % 7)
    dst_start = dst_start.replace(hour=1)
    # Last Sunday of October
    oct31 = datetime(year, 10, 31, tzinfo=timezone.utc)
    dst_end = oct31 - timedelta(days=(oct31.weekday() + 1) % 7)
    dst_end = dst_end.replace(hour=1)

    if dst_start <= utc_now < dst_end:
        offset = timedelta(hours=2)  # CEST
    else:
        offset = timedelta(hours=1)  # CET

    madrid = utc_now + offset
    return madrid.strftime("%Y-%m-%d %H:%M:%S")


def ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        """Save an activation log."""
        try:
            if not SUPABASE_URL or not SUPABASE_KEY:
                self.send_json(500, {"error": "Supabase no configurado"})
                return

            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}

            row = {
                "video_name": body.get("video_name", ""),
                "video_id": body.get("video_id", ""),
                "table_names": body.get("table_names", ""),
                "table_ids": body.get("table_ids", ""),
                "table_count": body.get("table_count", 0),
                "role": body.get("role", ""),
                "activated_at_madrid": madrid_now()
            }

            data = json.dumps(row).encode()
            url = f"{SUPABASE_URL}/rest/v1/performance_logs"
            req = urllib.request.Request(url, data=data, headers={
                "Content-Type": "application/json",
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Prefer": "return=minimal"
            }, method="POST")

            urllib.request.urlopen(req, context=ssl_ctx(), timeout=10)
            self.send_json(200, {"success": True})

        except Exception as e:
            self.send_json(500, {"success": False, "error": str(e)})

    def do_GET(self):
        """Get recent activation logs."""
        try:
            if not SUPABASE_URL or not SUPABASE_KEY:
                self.send_json(500, {"error": "Supabase no configurado"})
                return

            url = f"{SUPABASE_URL}/rest/v1/performance_logs?select=*&order=activated_at.desc&limit=30"
            req = urllib.request.Request(url, headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}"
            }, method="GET")

            with urllib.request.urlopen(req, context=ssl_ctx(), timeout=10) as r:
                logs = json.loads(r.read().decode())

            self.send_json(200, logs)

        except Exception as e:
            self.send_json(500, {"error": str(e)})

    def send_json(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
