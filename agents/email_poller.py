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

def _decode_header(raw: str | None) -> str:
    if not raw:
        return ""
    parts = []
    for chunk, charset in email.header.decode_header(raw):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return "".join(parts)


def _extract_body(msg: email.message.Message) -> str:
    """Return the best plain-text body we can find in the message."""
    plain: list[str] = []
    html:  list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = part.get("Content-Disposition", "")
            if "attachment" in cd:
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if ct == "text/plain":
                plain.append(text)
            elif ct == "text/html":
                html.append(text)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
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
            raw = msg_data[0][1]
            sender, subject, body = _parse_message(raw)

            logger.info("Processing email from %s | %r", sender, subject[:60])

            ok = _submit_to_pipeline(sender, subject, body)

            # Mark as SEEN regardless — avoids reprocessing bad emails in a crash loop
            mail.store(uid, "+FLAGS", "\\Seen")

            if ok:
                processed += 1
        except Exception as e:
            logger.error("Failed to process message uid=%s: %s", uid, e)

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
