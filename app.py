"""
TikTok Research Tool — Flask Backend
Multi-provider AI + 5 source modes (hashtag, URL, user, keyword, related)
+ Multi-session & proxy support
"""

import asyncio
import csv
import io
import os
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


# ─── Load .env (no python-dotenv dep) ────────────────────────────────────────
def _load_dotenv(path: str = ".env") -> None:
    env_path = Path(__file__).parent / path
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.strip()
        # Strip inline comments (chỉ khi không nằm trong quote)
        if v and not (v.startswith('"') or v.startswith("'")):
            # Tìm " #" hoặc "\t#" (có space/tab trước #) để cắt
            for sep in (" #", "\t#"):
                idx = v.find(sep)
                if idx > 0:
                    v = v[:idx].strip()
                    break
        v = v.strip('"').strip("'")
        k = k.strip()
        if k and k not in os.environ:
            os.environ[k] = v


_load_dotenv()


from flask import Flask, jsonify, render_template, request, send_file, session
from TikTokApi import TikTokApi
from auth import init_auth, login_required

app = Flask(__name__)
init_auth(app)
jobs: dict = {}

# Có thể override qua env AI_SYSTEM_PROMPT
SYSTEM_PROMPT = os.environ.get("AI_SYSTEM_PROMPT") or """Bạn là chuyên gia phân tích content marketing trên TikTok.
Nhiệm vụ: phân tích comment TikTok để tìm insight và góc content đang "win" — pain points, emotion triggers, hook ideas, key message, điều nên tránh."""


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def extract_video_id(url: str) -> Optional[str]:
    url = url.strip()
    m = re.search(r"/video/(\d+)", url)
    if m:
        return m.group(1)
    m = re.search(r"tiktok\.com/.*?/(\d{15,25})", url)
    if m:
        return m.group(1)
    return None


def calc_engagement(stats: dict) -> dict:
    views = max(stats.get("playCount", 0), 1)
    likes = stats.get("diggCount", 0)
    comments = stats.get("commentCount", 0)
    shares = stats.get("shareCount", 0)
    return {
        "engagement_rate": round((likes + comments + shares) / views * 100, 2),
        "like_rate": round(likes / views * 100, 2),
        "comment_rate": round(comments / views * 100, 2),
    }


def is_win_video(stats: dict, criteria: dict) -> Tuple[bool, str]:
    views = stats.get("playCount", 0)
    if views < criteria["min_views"]:
        return False, f"views {views:,} < {criteria['min_views']:,}"
    rates = calc_engagement(stats)
    if rates["engagement_rate"] < criteria["min_engagement_rate"]:
        return False, f"engagement {rates['engagement_rate']}% < {criteria['min_engagement_rate']}%"
    if rates["comment_rate"] < criteria["min_comment_rate"]:
        return False, f"comment rate {rates['comment_rate']}% < {criteria['min_comment_rate']}%"
    if rates["like_rate"] < criteria["min_like_rate"]:
        return False, f"like rate {rates['like_rate']}% < {criteria['min_like_rate']}%"
    return True, "WIN"


def build_video_meta(d: dict, source: str) -> dict:
    stats = d.get("stats", {})
    author = d.get("author", {})
    rates = calc_engagement(stats)
    return {
        "video_id": d.get("id", ""),
        "source": source,
        "desc": d.get("desc", "").replace("\n", " ")[:200],
        "author": author.get("uniqueId", ""),
        "play_count": stats.get("playCount", 0),
        "like_count": stats.get("diggCount", 0),
        "comment_count": stats.get("commentCount", 0),
        "share_count": stats.get("shareCount", 0),
        **rates,
        "url": f"https://www.tiktok.com/@{author.get('uniqueId','')}/video/{d.get('id','')}",
    }


# ─── AI PROVIDERS ────────────────────────────────────────────────────────────

def call_ai(provider, model, api_key, system, user, max_tokens=2000):
    if provider == "anthropic":
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text

    if provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model, max_completion_tokens=max_tokens,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return resp.choices[0].message.content or ""

    if provider == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        gmodel = genai.GenerativeModel(model, system_instruction=system)
        resp = gmodel.generate_content(user, generation_config={"max_output_tokens": max_tokens, "temperature": 0.7})
        return resp.text or ""

    raise ValueError(f"Provider không hỗ trợ: {provider}")


# ─── ROUTES ──────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    return render_template(
        "index.html",
        user_email=session.get("user_email"),
        user_name=session.get("user_name"),
        user_role=session.get("user_role"),
        user_avatar=session.get("user_avatar") or "",
    )


