import os
import sqlite3
from datetime import datetime, timedelta, time, date

import pytz
from flask import Flask, request
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv


# -------------------------
# Load environment variables
# -------------------------
load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM")

USER1 = os.getenv("USER1")
USER2 = os.getenv("USER2")

TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")
DROP_HOUR = int(os.getenv("DROP_HOUR", "13"))
DROP_MINUTE = int(os.getenv("DROP_MINUTE", "30"))
CHECK_HOUR = int(os.getenv("CHECK_HOUR", "10"))
CHECK_MINUTE = int(os.getenv("CHECK_MINUTE", "0"))

TZ = pytz.timezone(TIMEZONE)

DB_FILE = "bot.db"

# Twilio client
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

app = Flask(__name__)


# -------------------------
# Bot signature + constants
# -------------------------
BOT_SIG = "\n\n ⭐ Anlin Bot"

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def format_puzzle_date(d: date) -> str:
    # Example: 14th Jan (Wed)
    return f"{ordinal(d.day)} {MONTHS[d.month - 1]} ({WEEKDAYS[d.weekday()]})"


def format_puzzle_date_str(puzzle_date_str: str) -> str:
    # puzzle_date_str is dd-mm-YYYY
    d = datetime.strptime(puzzle_date_str, "%d-%m-%Y").date()
    return format_puzzle_date(d)


# -------------------------
# Database helpers
# -------------------------
def db():
    return sqlite3.connect(DB_FILE)


