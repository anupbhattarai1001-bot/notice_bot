"""
BMC Student Helper Bot
======================
A Telegram bot for Butwal Multiple Campus (BMC) students.

INSTALLATION COMMAND:
    pip install "python-telegram-bot[job-queue]" tzdata

RUNNING THE BOT:
    python bot.py
"""

import asyncio
import html
import json
import logging
import os
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo  # Built into Python 3.9+

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import Forbidden, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# --------------------------------------------------------------------------
# 1. CONFIG & LOGGING
# --------------------------------------------------------------------------
# Your BotFather Token is set directly below:
BOT_TOKEN = os.getenv("BOT_TOKEN", "8595472714:AAGtzWVl6YAVt_ZycI2OjyiUGs3Dp6FRUig")

NEPAL_TZ = ZoneInfo("Asia/Kathmandu")     # All dates/times use Nepal time
ALERT_TIME = time(7, 0, tzinfo=NEPAL_TZ)  # Daily check runs at 07:00 AM
SUBSCRIBERS_FILE = Path("subscribers.json")

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("bmc_bot")

# --------------------------------------------------------------------------
# 2. SUBSCRIBERS (Chat IDs that receive broadcast alerts)
# --------------------------------------------------------------------------
def load_subscribers() -> set[int]:
    if SUBSCRIBERS_FILE.exists():
        try:
            return set(json.loads(SUBSCRIBERS_FILE.read_text()))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read %s: %s", SUBSCRIBERS_FILE, exc)
    return set()

def save_subscribers() -> None:
    try:
        SUBSCRIBERS_FILE.write_text(json.dumps(sorted(SUBSCRIBERS)))
    except OSError as exc:
        logger.error("Could not save subscribers: %s", exc)

SUBSCRIBERS: set[int] = load_subscribers()

# --------------------------------------------------------------------------
# 3. EDITABLE DATA (For BMC Students to update)
# --------------------------------------------------------------------------

# ---- 3a. MAJOR EVENTS / EXAMS -------------------------------------------
EVENTS = [
    {
        "date": date(2026, 10, 5),
        "title": "First Internal Assessment",
        "time": "07:30 AM",
        "location": "Science Block",
        "programs": "B.Sc. Physics & CSIT (1st year)",
    },
    {
        "date": date(2026, 11, 20),
        "title": "CSIT 1st Semester Model Exam",
        "time": "08:00 AM",
        "location": "Computer Lab, Science Block",
        "programs": "CSIT (1st year)",
    },
]

# ---- 3b. HOLIDAYS / CAMPUS CLOSURES -------------------------------------
HOLIDAYS = {
    date(2026, 10, 19): "Dashain (Fulpati)",
    date(2026, 10, 20): "Dashain (Maha Ashtami)",
    date(2026, 10, 21): "Dashain (Vijaya Dashami)",
    date(2026, 11, 9): "Tihar (Laxmi Puja)",
}

# ---- 3c. WEEKLY CLASS ROUTINE -------------------------------------------
CLASS_ROUTINE = {
    "B.Sc. Physics (1st year)": [
        ("Sunday", "07:00 - 08:00", "Mechanics", "Room 101"),
        ("Monday", "08:00 - 09:00", "Heat & Thermodynamics", "Room 101"),
        ("Tuesday", "07:00 - 09:00", "Physics Practical", "Physics Lab"),
        ("Thursday", "09:00 - 10:00", "Mathematical Physics", "Room 102"),
    ],
    "B.Sc. CSIT (1st year)": [
        ("Sunday", "08:00 - 09:00", "Introduction to IT", "Room 201"),
        ("Monday", "07:00 - 08:00", "C Programming", "Computer Lab"),
        ("Tuesday", "09:00 - 10:00", "Digital Logic", "Room 201"),
        ("Wednesday", "07:00 - 08:00", "Mathematics I", "Room 202"),
        ("Thursday", "10:00 - 12:00", "C Programming Lab", "Computer Lab"),
    ],
}

# ---- 3d. SYLLABUS --------------------------------------------------------
SYLLABUS = {
    "B.Sc. CSIT (1st year)": [
        ("Introduction to Information Technology", "https://example.com/csit/iit.pdf"),
        ("C Programming", "https://example.com/csit/c-programming.pdf"),
        ("Digital Logic", "https://example.com/csit/digital-logic.pdf"),
        ("Mathematics I", "https://example.com/csit/math1.pdf"),
    ],
    "B.Sc. Physics (1st year)": [
        ("Mechanics", "https://example.com/physics/mechanics.pdf"),
        ("Heat & Thermodynamics", "https://example.com/physics/heat.pdf"),
        ("Mathematical Physics", "https://example.com/physics/math-physics.pdf"),
    ],
}

