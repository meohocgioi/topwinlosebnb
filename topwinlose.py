# -*- coding: utf-8 -*-
"""
TopWinLose BNB — Bot Telegram: Top 15 Winner / Loser 24h cua Binance Futures (USDⓈ-M, tab Crypto).
Chay: bam dup TopWinLose.bat (Windows). Giao dien cai dat: http://127.0.0.1:8788
"""
VERSION = "1.1.0"

# Change log: ban moi nhat o tren cung. Bot gui phan nay sau moi lan /update.
CHANGELOG = [
    ("1.1.0", ["Snapshot mỗi giờ: đúng mỗi đầu giờ (20:00, 21:00…) bảng đang chạy được chốt lại thành bảng 📸 Snap Shot at HH:00 và giữ nguyên trong chat để xem lại",
               "Ngay dưới đó bot gửi bảng ⚡ Real time update mới (fetch every 10s) — bảng real time luôn nằm dưới cùng",
               "Gõ /start, /top, /win, /lose lại chỉ xoá bảng real time cũ, không bao giờ xoá các bảng snapshot"]),
    ("1.0.1", ["Bảng gọn cho vừa màn hình điện thoại, không phải kéo ngang: cột Coin/Vol · Price · 24h % · Fund %",
               "Bỏ dấu % trong từng ô (đã ghi ở tiêu đề cột); Funding còn 3 số lẻ (vd 0.005, -0.127)"]),
    ("1.0.0", ["Bản đầu tiên: /start, /top, /win, /lose — Top 15 Winner / Loser 24h của Binance Futures USDⓈ-M (tab Crypto)",
               "Bảng tự cập nhật trong cùng 1 tin (mặc định 10s/lần), nút chuyển Winner / Loser / Cả 2 ngay dưới tin",
               "Chỉ chủ bot dùng được các lệnh; người khác chỉ dùng /start (xem bảng, không tự cập nhật)",
               "/update: tải bản mới từ GitHub, tự kiểm tra, khởi động lại rồi gửi change log; bản lỗi thì tự quay về bản cũ",
               "/setting: chọn tốc độ tự cập nhật 5s / 10s / 30s"]),
]

import asyncio, json, os, re, sys, time, webbrowser
from datetime import datetime
from urllib.parse import urlparse

import aiohttp
from aiohttp import web

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
BABYBB_CFG = os.path.join(os.path.dirname(BASE_DIR), "BabyBB", "config.json")   # lay san Chat ID chu bot tu BabyBB
PORT = 8788                     # BabyBB dung 8787 -> 2 tool chay cung luc khong dung nhau
RESTART_CODE = 42
DEFAULT_UPDATE_URL = "https://raw.githubusercontent.com/meohocgioi/topwinlosebnb/main/topwinlose.py"
FAPI = os.environ.get("TWL_FAPI", "https://fapi.binance.com")
TG_API = os.environ.get("TWL_TG_API", "https://api.telegram.org")
TOP_N = 15
REFRESH_CHOICES = (5, 10, 30)
BOT_MAX_AGE = 120               # bo qua lenh cu hon 120s (gui luc tool dang tat)
GUEST_GAP = 15                  # nguoi ngoai: toi da 1 lan /start moi 15s
TRADFI_TYPES = {"EQUITY", "COMMODITY", "FOREX", "BOND", "ETF", "TRADFI"}

DEFAULT_CFG = {
    "bot_token": "", "bot_owner_id": "",
    "refresh": 10,                  # giay giua 2 lan bang tu cap nhat
    "widgets": True,                # True = Rich Message (bang), False = chu thuong
    "live_msg": None,               # [chat, message_id, rich, view] cua bang dang tu cap nhat
    "msg_track": {},
    "update_note": "",
    "update_url": DEFAULT_UPDATE_URL,
}

cfg = dict(DEFAULT_CFG)
logs = []
http = None
tg_http = None
botst = {"ok": False, "err": "", "last": 0, "name": "", "token": "", "cmds_for": None}
market = {"t": 0.0, "rows": [], "err": "", "err_t": 0.0, "syms": set(), "syms_t": 0.0, "backoff": 0.0}
live = {"chat": None, "mid": None, "rich": True, "view": "both", "t": 0.0, "wait": 0.0, "every": 0, "every_until": 0}
guests = {}                     # chat -> lan /start gan nhat
edit_lock = None                # asyncio.Lock: khong sua bang real time trong luc dang chup snapshot
PENDING = os.path.join(BASE_DIR, "update_pending")


