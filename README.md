# Tiktok Insight V1

Web tool **thu thập comment TikTok theo hashtag/URL/user/keyword** và **phân tích insight bằng AI** (Claude / OpenAI / Gemini).

## ✨ Tính năng chính

- 🔍 **5 nguồn data**: Hashtag · URL video · User profile · Keyword search · Related videos
- 🎯 **WIN filter**: tự động lọc video viral theo ngưỡng views / engagement / comment rate / like rate
- 💬 **Scrape comment** tới 200 / video
- 🤖 **AI insight đa provider**: Claude · OpenAI · Gemini · xAI Grok (user nhập API key của mình)
- 🌍 **Multi-region scrape**: HTTP proxy + msToken multi-token, auto-detect IP flag
- 🧪 **Test scrape 1 video**: verify proxy + msToken trước khi scrape full (15-30s)
- ⚠️ **Region mismatch warning**: cảnh báo khi msToken region ≠ outbound IP
- 👥 **User management**: email/password + Lark OAuth, role admin/user
- 📥 **Export**: CSV (raw comments) + Markdown (insight report)

## 🏗️ Stack

| Layer | Tech |
|---|---|
| Backend | Flask 3 + threading + asyncio |
| Frontend | Single HTML + Alpine.js + Tailwind (CDN, no build) |
| Scraping | [TikTokApi](https://github.com/davidteather/TikTok-Api) v7 + Playwright + WebKit |
| AI | anthropic / openai / google-generativeai SDKs |
| Auth | Flask sessions + werkzeug hash + Lark OAuth v1 |
| Deploy | Docker Compose (x86_64 + ARM64) |

## 🚀 Quick start local

```bash
git clone https://github.com/YOUR_USERNAME/tiktok-insight-tool.git
cd tiktok-insight-tool

# Python 3.9+ (3.11 recommended)
python3 -m venv .venv && source .venv/bin/activate

# Cài dependencies
pip install -r requirements.txt
python -m playwright install webkit

# Copy & edit .env
cp .env.production.example .env
# Mở .env và set: SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD
# (Lark OAuth optional, để trống nếu không dùng)

# Chạy
python app.py
```

Mở browser: <http://localhost:5001>

Login với `ADMIN_EMAIL` / `ADMIN_PASSWORD` đã set trong `.env`.

## 🐳 Deploy bằng Docker

```bash
# Copy .env như trên
docker compose up -d --build
docker compose logs -f
```

Mặc định serve cổng 5001. Đổi port hoặc bind interface trong `docker-compose.yml`.

## 🔑 Cách lấy `msToken`

1. Mở Chrome → vào [tiktok.com](https://www.tiktok.com) → đăng nhập
2. F12 (DevTools) → tab **Console**
3. Paste:
   ```javascript
   copy(document.cookie.split(';').filter(c=>c.includes('msToken')).map(c=>c.trim().split('=')[1]).sort((a,b)=>b.length-a.length)[0])
   ```
4. msToken đã copy vào clipboard → paste vào UI

⚠️ Token hết hạn sau **vài giờ** → lấy lại khi gặp lỗi auth.

## 🌐 Multi-region

Tool đọc geo từ **IP outbound** của process Flask:
- Chạy local máy ở VN → scrape data VN native
- Chạy VPS US → scrape data US native
- Cần data country khác → bật **HTTP Proxy** trong UI → paste proxy provider URL

UI tự **detect IP flag** qua `ipinfo.io` khi anh đổi proxy. Click **🧪 Test 1 video** để verify trước khi scrape full.

## 📊 Output báo cáo

1. **Top pain points** — xếp theo phổ biến
2. **Emotion triggers** — từ/cụm từ gây reaction mạnh
3. **Góc content đang win** — kèm ví dụ comment thực
4. **Hook ideas** — 5–8 hook dùng được luôn
5. **Key message**
6. **Nên tránh** — điều khiến audience phản ứng tiêu cực

## ⚙️ Tuỳ chỉnh AI prompt

Tool dùng `SYSTEM_PROMPT` trong [`app.py`](app.py) để hướng dẫn AI phân tích. Sửa biến này để fit niche/brand của anh (vd: fitness, beauty, finance, F&B…).

## 🛡️ Bảo mật

- `.env` + `users.json` + `.env.*` đều ở `.gitignore`
- Password lưu hashed bằng werkzeug `pbkdf2:sha256`
- Sessions cookie-based, có `HttpOnly` + `SameSite=Lax`
- API key user nhập trên UI → lưu **localStorage browser**, không gửi server trừ khi gọi AI

## 📜 Lưu ý pháp lý

Tool chỉ thu thập **comment công khai** trên video TikTok. Không thu thập thông tin cá nhân, không bypass auth, không spam, không upload. Dùng cho mục đích nghiên cứu thị trường nội bộ.

## 📄 License

Internal use only. Không thương mại hoá.
