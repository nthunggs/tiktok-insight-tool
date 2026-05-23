# 📘 Tiktok Insight V1 — Hướng dẫn sử dụng

Tài liệu vắn tắt theo trình tự UI từ trên xuống dưới.

---

## 🔐 1. Trang đăng nhập

- **Email + Password**: account admin tạo
- **Đăng nhập với Lark**: SSO bằng Lark workspace (cần Lark App + Redirect URL whitelist)

→ Sau login: vào dashboard chính.

---

## 🎨 2. Header (top bar)

| Phần tử | Mô tả |
|---|---|
| Logo TikTok + tên app | Tiktok Insight V1 |
| Badge AI active | Provider · model đang chọn (cyan/orange/blue dot) |
| Badge job status | "Đang scrape" / "Scrape xong" / "Đã phân tích" |
| Avatar góc phải | Click → menu **Quản lý user** (admin) / **Đăng xuất** |

---

## 🤖 3. Card AI MODEL

1. Chọn **provider**: Claude / OpenAI / Gemini / Grok
2. Paste **API key** của provider đó (key của user — không lưu server)
3. Click **🔄 Refresh** → fetch danh sách model **trực tiếp** từ API → chọn model
4. Key + model lưu vào `localStorage` browser

---

## 🔑 4. Card TIKTOK MS_TOKENS

| Phần | Hành động |
|---|---|
| Textarea | Paste msToken (mỗi dòng 1 token) |
| **Nút "Tự động fill msToken"** + stepper `− N +` (1-5) | 1 click → backend mở CloakBrowser headless → visit tiktok.com → extract cookie msToken qua proxy → auto paste |
| Dropdown **"Country Scrape"** | Chọn quốc gia mà msToken được issue (để check region mismatch) |
| Nút **🧪 Test 1 video** | Verify msToken + proxy còn work — scrape 1 video #fyp + 5 comments (~30s) |
| Warning region mismatch | Hiện khi msToken country ≠ outbound IP detected |
| **▶ Hướng dẫn & lưu ý** | Click sổ ra: tip chọn cookie + guide macOS/Windows/Safari + warning token expiry |

---

## 📂 5. Card Nguồn dữ liệu (5 mode)

Click toggle bật/tắt từng mode:

| Mode | Cách dùng | WIN filter |
|---|---|---|
| 🔍 **Hashtag** | Nhập hashtag (vd `gym`, `ashwagandha`) | ✅ Có |
| 🎯 **URL video** | Paste full URL TikTok video | ❌ Không (lấy tất) |
| 👤 **User** | Nhập `@username` hoặc URL profile | ❌ Không (lấy tất video của creator) |
| 🔎 **Keyword search** | Nhập từ khoá tìm kiếm | ✅ Có |
| 🌱 **Related videos** | Paste URL video seed → TikTok gợi ý related | ✅ Có |

→ Có thể bật nhiều mode cùng lúc.

---

## ⚙️ 6. Card Bộ lọc / Multi-session & Proxy

### Multi-session
- Slider **1-3 sessions** chạy parallel (cần N msToken nếu N > 1)

### Proxy HTTP
- Toggle bật/tắt
- Server / Username / Password (paste từ proxy provider: IPRoyal, Bright Data, hoặc us-squid-proxy của bạn)
- **Badge cờ tự detect**: tool gọi ipinfo.io qua proxy → hiện 🇺🇸 / 🇻🇳 / 🇯🇵... + city
- Tool tự match locale + timezone browser theo country detected

---

## 🎯 7. Card Tiêu chí WIN *(tự ẩn nếu chỉ dùng URL/User mode)*

4 sliders lọc video viral (chỉ áp dụng hashtag/keyword/related):

| Slider | Range | Default đề xuất |
|---|---|---|
| **Min views** | 1K → 1M (step 1K) | 100K |
| **Min engagement** | 0.01% → 20% (step 0.01) | 5% |
| **Min comment rate ★** | 0.01% → 2% (step 0.01) | 0.3% — quan trọng nhất, insight nằm ở comment |
| **Min like rate** | 0.01% → 20% (step 0.01) | 5% |

→ Có thể hạ xuống mức rất thấp (0.01%) để bắt video VN có comment rate thấp.

---

## 📊 8. Card Giới hạn

- **Video / nguồn**: 10-100 (max scrape mỗi hashtag/user)
- **Comment / video**: 20-200 (max scrape mỗi video WIN)
- Checkbox **Dedup videos**: bỏ trùng nếu video xuất hiện ở nhiều nguồn

---

## ▶️ 9. Bắt đầu Scrape

Click **"Bắt đầu Scrape"** → backend chạy background job. Đợi 1-10 phút tùy số lượng.

---

## 📈 10. Cột phải — Kết quả

### Khi job đang chạy:
- **3 stat cards**: Video WIN · Comment · Sources
- **Live log box** (đen) — realtime tiến độ:
  - `🔍 #hashtag (max 30)...`
  - `✅ WIN 1 @author: 250Kv | eng 5.2% — "video desc..."`
  - `      💬 80 comment`
  - `🎉 Hoàn tất! 8 video WIN | 640 comment`

