from http.server import BaseHTTPRequestHandler
import json, os, ssl, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

CRON_SECRET = os.environ.get("CRON_SECRET", "")
BLOB_TOKEN = os.environ.get("BLOB_READ_WRITE_TOKEN", "")
BLOB_STORE_ID = os.environ.get("BLOB_STORE_ID", "")
SCHEDULE_PATH = "schedule.json"

# Dotyk API config (duplicated from menus.py for serverless isolation)
EMAIL = os.environ.get("DOTYK_EMAIL", "")
PASSWORD = os.environ.get("DOTYK_PASSWORD", "")
TOKEN_API = "https://dotyk.me/api/v1.2/token/password"
RESTAURANT_API = "https://eu.restaurant.dotyk.cloud"
VENUE = "nua-barcelona"

BLOB_API = "https://blob.vercel-storage.com"

# All category IDs to toggle (parent + children)
ALL_CATEGORY_IDS = {
    "7037dd01-8e70-4571-8857-6295f01c8862": "Smart Menús",
    "7b2ed65e-05c9-45b9-b7b9-adc83345cd5b": "Smart Menú: Poke edition",
    "a61bbcb4-6efe-4be7-85f1-2d6c84adf564": "Smart Menú: Burger edition",
    "782e61b7-9cc9-48e2-b5be-b78876692929": "Crea tu Smart Menú",
    "338712fd-f2a9-463e-8532-6fa17c7ebe8e": "Smart Love Menú",
    "4c394f20-e562-4ed5-aa2b-fa7a3ffbbc18": "Smart Menú: Business Edition",
}

def ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def get_madrid_now():
    """Get current time in Europe/Madrid timezone."""
    if ZoneInfo:
        return datetime.now(ZoneInfo("Europe/Madrid"))
    # Fallback: CET = UTC+1 (doesn't handle DST perfectly)
    return datetime.now(timezone(timedelta(hours=1)))

def blob_url():
    if BLOB_STORE_ID:
        return f"https://{BLOB_STORE_ID}.public.blob.vercel-storage.com/{SCHEDULE_PATH}"
    return None

def read_schedule():
    default = {"enabled": False, "rules": [], "lastAction": None, "lastCronRun": None}
    url = blob_url()
    if not url:
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
    except:
        return default

def write_schedule(schedule_data):
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

def get_restaurant_token():
    req = urllib.request.Request(
        TOKEN_API,
        data=json.dumps({
            "username": EMAIL, "password": PASSWORD,
            "duration": "Long",
            "audience": f"{RESTAURANT_API}/",
            "scope": ["caud", "basic"]
        }).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        method="POST"
    )
    with urllib.request.urlopen(req, context=ssl_ctx(), timeout=15) as r:
        token_data = json.loads(r.read().decode())
        return token_data.get("token") or token_data.get("access_token")

def patch_category(jwt_token, cat_id, cat_name, is_enabled):
    url = f"{RESTAURANT_API}/{VENUE}/Category"
    payload = {"id": cat_id, "name": cat_name, "isEnabled": is_enabled, "type": "Category"}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {jwt_token}",
            "User-Agent": "Mozilla/5.0"
        },
        method="PATCH"
    )
    with urllib.request.urlopen(req, context=ssl_ctx(), timeout=15) as resp:
        return resp.status

def should_be_enabled(schedule, now):
    """Check if menus should be enabled right now based on schedule rules."""
    if not schedule.get("enabled"):
        return None  # Schedule disabled, don't act

    weekday = now.weekday()  # 0=Monday ... 6=Sunday
    current_time = now.strftime("%H:%M")

    for rule in schedule.get("rules", []):
        if not rule.get("active", True):
            continue
        if weekday in rule.get("days", []):
            start = rule.get("startTime", "00:00")
            end = rule.get("endTime", "23:59")
            if start <= current_time < end:
                return True  # At least one rule says "enable now"

    # No rule matched = should be disabled
    return False


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # Verify secret
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            secret = query.get("secret", [""])[0]

            if not CRON_SECRET or secret != CRON_SECRET:
                self.send_json(401, {"error": "Unauthorized"})
                return

            if not BLOB_TOKEN:
                self.send_json(500, {"error": "BLOB_TOKEN not configured"})
                return

            # Read schedule
            schedule = read_schedule()
            now = get_madrid_now()
            now_str = now.strftime("%Y-%m-%d %H:%M:%S")

            # Determine desired state
            desired = should_be_enabled(schedule, now)

            if desired is None:
                # Schedule is disabled, don't act
                schedule["lastCronRun"] = now_str
                write_schedule(schedule)
                self.send_json(200, {"action": "none", "reason": "schedule disabled", "time": now_str})
                return

            desired_action = "enabled" if desired else "disabled"
            last_action = schedule.get("lastAction")

            if desired_action == last_action:
                # No state change needed
                schedule["lastCronRun"] = now_str
                write_schedule(schedule)
                self.send_json(200, {"action": "none", "reason": f"already {desired_action}", "time": now_str})
                return

            # State change needed - PATCH all categories
            if not EMAIL or not PASSWORD:
                self.send_json(500, {"error": "Dotyk credentials not configured"})
                return

            jwt_token = get_restaurant_token()
            if not jwt_token:
                self.send_json(500, {"error": "Could not get Dotyk token"})
                return

            errors = []
            for cat_id, cat_name in ALL_CATEGORY_IDS.items():
                try:
                    patch_category(jwt_token, cat_id, cat_name, desired)
                except Exception as e:
                    errors.append(f"{cat_name}: {str(e)}")

            # Update schedule state
            schedule["lastAction"] = desired_action
            schedule["lastCronRun"] = now_str
            write_schedule(schedule)

            if errors:
                self.send_json(200, {
                    "action": desired_action,
                    "time": now_str,
                    "partial_errors": errors
                })
            else:
                self.send_json(200, {
                    "action": desired_action,
                    "time": now_str,
                    "categories_updated": len(ALL_CATEGORY_IDS)
                })

        except Exception as e:
            self.send_json(500, {"error": f"Cron: {str(e)}"})

    def send_json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