@app.route("/api/mstoken/auto", methods=["POST"])
@login_required
def auto_fetch_mstoken():
    """Tự launch CloakBrowser → visit tiktok.com → extract msToken từ cookies."""
    data = request.json or {}
    proxy_cfg = data.get("proxy") or {}
    count = max(1, min(int(data.get("count", 1)), 3))  # 1-3 tokens

    proxy_arg = None
    if proxy_cfg.get("server", "").strip():
        proxy_arg = {
            "server": proxy_cfg["server"] if "://" in proxy_cfg["server"] else f"http://{proxy_cfg['server']}",
            "username": proxy_cfg.get("username", ""),
            "password": proxy_cfg.get("password", ""),
        }

    result = {}
    def run():
        try:
            result.update(asyncio.run(_fetch_mstoken_async(proxy_arg, count)))
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {e}"

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=120)
    if not result:
        return jsonify({"error": "Timeout sau 120s"}), 408
    return jsonify(result)


async def _fetch_mstoken_async(proxy_arg, count=1):
    import cloakbrowser
    from tiktok_scraper import BROWSER_DATA_DIR, get_country_profile

    os.makedirs(BROWSER_DATA_DIR, exist_ok=True)
    profile = get_country_profile(None)

    ctx_kwargs = dict(
        user_data_dir=BROWSER_DATA_DIR,
        headless=True,
        stealth_args=True,
        humanize=False,
        locale=profile["locale"],
        timezone=profile["timezone"],
    )
    if proxy_arg:
        ctx_kwargs["proxy"] = proxy_arg

    tokens = []
    try:
        ctx = await cloakbrowser.launch_persistent_context_async(**ctx_kwargs)
        try:
            for i in range(count):
                page = await ctx.new_page()
                try:
                    await page.goto("https://www.tiktok.com",
                                     wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(4 if i == 0 else 6)  # wait cookie rotate
                    cookies = await ctx.cookies()
                    ms = [c for c in cookies if c.get("name") == "msToken"]
                    ms.sort(key=lambda c: len(c.get("value", "")), reverse=True)
                    if ms:
                        tok = ms[0]["value"]
                        if tok and tok not in tokens:
                            tokens.append(tok)
                finally:
                    await page.close()
        finally:
            await ctx.close()
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    if not tokens:
        return {
            "success": False,
            "error": "Không tìm thấy cookie msToken sau khi visit tiktok.com",
            "suggest": "TikTok có thể chặn IP/region. Thử bật proxy hoặc kiểm tra mạng.",
        }
    return {
        "success": True,
        "tokens": tokens,
        "count": len(tokens),
        "ms_token": tokens[0],  # legacy single token field
    }


@app.route("/api/test-scrape", methods=["POST"])
@login_required
def test_scrape_endpoint():
    """Test 1 video scrape qua msToken + proxy → verify TikTok không block."""
    data = request.json or {}
    ms_token = (data.get("ms_token") or "").strip()
    proxy_cfg = data.get("proxy") or {}
    if not ms_token:
        return jsonify({"error": "Cần msToken"}), 400

    proxies = []
    if proxy_cfg.get("server", "").strip():
        proxies.append({
            "server": proxy_cfg["server"].strip(),
            "username": proxy_cfg.get("username", "").strip(),
            "password": proxy_cfg.get("password", "").strip(),
        })

    result = {}
    def run():
        try:
            result.update(asyncio.run(_test_scrape_async(ms_token, proxies)))
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {e}"

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=180)
    if not result:
        return jsonify({"error": "Timeout sau 180s — TikTok không phản hồi"}), 408
    return jsonify(result)


async def _test_scrape_async(ms_token, proxies):
    """Test 1 video qua TikTokApi + CloakBrowser context."""
    proxy_arg = None
    proxy_country = None
    if proxies:
        p = proxies[0]
        proxy_arg = {
            "server": p["server"] if "://" in p["server"] else f"http://{p['server']}",
            "username": p.get("username", ""),
            "password": p.get("password", ""),
        }

    use_cloak = os.environ.get("TIKTOK_USE_CLOAK", "true").lower() == "true"

    async def cloak_factory(playwright):
        import cloakbrowser
        from tiktok_scraper import get_country_profile, BROWSER_DATA_DIR
        os.makedirs(BROWSER_DATA_DIR, exist_ok=True)
        profile = get_country_profile(proxy_country)
        cloak_kwargs = dict(
            user_data_dir=BROWSER_DATA_DIR,
            headless=os.environ.get("TIKTOK_HEADLESS", "true").lower() != "false",
            stealth_args=True,
            humanize=False,
            locale=profile["locale"],
            timezone=profile["timezone"],
        )
        if proxy_arg:
            cloak_kwargs["proxy"] = proxy_arg
        return await cloakbrowser.launch_persistent_context_async(**cloak_kwargs)

    session_kwargs = dict(
        ms_tokens=[ms_token], num_sessions=1,
        sleep_after=2, headless=True,
    )
    if proxies:
        session_kwargs["proxies"] = proxies
    if use_cloak:
        session_kwargs["browser_context_factory"] = cloak_factory

    try:
        async with TikTokApi() as api:
            await api.create_sessions(**session_kwargs)
            try:
                async for video in api.hashtag(name="fyp").videos(count=1):
                    d = video.as_dict
                    stats = d.get("stats", {})
                    sample = {
                        "video_id": d.get("id"),
                        "views": stats.get("playCount", 0),
                        "likes": stats.get("diggCount", 0),
                        "author": d.get("author", {}).get("uniqueId"),
                        "desc": (d.get("desc") or "")[:80],
                    }
                    cmt_count = 0
                    cmt_err = None
                    try:
                        async for cmt in video.comments(count=5):
                            cmt_count += 1
                    except Exception as e:
                        cmt_err = str(e)
                    sample["comments_fetched"] = cmt_count

                    if cmt_err or cmt_count == 0:
                        return {
                            "success": False, "stage": "comments", "video": sample,
                            "error": cmt_err or "Comment API trả empty",
                            "suggest": "Comment bị block. Thử: msToken mới, proxy residential, hoặc TIKTOK_USE_CLOAK=false để debug.",
                        }
                    return {"success": True, "video": sample}
                return {
                    "success": False, "stage": "list",
                    "error": "TikTok không trả về video nào từ #fyp",
                    "suggest": "msToken sai/hết hạn/region mismatch. Lấy msToken mới.",
                }
            except Exception as e:
                return {
                    "success": False, "stage": "session",
                    "error": f"{type(e).__name__}: {e}",
                    "suggest": "Session bị reject. Verify msToken + proxy + CloakBrowser binary.",
                }
    except Exception as e:
        return {
            "success": False, "stage": "session",
            "error": f"{type(e).__name__}: {e}",
            "suggest": "Setup session fail. Check CloakBrowser binary có tải về chưa.",
        }


