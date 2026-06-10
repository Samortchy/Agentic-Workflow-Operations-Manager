"""
email_poller.py — Watches the agent Gmail inbox for unread emails and feeds
each one into the AWOM pipeline.

Run from the agents/ directory:
    python email_poller.py

Flow per email
--------------
1. Connect to Gmail via IMAP SSL.
2. Search INBOX for UNSEEN messages.
3. For each: extract From, Subject, body text.
4. POST to the pipeline API → task registered in backend → worker executes.
5. Mark email as SEEN so it isn't reprocessed.

Requirements
------------
- IMAP must be enabled in Gmail settings:
  Gmail → Settings → See all settings → Forwarding and POP/IMAP → Enable IMAP
- SMTP_PASSWORD must be a Google App Password (not your account password).
  Gmail → Google Account → Security → 2-Step Verification → App passwords
"""

import ssl_patch  # noqa: F401 — must be first

import email
import email.header
import imaplib
import logging
import os
import re
import time
from html.parser import HTMLParser
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=False)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("email_poller")

IMAP_HOST     = os.environ.get("IMAP_HOST", "imap.gmail.com")
IMAP_PORT     = int(os.environ.get("IMAP_PORT", "993"))
IMAP_USER     = os.environ.get("SMTP_USER", "")
IMAP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
PIPELINE_URL  = os.environ.get("PIPELINE_URL", "http://localhost:8000")
POLL_INTERVAL = int(os.environ.get("EMAIL_POLL_INTERVAL", "30"))
COMPANY_ID    = os.environ.get("COMPANY_ID", "").strip() or None


# ── HTML → plain text ────────────────────────────────────────────────────────

class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str):
        self._parts.append(data)

    def get_text(self) -> str:
        return "\n".join(p for p in self._parts if p.strip())


def _strip_html(html: str) -> str:
    s = _HTMLStripper()
    try:
        s.feed(html)
    except Exception:
        # Fallback: crude tag removal
        return re.sub(r"<[^>]+>", " ", html)
    return s.get_text()


# ── Email parsing ─────────────────────────────────────────────────────────────

def _decode_header(raw) -> str:
    """Decode a possibly RFC2047-encoded header. Never raises on malformed input."""
    if not raw:
        return ""
    try:
        # Standard robust idiom — handles mixed encoded-words/charsets cleanly.
        return str(email.header.make_header(email.header.decode_header(raw)))
    except Exception:
        pass
    # Fallback: best-effort manual decode that tolerates odd chunk/charset types.
    try:
        parts = []
        for chunk, charset in email.header.decode_header(raw):
            if isinstance(chunk, (bytes, bytearray)):
                enc = charset if isinstance(charset, str) else "utf-8"
                parts.append(bytes(chunk).decode(enc, errors="replace"))
            else:
                parts.append(str(chunk))   # str/int/anything → str
        return "".join(parts)
    except Exception:
        return str(raw)


def _decode_part(part) -> str | None:
    """Decode one message part to text, tolerating odd payload/charset types.
    Returns None if the part has no usable text (so callers can skip it)."""
    try:
        payload = part.get_payload(decode=True)
        if not isinstance(payload, (bytes, bytearray)):
            return None  # multipart container, None, or an unexpected type (e.g. int)
        charset = part.get_content_charset()
        if not isinstance(charset, str):
            charset = "utf-8"
        return bytes(payload).decode(charset, errors="replace")
    except Exception:
        return None


def _extract_body(msg: email.message.Message) -> str:
    """Return the best plain-text body we can find in the message."""
    plain: list[str] = []
    html:  list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            if "attachment" in str(part.get("Content-Disposition", "")):
                continue
            text = _decode_part(part)
            if text is None:
                continue
            ct = part.get_content_type()
            if ct == "text/plain":
                plain.append(text)
            elif ct == "text/html":
                html.append(text)
    else:
        text = _decode_part(msg)
        if text is not None:
            if msg.get_content_type() == "text/html":
                html.append(text)
            else:
                plain.append(text)

    if plain:
        return "\n".join(plain).strip()
    if html:
        return _strip_html("\n".join(html)).strip()
    return ""


def _parse_message(raw_bytes: bytes) -> tuple[str, str, str]:
    """Return (sender, subject, body)."""
    msg     = email.message_from_bytes(raw_bytes)
    sender  = _decode_header(msg.get("From", ""))
    subject = _decode_header(msg.get("Subject", "(no subject)"))
    body    = _extract_body(msg)
    return sender, subject, body


# ── Pipeline call ─────────────────────────────────────────────────────────────

