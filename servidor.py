#!/usr/bin/env python3
from http.server import HTTPServer, SimpleHTTPRequestHandler
import urllib.request, urllib.parse, json, ssl, os

PORT = 8080
API = "https://eu.performanceshow.dotyk.cloud/nua-barcelona/Template"
TOKEN = None

def auth():
    global TOKEN
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    if os.path.exists(cfg_path):
        with open(cfg_path) as f:
            cfg = json.load(f)
        print(f"🔐 Auth {cfg['email']}...")
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        # POST con form data
        data = urllib.parse.urlencode({
            'username': cfg['email'],
            'password': cfg['password']
        }).encode()
        
        req = urllib.request.Request(
            "https://dotyk.me/api/v1.2/token/password/",
            data=data,
            method='POST'
        )
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
        
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
                resp = r.read().decode()
                try:
                    TOKEN = json.loads(resp).get('token', resp)
                except:
                    TOKEN = resp.strip('"')
                print(f"✅ Token OK: {TOKEN[:30]}...")
        except Exception as e:
            print(f"❌ Auth fail: {e}")

class H(SimpleHTTPRequestHandler):
    def do_GET(self):
        if 'favicon' in self.path:
            self.send_response(204)
            self.end_headers()
            return
        super().do_GET()
    def do_PATCH(self):
        self.proxy()
    def do_POST(self):
        self.proxy()
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', '*')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()
    def proxy(self):
        try:
            ln = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(ln) if ln else None
            print(f"\n📤 PATCH {API}")
            print(f"   Body: {body.decode() if body else '-'}")
            print(f"   Token: {TOKEN[:40] if TOKEN else 'NONE'}...")
            hdrs = {'Content-Type': 'application/json', 'Accept': '*/*'}
            if TOKEN:
                hdrs['Authorization'] = f'Bearer {TOKEN}'
            req = urllib.request.Request(API, data=body, headers=hdrs, method='PATCH')
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
                out = r.read()
                print(f"✅ {r.status}")
                self.send_response(r.status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(out or b'{}')
        except urllib.error.HTTPError as e:
            err = e.read() if hasattr(e, 'read') else b'{}'
            print(f"❌ {e.code}: {err.decode()[:200]}")
            self.send_response(e.code)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(err)
        except Exception as e:
            print(f"❌ {e}")
            self.send_response(500)
            self.end_headers()
    def log_message(self, *a):
        pass

if __name__ == '__main__':
    print("="*50)
    print("🎬 DOTYK PUBLISHER v3")
    print("="*50)
    auth()
    print(f"\n✅ http://localhost:{PORT}\n")
    HTTPServer(('', PORT), H).serve_forever()
