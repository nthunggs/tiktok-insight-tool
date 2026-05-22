# Tiktok Insight V1

Web tool **thu thập comment TikTok theo hashtag / URL / user / keyword / related** và **phân tích insight bằng AI** (Claude / OpenAI / Gemini / Grok).

> 🔥 **Engine mới (v2)**: TikTokApi (fast, API direct) + **[CloakBrowser](https://github.com/CloakHQ/cloakbrowser)** (58 anti-detect patches, prevents captcha). Auto-fetch msToken bằng 1 click.

## ✨ Tính năng chính

- 🔍 **5 nguồn data**: Hashtag · URL video · User profile · Keyword search · Related videos
- 🎯 **WIN filter**: tự động lọc video viral theo ngưỡng views / engagement / comment rate / like rate
- 💬 **Scrape comment** tới 200 / video
- 🤖 **AI insight đa provider**: Claude · OpenAI · Gemini · xAI Grok (bạn nhập API key của mình)
- 🥷 **Anti-detect engine**: TikTokApi + CloakBrowser combo → bypass captcha, nhanh, scale được
- 🔄 **Auto-fetch msToken**: 1 click lấy token từ tiktok.com qua CloakBrowser headless, không cần DevTools
- 🌍 **Multi-region scrape**: HTTP proxy + msToken multi-token, auto-detect IP flag qua ipinfo.io
- 🧪 **Test scrape 1 video**: verify msToken + proxy trước khi scrape full (~30s)
- ⚠️ **Region mismatch warning**: cảnh báo khi msToken region ≠ outbound IP
- 👥 **User management**: email/password + Lark OAuth, role admin/user
- 📥 **Export**: CSV (raw comments) + Markdown (insight report)

## 🏗️ Stack

| Layer | Tech |
|---|---|
| Backend | Flask 3 + threading + asyncio |
| Frontend | Single HTML + Alpine.js + Tailwind (CDN, no build) |
| Scraping engine | **TikTokApi v7** + **CloakBrowser** (stealth Chromium with 58 source-level anti-detect patches) |
| Fallback engine | Playwright + Chrome thật (qua `tiktok_scraper.py`) |
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

# Tải binary CloakBrowser (~200MB lần đầu)
python -c "import cloakbrowser; cloakbrowser.ensure_binary()"

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
cp .env.production.example .env  # sửa giá trị
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
2. Copy 2 thứ:
   - **App ID** (dạng `cli_xxxxxxxxxxxxxxxx`)
   - **App Secret** (dạng chuỗi 32 ký tự)

#### Bước 2: Cấu hình app
**A. Add Redirect URL** (Security Settings → Redirect URLs):
```
https://yourdomain.com/auth/lark/callback
```

**B. Bật scopes** (Permissions & Scopes):
- ✅ `contact:user.base:readonly` — name + mobile (đủ login, hỗ trợ account chỉ có SĐT)
- ✅ `contact:user.email:readonly` — email (nếu có)
- ✅ `contact:user.id:readonly` — open_id

**C. Publish app** (Custom App): bấm **Apply for release**.

#### Bước 3: Set env trong `.env`
```bash
LARK_APP_ID=cli_xxxxxxxxxxxxxxxx
LARK_APP_SECRET=your_app_secret_32_chars
LARK_REDIRECT_URI=https://yourdomain.com/auth/lark/callback

# Optional whitelist
# LARK_ALLOWED_EMAILS=user1@yourcompany.com,user2@yourcompany.com
```

#### Bước 4: Restart tool → nút **"Đăng nhập với Lark"** sẽ tự active.

> 💡 **User chỉ có SĐT**: code fallback identifier `mobile@lark.local` hoặc `open_id@lark.local`. Vẫn login được.

## 🔑 Cách lấy `msToken`

### Cách 1: Auto-fetch (recommend ⭐)
Trong UI, bấm nút **🔄 Auto lấy msToken** → backend launch CloakBrowser headless → visit tiktok.com → extract cookie msToken → tự paste vào textarea.

→ KHÔNG cần DevTools, KHÔNG cần copy/paste thủ công.

### Cách 2: Thủ công qua Console
1. Vào [tiktok.com](https://www.tiktok.com) trên Chrome (login optional)
2. F12 (DevTools) → tab **Console**
3. Gõ `allow pasting` + Enter (Chrome chặn paste code lạ)
4. Paste:
   ```javascript
   copy(document.cookie.split(';').filter(c=>c.includes('msToken')).map(c=>c.trim().split('=')[1]).sort((a,b)=>b.length-a.length)[0])
   ```
5. msToken đã copy vào clipboard → paste vào UI

⚠️ Token tự refresh qua TikTok mỗi 5-10s → lấy token tươi rồi dùng ngay trong < 60s.

## 🌐 Multi-region

Tool đọc geo từ **IP outbound** của process Flask:
- Chạy local máy ở VN → scrape data VN native
- Chạy VPS US → scrape data US native
- Cần data country khác → bật **HTTP Proxy** trong UI → paste proxy provider URL

UI tự **detect IP flag** qua `ipinfo.io` khi đổi proxy. Engine **tự match locale + timezone** browser theo country detected (21 countries: VN/US/JP/KR/TH/ID/MY/PH/SG/TW/HK/IN/AU/CA/GB/DE/FR/NL/BR/MX...).

→ Khi bật proxy US, tool launch CloakBrowser **với locale `en-US` + timezone `America/New_York`** → TikTok không thấy mismatch fingerprint.

Click **🧪 Test 1 video** để verify msToken + proxy trước khi scrape full (~30s test).

## 🥷 Engine anti-detect

Tool kết hợp 2 thư viện:

| | TikTokApi (v7) | CloakBrowser |
|---|---|---|
| Vai trò | Engine chính, gọi API TikTok direct | Browser binary cho session init |
| Speed | ⚡ Fast (no web flow) | — |
| Captcha | ✅ Bypass (không hit web flow) | ✅ Prevent (58 anti-detect patches) |
| Anti-fingerprint | ❌ Vanilla Playwright Chromium | ✅ Canvas, WebGL, audio, fonts, GPU, screen, WebRTC patches |
| Humanize | ❌ | ✅ Mouse curves, keyboard timing (optional) |
| Cost | Free | Free (MIT) |

**Kiến trúc**:
```
TikTokApi.create_sessions(browser_context_factory=cloak_factory)
                          ↓
       cloakbrowser.launch_persistent_context_async(
           stealth_args=True, humanize=False,
           locale=<auto>, timezone=<auto>,
           proxy=<from UI>,
       )
                          ↓
       TikTokApi dùng CloakBrowser context để chạy → API direct + stealth
```

### Cấu hình qua `.env`
```bash
TIKTOK_USE_CLOAK=true       # true = TikTokApi + CloakBrowser, false = Chromium bundled
TIKTOK_HEADLESS=true        # CloakBrowser stealth đủ → headless OK (nhanh)
TIKTOK_HUMANIZE=false       # true = human-like mouse/keyboard (slow nhưng safer)
TIKTOK_SLEEP_AFTER=3        # giây sleep giữa requests TikTokApi
```

## 📊 Output báo cáo

1. **Top pain points** — xếp theo phổ biến
2. **Emotion triggers** — từ/cụm từ gây reaction mạnh
3. **Góc content đang win** — kèm ví dụ comment thực
4. **Hook ideas** — 5–8 hook dùng được luôn
5. **Key message**
6. **Nên tránh** — điều khiến audience phản ứng tiêu cực

## ⚙️ Tuỳ chỉnh AI prompt

Tool dùng biến `SYSTEM_PROMPT` trong [`app.py`](app.py). Override bằng env:

```bash
# Trong .env
AI_SYSTEM_PROMPT="Bạn là chuyên gia phân tích content marketing cho ngành [NICHE].
Nhiệm vụ: phân tích comment TikTok để tìm insight và góc content win cho brand [BRAND]..."
```

Niche ví dụ: F&B, beauty, fitness, finance, travel, education...

## 🛡️ Bảo mật

- `.env` + `users.json` + `.env.*` đều ở `.gitignore`
- Password lưu hashed bằng werkzeug `pbkdf2:sha256`
- Sessions cookie-based, có `HttpOnly` + `SameSite=Lax`
- API key user nhập trên UI → lưu **localStorage browser**, không gửi server trừ khi gọi AI
- Lark OAuth dùng state token chống CSRF
- CloakBrowser binary lưu ở `~/.cloakbrowser/` (user home), không commit vào git

## 📂 File structure

```
tiktok-insight-tool/
├── app.py                       # Flask + REST API + scrape job orchestration
├── auth.py                      # Sessions + Lark OAuth + user CRUD
├── tiktok_scraper.py            # Playwright-based fallback engine (no captcha bypass, slower)
├── templates/
│   ├── index.html               # Main UI (Alpine + Tailwind + marked.js)
│   └── login.html               # Login page (gradient mesh)
├── requirements.txt             # Python deps
├── Dockerfile                   # ARM64 + x86_64
├── docker-compose.yml           # 1 service + healthcheck
├── .env.production.example      # Template
├── .gitignore
└── README.md
```

## 📜 Lưu ý pháp lý

Tool chỉ thu thập **comment công khai** trên video TikTok. Không thu thập thông tin cá nhân, không bypass auth, không spam, không upload. Dùng cho mục đích nghiên cứu thị trường nội bộ.

## 🙏 Credits

- [TikTokApi](https://github.com/davidteather/TikTok-Api) by David Teather
- [CloakBrowser](https://github.com/CloakHQ/cloakbrowser) by CloakHQ
- [Playwright](https://playwright.dev/python/)

## 📄 License

Internal use only. Không thương mại hoá.
