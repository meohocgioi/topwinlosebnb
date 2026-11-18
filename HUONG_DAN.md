# TopWinLose BNB — Hướng dẫn

## 1. Chạy tool
Chỉ cần **một file**: `TopWinLose.bat`. Tải về, để ở Desktop, bấm đúp để chạy.
- Lần đầu file tự tải tool, tự cài thư viện (và thử tự cài Python nếu máy chưa có).
- Trình duyệt tự mở http://127.0.0.1:8788. Giữ cửa sổ đen mở trong lúc dùng; đóng cửa sổ đen = tắt bot.
- Chạy song song với BabyBB được (BabyBB dùng cổng 8787, tool này 8788).
- Code và cài đặt nằm trong thư mục `C:\Users\<tên bạn>\TopWinLose` — bạn không cần đụng vào.

## 2. Tạo bot Telegram
1. Nhắn @BotFather → `/newbot` → lấy **Bot Token**. Phải là bot **mới** — không dùng chung token với BabyBB (2 tool cùng 1 bot sẽ giành lệnh của nhau).
2. Dán Bot Token vào trang tool → **Lưu cài đặt**.
3. **Chat ID chủ bot**: nếu máy đã có BabyBB, tool tự lấy Chat ID chủ bot từ BabyBB. Nếu ô còn trống: nhắn `/start` cho bot mới → bot trả về Chat ID → dán vào ô → Lưu.

## 3. Lệnh
| Lệnh | Tác dụng |
|---|---|
| `/start` hoặc `/top` | Bảng Top 15 Winner + Top 15 Loser 24h |
| `/win` | Chỉ Top 15 Winner |
| `/lose` | Chỉ Top 15 Loser |
| `/setting` | Tốc độ tự cập nhật bảng: 5s / 10s / 30s (mặc định 10s) |
| `/update` | Cập nhật bot lên bản mới nhất, gửi change log |
| `/help` | Danh sách lệnh |

- **Snapshot mỗi giờ:** sau khi gõ `/start` (hoặc `/top`, `/win`, `/lose`), cứ đúng mỗi đầu giờ (20:00, 21:00, … 07:00) bảng đang chạy được chốt lại, tiêu đề đổi thành `📸 Snap Shot at 20:00 · 18/11/2026`, và **giữ nguyên trong chat** để xem lại. Ngay bên dưới bot gửi bảng real time mới (tiêu đề `⚡ Real time update (fetch every 10s)`), nên bảng real time luôn nằm dưới cùng. Gõ lệnh lại chỉ xoá bảng real time cũ, không bao giờ xoá snapshot. Tool phải đang chạy vào đầu giờ thì mới chụp được (bật lại trong 5 phút đầu giờ vẫn chụp bù).
- Bảng tự sửa số liệu ngay trong tin; dưới tin có nút **🟢 Winner / 🔴 Loser / 📊 Cả 2** để đổi bảng.
- Gõ lệnh mới thì bảng cũ và lệnh cũ tự bị xoá, chat luôn gọn.
- **Người không phải chủ bot** chỉ dùng được `/start`: nhận 1 bảng chụp nhanh (không tự cập nhật, không có nút). Lệnh khác bị từ chối. Menu lệnh của họ cũng chỉ hiện `/start`.

## 4. Dữ liệu
- Nguồn: Binance Futures API công khai (`/fapi/v1/ticker/24hr`, `/fapi/v1/premiumIndex`, `/fapi/v1/exchangeInfo`), không cần API key.
- Tab **Crypto** = hợp đồng PERPETUAL ký quỹ USDT đang giao dịch, **không** gồm TradFi (cổ phiếu, vàng…), USDC và hợp đồng quý.
- Cột: Coin/Vol (khối lượng 24h bằng USDT), Price, 24h % (thay đổi giá 24h), Fund % (funding rate).

## 5. Cập nhật
Gõ `/update` cho bot (hoặc bấm **Update New Ver** trên trang tool). Tool tải bản mới từ repo này, chạy thử, thay file, khởi động lại rồi bot gửi change log. Bản mới lỗi khi khởi động thì tool tự quay về bản cũ. Tool **không** tự cập nhật khi bạn chưa ra lệnh.

Bot Token nằm trong `config.json` trên máy bạn — đừng upload file này lên GitHub.
