"""
Auth module — session-based admin login + Lark OAuth scaffold.

Users storage: `users.json` (list of {email, password_hash, name, role}).
Sessions: Flask built-in cookie sessions (needs SECRET_KEY).

ENV VARS:
  SECRET_KEY          — Flask session signing key (required)
  ADMIN_EMAIL         — Bootstrap admin (optional, overrides users.json)
  ADMIN_PASSWORD      — Bootstrap admin password (plaintext, hashed on boot)
  LARK_APP_ID         — Lark App ID for OAuth (optional)
  LARK_APP_SECRET     — Lark App Secret (optional)
  LARK_REDIRECT_URI   — Full callback URL (e.g. http://localhost:5001/auth/lark/callback)
  LARK_ALLOWED_EMAILS — Comma-separated whitelist (optional, allow-all if empty)
"""

import json
import os
import secrets
from functools import wraps
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import requests
from flask import jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

USERS_FILE = Path(__file__).parent / "users.json"


# ─── USERS STORE ─────────────────────────────────────────────────────────────

def _load_users() -> list:
    if not USERS_FILE.exists():
        return []
    try:
        return json.loads(USERS_FILE.read_text())
    except Exception:
        return []


def _save_users(users: list) -> None:
    USERS_FILE.write_text(json.dumps(users, indent=2, ensure_ascii=False))


def _find_user(email: str) -> Optional[dict]:
    email = (email or "").strip().lower()
    for u in _load_users():
        if u.get("email", "").lower() == email:
            return u
    return None


def _bootstrap_admin() -> None:
    """Create admin from ADMIN_EMAIL/ADMIN_PASSWORD env if users.json empty."""
    users = _load_users()
    if users:
        return
    email = os.environ.get("ADMIN_EMAIL", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "").strip()
    if email and password:
        users.append({
            "email": email,
            "password_hash": generate_password_hash(password),
            "name": "Admin",
            "role": "admin",
            "source": "bootstrap",
        })
        _save_users(users)
        print(f"[auth] Bootstrapped admin: {email}")
    else:
        # Default admin nếu chưa setup gì cả
        default_email = "admin@example.local"
        default_password = "changeme123"
        users.append({
            "email": default_email,
            "password_hash": generate_password_hash(default_password),
            "name": "Admin",
            "role": "admin",
            "source": "default",
        })
        _save_users(users)
        print(f"[auth] Created default admin: {default_email} / {default_password}")
        print(f"[auth] ⚠️  ĐỔI password ngay bằng cách edit users.json hoặc set ADMIN_PASSWORD env")


# ─── DECORATOR ───────────────────────────────────────────────────────────────

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_email"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized — vui lòng đăng nhập"}), 401
            return redirect(url_for("login_page"))
        return fn(*args, **kwargs)
    return wrapper


# ─── ROUTE REGISTRATION ──────────────────────────────────────────────────────

