from http.server import BaseHTTPRequestHandler
import json, os, ssl, urllib.request, http.cookiejar

EMAIL = os.environ.get("DOTYK_EMAIL", "")
PASSWORD = os.environ.get("DOTYK_PASSWORD", "")
VIDEO_URL = "https://irtperformanceshoweu.blob.core.windows.net/dotykcloudperformanceshow/1qfl_FzhVSQfWSsQ6uBLxswJV9x4_BbeV22KojBIMOwxJAD4CGPWPwFnFf8m"
TOKEN_API = "https://dotyk.me/api/v1.2/token/password"
LOGIN_API = "https://dotyk.tech/api/user/LoginWithDotykMe"
START_API = "https://dotyk.tech/api/PerformanceShow/start/"

def ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, PATCH, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        self._handle_request()

    def do_PATCH(self):
        self._handle_request()

    def _handle_request(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            
            # El frontend envía un objeto con "tables" que es una lista de objetos { item: { tableId: "..." } }
            # O directamente una lista de IDs si es POST simple
            tables_data = body.get("tables", [])
            table_ids = []
            
            for item in tables_data:
                if isinstance(item, dict) and "item" in item:
                    table_ids.append(item["item"]["tableId"])
                else:
                    table_ids.append(str(item))
                    
            video_url = body.get("videoUrl") or VIDEO_URL
            
            if not table_ids:
                self.send_json(400, {"error": "No hay mesas seleccionadas"})
                return
            if not EMAIL or not PASSWORD:
                self.send_json(500, {"error": "Credenciales no configuradas en entorno"})
                return
            
            # Token
            req = urllib.request.Request(TOKEN_API, data=json.dumps({"username": EMAIL, "password": PASSWORD, "duration": "Long", "audience": "https://dotyk.tech/", "scope": ["basic"]}).encode(), headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, context=ssl_ctx(), timeout=30) as r:
                token_data = json.loads(r.read().decode())
                token = token_data.get("token") or token_data.get("access_token")
            
            # Login + Publish
            cj = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj), urllib.request.HTTPSHandler(context=ssl_ctx()))
            req = urllib.request.Request(LOGIN_API, data=f'"{token}"'.encode(), headers={"Content-Type": "application/json"}, method="POST")
            opener.open(req, timeout=30)
            
            params = "&".join([f"id={t}" for t in table_ids])
            url = f"{START_API}?viewMode=FullScreen&{params}"
            req = urllib.request.Request(url, data=json.dumps({"ApplicationName": "Dotyk.Extension.PerformanceShow", "Argument": f"-performaceUrl {video_url}", "StartOptions": {"IsForceFullScreenIfSupported": True}}).encode(), headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}, method="POST")
            opener.open(req, timeout=30)
            
            self.send_json(200, {"success": True, "status": "ok", "message": f"Publicado en {len(table_ids)} mesa(s)"})
        except Exception as e:
            self.send_json(500, {"success": False, "error": str(e)})

    def send_json(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