def log(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    logs.insert(0, line)
    del logs[300:]
    try:
        print(line, flush=True)
    except Exception:
        pass


def load_cfg():
    global cfg
    cfg = dict(DEFAULT_CFG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception as e:
            log(f"Lỗi đọc config.json: {e}")
    if not str(cfg.get("update_url") or "").strip():
        cfg["update_url"] = DEFAULT_UPDATE_URL
    if not str(cfg.get("bot_owner_id") or "").strip():
        own = babybb_cfg().get("bot_owner_id")
        if own:
            cfg["bot_owner_id"] = str(own).strip()
            log(f"Đã lấy Chat ID chủ bot từ BabyBB: {cfg['bot_owner_id']}")
            save_cfg()


def save_cfg():
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)


def babybb_cfg():
    try:
        with open(BABYBB_CFG, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def owner():
    return str(cfg.get("bot_owner_id") or "").strip()


def refresh_s():
    try:
        v = int(cfg.get("refresh") or 10)
    except Exception:
        v = 10
    return v if v in REFRESH_CHOICES else 10


def ver_key(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except Exception:
        return (0,)


def changelog_since(old=None, limit=6):
    if old is None:
        return CHANGELOG[:1]
    return [e for e in CHANGELOG if ver_key(old) < ver_key(e[0]) <= ver_key(VERSION)][:limit] or CHANGELOG[:1]


# ----------------------------------------------------------------------------
# Rich message (giong BabyBB)
# ----------------------------------------------------------------------------
def B(t):
    return {"type": "bold", "text": t}


def K(t):
    return {"type": "code", "text": t}


def cell(text, header=False, align=None):
    c = {"text": text} if text != "" else {}
    if header:
        c["is_header"] = True
    if align:
        c["align"] = align
    return c


def r_head(text, size=3):
    return {"type": "heading", "text": text, "size": size}


def r_par(text):
    return {"type": "paragraph", "text": text}


def r_table(header, rows, aligns=None, show_header=True):
    aligns = aligns or [None] * len(header)
    cells = [[cell(B(h), True, a) for h, a in zip(header, aligns)]] if show_header else []
    cells += [[cell(v, False, a) for v, a in zip(r, aligns)] for r in rows]
    return {"type": "table", "cells": cells, "is_bordered": True, "is_striped": True, "is_compact": True}


def r_foot(text):
    return {"type": "footer", "text": text}


def chip(text, good):
    """So co mau (vien xanh / do) nhu cot 24h Chg cua Binance. Telegram khong nhan -> chu kem cham mau."""
    if botst.get("rich_buttons") is False:
        return f"{'🟢' if good else '🔴'} {text}"
    b = {"text": text, "callback_data": "noop"}
    if botst.get("chip_style") is not False:
        b["style"] = "success" if good else "danger"
    return {"type": "button", "button": b}


def changelog_msg(title, entries):
    T = [title] + [f"v{v}\n" + "\n".join(f"  • {c}" for c in ch) for v, ch in entries]
    blocks = [r_head(title),
              r_table(["Bản", "Thay đổi"], [[B(f"v{v}"), "\n".join(f"• {c}" for c in ch)] for v, ch in entries])]
    return "\n".join(T), blocks


# ----------------------------------------------------------------------------
# Du lieu Binance Futures
# ----------------------------------------------------------------------------
def crypto_symbols(info):
    """Tab USDⓈ-M -> Crypto: hop dong PERPETUAL, ky quy USDT, dang giao dich, khong phai TradFi.
    (TradFi = contractType TRADIFI_PERPETUAL / underlyingType EQUITY, COMMODITY...; USDC co tab rieng;
    hop dong quy (CURRENT_QUARTER...) cung bi bo.)"""
    out = set()
    for s in info.get("symbols") or []:
        if s.get("contractType") != "PERPETUAL" or s.get("quoteAsset") != "USDT" or s.get("status") != "TRADING":
            continue
        if str(s.get("underlyingType") or "COIN").upper() in TRADFI_TYPES:
            continue
        out.add(s["symbol"])
    return out


def build_rows(syms, tickers, prem):
    fund = {p.get("symbol"): p.get("lastFundingRate") for p in prem or []}
    rows = []
    for t in tickers or []:
        s = t.get("symbol")
        if s not in syms:
            continue
        try:
            rows.append({"sym": s, "coin": s[:-4] if s.endswith("USDT") else s,
                         "price": t.get("lastPrice"), "chg": float(t.get("priceChangePercent") or 0),
                         "vol": float(t.get("quoteVolume") or 0), "fund": float(fund.get(s) or 0)})
        except (TypeError, ValueError):
            continue
    return rows


def winners(rows):
    return sorted(rows, key=lambda r: -r["chg"])[:TOP_N]


def losers(rows):
    return sorted(rows, key=lambda r: r["chg"])[:TOP_N]


async def bn_get(path):
    async with http.get(FAPI + path) as r:
        if r.status in (418, 429):
            ra = float(r.headers.get("Retry-After") or 60)
            market["backoff"] = time.time() + ra
            raise RuntimeError(f"Binance giới hạn tốc độ (HTTP {r.status}), chờ {ra:.0f}s")
        if r.status == 451:
            raise RuntimeError("Binance chặn vùng / IP này (HTTP 451)")
        if r.status != 200:
            raise RuntimeError(f"Binance HTTP {r.status}")
        return await r.json(content_type=None)


async def refresh_market(force=False):
    """Lay du lieu moi neu cu hon refresh_s()-1 giay. Loi -> giu du lieu cu va ghi loi."""
    now = time.time()
    if not force and now - market["t"] < max(3, refresh_s() - 1):
        return
    if now < market["backoff"]:
        return
    try:
        if not market["syms"] or now - market["syms_t"] > 600:     # danh sach hop dong: 10 phut lay lai 1 lan
            syms = crypto_symbols(await bn_get("/fapi/v1/exchangeInfo"))
            if syms:
                market.update(syms=syms, syms_t=now)
        tickers, prem = await asyncio.gather(bn_get("/fapi/v1/ticker/24hr"), bn_get("/fapi/v1/premiumIndex"))
        rows = build_rows(market["syms"], tickers, prem)
        if not rows:
            raise RuntimeError("Binance trả về danh sách rỗng")
        if market["err"]:
            log("✅ Lấy được dữ liệu Binance trở lại")
        market.update(t=time.time(), rows=rows, err="")
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:120]}" if not isinstance(e, RuntimeError) else str(e)
        if err != market["err"]:
            log(f"⚠️ Lấy dữ liệu Binance lỗi: {err}")
        market.update(err=err, err_t=time.time())


# ----------------------------------------------------------------------------
# Trinh bay
# ----------------------------------------------------------------------------
VIEWS = {"both": "📊 Cả 2", "win": "🟢 Winner", "lose": "🔴 Loser"}
HEAD = ["Coin/Vol", "Price", "24h %", "Fund %"]
ALIGN = [None, "right", "right", "right"]


def fmt_vol(v):
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if v >= div:
            return f"{v / div:.2f}{suf}"
    return f"{v:.2f}"


def fmt_price(p):
    s = str(p or "0")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def fmt_chg(c):
    return f"{c:+.2f}"


def fmt_fund(f):
    return f"{f * 100:.3f}"


def stamp():
    if market["t"]:
        s = f"Binance USDⓈ-M · Crypto · Last Update: {datetime.fromtimestamp(market['t']).strftime('%H:%M:%S')}"
    else:
        s = "Binance USDⓈ-M · Crypto · chưa có dữ liệu"
    if market["err"]:
        s += f"\n⚠️ {market['err']}"
    return s


def table_rows(rows):
    return [[[B(r["coin"]), f"\n{fmt_vol(r['vol'])}"], fmt_price(r["price"]),
             [chip(fmt_chg(r["chg"]), r["chg"] >= 0)], fmt_fund(r["fund"])] for r in rows]


def snap_label(ts):
    d = datetime.fromtimestamp(ts)
    return f"📸 Snap Shot at {d.strftime('%H:%M')} · {d.strftime('%d/%m/%Y')}"


def sub_label(snap=None):
    return snap_label(snap) if snap else f"⚡ Real time update (fetch every {refresh_s()}s)"


def snap_stamp():
    t = f" · dữ liệu lúc {datetime.fromtimestamp(market['t']).strftime('%H:%M:%S')}" if market["t"] else ""
    return "Binance USDⓈ-M · Crypto" + t


def board_blocks(view="both", note=None, snap=None):
    rows = market["rows"]
    blocks = []
    if note:
        blocks.append(r_par(note))
    if not rows:
        blocks.append(r_head("📊 Top Winner / Loser 24h"))
        blocks.append(r_par("Chưa lấy được dữ liệu từ Binance."))
    for key, title, pick in (("win", f"🟢 Top {TOP_N} Winner · 24h", winners),
                             ("lose", f"🔴 Top {TOP_N} Loser · 24h", losers)):
        if rows and view in (key, "both"):
            blocks.append(r_head(title))
            blocks.append(r_par(B(sub_label(snap))))
            blocks.append(r_table(HEAD, table_rows(pick(rows)), ALIGN))
    blocks.append(r_foot(snap_stamp() if snap else stamp()))
    return blocks


def board_text(view="both", note=None, snap=None):
    rows = market["rows"]
    L = [note] if note else []
    if not rows:
        L.append("Chưa lấy được dữ liệu từ Binance.")
    for key, title, pick in (("win", f"🟢 Top {TOP_N} Winner · 24h", winners),
                             ("lose", f"🔴 Top {TOP_N} Loser · 24h", losers)):
        if rows and view in (key, "both"):
            L.append(title)
            L.append(sub_label(snap))
            for i, r in enumerate(pick(rows), 1):
                L.append(f"{i:>2}. {r['coin']:<10} {fmt_price(r['price']):>10}  {'🟢' if r['chg'] >= 0 else '🔴'}{fmt_chg(r['chg']):>8}%"
                         f"  F {fmt_fund(r['fund'])}%  V {fmt_vol(r['vol'])}")
            L.append("")
    L.append(snap_stamp() if snap else stamp())
    return "\n".join(L)


def board_kb(view):
    return {"inline_keyboard": [[{"text": ("• " if view == k else "") + v, "callback_data": f"v:{k}"}
                                 for k, v in (("win", VIEWS["win"]), ("lose", VIEWS["lose"]), ("both", VIEWS["both"]))]]}


HELP_ITEMS = [
    ("/start", "Bảng Top 15 Winner + Loser 24h real time; mỗi đầu giờ tự chụp 1 bảng snapshot giữ lại trong chat"),
    ("/top", "Giống /start"),
    ("/win", "Chỉ Top 15 Winner"),
    ("/lose", "Chỉ Top 15 Loser"),
    ("/setting", "Tốc độ tự cập nhật bảng: 5s / 10s / 30s"),
    ("/update", "Cập nhật bot lên bản mới nhất và gửi change log"),
    ("/help", "Danh sách lệnh"),
]
HELP_TEXT = "📖 Các lệnh:\n" + "\n".join(f"{c} — {d}" for c, d in HELP_ITEMS)


def help_blocks():
    return [r_head(f"📖 Các lệnh — v{VERSION}"),
            r_table(["Lệnh", "Tác dụng"], [[K(c), d] for c, d in HELP_ITEMS]),
            r_foot("Dữ liệu: Binance Futures USDⓈ-M, tab Crypto (perp USDT, không gồm TradFi / USDC). "
                   "Người khác chỉ dùng được /start.")]


def setting_view(note=None):
    cur = refresh_s()
    text = f"⚙️ Cài đặt\nTự cập nhật bảng: {cur}s/lần" + (f"\n{note}" if note else "")
    kb = {"inline_keyboard": [[{"text": ("• " if s == cur else "") + f"{s}s", "callback_data": f"r:{s}"} for s in REFRESH_CHOICES]]}
    return text, kb


# ----------------------------------------------------------------------------
# Telegram Bot API
# ----------------------------------------------------------------------------
async def bot_api(method, _timeout=10, _quiet=False, **params):
    if not cfg["bot_token"]:
        return {}
    url = f"{TG_API}/bot{cfg['bot_token']}/{method}"
    try:
        to = aiohttp.ClientTimeout(total=_timeout, sock_connect=5)
        async with tg_http.post(url, json=params, timeout=to) as r:
            j = await r.json(content_type=None)
    except Exception as e:
        j = {"ok": False, "description": f"{type(e).__name__}: {str(e)[:100]}".rstrip(": ")}
    if not j.get("ok") and not _quiet:
        log(f"⚠️ Bot Telegram {method} lỗi: {j.get('description')}")
    return j


def _net_err(desc):
    d = str(desc)
    return any(x in d for x in ("Timeout", "Connect", "Disconnected", "ServerDisconnected", "ClientOSError"))


async def _send(chat, text, kb=None):
    extra = {"reply_markup": kb} if kb else {}
    desc = ""
    for _ in range(4):
        r = await bot_api("sendMessage", _quiet=True, chat_id=chat, text=text[:4000], **extra)
        if r.get("ok"):
            return (r.get("result") or {}).get("message_id"), False
        desc = str(r.get("description"))
        if not _net_err(desc):
            break
    log(f"⚠️ Bot không gửi được tin: {desc}")
    return None, False


def _fallback(desc):
    """Telegram chua nhan nut / mau trong rich message -> tat tinh nang do. -> True neu nen thu lai."""
    d = desc.lower()
    if "style" in d and botst.get("chip_style") is not False:
        botst["chip_style"] = False
        log(f"Telegram không nhận màu ô ({desc[:100]}) — hiện chấm màu")
        return True
    if "button" in d and botst.get("rich_buttons") is not False:
        botst["rich_buttons"] = False
        log(f"Telegram không nhận nút trong bảng ({desc[:100]}) — hiện chấm màu")
        return True
    return False


async def _send_rich(chat, text, make_blocks, kb=None):
    """make_blocks(): dung lai blocks sau khi tat tinh nang Telegram chua ho tro."""
    extra = {"reply_markup": kb} if kb else {}
    if cfg.get("widgets", True) and botst.get("rich") is not False:
        for _ in range(4):
            r = await bot_api("sendRichMessage", _quiet=True, chat_id=chat, rich_message={"blocks": make_blocks()}, **extra)
            if r.get("ok"):
                botst["rich"] = True
                return (r.get("result") or {}).get("message_id"), True
            desc = str(r.get("description"))
            if "Too Many Requests" in desc:
                log("Telegram đang giới hạn tốc độ gửi tin — bỏ qua tin này")
                return None, False
            if _fallback(desc) or _net_err(desc):
                continue
            if "not found" in desc.lower() or "404" in desc:
                botst["rich"] = False
            log(f"Rich message bị Telegram từ chối ({desc[:120]}) — gửi bản chữ")
            break
    return await _send(chat, text, kb)


async def tg_delete(chat, mids):
    mids = sorted({int(x) for x in mids if x})
    if not mids or not chat:
        return
    r = await bot_api("deleteMessages", _quiet=True, chat_id=chat, message_ids=mids[:100])
    if not r.get("ok"):
        for x in mids:
            await bot_api("deleteMessage", _quiet=True, chat_id=chat, message_id=x)


def track_new(key, chat, *mids, also_old=()):
    """Nhom tin moi cho lenh key; xoa nhom tin cu cua lenh do (chat gon nhu BabyBB)."""
    tr = cfg.setdefault("msg_track", {})
    old = tr.get(key) or {}
    tr[key] = {"chat": str(chat), "mids": [int(m) for m in mids if m]}
    save_cfg()
    gone = [m for m in (old.get("mids") or []) + list(also_old) if m and int(m) not in tr[key]["mids"]]
    if gone:
        asyncio.create_task(tg_delete(old.get("chat") or str(chat), gone))


def track_add(key, chat, *mids):
    tr = cfg.setdefault("msg_track", {})
    g = tr.setdefault(key, {"chat": str(chat), "mids": []})
    g["mids"] += [int(m) for m in mids if m]
    save_cfg()


async def set_commands():
    """Menu lenh: nguoi ngoai chi thay /start; chu bot thay du lenh."""
    base = [{"command": "start", "description": "Top 15 Winner / Loser 24h Binance Futures"}]
    await bot_api("setMyCommands", _quiet=True, commands=base)
    if owner():
        full = [{"command": c.lstrip("/"), "description": d[:100]} for c, d in HELP_ITEMS]
        r = await bot_api("setMyCommands", _quiet=True, commands=full, scope={"type": "chat", "chat_id": int(owner())})
        if r.get("ok"):
            botst["cmds_for"] = owner()


# --- Bang tu cap nhat ---
async def start_live(chat, view, user_mid=None):
    async with edit_lock:
        await _start_live(chat, view, user_mid)


async def _start_live(chat, view, user_mid=None):
    old = (live["chat"], live["mid"])
    await refresh_market(force=time.time() - market["t"] > 3)
    live.update(chat=None, mid=None)
    mid, rich = await _send_rich(chat, board_text(view), lambda: board_blocks(view), board_kb(view))
    if mid:
        live.update(chat=chat, mid=mid, rich=rich, view=view, t=time.time(), wait=0.0)
        cfg["live_msg"] = [chat, mid, rich, view]
        cfg["snap_last"] = datetime.now().strftime("%Y%m%d%H")      # snapshot dau tien: dau gio tiep theo
        save_cfg()
        track_new("board", chat, mid, user_mid, also_old=[old[1]] if str(old[0]) == str(chat) else [])
    elif old[1]:
        live.update(chat=old[0], mid=old[1])


async def live_edit(final=False):
    view = live["view"]
    p = {"chat_id": live["chat"], "message_id": live["mid"]}
    note = "⏹ Đã ngừng cập nhật — xem bảng mới hơn" if final else None
    if not final:
        p["reply_markup"] = board_kb(view)
    if live["rich"]:
        for _ in range(3):
            p["rich_message"] = {"blocks": board_blocks(view, note)}
            r = await bot_api("editMessageText", _quiet=True, **p)
            if r.get("ok") or not _fallback(str(r.get("description") or "")):
                return r
        return r
    p["text"] = board_text(view, note)[:4000]
    return await bot_api("editMessageText", _quiet=True, **p)


async def live_loop():
    lm = cfg.get("live_msg")
    if lm and len(lm) >= 3:                 # tiep tuc sau khi khoi dong lai / update
        live.update(chat=lm[0], mid=lm[1], rich=bool(lm[2]), view=lm[3] if len(lm) > 3 else "both")
    while True:
        await asyncio.sleep(1)
        try:
            if not live["mid"] or not cfg["bot_token"]:
                continue
            now = time.time()
            every = live["every"] if now < live["every_until"] else refresh_s()
            if now < live["wait"] or now - live["t"] < every:
                continue
            await refresh_market()
            async with edit_lock:
                if not live["mid"]:
                    continue
                r = await live_edit()
            desc = str(r.get("description") or "")
            if r.get("ok") or "not modified" in desc:
                live["t"] = time.time()
            elif "Too Many Requests" in desc or "retry after" in desc.lower():
                wait = float((r.get("parameters") or {}).get("retry_after") or 10)
                live["wait"] = time.time() + wait + 1
                live["every"] = min(60, max(refresh_s() * 2, 15))
                live["every_until"] = time.time() + wait + 3600
                log(f"Telegram giới hạn tốc độ sửa tin — chờ {wait:.0f}s, sau đó {live['every']}s/lần trong 1 tiếng")
            elif _net_err(desc) or not desc:
                live["wait"] = time.time() + 5
            else:                              # tin da bi xoa / khong sua duoc
                log(f"Ngừng tự cập nhật bảng: {desc[:100]}")
                live.update(chat=None, mid=None)
                cfg["live_msg"] = None
                save_cfg()
        except Exception as e:
            log(f"live: {type(e).__name__}: {e}")


SNAP_WINDOW = 5 * 60          # tool vua bat lai trong 5 phut dau gio van chup bu


async def take_snapshot(key):
    """Chot bang real time hien tai thanh bang snapshot (giu lai, khong xoa) roi gui bang real time moi ben duoi."""
    chat, mid, rich, view = live["chat"], live["mid"], live["rich"], live["view"]
    await refresh_market(force=True)
    ts = time.time()
    if not market["rows"]:
        return False
    p = {"chat_id": chat, "message_id": mid, "reply_markup": {"inline_keyboard": []}}
    r = {}
    if rich:
        for _ in range(3):
            p["rich_message"] = {"blocks": board_blocks(view, snap=ts)}
            r = await bot_api("editMessageText", _quiet=True, **p)
            if r.get("ok") or not _fallback(str(r.get("description") or "")):
                break
    else:
        p["text"] = board_text(view, snap=ts)[:4000]
        r = await bot_api("editMessageText", _quiet=True, **p)
    desc = str(r.get("description") or "")
    if not (r.get("ok") or "not modified" in desc):
        if _net_err(desc) or "Too Many Requests" in desc:
            return False                   # thu lai sau
        await _send_rich(chat, board_text(view, snap=ts), lambda: board_blocks(view, snap=ts))   # tin cu mat -> gui snapshot moi
    mid2, rich2 = await _send_rich(chat, board_text(view), lambda: board_blocks(view), board_kb(view))
    if mid2:
        live.update(mid=mid2, rich=rich2, t=time.time(), wait=0.0)
        cfg["live_msg"] = [chat, mid2, rich2, view]
    else:
        live.update(chat=None, mid=None)
        cfg["live_msg"] = None
    cfg["snap_last"] = key
    cfg.setdefault("msg_track", {})["board"] = {"chat": str(chat), "mids": [int(mid2)] if mid2 else []}   # snapshot khong bi xoa
    save_cfg()
    log(f"📸 Snapshot {datetime.fromtimestamp(ts).strftime('%H:%M %d/%m')} — bảng real time mới ở dưới")
    return True


async def snap_loop():
    while True:
        await asyncio.sleep(2)
        try:
            if not live["mid"] or not cfg["bot_token"]:
                continue
            now = datetime.now()
            key = now.strftime("%Y%m%d%H")
            if cfg.get("snap_last") == key or now.minute * 60 + now.second >= SNAP_WINDOW:
                continue
            async with edit_lock:
                if live["mid"]:
                    await take_snapshot(key)
        except Exception as e:
            log(f"snapshot: {type(e).__name__}: {e}")
            await asyncio.sleep(10)


async def guest_start(chat, m):
    """Nguoi khong phai chu bot: chi /start -> 1 bang chup nhanh, khong tu cap nhat, khong nut."""
    now = time.time()
    if now - guests.get(chat, 0) < GUEST_GAP:
        return
    guests[chat] = now
    if len(guests) > 2000:
        guests.clear()
    await refresh_market(force=now - market["t"] > 10)
    note = "Bot riêng — bạn chỉ dùng được /start."
    if not owner():
        note = f"Bot chưa có chủ. Chat ID của bạn: {chat} — nhập số này vào ô 'Chat ID chủ bot' trên tool."
    await _send_rich(chat, board_text("both", note), lambda: board_blocks("both", note))


async def handle_callback(cq):
    data = cq.get("data") or ""
    frm = str((cq.get("from") or {}).get("id"))
    msg = cq.get("message") or {}
    chat = str((msg.get("chat") or {}).get("id") or "")
    mid = msg.get("message_id")
    if data == "noop":
        return await bot_api("answerCallbackQuery", _quiet=True, callback_query_id=cq["id"])
    if not owner() or frm != owner():
        return await bot_api("answerCallbackQuery", _quiet=True, callback_query_id=cq["id"],
                             text="⛔ Chỉ chủ bot dùng được nút này", show_alert=False)
    await bot_api("answerCallbackQuery", _quiet=True, callback_query_id=cq["id"])
    if data.startswith("v:") and data[2:] in VIEWS:
        view = data[2:]
        if live["mid"] and str(live["chat"]) == chat and live["mid"] == mid:
            live["view"] = view
            cfg["live_msg"] = [live["chat"], live["mid"], live["rich"], view]
            save_cfg()
            async with edit_lock:
                r = await live_edit()
            if r.get("ok"):
                live["t"] = time.time()
        else:
            await start_live(chat, view)
    elif data.startswith("r:"):
        try:
            s = int(data[2:])
        except ValueError:
            return
        if s in REFRESH_CHOICES:
            cfg["refresh"] = s
            save_cfg()
            log(f"⚙️ Tự cập nhật bảng: {s}s/lần")
            text, kb = setting_view(f"✅ Đã đổi sang {s}s/lần")
            await bot_api("editMessageText", _quiet=True, chat_id=chat, message_id=mid, text=text, reply_markup=kb)


async def handle_update(u):
    if u.get("callback_query"):
        return await handle_callback(u["callback_query"])
    m = u.get("message") or {}
    chat = str((m.get("chat") or {}).get("id", ""))
    text = (m.get("text") or "").strip()
    if not chat or not text:
        return
    age = time.time() - m.get("date", time.time())
    if age > BOT_MAX_AGE:
        return
    cmd = text.split()[0].split("@")[0].lower()
    umid = m.get("message_id")
    is_owner = bool(owner()) and chat == owner() and (m.get("chat") or {}).get("type", "private") == "private"
    log(f"📩 {'Chủ bot' if is_owner else 'Người khác'} ({chat}): {text[:40]}")
    if not is_owner:
        if cmd == "/start":
            await guest_start(chat, m)
        else:
            await _send(chat, "⛔ Bot riêng — bạn chỉ dùng được /start." if owner() else
                        f"Bot chưa có chủ. Chat ID của bạn: {chat}\nNhập số này vào ô 'Chat ID chủ bot' trên tool.")
        return
    if cmd in ("/start", "/top"):
        await start_live(chat, "both", umid)
    elif cmd == "/win":
        await start_live(chat, "win", umid)
    elif cmd == "/lose":
        await start_live(chat, "lose", umid)
    elif cmd == "/setting":
        text, kb = setting_view()
        rm, _ = await _send(chat, text, kb)
        track_new("setting", chat, rm, umid)
    elif cmd == "/update":
        log("⬆️ /update (từ Telegram)")
        track_new("update", chat, umid)
        ok, msg, rs = await do_update("lệnh /update")
        if ok and not rs:
            t, b = changelog_msg(f"✅ Đang là bản mới nhất — v{VERSION}", changelog_since())
            rm, _ = await _send_rich(chat, t, lambda: b)
            track_add("update", chat, rm)
            return
        rm, _ = await _send(chat, ("⬆️ " if ok else "⚠️ ") + msg + ("\nBot sẽ gửi change log sau vài giây." if rs else ""))
        track_add("update", chat, rm)
    else:
        rm, _ = await _send_rich(chat, HELP_TEXT, help_blocks)
        track_new("help", chat, rm, umid)


async def send_update_note():
    """Sau khi cap nhat / quay ve ban cu: gui change log cho chu bot, thu lai toi khi gui duoc."""
    for _ in range(40):
        await asyncio.sleep(3)
        note = cfg.get("update_note")
        if not note:
            return
        if not (cfg["bot_token"] and owner()):
            continue
        try:
            m_old = re.search(r"(\d+(?:\.\d+)+) →", note)
            if note.startswith("⬆️") and m_old:
                t, b = changelog_msg(f"⬆️ Đã cập nhật v{m_old.group(1)} → v{VERSION}", changelog_since(m_old.group(1)))
                rm, _ = await _send_rich(owner(), t, lambda: b)
            else:
                rm, _ = await _send(owner(), note)
            if rm:
                cfg["update_note"] = ""
                save_cfg()
                track_add("update", owner(), rm)
                log(f"Đã gửi change log v{VERSION} qua bot")
                return
        except Exception as e:
            log(f"Gửi change log lỗi: {type(e).__name__}: {str(e)[:100]}")


async def bot_loop():
    offset = None
    while True:
        try:
            if not cfg["bot_token"]:
                botst.update(ok=False, err="")
                await asyncio.sleep(3)
                continue
            p = {"timeout": 25, "allowed_updates": ["message", "callback_query"]}
            if offset:
                p["offset"] = offset
            r = await bot_api("getUpdates", _timeout=40, _quiet=True, **p)
            if not r.get("ok"):
                err = str(r.get("description") or "không kết nối được Telegram")
                if err != botst["err"]:
                    log(f"⚠️ Bot Telegram không nhận được lệnh: {err}")
                    if "conflict" in err.lower():
                        log("⚠️ Bot này đang được 1 chương trình khác dùng (vd BabyBB dùng chung token, hoặc 2 cửa sổ tool). "
                            "Mỗi tool phải có bot riêng.")
                botst.update(ok=False, err=err)
                await asyncio.sleep(3)
                continue
            if not botst["ok"] or botst["token"] != cfg["bot_token"]:
                me = await bot_api("getMe", _quiet=True)
                botst["name"] = "@" + str((me.get("result") or {}).get("username") or "?")
                botst["token"] = cfg["bot_token"]
                botst["cmds_for"] = None
                log(f"🤖 Bot Telegram đã kết nối: {botst['name']}")
            if botst["cmds_for"] != owner():
                await set_commands()
            botst.update(ok=True, err="", last=time.time())
            for u in r["result"]:
                offset = u["update_id"] + 1
                try:
                    await handle_update(u)
                except Exception as e:
                    log(f"⚠️ Lỗi xử lý lệnh bot: {type(e).__name__}: {e}")
        except Exception as e:
            log(f"⚠️ bot loop: {type(e).__name__}: {e}")
            await asyncio.sleep(3)


# ----------------------------------------------------------------------------
# Update tu GitHub (giong BabyBB)
# ----------------------------------------------------------------------------
def _api_url(url):
    """raw.githubusercontent.com bi cache ~5 phut -> dung GitHub API (luon moi nhat)."""
    m = re.match(r"https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)$", url)
    return f"https://api.github.com/repos/{m.group(1)}/{m.group(2)}/contents/{m.group(4)}?ref={m.group(3)}" if m else None


async def fetch_latest():
    url = cfg["update_url"].strip()
    api = _api_url(url)
    tries = ([(api, {"Accept": "application/vnd.github.raw"})] if api else []) + \
            [(f"{url}{'&' if '?' in url else '?'}t={int(time.time())}", {})]
    err = ""
    for u, h in tries:
        try:
            async with http.get(u, headers=h) as r:
                if r.status == 200:
                    return await r.text(), None
                err = f"Tải file lỗi HTTP {r.status}"
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:80]}"
    return None, err


