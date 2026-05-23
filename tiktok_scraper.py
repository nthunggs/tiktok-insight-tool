"""
TikTok Scraper Engine — Playwright-based (không dùng TikTokApi)
Mở trình duyệt thật, chặn API response của TikTok để lấy dữ liệu.
"""

import asyncio
import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────

def safe_get(data, *keys, default=None):
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key, default)
        else:
            return default
    return data if data is not None else default


def format_video(item: dict) -> dict:
    author = safe_get(item, "author", default={})
    stats  = safe_get(item, "stats", default={})
    music  = safe_get(item, "music", default={})
    desc   = safe_get(item, "desc", default="")
    vid    = safe_get(item, "id", default="")
    hashtags = ", ".join(
        w.lstrip("#") for w in desc.split() if w.startswith("#")
    )
    ts = safe_get(item, "createTime", default=0)
    try:
        created = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        created = ""
    return {
        "video_id":        vid,
        "url":             f"https://www.tiktok.com/@{safe_get(author,'uniqueId',default='')}/video/{vid}",
        "description":     desc,
        "hashtags":        hashtags,
        "author_username": safe_get(author, "uniqueId",   default=""),
        "author_name":     safe_get(author, "nickname",   default=""),
        "author_verified": safe_get(author, "verified",   default=False),
        "views":           safe_get(stats,  "playCount",  default=0),
        "likes":           safe_get(stats,  "diggCount",  default=0),
        "comments_count":  safe_get(stats,  "commentCount", default=0),
        "shares":          safe_get(stats,  "shareCount", default=0),
        "music_title":     safe_get(music,  "title",      default=""),
        "music_author":    safe_get(music,  "authorName", default=""),
        "duration_sec":    safe_get(item,   "video", "duration", default=0),
        "created_at":      created,
        "crawled_at":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def format_comment(item: dict, video_url: str = "") -> dict:
    user = safe_get(item, "user", default={})
    ts   = safe_get(item, "createTime", default=safe_get(item, "create_time", default=0))
    try:
        created = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        created = ""
    return {
        "comment_id":      safe_get(item, "cid", default=""),
        "video_url":       video_url,
        "text":            safe_get(item, "text", default=""),
        "author_username": safe_get(user, "uniqueId", default=safe_get(user, "unique_id", default="")),
        "author_name":     safe_get(user, "nickname", default=""),
        "likes":           safe_get(item, "diggCount", default=safe_get(item, "digg_count", default=0)),
        "reply_count":     safe_get(item, "replyCommentTotal",
                                    default=safe_get(item, "reply_comment_total", default=0)),
        "created_at":      created,
        "crawled_at":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ── Cookie builder ──────────────────────────────────────────────

def build_cookies(ms_token: str = None) -> list:
    base = [
        {"name": "tt_chain_token", "value": "placeholder",
         "domain": ".tiktok.com", "path": "/"},
    ]
    if ms_token:
        base.append({
            "name": "msToken", "value": ms_token,
            "domain": ".tiktok.com", "path": "/"
        })
    return base


# ── Core Playwright crawler ─────────────────────────────────────

BROWSER_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_profile")

# Map country → locale + timezone match cho browser fingerprint.
# Khi scrape qua proxy US, browser cũng giả Mỹ → TikTok không thấy mismatch.
COUNTRY_PROFILES = {
    "vn": {"locale": "vi-VN", "timezone": "Asia/Ho_Chi_Minh"},
    "us": {"locale": "en-US", "timezone": "America/New_York"},
    "gb": {"locale": "en-GB", "timezone": "Europe/London"},
    "uk": {"locale": "en-GB", "timezone": "Europe/London"},
    "jp": {"locale": "ja-JP", "timezone": "Asia/Tokyo"},
    "kr": {"locale": "ko-KR", "timezone": "Asia/Seoul"},
    "th": {"locale": "th-TH", "timezone": "Asia/Bangkok"},
    "id": {"locale": "id-ID", "timezone": "Asia/Jakarta"},
    "my": {"locale": "ms-MY", "timezone": "Asia/Kuala_Lumpur"},
    "ph": {"locale": "en-PH", "timezone": "Asia/Manila"},
    "sg": {"locale": "en-SG", "timezone": "Asia/Singapore"},
    "tw": {"locale": "zh-TW", "timezone": "Asia/Taipei"},
    "hk": {"locale": "zh-HK", "timezone": "Asia/Hong_Kong"},
    "in": {"locale": "en-IN", "timezone": "Asia/Kolkata"},
    "au": {"locale": "en-AU", "timezone": "Australia/Sydney"},
    "ca": {"locale": "en-CA", "timezone": "America/Toronto"},
    "de": {"locale": "de-DE", "timezone": "Europe/Berlin"},
    "fr": {"locale": "fr-FR", "timezone": "Europe/Paris"},
    "nl": {"locale": "nl-NL", "timezone": "Europe/Amsterdam"},
    "br": {"locale": "pt-BR", "timezone": "America/Sao_Paulo"},
    "mx": {"locale": "es-MX", "timezone": "America/Mexico_City"},
}

def get_country_profile(country: str = None) -> dict:
    """Pick locale+timezone fit country code (vd 'us', 'jp')."""
    if country:
        c = country.strip().lower()
        if c in COUNTRY_PROFILES:
            return COUNTRY_PROFILES[c]
    env_country = (os.environ.get("TIKTOK_COUNTRY", "") or "").strip().lower()
    if env_country in COUNTRY_PROFILES:
        return COUNTRY_PROFILES[env_country]
    return COUNTRY_PROFILES["vn"]


async def _launch_persistent(playwright, ms_token=None, proxy=None, country=None,
                              data_dir=None):
    """Persistent context — lưu cookies/session giữa lần chạy.

    Args:
      data_dir: override profile dir (default BROWSER_DATA_DIR). Truyền dir khác
                khi launch song song nhiều browser tránh ProcessSingleton conflict.

    ENV overrides:
      TIKTOK_HEADLESS  - "true"/"false" (default false)
      TIKTOK_CHANNEL   - "chrome"/"msedge"/"" (default chrome, bỏ qua khi dùng CloakBrowser)
      TIKTOK_ENGINE    - "cloak" (default, anti-detect mạnh) / "playwright" (fallback)
      TIKTOK_HUMANIZE  - "true" (default) — human-like mouse/keyboard pattern (cloak only)
    """
    profile_dir = data_dir or BROWSER_DATA_DIR
    os.makedirs(profile_dir, exist_ok=True)
    # Clear stale singleton locks (từ crash trước)
    for fn in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        try:
            os.remove(os.path.join(profile_dir, fn))
        except FileNotFoundError:
            pass
        except Exception:
            pass

    headless = os.environ.get("TIKTOK_HEADLESS", "false").lower() == "true"
    channel = os.environ.get("TIKTOK_CHANNEL", "chrome")
    engine = os.environ.get("TIKTOK_ENGINE", "cloak").lower()
    humanize = os.environ.get("TIKTOK_HUMANIZE", "true").lower() == "true"
    profile = get_country_profile(country)
    logger.info(f"Engine: {engine} | Browser profile: locale={profile['locale']} timezone={profile['timezone']}")

    # ─── CloakBrowser path: 58 anti-detect patches, prevents captcha ───
    if engine == "cloak":
        try:
            import cloakbrowser
            cloak_kwargs = dict(
                user_data_dir=profile_dir,
                headless=headless,
                stealth_args=True,
                user_agent=os.environ.get("TIKTOK_USER_AGENT") or None,  # cloak có UA hợp lý mặc định
                locale=profile["locale"],
                timezone=profile["timezone"],
                humanize=humanize,
            )
            if proxy:
                cloak_kwargs["proxy"] = proxy
            ctx = await cloakbrowser.launch_persistent_context_async(**cloak_kwargs)
            if ms_token:
                await ctx.add_cookies(build_cookies(ms_token))
            logger.info("✓ CloakBrowser launched (stealth=on, humanize=%s)", humanize)
            return ctx
        except Exception as e:
            logger.warning(f"CloakBrowser fail → fallback Playwright: {e}")

    kwargs = dict(
        user_data_dir=profile_dir,
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
        ],
        ignore_default_args=["--enable-automation"],
        # User-Agent giả Windows Chrome (cố định, anti-detect) — TikTok ít flag Windows hơn Mac
        # Update string này định kỳ theo Chrome stable version
        user_agent=os.environ.get("TIKTOK_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
        locale=profile["locale"],
        timezone_id=profile["timezone"],
    )
    if channel:
        kwargs["channel"] = channel
    if proxy:
        kwargs["proxy"] = proxy

    try:
        ctx = await playwright.chromium.launch_persistent_context(**kwargs)
    except Exception as e:
        # Fallback: Chromium bundled nếu Chrome thật chưa cài
        if channel and "Executable doesn't exist" in str(e):
            logger.warning(f"Chrome channel '{channel}' không có → fallback Chromium bundled")
            kwargs.pop("channel", None)
            ctx = await playwright.chromium.launch_persistent_context(**kwargs)
        else:
            raise

    if ms_token:
        await ctx.add_cookies(build_cookies(ms_token))
    return ctx


async def _scroll_and_collect(page, collected: list, limit: int,
                               check_url_fragment: str, extract_fn):
    """Cuộn trang, chặn API response, thu thập dữ liệu"""
    done = asyncio.Event()

    async def on_response(response):
        if check_url_fragment not in response.url:
            return
        if len(collected) >= limit:
            done.set()
            return
        try:
            body = await response.json()
            items = (
                body.get("itemList") or
                body.get("aweme_list") or
                body.get("data", {}).get("videos") or
                []
            )
            for item in items:
                if len(collected) < limit:
                    row = extract_fn(item)
                    if row:
                        collected.append(row)
            if not items or len(collected) >= limit:
                done.set()
        except Exception:
            pass

    page.on("response", on_response)

    # Cuộn trang để trigger thêm request
    prev = 0
    stall = 0
    for _ in range(40):
        if len(collected) >= limit:
            break
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1.8)
        if len(collected) == prev:
            stall += 1
            if stall >= 4:
                break
        else:
            stall = 0
            prev = len(collected)


# ── Crawl functions ─────────────────────────────────────────────

async def _try_extract_page_state(page) -> list:
    """Lấy video từ SIGI_STATE / __UNIVERSAL_DATA__ của TikTok"""
    collected = []
    try:
        raw = await page.evaluate("""
            () => {
                // TikTok lưu data trong các biến này
                const candidates = [
                    window.SIGI_STATE,
                    window.__UNIVERSAL_DATA_FOR_REHYDRATION__,
                    window.__NEXT_DATA__,
                ];
                for (const c of candidates) {
                    if (c) return JSON.stringify(c);
                }
                // Fallback: tìm trong <script id="SIGI_STATE">
                const el = document.getElementById('SIGI_STATE') ||
                           document.querySelector('script[id="SIGI_STATE"]');
                if (el) return el.textContent;
                return null;
            }
        """)
        if not raw:
            logger.warning("Không tìm thấy page state")
            return []

        data = json.loads(raw)
        logger.info(f"Page state keys: {list(data.keys())[:10]}")

        # TikTok user profile: data nằm trong ItemModule (dict videoId -> videoData)
        item_module = data.get("ItemModule") or {}
        if item_module:
            logger.info(f"ItemModule: {len(item_module)} videos")
            for vid_data in item_module.values():
                row = format_video(vid_data)
                if row.get("video_id"):
                    collected.append(row)
            return collected

        # Fallback: tìm trong __DEFAULT_SCOPE__ > webapp.user-detail
        scope = data.get("__DEFAULT_SCOPE__", {})
        user_detail = scope.get("webapp.user-detail", {})
        items = (user_detail.get("itemList") or
                 user_detail.get("items") or [])
        if items:
            for item in items:
                collected.append(format_video(item))
            return collected

        # Last resort: tìm bất kỳ object nào có field "stats" + "id"
        def find_deep(obj, depth=0):
            if depth > 8 or len(collected) > 200:
                return
            if isinstance(obj, dict):
                if obj.get("id") and obj.get("stats") and obj.get("desc") is not None:
                    row = format_video(obj)
                    if row.get("video_id"):
                        collected.append(row)
                    return
                for v in obj.values():
                    find_deep(v, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    find_deep(item, depth + 1)

        find_deep(data)

    except Exception as e:
        logger.exception(f"page_state extract error: {e}")
    return collected


async def _collect_from_responses(page, collected: list, limit: int,
                                   fragments: list, extract_fn):
    """Gắn listener TRƯỚC khi goto — dedup theo video_id để không bỏ sót"""
    seen_ids: set = set()

    # Sync với collected ban đầu (nếu đã có data từ page state)
    for item in collected:
        vid = item.get("video_id") or item.get("comment_id", "")
        if vid:
            seen_ids.add(vid)

    async def on_response(response):
        url = response.url
        if not any(f in url for f in fragments):
            return
        logger.info(f"[→] Intercept: {url[:100]}")
        try:
            raw  = await response.body()
            body = json.loads(raw.decode("utf-8"))
            items = (
                body.get("itemList") or
                body.get("aweme_list") or
                body.get("data", {}).get("videos") or
                body.get("item_list") or
                []
            )
            new_count = 0
            for item in items:
                uid = str(item.get("id") or item.get("cid") or "")
                if uid and uid in seen_ids:
                    continue          # bỏ qua trùng lặp
                row = extract_fn(item)
                if row:
                    seen_ids.add(uid)
                    collected.append(row)
                    new_count += 1
            logger.info(f"[✓] +{new_count} mới / {len(items)} tổng từ batch ({url[:70]})")
        except Exception as e:
            logger.warning(f"[!] parse error ({url[:60]}): {e}")

    page.on("response", on_response)
    return on_response


async def crawl_user_videos(username: str, limit: int = 30,
                             ms_token: str = None, proxy: dict = None, country: str = None, data_dir: str = None) -> dict:
    # Xử lý nếu user paste cả URL
    if "tiktok.com/@" in username:
        username = username.split("tiktok.com/@")[-1].split("?")[0].strip("/")
    username = username.lstrip("@").strip()
    collected: list = []

    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            ctx  = await _launch_persistent(pw, ms_token, proxy=proxy, country=country, data_dir=data_dir)
            page = await ctx.new_page()

            # Gắn listener TRƯỚC khi goto
            await _collect_from_responses(
                page, collected, limit,
                fragments=["/api/post/item_list/", "aweme/v1/web/aweme/post/"],
                extract_fn=format_video,
            )

            await page.goto(
                f"https://www.tiktok.com/@{username}",
                wait_until="domcontentloaded", timeout=30000
            )
            await asyncio.sleep(5)

            # Cuộn để load thêm — dừng khi không còn video mới (stall) hoặc đủ limit
            prev = 0
            stall = 0
            for _ in range(25):          # tăng số lần scroll
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)
                if len(collected) == prev:
                    stall += 1
                    if stall >= 4:       # dừng sau 4 lần không có gì mới
                        break
                else:
                    stall = 0
                    prev = len(collected)
                if len(collected) >= limit * 1.1:  # dừng khi vượt 110% limit
                    break

            # Fallback: extract từ page state
            if not collected:
                logger.info("Thử extract từ page state...")
                collected = await _try_extract_page_state(page)

            await page.close()
            await ctx.close()

        if not collected:
            return {"success": False,
                    "error": "Không lấy được dữ liệu. Kiểm tra lại username (vd: gymstore.vn).",
                    "data": []}
        return {"success": True, "data": collected[:limit], "total": len(collected[:limit])}

    except Exception as e:
        logger.exception("crawl_user_videos")
        return {"success": False, "error": str(e), "data": []}


async def crawl_by_hashtag(tag: str, limit: int = 30,
                            ms_token: str = None, proxy: dict = None, country: str = None, data_dir: str = None) -> dict:
    tag = tag.lstrip("#")
    collected: list = []
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            ctx  = await _launch_persistent(pw, ms_token, proxy=proxy, country=country, data_dir=data_dir)
            page = await ctx.new_page()

            await _collect_from_responses(
                page, collected, limit,
                fragments=["/api/challenge/item_list/"],
                extract_fn=format_video,
            )

            await page.goto(
                f"https://www.tiktok.com/tag/{tag}",
                wait_until="domcontentloaded", timeout=30000
            )
            await asyncio.sleep(4)

            prev = 0
            stall = 0
            for _ in range(15):
                if len(collected) >= limit:
                    break
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)
                if len(collected) == prev:
                    stall += 1
                    if stall >= 3:
                        break
                else:
                    stall = 0
                    prev = len(collected)

            if not collected:
                collected = await _try_extract_page_state(page)
            await page.close()
            await ctx.close()

        if not collected:
            return {"success": False, "error": "Không lấy được dữ liệu hashtag.", "data": []}
        return {"success": True, "data": collected[:limit], "total": len(collected[:limit])}

    except Exception as e:
        logger.exception("crawl_by_hashtag")
        return {"success": False, "error": str(e), "data": []}


