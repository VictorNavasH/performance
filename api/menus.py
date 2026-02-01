from http.server import BaseHTTPRequestHandler
import json, os, ssl, urllib.request

EMAIL = os.environ.get("DOTYK_EMAIL", "")
PASSWORD = os.environ.get("DOTYK_PASSWORD", "")
TOKEN_API = "https://dotyk.me/api/v1.2/token/password"
RESTAURANT_API = "https://eu.restaurant.dotyk.cloud"
VENUE = "nua-barcelona"

def ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def get_restaurant_token():
    """Pide token directamente a dotyk.me con audience del restaurante"""
    req = urllib.request.Request(
        TOKEN_API,
        data=json.dumps({
            "username": EMAIL,
            "password": PASSWORD,
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
                self.send_json(500, {"success": False, "error": f"Sin credenciales. EMAIL={bool(EMAIL)} PASS={bool(PASSWORD)}"})
                return

            # Paso 1: Token directo con audience del restaurante
            try:
                jwt_token = get_restaurant_token()
                if not jwt_token:
                    self.send_json(500, {"success": False, "error": "Token vacio de dotyk.me"})
                    return
            except Exception as e:
                self.send_json(500, {"success": False, "error": f"Token: {str(e)}"})
                return

            # Paso 2: PATCH a la categoria
            url = f"{RESTAURANT_API}/{VENUE}/Category"
            payload = {"id": category_id, "isEnabled": is_enabled, "type": "Category"}
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

            try:
                with urllib.request.urlopen(req, context=ssl_ctx(), timeout=15) as resp:
                    resp_body = resp.read().decode()[:300]
                    self.send_json(200, {"success": True, "message": "OK", "debug": {"sent": payload, "resp": resp_body}})
            except urllib.request.HTTPError as he:
                body_err = ""
                try:
                    body_err = he.read().decode()[:300]
                except:
                    pass
                self.send_json(500, {"success": False, "error": f"PATCH {he.code}: {body_err}", "debug": {"sent": payload}})

        except Exception as e:
            self.send_json(500, {"success": False, "error": f"General: {str(e)}"})

    def send_json(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