def _selftest_file(path):
    import subprocess
    try:
        r = subprocess.run([sys.executable, path, "--selftest"], capture_output=True, timeout=60)
        out = (r.stdout + r.stderr).decode("utf-8", "replace").strip().splitlines()
        return r.returncode == 0, (out[-1] if out else f"exit {r.returncode}")
    except Exception as e:
        return False, str(e)


async def do_update(source="tool"):
    """-> (ok, msg, restart)"""
    code, err = await fetch_latest()
    if code is None:
        return False, err, False
    m = re.search(r'^VERSION\s*=\s*"([^"]+)"', code, re.M)
    if not m:
        return False, "File tải về không phải tool này (thiếu VERSION)", False
    new = m.group(1)
    if new == VERSION:
        return True, f"Đang là bản mới nhất ({VERSION})", False
    try:
        compile(code, "topwinlose.py", "exec")
    except SyntaxError as e:
        return False, f"Bản {new} bị lỗi code, giữ bản {VERSION}: {e}", False
    me = os.path.abspath(__file__)
    tmp = os.path.join(BASE_DIR, "topwinlose_new.py")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(code)
    ok, why = await asyncio.to_thread(_selftest_file, tmp)
    if not ok:
        try:
            os.remove(tmp)
        except Exception:
            pass
        return False, f"Bản {new} không qua được bước tự kiểm tra, giữ bản {VERSION}: {why[:150]}", False
    with open(me, "r", encoding="utf-8") as f:
        old = f.read()
    with open(me + ".bak", "w", encoding="utf-8", newline="\n") as f:
        f.write(old)
    os.replace(tmp, me)
    with open(PENDING, "w") as f:
        f.write(VERSION)
    cfg["update_note"] = f"⬆️ Đã cập nhật {VERSION} → {new} ({source})"
    save_cfg()
    log(f"⬆️ Update {VERSION} -> {new} ({source}), đang khởi động lại...")
    asyncio.get_event_loop().call_later(1.0, restart)
    return True, f"Đã update lên {new} — bot tự khởi động lại", True