def init_db():
    conn = db()
    cur = conn.cursor()

    # log plays for each cycle/puzzle date
    cur.execute("""
    CREATE TABLE IF NOT EXISTS play_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT NOT NULL,
        puzzle_date TEXT NOT NULL,
        played_at TEXT NOT NULL
    )
    """)

    # settings
    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """)

    cur.execute("INSERT OR IGNORE INTO settings(key, value) VALUES('paused', '0')")
    cur.execute("INSERT OR IGNORE INTO settings(key, value) VALUES('pause_until', '')")

    conn.commit()
    conn.close()


def set_setting(key, value):
    conn = db()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", (key, value))
    conn.commit()
    conn.close()


def get_setting(key):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def clear_logs():
    conn = db()
    cur = conn.cursor()
    cur.execute("DELETE FROM play_log")
    conn.commit()
    conn.close()


def log_play(user, puzzle_date):
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO play_log(user, puzzle_date, played_at) VALUES(?, ?, ?)",
        (user, puzzle_date, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def has_played(user, puzzle_date):
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM play_log WHERE user=? AND puzzle_date=?",
        (user, puzzle_date)
    )
    count = cur.fetchone()[0]
    conn.close()
    return count > 0


def has_anyone_played(puzzle_date):
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM play_log WHERE puzzle_date=?",
        (puzzle_date,)
    )
    count = cur.fetchone()[0]
    conn.close()
    return count > 0


# -------------------------
# Time & cycle logic
# -------------------------
def now_ist():
    return datetime.now(TZ)


def get_today_drop_datetime(day=None):
    """Return drop datetime for a given IST date."""
    if day is None:
        day = now_ist().date()
    return TZ.localize(datetime.combine(day, time(DROP_HOUR, DROP_MINUTE)))


def get_check_datetime(day=None):
    """Return check datetime for a given IST date (10:00AM)."""
    if day is None:
        day = now_ist().date()
    return TZ.localize(datetime.combine(day, time(CHECK_HOUR, CHECK_MINUTE)))


def get_current_puzzle_date():
    """
    Current cycle logic (based on LinkedIn drop time at 1:30 PM IST):

    - After today's drop time -> today's puzzle date
    - Before today's drop time -> yesterday's puzzle date
    """
    n = now_ist()
    today = n.date()
    drop_today = get_today_drop_datetime(today)

    if n >= drop_today:
        return today.strftime("%d-%m-%Y")

    y = today - timedelta(days=1)
    return y.strftime("%d-%m-%Y")


def is_within_play_window():
    """
    Accept !played within:
    from drop_time of puzzle_date until drop_time next day.
    """
    n = now_ist()
    puzzle_date_str = get_current_puzzle_date()
    puzzle_date = datetime.strptime(puzzle_date_str, "%d-%m-%Y").date()

    drop_dt = get_today_drop_datetime(puzzle_date)
    next_drop_dt = get_today_drop_datetime(puzzle_date + timedelta(days=1))

    return drop_dt <= n < next_drop_dt


def puzzle_date_for_10am_check():
    """
    At 10AM of a given day, we should check yesterday's dropped puzzle.
    Example: 16th 10AM -> check puzzle dropped on 15th.
    """
    n = now_ist()
    y = n.date() - timedelta(days=1)
    return y.strftime("%d-%m-%Y")


# -------------------------
# Bot helpers
# -------------------------
def send_whatsapp(to, body):
    client.messages.create(
        from_=TWILIO_WHATSAPP_FROM,
        to=to,
        body=body
    )


def other_user(sender):
    return USER2 if sender == USER1 else USER1


def sender_name(sender):
    return "Alvin" if sender == USER1 else "Ananya"


def is_paused():
    paused = get_setting("paused") == "1"
    pause_until = (get_setting("pause_until") or "").strip()

    if not paused:
        return False

    # since pause is indefinite now, just keep paused
    # (pause_until retained only for compatibility)
    if pause_until:
        try:
            until_dt = datetime.fromisoformat(pause_until)
            if now_ist() > until_dt:
                set_setting("paused", "0")
                set_setting("pause_until", "")
                return False
        except:
            pass

    return True


# -------------------------
# Daily 10AM check job
# -------------------------
def daily_check_job():
    if is_paused():
        print("Bot paused -> daily check skipped")
        return

    puzzle_date = puzzle_date_for_10am_check()

    if not has_anyone_played(puzzle_date):
        puzzle_date_fmt = format_puzzle_date_str(puzzle_date)

        msg = (
            "⚠️ Game Alert!\n"
            "😕 Neither of you played LinkedIn Games for: "
            f"{puzzle_date_fmt}.\n"
            "🔥 Don’t break the streak — go solve it now!"
            + BOT_SIG
        )
        send_whatsapp(USER1, msg)
        send_whatsapp(USER2, msg)
        print("10AM check: sent to both for", puzzle_date_fmt)
    else:
        print("10AM check: at least one played for", puzzle_date)


# -------------------------
# Flask webhook
# -------------------------
@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    sender = request.form.get("From", "")
    text = (request.form.get("Body", "") or "").strip()
    msg = text.lower()

    resp = MessagingResponse()

    # allow only your 2 numbers
    if sender not in [USER1, USER2]:
        resp.message("❌ Access denied." + BOT_SIG)
        return str(resp)

    # Allowed commands only
    if msg == "!status":
        puzzle_date = format_puzzle_date_str(get_current_puzzle_date())
        today_str = format_puzzle_date(now_ist().date())

        if is_paused():
            resp.message(
                "⏸️ Bot paused!\n\n"
                f"📍 LinkedIn Games running on: {puzzle_date}\n"
                f"📍 Today's Date: {today_str}"
                + BOT_SIG
            )
        else:
            resp.message(
                "✅ Bot active!\n\n"
                f"📍 LinkedIn Games running on: {puzzle_date}\n"
                f"📍 Today's Date: {today_str}"
                + BOT_SIG
            )
        return str(resp)

    if msg == "!pause":
        set_setting("paused", "1")
        set_setting("pause_until", "")
        resp.message(
            "⏸️ Bot paused indefinitely. Send ⁠ !resume ⁠ to resume."
        )
        return str(resp)

    if msg == "!resume":
        set_setting("paused", "0")
        set_setting("pause_until", "")
        resp.message("✅ Bot resumed!")
        return str(resp)

    if msg == "!reset":
        clear_logs()
        resp.message("🧹 Reset done! All play logs cleared." + BOT_SIG)
        return str(resp)
    
    if msg == "!allplayed":
        if is_paused():
            resp.message("⏸️ Bot paused!" + BOT_SIG)
            return str(resp)

        if not is_within_play_window():
            resp.message("⏳ Too late for this cycle!" + BOT_SIG)
            return str(resp)

        puzzle_date_str = get_current_puzzle_date()

        # Log sender if not already logged
        if not has_played(sender, puzzle_date_str):
            log_play(sender, puzzle_date_str)

        # Minimal reply only
        resp.message("✅ Noted!")
        return str(resp)


    if msg == "!played":
        if is_paused():
            resp.message("⏸️ Bot paused!")
            return str(resp)

        if not is_within_play_window():
            resp.message("⏳ Too late for this cycle!")
            return str(resp)

        puzzle_date_str = get_current_puzzle_date()
        puzzle_date_fmt = format_puzzle_date_str(puzzle_date_str)

        # prevent duplicate spam
        if has_played(sender, puzzle_date_str):
            resp.message(f"✅ Already recorded for: {puzzle_date_fmt}.")
            return str(resp)

        log_play(sender, puzzle_date_str)

        other = other_user(sender)
        name = sender_name(sender)

        # notify other person
        notify = (
            "📛 Update!\n"
            f"{name} has completed LinkedIn Games for: {puzzle_date_fmt}.\n"
            "Don't miss your turn!"
            + BOT_SIG
        )
        send_whatsapp(other, notify)

        resp.message(
            "✅ Noted! I informed the other person for: "
            f"{puzzle_date_fmt}."
        )
        return str(resp)

    # anything else
    resp.message(
        "🤔 Sorry, I didn’t quite understand that!\n"
        "Try using !status to view bot stats."
        + BOT_SIG
    )
    return str(resp)


# -------------------------
# Run everything
# -------------------------
def start_scheduler():
    scheduler = BackgroundScheduler(timezone=str(TZ))
    scheduler.add_job(daily_check_job, "cron", hour=CHECK_HOUR, minute=CHECK_MINUTE)
    scheduler.start()
    return scheduler


if __name__ == "__main__":
    init_db()
    scheduler = start_scheduler()

    print("✅ Bot started!")
    print(f"Timezone: {TIMEZONE}")
    print(f"Drop time: {DROP_HOUR:02d}:{DROP_MINUTE:02d} IST")
    print(f"Daily check: {CHECK_HOUR:02d}:{CHECK_MINUTE:02d} IST")

    app.run(host="0.0.0.0", port=5000)