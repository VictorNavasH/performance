import json
import os
import ssl
import urllib.request
import http.cookiejar

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

def handler(request):
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Content-Type": "application/json"
    }
    
    if request.method == "OPTIONS":
        return {"statusCode": 200, "headers": headers, "body": ""}
    
    if request.method == "POST":
        try:
            body = json.loads(request.body) if request.body else {}
            table_ids = body.get("tables", [])
            video_url = body.get("videoUrl") or VIDEO_URL
            
            if not table_ids:
                return {"statusCode": 400, "headers": headers, "body": json.dumps({"error": "No hay mesas"})}
            
            if not EMAIL or not PASSWORD:
                return {"statusCode": 500, "headers": headers, "body": json.dumps({"error": "Credenciales no configuradas"})}
            
            # Token
            req = urllib.request.Request(TOKEN_API, 
                data=json.dumps({"username": EMAIL, "password": PASSWORD, "duration": "Long", "audience": "https://dotyk.tech/", "scope": ["basic"]}).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, context=ssl_ctx(), timeout=30) as r:
                token = json.loads(r.read().decode()).get("token")
            
            # Login + Publish
            cj = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj), urllib.request.HTTPSHandler(context=ssl_ctx()))
            req = urllib.request.Request(LOGIN_API, data=f'"{token}"'.encode(), headers={"Content-Type": "application/json"}, method="POST")
            opener.open(req, timeout=30)
            
            params = "&".join([f"id={t}" for t in table_ids])
            url = f"{START_API}?viewMode=FullScreen&{params}"
            req = urllib.request.Request(url,
                data=json.dumps({"ApplicationName": "Dotyk.Extension.PerformanceShow", "Argument": f"-performaceUrl {video_url}", "StartOptions": {"IsForceFullScreenIfSupported": True}}).encode(),
                headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}, method="POST")
            opener.open(req, timeout=30)
            
            return {"statusCode": 200, "headers": headers, "body": json.dumps({"status": "ok", "message": f"Publicado en {len(table_ids)} mesa(s)"})}
        except Exception as e:
            return {"statusCode": 500, "headers": headers, "body": json.dumps({"error": str(e)})}
    
    return {"statusCode": 405, "headers": headers, "body": json.dumps({"error": "Method not allowed"})}