async def clear_pending_later():
    await asyncio.sleep(45)
    if os.path.exists(PENDING):
        try:
            os.remove(PENDING)
        except Exception:
            pass


def restart():
    if os.environ.get("TWL_LAUNCHER"):
        os._exit(RESTART_CODE)          # TopWinLose.bat se chay lai
    import subprocess
    env = dict(os.environ, TWL_RESTARTED="1")
    subprocess.Popen([sys.executable, os.path.abspath(__file__)], env=env)
    os._exit(0)


def selftest():
    info = {"symbols": [
        {"symbol": "BTCUSDT", "contractType": "PERPETUAL", "quoteAsset": "USDT", "status": "TRADING", "underlyingType": "COIN"},
        {"symbol": "BTCDOMUSDT", "contractType": "PERPETUAL", "quoteAsset": "USDT", "status": "TRADING", "underlyingType": "INDEX"},
        {"symbol": "TSLAUSDT", "contractType": "TRADIFI_PERPETUAL", "quoteAsset": "USDT", "status": "TRADING", "underlyingType": "EQUITY"},
        {"symbol": "XAUUSDT", "contractType": "PERPETUAL", "quoteAsset": "USDT", "status": "TRADING", "underlyingType": "COMMODITY"},
        {"symbol": "BTCUSDC", "contractType": "PERPETUAL", "quoteAsset": "USDC", "status": "TRADING", "underlyingType": "COIN"},
        {"symbol": "BTCUSDT_261225", "contractType": "CURRENT_QUARTER", "quoteAsset": "USDT", "status": "TRADING", "underlyingType": "COIN"},
        {"symbol": "OLDUSDT", "contractType": "PERPETUAL", "quoteAsset": "USDT", "status": "SETTLING", "underlyingType": "COIN"}]}
    syms = crypto_symbols(info)
    assert syms == {"BTCUSDT", "BTCDOMUSDT"}, syms
    tick = [{"symbol": f"C{i}USDT", "lastPrice": f"{0.001 * (i + 1):.6f}", "priceChangePercent": f"{i * 3 - 40:.3f}",
             "quoteVolume": str(1234567.0 * (i + 1))} for i in range(40)] + [{"symbol": "TSLAUSDT", "priceChangePercent": "99"}]
    prem = [{"symbol": f"C{i}USDT", "lastFundingRate": "-0.00011141" if i % 3 else "0.00005"} for i in range(40)]
    rows = build_rows({f"C{i}USDT" for i in range(40)}, tick, prem)
    assert len(rows) == 40 and winners(rows)[0]["coin"] == "C39" and losers(rows)[0]["coin"] == "C0"
    assert len(winners(rows)) == TOP_N == len(losers(rows))
    assert fmt_vol(729.84e6) == "729.84M" and fmt_vol(1.5e9) == "1.50B" and fmt_price("0.0010670") == "0.001067"
    assert fmt_chg(92.484) == "+92.48" and fmt_chg(-15.674) == "-15.67" and fmt_fund(0.00005) == "0.005"
    assert fmt_fund(-0.0111233) == "-1.112"
    market.update(rows=rows, t=time.time())
    for v in VIEWS:
        json.dumps([board_blocks(v), board_kb(v), board_blocks(v, "x")], ensure_ascii=False)
        assert "Top" in board_text(v)
    for v in VIEWS:
        assert "Snap Shot at" in json.dumps(board_blocks(v, snap=time.time()), ensure_ascii=False)
        assert "Real time update" in board_text(v) and "Snap Shot at" in board_text(v, snap=time.time())
    json.dumps([help_blocks(), changelog_msg("x", changelog_since("0.0.1")), setting_view()], ensure_ascii=False)
    assert CHANGELOG[0][0] == VERSION, "CHANGELOG thieu ban hien tai"
    assert "__VERSION__" in HTML
    print("selftest ok", VERSION)


