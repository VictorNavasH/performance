from http.server import BaseHTTPRequestHandler
import json, os, ssl, urllib.request
from datetime import datetime, timezone, timedelta

BLOB_TOKEN = os.environ.get("BLOB_READ_WRITE_TOKEN", "")
BLOB_API = "https://blob.vercel-storage.com"
LOG_PATH = "performance_logs.json"
MAX_LOGS = 100


def ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def get_store_id():
    parts = BLOB_TOKEN.split("_")
    if len(parts) >= 4:
        return parts[3]
    return None


def madrid_now():
    """Get current Madrid time (handles CET/CEST)."""
    utc_now = datetime.now(timezone.utc)
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


def read_logs():
    """Read logs from Vercel Blob. Returns empty list if not found."""
    if not BLOB_TOKEN:
        return []

    store_id = get_store_id()
    if store_id:
        try:
            url = f"https://{store_id}.public.blob.vercel-storage.com/{LOG_PATH}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, context=ssl_ctx(), timeout=10) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
        except:
            pass

    # Fallback: list API
    try:
        req = urllib.request.Request(
            f"{BLOB_API}?prefix={LOG_PATH}",
            headers={"Authorization": f"Bearer {BLOB_TOKEN}"},
            method="GET"
        )
        with urllib.request.urlopen(req, context=ssl_ctx(), timeout=10) as r:
            data = json.loads(r.read().decode())
            blobs = data.get("blobs", [])
            if blobs:
                blob_url = blobs[0].get("url", "")
                if blob_url:
                    req2 = urllib.request.Request(blob_url)
                    with urllib.request.urlopen(req2, context=ssl_ctx(), timeout=10) as r2:
                        return json.loads(r2.read().decode())
    except:
        pass

    return []


def write_logs(logs):
    """Write logs JSON to Vercel Blob."""
    body = json.dumps(logs, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{BLOB_API}/{LOG_PATH}",
        data=body,
        headers={
            "Authorization": f"Bearer {BLOB_TOKEN}",
            "Content-Type": "application/json",
            "x-api-version": "7",
            "x-content-type": "application/json",
            "x-add-random-suffix": "0",
        },
        method="PUT"
    )
    with urllib.request.urlopen(req, context=ssl_ctx(), timeout=10) as r:
        return json.loads(r.read().decode())


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        """Save a performance log entry."""
        try:
            if not BLOB_TOKEN:
                self.send_json(500, {"error": "BLOB_READ_WRITE_TOKEN no configurado"})
                return

            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}

            entry = {
                "video_name": body.get("video_name", ""),
                "video_id": body.get("video_id", ""),
                "table_names": body.get("table_names", ""),
                "table_ids": body.get("table_ids", ""),
                "table_count": body.get("table_count", 0),
                "role": body.get("role", ""),
                "activated_at_madrid": madrid_now()
            }

            # Read existing, prepend new entry, trim to MAX_LOGS
            logs = read_logs()
            logs.insert(0, entry)
            logs = logs[:MAX_LOGS]

            write_logs(logs)
            self.send_json(200, {"success": True})

        except Exception as e:
            self.send_json(500, {"success": False, "error": str(e)})

    def do_GET(self):
        """Get recent performance logs."""
        try:
            if not BLOB_TOKEN:
                self.send_json(200, [])
                return

            logs = read_logs()
            self.send_json(200, logs)

        except Exception as e:
            self.send_json(500, {"error": str(e)})

    def send_json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
