# Tiktok Insight V1

Web tool **thu thập comment TikTok theo hashtag / URL / user / keyword / related** và **phân tích insight bằng AI** (Claude / OpenAI / Gemini / Grok).

## ✨ Tính năng chính

- 🔍 **5 nguồn data**: Hashtag · URL video · User profile · Keyword search · Related videos
- 🎯 **WIN filter**: tự động lọc video viral theo ngưỡng views / engagement / comment rate / like rate
- 💬 **Scrape comment** tới 200 / video
- 🤖 **AI insight đa provider**: Claude · OpenAI · Gemini · xAI Grok (bạn nhập API key của mình)
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
# (Lark OAuth optional, xem section dưới)

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

## 🔐 Login

Tool có **2 cách đăng nhập**:

### 1. Email + Password (mặc định)
- Default admin tạo từ `ADMIN_EMAIL` / `ADMIN_PASSWORD` trong `.env`
- Admin login → vào **User menu → Quản lý user** → tạo account cho team

### 2. Lark OAuth (optional, cho team dùng Lark/Feishu Workspace)

#### Bước 1: Tạo Lark Developer App
1. Vào [Lark Developer Console](https://open.larksuite.com/app) → **Create Custom App**
2. Sau khi tạo xong, copy 2 thứ:
   - **App ID** (dạng `cli_xxxxxxxxxxxxxxxx`)
   - **App Secret** (dạng chuỗi 32 ký tự)

#### Bước 2: Cấu hình app
Trong Lark Developer Console của app vừa tạo:

**A. Add Redirect URL** (Security Settings → Redirect URLs):
```
https://yourdomain.com/auth/lark/callback
```
*(Đổi `yourdomain.com` thành URL thật của bạn — phải khớp với `LARK_REDIRECT_URI`)*

**B. Bật scopes** (Permissions & Scopes):
- ✅ `contact:user.email:readonly` — lấy email user
- ✅ `contact:user.base:readonly` — lấy mobile + name (quan trọng cho user chỉ có SĐT)
- ✅ `contact:user.id:readonly` — lấy open_id

**C. Publish app** (nếu là Custom App): bấm **Apply for release** để team trong workspace dùng được.

#### Bước 3: Set env trong `.env`
```bash
LARK_APP_ID=cli_xxxxxxxxxxxxxxxx
LARK_APP_SECRET=your_app_secret_32_chars
LARK_REDIRECT_URI=https://yourdomain.com/auth/lark/callback

# Optional: chỉ cho phép 1 số email/phone trong workspace login
# LARK_ALLOWED_EMAILS=user1@yourcompany.com,user2@yourcompany.com
```

#### Bước 4: Restart tool
```bash
docker compose restart
# hoặc nếu chạy local: kill rồi run lại python app.py
```

Nút **"Đăng nhập với Lark"** sẽ tự active trên trang login. User click → redirect Lark → grant permissions → tự được provision vào `users.json` với role `user`.

> 💡 **User chỉ có SĐT (account VN)**: code tự fallback identifier `mobile@lark.local` hoặc `open_id@lark.local`. Vẫn login được.

## 🔑 Cách lấy `msToken`

1. Mở Chrome → vào [tiktok.com](https://www.tiktok.com) → đăng nhập
2. F12 (DevTools) → tab **Console**
3. Gõ `allow pasting` + Enter (Chrome chặn paste code lạ)
4. Paste:
   ```javascript
   copy(document.cookie.split(';').filter(c=>c.includes('msToken')).map(c=>c.trim().split('=')[1]).sort((a,b)=>b.length-a.length)[0])
   ```
5. msToken đã copy vào clipboard → paste vào UI

⚠️ Token hết hạn sau **vài giờ** → lấy lại khi gặp lỗi auth.

## 🌐 Multi-region

Tool đọc geo từ **IP outbound** của process Flask:
- Chạy local máy ở VN → scrape data VN native
- Chạy VPS US → scrape data US native
- Cần data country khác → bật **HTTP Proxy** trong UI → paste proxy provider URL

UI tự **detect IP flag** qua `ipinfo.io` khi bạn đổi proxy. Click **🧪 Test 1 video** để verify trước khi scrape full.

## 📊 Output báo cáo

1. **Top pain points** — xếp theo phổ biến
2. **Emotion triggers** — từ/cụm từ gây reaction mạnh
3. **Góc content đang win** — kèm ví dụ comment thực
4. **Hook ideas** — 5–8 hook dùng được luôn
5. **Key message**
6. **Nên tránh** — điều khiến audience phản ứng tiêu cực

## ⚙️ Tuỳ chỉnh AI prompt

Tool dùng biến `SYSTEM_PROMPT` trong [`app.py`](app.py) để hướng dẫn AI phân tích. Override bằng env:

```bash
# Trong .env
AI_SYSTEM_PROMPT="Bạn là chuyên gia phân tích content marketing cho ngành [NICHE].
Nhiệm vụ: phân tích comment TikTok để tìm insight và góc content win cho brand [BRAND]..."
```

Tool tự pickup khi restart. Niche ví dụ: F&B, beauty, fitness, finance, travel, education...

## 🧪 Tuỳ chỉnh bot detect

Mặc định dùng **WebKit** (ít bị TikTok flag hơn Chromium). Tweak nếu vẫn bị detect:

```bash
# Trong .env
TIKTOK_BROWSER=webkit       # webkit / chromium / firefox
TIKTOK_HEADLESS=true        # false = hiện browser window (chống detect mạnh hơn)
TIKTOK_SLEEP_AFTER=5        # giây sleep giữa requests
```

## 🛡️ Bảo mật

- `.env` + `users.json` + `.env.*` đều ở `.gitignore`
- Password lưu hashed bằng werkzeug `pbkdf2:sha256`
- Sessions cookie-based, có `HttpOnly` + `SameSite=Lax`
- API key user nhập trên UI → lưu **localStorage browser**, không gửi server trừ khi gọi AI
- Lark OAuth dùng state token chống CSRF

## 📜 Lưu ý pháp lý

Tool chỉ thu thập **comment công khai** trên video TikTok. Không thu thập thông tin cá nhân, không bypass auth, không spam, không upload. Dùng cho mục đích nghiên cứu thị trường nội bộ.

## 📄 License

Internal use only. Không thương mại hoá.
