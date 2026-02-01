from http.server import BaseHTTPRequestHandler
import json, os, ssl, urllib.request, http.cookiejar

EMAIL = os.environ.get("DOTYK_EMAIL", "")
PASSWORD = os.environ.get("DOTYK_PASSWORD", "")
TOKEN_API = "https://dotyk.me/api/v1.2/token/password"
PORTAL_LOGIN_API = "https://portal.dotyk.cloud/api/user/LoginWithDotykMe"
PORTAL_TOKEN_API = "https://portal.dotyk.cloud/api/portal/token"
RESTAURANT_API = "https://eu.restaurant.dotyk.cloud"
VENUE = "nua-barcelona"

def ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def get_restaurant_token():
    """
    Auth flow (from HAR analysis):
    1. Get DotykMe token with audience for portal
    2. Login to portal.dotyk.cloud with that token (sets session cookies)
    3. Get a JWT scoped to eu.restaurant.dotyk.cloud via portal token endpoint
    4. Use that JWT as Bearer token for restaurant API calls
    """
    # Step 1: Get DotykMe token (audience = portal)
    req = urllib.request.Request(
        TOKEN_API,
        data=json.dumps({
            "username": EMAIL, "password": PASSWORD,
            "duration": "Long",
            "audience": "https://portal.dotyk.cloud/",
            "scope": ["basic"]
        }).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, context=ssl_ctx(), timeout=30) as r:
        token_data = json.loads(r.read().decode())
        dotyk_token = token_data.get("token") or token_data.get("access_token")

    # Step 2: Login to portal with DotykMe token (gets session cookies)
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cj),
        urllib.request.HTTPSHandler(context=ssl_ctx())
    )
    req = urllib.request.Request(
        PORTAL_LOGIN_API,
        data=f'"{dotyk_token}"'.encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    opener.open(req, timeout=30)

    # Step 3: Get JWT token scoped to restaurant API
    app_url = f"{RESTAURANT_API}/{VENUE}"
    token_url = f"{PORTAL_TOKEN_API}?appUrl={urllib.request.quote(app_url, safe='')}"
    req = urllib.request.Request(token_url, method="GET")
    with opener.open(req, timeout=30) as r:
        portal_data = json.loads(r.read().decode())
        restaurant_jwt = portal_data.get("token")

    return restaurant_jwt

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

            # Get JWT token for restaurant API
            jwt_token = get_restaurant_token()

            # PATCH to toggle isEnabled
            # URL: /nua-barcelona/Category (NOT /api/Category)
            url = f"{RESTAURANT_API}/{VENUE}/Category"
            patch_data = json.dumps({
                "id": category_id,
                "isEnabled": is_enabled,
                "type": "Category"
            }).encode()
            req = urllib.request.Request(
                url,
                data=patch_data,
                headers={
                    "Content-Type": "application/json",
                    "Content-Language": "es",
                    "Authorization": f"Bearer {jwt_token}"
                },
                method="PATCH"
            )
            with urllib.request.urlopen(req, context=ssl_ctx(), timeout=30) as resp:
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