# ---- 3e. NOTICES ---------------------------------------------------------
NOTICES = [
    ("2026-09-25", "First Internal Assessment routine published for 1st-year programs."),
    ("2026-09-20", "Library will open 7:00 AM - 4:00 PM on weekdays."),
    ("2026-09-15", "Scholarship application forms available at the Admin Block."),
]

# ---- 3f. CAMPUS MAP ------------------------------------------------------
CAMPUS_BLOCKS = [
    ("🏛 Admin Block", "Principal's office, accounts, admission & exam sections."),
    ("🔬 Science Labs", "Physics, Chemistry & Biology labs plus the CSIT Computer Lab."),
    ("📚 Library", "Reading hall, reference books, past question papers."),
    ("🍵 Canteen", "Tea, snacks and meals; a common student meeting spot."),
]

# --------------------------------------------------------------------------
# 4. MESSAGE BUILDERS
# --------------------------------------------------------------------------
e = html.escape

def today_nepal() -> date:
    return datetime.now(NEPAL_TZ).date()

def build_routine_text() -> str:
    parts = ["📅 <b>Routine – 1st Year (Physics &amp; CSIT)</b>\n"]
    for program, rows in CLASS_ROUTINE.items():
        parts.append(f"<b>{e(program)}</b>")
        for day, slot, subject, room in rows:
            parts.append(f"• {e(day)} {e(slot)} – {e(subject)} (<i>{e(room)}</i>)")
        parts.append("")

    upcoming = sorted(
        (ev for ev in EVENTS if ev["date"] >= today_nepal()),
        key=lambda ev: ev["date"],
    )
    parts.append("📝 <b>Upcoming Exams / Events</b>")
    if upcoming:
        for ev in upcoming:
            parts.append(
                f"• <b>{ev['date']:%d %b %Y}</b> – {e(ev['title'])}\n"
                f"    🕗 {e(ev['time'])} | 📍 {e(ev['location'])} | 🎓 {e(ev['programs'])}"
            )
    else:
        parts.append("No upcoming events listed.")
    return "\n".join(parts)

def build_syllabus_text() -> str:
    parts = ["📖 <b>1st-Year Syllabus</b>\n"]
    for program, subjects in SYLLABUS.items():
        parts.append(f"<b>{e(program)}</b>")
        for name, link in subjects:
            parts.append(f'• <a href="{e(link, quote=True)}">{e(name)}</a>')
        parts.append("")
    return "\n".join(parts)

def build_notice_text() -> str:
    parts = ["📢 <b>Recent BMC Notices</b>\n"]
    for when, headline in NOTICES:
        parts.append(f"• <b>{e(when)}</b> – {e(headline)}")
    return "\n".join(parts)

def build_map_text() -> str:
    parts = ["🗺 <b>BMC Campus Guide</b>\n"]
    for name, desc in CAMPUS_BLOCKS:
        parts.append(f"<b>{e(name)}</b>\n{e(desc)}\n")
    return "\n".join(parts)

def build_welcome_text(first_name: str) -> str:
    return (
        f"👋 Namaste, <b>{e(first_name)}</b>!\n\n"
        "Welcome to the <b>BMC Student Helper Bot</b> for Butwal Multiple Campus.\n"
        "You are now subscribed to exam &amp; holiday alerts 🔔\n\n"
        "Tap a button below, or use /routine, /syllabus, /notice, /map.\n"
        "Send /stop to unsubscribe from alerts."
    )

SECTIONS = {
    "routine": build_routine_text,
    "syllabus": build_syllabus_text,
    "notice": build_notice_text,
    "map": build_map_text,
}

# --------------------------------------------------------------------------
# 5. KEYBOARDS
# --------------------------------------------------------------------------
def main_menu_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    alerts_label = "🔔 Alerts: ON" if chat_id in SUBSCRIBERS else "🔕 Alerts: OFF"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📅 Routine", callback_data="routine"),
                InlineKeyboardButton("📖 Syllabus", callback_data="syllabus"),
            ],
            [
                InlineKeyboardButton("📢 Notices", callback_data="notice"),
                InlineKeyboardButton("🗺 Campus Map", callback_data="map"),
            ],
            [InlineKeyboardButton(alerts_label, callback_data="toggle_alerts")],
        ]
    )

