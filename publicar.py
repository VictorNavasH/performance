#!/usr/bin/env python3
import urllib.request, json, ssl, http.cookiejar

EMAIL = "test.nua.kodisoft@gmail.com"
PASSWORD = "TestAccount1!"
VIDEO_URL = "https://irtperformanceshoweu.blob.core.windows.net/dotykcloudperformanceshow/1qfl_FzhVSQfWSsQ6uBLxswJV9x4_BbeV22KojBIMOwxJAD4CGPWPwFnFf8m"

def ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def get_token():
    print("🔐 Obteniendo token...")
    body = json.dumps({"username": EMAIL, "password": PASSWORD, "duration": "Long", "audience": "https://dotyk.tech/", "scope": ["basic"]}).encode()
    req = urllib.request.Request("https://dotyk.me/api/v1.2/token/password", data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, context=ssl_ctx(), timeout=30) as r:
        token = json.loads(r.read().decode()).get("token")
        print(f"   ✅ Token: {token[:40]}...")
        return token

def login(opener, token):
    print("🔑 Login dotyk.tech...")
    req = urllib.request.Request("https://dotyk.tech/api/user/LoginWithDotykMe", data=f'"{token}"'.encode(), headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    with opener.open(req, timeout=30) as r:
        print(f"   ✅ Login OK")
        return True

def publish(opener, ids):
    print(f"🎬 Publicando en mesas {ids}...")
    params = "&".join([f"id={t}" for t in ids])
    url = f"https://dotyk.tech/api/PerformanceShow/start/?viewMode=FullScreen&{params}"
    body = json.dumps({"ApplicationName": "Dotyk.Extension.PerformanceShow", "Argument": f"-performaceUrl {VIDEO_URL}", "StartOptions": {"IsForceFullScreenIfSupported": True}}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json; charset=UTF-8", "X-Requested-With": "XMLHttpRequest"}, method="POST")
    with opener.open(req, timeout=30) as r:
        print(f"   ✅ PUBLICADO! (status {r.status})")

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj), urllib.request.HTTPSHandler(context=ssl_ctx()))
token = get_token()
login(opener, token)
ids = input("IDs de mesas (ej: 222,223): ").split(",")
publish(opener, [x.strip() for x in ids])