# ----------------------------------------------------------------------------
# Giao dien cai dat (chi may ban mo duoc)
# ----------------------------------------------------------------------------
async def h_index(req):
    return web.Response(text=HTML.replace("__VERSION__", VERSION), content_type="text/html")


async def h_state(req):
    bb = babybb_cfg()
    same = bool(cfg["bot_token"]) and str(bb.get("bot_token") or "").strip() == cfg["bot_token"]
    return web.json_response({
        "version": VERSION, "has_token": bool(cfg["bot_token"]), "owner": owner(), "refresh": refresh_s(),
        "bot": botst["name"] if botst["ok"] else "", "bot_err": botst["err"], "same_as_babybb": same,
        "data": f"{len(market['rows'])} coin · {datetime.fromtimestamp(market['t']).strftime('%H:%M:%S')}" if market["t"] else "",
        "data_err": market["err"], "logs": logs[:120]})


async def h_save(req):
    b = await req.json()
    tok = str(b.get("bot_token") or "").strip()
    if tok:
        if tok == str(babybb_cfg().get("bot_token") or "").strip():
            return web.json_response({"ok": False, "msg": "Token này là bot của BabyBB. Hãy tạo bot MỚI ở @BotFather cho tool này."})
        cfg["bot_token"] = tok
    if "bot_owner_id" in b:
        cfg["bot_owner_id"] = re.sub(r"[^\d-]", "", str(b.get("bot_owner_id") or ""))
    save_cfg()
    log("💾 Đã lưu cài đặt")
    return web.json_response({"ok": True, "msg": "Đã lưu cài đặt"})


