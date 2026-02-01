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

def get_restaurant_jwt():
    """
    Auth flow:
    1. Get DotykMe token with audience for portal.dotyk.cloud
    2. Login to portal.dotyk.cloud (session cookies)
    3. Request JWT scoped to eu.restaurant.dotyk.cloud via portal
    """
    # Step 1: Get DotykMe token for portal
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

    if not dotyk_token:
        raise Exception("Failed to get DotykMe token")

    # Step 2: Login to portal
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

    # Step 3: Get JWT for restaurant
    app_url = f"{RESTAURANT_API}/{VENUE}"
    token_url = f"{PORTAL_TOKEN_API}?appUrl={urllib.request.quote(app_url, safe='')}"
    req = urllib.request.Request(token_url, method="GET")
    with opener.open(req, timeout=30) as r:
        portal_data = json.loads(r.read().decode())
        restaurant_jwt = portal_data.get("token")

    if not restaurant_jwt:
        raise Exception("Failed to get restaurant JWT from portal")

    return restaurant_jwt, opener

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

            jwt_token, opener = get_restaurant_jwt()

            # First, initialize session on restaurant domain with the JWT
            # The portal loads the restaurant app via iframe with the token
            # We simulate this by accessing the cms endpoint which sets session cookies
            cms_url = f"{RESTAURANT_API}/{VENUE}/cms?frameId=api-session"
            req = urllib.request.Request(
                cms_url,
                headers={"Authorization": f"Bearer {jwt_token}"},
                method="GET"
            )
            try:
                opener.open(req, timeout=30)
            except Exception:
                pass  # May redirect or return HTML, that's fine - we just need cookies

            # Now PATCH to toggle isEnabled using the session
            url = f"{RESTAURANT_API}/{VENUE}/Category"
            patch_data = json.dumps({
                "id": category_id,
                "isEnabled": is_enabled,
                "type": "Category"
            }).encode()

            # Try with session cookies (from cms init) + Bearer token
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
            try:
                with opener.open(req, timeout=30) as resp:
                    resp_body = resp.read().decode()
                self.send_json(200, {
                    "success": True,
                    "message": f"Menu {'activado' if is_enabled else 'desactivado'}"
                })
                return
            except urllib.request.HTTPError as e1:
                error1 = f"Attempt 1 (Bearer+session): {e1.code} {e1.reason}"
                try:
                    error1 += f" - {e1.read().decode()[:200]}"
                except:
                    pass

            # Fallback: try direct token auth without cms init
            req = urllib.request.Request(
                url,
                data=patch_data,
                headers={
                    "Content-Type": "application/json",
                    "Content-Language": "es",
                    "Authorization": f"Bearer {jwt_token}",
                    "X-Requested-With": "XMLHttpRequest"
                },
                method="PATCH"
            )
            try:
                with urllib.request.urlopen(req, context=ssl_ctx(), timeout=30) as resp:
                    resp_body = resp.read().decode()
                self.send_json(200, {
                    "success": True,
                    "message": f"Menu {'activado' if is_enabled else 'desactivado'}"
                })
                return
            except urllib.request.HTTPError as e2:
                error2 = f"Attempt 2 (Bearer only): {e2.code} {e2.reason}"
                try:
                    error2 += f" - {e2.read().decode()[:200]}"
                except:
                    pass

            self.send_json(500, {
                "success": False,
                "error": f"{error1} | {error2}"
            })

        except Exception as e:
            self.send_json(500, {"success": False, "error": str(e)})

    def send_json(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