def init_auth(app):
    app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    _bootstrap_admin()

    @app.route("/login")
    def login_page():
        if session.get("user_email"):
            return redirect(url_for("index"))
        lark_enabled = bool(os.environ.get("LARK_APP_ID") and os.environ.get("LARK_APP_SECRET"))
        return render_template("login.html", lark_enabled=lark_enabled)

    @app.route("/auth/login", methods=["POST"])
    def auth_login():
        data = request.get_json(silent=True) or request.form
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        user = _find_user(email)
        if not user or not check_password_hash(user.get("password_hash", ""), password):
            return jsonify({"error": "Email hoặc password sai"}), 401
        session["user_email"] = user["email"]
        session["user_name"] = user.get("name") or email
        session["user_role"] = user.get("role") or "user"
        return jsonify({"ok": True, "user": _public_user(user)})

    @app.route("/auth/logout", methods=["POST", "GET"])
    def auth_logout():
        session.clear()
        if request.method == "GET":
            return redirect(url_for("login_page"))
        return jsonify({"ok": True})

    @app.route("/auth/me")
    def auth_me():
        if not session.get("user_email"):
            return jsonify({"user": None})
        u = _find_user(session["user_email"])
        return jsonify({"user": _public_user(u) if u else None})

    # ─── User management (admin only) ───
    @app.route("/auth/users", methods=["GET"])
    @login_required
    def list_users():
        if session.get("user_role") != "admin":
            return jsonify({"error": "Chỉ admin"}), 403
        return jsonify({"users": [_public_user(u) for u in _load_users()]})

    @app.route("/auth/users", methods=["POST"])
    @login_required
    def create_user():
        if session.get("user_role") != "admin":
            return jsonify({"error": "Chỉ admin"}), 403
        data = request.get_json() or {}
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        name = data.get("name") or email
        role = data.get("role") or "user"
        if not email or not password:
            return jsonify({"error": "Thiếu email/password"}), 400
        if _find_user(email):
            return jsonify({"error": "Email đã tồn tại"}), 400
        users = _load_users()
        users.append({
            "email": email,
            "password_hash": generate_password_hash(password),
            "name": name, "role": role, "source": "manual",
        })
        _save_users(users)
        return jsonify({"ok": True})

    @app.route("/auth/users/<email>", methods=["DELETE"])
    @login_required
    def delete_user(email):
        if session.get("user_role") != "admin":
            return jsonify({"error": "Chỉ admin"}), 403
        email = email.lower()
        if email == session.get("user_email"):
            return jsonify({"error": "Không thể xóa chính mình"}), 400
        users = [u for u in _load_users() if u.get("email", "").lower() != email]
        _save_users(users)
        return jsonify({"ok": True})

    # ─── Lark OAuth ───
    @app.route("/auth/lark/login")
    def lark_login():
        app_id = os.environ.get("LARK_APP_ID")
        redirect_uri = os.environ.get("LARK_REDIRECT_URI")
        if not app_id or not redirect_uri:
            return "Lark OAuth chưa cấu hình. Set LARK_APP_ID + LARK_APP_SECRET + LARK_REDIRECT_URI.", 500
        state = secrets.token_urlsafe(16)
        session["lark_oauth_state"] = state
        # Request scopes: email + mobile + base info để hỗ trợ cả user chỉ có SĐT
        params = urlencode({
            "app_id": app_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": "contact:user.email:readonly contact:user.base:readonly contact:user.id:readonly",
        })
        return redirect(f"https://accounts.larksuite.com/open-apis/authen/v1/authorize?{params}")

    @app.route("/auth/lark/callback")
    def lark_callback():
        code = request.args.get("code")
        state = request.args.get("state")
        if not code or state != session.pop("lark_oauth_state", None):
            return "Invalid OAuth state", 400
        app_id = os.environ.get("LARK_APP_ID")
        app_secret = os.environ.get("LARK_APP_SECRET")
        try:
            # 1. Get app_access_token
            r1 = requests.post(
                "https://open.larksuite.com/open-apis/auth/v3/app_access_token/internal",
                json={"app_id": app_id, "app_secret": app_secret},
                timeout=10,
            ).json()
            app_token = r1.get("app_access_token")
            if not app_token:
                return f"Lark không cấp app_access_token. Response: {r1}", 500

            # 2. Exchange code → user_access_token + user info
            r2 = requests.post(
                "https://open.larksuite.com/open-apis/authen/v1/access_token",
                headers={"Authorization": f"Bearer {app_token}"},
                json={"grant_type": "authorization_code", "code": code},
                timeout=10,
            ).json()
            data = r2.get("data") or {}
            email = (data.get("email") or "").lower().strip()
            mobile = (data.get("mobile") or "").strip()
            open_id = (data.get("open_id") or "").strip()
            name = data.get("name") or data.get("en_name") or "Lark User"

            # Build identifier — prefer email, fallback to mobile@lark.local hoặc open_id@lark.local
            if email:
                identifier = email
                login_method = "email"
            elif mobile:
                # Normalize mobile: bỏ + và space
                clean_mobile = mobile.replace("+", "").replace(" ", "").replace("-", "")
                identifier = f"{clean_mobile}@lark.local"
                login_method = "mobile"
            elif open_id:
                identifier = f"{open_id}@lark.local"
                login_method = "open_id"
            else:
                return (
                    f"Lark không trả về email/mobile/open_id nào.<br>"
                    f"Response: {data}<br><br>"
                    f"Anh kiểm tra Lark app đã enable scopes:"
                    f"<ul>"
                    f"<li><code>contact:user.email:readonly</code></li>"
                    f"<li><code>contact:user.base:readonly</code> (cho mobile)</li>"
                    f"<li><code>contact:user.id:readonly</code> (cho open_id)</li>"
                    f"</ul>",
                    400,
                )

            # Whitelist check (support email hoặc mobile)
            allow = os.environ.get("LARK_ALLOWED_EMAILS", "").strip()
            if allow:
                whitelist = {e.strip().lower() for e in allow.split(",")}
                if identifier not in whitelist and email not in whitelist and mobile not in whitelist:
                    return f"User {identifier} không trong whitelist", 403

            # Auto-provision user
            if not _find_user(identifier):
                users = _load_users()
                users.append({
                    "email": identifier,
                    "password_hash": "",
                    "name": name,
                    "role": "user",
                    "source": f"lark:{login_method}",
                    "lark_email": email,
                    "lark_mobile": mobile,
                    "lark_open_id": open_id,
                })
                _save_users(users)

            user = _find_user(identifier)
            session["user_email"] = identifier
            session["user_name"] = user.get("name") or name
            session["user_role"] = user.get("role") or "user"
            return redirect(url_for("index"))
        except Exception as e:
            return f"Lark OAuth lỗi: {type(e).__name__}: {e}", 500


def _public_user(u: dict) -> dict:
    if not u:
        return {}
    return {
        "email": u.get("email"),
        "name": u.get("name"),
        "role": u.get("role"),
        "source": u.get("source"),
    }
