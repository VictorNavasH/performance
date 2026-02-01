from http.server import BaseHTTPRequestHandler
import json, os, ssl, urllib.request, http.cookiejar

EMAIL = os.environ.get("DOTYK_EMAIL", "")
PASSWORD = os.environ.get("DOTYK_PASSWORD", "")
TOKEN_API = "https://dotyk.me/api/v1.2/token/password"
LOGIN_API = "https://dotyk.tech/api/user/LoginWithDotykMe"
RESTAURANT_API = "https://eu.restaurant.dotyk.cloud"

def ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def get_authenticated_opener():
    """Authenticate and return opener with session cookies."""
    req = urllib.request.Request(
        TOKEN_API,
        data=json.dumps({
            "username": EMAIL, "password": PASSWORD,
            "duration": "Long", "audience": "https://dotyk.tech/", "scope": ["basic"]
        }).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, context=ssl_ctx(), timeout=30) as r:
        token_data = json.loads(r.read().decode())
        token = token_data.get("token") or token_data.get("access_token")

    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cj),
        urllib.request.HTTPSHandler(context=ssl_ctx())
    )
    req = urllib.request.Request(
        LOGIN_API,
        data=f'"{token}"'.encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    opener.open(req, timeout=30)
    return opener

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, PATCH, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        """Toggle a menu category's isEnabled state."""
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}

            category_id = body.get("categoryId")
            is_enabled = body.get("isEnabled")

            if not category_id or is_enabled is None:
                self.send_json(400, {"error": "categoryId and isEnabled are required"})
                return
            if not EMAIL or not PASSWORD:
                self.send_json(500, {"error": "Credenciales no configuradas"})
                return

            opener = get_authenticated_opener()

            # PATCH to toggle isEnabled
            url = f"{RESTAURANT_API}/api/Category/{category_id}"
            patch_data = json.dumps({"isEnabled": is_enabled}).encode()
            req = urllib.request.Request(
                url,
                data=patch_data,
                headers={
                    "Content-Type": "application/json",
                    "X-Requested-With": "XMLHttpRequest"
                },
                method="PATCH"
            )
            with opener.open(req, timeout=30) as resp:
                resp_body = resp.read().decode()

            self.send_json(200, {
                "success": True,
                "message": f"Menu {'activado' if is_enabled else 'desactivado'}"
            })
        except Exception as e:
            self.send_json(500, {"success": False, "error": str(e)})

    def send_json(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
