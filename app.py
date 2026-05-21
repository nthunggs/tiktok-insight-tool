"""
TikTok Research Tool — Flask Backend
Multi-provider AI: Anthropic / OpenAI / Gemini
"""

import asyncio
import csv
import io
import os
import re
import threading
import uuid
from datetime import datetime
from typing import Optional, Tuple

from flask import Flask, jsonify, render_template, request, send_file
from TikTokApi import TikTokApi

app = Flask(__name__)
jobs: dict = {}

SYSTEM_PROMPT = """Bạn là chuyên gia phân tích content marketing cho thị trường fitness/gym Việt Nam.
Nhiệm vụ: phân tích comment TikTok để tìm insight và góc content đang "win" cho sản phẩm Gymstore."""


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

def call_ai(provider: str, model: str, api_key: str, system: str, user: str, max_tokens: int = 2000) -> str:
    """Universal AI caller."""
    if provider == "anthropic":
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text

    if provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            max_completion_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""

    if provider == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        gmodel = genai.GenerativeModel(model, system_instruction=system)
        resp = gmodel.generate_content(
            user,
            generation_config={"max_output_tokens": max_tokens, "temperature": 0.7},
        )
        return resp.text or ""

    raise ValueError(f"Provider không hỗ trợ: {provider}")


# ─── ROUTES ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/models", methods=["POST"])
def list_models():
    """Fetch danh sách model thật từ provider dùng API key của user."""
    data = request.json or {}
    provider = data.get("provider", "")
    api_key = data.get("api_key", "").strip()

    if not api_key:
        return jsonify({"error": "Cần API key"}), 400

    try:
        if provider == "anthropic":
            from anthropic import Anthropic
            client = Anthropic(api_key=api_key)
            models = []
            for m in client.models.list().data:
                models.append({
                    "id": m.id,
                    "label": getattr(m, "display_name", None) or m.id,
                })
            return jsonify({"models": models})

        if provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            chat_prefixes = ("gpt-", "o1", "o3", "o4", "chatgpt-")
            excluded_terms = (
                "embedding", "whisper", "tts", "dall-e", "audio", "image",
                "realtime", "transcribe", "moderation", "-search-", "-ft-",
            )
            models = []
            for m in client.models.list().data:
                mid = m.id
                if any(mid.startswith(p) for p in chat_prefixes) and \
                   not any(x in mid for x in excluded_terms):
                    models.append({"id": mid, "label": mid})
            models.sort(key=lambda x: x["id"])
            return jsonify({"models": models})

        if provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            models = []
            for m in genai.list_models():
                if "generateContent" in m.supported_generation_methods:
                    mid = m.name.replace("models/", "")
                    label = getattr(m, "display_name", None) or mid
                    models.append({"id": mid, "label": label})
            models.sort(key=lambda x: x["id"], reverse=True)
            return jsonify({"models": models})

        return jsonify({"error": "Provider không hỗ trợ"}), 400

    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 400


@app.route("/api/scrape", methods=["POST"])
def start_scrape():
    data = request.json or {}
    ms_token = data.get("ms_token", "").strip()
    source_mode = data.get("source_mode", "hashtag")
    hashtags = [h.strip().lstrip("#") for h in data.get("hashtags", []) if h.strip()]
    video_urls = [u.strip() for u in data.get("video_urls", []) if u.strip()]
    max_videos = max(1, min(int(data.get("max_videos", 30)), 100))
    max_comments = max(1, min(int(data.get("max_comments", 80)), 200))

    criteria = {
        "min_views": int(data.get("min_views", 100_000)),
        "min_engagement_rate": float(data.get("min_engagement_rate", 5.0)),
        "min_comment_rate": float(data.get("min_comment_rate", 0.3)),
        "min_like_rate": float(data.get("min_like_rate", 5.0)),
    }

    if not ms_token:
        return jsonify({"error": "Thiếu ms_token"}), 400
    if source_mode in ("hashtag", "both") and not hashtags:
        return jsonify({"error": "Cần ít nhất 1 hashtag"}), 400
    if source_mode in ("url", "both") and not video_urls:
        return jsonify({"error": "Cần ít nhất 1 URL video"}), 400

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "running",
        "logs": [],
        "comments": [],
        "videos": [],
        "report": None,
        "created_at": datetime.now().isoformat(),
    }

    thread = threading.Thread(
        target=lambda: asyncio.run(_scrape_job(
            job_id, ms_token, source_mode, hashtags, video_urls,
            max_videos, max_comments, criteria,
        )),
        daemon=True,
    )
    thread.start()
    return jsonify({"job_id": job_id})


@app.route("/api/jobs/<job_id>")
def get_job(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job không tồn tại"}), 404
    return jsonify({
        "status": job["status"],
        "logs": job["logs"],
        "video_count": len(job["videos"]),
        "comment_count": len(job["comments"]),
        "report": job.get("report"),
        "error": job.get("error"),
        "analysis_error": job.get("analysis_error"),
    })


@app.route("/api/analyze/<job_id>", methods=["POST"])
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
        return jsonify({"error": "Thiếu API key cho " + provider}), 400
    if not model.strip():
        return jsonify({"error": "Chưa chọn model"}), 400

    job["status"] = "analyzing"
    job["ai_config"] = {"provider": provider, "model": model, "api_key": api_key}

    thread = threading.Thread(target=lambda: _analyze_job(job_id), daemon=True)
    thread.start()
    return jsonify({"status": "analyzing"})


@app.route("/api/jobs/<job_id>/download/<file_type>")
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
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"tiktok_comments_{job_id}.csv",
        )

    if file_type == "report":
        report = job.get("report")
        if not report:
            return jsonify({"error": "Chưa có báo cáo phân tích"}), 400
        return send_file(
            io.BytesIO(report.encode("utf-8")),
            mimetype="text/markdown",
            as_attachment=True,
            download_name=f"insight_report_{job_id}.md",
        )

    return jsonify({"error": "Loại file không hợp lệ"}), 400


