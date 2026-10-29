import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date, datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

# All "what is today" date math runs in the bot owner's local tz, not the
# container's UTC. Without this, between local-evening and UTC-midnight
# `date.today()` reports tomorrow, so days_until is off by one for the
# evening read of the dashboard.
LOCAL_TZ = ZoneInfo(os.getenv("TZ") or "UTC")

from urllib.parse import urlparse
from database import SessionLocal
from models import Person, Setting, PushSubscription

try:
    from pywebpush import webpush, WebPushException
    WEBPUSH_AVAILABLE = True
except ImportError:
    WEBPUSH_AVAILABLE = False

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT") or "587")
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM") or SMTP_USER

VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_CLAIMS_EMAIL = os.getenv("VAPID_CLAIMS_EMAIL") or "admin@example.com"


def get_setting(db: Session, key: str, default: str = None) -> str:
    setting = db.query(Setting).filter(Setting.key == key).first()
    return setting.value if setting else default


def calculate_days_until(birthday: date) -> int:
    today = datetime.now(LOCAL_TZ).date()
    this_year_birthday = birthday.replace(year=today.year)
    if this_year_birthday < today:
        this_year_birthday = birthday.replace(year=today.year + 1)
    return (this_year_birthday - today).days


# Alerts fire on exact-match thresholds, not a window. e.g. with the default
# "60,30,7,0", a person whose birthday is 60d away gets one alert today and
# another at 30d, 7d, and on the day; nothing on the days in between.
DEFAULT_THRESHOLDS = "60,30,7,0"


def parse_thresholds(s: str | None) -> set[int]:
    out: set[int] = set()
    for tok in (s or "").split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            n = int(tok)
        except ValueError:
            continue
        if n >= 0:
            out.add(n)
    return out


def get_alerting_birthdays(db: Session) -> list:
    """Return the people who match an alert threshold today, sorted by
    days_until ascending. People who match no threshold are not returned."""
    raw = get_setting(db, "notify_thresholds", DEFAULT_THRESHOLDS) or DEFAULT_THRESHOLDS
    thresholds = parse_thresholds(raw)
    if not thresholds:
        return []
    out = []
    for person in db.query(Person).all():
        d = calculate_days_until(person.birthday)
        if d in thresholds:
            out.append({"name": person.name, "birthday": person.birthday, "days_until": d})
    return sorted(out, key=lambda x: x["days_until"])


def send_push_notifications(test: bool = False) -> bool:
    if not WEBPUSH_AVAILABLE:
        print(f"[{datetime.now()}] pywebpush not available")
        return False

    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        print(f"[{datetime.now()}] VAPID keys not configured")
        return False

    db = SessionLocal()
    try:
        subscriptions = db.query(PushSubscription).all()
        if not subscriptions:
            print(f"[{datetime.now()}] No push subscriptions found")
            return False

        if test:
            payload = {
                "title": "Birthday Reminder",
                "body": "Push notifications are working!",
                "url": "/"
            }
        else:
            upcoming = get_alerting_birthdays(db)
            if not upcoming:
                return True

            body_parts = []
            for b in upcoming[:3]:
                if b["days_until"] == 0:
                    body_parts.append(f"{b['name']}: TODAY!")
                elif b["days_until"] == 1:
                    body_parts.append(f"{b['name']}: Tomorrow")
                else:
                    body_parts.append(f"{b['name']}: {b['days_until']} days")

            if len(upcoming) > 3:
                body_parts.append(f"...and {len(upcoming) - 3} more")

            payload = {
                "title": f"{len(upcoming)} upcoming birthday(s)",
                "body": ", ".join(body_parts),
                "url": "/"
            }

        success_count = 0

        print(f"[{datetime.now()}] Sending push with payload: {payload}")

        for sub in subscriptions:
            subscription_info = {
                "endpoint": sub.endpoint,
                "keys": {
                    "p256dh": sub.p256dh_key,
                    "auth": sub.auth_key
                }
            }

            # Set aud claim to the push service origin
            parsed = urlparse(sub.endpoint)
            aud = f"{parsed.scheme}://{parsed.netloc}"
            claims = {"sub": f"mailto:{VAPID_CLAIMS_EMAIL}", "aud": aud}

            try:
                response = webpush(
                    subscription_info=subscription_info,
                    data=json.dumps(payload),
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims=claims
                )
                print(f"[{datetime.now()}] Push success for {sub.endpoint[:50]}... - Status: {response.status_code}")
                success_count += 1
            except WebPushException as e:
                print(f"[{datetime.now()}] Push failed for {sub.endpoint[:50]}...: {e}")
                if e.response and e.response.status_code in [404, 410]:
                    db.delete(sub)
                    db.commit()
                    print(f"[{datetime.now()}] Removed invalid subscription")

        print(f"[{datetime.now()}] Sent push notifications to {success_count}/{len(subscriptions)} subscribers")
        return success_count > 0
    except Exception as e:
        print(f"[{datetime.now()}] Failed to send push notifications: {e}")
        return False
    finally:
        db.close()


def send_notification_email():
    db = SessionLocal()
    try:
        email = get_setting(db, "notification_email")
        upcoming = get_alerting_birthdays(db)
        if not upcoming:
            return

        # Send browser push notifications (optional; only if VAPID keys are set)
        if VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY:
            send_push_notifications()

        # Send email if configured
        if not email or not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
            return

        subject = f"Birthday Reminder: {len(upcoming)} upcoming birthday(s)"

        body_lines = ["Upcoming birthdays:\n"]
        for b in upcoming:
            if b["days_until"] == 0:
                body_lines.append(f"- {b['name']}: TODAY!")
            elif b["days_until"] == 1:
                body_lines.append(f"- {b['name']}: Tomorrow")
            else:
                body_lines.append(f"- {b['name']}: in {b['days_until']} days ({b['birthday'].strftime('%B %d')})")

        body = "\n".join(body_lines)

        msg = MIMEMultipart()
        msg["From"] = SMTP_FROM
        msg["To"] = email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        print(f"[{datetime.now()}] Sent birthday reminder email to {email}")
    except Exception as e:
        print(f"[{datetime.now()}] Failed to send email: {e}")
    finally:
        db.close()


def start_scheduler():
    scheduler = BackgroundScheduler(timezone=LOCAL_TZ)
    scheduler.add_job(
        send_notification_email,
        "cron",
        hour=18,
        minute=0,
        id="birthday_reminder"
    )
    scheduler.start()
    print(f"Optional email/web-push reminder scheduler started (daily at 18:00 {LOCAL_TZ.key})")
    return scheduler
