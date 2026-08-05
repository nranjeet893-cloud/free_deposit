"""
Force-Join Bot — Set 1 → Force Join | Set 2 → After Join (Deposit)
"""

import os, asyncio, sqlite3, threading, logging, json
from datetime import date
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)
from telegram.constants import ParseMode

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ✅ FIXED: Hamesha project directory — Render pe persistent & writable, no /data needed
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH      = os.path.join(_PROJECT_DIR, "bot_data.db")

# ═══════════════════════════════════════════════════════════════════
#  KEEP-ALIVE SERVER + SELF-PING  (Render free tier spin-down fix)
# ═══════════════════════════════════════════════════════════════════

class _Ping(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, *a): pass

def start_keep_alive(port=10000):
    server = HTTPServer(("0.0.0.0", port), _Ping)
    t = threading.Thread(target=server.serve_forever)
    t.daemon = True
    t.start()
    logger.info(f"✅ Keep-alive server: port {port}")

async def _self_ping_loop(port: int):
    """Har 4 min mein apne aap ko ping karo — Render spin-down rokne ke liye."""
    import urllib.request
    await asyncio.sleep(60)           # startup ke baad 1 min wait
    while True:
        try:
            urllib.request.urlopen(f"http://localhost:{port}/", timeout=5)
            logger.info("🏓 Self-ping OK — server alive")
        except Exception as e:
            logger.warning(f"⚠️ Self-ping failed: {e}")
        await asyncio.sleep(240)      # 4 minute interval

# ═══════════════════════════════════════════════════════════════════
#  DATABASE SETUP
# ═══════════════════════════════════════════════════════════════════

def _conn():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    return sqlite3.connect(DB_PATH)

