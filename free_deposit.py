"""
╔══════════════════════════════════════════════════════════════════════╗
║     ULTRA PREMIUM FORCE-JOIN BOT  —  VERSION 3.0 COMPLETE          ║
║     Set 1 → Force Join  |  Set 2 → After Join (Deposit)            ║
║     ✅ Full Named Buttons | Custom Alert | Premium Flow | Advanced  ║
╚══════════════════════════════════════════════════════════════════════╝
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

# Project directory use karo by default - Render pe hamesha writable hota hai
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("DB_PATH", os.path.join(_PROJECT_DIR, "bot_data.db"))

# ═══════════════════════════════════════════════════════════════════
#  KEEP-ALIVE SERVER
# ═══════════════════════════════════════════════════════════════════

class _Ping(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, *a): pass

def start_keep_alive(port=10000):
    server = HTTPServer(("0.0.0.0", port), _Ping)
    t = threading.Thread(target=server.serve_forever)
    t.daemon = False  # ✅ FIX: daemon=False so server stays alive
    t.start()
    logger.info(f"Keep-alive server: port {port}")

# ═══════════════════════════════════════════════════════════════════
#  DATABASE SETUP
# ═══════════════════════════════════════════════════════════════════

def _conn():
    try:
        abs_path = os.path.abspath(DB_PATH)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        return sqlite3.connect(abs_path)
    except (PermissionError, OSError):
        # /data ya koi aur restricted path set hai - project folder use karo
        fallback = os.path.join(_PROJECT_DIR, "bot_data.db")
        logger.warning(f"⚠️ '{DB_PATH}' access nahi mila — fallback: {fallback}")
        return sqlite3.connect(fallback)

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
                "🔐 <b>Hey {name}! Welcome to Free Recharge Bot</b> 💸\n\n"
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
            "btn_verify_label":  "✅ Verify & Claim Reward 🎁",
            "btn_deposit_label": "🚀 Deposit Karo & Reward Pao 💰",
            # ── Join button style: "naam_only" / "naam_arrow" / "join_naam" / "custom" ──
            "join_btn_style":  "naam_only",
            "join_btn_prefix": "👉",
            # ── Buttons per row: "1" or "2" ──
            "btns_per_row": "2",
        }
        for k, v in defaults.items():
            c.execute("INSERT OR IGNORE INTO config (key,value) VALUES (?,?)", (k, v))
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

def _join_btn_label(ch, cfg):
    """
    Channel join button ka label:
    - naam_only  → sirf channel naam (admin ka diya hua)
    - naam_arrow → Channel Naam ↗
    - join_naam  → Join Channel Naam
    - custom     → [prefix] Channel Naam
    """
    style  = cfg.get("join_btn_style", "naam_only")
    prefix = cfg.get("join_btn_prefix", "👉").strip()
    name   = ch.get("name", "Channel").strip()

    if style == "naam_arrow":
        return f"{name} ↗"
    elif style == "join_naam":
        return f"Join {name}"
    elif style == "custom" and prefix:
        return f"{prefix} {name}"
    else:
        return name  # naam_only — sirf naam, koi extra nahi

def _build_channel_buttons(channels, cfg):
    """Channels ki rows banata hai — 1 ya 2 per row as per config."""
    per_row = int(cfg.get("btns_per_row", "2"))
    rows, pair = [], []
    for ch in channels:
        label = _join_btn_label(ch, cfg)
        pair.append(InlineKeyboardButton(label, url=ch.get("link", "https://t.me/")))
        if len(pair) == per_row:
            rows.append(pair); pair = []
    if pair:
        rows.append(pair)
    return rows

def kb_force_join(not_joined, cfg):
    rows = _build_channel_buttons(not_joined, cfg)
    verify_label = cfg.get("btn_verify_label", "✅ Verify & Claim Reward 🎁")
    rows.append([InlineKeyboardButton(verify_label, callback_data="verify_join")])
    return InlineKeyboardMarkup(rows)

def kb_after_join(deposit_link, cfg):
    after_chs = get_channels("channels_after")
    rows = _build_channel_buttons(after_chs, cfg)
    deposit_label = cfg.get("btn_deposit_label", "🚀 Deposit Karo & Reward Pao 💰")
    rows.append([InlineKeyboardButton(
        deposit_label,
        url=deposit_link if deposit_link else "https://t.me/"
    )])
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
         InlineKeyboardButton("Join Btn Style",            callback_data="admin_join_style")],
        [InlineKeyboardButton("💬 Alert Messages",         callback_data="admin_alerts"),
         InlineKeyboardButton("🔢 Buttons Per Row",        callback_data="admin_btn_row")],
        [InlineKeyboardButton("━━━━ 📨 BROADCAST ━━━━", callback_data="noop")],
        [InlineKeyboardButton("📨 Broadcast Message",      callback_data="admin_broadcast_menu"),
         InlineKeyboardButton("👑 Admin Manage",           callback_data="admin_manage_admins")],
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

async def send_joined_content(bot, chat_id, user_id, cfg):
    voice_id     = cfg.get("voice_file_id", "")
    joined_text  = cfg.get("joined_text", "✅ <b>Sab Channels Join Ho Gaye!</b>")
    deposit_link = cfg.get("deposit_link", "").strip()

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
            text=(
                "🎉 <b>Congratulations! Reward Unlock Ho Gaya!</b>\n\n"
                "✅ Saare channels join kar liye!\n"
                "🔊 <b>Ab sound on karo aur niche dekho</b> 👇"
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass
    await asyncio.sleep(0.8)

    # Step 2: Voice note
    if voice_id:
        try:
            await bot.send_voice(
                chat_id=chat_id,
                voice=voice_id,
                caption="🔊 <b>Sound On Karo</b> — Yeh message zaroor suno! 🎙️👆",
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning(f"Voice send failed: {e}")

    # Step 3: Main content + deposit buttons
    sent = await bot.send_message(
        chat_id=chat_id,
        text=joined_text,
        reply_markup=kb_after_join(deposit_link, cfg),
        parse_mode=ParseMode.HTML,
    )
    db_set_msg(user_id, sent.message_id)

    # Step 4: Second message — Register link + Instructions + DM Agent
    await asyncio.sleep(0.5)
    register_link  = cfg.get("register_link", "").strip()
    reg_instr      = cfg.get("register_instructions",
                             "📌 <b>REGISTER LINK</b> 📌\n\n{register_link}\n\n"
                             "<b>Send Screenshot Agent UID And Bank add Screenshot Send</b>")
    dm_agent_text  = cfg.get("dm_agent_text", "").strip()

    # Only send if at least register_link or dm_agent_text is set
    if register_link or dm_agent_text:
        reg_display = f'<a href="{register_link}">{register_link}</a>' if register_link else "—"
        second_text = reg_instr.replace("{register_link}", reg_display)
        if dm_agent_text:
            second_text += f"\n\n{dm_agent_text}"
        try:
            from telegram import LinkPreviewOptions
            await bot.send_message(
                chat_id=chat_id,
                text=second_text,
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=False),
            )
        except Exception as e:
            logger.warning(f"Second message send failed: {e}")

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
        text = cfg.get("welcome_text", "🔐 <b>Hey {name}!</b> Channels join karo.").format(
            name=user.first_name or "User")
        sent = await update.message.reply_text(
            text,
            reply_markup=kb_force_join(not_joined, cfg),
            parse_mode=ParseMode.HTML,
        )
        db_set_msg(user.id, sent.message_id)
    else:
        await send_joined_content(context.bot, update.effective_chat.id, user.id, cfg)

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
            cfg2      = cfg_get()
            base_text = cfg2.get("welcome_text",
                "🔐 <b>Hey {name}!</b>\n\nChannels join karo."
            ).format(name=user.first_name or "User")
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
        await send_joined_content(context.bot, q.message.chat_id, user.id, cfg)
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
            "📝 Welcome text bhejo.\n<code>{name}</code> = user ka naam",
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

    # ── JOIN BUTTON STYLE ──────────────────────────────
    elif data == "admin_join_style":
        style  = cfg.get("join_btn_style", "naam_only")
        prefix = cfg.get("join_btn_prefix", "👉")
        await q.edit_message_text(
            f"✏️ <b>Join Button Style</b>\n\n"
            f"Current: <b>{style}</b>  |  Prefix: <code>{prefix}</code>\n\n"
            f"<b>naam_only</b>  → <code>Earn With Komal</code>\n"
            f"<b>naam_arrow</b> → <code>Earn With Komal ↗</code>\n"
            f"<b>join_naam</b>  → <code>Join Earn With Komal</code>\n"
            f"<b>custom</b>     → <code>👉 Earn With Komal</code>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Naam Only",  callback_data="admin_jstyle_naam_only"),
                 InlineKeyboardButton("Naam ↗",     callback_data="admin_jstyle_naam_arrow")],
                [InlineKeyboardButton("Join Naam",  callback_data="admin_jstyle_join_naam"),
                 InlineKeyboardButton("Custom Prefix", callback_data="admin_jstyle_custom")],
                [InlineKeyboardButton("🔙 Back",    callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    elif data in ("admin_jstyle_naam_only", "admin_jstyle_naam_arrow", "admin_jstyle_join_naam"):
        style_map = {
            "admin_jstyle_naam_only":  "naam_only",
            "admin_jstyle_naam_arrow": "naam_arrow",
            "admin_jstyle_join_naam":  "join_naam",
        }
        cfg_set("join_btn_style", style_map[data])
        await q.answer(f"✅ Style set: {style_map[data]}", show_alert=True)
        await q.edit_message_text("👑 <b>Admin Panel</b>",
                                   reply_markup=kb_admin(), parse_mode=ParseMode.HTML)

    elif data == "admin_jstyle_custom":
        context.user_data["awaiting"] = "join_btn_prefix"
        await q.edit_message_text(
            "✏️ Custom prefix bhejo jo button ke aage lage:\n"
            "(e.g. <code>👉</code> ya <code>📢</code> ya <code>Join</code>)",
            reply_markup=kb_back("admin_join_style"), parse_mode=ParseMode.HTML)

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
        style  = cfg.get("join_btn_style", "naam_only")
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
            f"  🔘 Btn Style  : <b>{style}</b>\n"
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
            f"Kaunsa type ka broadcast karna hai?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Text",   callback_data="admin_bcast_text"),
                 InlineKeyboardButton("🖼 Photo",  callback_data="admin_bcast_photo")],
                [InlineKeyboardButton("🎥 Video",  callback_data="admin_bcast_video"),
                 InlineKeyboardButton("🔙 Back",   callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    elif data in ("admin_bcast_text", "admin_bcast_photo", "admin_bcast_video"):
        btype = data.replace("admin_bcast_", "")
        context.user_data["awaiting"]       = "broadcast"
        context.user_data["broadcast_type"] = btype
        hint = {
            "text":  "📝 <b>Text Broadcast</b>\n\nMessage bhejo (HTML allowed):",
            "photo": "🖼 <b>Photo Broadcast</b>\n\nPhoto bhejo (caption optional):",
            "video": "🎥 <b>Video Broadcast</b>\n\nVideo bhejo (caption optional):",
        }
        await q.edit_message_text(hint.get(btype, "Message bhejo:"),
                                   reply_markup=kb_back("admin_broadcast_menu"),
                                   parse_mode=ParseMode.HTML)

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

    # ── BROADCAST ────────────────────────────────────
    if awaiting == "broadcast":
        users  = db_all_users()
        btype  = context.user_data.pop("broadcast_type", "text")
        ok = fail = 0
        sm = await msg.reply_text(f"📨 Broadcast chal raha hai... (0/{len(users)})")
        for i, uid in enumerate(users):
            try:
                if btype == "photo" and msg.photo:
                    await context.bot.send_photo(uid,
                        photo=msg.photo[-1].file_id,
                        caption=msg.caption or "", parse_mode=ParseMode.HTML)
                elif btype == "video" and msg.video:
                    await context.bot.send_video(uid,
                        video=msg.video.file_id,
                        caption=msg.caption or "", parse_mode=ParseMode.HTML)
                else:
                    await context.bot.send_message(uid, msg.text or "",
                                                   parse_mode=ParseMode.HTML)
                ok += 1
            except Exception as e:
                logger.warning(f"Broadcast failed for {uid}: {e}")
                fail += 1
            await asyncio.sleep(0.05)   # rate limit se bachne ke liye
            if (i + 1) % 20 == 0:
                try: await sm.edit_text(f"📨 Chal raha hai... ({i+1}/{len(users)})")
                except: pass
        await sm.edit_text(
            f"📨 <b>Broadcast Done!</b>\n✅ Sent: {ok}\n❌ Failed: {fail}",
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
        # ✅ Forward se channel naam + ID auto detect karo
        fwd_chat = None
        if getattr(msg, 'forward_from_chat', None):
            fwd_chat = msg.forward_from_chat
        elif getattr(getattr(msg, 'forward_origin', None), 'chat', None):
            fwd_chat = msg.forward_origin.chat

        if fwd_chat and getattr(fwd_chat, 'type', '') in ('channel', 'supergroup'):
            context.user_data["new_ch_name"] = fwd_chat.title
            context.user_data["new_ch_id"]   = str(fwd_chat.id)
            context.user_data["awaiting"]    = "ch_link"
            sl = "Set-1" if ch_set_key == "channels" else "Set-2"
            await msg.reply_text(
                f"✅ <b>Channel Auto-Detect Ho Gaya!</b>\n\n"
                f"📢 Naam : <b>{fwd_chat.title}</b>\n"
                f"🆔 ID   : <code>{fwd_chat.id}</code>\n\n"
                f"➕ <b>{sl} — Step 2/2</b>\n\n"
                f"Ab channel ka <b>Invite Link</b> bhejo:\n"
                f"(e.g. <code>https://t.me/yourchannel</code>)",
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

    # ── JOIN BUTTON CUSTOM PREFIX ────────────────────
    if awaiting == "join_btn_prefix":
        cfg_set("join_btn_style", "custom")
        cfg_set("join_btn_prefix", msg.text.strip())
        await msg.reply_text(
            f"✅ Custom prefix set!\nButton dikhega: <code>{msg.text.strip()} Channel Naam</code>",
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
    logger.info("✅ Ultra Premium Force-Join Bot chal raha hai...")

    # ── Step 5: Manual get_updates loop ───────────────────
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