def _submit_to_pipeline(sender: str, subject: str, body: str) -> bool:
    """POST to the pipeline API. Returns True on success."""
    raw_text = (
        f"From: {sender}\n"
        f"Subject: {subject}\n"
        f"\n"
        f"{body}"
    ).strip()

    if not raw_text:
        logger.warning("Empty email body — skipping")
        return False

    payload: dict = {"raw_text": raw_text}
    if COMPANY_ID:
        payload["company_id"] = COMPANY_ID

    try:
        r = requests.post(
            f"{PIPELINE_URL}/api/pipeline",
            json=payload,
            timeout=60,
        )
        if r.ok:
            data = r.json()
            task_id = data.get("task", {}).get("task_id", "?")
            logger.info("Task registered: %s | subject: %r", task_id, subject[:60])
            return True
        else:
            logger.error("Pipeline rejected email: %s — %s", r.status_code, r.text[:200])
            return False
    except Exception as e:
        logger.error("Pipeline call failed: %s", e)
        return False


# ── Bounce / auto-mail filtering ─────────────────────────────────────────────
# Replies sent to non-deliverable addresses generate bounce / "delivery status"
# mail from mailer-daemon. These are not user requests and must not be fed to the
# pipeline (they only create noise). Detect and skip them.
_BOUNCE_SENDERS  = ("mailer-daemon", "postmaster", "no-reply", "noreply")
_BOUNCE_SUBJECTS = (
    "delivery status notification", "undelivered mail", "mail delivery",
    "delivery incomplete", "returned mail", "failure notice", "delivery has failed",
    "out of office", "automatic reply",
)


def _is_bounce(sender: str, subject: str) -> bool:
    s = (sender or "").lower()
    subj = (subject or "").lower()
    return (any(b in s for b in _BOUNCE_SENDERS)
            or any(b in subj for b in _BOUNCE_SUBJECTS))


# ── IMAP polling ──────────────────────────────────────────────────────────────

def _connect() -> imaplib.IMAP4_SSL:
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    mail.login(IMAP_USER, IMAP_PASSWORD)
    mail.select("INBOX")
    return mail


def _process_unseen(mail: imaplib.IMAP4_SSL) -> int:
    """Fetch and process all UNSEEN emails. Returns count processed."""
    _, data = mail.search(None, "UNSEEN")
    ids = data[0].split()
    if not ids:
        return 0

    processed = 0
    for uid in ids:
        try:
            _, msg_data = mail.fetch(uid, "(RFC822)")
            # The fetch response can contain non-tuple items (flags, closing parens),
            # so msg_data[0][1] may be an int and message_from_bytes() then crashes with
            # "'int' object has no attribute 'decode'". Pick the element whose second
            # member is the actual RFC822 byte payload.
            raw = next((p[1] for p in (msg_data or [])
                        if isinstance(p, tuple) and len(p) >= 2 and isinstance(p[1], (bytes, bytearray))), None)
            if not isinstance(raw, (bytes, bytearray)):
                logger.warning("uid=%s: fetch returned no RFC822 body — skipping", uid)
                continue
            sender, subject, body = _parse_message(raw)

            if _is_bounce(sender, subject):
                logger.info("Skipping bounce/auto email from %s | %r", sender, subject[:60])
                continue   # finally still marks it \Seen so it won't recur

            logger.info("Processing email from %s | %r", sender, subject[:60])

            ok = _submit_to_pipeline(sender, subject, body)

            if ok:
                processed += 1
        except Exception as e:
            logger.error("Failed to process message uid=%s: %s", uid, e)
        finally:
            # Mark as SEEN regardless — a bad email must not be retried every poll.
            try:
                mail.store(uid, "+FLAGS", "\\Seen")
            except Exception as e:
                logger.warning("Could not mark uid=%s as seen: %s", uid, e)

    return processed


def poll_forever() -> None:
    if not IMAP_USER or not IMAP_PASSWORD:
        logger.error(
            "SMTP_USER / SMTP_PASSWORD not set in .env — "
            "cannot connect to Gmail IMAP"
        )
        return

    logger.info(
        "Email poller started | inbox=%s | pipeline=%s | interval=%ds",
        IMAP_USER, PIPELINE_URL, POLL_INTERVAL,
    )

    mail: imaplib.IMAP4_SSL | None = None

    while True:
        try:
            if mail is None:
                mail = _connect()
                logger.info("Connected to Gmail IMAP")

            # NOOP keeps the connection alive and re-syncs the mailbox
            mail.noop()
            count = _process_unseen(mail)
            if count:
                logger.info("Processed %d email(s)", count)

        except imaplib.IMAP4.abort:
            logger.warning("IMAP connection dropped — reconnecting")
            mail = None
        except Exception as e:
            logger.error("Poll error: %s — reconnecting", e)
            try:
                if mail:
                    mail.logout()
            except Exception:
                pass
            mail = None

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    poll_forever()
