import os
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from ..base_step import BaseStep, StepResult


# Step data keys that carry scheduling outputs from prior steps.
_SLOT_KEYS        = ("proposed_slots", "selected_slot", "available_slots")
_PARTICIPANT_KEYS = ("participant_names", "participants", "attendees")


class CalendarDispatcher(BaseStep):
    """
    Mock calendar invite dispatcher (Phase 2 — no real Outlook/GCal API).

    Reads the confirmed slot and participant list from prior step data, then
    notifies the requester (organizer) AND the participants of the meeting
    details by email.

    Delivery follows the same convention as EmailDispatcher:
      - EMAIL_DRY_RUN=true (default): writes a notice file under output/invites/.
      - EMAIL_DRY_RUN=false: sends the invite over SMTP to organizer + participants.

    Config fields
    -------------
    monitor_rsvp : bool   Whether to track RSVPs (stored in result, not acted on).
    template     : str    Email template path (informational, not rendered here).
    """

    def run(self, envelope: dict, config: dict) -> StepResult:
        try:
            steps = envelope.get("execution", {}).get("steps", {})

            selected_slot: str | None = None
            participants:  list       = []

            for step_obj in reversed(list(steps.values())):
                data = step_obj.get("data", {})

                if selected_slot is None:
                    # Prefer an explicitly selected slot; fall back to first proposed.
                    selected_slot = data.get("selected_slot")
                    if selected_slot is None:
                        slots = data.get("proposed_slots") or data.get("available_slots")
                        if slots and isinstance(slots, list) and slots:
                            top = slots[0]
                            selected_slot = top.get("slot_start") if isinstance(top, dict) else top

                if not participants:
                    for key in _PARTICIPANT_KEYS:
                        raw = data.get(key)
                        if raw:
                            participants = raw if isinstance(raw, list) else [raw]
                            break

                if selected_slot and participants:
                    break

            task        = envelope.get("task", {})
            title       = task.get("title") or "Scheduled meeting"
            organizer   = task.get("requester_email")
            tzname      = self._find_timezone(steps)

            # Recipients = organizer + participants (deduped, email-shaped only).
            recipients = self._collect_recipients(organizer, participants)

            invite = {
                "invite_sent":   True,
                "selected_slot": selected_slot or "TBD",
                "participants":  participants,
                "organizer":     organizer,
                "monitor_rsvp":  config.get("monitor_rsvp", False),
                "note":          "Calendar API not connected — mock response",
            }

            subject = f"Meeting scheduled: {title}"
            body    = self._build_body(title, selected_slot, participants, tzname)

            dry_run = os.environ.get("EMAIL_DRY_RUN", "true").lower() == "true"
            if dry_run:
                invite["notice_path"] = self._write_invite(envelope, selected_slot, participants, tzname)
                invite["notified"]    = recipients
            else:
                sent = self._smtp_send(recipients, subject, body) if recipients else []
                invite["notified"] = sent

            return StepResult(success=True, data=invite, error=None)

        except Exception as e:
            return StepResult(success=False, data={}, error=str(e))

    # ------------------------------------------------------------------

    @staticmethod
    def _find_timezone(steps: dict) -> str:
        for step_obj in reversed(list(steps.values())):
            tz = step_obj.get("data", {}).get("timezone")
            if tz:
                return tz
        return "UTC"

    @staticmethod
    def _collect_recipients(organizer: str | None, participants: list) -> list:
        seen, out = set(), []
        for addr in [organizer, *participants]:
            if isinstance(addr, str) and "@" in addr and addr.lower() not in seen:
                seen.add(addr.lower())
                out.append(addr)
        return out

    @staticmethod
    def _format_slot(slot, tzname: str) -> str:
        """Render an ISO slot as a friendly local wall-clock string."""
        if not slot or not isinstance(slot, str):
            return "To be confirmed"
        try:
            dt = datetime.fromisoformat(slot)
            stamp = dt.strftime("%A, %d %B %Y at %H:%M")
            return f"{stamp} ({tzname})"
        except (ValueError, TypeError):
            return str(slot)

    @classmethod
    def _build_body(cls, title: str, slot, participants: list, tzname: str) -> str:
        when    = cls._format_slot(slot, tzname)
        people  = ", ".join(participants) if participants else "(to be confirmed)"
        return (
            "Hello,\n\n"
            "Your meeting has been scheduled. Here are the details:\n\n"
            f"  Subject      : {title}\n"
            f"  When         : {when}\n"
            f"  Participants : {people}\n\n"
            "This invite was arranged automatically by the Office Workflow assistant. "
            "Reply to this email if you need to reschedule.\n\n"
            "— Office Automation System"
        )

    @staticmethod
    def _smtp_send(recipients: list, subject: str, body: str) -> list:
        smtp_host     = os.environ.get("SMTP_HOST", "localhost")
        smtp_port     = int(os.environ.get("SMTP_PORT", "587"))
        smtp_user     = os.environ.get("SMTP_USER", "")
        smtp_password = os.environ.get("SMTP_PASSWORD", "")
        smtp_from     = os.environ.get("SMTP_FROM", smtp_user)

        msg = MIMEText(body, "plain")
        msg["From"]    = smtp_from
        msg["To"]      = ", ".join(recipients)
        msg["Subject"] = subject

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, recipients, msg.as_string())

        return recipients

    @classmethod
    def _write_invite(cls, envelope: dict, selected_slot, participants: list, tzname: str) -> str:
        task_id = envelope.get("task", {}).get("task_id", "unknown")
        out_dir = Path("output/invites")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{task_id}.txt"
        lines = [
            "MEETING SCHEDULE UPDATE",
            f"When         : {cls._format_slot(selected_slot, tzname)}",
            f"Participants : {', '.join(participants) if participants else '(none)'}",
            f"Generated-at : {datetime.now(timezone.utc).isoformat()}",
        ]
        out_path.write_text("\n".join(lines), encoding="utf-8")
        return str(out_path)