# ─── BACKGROUND TASKS ────────────────────────────────────────────────────────

async def _scrape_job(job_id, ms_token, source_mode, hashtags, video_urls,
                       max_videos, max_comments, criteria):
    job = jobs[job_id]

    def log(msg):
        job["logs"].append(msg)

    try:
        log(f"⚙️  Tiêu chí WIN: ≥{criteria['min_views']:,} views | "
            f"engagement ≥{criteria['min_engagement_rate']}% | "
            f"comment rate ≥{criteria['min_comment_rate']}% | "
            f"like rate ≥{criteria['min_like_rate']}%")

        async with TikTokApi() as api:
            await api.create_sessions(
                ms_tokens=[ms_token],
                num_sessions=1,
                sleep_after=3,
                headless=True,
            )

            if source_mode in ("url", "both"):
                log(f"🎯 Scrape {len(video_urls)} URL video chỉ định...")
                for url in video_urls:
                    vid = extract_video_id(url)
                    if not vid:
                        log(f"  ⚠️ URL không hợp lệ: {url}")
                        continue
                    try:
                        video = api.video(id=vid)
                        info = await video.info()
                        meta = build_video_meta(info, source=f"url:{url[:60]}")
                        job["videos"].append(meta)
                        log(f"  ✅ Video {vid}: {meta['play_count']:,} views | "
                            f"engagement {meta['engagement_rate']}% | "
                            f"comment {meta['comment_rate']}%")
                        await _scrape_comments(video, meta, job, max_comments, log)
                    except Exception as e:
                        log(f"  ❌ Lỗi video {vid}: {e}")

            if source_mode in ("hashtag", "both"):
                for tag in hashtags:
                    log(f"🔍 Quét #{tag} (tối đa {max_videos} video)...")
                    checked = 0
                    won = 0
                    try:
                        async for video in api.hashtag(name=tag).videos(count=max_videos):
                            d = video.as_dict
                            stats = d.get("stats", {})
                            checked += 1
                            ok, reason = is_win_video(stats, criteria)
                            if not ok:
                                log(f"  ⏭️  Bỏ qua: {reason}")
                                continue
                            won += 1
                            meta = build_video_meta(d, source=f"#{tag}")
                            job["videos"].append(meta)
                            log(f"  ✅ WIN video {won}: {meta['play_count']:,} views | "
                                f"engagement {meta['engagement_rate']}% | "
                                f"comment {meta['comment_rate']}%")
                            await _scrape_comments(video, meta, job, max_comments, log)
                        log(f"  📊 #{tag}: {won}/{checked} video đạt tiêu chí WIN")
                    except Exception as e:
                        log(f"❌ Lỗi #{tag}: {e}")

        job["status"] = "done"
        log(f"🎉 Hoàn tất! {len(job['videos'])} video WIN | {len(job['comments'])} comment")

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        log(f"❌ Lỗi nghiêm trọng: {e}")


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
                    lines.append(f"[{src} | {views:,} views | {likes}❤️] {text}")

            result = call_ai(
                provider=provider,
                model=model,
                api_key=api_key,
                system=SYSTEM_PROMPT,
                user=f"""Phân tích batch {i}/{len(chunks)} comment TikTok gym/fitness (đã lọc video WIN).
Trả lời bullet points ngắn gọn:
• Pain points nổi bật
• Emotion triggers (từ gây cảm xúc)
• Câu hỏi hay gặp
• Patterns engagement cao

---
{chr(10).join(lines)}""",
                max_tokens=1500,
            )
            chunk_results.append(result)

        log("🎯 Tổng hợp báo cáo cuối...")
        total_videos = len(set(r.get("video_id", "") for r in comments))

        report = call_ai(
            provider=provider,
            model=model,
            api_key=api_key,
            system=SYSTEM_PROMPT,
            user=f"""Tổng hợp insight từ {len(chunk_results)} batch phân tích.
Dữ liệu: {len(comments)} comment | {total_videos} video gym/fitness TikTok (đã lọc WIN).

Viết báo cáo theo format:

# INSIGHT REPORT — GYMSTORE TIKTOK
> Dữ liệu: {len(comments)} comment | {total_videos} video WIN | AI: {provider}/{model}

## 1. TOP PAIN POINTS (xếp theo mức độ phổ biến)

## 2. EMOTION TRIGGERS PHỔ BIẾN
(từ/cụm từ gây reaction mạnh, kèm ví dụ)

## 3. GÓC CONTENT ĐANG WIN
(kèm ví dụ comment minh họa thực tế)

## 4. HOOK IDEAS (5–8 hook dùng được luôn)

## 5. KEY MESSAGE CHO GYMSTORE

## 6. NÊN TRÁNH

---
{chr(10).join(chunk_results)}""",
            max_tokens=4000,
        )

        job["report"] = report
        job["status"] = "analyzed"
        log("✅ Báo cáo hoàn tất!")

        # Clear API key sau khi xong
        if "ai_config" in job:
            job["ai_config"]["api_key"] = "***cleared***"

    except Exception as e:
        job["status"] = "done"
        job["analysis_error"] = str(e)
        log(f"❌ Lỗi phân tích: {e}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)