@app.route("/api/proxy/check", methods=["POST"])
@login_required
def check_proxy():
    """Test outbound IP qua proxy (hoặc direct) → trả về country + city."""
    import requests as _req
    data = request.json or {}
    server = (data.get("server") or "").strip()
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    proxies = None
    if server:
        url = server
        if not url.startswith(("http://", "https://", "socks5://")):
            url = f"http://{url}"
        if username:
            scheme, rest = url.split("://", 1)
            url = f"{scheme}://{username}:{password}@{rest}"
        proxies = {"http": url, "https": url}

    try:
        r = _req.get("https://ipinfo.io/json", proxies=proxies, timeout=10)
        d = r.json()
        return jsonify({
            "ip": d.get("ip"),
            "country": (d.get("country") or "").lower(),
            "country_name": _country_name(d.get("country", "")),
            "city": d.get("city"),
            "region": d.get("region"),
            "org": d.get("org"),
        })
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 400


_COUNTRY_NAMES = {
    "VN": "Việt Nam", "US": "United States", "GB": "United Kingdom", "JP": "Japan",
    "KR": "South Korea", "TH": "Thailand", "ID": "Indonesia", "PH": "Philippines",
    "MY": "Malaysia", "SG": "Singapore", "AU": "Australia", "DE": "Germany",
    "FR": "France", "NL": "Netherlands", "CA": "Canada", "BR": "Brazil",
    "MX": "Mexico", "TW": "Taiwan", "HK": "Hong Kong", "IN": "India",
    "RU": "Russia", "CN": "China", "IT": "Italy", "ES": "Spain",
}

def _country_name(code: str) -> str:
    return _COUNTRY_NAMES.get((code or "").upper(), code.upper() or "Unknown")


@app.route("/api/models", methods=["POST"])
@login_required
def list_models():
    data = request.json or {}
    provider = data.get("provider", "")
    api_key = data.get("api_key", "").strip()
    if not api_key:
        return jsonify({"error": "Cần API key"}), 400
    try:
        if provider == "anthropic":
            from anthropic import Anthropic
            client = Anthropic(api_key=api_key)
            models = [{"id": m.id, "label": getattr(m, "display_name", None) or m.id} for m in client.models.list().data]
            return jsonify({"models": models})

        if provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            chat_prefixes = ("gpt-", "o1", "o3", "o4", "chatgpt-")
            excluded = ("embedding", "whisper", "tts", "dall-e", "audio", "image", "realtime", "transcribe", "moderation", "-search-", "-ft-")
            models = []
            for m in client.models.list().data:
                if any(m.id.startswith(p) for p in chat_prefixes) and not any(x in m.id for x in excluded):
                    models.append({"id": m.id, "label": m.id})
            models.sort(key=lambda x: x["id"])
            return jsonify({"models": models})

        if provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            models = []
            for m in genai.list_models():
                if "generateContent" in m.supported_generation_methods:
                    mid = m.name.replace("models/", "")
                    models.append({"id": mid, "label": getattr(m, "display_name", None) or mid})
            models.sort(key=lambda x: x["id"], reverse=True)
            return jsonify({"models": models})

        return jsonify({"error": "Provider không hỗ trợ"}), 400
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 400