async def h_update(req):
    ok, msg, rs = await do_update("bấm nút trên tool")
    return web.json_response({"ok": ok, "msg": msg, "restart": rs})


@web.middleware
async def guard(req, handler):
    origin = req.headers.get("Origin")
    if req.method == "POST" and origin and urlparse(origin).netloc != req.host:
        return web.json_response({"ok": False, "msg": "forbidden"}, status=403)
    return await handler(req)


async def main():
    global http, tg_http, edit_lock
    load_cfg()
    edit_lock = asyncio.Lock()
    http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
    tg_http = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=20, keepalive_timeout=90))
    app = web.Application(middlewares=[guard])
    app.add_routes([web.get("/", h_index), web.get("/api/state", h_state),
                    web.post("/api/config", h_save), web.post("/api/update", h_update)])
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", PORT).start()
    log(f"TopWinLose v{VERSION} đang chạy: http://127.0.0.1:{PORT}")
    if not os.environ.get("TWL_RESTARTED") and not os.environ.get("TWL_NO_BROWSER"):
        try:
            webbrowser.open(f"http://127.0.0.1:{PORT}")
        except Exception:
            pass
    await refresh_market(force=True)
    if market["rows"]:
        log(f"Đã lấy dữ liệu {len(market['rows'])} hợp đồng Crypto USDT perp")
    asyncio.create_task(bot_loop())
    asyncio.create_task(live_loop())
    asyncio.create_task(snap_loop())
    asyncio.create_task(send_update_note())
    asyncio.create_task(clear_pending_later())
    await asyncio.Event().wait()