def init_db():
    with _conn() as c:
        # Users table
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id      INTEGER PRIMARY KEY,
            username     TEXT    DEFAULT '',
            first_name   TEXT    DEFAULT '',
            joined_date  TEXT    DEFAULT '',
            is_blocked   INTEGER DEFAULT 0,
            last_bot_msg INTEGER DEFAULT 0,
            join_count   INTEGER DEFAULT 0
        )""")
        # Config table
        c.execute("""CREATE TABLE IF NOT EXISTS config (
            key   TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        )""")
        defaults = {
            # ── User facing texts ──
            "welcome_text": (
                "🔐 <b>Welcome to Free Recharge Bot</b> 💸\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🎁 <b>Tumhara ₹500 Reward Ready Hai!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "⚡ <b>Reward Unlock Karne Ke Liye:</b>\n"
                "  ✅ Niche diye <b>saare channels</b> join karo\n"
                "  🔓 Phir <b>Verify &amp; Claim</b> button dabao"
            ),
            "joined_text": (
                "🎊 <b>Congratulations! Reward Unlock Ho Gaya!</b>\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "💰 <b>Abhi Deposit Karo — Pao Extra Bonus!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "👇 <b>Button dabao aur apna bonus claim karo:</b>"
            ),
            "deposit_text": (
                "🎁 <b>Aapka Special Bonus Ready Hai!</b>\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "💰 Pehli deposit pe <b>EXTRA BONUS</b> milega!\n"
                "🎯 Niche button dabao aur deposit karo!\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            # ── Alert messages (popup) ──
            "alert_not_joined": "❌ Pehle saare channels join karo! Phir Verify karo.",
            "alert_blocked":    "🚫 Aap block hain. Admin se contact karo.",
            # ── Links ──
            "deposit_link":  "",
            "voice_file_id": "",
            # ── Second message (Register info) ──
            "register_link":         "",
            "register_instructions": "📌 <b>REGISTER LINK</b> 📌\n\n{register_link}\n\n<b>Send Screenshot Agent UID And Bank add Screenshot Send</b>",
            "dm_agent_text":         "💝 <b>DM Agent</b> 👉 @YourAgentUsername",
            # ── Channel sets ──
            "channels":       "[]",
            "channels_after": "[]",
            # ── Admin IDs ──
            "admin_ids": "",
            # ── Button labels ──
            "btn_verify_label":      "🔓 Verify & Unlock Reward 🔐",
            "btn_deposit_label":     "💰 Deposit Karo & Bonus Pao 🚀",
            "deposit_popup_btn_label": "🚀 Abhi Deposit Karo & Bonus Pao 💰",
            # ── Custom emojis (admin se change ho sakta hai) ──
            "join_emoji":    "",
            "deposit_emoji": "💰",
            "voice_emoji":   "🔊",
            "verify_emoji":  "✅",
            "alert_emoji":   "⚡",
            # ── Voice caption ──
            "voice_caption": "🔊 Sound On Karo — Yeh zaroor suno! 👆",
            # ── Message Photos (file_id) ──
            "welcome_photo":  "",
            "joined_photo":   "",
            "deposit_photo":  "",
            # ── Buttons per row: "1" or "2" ──
            "btns_per_row": "2",
        }
        for k, v in defaults.items():
            c.execute("INSERT OR IGNORE INTO config (key,value) VALUES (?,?)", (k, v))

        # ── MIGRATION: purane welcome_text se {name} hata do ──
        # Agar DB mein purana text hai jisme {name} hai, update karo
        old_welcome = c.execute(
            "SELECT value FROM config WHERE key='welcome_text'").fetchone()
        if old_welcome and "{name}" in old_welcome[0]:
            new_w = (old_welcome[0]
                     .replace("Hey {name}! ", "")
                     .replace("Hey {name}!", "")
                     .replace("{name}! ", "")
                     .replace("{name}!", "")
                     .replace("{name}", "")
                     .strip())
            c.execute("UPDATE config SET value=? WHERE key='welcome_text'", (new_w,))

        # ── MIGRATION: button labels premium style ──
        c.execute("UPDATE config SET value=? WHERE key='btn_verify_label'",
                  ("🔓 Verify & Unlock Reward 🔐",))
        c.execute("UPDATE config SET value=? WHERE key='btn_deposit_label'",
                  ("💰 Deposit Karo & Bonus Pao 🚀",))

        # ── MIGRATION: join_emoji clear karo (🔗 link emoji hata do) ──
        c.execute("UPDATE config SET value='' WHERE key='join_emoji' AND value='🔗'")

        # ── MIGRATION: joined_text — purana sound-repeat wala update karo ──
        cur_joined = c.execute("SELECT value FROM config WHERE key='joined_text'").fetchone()
        if cur_joined:
            _jv = cur_joined[0]
            if "Sound On Karo — Important Message Sun Lo" in _jv or "Deposit Milega — Play on Sound" in _jv:
                c.execute("UPDATE config SET value=? WHERE key='joined_text'", (
                    "🎊 <b>Congratulations! Reward Unlock Ho Gaya!</b>\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "💰 <b>Abhi Deposit Karo — Pao Extra Bonus!</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "👇 <b>Button dabao aur apna bonus claim karo:</b>",
                ))

        # ── MIGRATION: deposit_text — purana default → naya premium look ──
        cur_dep = c.execute("SELECT value FROM config WHERE key='deposit_text'").fetchone()
        if cur_dep and "Deposit Karo — Reward Unlock Karo!" in cur_dep[0]:
            c.execute("UPDATE config SET value=? WHERE key='deposit_text'", (
                "🎁 <b>Aapka Special Bonus Ready Hai!</b>\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "💰 Pehli deposit pe <b>EXTRA BONUS</b> milega!\n"
                "🎯 Niche button dabao aur deposit karo!\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━",
            ))

        c.commit()

# ── User helpers ──────────────────────────────────────────────────
def db_add_user(uid, uname, fname):
    with _conn() as c:
        c.execute("""
            INSERT INTO users (user_id,username,first_name,joined_date,join_count)
            VALUES (?,?,?,?,1)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                join_count=join_count+1
        """, (uid, uname, fname, str(date.today())))
        c.commit()

def db_all_users():
    with _conn() as c:
        return [r[0] for r in c.execute(
            "SELECT user_id FROM users WHERE is_blocked=0").fetchall()]

def db_is_blocked(uid):
    with _conn() as c:
        r = c.execute("SELECT is_blocked FROM users WHERE user_id=?", (uid,)).fetchone()
    return bool(r and r[0])

def db_block(uid):
    with _conn() as c:
        c.execute("UPDATE users SET is_blocked=1 WHERE user_id=?", (uid,)); c.commit()

def db_unblock(uid):
    with _conn() as c:
        c.execute("UPDATE users SET is_blocked=0 WHERE user_id=?", (uid,)); c.commit()

def db_set_msg(uid, mid):
    with _conn() as c:
        c.execute("UPDATE users SET last_bot_msg=? WHERE user_id=?", (mid, uid)); c.commit()

def db_get_msg(uid):
    with _conn() as c:
        r = c.execute("SELECT last_bot_msg FROM users WHERE user_id=?", (uid,)).fetchone()
    return r[0] if r and r[0] else None

def db_stats():
    with _conn() as c:
        total   = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        active  = c.execute("SELECT COUNT(*) FROM users WHERE is_blocked=0").fetchone()[0]
        blocked = c.execute("SELECT COUNT(*) FROM users WHERE is_blocked=1").fetchone()[0]
        today   = c.execute("SELECT COUNT(*) FROM users WHERE joined_date=?",
                            (str(date.today()),)).fetchone()[0]
    return {"total": total, "active": active, "blocked": blocked, "today": today}

def db_search_user(uid):
    with _conn() as c:
        r = c.execute(
            "SELECT user_id,username,first_name,joined_date,is_blocked,join_count FROM users WHERE user_id=?",
            (uid,)).fetchone()
    return r

# ═══════════════════════════════════════════════════════════════════
#  CONFIG HELPERS
# ═══════════════════════════════════════════════════════════════════

def cfg_get():
    with _conn() as c:
        return dict(c.execute("SELECT key,value FROM config").fetchall())

def cfg_set(key, value):
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO config (key,value) VALUES (?,?)", (key, value))
        c.commit()

def apply_emojis(text: str, cfg: dict) -> str:
    """
    Text mein {join_emoji}, {deposit_emoji} etc. replace karo.
    Welcome text, joined text, button labels — sab jagah kaam karta hai.
    """
    replacements = {
        "{join_emoji}":    cfg.get("join_emoji",    "🔗"),
        "{deposit_emoji}": cfg.get("deposit_emoji", "💰"),
        "{voice_emoji}":   cfg.get("voice_emoji",   "🔊"),
        "{verify_emoji}":  cfg.get("verify_emoji",  "✅"),
        "{alert_emoji}":   cfg.get("alert_emoji",   "⚡"),
    }
    for placeholder, emoji in replacements.items():
        text = text.replace(placeholder, emoji)
    return text

def fix_html_entities(text: str) -> str:
    """
    ✅ FIX: Entity_text_invalid error solve karo.
    Bare '&' ko '&amp;' se replace karo — already escaped wale touch nahi hote.
    """
    import re
    return re.sub(r'&(?!amp;|lt;|gt;|quot;|#\d+;|#x[\da-fA-F]+;)', '&amp;', text)

async def safe_html_reply(message, text: str, reply_markup=None) -> object:
    """
    ✅ FIX: HTML mode mein bhejo — fail ho to HTML tags hata ke plain text bhejo.
    Kabhi silent fail nahi hoga.
    """
    import re
    try:
        fixed = fix_html_entities(text)
        return await message.reply_text(fixed, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except Exception as e:
        if "Entity" in str(e) or "entity" in str(e) or "invalid" in str(e).lower():
            # HTML invalid — tags hata ke plain text mein bhejo
            plain = re.sub(r'<[^>]+>', '', text)
            plain = plain.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
            return await message.reply_text(plain, reply_markup=reply_markup)
        raise

async def safe_html_send(bot, chat_id: int, text: str, reply_markup=None) -> object:
    """
    ✅ FIX: bot.send_message HTML version — Entity error pe plain text fallback.
    """
    import re
    try:
        fixed = fix_html_entities(text)
        return await bot.send_message(chat_id, fixed, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except Exception as e:
        if "Entity" in str(e) or "entity" in str(e) or "invalid" in str(e).lower():
            plain = re.sub(r'<[^>]+>', '', text)
            plain = plain.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
            return await bot.send_message(chat_id, plain, reply_markup=reply_markup)
        raise

async def safe_reply_with_photo(message, text: str, photo_id: str = "", reply_markup=None) -> object:
    """
    ✅ Photo set hai to photo+caption reply karo, warna plain text reply.
    Telegram caption limit 1024 chars hai — overflow hone par text fallback.
    """
    if photo_id:
        try:
            fixed = fix_html_entities(text)
            return await message.reply_photo(
                photo=photo_id,
                caption=fixed[:1024],
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning(f"Photo reply failed ({e}), falling back to text")
    return await safe_html_reply(message, text, reply_markup=reply_markup)

async def safe_send_with_photo(bot, chat_id: int, text: str, photo_id: str = "", reply_markup=None) -> object:
    """
    ✅ Photo set hai to bot.send_photo+caption, warna bot.send_message.
    """
    if photo_id:
        try:
            fixed = fix_html_entities(text)
            return await bot.send_photo(
                chat_id=chat_id,
                photo=photo_id,
                caption=fixed[:1024],
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning(f"Photo send failed ({e}), falling back to text")
    return await safe_html_send(bot, chat_id, text, reply_markup=reply_markup)

def preserve_custom_emojis(text: str, entities) -> str:
    """
    ✅ FIX: Welcome/Joined text mein custom emoji directly paste karne pe
    kaam karta hai — ID ki zaroorat nahi.
    Message ke text + entities ko HTML mein convert karo.
    Custom emoji entities → <tg-emoji emoji-id="..."> tags.
    """
    if not text or not entities:
        return text or ""
    # ✅ ROOT FIX: Telegram entity offsets are in UTF-16 code units, NOT Python
    # string indices.  Most common emojis (🔐🎉💰 etc.) are outside the BMP —
    # each takes 2 UTF-16 units but only 1 Python index.  Using raw ent.offset
    # as a Python index therefore mis-slices the string whenever such an emoji
    # appears before the premium emoji, so the custom_emoji entity is never
    # found / extracted correctly.
    # Fix: encode to UTF-16-LE first, slice by byte position (offset * 2),
    # then decode each piece back to str.
    text_utf16 = text.encode("utf-16-le")
    sorted_ents = sorted(entities, key=lambda e: e.offset)
    result_parts: list[str] = []
    last_utf16 = 0
    for ent in sorted_ents:
        if ent.type == "custom_emoji" and getattr(ent, "custom_emoji_id", None):
            before   = text_utf16[last_utf16 * 2 : ent.offset * 2].decode("utf-16-le")
            fallback = text_utf16[ent.offset * 2 : (ent.offset + ent.length) * 2].decode("utf-16-le")
            result_parts.append(before)
            result_parts.append(
                f'<tg-emoji emoji-id="{ent.custom_emoji_id}">{fallback}</tg-emoji>'
            )
            last_utf16 = ent.offset + ent.length
    result_parts.append(text_utf16[last_utf16 * 2 :].decode("utf-16-le"))
    return "".join(result_parts)

def normalize_link(link: str) -> str:
    """
    ✅ FIX: Channel links ko proper https:// format mein convert karo.
    t.me/channel → https://t.me/channel
    @channel     → https://t.me/channel
    """
    link = link.strip()
    if not link:
        return ""
    if link.startswith("@"):
        return "https://t.me/" + link[1:]
    if link.startswith(("t.me/", "telegram.me/")):
        return "https://" + link
    return link   # already https:// ya unknown

def strip_tg_emoji(text: str) -> str:
    """
    ✅ FIX: Button labels ke liye — Telegram buttons mein premium emoji nahi chalte.
    <tg-emoji emoji-id="...">⭐</tg-emoji> → ⭐ (sirf fallback character)
    """
    import re
    return re.sub(r'<tg-emoji emoji-id="[^"]+">([^<]*)</tg-emoji>', r'\1', text)

def get_channels(key="channels"):
    try:
        return json.loads(cfg_get().get(key, "[]"))
    except Exception:
        return []

def set_channels(ch_list, key="channels"):
    cfg_set(key, json.dumps(ch_list, ensure_ascii=False))

def admin_ids():
    ids = set()
    for src in [os.getenv("ADMIN_IDS", ""), cfg_get().get("admin_ids", "")]:
        for x in src.split(","):
            x = x.strip()
            if x:
                try: ids.add(int(x))
                except: pass
    return list(ids)

def add_admin(uid):
    cfg = cfg_get()
    existing = [x.strip() for x in cfg.get("admin_ids", "").split(",") if x.strip()]
    if str(uid) not in existing:
        existing.append(str(uid))
    cfg_set("admin_ids", ",".join(existing))

def remove_admin(uid):
    cfg = cfg_get()
    existing = [x.strip() for x in cfg.get("admin_ids", "").split(",")
                if x.strip() and x.strip() != str(uid)]
    cfg_set("admin_ids", ",".join(existing))

# ═══════════════════════════════════════════════════════════════════
#  FORCE-JOIN CHECK
# ═══════════════════════════════════════════════════════════════════

async def check_not_joined(bot, uid):
    not_joined = []
    for ch in get_channels("channels"):
        try:
            m = await bot.get_chat_member(ch["id"], uid)
            if m.status not in (ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER):
                not_joined.append(ch)
        except Exception:
            not_joined.append(ch)
    return not_joined

# ═══════════════════════════════════════════════════════════════════
#  KEYBOARD BUILDERS
# ═══════════════════════════════════════════════════════════════════

def _join_btn_label(ch, cfg, idx=0):
    """Channel button label — kabhi empty nahi hoga."""
    label = ch.get("name", "").strip()
    if not label:
        label = f"Channel {idx + 1}"
    return label

def _build_channel_buttons(channels, cfg, ch_set="set1"):
    """
    ✅ FIX:
    1. normalize_link → t.me/ links https:// ban jaate hain → URL buttons kaam karte hain
    2. URL button → channel seedha khulta hai, koi nayi message nahi (no stacking/emoji spam)
    3. Premium emoji strip → plain emoji
    4. No 'Join Karo' suffix
    """
    per_row   = int(cfg.get("btns_per_row", "2"))
    raw_emoji = apply_emojis("{join_emoji}", cfg)
    emoji     = strip_tg_emoji(raw_emoji)
    rows, pair = [], []
    for i, ch in enumerate(channels):
        label    = _join_btn_label(ch, cfg, idx=i)
        link     = normalize_link(ch.get("link", ""))
        btn_text = f"{emoji} {label}".strip() if emoji else label
        if link.startswith(("https://", "http://")):
            pair.append(InlineKeyboardButton(btn_text, url=link))
        else:
            pair.append(InlineKeyboardButton(btn_text, callback_data=f"ch_join_{ch_set}_{i}"))
        if len(pair) == per_row:
            rows.append(pair); pair = []
    if pair:
        rows.append(pair)
    return rows

def kb_force_join(not_joined, cfg):
    rows = _build_channel_buttons(not_joined, cfg, ch_set="set1")
    raw_label    = apply_emojis(cfg.get("btn_verify_label", "✅ Verify & Claim Reward 🎁"), cfg)
    verify_label = strip_tg_emoji(raw_label)   # ✅ premium emoji → plain
    rows.append([InlineKeyboardButton(verify_label, callback_data="verify_join")])
    return InlineKeyboardMarkup(rows)

def kb_after_join(cfg):
    """Deposit screen — sirf EK deposit button, koi extra channel buttons nahi."""
    raw_label     = apply_emojis(cfg.get("btn_deposit_label", "💰 Deposit Karo & Bonus Pao 🚀"), cfg)
    deposit_label = strip_tg_emoji(raw_label)
    return InlineKeyboardMarkup([[InlineKeyboardButton(deposit_label, callback_data="deposit_clicked")]])

def kb_after_join_with_ch2(cfg, ch2_list):
    """
    ✅ NEW: Joined screen mein Set-2 channels (join buttons) + deposit button dono dikhao.
    Voice ke saath yeh keyboard aata hai — channels aur deposit ek hi message mein.
    """
    rows = []
    # Set-2 channels (channels_after) ke join buttons
    if ch2_list:
        rows = _build_channel_buttons(ch2_list, cfg, ch_set="set2")
    # Deposit button neeche
    raw_label     = apply_emojis(cfg.get("btn_deposit_label", "💰 Deposit Karo & Bonus Pao 🚀"), cfg)
    deposit_label = strip_tg_emoji(raw_label)
    rows.append([InlineKeyboardButton(deposit_label, callback_data="deposit_clicked")])
    return InlineKeyboardMarkup(rows)

def kb_admin():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("━━━━━ 📊 OVERVIEW ━━━━━", callback_data="noop")],
        [InlineKeyboardButton("📊 Live Stats",            callback_data="admin_stats"),
         InlineKeyboardButton("👥 User Manager",          callback_data="admin_user_manager")],
        [InlineKeyboardButton("━━━━━ 📢 CHANNELS ━━━━━", callback_data="noop")],
        [InlineKeyboardButton("📢 Set-1 Force Join",      callback_data="admin_ch1_list"),
         InlineKeyboardButton("📣 Set-2 Deposit",         callback_data="admin_ch2_list")],
        [InlineKeyboardButton("━━━━ 💰 MONETIZE ━━━━━", callback_data="noop")],
        [InlineKeyboardButton("💰 Deposit Settings",      callback_data="admin_deposit_menu"),
         InlineKeyboardButton("🎙 Voice Message",         callback_data="admin_voice_menu")],
        [InlineKeyboardButton("━━━━ CUSTOMIZE ━━━━", callback_data="noop")],
        [InlineKeyboardButton("📝 Welcome Text",           callback_data="admin_welcome_menu"),
         InlineKeyboardButton("📝 Joined Text",            callback_data="admin_joined_text")],
        [InlineKeyboardButton("🔘 Button Labels",          callback_data="admin_btn_labels"),
         InlineKeyboardButton("💬 Alert Messages",         callback_data="admin_alerts")],
        [InlineKeyboardButton("😊 Custom Emojis",          callback_data="admin_emoji_menu"),
         InlineKeyboardButton("🎙 Voice Caption",          callback_data="admin_voice_caption")],
        [InlineKeyboardButton("🖼 Message Photos",         callback_data="admin_photo_menu"),
         InlineKeyboardButton("🔢 Buttons Per Row",        callback_data="admin_btn_row")],
        [InlineKeyboardButton("━━━━ 📨 BROADCAST ━━━━", callback_data="noop")],
        [InlineKeyboardButton("📨 Broadcast Message",      callback_data="admin_broadcast_menu"),
         InlineKeyboardButton("👑 Admin Manage",           callback_data="admin_manage_admins")],
        [InlineKeyboardButton("━━━━ 💾 DATABASE ━━━━━", callback_data="noop")],
        [InlineKeyboardButton("💾 Backup Download",        callback_data="admin_db_backup"),
         InlineKeyboardButton("📤 Restore Upload",         callback_data="admin_db_restore")],
    ])

def kb_back(target="admin_panel"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=target)]])

# ═══════════════════════════════════════════════════════════════════
#  CHANNEL LIST (Admin display)
# ═══════════════════════════════════════════════════════════════════

async def show_ch_list(q, set_key, set_label, add_cb, del_prefix, back_cb="admin_panel"):
    channels = get_channels(set_key)
    if not channels:
        await q.edit_message_text(
            f"📢 <b>{set_label}</b>\n\nKoi channel nahi hai abhi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Add Channel", callback_data=add_cb)],
                [InlineKeyboardButton("🔙 Back", callback_data=back_cb)],
            ]), parse_mode=ParseMode.HTML)
        return
    text = f"📢 <b>{set_label}</b>\n\n"
    rows = []
    for i, ch in enumerate(channels):
        text += f"{i+1}. <b>{ch.get('name','?')}</b> | <code>{ch.get('id','?')}</code>\n"
        rows.append([InlineKeyboardButton(
            f"🗑️ {ch.get('name','?')}", callback_data=f"{del_prefix}{i}")])
    rows.append([InlineKeyboardButton("➕ Add Channel", callback_data=add_cb)])
    rows.append([InlineKeyboardButton("🔙 Back", callback_data=back_cb)])
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows),
                              parse_mode=ParseMode.HTML)

# ═══════════════════════════════════════════════════════════════════
#  PREMIUM UNLOCK FLOW
# ═══════════════════════════════════════════════════════════════════

async def send_joined_content(bot, chat_id, user_id, cfg, user_name=""):
    voice_id      = cfg.get("voice_file_id", "")
    voice_caption = cfg.get("voice_caption", "🔊 Sound On Karo — Yeh zaroor suno! 👆")
    voice_caption = apply_emojis(voice_caption, cfg)

    # Keyboard: Set-2 channels (agar hain) + deposit button
    ch2_list = get_channels("channels_after")
    kb = kb_after_join_with_ch2(cfg, ch2_list) if ch2_list else kb_after_join(cfg)

    # Step 1: Unlock animation
    anim = await bot.send_message(
        chat_id=chat_id,
        text="🔓 <b>Reward Unlock Ho Raha Hai...</b>\n\n⏳ Please wait...",
        parse_mode=ParseMode.HTML,
    )
    await asyncio.sleep(1.2)
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=anim.message_id,
            text="🎉 <b>Congratulations! Reward Unlock Ho Gaya!</b>\n✅ Channels join ho gaye!",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass
    await asyncio.sleep(0.8)

    # Step 2: Voice + keyboard seedha voice pe — koi alag message nahi
    if voice_id:
        try:
            sent = await bot.send_voice(
                chat_id=chat_id,
                voice=voice_id,
                caption=voice_caption,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
            db_set_msg(user_id, sent.message_id)
        except Exception as e:
            logger.warning(f"Voice send failed: {e}")
            sent = await safe_html_send(
                bot, chat_id, voice_caption, reply_markup=kb)
            db_set_msg(user_id, sent.message_id)
    else:
        sent = await safe_html_send(
            bot, chat_id,
            "👇 <b>Button dabao aur apna bonus claim karo:</b>",
            reply_markup=kb,
        )
        db_set_msg(user_id, sent.message_id)

    # ℹ️ Register/instruction text → deposit button click pe aayega

# ═══════════════════════════════════════════════════════════════════
#  /start COMMAND
# ═══════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        db_add_user(user.id, user.username or "", user.first_name or "")

        prev = db_get_msg(user.id)
        if prev:
            try: await context.bot.delete_message(update.effective_chat.id, prev)
            except: pass

        if db_is_blocked(user.id):
            await update.message.reply_text("🚫 Aap block hain. Admin se contact karo.")
            return

        cfg      = cfg_get()
        ch1_list = get_channels("channels")

        if not ch1_list:
            sent = await update.message.reply_text(
                "⚠️ <b>Bot Setup Pending</b>\n\nAdmin ne abhi channels set nahi kiye.",
                parse_mode=ParseMode.HTML)
            db_set_msg(user.id, sent.message_id)
            return

        not_joined = await check_not_joined(context.bot, user.id)

        # ✅ FIX: /start pe HAMESHA saare channels dikhao
        # not_joined/joined kuch bhi ho — sab channels hamesha visible rahenge
        # Deposit screen SIRF "Verify" button click karne pe aayega
        raw_text  = cfg.get("welcome_text", "🔐 <b>Welcome!</b> Channels join karo.")
        safe_name = (user.first_name or user.username or "").strip()
        text = raw_text.replace("{name}", safe_name).replace("Hey , ", "Hey 👋 ").replace("Hey ,", "Hey 👋").strip()
        text = apply_emojis(text, cfg)

        # ✅ Hamesha ch1_list use karo — koi channel hide nahi hoga
        kb = kb_force_join(ch1_list, cfg)
        welcome_photo = cfg.get("welcome_photo", "")
        sent = await safe_reply_with_photo(update.message, text, photo_id=welcome_photo, reply_markup=kb)
        db_set_msg(user.id, sent.message_id)

    except Exception as e:
        logger.error(f"❌ cmd_start ERROR — user {user.id}: {e}", exc_info=True)
        try:
            await update.message.reply_text(
                f"⚠️ Bot mein kuch error hua.\n"
                f"Admin se contact karo ya thodi der baad /start dobara bhejo.\n\n"
                f"<code>{type(e).__name__}: {e}</code>",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

# ═══════════════════════════════════════════════════════════════════
#  /admin COMMAND
# ═══════════════════════════════════════════════════════════════════

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    # ✅ AUTO ADMIN: Agar koi admin nahi hai, pehla user admin ban jaye
    if not admin_ids():
        add_admin(uid)
        await update.message.reply_text(
            f"👑 <b>Aap pehle Admin ban gaye!</b>\n\n"
            f"🆔 Aapka ID: <code>{uid}</code>\n\n"
            f"✅ Ab niche Admin Panel use karo.",
            parse_mode=ParseMode.HTML
        )

    if uid not in admin_ids(): return
    s   = db_stats()
    ch1 = get_channels("channels")
    ch2 = get_channels("channels_after")
    cfg = cfg_get()
    voice = "✅ Set" if cfg.get("voice_file_id") else "❌ Nahi"
    dlink = "✅ Set" if cfg.get("deposit_link")  else "❌ Nahi"
    rlink = "✅ Set" if cfg.get("register_link") else "❌ Nahi"
    await update.message.reply_text(
        f"╔══════════════════════════╗\n"
        f"║  👑 <b>PRO ADMIN PANEL</b>  ║\n"
        f"╚══════════════════════════╝\n\n"
        f"━━━━━━ 📊 QUICK STATS ━━━━━━\n"
        f"👥 Total  : <b>{s['total']}</b>   🟢 Active : <b>{s['active']}</b>\n"
        f"📅 Aaj    : <b>{s['today']}</b>   🚫 Blocked: <b>{s['blocked']}</b>\n\n"
        f"━━━━━━ ⚙️ BOT STATUS ━━━━━━━\n"
        f"📢 Set-1 Ch   : <b>{len(ch1)}</b> channels\n"
        f"📣 Set-2 Ch   : <b>{len(ch2)}</b> channels\n"
        f"🎙 Voice      : {voice}\n"
        f"💰 Dep Link   : {dlink}\n"
        f"📌 Reg Link   : {rlink}",
        reply_markup=kb_admin(), parse_mode=ParseMode.HTML)

# ═══════════════════════════════════════════════════════════════════
#  CALLBACK HANDLER
# ═══════════════════════════════════════════════════════════════════

async def cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    user = q.from_user
    data = q.data
    cfg  = cfg_get()
    # ✅ FIX: q.answer() yahan se hataya — verify_join ka show_alert kaam nahi karta tha
    # Ab har branch apna q.answer() khud call karta hai

    if data == "noop":
        await q.answer()
        return

    # ════════════════════════════════════════════════
    #  VERIFY JOIN — PEHLE handle karo (blanket answer se pehle)
    # ════════════════════════════════════════════════
    if data == "verify_join":
        if db_is_blocked(user.id):
            await q.answer("🚫 Aap block hain.", show_alert=True)
            return

        # ✅ check_not_joined bhi try-except mein
        try:
            not_joined = await check_not_joined(context.bot, user.id)
        except Exception:
            await q.answer("⚠️ Error aaya! Thodi der baad try karo.", show_alert=True)
            return

        if not_joined:
            # ── Step 1: Popup ──
            await q.answer("❌ Pehle saare channels join karo!", show_alert=True)

            # ── Step 2: Screen pe HAMESHA saare channels dikhenge ──
            cfg2      = cfg_get()
            raw_text  = cfg2.get("welcome_text", "🔐 <b>Welcome!</b>\n\nChannels join karo.")
            base_text = raw_text.replace("{name}", "").replace("Hey , ", "").replace("Hey ,", "").strip()
            base_text = apply_emojis(base_text, cfg2)

            full_text = fix_html_entities(base_text)
            # ✅ FIX: ch1_list use karo — sab channels dikhenge, sirf not_joined nahi
            all_ch1   = get_channels("channels")
            fixed_kb  = kb_force_join(all_ch1, cfg2)

            # Try 1: edit existing message
            try:
                await q.edit_message_text(full_text, reply_markup=fixed_kb, parse_mode=ParseMode.HTML)
                return
            except Exception as e1:
                if "message is not modified" in str(e1).lower():
                    return

            # Try 2: delete + send new
            try:
                try: await q.message.delete()
                except: pass
                sent = await safe_html_send(context.bot, q.message.chat_id, full_text, reply_markup=fixed_kb)
                db_set_msg(user.id, sent.message_id)
                return
            except Exception:
                pass

            # Try 3: plain text fallback — kabhi fail nahi hoga
            import re
            plain = re.sub(r'<[^>]+>', '', full_text).replace('&amp;', '&')
            try:
                sent = await context.bot.send_message(q.message.chat_id, plain, reply_markup=fixed_kb)
                db_set_msg(user.id, sent.message_id)
            except Exception:
                pass
            return

        await q.answer()
        try: await q.message.delete()
        except: pass
        await send_joined_content(context.bot, q.message.chat_id, user.id, cfg,
                                  user.first_name or user.username or 'Dost')
        return

    # ════════════════════════════════════════════════
    #  DEPOSIT BUTTON CLICK → deposit msg + link button + register info + DM agent
    # ════════════════════════════════════════════════
    if data == "deposit_clicked":
        await q.answer()

        deposit_text = cfg.get("deposit_text", "").strip()
        if not deposit_text:
            deposit_text = (
                "🎁 <b>Aapka Special Bonus Ready Hai!</b>\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "💰 Pehli deposit pe <b>EXTRA BONUS</b> milega!\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
        deposit_text = apply_emojis(deposit_text, cfg)

        # ✅ NEW: Deposit link → URL button banana (agar admin ne set kiya hai)
        deposit_link = cfg.get("deposit_link", "").strip()
        if deposit_link and not deposit_link.startswith(("https://", "http://")):
            deposit_link = "https://" + deposit_link
        raw_popup_label = apply_emojis(
            cfg.get("deposit_popup_btn_label", "🚀 Abhi Deposit Karo & Bonus Pao 💰"), cfg)
        popup_label = strip_tg_emoji(raw_popup_label)
        dep_kb = (
            InlineKeyboardMarkup([[InlineKeyboardButton(popup_label, url=deposit_link)]])
            if deposit_link else None
        )

        # Step A: Deposit photo/text + link button
        deposit_photo = cfg.get("deposit_photo", "")
        if deposit_photo:
            try:
                await context.bot.send_photo(
                    chat_id=q.message.chat_id,
                    photo=deposit_photo,
                    caption=fix_html_entities(deposit_text)[:1024],
                    parse_mode=ParseMode.HTML,
                    reply_markup=dep_kb,
                )
            except Exception as e:
                logger.warning(f"Deposit photo send failed ({e}), using text")
                await safe_html_send(
                    context.bot, q.message.chat_id, deposit_text, reply_markup=dep_kb)
        else:
            await safe_html_send(
                context.bot, q.message.chat_id, deposit_text, reply_markup=dep_kb)

        # ✅ NEW: Step B: Register instructions (agar admin ne register_link set kiya hai)
        reg_link  = cfg.get("register_link",         "").strip()
        reg_instr = cfg.get("register_instructions", "").strip()
        if reg_link and reg_instr:
            reg_text = reg_instr.replace("{register_link}", reg_link)
            reg_text = apply_emojis(reg_text, cfg)
            await safe_html_send(context.bot, q.message.chat_id, reg_text)

        # ✅ NEW: Step C: DM Agent text (agar admin ne set kiya hai)
        dm_text = cfg.get("dm_agent_text", "").strip()
        if dm_text and dm_text != "💝 <b>DM Agent</b> 👉 @YourAgentUsername":
            dm_text = apply_emojis(dm_text, cfg)
            await safe_html_send(context.bot, q.message.chat_id, dm_text)

        return

    # Baaki sab callbacks ke liye blanket dismiss
    await q.answer()

    # ════════════════════════════════════════════════
    #  CHANNEL JOIN FALLBACK (jab URL button nahi bana)
    # ════════════════════════════════════════════════
    if data.startswith("ch_join_"):
        parts   = data.split("_")
        ch_set  = parts[2]
        idx     = int(parts[3])
        set_key = "channels" if ch_set == "set1" else "channels_after"
        chs     = get_channels(set_key)
        if idx < len(chs):
            ch    = chs[idx]
            link  = normalize_link(ch.get("link", ""))
            name  = ch.get("name", f"Channel {idx+1}")
            if link.startswith(("https://", "http://")):
                # ✅ FIX: Koi nayi message nahi — channel URL seedha khulega
                pass
            else:
                await q.answer("⚠️ Channel link set nahi! Admin se poocho.", show_alert=True)
        return

    # ════════════════════════════════════════════════
    #  ADMIN SECTION
    # ════════════════════════════════════════════════
    if not data.startswith("admin_"):
        return

    if user.id not in admin_ids():
        await q.answer("🚫 Sirf Admin ke liye!", show_alert=True)
        return

    # ── PANEL ─────────────────────────────────────────
    if data == "admin_panel":
        s   = db_stats()
        ch1 = get_channels("channels")
        ch2 = get_channels("channels_after")
        cfg2 = cfg_get()
        voice = "✅" if cfg2.get("voice_file_id") else "❌"
        dlink = "✅" if cfg2.get("deposit_link")  else "❌"
        rlink = "✅" if cfg2.get("register_link") else "❌"
        await q.edit_message_text(
            f"╔══════════════════════════╗\n"
            f"║  👑 <b>PRO ADMIN PANEL</b>  ║\n"
            f"╚══════════════════════════╝\n\n"
            f"━━━━━━ 📊 QUICK STATS ━━━━━━\n"
            f"👥 Total  : <b>{s['total']}</b>   🟢 Active : <b>{s['active']}</b>\n"
            f"📅 Aaj    : <b>{s['today']}</b>   🚫 Blocked: <b>{s['blocked']}</b>\n\n"
            f"━━━━━━ ⚙️ BOT STATUS ━━━━━━━\n"
            f"📢 Set-1 Ch   : <b>{len(ch1)}</b> channels\n"
            f"📣 Set-2 Ch   : <b>{len(ch2)}</b> channels\n"
            f"🎙 Voice      : {voice}\n"
            f"💰 Dep Link   : {dlink}\n"
            f"📌 Reg Link   : {rlink}",
            reply_markup=kb_admin(), parse_mode=ParseMode.HTML)

    # ── SET-1 CHANNELS ─────────────────────────────────
    elif data == "admin_ch1_list":
        await show_ch_list(q, "channels", "Set-1 Channels (Force Join)",
                           "admin_ch1_add", "admin_ch1_del_")

    elif data == "admin_ch1_add":
        context.user_data["awaiting"]   = "ch_forward"
        context.user_data["ch_set_key"] = "channels"
        await q.edit_message_text(
            "➕ <b>Set-1 Channel Add</b>\n\n"
            "Do tarike se channel add karo:\n\n"
            "1️⃣ <b>Forward karo:</b>\n"
            "   Channel kholo → post pe tap → Forward → Yahan bhejo\n\n"
            "2️⃣ <b>@Username type karo:</b>\n"
            "   Sirf <code>@channelname</code> ya\n"
            "   <code>https://t.me/channelname</code> type karo\n\n"
            "⚠️ Private channel ke liye <b>forward</b> use karo",
            reply_markup=kb_back("admin_ch1_list"), parse_mode=ParseMode.HTML)

    elif data.startswith("admin_ch1_del_"):
        idx = int(data.replace("admin_ch1_del_", ""))
        chs = get_channels("channels")
        if 0 <= idx < len(chs):
            removed = chs.pop(idx)
            set_channels(chs, "channels")
            await q.answer(f"🗑️ '{removed.get('name','')}' delete!", show_alert=True)
        await show_ch_list(q, "channels", "Set-1 Channels (Force Join)",
                           "admin_ch1_add", "admin_ch1_del_")

    # ── SET-2 CHANNELS ─────────────────────────────────
    elif data == "admin_ch2_list":
        await show_ch_list(q, "channels_after", "Set-2 Channels (Deposit Screen)",
                           "admin_ch2_add", "admin_ch2_del_")

    elif data == "admin_ch2_add":
        context.user_data["awaiting"]   = "ch_forward"
        context.user_data["ch_set_key"] = "channels_after"
        await q.edit_message_text(
            "➕ <b>Set-2 Channel Add</b>\n\n"
            "Do tarike se channel add karo:\n\n"
            "1️⃣ <b>Forward karo:</b>\n"
            "   Channel kholo → post pe tap → Forward → Yahan bhejo\n\n"
            "2️⃣ <b>@Username type karo:</b>\n"
            "   Sirf <code>@channelname</code> ya\n"
            "   <code>https://t.me/channelname</code> type karo\n\n"
            "⚠️ Private channel ke liye <b>forward</b> use karo",
            reply_markup=kb_back("admin_ch2_list"), parse_mode=ParseMode.HTML)

    elif data.startswith("admin_ch2_del_"):
        idx = int(data.replace("admin_ch2_del_", ""))
        chs = get_channels("channels_after")
        if 0 <= idx < len(chs):
            removed = chs.pop(idx)
            set_channels(chs, "channels_after")
            await q.answer(f"🗑️ '{removed.get('name','')}' delete!", show_alert=True)
        await show_ch_list(q, "channels_after", "Set-2 Channels (Deposit Screen)",
                           "admin_ch2_add", "admin_ch2_del_")

    # ── VOICE ──────────────────────────────────────────
    elif data == "admin_voice_menu":
        status = "✅ Set hai" if cfg.get("voice_file_id") else "❌ Set nahi"
        await q.edit_message_text(
            f"🎙️ <b>Voice Message</b>\n\nStatus: {status}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎙️ Upload Voice", callback_data="admin_set_voice"),
                 InlineKeyboardButton("🗑️ Delete",       callback_data="admin_del_voice")],
                [InlineKeyboardButton("🔙 Back",          callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    elif data == "admin_set_voice":
        context.user_data["awaiting"] = "voice"
        await q.edit_message_text(
            "🎙️ Voice note bhejo (record karke):",
            reply_markup=kb_back(), parse_mode=ParseMode.HTML)

    elif data == "admin_del_voice":
        cfg_set("voice_file_id", "")
        await q.answer("🗑️ Voice delete!", show_alert=True)
        await q.edit_message_text(
            "👑 <b>Admin Panel</b>", reply_markup=kb_admin(), parse_mode=ParseMode.HTML)

    # ── DEPOSIT ────────────────────────────────────────
    elif data == "admin_deposit_menu":
        dep_txt_ok = "✅ Custom set hai" if cfg.get("deposit_text","") else "📄 Default use ho raha hai"
        dep_photo  = "✅ Set hai" if cfg.get("deposit_photo","") else "❌ Nahi"
        await q.edit_message_text(
            f"💰 <b>Deposit Message Settings</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 Deposit Message : {dep_txt_ok}\n"
            f"📸 Deposit Photo   : {dep_photo}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<i>💡 Deposit button click hone pe yeh message aata hai.\n"
            f"Premium emoji, bold, italic — sab kuch kaam karta hai!</i>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Deposit Message Set Karo", callback_data="admin_set_deposit_text")],
                [InlineKeyboardButton("📸 Deposit Photo Set Karo",   callback_data="admin_set_deposit_photo"),
                 InlineKeyboardButton("🗑️ Photo Hatao",             callback_data="admin_del_deposit_photo")],
                [InlineKeyboardButton("🔙 Back",                     callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    elif data == "admin_set_deposit_text":
        context.user_data["awaiting"] = "deposit_text"
        cur = cfg.get("deposit_text", "")
        cur_disp = cur[:150] if cur else "(Default use ho raha hai)"
        await q.edit_message_text(
            "📝 <b>Deposit Message Set Karo</b>\n\n"
            "Deposit button click hone pe yeh message aayega.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "✅ <b>Sab kuch kaam karta hai:</b>\n"
            "• Premium / Custom emoji — seedha paste karo\n"
            "• <code>&lt;b&gt;Bold&lt;/b&gt;</code>  <code>&lt;i&gt;Italic&lt;/i&gt;</code>\n"
            "• Links:  <code>&lt;a href='url'&gt;Text&lt;/a&gt;</code>\n"
            "• Placeholders: <code>{deposit_emoji}</code>\n\n"
            f"Current:\n<i>{cur_disp}</i>\n\n"
            "Naya message bhejo 👇",
            reply_markup=kb_back("admin_deposit_menu"), parse_mode=ParseMode.HTML)

    # ── WELCOME / JOINED TEXT ──────────────────────────
    elif data == "admin_welcome_menu":
        context.user_data["awaiting"] = "welcome_text"
        await q.edit_message_text(
            f"📝 <b>Welcome Text Set Karo</b>\n\n"
            f"{'✨ <i>Premium emoji set hai!</i>' if '<tg-emoji' in cfg.get('welcome_text','') else ''}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 <b>Premium Emoji:</b> Directly paste karo — ID nahi chahiye!\n"
            "• Placeholders: <code>{join_emoji}</code> <code>{verify_emoji}</code>\n"
            "• HTML: <code>&lt;b&gt;</code> <code>&lt;i&gt;</code>\n"
            "• <code>{name}</code> → user ka naam\n\n"
            "Naya text bhejo (premium emoji bhi chalega ✨):",
            reply_markup=kb_back(), parse_mode=ParseMode.HTML)

    elif data == "admin_joined_text":
        context.user_data["awaiting"] = "joined_text"
        cur = cfg.get("joined_text", "")
        has_prem = "<tg-emoji" in cur
        await q.edit_message_text(
            "📝 <b>Joined Text Set Karo</b>\n\n"
            "Yeh message voice ke baad aata hai — deposit button ke saath.\n\n"
            f"{'✨ <i>Premium emoji already set hai!</i>' if has_prem else ''}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 <b>Premium Emoji:</b> Directly paste karo!\n"
            "• Placeholders: <code>{deposit_emoji}</code> <code>{voice_emoji}</code>\n"
            "• HTML: <code>&lt;b&gt;</code> <code>&lt;i&gt;</code>\n"
            "• Sound instructions mat dalo — voice caption alag hota hai\n\n"
            "Naya text bhejo (premium emoji bhi chalega ✨):",
            reply_markup=kb_back(), parse_mode=ParseMode.HTML)

    # ── BUTTON LABELS ──────────────────────────────────
    elif data == "admin_btn_labels":
        v = cfg.get("btn_verify_label", "✅ Verify & Claim Reward 🎁")
        d = cfg.get("btn_deposit_label", "🚀 Deposit Karo & Reward Pao 💰")
        await q.edit_message_text(
            f"🔘 <b>Button Labels</b>\n\n"
            f"✅ Verify Button:\n<code>{v}</code>\n\n"
            f"💰 Deposit Button:\n<code>{d}</code>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ Verify Btn",  callback_data="admin_set_verify_label"),
                 InlineKeyboardButton("✏️ Deposit Btn", callback_data="admin_set_deposit_label")],
                [InlineKeyboardButton("🔙 Back",         callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    elif data == "admin_set_verify_label":
        context.user_data["awaiting"] = "btn_verify_label"
        await q.edit_message_text(
            "✏️ Verify button ka naya text bhejo:\n(e.g. <code>✅ Claim Karo</code>)",
            reply_markup=kb_back("admin_btn_labels"), parse_mode=ParseMode.HTML)

    elif data == "admin_set_deposit_label":
        context.user_data["awaiting"] = "btn_deposit_label"
        await q.edit_message_text(
            "✏️ Deposit button ka naya text bhejo:\n(e.g. <code>💸 Abhi Deposit Karo</code>)",
            reply_markup=kb_back("admin_btn_labels"), parse_mode=ParseMode.HTML)

    # ── CUSTOM EMOJI MENU ──────────────────────────────
    elif data == "admin_emoji_menu":
        cfg2 = cfg_get()

        def _edisp(val): return val if val else "<i>(blank — no emoji)</i>"

        await q.edit_message_text(
            "🌟 <b>Custom Emoji Settings</b>\n\n"
            "Yahan se JOIN buttons ke emojis change ya hata sakte ho.\n\n"
            f"<code>{{join_emoji}}</code>    → {_edisp(cfg2.get('join_emoji','🔗'))}\n"
            f"<code>{{deposit_emoji}}</code> → {_edisp(cfg2.get('deposit_emoji','💰'))}\n"
            f"<code>{{voice_emoji}}</code>   → {_edisp(cfg2.get('voice_emoji','🔊'))}\n"
            f"<code>{{verify_emoji}}</code>  → {_edisp(cfg2.get('verify_emoji','✅'))}\n"
            f"<code>{{alert_emoji}}</code>   → {_edisp(cfg2.get('alert_emoji','⚡'))}\n\n"
            "💡 <b>Tips:</b>\n"
            "• Koi emoji bhejo → set ho jayega\n"
            "• <b>Hatane ke liye:</b> <code>0</code> ya <code>-</code> type karo\n"
            "• Sab ek saath hatane ke liye: <b>Sab Clear</b> button dabao",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Join Emoji",    callback_data="admin_set_emoji_join"),
                 InlineKeyboardButton("💰 Deposit Emoji", callback_data="admin_set_emoji_deposit")],
                [InlineKeyboardButton("🔊 Voice Emoji",   callback_data="admin_set_emoji_voice"),
                 InlineKeyboardButton("✅ Verify Emoji",  callback_data="admin_set_emoji_verify")],
                [InlineKeyboardButton("⚡ Alert Emoji",   callback_data="admin_set_emoji_alert")],
                [InlineKeyboardButton("🗑️ Sab Emoji Clear Karo", callback_data="admin_clear_all_emojis")],
                [InlineKeyboardButton("🔙 Back",          callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    elif data == "admin_clear_all_emojis":
        for k in ["join_emoji", "deposit_emoji", "voice_emoji", "verify_emoji", "alert_emoji"]:
            cfg_set(k, "")
        await q.answer("✅ Sab emojis hata diye gaye!", show_alert=True)
        cfg2 = cfg_get()
        def _edisp(val): return val if val else "<i>(blank)</i>"
        await q.edit_message_text(
            "🌟 <b>Custom Emoji Settings</b>\n\n"
            "✅ <b>Sab emojis clear ho gaye!</b>\n\n"
            f"<code>{{join_emoji}}</code>    → {_edisp(cfg2.get('join_emoji',''))}\n"
            f"<code>{{deposit_emoji}}</code> → {_edisp(cfg2.get('deposit_emoji',''))}\n"
            f"<code>{{voice_emoji}}</code>   → {_edisp(cfg2.get('voice_emoji',''))}\n"
            f"<code>{{verify_emoji}}</code>  → {_edisp(cfg2.get('verify_emoji',''))}\n"
            f"<code>{{alert_emoji}}</code>   → {_edisp(cfg2.get('alert_emoji',''))}\n\n"
            "💡 Wapas set karne ke liye kisi bhi button pe tap karo.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Join Emoji",    callback_data="admin_set_emoji_join"),
                 InlineKeyboardButton("💰 Deposit Emoji", callback_data="admin_set_emoji_deposit")],
                [InlineKeyboardButton("🔊 Voice Emoji",   callback_data="admin_set_emoji_voice"),
                 InlineKeyboardButton("✅ Verify Emoji",  callback_data="admin_set_emoji_verify")],
                [InlineKeyboardButton("⚡ Alert Emoji",   callback_data="admin_set_emoji_alert")],
                [InlineKeyboardButton("🗑️ Sab Emoji Clear Karo", callback_data="admin_clear_all_emojis")],
                [InlineKeyboardButton("🔙 Back",          callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    elif data.startswith("admin_set_emoji_"):
        key_map = {
            "admin_set_emoji_join":    "join_emoji",
            "admin_set_emoji_deposit": "deposit_emoji",
            "admin_set_emoji_voice":   "voice_emoji",
            "admin_set_emoji_verify":  "verify_emoji",
            "admin_set_emoji_alert":   "alert_emoji",
        }
        emoji_key = key_map.get(data, "")
        if emoji_key:
            context.user_data["awaiting"]  = "set_emoji"
            context.user_data["emoji_key"] = emoji_key
            await q.edit_message_text(
                f"✨ <b>Emoji Set / Hatao</b>\n\n"
                f"Key: <code>{emoji_key}</code>\n\n"
                f"<b>Options:</b>\n"
                f"• Regular emoji bhejo → set ho jayega 😊\n"
                f"• Premium emoji paste karo → woh bhi kaam karta hai ✨\n"
                f"• <b>Hatane ke liye:</b> <code>0</code> ya <code>-</code> type karo",
                reply_markup=kb_back("admin_emoji_menu"), parse_mode=ParseMode.HTML)

    elif data == "admin_voice_caption":
        cfg2 = cfg_get()
        context.user_data["awaiting"] = "voice_caption"
        cur_cap = cfg2.get("voice_caption", "🔊 Sound On Karo — Yeh zaroor suno! 👆")
        has_prem = "<tg-emoji" in cur_cap
        prem_note = " ✨ <i>(premium emoji set hai)</i>" if has_prem else ""
        await q.edit_message_text(
            f"🎤 <b>Voice Caption Set Karo</b>\n\n"
            f"Current:{prem_note}\n{fix_html_entities(cur_cap[:120])}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 <b>Premium Emoji Kaise Lagayen:</b>\n"
            "1️⃣ Custom emoji pe hold → Copy karo\n"
            "2️⃣ Yahan paste karke send karo\n"
            "3️⃣ Bot automatically save kar lega! ✨\n\n"
            "• HTML bhi allowed: <code>&lt;b&gt;</code> <code>&lt;i&gt;</code>\n\n"
            "Naya caption bhejo:",
            reply_markup=kb_back("admin_panel"), parse_mode=ParseMode.HTML)

    # ── ALERT MESSAGES ─────────────────────────────────
    elif data == "admin_alerts":
        nj = cfg.get("alert_not_joined", "")
        bl = cfg.get("alert_blocked", "")
        await q.edit_message_text(
            f"💬 <b>Alert Messages (Popup)</b>\n\n"
            f"❌ Not Joined Alert:\n<code>{nj}</code>\n\n"
            f"🚫 Blocked Alert:\n<code>{bl}</code>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ Not Joined Alert", callback_data="admin_set_alert_nj"),
                 InlineKeyboardButton("✏️ Blocked Alert",    callback_data="admin_set_alert_bl")],
                [InlineKeyboardButton("🔙 Back",              callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    elif data == "admin_set_alert_nj":
        context.user_data["awaiting"] = "alert_not_joined"
        await q.edit_message_text(
            "💬 'Channel join nahi kiya' wala alert text bhejo:\n"
            "(e.g. <code>❌ Pehle join karo!</code>)",
            reply_markup=kb_back("admin_alerts"), parse_mode=ParseMode.HTML)

    elif data == "admin_set_alert_bl":
        context.user_data["awaiting"] = "alert_blocked"
        await q.edit_message_text(
            "💬 'Block' wala alert text bhejo:\n"
            "(e.g. <code>🚫 Aap block hain!</code>)",
            reply_markup=kb_back("admin_alerts"), parse_mode=ParseMode.HTML)

    # ── BUTTONS PER ROW ────────────────────────────────
    elif data == "admin_btn_row":
        cur = cfg.get("btns_per_row", "2")
        await q.edit_message_text(
            f"🔢 <b>Buttons Per Row</b>\n\nCurrent: <b>{cur} per row</b>\n\n"
            f"Join channel buttons ek row mein kitne chahiye?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("1️⃣ Ek (Full Width)", callback_data="admin_bpr_1"),
                 InlineKeyboardButton("2️⃣ Do (Default)",    callback_data="admin_bpr_2")],
                [InlineKeyboardButton("🔙 Back",             callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    elif data == "admin_bpr_1":
        cfg_set("btns_per_row", "1")
        await q.answer("✅ Ek button per row!", show_alert=True)
        await q.edit_message_text("👑 <b>Admin Panel</b>",
                                   reply_markup=kb_admin(), parse_mode=ParseMode.HTML)

    elif data == "admin_bpr_2":
        cfg_set("btns_per_row", "2")
        await q.answer("✅ Do button per row!", show_alert=True)
        await q.edit_message_text("👑 <b>Admin Panel</b>",
                                   reply_markup=kb_admin(), parse_mode=ParseMode.HTML)

    # ── MESSAGE PHOTOS ─────────────────────────────────
    elif data == "admin_photo_menu":
        cfg2    = cfg_get()
        w_ok    = "✅ Set" if cfg2.get("welcome_photo")  else "❌ Nahi"
        j_ok    = "✅ Set" if cfg2.get("joined_photo")   else "❌ Nahi"
        d_ok    = "✅ Set" if cfg2.get("deposit_photo")  else "❌ Nahi"
        await q.edit_message_text(
            "🖼 <b>Message Photos</b>\n\n"
            "Har message ke saath ek photo set kar sakte ho.\n"
            "Photo ke andar message caption ke roop mein dikhega.\n\n"
            f"📸 Welcome Photo  : {w_ok}\n"
            f"📸 Joined Photo   : {j_ok}\n"
            f"📸 Deposit Photo  : {d_ok}\n\n"
            "<i>💡 Photo set karne ke liye button dabao, phir koi photo bhejo.</i>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📸 Set Welcome Photo",  callback_data="admin_set_welcome_photo"),
                 InlineKeyboardButton("🗑️ Del",               callback_data="admin_del_welcome_photo")],
                [InlineKeyboardButton("📸 Set Joined Photo",   callback_data="admin_set_joined_photo"),
                 InlineKeyboardButton("🗑️ Del",               callback_data="admin_del_joined_photo")],
                [InlineKeyboardButton("📸 Set Deposit Photo",  callback_data="admin_set_deposit_photo"),
                 InlineKeyboardButton("🗑️ Del",               callback_data="admin_del_deposit_photo")],
                [InlineKeyboardButton("🔙 Back",               callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    elif data == "admin_set_welcome_photo":
        context.user_data["awaiting"] = "welcome_photo"
        await q.edit_message_text(
            "📸 <b>Welcome Photo Set Karo</b>\n\n"
            "Jo photo welcome message ke saath dikhani hai woh yahan bhejo.\n\n"
            "⚠️ Photo ke saath aapka welcome text caption mein aayega.\n"
            "(Telegram caption max 1024 characters allow karta hai)",
            reply_markup=kb_back("admin_photo_menu"), parse_mode=ParseMode.HTML)

    elif data == "admin_set_joined_photo":
        context.user_data["awaiting"] = "joined_photo"
        await q.edit_message_text(
            "📸 <b>Joined Photo Set Karo</b>\n\n"
            "Jo photo channels join karne ke baad dikhani hai woh bhejo.",
            reply_markup=kb_back("admin_photo_menu"), parse_mode=ParseMode.HTML)

    elif data == "admin_set_deposit_photo":
        context.user_data["awaiting"] = "deposit_photo"
        await q.edit_message_text(
            "📸 <b>Deposit Photo Set Karo</b>\n\n"
            "Jo photo deposit button click karne ke baad dikhani hai woh bhejo.",
            reply_markup=kb_back("admin_photo_menu"), parse_mode=ParseMode.HTML)

    elif data == "admin_del_welcome_photo":
        cfg_set("welcome_photo", "")
        await q.answer("🗑️ Welcome photo delete ho gaya!", show_alert=True)
        # refresh menu
        cfg2 = cfg_get()
        w_ok = "❌ Nahi"; j_ok = "✅ Set" if cfg2.get("joined_photo") else "❌ Nahi"
        d_ok = "✅ Set" if cfg2.get("deposit_photo") else "❌ Nahi"
        await q.edit_message_text(
            "🖼 <b>Message Photos</b>\n\n"
            f"📸 Welcome Photo  : {w_ok}\n📸 Joined Photo   : {j_ok}\n📸 Deposit Photo  : {d_ok}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📸 Set Welcome Photo",  callback_data="admin_set_welcome_photo"),
                 InlineKeyboardButton("🗑️ Del",               callback_data="admin_del_welcome_photo")],
                [InlineKeyboardButton("📸 Set Joined Photo",   callback_data="admin_set_joined_photo"),
                 InlineKeyboardButton("🗑️ Del",               callback_data="admin_del_joined_photo")],
                [InlineKeyboardButton("📸 Set Deposit Photo",  callback_data="admin_set_deposit_photo"),
                 InlineKeyboardButton("🗑️ Del",               callback_data="admin_del_deposit_photo")],
                [InlineKeyboardButton("🔙 Back",               callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    elif data == "admin_del_joined_photo":
        cfg_set("joined_photo", "")
        await q.answer("🗑️ Joined photo delete ho gaya!", show_alert=True)
        cfg2 = cfg_get()
        w_ok = "✅ Set" if cfg2.get("welcome_photo") else "❌ Nahi"; j_ok = "❌ Nahi"
        d_ok = "✅ Set" if cfg2.get("deposit_photo") else "❌ Nahi"
        await q.edit_message_text(
            "🖼 <b>Message Photos</b>\n\n"
            f"📸 Welcome Photo  : {w_ok}\n📸 Joined Photo   : {j_ok}\n📸 Deposit Photo  : {d_ok}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📸 Set Welcome Photo",  callback_data="admin_set_welcome_photo"),
                 InlineKeyboardButton("🗑️ Del",               callback_data="admin_del_welcome_photo")],
                [InlineKeyboardButton("📸 Set Joined Photo",   callback_data="admin_set_joined_photo"),
                 InlineKeyboardButton("🗑️ Del",               callback_data="admin_del_joined_photo")],
                [InlineKeyboardButton("📸 Set Deposit Photo",  callback_data="admin_set_deposit_photo"),
                 InlineKeyboardButton("🗑️ Del",               callback_data="admin_del_deposit_photo")],
                [InlineKeyboardButton("🔙 Back",               callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    elif data == "admin_del_deposit_photo":
        cfg_set("deposit_photo", "")
        await q.answer("🗑️ Deposit photo delete ho gaya!", show_alert=True)
        cfg2 = cfg_get()
        w_ok = "✅ Set" if cfg2.get("welcome_photo") else "❌ Nahi"
        j_ok = "✅ Set" if cfg2.get("joined_photo")  else "❌ Nahi"; d_ok = "❌ Nahi"
        await q.edit_message_text(
            "🖼 <b>Message Photos</b>\n\n"
            f"📸 Welcome Photo  : {w_ok}\n📸 Joined Photo   : {j_ok}\n📸 Deposit Photo  : {d_ok}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📸 Set Welcome Photo",  callback_data="admin_set_welcome_photo"),
                 InlineKeyboardButton("🗑️ Del",               callback_data="admin_del_welcome_photo")],
                [InlineKeyboardButton("📸 Set Joined Photo",   callback_data="admin_set_joined_photo"),
                 InlineKeyboardButton("🗑️ Del",               callback_data="admin_del_joined_photo")],
                [InlineKeyboardButton("📸 Set Deposit Photo",  callback_data="admin_set_deposit_photo"),
                 InlineKeyboardButton("🗑️ Del",               callback_data="admin_del_deposit_photo")],
                [InlineKeyboardButton("🔙 Back",               callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    # ── LIVE STATS ─────────────────────────────────────
    elif data == "admin_stats":
        s      = db_stats()
        admins = admin_ids()
        ch1    = get_channels("channels")
        ch2    = get_channels("channels_after")
        voice  = "✅ Set" if cfg.get("voice_file_id") else "❌ Nahi"
        dlink  = "✅ Set" if cfg.get("deposit_link")  else "❌ Nahi"
        rlink  = "✅ Set" if cfg.get("register_link") else "❌ Nahi"
        bpr    = cfg.get("btns_per_row", "2")
        pct    = round(s['active'] / s['total'] * 100) if s['total'] else 0
        bar_on = round(pct / 10)
        bar    = "🟩" * bar_on + "⬜" * (10 - bar_on)
        await q.edit_message_text(
            f"📊 <b>LIVE BOT STATS</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👥 <b>USERS</b>\n"
            f"  📌 Total      : <b>{s['total']}</b>\n"
            f"  🟢 Active     : <b>{s['active']}</b>\n"
            f"  🚫 Blocked    : <b>{s['blocked']}</b>\n"
            f"  📅 Aaj Joined : <b>{s['today']}</b>\n\n"
            f"  {bar} <b>{pct}%</b> active\n\n"
            f"📢 <b>CHANNELS</b>\n"
            f"  Set-1 (Force) : <b>{len(ch1)}</b>\n"
            f"  Set-2 (Dep.)  : <b>{len(ch2)}</b>\n\n"
            f"⚙️ <b>SETTINGS</b>\n"
            f"  🎙 Voice      : {voice}\n"
            f"  💰 Dep Link   : {dlink}\n"
            f"  📌 Reg Link   : {rlink}\n"
            f"  🔢 Btns/Row   : <b>{bpr}</b>\n"
            f"  👑 Admins     : <b>{len(admins)}</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data="admin_stats"),
                 InlineKeyboardButton("🔙 Back",    callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    # ── USER MANAGER ───────────────────────────────────
    elif data == "admin_user_manager":
        s = db_stats()
        await q.edit_message_text(
            f"👥 <b>USER MANAGER</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📌 Total   : <b>{s['total']}</b>\n"
            f"🟢 Active  : <b>{s['active']}</b>\n"
            f"🚫 Blocked : <b>{s['blocked']}</b>\n"
            f"📅 Aaj     : <b>{s['today']}</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔍 Search User",   callback_data="admin_search_user"),
                 InlineKeyboardButton("🚫 Block User",    callback_data="admin_block_menu")],
                [InlineKeyboardButton("✅ Unblock User",  callback_data="admin_unblock_menu"),
                 InlineKeyboardButton("📋 Recent Users",  callback_data="admin_recent_users")],
                [InlineKeyboardButton("🔙 Back",          callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    elif data == "admin_recent_users":
        with __import__('sqlite3').connect(DB_PATH) as c:
            rows = c.execute(
                "SELECT user_id, first_name, username, joined_date, is_blocked "
                "FROM users ORDER BY rowid DESC LIMIT 10"
            ).fetchall()
        if not rows:
            await q.edit_message_text("❌ Koi user nahi mila.",
                reply_markup=kb_back("admin_user_manager"), parse_mode=ParseMode.HTML)
            return
        text = "📋 <b>Recent 10 Users</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for uid_, fname, uname, jdate, blocked in rows:
            status = "🚫" if blocked else "🟢"
            text += (f"{status} <code>{uid_}</code> — <b>{fname or 'No Name'}</b>"
                     f" (@{uname or '—'}) | {jdate}\n")
        await q.edit_message_text(text,
            reply_markup=kb_back("admin_user_manager"), parse_mode=ParseMode.HTML)

    # ── BLOCK / UNBLOCK ────────────────────────────────
    elif data == "admin_block_menu":
        context.user_data["awaiting"] = "block_user"
        await q.edit_message_text(
            "🚫 <b>Block User</b>\n\nUser ka ID bhejo jise block karna hai:\n"
            "<i>(Apna ID @userinfobot se pata karo)</i>",
            reply_markup=kb_back("admin_user_manager"), parse_mode=ParseMode.HTML)

    elif data == "admin_unblock_menu":
        context.user_data["awaiting"] = "unblock_user"
        await q.edit_message_text(
            "✅ <b>Unblock User</b>\n\nUser ka ID bhejo jise unblock karna hai:",
            reply_markup=kb_back("admin_user_manager"), parse_mode=ParseMode.HTML)

    # ── USER SEARCH ────────────────────────────────────
    elif data == "admin_search_user":
        context.user_data["awaiting"] = "search_user"
        await q.edit_message_text(
            "🔍 <b>User Search</b>\n\nUser ID bhejo jise search karna hai:",
            reply_markup=kb_back("admin_user_manager"), parse_mode=ParseMode.HTML)

    # ── BROADCAST ──────────────────────────────────────
    elif data == "admin_broadcast_menu":
        s = db_stats()
        await q.edit_message_text(
            f"📨 <b>BROADCAST</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📤 Recipients: <b>{s['active']}</b> active users\n\n"
            f"✅ <b>Supported types:</b>\n"
            f"📝 Text  |  🖼 Photo  |  🎥 Video\n"
            f"🎙 Voice  |  📄 File  |  🎭 Sticker\n"
            f"🎞 GIF  |  🎵 Audio  |  📍 Location\n\n"
            f"<b>Koi bhi ek message yahan bhejo — sab users ko jayega!</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📨 Broadcast Bhejo", callback_data="admin_bcast_any")],
                [InlineKeyboardButton("🔙 Back",            callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    elif data == "admin_bcast_any":
        context.user_data["awaiting"] = "broadcast"
        await q.edit_message_text(
            "📨 <b>Broadcast — Koi bhi message bhejo</b>\n\n"
            "Text, photo, video, voice, sticker, GIF, document, audio\n"
            "— <b>sab kuch kaam karta hai!</b>\n\n"
            "👇 Abhi message bhejo:",
            reply_markup=kb_back("admin_broadcast_menu"),
            parse_mode=ParseMode.HTML)

    # legacy type buttons bhi kaam karein
    elif data in ("admin_bcast_text", "admin_bcast_photo", "admin_bcast_video"):
        context.user_data["awaiting"] = "broadcast"
        await q.edit_message_text(
            "📨 <b>Broadcast</b>\n\nMessage bhejo:",
            reply_markup=kb_back("admin_broadcast_menu"),
            parse_mode=ParseMode.HTML)

    # ── DATABASE BACKUP ────────────────────────────────
    elif data == "admin_db_backup":
        import shutil, datetime
        await q.answer("⏳ Backup bana raha hoon...", show_alert=False)
        try:
            # Safe copy — live DB ko ek temp file mein copy karo (SQLite WAL safe)
            ts       = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            bak_path = os.path.join(_PROJECT_DIR, f"backup_{ts}.db")
            with sqlite3.connect(DB_PATH) as src:
                bak = sqlite3.connect(bak_path)
                src.backup(bak)
                bak.close()

            # File bhejon admin ko
            with open(bak_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=q.message.chat_id,
                    document=f,
                    filename=f"bot_backup_{ts}.db",
                    caption=(
                        f"💾 <b>Database Backup</b>\n"
                        f"📅 {datetime.datetime.now().strftime('%d %b %Y %I:%M %p')}\n"
                        f"📦 File: <code>bot_backup_{ts}.db</code>\n\n"
                        f"Restore karne ke liye yeh file wapas bhejo → "
                        f"Admin Panel → 📤 Restore Upload"
                    ),
                    parse_mode=ParseMode.HTML,
                )
            os.remove(bak_path)   # temp file clean up
        except Exception as e:
            await context.bot.send_message(
                q.message.chat_id,
                f"❌ Backup failed: <code>{e}</code>",
                parse_mode=ParseMode.HTML)

    # ── DATABASE RESTORE ────────────────────────────────
    elif data == "admin_db_restore":
        context.user_data["awaiting"] = "db_restore"
        await q.edit_message_text(
            "📤 <b>Database Restore</b>\n\n"
            "⚠️ <b>Dhyan rakhein:</b> Purana data replace ho jayega!\n\n"
            "Pehle download kiya hua <code>.db</code> backup file yahan bhejo:",
            reply_markup=kb_back("admin_panel"), parse_mode=ParseMode.HTML)

    # ── ADMIN MANAGE ───────────────────────────────────
    elif data == "admin_manage_admins":
        admins = admin_ids()
        text   = "👑 <b>ADMIN MANAGEMENT</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        if admins:
            text += "Current Admins:\n"
            for a in admins:
                text += f"  • <code>{a}</code>\n"
        else:
            text += "⚠️ Koi DB admin nahi\n(ENV ADMIN_IDS se chal raha)"
        await q.edit_message_text(text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Add Admin",    callback_data="admin_add_admin"),
                 InlineKeyboardButton("➖ Remove Admin", callback_data="admin_remove_admin")],
                [InlineKeyboardButton("🔙 Back",         callback_data="admin_panel")],
            ]))

    elif data == "admin_add_admin":
        context.user_data["awaiting"] = "add_admin"
        await q.edit_message_text(
            "👑 <b>Add Admin</b>\n\nNaye admin ka User ID bhejo:\n"
            "<i>(@userinfobot se pata karo)</i>",
            reply_markup=kb_back("admin_manage_admins"), parse_mode=ParseMode.HTML)

    elif data == "admin_remove_admin":
        context.user_data["awaiting"] = "remove_admin"
        await q.edit_message_text(
            "👑 <b>Remove Admin</b>\n\nJis admin ko hatana hai uska ID bhejo:",
            reply_markup=kb_back("admin_manage_admins"),
                                   parse_mode=ParseMode.HTML)

# ═══════════════════════════════════════════════════════════════════
#  MESSAGE HANDLER
# ═══════════════════════════════════════════════════════════════════

async def msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user     = update.effective_user
    awaiting = context.user_data.get("awaiting", "")

    if db_is_blocked(user.id) and user.id not in admin_ids():
        await update.message.reply_text("🚫 Aap block hain.")
        return

    if user.id not in admin_ids() or not awaiting:
        return

    context.user_data.pop("awaiting", None)
    msg     = update.message
    back_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]])

    # ── VOICE ────────────────────────────────────────
    if awaiting == "voice":
        if msg.voice:
            cfg_set("voice_file_id", msg.voice.file_id)
            await msg.reply_text("✅ Voice save ho gaya!", reply_markup=back_kb)
        else:
            await msg.reply_text("❌ Voice note bhejo (record karke)!", reply_markup=back_kb)
        return

    # ── BROADCAST ─────────────────────────────────────
    # copy_to → automatically sab types handle karta hai:
    # text, photo, video, voice, sticker, GIF, document, audio, location, sab!
    if awaiting == "broadcast":
        context.user_data.pop("broadcast_type", None)   # cleanup
        users    = db_all_users()
        ok = fail = 0
        blocked_uids = []

        sm = await msg.reply_text(f"📨 Broadcast shuru... (0/{len(users)})")

        for i, uid in enumerate(users):
            try:
                await msg.copy_to(chat_id=uid)
                ok += 1
            except Exception as e:
                err = str(e)
                if "bot was blocked" in err or "user is deactivated" in err or "chat not found" in err:
                    blocked_uids.append(uid)
                fail += 1
            # Telegram rate limit: ~30 msg/sec max → 0.04s safe delay
            await asyncio.sleep(0.04)
            if (i + 1) % 25 == 0:
                try: await sm.edit_text(f"📨 Chal raha hai... ({i+1}/{len(users)}) ✅{ok} ❌{fail}")
                except: pass

        # Auto-block jo users bot block kar chuke hain
        for uid in blocked_uids:
            try: db_block(uid)
            except: pass

        await sm.edit_text(
            f"📨 <b>Broadcast Complete!</b>\n\n"
            f"✅ Delivered : <b>{ok}</b>\n"
            f"❌ Failed    : <b>{fail}</b>\n"
            f"🚫 Auto-blocked: <b>{len(blocked_uids)}</b> (bot block kiya hua)",
            parse_mode=ParseMode.HTML, reply_markup=back_kb)
        return

    # ── USER SEARCH ──────────────────────────────────
    if awaiting == "search_user":
        try:
            uid = int(msg.text.strip())
            row = db_search_user(uid)
            if row:
                uid_, uname, fname, jdate, blocked, jcount = row
                status = "🚫 Blocked" if blocked else "🟢 Active"
                await msg.reply_text(
                    f"🔍 <b>User Info</b>\n\n"
                    f"🆔 ID         : <code>{uid_}</code>\n"
                    f"👤 Name       : {fname}\n"
                    f"📛 Username   : @{uname or 'nahi'}\n"
                    f"📅 Joined     : {jdate}\n"
                    f"🔢 /start x   : {jcount} baar\n"
                    f"🔴 Status     : {status}",
                    parse_mode=ParseMode.HTML, reply_markup=back_kb)
            else:
                await msg.reply_text("❌ User nahi mila database mein.", reply_markup=back_kb)
        except ValueError:
            await msg.reply_text("❌ Valid User ID dalo (sirf numbers)!", reply_markup=back_kb)
        return

    # ── BLOCK / UNBLOCK ──────────────────────────────
    if awaiting in ("block_user", "unblock_user"):
        try:
            uid = int(msg.text.strip())
            if awaiting == "block_user":
                db_block(uid)
                await msg.reply_text(f"🚫 <code>{uid}</code> block ho gaya!",
                                     parse_mode=ParseMode.HTML, reply_markup=back_kb)
            else:
                db_unblock(uid)
                await msg.reply_text(f"✅ <code>{uid}</code> unblock ho gaya!",
                                     parse_mode=ParseMode.HTML, reply_markup=back_kb)
        except ValueError:
            await msg.reply_text("❌ Valid User ID dalo!", reply_markup=back_kb)
        return

    # ── ADMIN ADD / REMOVE ───────────────────────────
    if awaiting == "add_admin":
        try:
            uid = int(msg.text.strip()); add_admin(uid)
            await msg.reply_text(f"✅ <code>{uid}</code> admin ban gaya!",
                                 parse_mode=ParseMode.HTML, reply_markup=back_kb)
        except ValueError:
            await msg.reply_text("❌ Valid ID dalo!", reply_markup=back_kb)
        return

    if awaiting == "remove_admin":
        try:
            uid = int(msg.text.strip()); remove_admin(uid)
            await msg.reply_text(f"✅ <code>{uid}</code> admin se hata diya!",
                                 parse_mode=ParseMode.HTML, reply_markup=back_kb)
        except ValueError:
            await msg.reply_text("❌ Valid ID dalo!", reply_markup=back_kb)
        return

    # ── DB RESTORE ─────────────────────────────────────
    if awaiting == "db_restore":
        import shutil, datetime
        if not msg.document:
            await msg.reply_text(
                "❌ <b>.db file bhejo!</b>\n\nKoi document nahi mila.",
                parse_mode=ParseMode.HTML, reply_markup=back_kb)
            return

        fname = msg.document.file_name or ""
        if not fname.endswith(".db"):
            await msg.reply_text(
                f"❌ Wrong file: <code>{fname}</code>\n\n"
                f"Sirf <code>.db</code> file accept hoti hai!",
                parse_mode=ParseMode.HTML, reply_markup=back_kb)
            return

        try:
            dl_path = os.path.join(_PROJECT_DIR, "restore_upload.db")
            tg_file  = await context.bot.get_file(msg.document.file_id)
            await tg_file.download_to_drive(dl_path)

            test = sqlite3.connect(dl_path)
            tables = test.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            test.close()
            table_names = [t[0] for t in tables]
            if "config" not in table_names or "users" not in table_names:
                os.remove(dl_path)
                await msg.reply_text(
                    "❌ <b>Invalid backup file!</b>\n\n"
                    "Yeh is bot ka backup nahi lagta (config/users table missing).",
                    parse_mode=ParseMode.HTML, reply_markup=back_kb)
                return

            ts       = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            auto_bak = os.path.join(_PROJECT_DIR, f"pre_restore_{ts}.db")
            with sqlite3.connect(DB_PATH) as src:
                bak = sqlite3.connect(auto_bak)
                src.backup(bak)
                bak.close()

            shutil.copy2(dl_path, DB_PATH)
            os.remove(dl_path)

            await msg.reply_text(
                f"✅ <b>Database Restore Ho Gaya!</b>\n\n"
                f"📋 Tables: <code>{', '.join(table_names)}</code>\n"
                f"💾 Old DB auto-saved as: <code>pre_restore_{ts}.db</code> (server pe)\n\n"
                f"Bot ab naye data ke saath chal raha hai!",
                parse_mode=ParseMode.HTML, reply_markup=back_kb)
        except Exception as e:
            await msg.reply_text(
                f"❌ Restore failed: <code>{e}</code>",
                parse_mode=ParseMode.HTML, reply_markup=back_kb)
        return

    # ── MESSAGE PHOTO UPLOAD ──────────────────────────────
    if awaiting in ("welcome_photo", "joined_photo", "deposit_photo"):
        if msg.photo:
            file_id = msg.photo[-1].file_id   # sabse badi quality
            cfg_set(awaiting, file_id)
            label_map = {
                "welcome_photo":  "Welcome Photo",
                "joined_photo":   "Joined Photo",
                "deposit_photo":  "Deposit Photo",
            }
            label = label_map.get(awaiting, awaiting)
            await msg.reply_text(
                f"✅ <b>{label} save ho gaya!</b>\n\n"
                f"Ab is photo ke saath message jayega.",
                parse_mode=ParseMode.HTML, reply_markup=back_kb)
        else:
            await msg.reply_text(
                "❌ <b>Photo nahi mili!</b>\n\nKripya ek photo bhejo (file nahi, seedha photo).",
                parse_mode=ParseMode.HTML, reply_markup=back_kb)
        return

    # ── CHANNEL ADD — 2 STEP (Forward + Link) ───────────
    ch_set_key = context.user_data.get("ch_set_key", "channels")

    if awaiting == "ch_forward":
        # ✅ FIX: Forward ya @username/link — dono se channel add karo
        fwd_chat = None
        if getattr(msg, 'forward_from_chat', None):
            fwd_chat = msg.forward_from_chat
        elif getattr(getattr(msg, 'forward_origin', None), 'chat', None):
            fwd_chat = msg.forward_origin.chat

        if fwd_chat and getattr(fwd_chat, 'type', '') in ('channel', 'supergroup'):
            # ── Method 1: Forward se detect ──
            context.user_data["new_ch_id"] = str(fwd_chat.id)
            context.user_data["awaiting"]  = "ch_name"
            sl = "Set-1" if ch_set_key == "channels" else "Set-2"
            await msg.reply_text(
                f"✅ <b>Channel Detect Ho Gaya!</b>\n"
                f"🆔 ID : <code>{fwd_chat.id}</code>\n\n"
                f"➕ <b>{sl} — Step 2/3</b>\n\n"
                f"Button pe <b>kya naam dikhana hai</b> woh type karo:",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Cancel", callback_data="admin_panel")]])
            )
        else:
            # ── Method 2: @username ya t.me link se detect ──
            text_in = (msg.text or "").strip()
            if text_in:
                # t.me link se @username nikalo
                if "t.me/" in text_in:
                    uname = "@" + text_in.split("t.me/")[-1].split("/")[0].split("?")[0]
                elif text_in.startswith("@"):
                    uname = text_in
                else:
                    uname = "@" + text_in
                try:
                    chat_obj = await context.bot.get_chat(uname)
                    context.user_data["new_ch_id"]   = str(chat_obj.id)
                    context.user_data["new_ch_name"] = chat_obj.title or uname
                    context.user_data["awaiting"]    = "ch_name"
                    sl = "Set-1" if ch_set_key == "channels" else "Set-2"
                    await msg.reply_text(
                        f"✅ <b>Channel Detect Ho Gaya!</b>\n"
                        f"📢 Naam : <b>{chat_obj.title}</b>\n"
                        f"🆔 ID   : <code>{chat_obj.id}</code>\n\n"
                        f"➕ <b>{sl} — Step 2/3</b>\n\n"
                        f"Button pe <b>kya naam dikhana hai</b> woh type karo:\n"
                        f"<i>(Same naam chahiye to: <code>{chat_obj.title}</code>)</i>",
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("❌ Cancel", callback_data="admin_panel")]])
                    )
                except Exception:
                    await msg.reply_text(
                        "❌ <b>Channel detect nahi hua!</b>\n\n"
                        "Do tarike se channel add karo:\n\n"
                        "1️⃣ Channel ki post <b>forward</b> karo yahan\n"
                        "2️⃣ Ya channel ka <b>@username</b> type karo\n"
                        "   (e.g. <code>@mychannel</code>)\n"
                        "   Ya link: <code>https://t.me/mychannel</code>\n\n"
                        "⚠️ Private channel ke liye sirf <b>forward</b> kaam karega",
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("❌ Cancel", callback_data="admin_panel")]])
                    )
            else:
                await msg.reply_text(
                    "❌ <b>Kuch nahi mila!</b>\n\n"
                    "Do tarike se channel add karo:\n\n"
                    "1️⃣ Channel ki post <b>forward</b> karo\n"
                    "2️⃣ Ya <b>@username</b> type karo",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("❌ Cancel", callback_data="admin_panel")]])
                )
        return

    if awaiting == "ch_name":
        context.user_data["new_ch_name"] = msg.text.strip()
        context.user_data["awaiting"]    = "ch_link"
        sl = "Set-1" if ch_set_key == "channels" else "Set-2"
        await msg.reply_text(
            f"✅ <b>Naam set: {msg.text.strip()}</b>\n\n"
            f"➕ <b>{sl} — Step 3/3</b>\n\n"
            f"Ab channel ka <b>Invite Link</b> bhejo:\n"
            f"(e.g. <code>https://t.me/yourchannel</code>)",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data="admin_panel")]])
        )
        return

    if awaiting == "ch_link":
        ch_name  = context.user_data.pop("new_ch_name", "Channel")
        ch_id    = context.user_data.pop("new_ch_id", "")
        ch_link  = msg.text.strip()
        key      = context.user_data.pop("ch_set_key", "channels")
        channels = get_channels(key)
        channels.append({"name": ch_name, "id": ch_id, "link": ch_link})
        set_channels(channels, key)
        sl = "Set-1 (Force Join)" if key == "channels" else "Set-2 (After Join)"
        await msg.reply_text(
            f"✅ <b>Channel Add Ho Gaya!</b>\n\n"
            f"📢 Naam   : <b>{ch_name}</b>\n"
            f"🆔 ID     : <code>{ch_id}</code>\n"
            f"🔗 Link   : {ch_link}\n\n"
            f"📌 <b>Button pe yahi naam dikhega: {ch_name}</b>\n"
            f"Total {sl}: <b>{len(channels)}</b>",
            parse_mode=ParseMode.HTML, reply_markup=back_kb)
        return

    # ── CUSTOM EMOJI INPUT (regular + Telegram premium both) ──
    if awaiting == "set_emoji":
        emoji_key = context.user_data.get("emoji_key", "")
        if emoji_key:
            # 🌟 Check karo — premium custom emoji entity hai?
            value      = msg.text.strip() if msg.text else ""
            is_premium = False
            if msg.entities:
                for ent in msg.entities:
                    if ent.type == "custom_emoji" and ent.custom_emoji_id:
                        # Premium animated emoji — tg-emoji HTML tag store karo
                        fallback = (msg.text or "")[ent.offset : ent.offset + ent.length]
                        value    = f'<tg-emoji emoji-id="{ent.custom_emoji_id}">{fallback}</tg-emoji>'
                        is_premium = True
                        break

            # ✅ FIX: "0" ya "-" bhejo to emoji hata jayega (clear hoga)
            if value.lower() in ("0", "-", "off", "none", "clear", "hata", "hatao"):
                value      = ""
                is_premium = False
            elif not value:
                await msg.reply_text(
                    "⚠️ Emoji bhejo — ya <code>0</code> type karo emoji hatane ke liye!",
                    parse_mode=ParseMode.HTML, reply_markup=back_kb)
                return

            cfg_set(emoji_key, value)
            if not value:
                preview = "🗑️ <i>Emoji hata diya gaya (blank)</i>"
            elif is_premium:
                preview = "✨ Premium animated emoji!"
            else:
                preview = value
            await msg.reply_text(
                f"✅ <b>Set ho gaya!</b>\n\nKey: <code>{emoji_key}</code>\n"
                f"Value: {preview}",
                parse_mode=ParseMode.HTML, reply_markup=back_kb)
        return

    # ── ALL TEXT INPUTS (including voice_caption) ─────
    # ✅ UNIFIED: Sabhi text inputs ke liye ek hi block
    # preserve_custom_emojis → <tg-emoji> tags → DB mein save → render hota hai
    key_map = {
        # ── User messages ──────────────────────────────
        "welcome_text":            "welcome_text",
        "joined_text":             "joined_text",
        "deposit_text":            "deposit_text",
        "voice_caption":           "voice_caption",       # ✅ FIX: premium emoji ab kaam karega
        "dm_agent_text":           "dm_agent_text",
        "register_instructions":   "register_instructions",
        # ── Links ──────────────────────────────────────
        "deposit_link":            "deposit_link",
        "register_link":           "register_link",
        # ── Button labels ──────────────────────────────
        "btn_verify_label":        "btn_verify_label",
        "btn_deposit_label":       "btn_deposit_label",
        "deposit_popup_btn_label": "deposit_popup_btn_label",
        # ── Alert popups ───────────────────────────────
        "alert_not_joined":        "alert_not_joined",
        "alert_blocked":           "alert_blocked",
    }
    if awaiting in key_map:
        import re as _re
        # ── Custom / premium emoji preserve karo (sabhi text inputs ke liye) ──
        text_val = preserve_custom_emojis(msg.text or "", msg.entities or [])
        if not text_val.strip():
            text_val = (msg.text or "").strip()
        cfg_set(key_map[awaiting], text_val)

        # ── Confirmation: premium emoji status + live preview ──
        has_premium = "<tg-emoji" in text_val
        # Sirf pehle 150 chars preview (HTML render hoga → emoji dikhega)
        preview_raw  = text_val[:150] + ("…" if len(text_val) > 150 else "")
        # Links ke liye plain preview (HTML tags strip)
        if awaiting in ("deposit_link", "register_link"):
            preview_line = f"\n🔗 <code>{_re.sub(r'<[^>]+>', '', text_val)[:80]}</code>"
            premium_line = ""
        else:
            premium_line = "\n✨ <i>Premium animated emoji save ho gaya!</i>" if has_premium else ""
            preview_line = f"\n\n<b>Preview:</b>\n{fix_html_entities(preview_raw)}"

        label = awaiting.replace("_", " ").title()
        await msg.reply_text(
            f"✅ <b>{label} update ho gaya!</b>{premium_line}{preview_line}",
            parse_mode=ParseMode.HTML, reply_markup=back_kb)

# ═══════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════

async def _main_async():
    """
    ════════════════════════════════════════════════════════
    Pure asyncio polling loop — Updater ka bilkul use nahi.

    WHY: Render uses Python 3.14. PTB v20/v21 ka Updater
    class __slots__ use karta hai jo Python 3.14 mein
    __init__ pe hi crash karta hai:
      'Updater' object has no attribute
      '_Updater__polling_cleanup_cb'

    FIX: Application.builder() se sirf bot + dispatcher
    banao. Polling manually karo via bot.get_updates().
    Updater object kabhi nahi banega = crash impossible.
    ════════════════════════════════════════════════════════
    """
    import sys

    # ── Step 1: BOT_TOKEN check ────────────────────────────
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        logger.error("=" * 55)
        logger.error("❌  BOT_TOKEN SET NAHI HAI!")
        logger.error("   Render Dashboard → Environment → Add:")
        logger.error("   Key: BOT_TOKEN")
        logger.error("   Value: apna bot token (@BotFather se)")
        logger.error("=" * 55)
        sys.exit(1)

    # ── Step 2: Database initialize ───────────────────────
    try:
        init_db()
        logger.info("✅ Database ready")
    except Exception as e:
        logger.error(f"❌ Database error: {e}")
        sys.exit(1)

    # ── Step 3: Keep-alive server ─────────────────────────
    try:
        port = int(os.getenv("PORT", "10000").strip().split()[0])
    except (ValueError, IndexError):
        port = 10000
    start_keep_alive(port)

    # ── Step 4: Build Application WITHOUT Updater ─────────
    # updater=None → PTB Updater object kabhi nahi banega
    app = (
        Application.builder()
        .token(token)
        .updater(None)          # ← KEY FIX: no Updater at all
        .build()
    )
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("admin",  cmd_admin))
    app.add_handler(CallbackQueryHandler(cb_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, msg_handler))

    await app.initialize()
    await app.start()

    # ── Step 5: Webhook delete + conflict clear ────────────
    # 409 Conflict fix: purana instance ya webhook clear karo
    try:
        await app.bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Webhook cleared — polling shuru hoga")
    except Exception as e:
        logger.warning(f"⚠️ delete_webhook: {e}")

    # Purane instance ke band hone ka intezaar (deploy overlap fix)
    await asyncio.sleep(3)
    logger.info("✅ Bot chal raha hai...")

    # ── Step 6: Self-ping background task start ────────────
    asyncio.create_task(_self_ping_loop(port))

    # ── Step 7: Manual get_updates loop ───────────────────
    offset = None
    while True:
        try:
            updates = await app.bot.get_updates(
                offset=offset,
                timeout=30,
                allowed_updates=Update.ALL_TYPES,
            )
            for update in updates:
                offset = update.update_id + 1
                await app.process_update(update)
        except asyncio.CancelledError:
            break
        except Exception as e:
            err = str(e)
            if "Conflict" in err or "409" in err:
                # Doosra instance chal raha hai — 15 sec wait karo
                logger.warning("⚠️ 409 Conflict — doosra instance mil raha hai, 15s wait...")
                await asyncio.sleep(15)
            else:
                logger.error(f"❌ Polling error: {e} — 5 sec mein retry...")
                await asyncio.sleep(5)

    # ── Graceful shutdown ──────────────────────────────────
    await app.stop()
    await app.shutdown()


def main():
    try:
        asyncio.run(_main_async())
    except KeyboardInterrupt:
        logger.info("Bot manually band kiya gaya.")


if __name__ == "__main__":
    main()
