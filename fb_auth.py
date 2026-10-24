"""
Facebook token helper untuk ytbot.

Ada 2 jenis token yang dipakai:
- FACEBOOK_USER_ACCESS_TOKEN  : user token dari Graph API Explorer.
- FACEBOOK_PAGE_ACCESS_TOKEN  : page token untuk upload.

Alur refresh otomatis:
  page token expired -> pakai user token -> tukar long-lived user token
  -> ambil page token baru dari /me/accounts -> simpan ke .env
"""

import os
import requests

# Load .env file
def _load_env():
    """Load environment variables from .env file."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        for line in open(env_path):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

_load_env()

API = "https://graph.facebook.com/v18.0"
H = {"User-Agent": "Mozilla/5.0 (Linux; Android) ytbot/1.0"}


def _get(key, default=""):
    """Baca key dari .env atau environment."""
    return os.environ.get(key, default)


def page_id():
    return _get("FACEBOOK_PAGE_ID")


def page_token():
    """Page access token yang dipakai untuk upload."""
    return _get("FACEBOOK_PAGE_ACCESS_TOKEN") or _get("FACEBOOK_ACCESS_TOKEN")


def user_token():
    """User access token (untuk tukar ke long-lived)."""
    return _get("FACEBOOK_USER_ACCESS_TOKEN")


def app_creds():
    return _get("FACEBOOK_APP_ID"), _get("FACEBOOK_APP_SECRET")


def _update_env(key, value):
    """Update .env file dengan key baru."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    
    lines = []
    found = False
    with open(env_path, "r") as f:
        for line in f:
            if line.strip().startswith(key + "="):
                lines.append(f"{key}={value}\n")
                found = True
            else:
                lines.append(line)
    
    if not found:
        lines.append(f"{key}={value}\n")
    
    with open(env_path, "w") as f:
        f.writelines(lines)
    
    # Update environment variable
    os.environ[key] = value


def cek_token(pid=None, tok=None):
    """
    Cek apakah token bisa akses page.
    
    Returns: (ok, pesan)
    """
    pid = pid or page_id()
    tok = tok or page_token()
    if not pid or not tok:
        return False, "FACEBOOK_PAGE_ID / FACEBOOK_PAGE_ACCESS_TOKEN belum diisi"
    try:
        r = requests.get(f"{API}/{pid}",
                         params={"access_token": tok, "fields": "id,name"},
                         headers=H, timeout=20)
        d = r.json()
        if "error" not in d:
            info = d.get("data", d)
            return True, f"✅ Valid - {info.get('name', 'Page')}"
        err = d["error"]
        if err.get("code") == 190:
            return False, "Token expired"
        return False, err.get("message", "")[:100]
    except Exception as e:
        return False, f"Error: {str(e)[:80]}"


def long_lived(user_tok=None):
    """
    Tukar user token -> long-lived user token (60 hari).
    
    Returns: (token, pesan)
    """
    user_tok = user_tok or user_token()
    app_id, app_secret = app_creds()

    if not user_tok:
        return None, "FACEBOOK_USER_ACCESS_TOKEN belum diisi"
    if not app_id or not app_secret:
        return None, "FACEBOOK_APP_ID / FACEBOOK_APP_SECRET belum diisi"

    # Validasi dulu
    chk = requests.get(f"{API}/me", params={
        "access_token": user_tok, "fields": "id,name"}, headers=H, timeout=20).json()
    if "error" in chk:
        return None, f"User token tidak valid: {chk['error'].get('message','')[:100]}"

    try:
        r = requests.get(f"{API}/oauth/access_token", params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": user_tok,
        }, headers=H, timeout=20)
        d = r.json()
    except Exception as e:
        return None, f"Error: {str(e)[:80]}"

    if "error" in d:
        return None, f"Long-lived gagal: {d['error'].get('message','')[:100]}"
    return d.get("access_token"), "✅ Long-lived user token"


