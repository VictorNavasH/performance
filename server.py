#!/usr/bin/env python3
from http.server import HTTPServer, SimpleHTTPRequestHandler
import urllib.request, json, ssl, os

PORT = 8080
TOKEN_API = "https://dotyk.me/api/v1.2/token/password/"
LOGIN_API = "https://dotyk.tech/api/user/LoginWithDotykMe"
AUTH_TOKEN = None

def ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def load_config():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    return json.load(open(p)) if os.path.exists(p) else {}

def get_token(email, pwd):
    print("🔐 [1/2] Obteniendo token...")
    body = json.dumps({"username": email, "password": pwd, "duration": "Long", "audience": "https://dotyk.tech/", "scope": ["basic"]}).encode()
    req = urllib.request.Request(TOKEN_API, data=body, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, context=ssl_ctx(), timeout=30) as r:
            data = json.loads(r.read().decode())
            token = data.get('token') or data.get('access_token')
            print(f"   ✅ Token OK: {str(token)[:40]}...")
            return token
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None

def login(token):
    print("🔑 [2/2] Login dotyk.tech...")
    body = f'"{token}"'.encode()
    req = urllib.request.Request(LOGIN_API, data=body, headers={'Content-Type': 'application/json; charset=utf-8'}, method='POST')
    try:
        with urllib.request.urlopen(req, context=ssl_ctx(), timeout=30) as r:
            print("   ✅ Login OK")
            return r.headers.get('Set-Cookie', '')
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None

class H(SimpleHTTPRequestHandler):
    def do_GET(self):
        if 'favicon' in self.path:
            self.send_response(204)
            self.end_headers()
            return
        super().do_GET()
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', '*')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()
    def do_PATCH(self):
        if '/api/' in self.path:
            self.proxy_patch()
        else:
            self.send_error(404)
    def proxy_patch(self):
        global AUTH_TOKEN
        API = "https://eu.performanceshow.dotyk.cloud/nua-barcelona/Template"
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length) if length else None
            print(f"\n📤 PATCH → {API}")
            headers = {'Content-Type': 'application/json', 'Accept': '*/*'}
            if AUTH_TOKEN:
                headers['Authorization'] = f'Bearer {AUTH_TOKEN}'
            req = urllib.request.Request(API, data=body, headers=headers, method='PATCH')
            with urllib.request.urlopen(req, context=ssl_ctx(), timeout=30) as r:
                out = r.read()
                print(f"   ✅ OK: {r.status}")
                self.send_response(r.status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(out or b'{}')
        except urllib.error.HTTPError as e:
            err = e.read() if hasattr(e, 'read') else b'{}'
            print(f"   ❌ HTTP {e.code}: {err.decode()[:100]}")
            self.send_response(e.code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(err)
        except Exception as e:
            print(f"   ❌ Error: {e}")
            self.send_response(500)
            self.end_headers()
    def log_message(self, *args):
        pass

if __name__ == '__main__':
    print("=" * 50)
    print("🎬 DOTYK PUBLISHER v4")
    print("=" * 50)
    cfg = load_config()
    if cfg.get('email') and cfg.get('password'):
        AUTH_TOKEN = get_token(cfg['email'], cfg['password'])
        if AUTH_TOKEN:
            login(AUTH_TOKEN)
    if not AUTH_TOKEN:
        print("\n⚠️  Sin token - puede haber errores 403")
    print(f"\n✅ http://localhost:{PORT}\n")
    HTTPServer(('', PORT), H).serve_forever()