### Khi xong:
- Nút **📥 Tải CSV** (raw comments)
- Nút **✨ Phân tích với Claude** → AI sinh report 6 phần:
  1. Top pain points
  2. Emotion triggers
  3. Góc content đang win
  4. Hook ideas
  5. Key message
  6. Nên tránh
- Sau analyze: nút **📥 Tải báo cáo .md**

### Buttons:
- **Clear log** (có confirm) → wipe job state local
- Job state **persist 24h** trong browser → F5 vẫn còn

---

## 🆕 Cập nhật mới nhất

| Tính năng | Mô tả |
|---|---|
| 🥷 **Engine TikTokApi + CloakBrowser** | Combo bypass captcha + anti-detect 58 patches |
| 🔄 **Auto fill msToken (1-5 tokens)** | Stepper count, 1 click lấy multi-session tokens |
| 🌍 **Auto IP detect + flag badge** | Tự match locale/timezone theo proxy country |
| 🧪 **Test 1 video** | Verify config trong 30s trước khi scrape full |
| ⚠️ **Region mismatch warning** | Cảnh báo khi msToken country ≠ IP |
| 💾 **Persist job state localStorage** | F5/restart Flask vẫn còn log + report |
| 🎯 **WIN filter auto-skip** cho URL/User mode | URL/User = user chủ động chọn → lấy tất |
| 📊 **Slider WIN range cực thấp** | Min 0.01% cho mọi rate |
| 🎨 **UI redesign card msToken** | Button stretch full + count stepper, gom guide vào 1 collapsible |
| 🔐 **Lark OAuth fallback identifier** | Account chỉ có SĐT vẫn login được (`mobile@lark.local`) |
| 👤 **Avatar user từ Lark** | Lưu avatar_url + display trong header |
| 🔧 **`.env` parser strip inline comments** | Comment sau giá trị không break env loading |
| 🌐 **ngrok-skip-browser-warning header** | Override `window.fetch` global, JSON endpoints không bị HTML interstitial |

---

## 🚨 Troubleshooting

| Lỗi log box | Fix |
|---|---|
| `0 video WIN \| 0 comment` | Hạ WIN criteria xuống thấp nhất (0.01%) hoặc đổi sang Hashtag (loose hơn Keyword) |
| `TikTok returned empty response` | msToken hết hạn → bấm **Tự động fill msToken** lấy mới |
| `Search has no attribute 'videos'` | (Đã fix) keyword auto fallback Playwright engine |
| `ProcessSingleton conflict` | (Đã fix) keyword dùng profile dir riêng |
| `Unexpected token '<'` | (Đã fix) inject `ngrok-skip-browser-warning` header |
| Login Lark `Missing permissions` | Enable scopes trong Lark Developer Console: `contact:user.base:readonly`, `contact:user.email:readonly`, `contact:user.id:readonly` |
| Login Lark `Invalid redirect URL` | Add đúng URL vào Lark Console Security Settings → Redirect URLs |

---

## 💡 Tip best practice

1. **Lần đầu setup**: Login → Quản lý user tạo account cho team
2. **Trước mỗi scrape**: bấm **Tự động fill msToken** → token tươi
3. **Test nhỏ trước**: bật 1 hashtag, max 5 video, max 20 comment + bấm **🧪 Test 1 video** verify
4. **Scrape full**: tăng max videos/comments lên
5. **Analyze**: chọn Claude Opus 4.7 cho chất lượng cao nhất, Gemini 2.5 Flash cho free + nhanh
6. **Output**: tải cả CSV (raw) + MD (insight) → backup

---

## 🔧 Cấu hình `.env` chính

```bash
# Random 32+ chars
SECRET_KEY=...

# Lark OAuth (optional)
LARK_APP_ID=cli_xxxxxxxxxxxxxxxx
LARK_APP_SECRET=...
LARK_REDIRECT_URI=https://yourdomain.com/auth/lark/callback

# Default admin (chỉ tạo khi users.json trống)
ADMIN_EMAIL=admin@example.local
ADMIN_PASSWORD=ChangeMe

# Engine
TIKTOK_USE_CLOAK=true    # CloakBrowser anti-detect
TIKTOK_HEADLESS=true
TIKTOK_HUMANIZE=false    # true = chậm hơn nhưng human-like
TIKTOK_SLEEP_AFTER=3

# AI prompt override (optional)
AI_SYSTEM_PROMPT="Bạn là chuyên gia content marketing cho ngành ..."
```

---

## 📦 Tech stack

- **Backend**: Flask 3 + threading + asyncio
- **Frontend**: Single HTML + Alpine.js + Tailwind (CDN)
- **Scraping**: TikTokApi v7 + CloakBrowser (58 anti-detect patches)
- **Fallback**: Playwright + Chrome thật (cho keyword search)
- **AI**: Anthropic / OpenAI / Google Gemini SDKs
- **Auth**: Flask sessions + werkzeug hash + Lark OAuth v1
- **Deploy**: Docker Compose

---

## 📄 License

Internal use only.
