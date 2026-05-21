# TikTok Research Tool — Gymstore

Tool thu thập comment TikTok theo hashtag và phân tích insight content "win" bằng Claude.

## Tính năng

- Scrape comment từ video TikTok trending theo hashtag (không cần đăng nhập đầy đủ, chỉ cần `ms_token` từ cookie)
- Web UI nhập hashtag, cấu hình số lượng video/comment
- Phân tích tự động bằng Claude → báo cáo insight (pain points, emotion triggers, hook ideas, key message)
- Tải về CSV (raw data) và Markdown (báo cáo)

## Stack

- **Backend & Frontend**: Flask (Python) — serve cả UI và API trên cùng port
- **Scraping**: [TikTokApi](https://github.com/davidteather/TikTok-Api) + Playwright (Chromium)
- **AI**: Claude Sonnet 4.6 qua Anthropic API
- **UI**: TailwindCSS + Alpine.js (CDN, không build step)

## Cài đặt local (iMac/Mac/Linux)

```bash
git clone https://github.com/YOUR_USERNAME/tiktok-research.git
cd tiktok-research

# Cài dependencies
pip install -r requirements.txt
python -m playwright install chromium

# Chạy
export ANTHROPIC_API_KEY="sk-ant-..."
python app.py
```

Mở browser: <http://localhost:5001>

## Deploy lên NAS (Synology DS223 ARM64)

```bash
# Copy code lên NAS
rsync -avz -e "ssh -p 2222" ./ henrynguyen@192.168.88.132:/volume1/HenryData/projects/tiktok-research/

# SSH vào NAS
ssh nas
cd /volume1/HenryData/projects/tiktok-research

# Set API key & start
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
docker compose up -d

# Xem log
docker compose logs -f
```

Mở browser trong LAN: <http://192.168.88.132:5001>

> ⚠️ **NAS RAM**: Container chiếm ~600–700MB (Chromium nặng). DS223 chỉ có ~1.1GB free — không chạy container nặng khác cùng lúc.

## Cách lấy `ms_token`

1. Mở Chrome → vào [tiktok.com](https://www.tiktok.com) → đăng nhập
2. Bấm `F12` → tab **Application** → **Cookies** → `https://www.tiktok.com`
3. Tìm cookie `msToken` → copy giá trị (~150 ký tự)
4. Paste vào UI

`ms_token` thường hết hạn sau vài giờ → lấy lại khi gặp lỗi.

## Workflow

1. Nhập `ms_token` + chọn hashtags (mặc định: `gymstore`, `gym`, `supplement`, `protein`, ...)
2. Chỉnh số video/hashtag và comment/video
3. Bấm **Bắt đầu Scrape** → xem log realtime
4. Khi scrape xong → tải CSV hoặc bấm **Phân tích với Claude**
5. Đọc báo cáo insight + tải file Markdown

## Cấu hình hashtag

Mặc định có sẵn `gymstore`, `gym`, `supplement`, `protein`, `wheyprotein`, `fitness`. Thêm/xóa trực tiếp trên UI hoặc sửa giá trị mặc định trong [`templates/index.html`](templates/index.html) (biến `hashtags` của Alpine).

## Cấu hình giới hạn

- **Video / hashtag**: 5–50 (slider trong UI)
- **Comment / video**: 20–200 (slider trong UI)
- Có thể chỉnh max trong [`app.py`](app.py) tại hàm `start_scrape`

## Output báo cáo gồm

1. **Top pain points** — xếp theo phổ biến
2. **Emotion triggers** — từ/cụm từ gây reaction mạnh
3. **Góc content đang win** — kèm ví dụ comment thực
4. **Hook ideas** — 5–8 hook dùng được luôn
5. **Key message** cho Gymstore
6. **Nên tránh** — điều khiến audience phản ứng tiêu cực

## Lưu ý pháp lý

Tool chỉ thu thập **comment công khai** trên video TikTok. Không thu thập thông tin cá nhân, không bypass auth, không spam, không upload. Dùng cho mục đích nghiên cứu thị trường nội bộ.

## License

Internal use — Gymstore.