async def crawl_by_keyword(keyword: str, limit: int = 30,
                            ms_token: str = None, proxy: dict = None, country: str = None, data_dir: str = None) -> dict:
    collected: list = []
    try:
        from playwright.async_api import async_playwright
        import urllib.parse
        async with async_playwright() as pw:
            ctx  = await _launch_persistent(pw, ms_token, proxy=proxy, country=country, data_dir=data_dir)
            page = await ctx.new_page()

            await _collect_from_responses(
                page, collected, limit,
                fragments=["/api/search/general/full/", "/api/search/"],
                extract_fn=format_video,
            )

            q = urllib.parse.quote(keyword)
            await page.goto(
                f"https://www.tiktok.com/search/video?q={q}",
                wait_until="domcontentloaded", timeout=30000
            )
            await asyncio.sleep(4)

            prev = 0
            stall = 0
            for _ in range(15):
                if len(collected) >= limit:
                    break
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)
                if len(collected) == prev:
                    stall += 1
                    if stall >= 3:
                        break
                else:
                    stall = 0
                    prev = len(collected)

            if not collected:
                collected = await _try_extract_page_state(page)
            await page.close()
            await ctx.close()

        if not collected:
            return {"success": False, "error": "Không tìm thấy video với từ khoá này.", "data": []}
        return {"success": True, "data": collected[:limit], "total": len(collected[:limit])}

    except Exception as e:
        logger.exception("crawl_by_keyword")
        return {"success": False, "error": str(e), "data": []}