@app.route("/api/scrape", methods=["POST"])
@login_required
def start_scrape():
    data = request.json or {}

    # ms_tokens: array (mỗi dòng 1 token)
    ms_tokens_raw = data.get("ms_tokens", "")
    if isinstance(ms_tokens_raw, str):
        ms_tokens = [t.strip() for t in ms_tokens_raw.split("\n") if t.strip()]
    elif isinstance(ms_tokens_raw, list):
        ms_tokens = [str(t).strip() for t in ms_tokens_raw if str(t).strip()]
    else:
        ms_tokens = []

    num_sessions = max(1, min(int(data.get("num_sessions", 1)), 3))

    # Proxy (optional)
    proxy_cfg = data.get("proxy") or {}
    proxies = []
    proxy_country = ""
    if proxy_cfg.get("server", "").strip():
        proxies.append({
            "server": proxy_cfg["server"].strip(),
            "username": proxy_cfg.get("username", "").strip(),
            "password": proxy_cfg.get("password", "").strip(),
        })
        proxy_country = proxy_cfg.get("country", "").strip().lower()

    # Sources
    sources_in = data.get("sources") or {}
    sources = {
        "hashtags":      [h.strip().lstrip("#") for h in sources_in.get("hashtags", []) if str(h).strip()],
        "video_urls":    [u.strip() for u in sources_in.get("video_urls", []) if str(u).strip()],
        "usernames":     [u.strip().lstrip("@") for u in sources_in.get("usernames", []) if str(u).strip()],
        "keywords":      [k.strip() for k in sources_in.get("keywords", []) if str(k).strip()],
        "related_seeds": [u.strip() for u in sources_in.get("related_seeds", []) if str(u).strip()],
    }
    related_count = max(5, min(int(data.get("related_count", 20)), 50))

    max_videos = max(1, min(int(data.get("max_videos", 30)), 100))
    max_comments = max(1, min(int(data.get("max_comments", 80)), 200))
    dedup_videos = bool(data.get("dedup_videos", True))

    criteria = {
        "min_views": int(data.get("min_views", 100_000)),
        "min_engagement_rate": float(data.get("min_engagement_rate", 5.0)),
        "min_comment_rate": float(data.get("min_comment_rate", 0.3)),
        "min_like_rate": float(data.get("min_like_rate", 5.0)),
    }

    # Validate
    if not ms_tokens:
        return jsonify({"error": "Thiếu ms_token"}), 400
    if num_sessions > len(ms_tokens):
        return jsonify({"error": f"Cần {num_sessions} ms_token cho {num_sessions} session"}), 400
    if not any(sources.values()):
        return jsonify({"error": "Phải bật & nhập dữ liệu cho ít nhất 1 nguồn"}), 400

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "running", "logs": [], "comments": [], "videos": [],
        "report": None, "created_at": datetime.now().isoformat(),
    }

    thread = threading.Thread(
        target=lambda: asyncio.run(_scrape_job(
            job_id, ms_tokens, num_sessions, proxies, proxy_country, sources,
            related_count, max_videos, max_comments, criteria, dedup_videos,
        )),
        daemon=True,
    )
    thread.start()
    return jsonify({"job_id": job_id})


@app.route("/api/jobs/<job_id>")
@login_required
def get_job(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job không tồn tại"}), 404
    return jsonify({
        "status": job["status"], "logs": job["logs"],
        "video_count": len(job["videos"]), "comment_count": len(job["comments"]),
        "report": job.get("report"), "error": job.get("error"),
        "analysis_error": job.get("analysis_error"),
    })


@app.route("/api/analyze/<job_id>", methods=["POST"])
@login_required
def analyze_job(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job không tồn tại"}), 404
    if job["status"] != "done":
        return jsonify({"error": "Scraping chưa hoàn tất"}), 400

    data = request.json or {}
    provider = data.get("provider", "anthropic")
    model = data.get("model", "")
    api_key = data.get("api_key", "")

    if not api_key.strip():
        return jsonify({"error": f"Thiếu API key cho {provider}"}), 400
    if not model.strip():
        return jsonify({"error": "Chưa chọn model"}), 400

    job["status"] = "analyzing"
    job["ai_config"] = {"provider": provider, "model": model, "api_key": api_key}

    thread = threading.Thread(target=lambda: _analyze_job(job_id), daemon=True)
    thread.start()
    return jsonify({"status": "analyzing"})


@app.route("/api/jobs/<job_id>/download/<file_type>")
@login_required
def download(job_id, file_type):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job không tồn tại"}), 404

    if file_type == "csv":
        output = io.StringIO()
        comments = job["comments"]
        if comments:
            writer = csv.DictWriter(output, fieldnames=comments[0].keys())
            writer.writeheader()
            writer.writerows(comments)
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode("utf-8-sig")),
            mimetype="text/csv", as_attachment=True,
            download_name=f"tiktok_comments_{job_id}.csv",
        )

    if file_type == "report":
        report = job.get("report")
        if not report:
            return jsonify({"error": "Chưa có báo cáo"}), 400
        return send_file(
            io.BytesIO(report.encode("utf-8")),
            mimetype="text/markdown", as_attachment=True,
            download_name=f"insight_report_{job_id}.md",
        )

    return jsonify({"error": "Loại file không hợp lệ"}), 400