HTML = r"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><title>TopWinLose BNB</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0e1116;--card:#171b22;--line:#262c36;--tx:#e6e9ee;--mut:#8b94a3;--gr:#20c997;--rd:#ff5c5c;--yl:#f0b90b;--bl:#4c8dff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.5 "Segoe UI",system-ui,sans-serif}
.wrap{max-width:820px;margin:0 auto;padding:18px}
header{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:14px}
h1{font-size:19px;margin:0;margin-right:auto}h1 small{color:var(--mut);font-weight:400;font-size:12px}
h2{font-size:14px;margin:0 0 10px;color:var(--yl);text-transform:uppercase;letter-spacing:.05em}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin-bottom:14px}
button{border:0;border-radius:7px;padding:8px 14px;font:600 13px inherit;cursor:pointer;color:#fff;background:#2c3440}
button:hover{filter:brightness(1.15)}.b-yl{background:var(--yl);color:#231800}.b-bl{background:var(--bl)}
input{width:100%;background:#0e1116;border:1px solid var(--line);border-radius:6px;color:var(--tx);padding:7px 9px;font:13px inherit}
.secret{-webkit-text-security:disc}
label{display:block;color:var(--mut);font-size:12px;margin:8px 0 3px}
.ok{color:var(--gr)}.bad{color:var(--rd)}.mut{color:var(--mut)}
#logs{font:12px/1.55 Consolas,monospace;max-height:320px;overflow:auto;white-space:pre-wrap;color:#c3cad5}
#toast{position:fixed;right:18px;bottom:18px;background:#222a35;border:1px solid var(--line);padding:10px 14px;border-radius:8px;display:none;max-width:420px;white-space:pre-wrap}
</style></head><body><div class="wrap">
<header><h1>TopWinLose BNB <small>v__VERSION__</small></h1>
<button class="b-yl" onclick="update()">⬆ Update New Ver</button></header>
<div class="card"><h2>Trạng thái</h2>
 <div>Bot Telegram: <span id="bot"></span></div>
 <div>Dữ liệu Binance: <span id="data"></span></div>
 <div class="mut" style="font-size:12px;margin-top:6px">Giữ cửa sổ đen mở trong lúc dùng. Lệnh bot: /start · /top · /win · /lose · /setting · /update · /help</div></div>
<div class="card"><h2>Bot Telegram</h2>
 <label>Bot Token (tạo bot MỚI ở @BotFather — không dùng chung bot với BabyBB)</label>
 <input id="bot_token" class="secret" autocomplete="off" data-lpignore="true" data-1p-ignore>
 <label>Chat ID chủ bot (chỉ người này dùng được mọi lệnh; người khác chỉ /start)</label><input id="bot_owner_id">
 <div style="margin-top:12px"><button class="b-bl" onclick="save()">💾 Lưu cài đặt</button></div></div>
<div class="card"><h2>Log</h2><div id="logs"></div></div>
</div><div id="toast"></div>
<script>
const $=id=>document.getElementById(id);let first=true;
function toast(t){const e=$('toast');e.textContent=t;e.style.display='block';clearTimeout(toast.t);toast.t=setTimeout(()=>e.style.display='none',6000)}
async function post(u,b){try{const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});const j=await r.json();if(j.msg)toast(j.msg);return j}catch(e){toast('Lỗi: '+e)}}
async function save(){const j=await post('/api/config',{bot_token:$('bot_token').value,bot_owner_id:$('bot_owner_id').value});if(j&&j.ok){$('bot_token').value='';first=true;refresh()}}
async function update(){const j=await post('/api/update');if(j&&j.restart)setTimeout(()=>location.reload(),6000)}
async function refresh(){try{const s=await(await fetch('/api/state')).json();
 if(first){$('bot_owner_id').value=s.owner;$('bot_token').placeholder=s.has_token?'•••• đã lưu':'';first=false}
 $('bot').innerHTML=s.same_as_babybb?'<span class="bad">⚠ token trùng bot BabyBB — tạo bot mới</span>':!s.has_token?'<span class="bad">chưa nhập Bot Token</span>':s.bot?'<span class="ok">✅ '+s.bot+'</span>'+(s.owner?'':' <span class="bad">· chưa có Chat ID chủ bot (nhắn /start cho bot để lấy)</span>'):'<span class="bad">⚠ '+(s.bot_err||'đang kết nối…')+'</span>';
 $('data').innerHTML=(s.data?'<span class="ok">✅ '+s.data+'</span>':'')+(s.data_err?' <span class="bad">⚠ '+s.data_err+'</span>':'');
 $('logs').textContent=s.logs.join('\n')}catch(e){$('bot').innerHTML='<span class="bad">MẤT KẾT NỐI TOOL</span>'}}
refresh();setInterval(refresh,2000);
</script></body></html>
"""

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass
    if "--selftest" in sys.argv:
        selftest()
        sys.exit(0)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        import traceback
        traceback.print_exc()
        me = os.path.abspath(__file__)
        if os.path.exists(PENDING) and os.path.exists(me + ".bak"):     # ban moi loi khi khoi dong -> quay ve ban cu
            try:
                with open(me + ".bak", "r", encoding="utf-8") as f:
                    old = f.read()
                with open(me, "w", encoding="utf-8", newline="\n") as f:
                    f.write(old)
                os.remove(PENDING)
                load_cfg()
                cfg["update_note"] = f"⚠️ Bản {VERSION} lỗi khi khởi động ({type(e).__name__}: {str(e)[:80]}) — đã tự quay về bản cũ"
                save_cfg()
                print("Da quay ve ban cu, dang chay lai...")
                restart()
            except Exception:
                traceback.print_exc()
        raise