async def crawl_video_comments(video_url: str, limit: int = 50,
                                ms_token: str = None, proxy: dict = None, country: str = None, data_dir: str = None) -> dict:
    collected: list = []
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            ctx  = await _launch_persistent(pw, ms_token, proxy=proxy, country=country, data_dir=data_dir)
            page = await ctx.new_page()

            async def on_response(response):
                if "/api/comment/list/" not in response.url:
                    return
                logger.info(f"[→] Comment API: {response.url[:80]}")
                try:
                    raw  = await response.body()
                    body = json.loads(raw.decode("utf-8"))
                    for c in body.get("comments", []):
                        if len(collected) < limit:
                            collected.append(format_comment(c, video_url))
                    logger.info(f"[✓] {len(body.get('comments', []))} comments")
                except Exception as e:
                    logger.warning(f"comment parse error: {e}")

            page.on("response", on_response)

            await page.goto(video_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(6)  # SPA hydration

            # 1. Đợi comments section render
            try:
                await page.wait_for_selector(
                    '[data-e2e="comment-level-1"], [data-e2e="search-comment-container"], div[class*="CommentList"], div[class*="DivCommentListContainer"]',
                    timeout=8000,
                )
            except Exception:
                logger.warning("Comments selector không xuất hiện sau 8s")

            # 2. Đóng popup login/banner nếu có
            try:
                await page.evaluate("""
                    () => {
                        const closeBtns = document.querySelectorAll('[data-e2e="modal-close-inner-button"], button[aria-label="Close"], div[role="dialog"] button');
                        closeBtns.forEach(b => { try { b.click(); } catch(_) {} });
                    }
                """)
            except Exception:
                pass

            # 3. Scroll comments section vào view + scroll container nội bộ
            for i in range(25):
                if len(collected) >= limit:
                    break
                try:
                    await page.evaluate("""
                        () => {
                            // Tìm comment container
                            const sels = [
                                '[data-e2e="search-comment-container"]',
                                'div[class*="DivCommentListContainer"]',
                                'div[class*="CommentListContainer"]',
                                'div[class*="CommentList"]',
                            ];
                            let container = null;
                            for (const s of sels) {
                                const el = document.querySelector(s);
                                if (el) { container = el; break; }
                            }
                            if (container) {
                                container.scrollTop = container.scrollHeight;
                                container.scrollIntoView({behavior: 'instant', block: 'end'});
                            }
                            // Scroll cả page để trigger lazy load
                            window.scrollTo(0, document.body.scrollHeight);
                            // Move mouse giả lập user
                            const evt = new MouseEvent('mousemove', {clientX: 500 + Math.random()*200, clientY: 300 + Math.random()*200});
                            document.dispatchEvent(evt);
                        }
                    """)
                except Exception as e:
                    logger.warning(f"scroll error: {e}")
                await asyncio.sleep(2)

            await page.close()
            await ctx.close()

        if not collected:
            return {"success": False,
                    "error": "Không lấy được comment. Video có thể tắt comment, msToken expired, hoặc TikTok rate-limit.",
                    "data": []}
        return {"success": True, "data": collected[:limit], "total": len(collected[:limit])}

    except Exception as e:
        logger.exception("crawl_video_comments")
        return {"success": False, "error": str(e), "data": []}


async def crawl_video_with_comments(video_url: str, comment_limit: int = 50,
                                     ms_token: str = None, proxy: dict = None, country: str = None, data_dir: str = None) -> dict:
    """Load video URL → extract video info từ page state + intercept comments cùng lúc."""
    comments: list = []
    video_info = None
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            ctx = await _launch_persistent(pw, ms_token, proxy=proxy, country=country, data_dir=data_dir)
            page = await ctx.new_page()

            async def on_response(response):
                if "/api/comment/list/" not in response.url:
                    return
                try:
                    raw = await response.body()
                    body = json.loads(raw.decode("utf-8"))
                    for c in body.get("comments", []):
                        if len(comments) < comment_limit:
                            comments.append(format_comment(c, video_url))
                except Exception as e:
                    logger.warning(f"comment parse: {e}")

            page.on("response", on_response)
            await page.goto(video_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(4)

            # Extract video info từ page state
            try:
                raw = await page.evaluate("""
                    () => {
                        const candidates = [
                            window.SIGI_STATE,
                            window.__UNIVERSAL_DATA_FOR_REHYDRATION__,
                            window.__NEXT_DATA__,
                        ];
                        for (const c of candidates) {
                            if (c) return JSON.stringify(c);
                        }
                        const el = document.getElementById('SIGI_STATE') ||
                                   document.querySelector('script[id="SIGI_STATE"]');
                        if (el) return el.textContent;
                        return null;
                    }
                """)
                if raw:
                    data = json.loads(raw)
                    item_module = data.get("ItemModule") or {}
                    for vid_data in item_module.values():
                        video_info = format_video(vid_data)
                        break
                    # Fallback: dig __DEFAULT_SCOPE__
                    if not video_info:
                        scope = data.get("__DEFAULT_SCOPE__", {})
                        detail = scope.get("webapp.video-detail", {})
                        item = (detail.get("itemInfo") or {}).get("itemStruct")
                        if item:
                            video_info = format_video(item)
            except Exception as e:
                logger.warning(f"page state extract: {e}")

            # Scroll để load thêm comment
            for _ in range(15):
                if len(comments) >= comment_limit:
                    break
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(1.5)

            await page.close()
            await ctx.close()

        return {
            "success": bool(video_info or comments),
            "video": video_info,
            "comments": comments,
            "error": None if (video_info or comments) else "Không lấy được data",
        }
    except Exception as e:
        logger.exception("crawl_video_with_comments")
        return {"success": False, "video": None, "comments": [], "error": str(e)}


# ── Reusable page helpers (cho shared context, nhanh hơn) ──────

async def scrape_videos_via_page(page, url: str, fragments: list, limit: int) -> list:
    """Mở URL trong page có sẵn, intercept responses → collect videos."""
    collected = []
    seen_ids = set()

    async def on_response(response):
        if not any(f in response.url for f in fragments):
            return
        try:
            raw = await response.body()
            body = json.loads(raw.decode("utf-8"))
            items = (body.get("itemList") or body.get("aweme_list") or
                     body.get("data", {}).get("videos") or body.get("item_list") or [])
            for item in items:
                uid = str(item.get("id") or "")
                if uid and uid not in seen_ids:
                    row = format_video(item)
                    if row.get("video_id"):
                        seen_ids.add(uid)
                        collected.append(row)
        except Exception:
            pass

    page.on("response", on_response)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        # Cuộn
        prev = 0
        stall = 0
        for _ in range(15):
            if len(collected) >= limit:
                break
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1.5)
            if len(collected) == prev:
                stall += 1
                if stall >= 3:
                    break
            else:
                stall = 0
                prev = len(collected)
        # Fallback page state
        if not collected:
            collected = await _try_extract_page_state(page)
    except Exception as e:
        logger.warning(f"scrape_videos_via_page: {e}")
    return collected[:limit]


async def scrape_comments_via_page(page, video_url: str, limit: int = 50) -> list:
    """Mở video URL trong page có sẵn, intercept /api/comment/list/."""
    collected = []

    async def on_response(response):
        if "/api/comment/list/" not in response.url:
            return
        try:
            raw = await response.body()
            body = json.loads(raw.decode("utf-8"))
            for c in body.get("comments", []):
                if len(collected) < limit:
                    collected.append(format_comment(c, video_url))
        except Exception:
            pass

    page.on("response", on_response)
    try:
        await page.goto(video_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)
        # Close popup modal nếu có
        try:
            await page.evaluate("""
                () => {
                    document.querySelectorAll('[data-e2e="modal-close-inner-button"], button[aria-label="Close"]').forEach(b => { try { b.click(); } catch(_) {} });
                }
            """)
        except Exception:
            pass
        # Scroll comment container
        for _ in range(15):
            if len(collected) >= limit:
                break
            try:
                await page.evaluate("""
                    () => {
                        const sels = ['[data-e2e="search-comment-container"]',
                                      'div[class*="DivCommentListContainer"]',
                                      'div[class*="CommentListContainer"]',
                                      'div[class*="CommentList"]'];
                        for (const s of sels) {
                            const el = document.querySelector(s);
                            if (el) { el.scrollTop = el.scrollHeight; el.scrollIntoView({block: 'end'}); break; }
                        }
                        window.scrollTo(0, document.body.scrollHeight);
                    }
                """)
            except Exception:
                pass
            await asyncio.sleep(1.5)
    except Exception as e:
        logger.warning(f"scrape_comments_via_page: {e}")
    return collected[:limit]


# ── Sync wrappers ───────────────────────────────────────────────

def run_async(coro):
    return asyncio.run(coro)

def scrape_user(username, limit=30, ms_token=None):
    return run_async(crawl_user_videos(username, limit, ms_token))

def scrape_hashtag(tag, limit=30, ms_token=None):
    return run_async(crawl_by_hashtag(tag, limit, ms_token))

def scrape_keyword(keyword, limit=30, ms_token=None):
    return run_async(crawl_by_keyword(keyword, limit, ms_token))

def scrape_comments(video_url, limit=50, ms_token=None):
    return run_async(crawl_video_comments(video_url, limit, ms_token))