# ─── BACKGROUND TASKS ────────────────────────────────────────────────────────

FLAG_MAP = {
    "vn": "🇻🇳", "us": "🇺🇸", "uk": "🇬🇧", "sg": "🇸🇬", "jp": "🇯🇵", "kr": "🇰🇷",
    "th": "🇹🇭", "id": "🇮🇩", "my": "🇲🇾", "ph": "🇵🇭", "tw": "🇹🇼", "hk": "🇭🇰",
    "in": "🇮🇳", "au": "🇦🇺", "ca": "🇨🇦", "de": "🇩🇪", "fr": "🇫🇷", "nl": "🇳🇱",
    "br": "🇧🇷", "mx": "🇲🇽",
}


def _scraper_to_meta(v: dict, source: str) -> dict:
    """Convert tiktok_scraper format → existing build_video_meta format."""
    stats = {
        "playCount": v.get("views", 0),
        "diggCount": v.get("likes", 0),
        "commentCount": v.get("comments_count", 0),
        "shareCount": v.get("shares", 0),
    }
    rates = calc_engagement(stats)
    return {
        "video_id": v.get("video_id", ""),
        "source": source,
        "desc": (v.get("description", "") or "").replace("\n", " ")[:200],
        "author": v.get("author_username", ""),
        "play_count": stats["playCount"],
        "like_count": stats["diggCount"],
        "comment_count": stats["commentCount"],
        "share_count": stats["shareCount"],
        **rates,
        "url": v.get("url", ""),
    }


def _scraper_stats(v: dict) -> dict:
    return {
        "playCount": v.get("views", 0),
        "diggCount": v.get("likes", 0),
        "commentCount": v.get("comments_count", 0),
        "shareCount": v.get("shares", 0),
    }


