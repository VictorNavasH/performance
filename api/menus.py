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
    try:
        # Paso 1: DotykMe Token
        req = urllib.request.Request(
            TOKEN_API,
            data=json.dumps({
                "username": EMAIL, "password": PASSWORD,
                "duration": "Long", "audience": "https://portal.dotyk.cloud/", "scope": ["basic"]
            }).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            method="POST"
        )
        with urllib.request.urlopen(req, context=ssl_ctx(), timeout=15) as r:
            token_data = json.loads(r.read().decode())
            dotyk_token = token_data.get("token") or token_data.get("access_token")

        if not dotyk_token:
            return None, "Paso1: No se obtuvo token de DotykMe"

        # Paso 2: Portal Login
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cj),
            urllib.request.HTTPSHandler(context=ssl_ctx())
        )
        req = urllib.request.Request(
            PORTAL_LOGIN_API,
            data=f'"{dotyk_token}"'.encode(),
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            method="POST"
        )
        opener.open(req, timeout=15)

        # Paso 3: Restaurant JWT
        app_url = f"{RESTAURANT_API}/{VENUE}"
        token_url = f"{PORTAL_TOKEN_API}?appUrl={urllib.request.quote(app_url, safe='')}"
        req = urllib.request.Request(token_url, headers={"User-Agent": "Mozilla/5.0"}, method="GET")
        with opener.open(req, timeout=15) as r:
            portal_data = json.loads(r.read().decode())
            restaurant_jwt = portal_data.get("token")

        if not restaurant_jwt:
            return None, "Paso3: El Portal no devolvio JWT de Restaurant"

        return (restaurant_jwt, opener), None

    except Exception as e:
        return None, f"Fallo en Auth: {str(e)}"

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            category_id = body.get("categoryId")
            is_enabled = body.get("isEnabled")

            if not EMAIL or not PASSWORD:
                self.send_json(500, {"success": False, "error": "Credenciales no configuradas en Vercel"})
                return

            auth_result, err = get_restaurant_jwt()
            if err:
                self.send_json(500, {"success": False, "error": err})
                return

            jwt_token, opener = auth_result

            # PATCH Category
            url = f"{RESTAURANT_API}/{VENUE}/Category"
            payload = {"id": category_id, "isEnabled": is_enabled, "type": "Category"}
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {jwt_token}",
                    "X-Requested-With": "XMLHttpRequest",
                    "User-Agent": "Mozilla/5.0"
                },
                method="PATCH"
            )

            with opener.open(req, timeout=15) as resp:
                self.send_json(200, {"success": True, "message": "OK"})

        except urllib.request.HTTPError as he:
            body_err = ""
            try:
                body_err = he.read().decode()[:300]
            except:
                pass
            self.send_json(500, {"success": False, "error": f"PATCH fallo: {he.code} {he.reason} - {body_err}"})
        except Exception as e:
            self.send_json(500, {"success": False, "error": f"Error Final: {str(e)}"})

    def send_json(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
