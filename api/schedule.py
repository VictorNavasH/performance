from http.server import BaseHTTPRequestHandler
import json, os, ssl, urllib.request, urllib.parse

BLOB_TOKEN = os.environ.get("BLOB_READ_WRITE_TOKEN", "")
BLOB_STORE_ID = os.environ.get("BLOB_STORE_ID", "")
SCHEDULE_PATH = "schedule.json"
ADMIN_PIN = "9069"

# Vercel Blob API base
BLOB_API = "https://blob.vercel-storage.com"

def ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def blob_url():
    """Build the full blob URL for schedule.json"""
    if BLOB_STORE_ID:
        return f"https://{BLOB_STORE_ID}.public.blob.vercel-storage.com/{SCHEDULE_PATH}"
    return None

def read_schedule():
    """Read schedule from Vercel Blob. Returns default if not found."""
    default = {"enabled": False, "rules": [], "lastAction": None, "lastCronRun": None}
    url = blob_url()
    if not url:
        # Try listing blobs to find the URL
        try:
            req = urllib.request.Request(
                f"{BLOB_API}?prefix={SCHEDULE_PATH}",
                headers={"Authorization": f"Bearer {BLOB_TOKEN}"},
                method="GET"
            )
            with urllib.request.urlopen(req, context=ssl_ctx(), timeout=10) as r:
                data = json.loads(r.read().decode())
                blobs = data.get("blobs", [])
                if blobs:
                    blob_file_url = blobs[0].get("url", "")
                    if blob_file_url:
                        req2 = urllib.request.Request(blob_file_url)
                        with urllib.request.urlopen(req2, context=ssl_ctx(), timeout=10) as r2:
                            return json.loads(r2.read().decode())
        except:
            pass
        return default

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, context=ssl_ctx(), timeout=10) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return default
        raise
    except:
        return default

def write_schedule(schedule_data):
    """Write schedule JSON to Vercel Blob."""
    body = json.dumps(schedule_data, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{BLOB_API}/{SCHEDULE_PATH}",
        data=body,
        headers={
            "Authorization": f"Bearer {BLOB_TOKEN}",
            "Content-Type": "application/json",
            "x-api-version": "7",
            "x-content-type": "application/json",
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

    def do_GET(self):
        """Return current schedule"""
        try:
            if not BLOB_TOKEN:
                self.send_json(200, {"enabled": False, "rules": [], "lastAction": None, "lastCronRun": None, "_note": "BLOB_TOKEN not configured"})
                return
            schedule = read_schedule()
            self.send_json(200, schedule)
        except Exception as e:
            self.send_json(500, {"error": f"Read: {str(e)}"})

    def do_POST(self):
        """Save schedule (admin only)"""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}

            # Verify admin PIN
            pin = body.get("pin", "")
            if pin != ADMIN_PIN:
                self.send_json(403, {"error": "PIN incorrecto"})
                return

            if not BLOB_TOKEN:
                self.send_json(500, {"error": "BLOB_READ_WRITE_TOKEN no configurado en Vercel"})
                return

            schedule = body.get("schedule", {})
            # Validate structure
            if "rules" not in schedule:
                schedule["rules"] = []
            if "enabled" not in schedule:
                schedule["enabled"] = False

            result = write_schedule(schedule)
            self.send_json(200, {"success": True, "url": result.get("url", ""), "schedule": schedule})
        except Exception as e:
            self.send_json(500, {"error": f"Write: {str(e)}"})

    def send_json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
