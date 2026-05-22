# HANDOFF — TikTok Insight Tool

> Tài liệu này dành cho việc tiếp tục dự án ở **máy tính khác / Claude Code session mới**.
> Đọc từ trên xuống để có toàn bộ context cần thiết.

---

## 1. Dự án này là gì?

Web tool nội bộ cho Gymstore, dùng để:

1. **Scrape comment TikTok** theo hashtag hoặc URL video cụ thể
2. **Lọc tự động video "WIN"** (đạt ngưỡng views, engagement, comment rate, like rate)
3. **Phân tích insight bằng AI** (Claude / OpenAI / Gemini — user chọn) → báo cáo Markdown gồm pain points, emotion triggers, hook ideas, key message, điều nên tránh

**Mục tiêu cuối:** tìm góc content "win" để chạy ads Gymstore (gym/fitness/supplement).

---

## 2. Tech Stack

| Layer | Stack |
|---|---|
| Backend | **Flask** (Python 3.9+), threading cho background jobs |
| Frontend | **Single HTML** (`templates/index.html`), TailwindCSS + Alpine.js + marked.js qua CDN |
| Scraping | [`TikTokApi`](https://github.com/davidteather/TikTok-Api) (v7.3+) + Playwright + Chromium |
| AI providers | Anthropic SDK, OpenAI SDK, `google-generativeai` |
| Storage | In-memory dict (không persist) |
| Deploy | Docker (ARM64 cho Synology NAS) hoặc local Python |

**Design choice quan trọng:** Flask vừa serve UI (`/`) vừa expose API (`/api/*`) — cùng 1 process, 1 port. Không cần frontend riêng (đã thử GitHub Pages nhưng browser chặn HTTPS → private IP).

---

## 3. Cấu trúc thư mục

```
webapp/
├── app.py                     # Flask backend + API + scraping + AI logic
├── templates/
│   └── index.html             # Toàn bộ frontend (~750 dòng)
├── requirements.txt           # Python deps
├── Dockerfile                 # ARM64 cho NAS Synology
├── docker-compose.yml         # mem_limit 800MB
├── .gitignore
├── README.md
└── HANDOFF.md                 # File này
```

---

## 4. Trạng thái hiện tại

### ✅ Đã hoàn thành
- [x] Backend Flask + 6 endpoint REST
- [x] Frontend UI hoàn chỉnh (shadcn-inspired design)
- [x] **5 source modes**: hashtag, URL, user (@username), keyword search, related videos (seed expansion)
- [x] **Multi-session** scraping (1-3 session song song, mỗi session 1 ms_token)
- [x] **Proxy support** (HTTP/SOCKS proxy với user/pass)
- [x] WIN filter áp dụng cho 4/5 mode (URL bypass)
- [x] Multi-provider AI (Anthropic/OpenAI/Gemini) — fetch model list **trực tiếp từ API**
- [x] Save config vào browser `localStorage` (v3 schema)
- [x] Live log realtime (polling 2s)
- [x] Download CSV (raw comments) + Markdown (insight report)
- [x] Hướng dẫn lấy `ms_token` cho macOS (Chrome/Safari)
- [x] Dockerfile cho ARM64
- [x] Test chạy local trên macOS, HTTP 200 ổn

### ⚠️ Chưa test
- [ ] Chưa test end-to-end với `ms_token` thật + API key thật → có thể có bug khi gọi TikTok thực tế
- [ ] Chưa deploy lên NAS, chưa benchmark RAM thực tế
- [ ] Chưa test Playwright trên NAS ARM64 — có thể cần adjust Dockerfile

### 🔧 Có thể cần làm tiếp
- [ ] Thêm endpoint cleanup job cũ (hiện tại memory grow vô hạn)
- [ ] Thêm rate limit cho TikTok scrape (tránh bị block)
- [ ] Lưu job history vào SQLite thay vì in-memory dict
- [ ] Authentication cho UI (hiện ai vào IP NAS đều dùng được)
- [ ] Schedule scrape định kỳ (cron job)
- [ ] Streaming response cho phân tích AI thay vì poll

---

## 5. Cách chạy local trên máy mới (macOS / Linux)

```bash
# Clone
git clone https://github.com/nthunggs/tiktok-insight-tool.git
cd tiktok-insight-tool

# Python 3.9+ (3.11 recommended)
python3 --version

# Cài dependencies
pip3 install -r requirements.txt

# Cài Chromium cho Playwright (~150MB)
python3 -m playwright install chromium

# Chạy
python3 app.py
# → mở http://localhost:5001
```

Không cần set env var. API key được nhập trực tiếp trên UI, lưu trong browser localStorage.

---

## 6. Deploy lên NAS Synology (DS223 ARM64)

```bash
# Copy code lên NAS
rsync -avz -e "ssh -p 2222" ./ henrynguyen@192.168.88.132:/volume1/HenryData/projects/tiktok-insight-tool/

# SSH vào NAS
ssh nas
cd /volume1/HenryData/projects/tiktok-insight-tool

# Chạy Docker
docker compose up -d
docker compose logs -f
```

Truy cập: `http://192.168.88.132:5001` (LAN only)

> ⚠️ **NAS RAM**: container chiếm ~600–700MB (Chromium nặng). DS223 chỉ có ~1.1GB free → không chạy container nặng khác cùng lúc.

---

## 7. Workflow sử dụng

1. Mở UI → chọn AI provider (Claude / OpenAI / Gemini)
2. Nhập API key của provider đó → auto fetch model list từ API
3. Chọn model
4. Lấy `ms_token` từ cookie TikTok (xem hướng dẫn trong UI)
5. Chọn nguồn: Hashtag / URL / Cả hai
6. Cấu hình tiêu chí WIN (views, engagement, comment rate, like rate)
7. Bấm **Bắt đầu Scrape** → xem log realtime
8. Khi xong → bấm **Phân tích với [Provider]**
9. Đọc báo cáo + tải CSV/MD

---

## 8. Tiêu chí "Content WIN" — Logic đề xuất

| Chỉ số | Công thức | Mặc định | Lý do |
|---|---|---|---|
| **Min views** | playCount | 100,000 | Đủ lan tỏa, đại diện xu hướng |
| **Min engagement rate** | (likes+comments+shares) / views | 5% | 5–10% tốt, >10% viral |
| **Min comment rate** ★ | comments / views | 0.3% | **Insight nằm ở comment** → quan trọng nhất |
| **Min like rate** | likes / views | 5% | Mức độ đồng cảm |

Logic: scrape `max_videos` mỗi hashtag → filter theo cả 4 ngưỡng → chỉ scrape comment từ video đạt → comment chất lượng hơn.

---

## 9. Lấy API key ở đâu

| Provider | Link | Giá |
|---|---|---|
| Anthropic | https://console.anthropic.com/settings/keys | Trả phí, có credits free khi tạo |
| OpenAI | https://platform.openai.com/api-keys | Trả phí |
| Gemini | https://aistudio.google.com/apikey | **Miễn phí** (rate limit nhẹ) |

Recommend: **Gemini 2.5 Flash** cho test (free + nhanh), Claude Sonnet 4.6 cho production analysis (chất lượng).

---

## 10. Lấy ms_token

**Chrome / Brave / Edge (macOS):**
1. Mở `tiktok.com` → đăng nhập
2. `⌘ + ⌥ + I` → DevTools
3. Tab `Application` → Cookies → `https://www.tiktok.com`
4. Tìm `msToken` → copy Value

Token hết hạn sau vài giờ → lấy lại khi gặp lỗi auth.

---

## 11. API Endpoints (cho người muốn tự gọi)

| Method | Path | Body | Mô tả |
|---|---|---|---|
| POST | `/api/scrape` | `{ ms_token, source_mode, hashtags, video_urls, max_videos, max_comments, min_views, min_engagement_rate, min_comment_rate, min_like_rate }` | Bắt đầu scrape job |
| GET | `/api/jobs/<id>` | — | Status, logs, video/comment count, report |
| POST | `/api/analyze/<id>` | `{ provider, model, api_key }` | Bắt đầu phân tích AI |
| POST | `/api/models` | `{ provider, api_key }` | Fetch model list trực tiếp từ provider |
| GET | `/api/jobs/<id>/download/csv` | — | Tải CSV comments |
| GET | `/api/jobs/<id>/download/report` | — | Tải Markdown insight |

---

## 12. Gotchas / Quirks đã gặp

- **Python 3.9 không hỗ trợ `str | None`** syntax → đã fix dùng `Optional[str]` từ `typing`
- **TikTokApi cần Playwright headless Chromium** → docker image ~600MB
- **`ms_token` hết hạn nhanh** (vài giờ) — đây là cookie session
- **Browser chặn HTTPS → private IP** → bắt buộc Flask serve cả UI + API, không tách
- **Background jobs là threading + in-memory** → restart Flask = mất hết job history

---

## 13. Mở lại với Claude Code ở máy mới

```bash
# Clone repo
git clone https://github.com/nthunggs/tiktok-insight-tool.git
cd tiktok-insight-tool

# Mở Claude Code trong thư mục này
claude

# Câu lệnh đầu tiên cho Claude Code:
```

> Đọc `HANDOFF.md` để hiểu context. Tôi muốn tiếp tục dự án này từ điểm: [mô tả mục tiêu cụ thể].

---

## 14. Liên hệ & ghi chú

- **Owner**: Henry Nguyen (Gymstore)
- **Email**: mr.vic6866@gmail.com
- **NAS**: `henrynguyen@192.168.88.132:2222` (LAN)
- **Mục đích**: Research nội bộ — không phục vụ thương mại bên thứ ba
- **License**: Internal use only
