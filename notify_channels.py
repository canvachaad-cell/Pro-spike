"""
notify_channels.py — Alert delivery channels for Pro-spike ledger exit alerts.

Channels:
    WhatsApp : CallMeBot REST API  (free, personal use only)
    Push     : ntfy.sh             (free, no account, topic name is the secret)
    Email    : Gmail SMTP over SSL

Design rules (AGENTS.md):
  * NO SILENT FAILURES — every failure is logged with a traceback to logs/alerts.log.
  * NO python-dotenv — the repo convention is a hand-rolled .env reader
    (dash_pages/_vikram_callback.py:374-392). python-dotenv is installed locally but is
    NOT in requirements.txt, so importing it would crash the Render deploy.
  * An UNCONFIGURED channel is a config state, not an error -> (False, "NOT_CONFIGURED").
  * Every network call carries an explicit timeout.
  * Only stdlib + requests (requests==2.31.0 is already in requirements.txt).
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from logging.handlers import RotatingFileHandler

import requests

# ---------------------------------------------------------------------------
# Logging — same RotatingFileHandler shape as auto_update_smart.py:22-26
# ---------------------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(ROOT_DIR, "logs"), exist_ok=True)

logger = logging.getLogger("alerts")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    _handler = RotatingFileHandler(
        os.path.join(ROOT_DIR, "logs", "alerts.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
    )
    _handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(_handler)

HTTP_TIMEOUT = 15
_ENV_PATH = os.path.join(ROOT_DIR, ".env")


# ---------------------------------------------------------------------------
# .env loading (no python-dotenv dependency) — ported from
# dash_pages/_vikram_callback.py:374-392, generalised to arbitrary keys.
# os.environ ALWAYS wins over .env so Render env vars take precedence.
# ---------------------------------------------------------------------------
def _read_env_key(name: str):
    """Resolve a config value: os.environ first, then the repo-root .env file."""
    val = os.environ.get(name)
    if val and val.strip():
        return val.strip()

    try:
        with open(_ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith(f"{name}="):
                    raw = line.split("=", 1)[1].strip().strip('"').strip("'")
                    return raw or None
    except OSError:
        # .env is optional (it is gitignored and absent on Render) — not an error.
        return None
    return None


def alerts_enabled() -> bool:
    v = (_read_env_key("ALERTS_ENABLED") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def channel_status() -> dict:
    """Report which channels are configured. Performs NO network calls."""
    email_to = _read_env_key("ALERT_EMAIL_TO")
    return {
        "whatsapp": bool(_read_env_key("WHATSAPP_PHONE") and _read_env_key("CALLMEBOT_APIKEY")),
        "ntfy": bool(_read_env_key("NTFY_TOPIC")),
        "email": bool(email_to and _read_env_key("GMAIL_APP_PASSWORD")),
    }


# ---------------------------------------------------------------------------
# WhatsApp via CallMeBot
#   https://api.callmebot.com/whatsapp.php?phone=<phone>&text=<urlencoded>&apikey=<key>
#   - phone MUST include the country code (e.g. +919876543210)
#   - text MUST be urlencoded -> handled by requests' params=, never hand-built
#   - WhatsApp markup (*bold*, _italic_) is supported
#   - Free tier is PERSONAL USE ONLY -> ONE batched digest per run, never spam
# ---------------------------------------------------------------------------
CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"


def send_whatsapp(text: str):
    """Returns (ok: bool, detail: str)."""
    phone = _read_env_key("WHATSAPP_PHONE")
    apikey = _read_env_key("CALLMEBOT_APIKEY")
    if not phone or not apikey:
        logger.info("send_whatsapp: NOT_CONFIGURED (WHATSAPP_PHONE / CALLMEBOT_APIKEY missing)")
        return False, "NOT_CONFIGURED"

    try:
        resp = requests.get(
            CALLMEBOT_URL,
            params={"phone": phone, "text": text, "apikey": apikey},
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.exception("send_whatsapp: request failed")
        return False, f"REQUEST_ERROR: {exc}"

    if resp.status_code != 200:
        logger.error("send_whatsapp: HTTP %s — %s", resp.status_code, resp.text[:300])
        return False, f"HTTP_{resp.status_code}"

    # CallMeBot returns HTTP 200 with a plain-text body; surface it for diagnostics.
    detail = (resp.text or "").strip()
    logger.info("send_whatsapp: OK (%s)", detail[:200])
    return True, detail or "OK"


# ---------------------------------------------------------------------------
# Phone push via ntfy.sh — auth optional; the topic name IS the secret.
# ---------------------------------------------------------------------------
NTFY_BASE = "https://ntfy.sh"


def send_ntfy(title: str, text: str, priority: str = "high", tags: str = ""):
    """Returns (ok: bool, detail: str)."""
    topic = _read_env_key("NTFY_TOPIC")
    if not topic:
        logger.info("send_ntfy: NOT_CONFIGURED (NTFY_TOPIC missing)")
        return False, "NOT_CONFIGURED"

    headers = {
        "Title": title,
        "Priority": priority,
        "Content-Type": "text/plain; charset=utf-8",
    }
    if tags:
        headers["Tags"] = tags

    try:
        resp = requests.post(
            f"{NTFY_BASE}/{topic}",
            data=text.encode("utf-8"),
            headers=headers,
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.exception("send_ntfy: request failed")
        return False, f"REQUEST_ERROR: {exc}"

    if resp.status_code != 200:
        logger.error("send_ntfy: HTTP %s — %s", resp.status_code, resp.text[:300])
        return False, f"HTTP_{resp.status_code}"

    logger.info("send_ntfy: OK")
    return True, "OK"


# ---------------------------------------------------------------------------
# Email via Gmail SMTP over SSL (transport shape from send_error_email.py:11,
# but with LOUD error handling instead of a bare except -> print).
# ---------------------------------------------------------------------------
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def send_email(subject: str, body: str):
    """Returns (ok: bool, detail: str)."""
    to_email = _read_env_key("ALERT_EMAIL_TO")
    from_email = _read_env_key("ALERT_EMAIL_FROM") or to_email
    password = _read_env_key("GMAIL_APP_PASSWORD")

    if not to_email or not from_email or not password:
        logger.info("send_email: NOT_CONFIGURED (ALERT_EMAIL_TO / GMAIL_APP_PASSWORD missing)")
        return False, "NOT_CONFIGURED"

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email

    server = None
    try:
        server = smtplib.SMTP_SSL(
            SMTP_HOST, SMTP_PORT, timeout=HTTP_TIMEOUT, context=ssl.create_default_context()
        )
        server.login(from_email, password)
        server.sendmail(from_email, [to_email], msg.as_string())
    except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
        logger.exception("send_email: send failed")
        return False, f"SMTP_ERROR: {exc}"
    finally:
        if server is not None:
            try:
                server.quit()
            except (smtplib.SMTPException, OSError):
                # Socket may already be gone; the send outcome is already known above.
                logger.warning("send_email: server.quit() failed (ignored)")

    logger.info("send_email: OK -> %s", to_email)
    return True, "OK"