async def _scrape_job(job_id, ms_tokens, num_sessions, proxies, proxy_country, sources,
                       related_count, max_videos, max_comments, criteria, dedup_videos=True):
    job = jobs[job_id]
    job["_seen_video_ids"] = set()

    def log(msg):
        job["logs"].append(msg)

    if dedup_videos:
        log("🔁 Dedup ON — bỏ qua video xuất hiện ở nhiều nguồn")

    try:
        log(f"⚙️  WIN: ≥{criteria['min_views']:,}v | eng ≥{criteria['min_engagement_rate']}% | "
            f"cmt ≥{criteria['min_comment_rate']}% | like ≥{criteria['min_like_rate']}%")
        if proxies:
            flag = FLAG_MAP.get(proxy_country, "🌐")
            label = proxy_country.upper() if proxy_country else "?"
            proxy_str = f"✓ {flag} {label} via {proxies[0]['server']}"
            proxy_arg = {
                "server": proxies[0]["server"] if "://" in proxies[0]["server"]
                          else f"http://{proxies[0]['server']}",
                "username": proxies[0].get("username", ""),
                "password": proxies[0].get("password", ""),
            }
        else:
            proxy_str = "✗ direct"
            proxy_arg = None

        engine_channel = os.environ.get("TIKTOK_CHANNEL", "chrome")
        engine_headless = os.environ.get("TIKTOK_HEADLESS", "false").lower() == "true"
        log(f"📡 Engine: Playwright + persistent context | channel={engine_channel or 'chromium'} | headless={engine_headless} | Proxy: {proxy_str}")
        if proxy_country:
            log(f"🌍 Browser locale + timezone tự match country: {FLAG_MAP.get(proxy_country, '🌐')} {proxy_country.upper()}")
        else:
            log("🌍 Browser locale: 🇻🇳 vi-VN (default, không có proxy country)")
        log(f"🔑 ms_tokens: {len(ms_tokens)} (engine dùng token đầu tiên, multi-session sẽ wire sau)")

        # First token used as primary; keyword fallback (Playwright) cần single token
        ms_token = ms_tokens[0] if ms_tokens else None

        # ─── TikTokApi engine + CloakBrowser context factory (anti-detect mạnh) ───
        use_cloak = os.environ.get("TIKTOK_USE_CLOAK", "true").lower() == "true"

        async def cloak_factory(playwright):
            """Factory: TikTokApi sẽ dùng context này thay vì Chromium bundled."""
            import cloakbrowser
            from tiktok_scraper import get_country_profile, BROWSER_DATA_DIR
            os.makedirs(BROWSER_DATA_DIR, exist_ok=True)
            profile = get_country_profile(proxy_country)
            cloak_kwargs = dict(
                user_data_dir=BROWSER_DATA_DIR,
                headless=os.environ.get("TIKTOK_HEADLESS", "true").lower() != "false",
                stealth_args=True,
                humanize=os.environ.get("TIKTOK_HUMANIZE", "false").lower() == "true",
                locale=profile["locale"],
                timezone=profile["timezone"],
            )
            if proxy_arg:
                cloak_kwargs["proxy"] = proxy_arg
            return await cloakbrowser.launch_persistent_context_async(**cloak_kwargs)

        session_kwargs = {
            "ms_tokens": ms_tokens,
            "num_sessions": num_sessions,
            "sleep_after": 3,
            "headless": True,  # ignored khi browser_context_factory được set
        }
        if proxies:
            session_kwargs["proxies"] = proxies
        if use_cloak:
            session_kwargs["browser_context_factory"] = cloak_factory
            log(f"🥷 Engine: TikTokApi + CloakBrowser (58 anti-detect patches, prevents captcha)")
        else:
            log(f"📡 Engine: TikTokApi + Playwright Chromium bundled")
        log(f"🔑 ms_tokens: {len(ms_tokens)} | Sessions: {num_sessions} | Proxy: {proxy_str}")

        async with TikTokApi() as api:
            await api.create_sessions(**session_kwargs)

            # 1. URL mode (no WIN filter — user explicitly chose)
            if sources["video_urls"]:
                log(f"🎯 URL mode: {len(sources['video_urls'])} video")
                seen = job.get("_seen_video_ids")
                for url in sources["video_urls"]:
                    vid = extract_video_id(url)
                    if not vid:
                        log(f"  ⚠️  URL không hợp lệ: {url}")
                        continue
                    if seen is not None and vid in seen:
                        log(f"  🔁 Skip duplicate v_id={vid}")
                        continue
                    try:
                        video = api.video(id=vid)
                        info = await video.info()
                        if seen is not None:
                            seen.add(vid)
                        meta = build_video_meta(info, source=f"url:{url[:50]}")
                        job["videos"].append(meta)
                        log(f"  ✅ {vid}: {meta['play_count']:,}v | eng {meta['engagement_rate']}%")
                        await _scrape_comments(video, meta, job, max_comments, log)
                    except Exception as e:
                        log(f"  ❌ {vid}: {e}")

            # 2. Hashtag mode
            for tag in sources["hashtags"]:
                log(f"🔍 #{tag} (max {max_videos})...")
                await _scrape_videos_generator(
                    api.hashtag(name=tag).videos(count=max_videos),
                    f"#{tag}", max_comments, criteria, job, log,
                )

            # 3. User mode
            for username in sources["usernames"]:
                log(f"👤 @{username} (max {max_videos})...")
                try:
                    user = api.user(username=username)
                    try:
                        uinfo = await user.info()
                        if isinstance(uinfo, dict):
                            ustats = uinfo.get("stats", {}) or uinfo.get("userInfo", {}).get("stats", {})
                            if ustats:
                                log(f"   ℹ️  {ustats.get('followerCount', 0):,} followers | "
                                    f"{ustats.get('heartCount', 0):,} hearts")
                    except Exception:
                        pass
                    await _scrape_videos_generator(
                        user.videos(count=max_videos),
                        f"@{username}", max_comments, criteria, job, log,
                        skip_win_filter=True,  # User mode = user chủ động chọn → lấy tất
                    )
                except Exception as e:
                    log(f"  ❌ @{username}: {e}")

            # 4. Keyword search — TikTokApi v7 không support search video
            #    → fallback Playwright engine (response interception)
            for kw in sources["keywords"]:
                log(f"🔎 search '{kw}' (max {max_videos}) — Playwright fallback...")
                try:
                    from tiktok_scraper import crawl_by_keyword, BROWSER_DATA_DIR
                    # Profile riêng cho keyword fallback tránh conflict với TikTokApi/CloakBrowser
                    kw_profile = os.path.join(BROWSER_DATA_DIR + "_keyword")
                    res = await crawl_by_keyword(
                        kw, limit=max_videos, ms_token=ms_token,
                        proxy=proxy_arg, country=proxy_country, data_dir=kw_profile,
                    )
                    if not res.get("success"):
                        log(f"  ❌ search '{kw}': {res.get('error')}")
                        continue
                    checked = won = 0
                    seen = job.get("_seen_video_ids")
                    for v in res["data"]:
                        checked += 1
                        vid = str(v.get("video_id", "") or "")
                        if seen is not None and vid and vid in seen:
                            log(f"  🔁 Skip duplicate v_id={vid}")
                            continue
                        stats = _scraper_stats(v)
                        ok, reason = is_win_video(stats, criteria)
                        if not ok:
                            log(f"  ⏭️  v{checked} ({stats['playCount']:,}v): {reason}")
                            continue
                        won += 1
                        if seen is not None and vid:
                            seen.add(vid)
                        meta = _scraper_to_meta(v, source=f"search:{kw[:30]}")
                        job["videos"].append(meta)
                        desc_preview = (meta.get("desc", "") or "")[:80]
                        log(f"  ✅ WIN {won} @{meta['author']}: {meta['play_count']:,}v | eng {meta['engagement_rate']}% — {desc_preview}")
                        # Comments via TikTokApi (fast)
                        try:
                            video = api.video(id=v["video_id"])
                            await _scrape_comments(video, meta, job, max_comments, log)
                        except Exception as e:
                            log(f"      ⚠️ Comment error: {e}")
                    log(f"  📊 search:{kw[:30]}: {won}/{checked} WIN")
                except Exception as e:
                    log(f"  ❌ search '{kw}': {type(e).__name__}: {e}")

            # 5. Related videos
            for seed_url in sources["related_seeds"]:
                vid = extract_video_id(seed_url)
                if not vid:
                    log(f"  ⚠️  Seed URL không hợp lệ: {seed_url}")
                    continue
                log(f"🌱 related từ seed {vid} (max {related_count})...")
                try:
                    seed = api.video(id=vid)
                    await _scrape_videos_generator(
                        seed.related_videos(count=related_count),
                        f"related:{vid}", max_comments, criteria, job, log,
                    )
                except Exception as e:
                    log(f"  ❌ related {vid}: {e}")

        job["status"] = "done"
        log(f"🎉 Hoàn tất! {len(job['videos'])} video WIN | {len(job['comments'])} comment")

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        log(f"❌ Lỗi nghiêm trọng: {e}")