def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Back to menu", callback_data="menu")]]
    )

# --------------------------------------------------------------------------
# 6. COMMAND HANDLERS
# --------------------------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if chat_id not in SUBSCRIBERS:
        SUBSCRIBERS.add(chat_id)
        save_subscribers()
        logger.info("New subscriber %s (total: %d)", chat_id, len(SUBSCRIBERS))

    name = update.effective_user.first_name if update.effective_user else "Student"
    await update.message.reply_text(
        build_welcome_text(name),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard(chat_id),
    )

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    SUBSCRIBERS.discard(update.effective_chat.id)
    save_subscribers()
    await update.message.reply_text(
        "🔕 You are unsubscribed from alerts. Send /start to subscribe again."
    )

def make_section_command(key: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            SECTIONS[key](),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=back_keyboard(),
        )
    return handler

# --------------------------------------------------------------------------
# 7. BUTTON (CALLBACK QUERY) HANDLER
# --------------------------------------------------------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    data = query.data

    if data == "menu":
        name = query.from_user.first_name if query.from_user else "Student"
        text = build_welcome_text(name)
        markup = main_menu_keyboard(chat_id)
    elif data == "toggle_alerts":
        if chat_id in SUBSCRIBERS:
            SUBSCRIBERS.discard(chat_id)
        else:
            SUBSCRIBERS.add(chat_id)
        save_subscribers()
        name = query.from_user.first_name if query.from_user else "Student"
        text = build_welcome_text(name)
        markup = main_menu_keyboard(chat_id)
    elif data in SECTIONS:
        text = SECTIONS[data]()
        markup = back_keyboard()
    else:
        return

    try:
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=markup,
        )
    except TelegramError as exc:
        logger.debug("edit_message_text skipped: %s", exc)

# --------------------------------------------------------------------------
# 8. BROADCAST & DAILY JOBQUEUE
# --------------------------------------------------------------------------
async def broadcast(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    for chat_id in list(SUBSCRIBERS):
        try:
            await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
        except Forbidden:
            SUBSCRIBERS.discard(chat_id)
            save_subscribers()
            logger.info("Removed %s (blocked the bot)", chat_id)
        except TelegramError as exc:
            logger.warning("Failed to send to %s: %s", chat_id, exc)
        await asyncio.sleep(0.05)

async def daily_event_check(context: ContextTypes.DEFAULT_TYPE) -> None:
    today = today_nepal()
    tomorrow = today + timedelta(days=1)
    logger.info("Daily check for %s (tomorrow = %s)", today, tomorrow)

    for ev in EVENTS:
        if ev["date"] == tomorrow:
            await broadcast(
                context,
                f"⚠️ <b>REMINDER:</b> {e(ev['title'])} begins tomorrow at "
                f"{e(ev['time'])} in {e(ev['location'])}!\n"
                f"🎓 For: {e(ev['programs'])}",
            )

    if tomorrow in HOLIDAYS and today not in HOLIDAYS:
        await broadcast(
            context,
            f"🎉 <b>HOLIDAY NOTICE:</b> BMC will remain closed tomorrow on "
            f"account of {e(HOLIDAYS[tomorrow])}.",
        )

# --------------------------------------------------------------------------
# 9. APPLICATION SETUP & STARTUP
# --------------------------------------------------------------------------
async def post_init(app: Application) -> None:
    await app.bot.set_my_commands(
        [
            BotCommand("start", "Welcome & menu (subscribes you to alerts)"),
            BotCommand("help", "Show the menu"),
            BotCommand("routine", "Class & exam routine"),
            BotCommand("syllabus", "1st-year syllabus"),
            BotCommand("notice", "Recent college notices"),
            BotCommand("map", "Campus blocks guide"),
            BotCommand("stop", "Unsubscribe from alerts"),
        ]
    )

    app.job_queue.run_daily(
        daily_event_check,
        time=ALERT_TIME,
        name="daily_event_check",
    )

application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

application.add_handler(CommandHandler(["start", "help"], start_command))
application.add_handler(CommandHandler("stop", stop_command))
for _key in SECTIONS:
    application.add_handler(CommandHandler(_key, make_section_command(_key)))
application.add_handler(CallbackQueryHandler(button_handler))

if __name__ == "__main__":
    if BOT_TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
        raise SystemExit("Set the BOT_TOKEN variable first.")
    logger.info("BMC Student Helper Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
