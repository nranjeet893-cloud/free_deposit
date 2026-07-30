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
                "🔊 <b>Sound On Karo — Important Message Sun Lo!</b> 👆\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "⚠️ <b>Deposit Milega — Play on Sound</b> 🎙️👆\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "👇 <b>Deposit karne ke liye click karo:</b>"
            ),
            "deposit_text": (
                "🎁 <b>Deposit Karo — Reward Unlock Karo!</b>\n\n"
                "💸 Pehli deposit pe <b>BONUS</b> milega!\n\n"
                "👇 Niche button pe click karo:"
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
            "btn_verify_label":  "🔓 Verify & Unlock Reward 🔐",
            "btn_deposit_label": "💰 Deposit Karo & Bonus Pao 🚀",
            # ── Custom emojis (admin se change ho sakta hai) ──
            "join_emoji":    "🔗",
            "deposit_emoji": "💰",
            "voice_emoji":   "🔊",
            "verify_emoji":  "✅",
            "alert_emoji":   "⚡",
            # ── Voice caption ──
            "voice_caption": "🔊 Sound On Karo — Yeh zaroor suno! 👆",
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
    """Channel button label — exactly as entered by admin."""
    return ch.get("name", f"Channel {idx + 1}").strip()

def _build_channel_buttons(channels, cfg, ch_set="set1"):
    """Channels ki rows banata hai — callback buttons (no ↗ URL arrow)."""
    per_row = int(cfg.get("btns_per_row", "2"))
    rows, pair = [], []
    for i, ch in enumerate(channels):
        label = _join_btn_label(ch, cfg, idx=i)
        pair.append(InlineKeyboardButton(label, callback_data=f"ch_join_{ch_set}_{i}"))
        if len(pair) == per_row:
            rows.append(pair); pair = []
    if pair:
        rows.append(pair)
    return rows

def kb_force_join(not_joined, cfg):
    rows = _build_channel_buttons(not_joined, cfg, ch_set="set1")
    verify_label = apply_emojis(cfg.get("btn_verify_label", "✅ Verify & Claim Reward 🎁"), cfg)
    rows.append([InlineKeyboardButton(verify_label, callback_data="verify_join")])
    return InlineKeyboardMarkup(rows)

def kb_after_join(cfg):
    """Deposit screen — Set-2 channels + deposit button (no ↗ arrows)."""
    after_chs = get_channels("channels_after")
    rows = _build_channel_buttons(after_chs, cfg, ch_set="set2")
    deposit_label = apply_emojis(cfg.get("btn_deposit_label", "💰 Deposit Karo & Reward Pao 🚀"), cfg)
    # Deposit button = callback → sirf click pe info aayega
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
        [InlineKeyboardButton("🔢 Buttons Per Row",        callback_data="admin_btn_row")],
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
    voice_id    = cfg.get("voice_file_id", "")
    joined_text = cfg.get("joined_text", "✅ <b>Sab Channels Join Ho Gaye!</b>")
    # {name} → actual naam, "None" kabhi nahi aayega
    safe_name   = user_name.strip() if user_name and user_name != "None" else "Dost"
    joined_text = joined_text.replace("{name}", safe_name)
    voice_caption = cfg.get("voice_caption", "🔊 Sound On Karo — Yeh zaroor suno! 👆")
    voice_caption = apply_emojis(voice_caption, cfg)   # ✅ emoji apply
    joined_text   = apply_emojis(joined_text, cfg)     # ✅ emoji apply

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

    # Step 2: Voice note (admin-set caption)
    if voice_id:
        try:
            await bot.send_voice(
                chat_id=chat_id,
                voice=voice_id,
                caption=voice_caption,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning(f"Voice send failed: {e}")

    # Step 3: Joined text + Deposit button ONLY (register info → deposit click pe aayega)
    sent = await bot.send_message(
        chat_id=chat_id,
        text=joined_text,
        reply_markup=kb_after_join(cfg),
        parse_mode=ParseMode.HTML,
    )
    db_set_msg(user_id, sent.message_id)

    # ℹ️ Register/instruction text → deposit button click pe aayega

# ═══════════════════════════════════════════════════════════════════
#  /start COMMAND
# ═══════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
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

    if not_joined:
        # naam nahi dikhana — {name} ko empty string se replace karo safely
        raw_text = cfg.get("welcome_text", "🔐 <b>Welcome!</b> Channels join karo.")
        safe_name = (user.first_name or user.username or "").strip()
        text = raw_text.replace("{name}", safe_name).replace("Hey , ", "Hey 👋 ").replace("Hey ,", "Hey 👋").strip()
        text = apply_emojis(text, cfg)   # ✅ custom emojis apply karo
        sent = await update.message.reply_text(
            text,
            reply_markup=kb_force_join(not_joined, cfg),
            parse_mode=ParseMode.HTML,
        )
        db_set_msg(user.id, sent.message_id)
    else:
        await send_joined_content(context.bot, update.effective_chat.id, user.id, cfg, user.first_name or user.username or 'Dost')

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
    await q.answer()

    if data == "noop":
        return

    # ════════════════════════════════════════════════
    #  VERIFY JOIN (User side)
    # ════════════════════════════════════════════════
    if data == "verify_join":
        if db_is_blocked(user.id):
            alert_msg = cfg.get("alert_blocked", "🚫 Aap block hain.")
            await q.answer(alert_msg, show_alert=True)
            return

        not_joined = await check_not_joined(context.bot, user.id)

        if not_joined:
            alert_msg = cfg.get("alert_not_joined",
                "❌ Pehle saare channels join karo! Phir Verify karo.")
            await q.answer(alert_msg, show_alert=True)

            # Refresh karke sirf baaki wale channels dikhao
            try: await q.message.delete()
            except: pass
            cfg2     = cfg_get()
            raw_text = cfg2.get("welcome_text", "🔐 <b>Welcome!</b>\n\nChannels join karo.")
            base_text = raw_text.replace("{name}", "").replace("Hey , ", "").replace("Hey ,", "").strip()
            base_text = apply_emojis(base_text, cfg2)   # ✅ custom emoji apply
            sent = await context.bot.send_message(
                chat_id=q.message.chat_id,
                text=base_text,
                reply_markup=kb_force_join(not_joined, cfg2),
                parse_mode=ParseMode.HTML,
            )
            db_set_msg(user.id, sent.message_id)
            return

        try: await q.message.delete()
        except: pass
        await send_joined_content(context.bot, q.message.chat_id, user.id, cfg, user.first_name or user.username or 'Dost')
        return

    # ════════════════════════════════════════════════
    #  CHANNEL JOIN LINK SENDER (no ↗ button fix)
    # ════════════════════════════════════════════════
    if data.startswith("ch_join_"):
        parts   = data.split("_")
        ch_set  = parts[2]
        idx     = int(parts[3])
        set_key = "channels" if ch_set == "set1" else "channels_after"
        chs     = get_channels(set_key)
        if idx < len(chs):
            ch   = chs[idx]
            link = ch.get("link", "").strip()
            name = ch.get("name", f"Channel {idx+1}")
            join_emoji = cfg.get("join_emoji", "🔗")
            if link:
                await context.bot.send_message(
                    chat_id=q.message.chat_id,
                    text=f"{join_emoji} <b>{name}</b>\n\nNiche button pe click karke join karo 👇",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(f"👉 {name} Join Karo", url=link)
                    ]]),
                    parse_mode=ParseMode.HTML,
                )
            else:
                await q.answer("⚠️ Link set nahi hai!", show_alert=True)
        return

    # ════════════════════════════════════════════════
    #  DEPOSIT BUTTON CLICK → info + link send
    # ════════════════════════════════════════════════
    if data == "deposit_clicked":
        deposit_link  = cfg.get("deposit_link", "").strip()
        register_link = cfg.get("register_link", "").strip()
        reg_instr     = cfg.get("register_instructions", "").strip()
        dm_agent_text = cfg.get("dm_agent_text", "").strip()
        dep_emoji     = cfg.get("deposit_emoji", "💰")

        if not deposit_link:
            await q.answer("⚠️ Deposit link set nahi hai!", show_alert=True)
            return

        parts = [f"{dep_emoji} <b>Deposit Link:</b>\n<a href='{deposit_link}'>{deposit_link}</a>"]
        if register_link:
            reg_display = f'<a href="{register_link}">{register_link}</a>'
            if reg_instr:
                parts.append(reg_instr.replace("{register_link}", reg_display))
            else:
                parts.append(f"📌 <b>Register Link:</b>\n{reg_display}")
        if dm_agent_text:
            parts.append(dm_agent_text)

        full_text = "\n\n".join(parts)
        await context.bot.send_message(
            chat_id=q.message.chat_id,
            text=full_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(f"{dep_emoji} Deposit Karo", url=deposit_link)
            ]]),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
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
            "📨 <b>Channel ki koi bhi post yahan FORWARD karo</b>\n\n"
            "💡 Bot automatically naam aur ID detect kar lega!\n\n"
            "Kaise forward kare:\n"
            "Channel kholo → koi message pe tap karo → Forward → Yahan bhejo",
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
            "📨 <b>Channel ki koi bhi post yahan FORWARD karo</b>\n\n"
            "💡 Bot automatically naam aur ID detect kar lega!\n\n"
            "Kaise forward kare:\n"
            "Channel kholo → koi message pe tap karo → Forward → Yahan bhejo",
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
        link     = cfg.get("deposit_link", "") or "Set nahi"
        reg_link = cfg.get("register_link", "") or "Set nahi"
        dm_agent = cfg.get("dm_agent_text", "") or "Set nahi"
        await q.edit_message_text(
            f"💰 <b>Deposit Settings</b>\n\n"
            f"🔗 Deposit Link: <code>{link}</code>\n\n"
            f"📌 Register Link: <code>{reg_link}</code>\n\n"
            f"💝 DM Agent Text: <code>{dm_agent}</code>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Deposit Link",    callback_data="admin_set_deposit_link"),
                 InlineKeyboardButton("📝 Joined Text",     callback_data="admin_set_deposit_text")],
                [InlineKeyboardButton("📌 Register Link",   callback_data="admin_set_register_link"),
                 InlineKeyboardButton("📋 Register Instr.", callback_data="admin_set_register_instr")],
                [InlineKeyboardButton("💝 DM Agent Text",   callback_data="admin_set_dm_agent")],
                [InlineKeyboardButton("🔙 Back",            callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    elif data == "admin_set_deposit_link":
        context.user_data["awaiting"] = "deposit_link"
        await q.edit_message_text(
            "💰 Deposit link bhejo:", reply_markup=kb_back("admin_deposit_menu"), parse_mode=ParseMode.HTML)

    elif data == "admin_set_deposit_text":
        context.user_data["awaiting"] = "deposit_text"
        await q.edit_message_text(
            "📝 Deposit screen text bhejo:", reply_markup=kb_back("admin_deposit_menu"), parse_mode=ParseMode.HTML)

    elif data == "admin_set_register_link":
        context.user_data["awaiting"] = "register_link"
        await q.edit_message_text(
            "📌 <b>Register Link bhejo:</b>\n"
            "(e.g. <code>https://13l777.com/register?inviteCode=XXXXX</code>)\n\n"
            "Yeh link second message mein aayega.",
            reply_markup=kb_back("admin_deposit_menu"), parse_mode=ParseMode.HTML)

    elif data == "admin_set_register_instr":
        context.user_data["awaiting"] = "register_instructions"
        await q.edit_message_text(
            "📋 <b>Register Instructions text bhejo:</b>\n\n"
            "Use <code>{register_link}</code> jahan link dikhana ho.\n\n"
            "Example:\n"
            "<code>📌 REGISTER LINK 📌\n\n{register_link}\n\nSend Screenshot Agent UID And Bank add Screenshot Send</code>",
            reply_markup=kb_back("admin_deposit_menu"), parse_mode=ParseMode.HTML)

    elif data == "admin_set_dm_agent":
        context.user_data["awaiting"] = "dm_agent_text"
        await q.edit_message_text(
            "💝 <b>DM Agent text bhejo:</b>\n\n"
            "Example:\n"
            "<code>💝DM Agent 👉 @Game13lbouns</code>",
            reply_markup=kb_back("admin_deposit_menu"), parse_mode=ParseMode.HTML)

    # ── WELCOME / JOINED TEXT ──────────────────────────
    elif data == "admin_welcome_menu":
        context.user_data["awaiting"] = "welcome_text"
        await q.edit_message_text(
            "📝 Welcome text bhejo.\n\n💡 Tip: Sirf text likho, naam automatic nahi aayega.",
            reply_markup=kb_back(), parse_mode=ParseMode.HTML)

    elif data == "admin_joined_text":
        context.user_data["awaiting"] = "joined_text"
        await q.edit_message_text(
            "📝 Join ke baad dikhne wala text bhejo:",
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
        await q.edit_message_text(
            "🌟 <b>Custom Emoji Settings</b>\n\n"
            "Yahan se bot ke har hisse ka emoji change karo.\n"
            "Texts mein in placeholders ka use karo:\n\n"
            f"<code>{{join_emoji}}</code>    → {cfg2.get('join_emoji','🔗')}\n"
            f"<code>{{deposit_emoji}}</code> → {cfg2.get('deposit_emoji','💰')}\n"
            f"<code>{{voice_emoji}}</code>   → {cfg2.get('voice_emoji','🔊')}\n"
            f"<code>{{verify_emoji}}</code>  → {cfg2.get('verify_emoji','✅')}\n"
            f"<code>{{alert_emoji}}</code>   → {cfg2.get('alert_emoji','⚡')}\n\n"
            "💡 <b>Tip:</b> Welcome text mein <code>{{verify_emoji}}</code> likho — "
            "wahan automatically woh emoji aa jayega!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Join Emoji",    callback_data="admin_set_emoji_join"),
                 InlineKeyboardButton("💰 Deposit Emoji", callback_data="admin_set_emoji_deposit")],
                [InlineKeyboardButton("🔊 Voice Emoji",   callback_data="admin_set_emoji_voice"),
                 InlineKeyboardButton("✅ Verify Emoji",     callback_data="admin_set_emoji_verify")],
                [InlineKeyboardButton("⚡ Alert Emoji",      callback_data="admin_set_emoji_alert")],
                [InlineKeyboardButton("🔙 Back",         callback_data="admin_panel")],
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
                f"✨ <b>Premium Custom Emoji Set Karo</b>\n\n"
                f"Key: <code>{emoji_key}</code>\n\n"
                f"<b>Kaise bhejein:</b>\n"
                f"Telegram mein custom emoji type karo (premium wala ✨) aur yahan bhejo\n\n"
                f"Ya regular emoji bhi chalta hai 😊",
                reply_markup=kb_back("admin_emoji_menu"), parse_mode=ParseMode.HTML)

    elif data == "admin_voice_caption":
        cfg2 = cfg_get()
        context.user_data["awaiting"] = "voice_caption"
        await q.edit_message_text(
            "🎤 <b>Voice Caption Set Karo</b>\n\n"
            f"Current: <code>{cfg2.get('voice_caption', '🔊 Sound On Karo')}</code>\n\n"
            "Naya caption type karo (HTML tags allowed):",
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

    # ── DB RESTORE ───────────────────────────────────
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
            # Download file
            dl_path = os.path.join(_PROJECT_DIR, "restore_upload.db")
            tg_file  = await context.bot.get_file(msg.document.file_id)
            await tg_file.download_to_drive(dl_path)

            # Validate — kya yeh valid SQLite DB hai?
            test = sqlite3.connect(dl_path)
            tables = test.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            test.close()
            table_names = [t[0] for t in tables]
            if "config" not in table_names or "users" not in table_names:
                os.remove(dl_path)
                await msg.reply_text(
                    "❌ <b>Invalid backup file!</b>\n\n"
                    "Yeh is bot ka backup nahi lagta (config/users table missing).",
                    parse_mode=ParseMode.HTML, reply_markup=back_kb)
                return

            # Current DB ka auto-backup pehle karo
            ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            auto_bak = os.path.join(_PROJECT_DIR, f"pre_restore_{ts}.db")
            with sqlite3.connect(DB_PATH) as src:
                bak = sqlite3.connect(auto_bak)
                src.backup(bak)
                bak.close()

            # Replace DB
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
            try: db_block_user(uid, True)
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

    # ── CHANNEL ADD — 2 STEP (Forward + Link) ───────────
    ch_set_key = context.user_data.get("ch_set_key", "channels")

    if awaiting == "ch_forward":
        # ✅ Forward se sirf ID detect karo — naam admin khud type karega
        fwd_chat = None
        if getattr(msg, 'forward_from_chat', None):
            fwd_chat = msg.forward_from_chat
        elif getattr(getattr(msg, 'forward_origin', None), 'chat', None):
            fwd_chat = msg.forward_origin.chat

        if fwd_chat and getattr(fwd_chat, 'type', '') in ('channel', 'supergroup'):
            context.user_data["new_ch_id"]   = str(fwd_chat.id)
            context.user_data["awaiting"]    = "ch_name"
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
            await msg.reply_text(
                "❌ <b>Channel post forward nahi mili!</b>\n\n"
                "⚠️ Sirf <b>channel ki post</b> forward karo\n"
                "(group message ya personal message nahi chalega)\n\n"
                "Dobara try karo:\n"
                "Channel kholo → koi bhi post → Forward → Yahan bhejo",
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

            if not value:
                await msg.reply_text("⚠️ Kuch bhejo — emoji ya text!", reply_markup=back_kb)
                return

            cfg_set(emoji_key, value)
            preview = "✨ Premium animated emoji!" if is_premium else value
            await msg.reply_text(
                f"✅ <b>Set ho gaya!</b>\n\nKey: <code>{emoji_key}</code>\n"
                f"Value: {preview}",
                parse_mode=ParseMode.HTML, reply_markup=back_kb)
        return

    # ── VOICE CAPTION INPUT ───────────────────────────
    if awaiting == "voice_caption":
        cfg_set("voice_caption", msg.text.strip())
        await msg.reply_text(
            f"✅ <b>Voice caption set ho gaya!</b>\n\n<code>{msg.text.strip()}</code>",
            parse_mode=ParseMode.HTML, reply_markup=back_kb)
        return

    # ── SIMPLE CONFIG KEYS ───────────────────────────
    key_map = {
        "deposit_link":          "deposit_link",
        "deposit_text":          "deposit_text",
        "welcome_text":          "welcome_text",
        "joined_text":           "joined_text",
        "btn_verify_label":      "btn_verify_label",
        "btn_deposit_label":     "btn_deposit_label",
        "alert_not_joined":      "alert_not_joined",
        "alert_blocked":         "alert_blocked",
        "register_link":         "register_link",
        "register_instructions": "register_instructions",
        "dm_agent_text":         "dm_agent_text",
    }
    if awaiting in key_map:
        cfg_set(key_map[awaiting], msg.text.strip())
        label = awaiting.replace("_", " ").title()
        await msg.reply_text(
            f"✅ <b>{label}</b> update ho gaya!",
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