async def _scrape_videos_generator(video_iter, source_label, max_comments, criteria,
                                     job, log, skip_win_filter=False):
    """Hashtag/keyword/related: filter WIN. URL/User mode: skip filter (user chủ động chọn)."""
    checked = won = 0
    seen = job.get("_seen_video_ids")
    try:
        async for video in video_iter:
            d = video.as_dict
            stats = d.get("stats", {})
            checked += 1
            vid = str(d.get("id", "") or "")
            if seen is not None and vid and vid in seen:
                log(f"  🔁 Skip duplicate v_id={vid} (đã scrape từ source khác)")
                continue
            if not skip_win_filter:
                ok, reason = is_win_video(stats, criteria)
                if not ok:
                    log(f"  ⏭️  {reason}")
                    continue
            won += 1
            if seen is not None and vid:
                seen.add(vid)
            meta = build_video_meta(d, source=source_label)
            job["videos"].append(meta)
            desc_preview = (meta.get("desc", "") or "")[:80]
            label = "ALL" if skip_win_filter else "WIN"
            log(f"  ✅ {label} {won} @{meta['author']}: {meta['play_count']:,}v | eng {meta['engagement_rate']}% — {desc_preview}")
            await _scrape_comments(video, meta, job, max_comments, log)
        if skip_win_filter:
            log(f"  📊 {source_label}: {won} video (no WIN filter)")
        else:
            log(f"  📊 {source_label}: {won}/{checked} WIN")
    except Exception as e:
        log(f"  ❌ {source_label}: {e}")


async def _scrape_comments(video, meta, job, max_comments, log):
    count = 0
    try:
        async for comment in video.comments(count=max_comments):
            c = comment.as_dict
            job["comments"].append({
                **meta,
                "comment_text": c.get("text", "").replace("\n", " "),
                "comment_likes": c.get("diggCount", 0),
                "comment_user": c.get("user", {}).get("uniqueId", ""),
            })
            count += 1
        log(f"      💬 {count} comment")
    except Exception as e:
        log(f"      ⚠️ Comment error: {e}")


async def _process_videos_shared(videos, source_label, criteria, job, log, comments_fn):
    """Filter WIN + dùng comments_fn (shared context tab) lấy comment."""
    checked = won = 0
    for v in videos:
        checked += 1
        stats = _scraper_stats(v)
        ok, reason = is_win_video(stats, criteria)
        if not ok:
            log(f"  ⏭️  v{checked} ({stats['playCount']:,}v): {reason}")
            continue
        won += 1
        meta = _scraper_to_meta(v, source_label)
        job["videos"].append(meta)
        log(f"  ✅ WIN {won}: {meta['play_count']:,}v | eng {meta['engagement_rate']}% | cmt {meta['comment_rate']}%")
        n = await comments_fn(meta)
        log(f"      💬 {n} comment")

    if checked == 0:
        log(f"  ⚠️  {source_label}: KHÔNG có video nào trả về")
    elif won == 0:
        log(f"  ⚠️  {source_label}: {checked} video đều bị filter bởi WIN criteria → hạ ngưỡng xuống")
    else:
        log(f"  📊 {source_label}: {won}/{checked} WIN")


async def _process_scraped_videos(videos, source_label, max_comments, criteria,
                                    job, log, ms_token, proxy_arg, country=None):
    """Filter WIN + scrape comment cho mỗi video pass."""
    checked = won = 0
    for v in videos:
        checked += 1
        stats = _scraper_stats(v)
        ok, reason = is_win_video(stats, criteria)
        views = stats["playCount"]
        if not ok:
            log(f"  ⏭️  v{checked} ({views:,}v): {reason}")
            continue
        won += 1
        meta = _scraper_to_meta(v, source_label)
        job["videos"].append(meta)
        log(f"  ✅ WIN {won}: {meta['play_count']:,}v | eng {meta['engagement_rate']}% | cmt {meta['comment_rate']}%")

        # Scrape comments cho video này
        if meta["url"]:
            cres = await crawl_video_comments(meta["url"], limit=max_comments,
                                                ms_token=ms_token, proxy=proxy_arg, country=country)
            if cres["success"]:
                for c in cres["data"]:
                    job["comments"].append({
                        **meta,
                        "comment_text": (c.get("text", "") or "").replace("\n", " "),
                        "comment_likes": c.get("likes", 0),
                        "comment_user": c.get("author_username", ""),
                    })
                log(f"      💬 {len(cres['data'])} comment")
            else:
                log(f"      ⚠️ Comment error: {cres.get('error')}")

    if checked == 0:
        log(f"  ⚠️  {source_label}: KHÔNG có video nào trả về")
    elif won == 0:
        log(f"  ⚠️  {source_label}: {checked} video đều bị filter bởi WIN criteria → hạ ngưỡng xuống")
    else:
        log(f"  📊 {source_label}: {won}/{checked} WIN")