def page_token_from(user_or_llt):
    """
    Ambil page access token dari /me/accounts.
    
    Returns: (page_id, page_token, pesan)
    """
    try:
        r = requests.get(f"{API}/me/accounts", params={
            "access_token": user_or_llt,
            "fields": "id,name,access_token,fan_count",
        }, headers=H, timeout=20)
        d = r.json()
    except Exception as e:
        return None, None, f"Error: {str(e)[:80]}"

    if "error" in d:
        return None, None, d["error"].get("message", "")[:100]

    pages = d.get("data", [])
    if not pages:
        return None, None, "Tidak ada page. Perlu scope 'pages_show_list'"

    target = page_id()
    for p in pages:
        if p["id"] == target:
            return p["id"], p.get("access_token"), f"✅ {p.get('name')}"
    # fallback: page pertama
    p = pages[0]
    return p["id"], p.get("access_token"), f"✅ {p.get('name')}"


def get_page_token(pid=None, tok=None, auto_refresh=True):
    """
    Ambil page access token yang siap pakai untuk upload.
    
    Kalau token sekarang masih valid -> pakai.
    Kalau expired & auto_refresh -> try refresh dari user token.
    
    Returns: (token, pesan)
    """
    pid = pid or page_id()
    tok = tok or page_token()

    if not pid or not tok:
        return None, "FACEBOOK_PAGE_ID / FACEBOOK_PAGE_ACCESS_TOKEN belum diisi"

    ok, msg = cek_token(pid, tok)
    if ok:
        return tok, msg

    print(f"[Facebook] Page token: {msg}")

    if not auto_refresh:
        return None, msg

    # Coba refresh dari user token
    ut = user_token()
    if not ut:
        return None, (
            f"{msg}. FACEBOOK_USER_ACCESS_TOKEN belum diisi, "
            "tidak bisa refresh otomatis."
        )

    print("[Facebook] Refresh dari user token...")
    llt, m1 = long_lived(ut)
    if not llt:
        return None, f"{msg} → {m1}"

    new_pid, new_tok, m2 = page_token_from(llt)
    if not new_tok:
        return None, f"{msg} → {m2}"

    _update_env("FACEBOOK_PAGE_ACCESS_TOKEN", new_tok)
    ok2, msg2 = cek_token(new_pid, new_tok)
    if ok2:
        print(f"[Facebook] ✅ Token di-refresh otomatis: {msg2}")
        return new_tok, f"✅ Token di-refresh otomatis ({msg2})"

    return None, f"{msg} → {m2} → {msg2}"


def status():
    """Status ringkas token Facebook."""
    pid, tok = page_id(), page_token()
    ut = user_token()
    app_id, app_secret = app_creds()

    if not pid or not tok:
        return "❌ FACEBOOK_PAGE_ID / FACEBOOK_PAGE_ACCESS_TOKEN belum diisi"

    out = []
    try:
        r = requests.get(f"{API}/{pid}",
                         params={"access_token": tok, "fields": "id,name"},
                         headers=H, timeout=20)
        d = r.json()
        if "error" in d:
            out.append(f"❌ Page token: {d['error'].get('message','')[:90]}")
        else:
            info = d.get("data", d)
            out.append(f"✅ Page: {info.get('name')} (ID: {info.get('id')})")
    except Exception as e:
        out.append(f"❌ {str(e)[:80]}")

    out.append("✅ User token ada" if ut else "⚠️  User token belum diisi (refresh otomatis mati)")
    out.append("✅ App ID/Secret ada" if (app_id and app_secret)
               else "⚠️  App ID/Secret belum diisi (refresh otomatis mati)")
    return "\n   ".join(out)


if __name__ == "__main__":
    print("Status:")
    print("   " + status())
    print()
    tok, msg = get_page_token()
    print("Result:", msg)
    if tok:
        print("Token :", tok[:25], "...")