def _analyze_job(job_id):
    job = jobs[job_id]
    comments = job["comments"]
    cfg = job.get("ai_config", {})
    provider = cfg.get("provider", "anthropic")
    model = cfg.get("model", "")
    api_key = cfg.get("api_key", "")

    def log(msg):
        job["logs"].append(msg)

    try:
        chunks = [comments[i:i + 200] for i in range(0, len(comments), 200)]
        log(f"🤖 Phân tích {len(chunks)} batch với {provider}/{model}...")

        chunk_results = []
        for i, chunk in enumerate(chunks, 1):
            log(f"  📊 Batch {i}/{len(chunks)}...")
            lines = []
            for r in chunk:
                text = r.get("comment_text", "").strip()
                if text:
                    views = int(r.get("play_count", 0))
                    likes = r.get("comment_likes", 0)
                    src = r.get("source", "")
                    lines.append(f"[{src} | {views:,}v | {likes}❤] {text}")

            result = call_ai(
                provider=provider, model=model, api_key=api_key,
                system=SYSTEM_PROMPT,
                user=f"""Phân tích batch {i}/{len(chunks)} comment TikTok gym/fitness (đã lọc WIN).
Bullet points ngắn gọn:
• Pain points nổi bật
• Emotion triggers
• Câu hỏi hay gặp
• Patterns engagement cao

---
{chr(10).join(lines)}""",
                max_tokens=1500,
            )
            chunk_results.append(result)

        log("🎯 Tổng hợp báo cáo cuối...")
        total_videos = len(set(r.get("video_id", "") for r in comments))
        sources_used = sorted(set(r.get("source", "") for r in comments))

        # Build sample list videos cho AI biết exactly scrape từ đâu
        sample_videos = []
        seen_vids = set()
        for r in comments:
            vid = r.get("video_id", "")
            if vid and vid not in seen_vids:
                seen_vids.add(vid)
                sample_videos.append({
                    "source": r.get("source", ""),
                    "author": r.get("author", ""),
                    "desc": (r.get("desc", "") or "")[:100],
                    "views": r.get("play_count", 0),
                })
                if len(sample_videos) >= 15:
                    break
        videos_block = "\n".join(
            f"  • [{v['source']}] @{v['author']} ({v['views']:,}v): {v['desc']}"
            for v in sample_videos
        )

        report = call_ai(
            provider=provider, model=model, api_key=api_key,
            system=SYSTEM_PROMPT,
            user=f"""Tổng hợp insight từ {len(chunk_results)} batch.
Dữ liệu: {len(comments)} comment | {total_videos} video WIN | {len(sources_used)} nguồn ({', '.join(sources_used[:8])}{'...' if len(sources_used)>8 else ''})

DANH SÁCH VIDEO ĐƯỢC SCRAPE (chỉ phân tích insight liên quan đến CHỦ ĐỀ của các video này):
{videos_block}

QUAN TRỌNG: chỉ rút insight về CHỦ ĐỀ trong video desc + nguồn ở trên. KHÔNG suy diễn về niche khác. Nếu comment đa số về A nhưng video chủ đề B → ưu tiên insight B.

Format:

# INSIGHT REPORT — TIKTOK
> {len(comments)} comment | {total_videos} video WIN | Sources: {', '.join(sources_used[:5])} | AI: {provider}/{model}

## 1. TOP PAIN POINTS (xếp theo phổ biến)

## 2. EMOTION TRIGGERS PHỔ BIẾN
(từ/cụm từ gây reaction mạnh + ví dụ)

## 3. GÓC CONTENT ĐANG WIN
(kèm ví dụ comment thực tế)

## 4. HOOK IDEAS (5–8 hook dùng được luôn)

## 5. KEY MESSAGE

## 6. NÊN TRÁNH

---
{chr(10).join(chunk_results)}""",
            max_tokens=4000,
        )

        job["report"] = report
        job["status"] = "analyzed"
        log("✅ Báo cáo hoàn tất!")

        if "ai_config" in job:
            job["ai_config"]["api_key"] = "***cleared***"

    except Exception as e:
        job["status"] = "done"
        job["analysis_error"] = str(e)
        log(f"❌ Lỗi phân tích: {e}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)
