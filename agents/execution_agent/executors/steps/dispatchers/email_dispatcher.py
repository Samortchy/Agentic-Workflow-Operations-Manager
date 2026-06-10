import json
import os
import smtplib
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

from pathlib import Path as _Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=_Path(__file__).parents[6] / ".env", override=False)

from ..base_step import BaseStep, StepResult
from ...core.envelope import resolve_path


# Body field names checked in order when scanning prior step data.
_BODY_KEYS = ("body","email_body","draft_email_reply", "draft_escalation_brief", "draft_report_ready", "draft_summary_ready", "rendered")


class EmailDispatcher(BaseStep):
    """
    Dispatches an email reply built by a prior processor step.

    Dry-run mode (EMAIL_DRY_RUN=true, the default): writes the email to
    output/emails/{task_id}_{step_name}.txt instead of sending via SMTP.

    Config fields
    -------------
    recipient_field : str   Dot-notation envelope path resolving to recipient.
    log_audit       : bool  If True, append a line to output/audit/audit_log.jsonl.
    attach_field    : str   Optional — dot-notation path to a file path to attach.
    """

    def run(self, envelope: dict, config: dict) -> StepResult:
        try:
            # 1. Resolve recipient.
            recipient_field = config.get("recipient_field", "")
            if not recipient_field:
                return StepResult(
                    success=False, data={}, error="config.recipient_field is required"
                )
            try:
                recipient = resolve_path(envelope, recipient_field)
            except KeyError:
                recipient = None

            # Trusted-recipient resolution: replies must reach the verified sender.
            # If the configured field is missing or isn't a real email address, fall back
            # to the From: header the poller captured from the email envelope (trusted) —
            # never an LLM-populated or body-embedded address.
            if not recipient or "@" not in str(recipient):
                recipient = self._extract_from_email(envelope.get("raw_text", "")) or recipient

            # 2. Find email body from most recent step that has one.
            body = self._find_body(envelope)

            # 3. Dry run or real send.
            task_id = envelope.get("task", {}).get("task_id", "unknown")
            step_name = envelope.get("execution", {}).get("agent_name", "email")
            log_audit: bool = config.get("log_audit", False)

            attach_path: str | None = None
            attach_field = config.get("attach_field")
            if attach_field:
                try:
                    attach_path = resolve_path(envelope, attach_field)
                except KeyError:
                    attach_path = None

            dry_run = os.environ.get("EMAIL_DRY_RUN", "true").lower() == "true"

            if dry_run:
                result_data = self._dry_run(task_id, step_name, recipient, body, attach_path)
               
               
            else:
                result_data = self._smtp_send(recipient, body, attach_path)

            if log_audit:
                audit_id = self._write_audit(envelope, recipient, result_data)
                result_data["audit_log_id"] = audit_id

            return StepResult(success=True, data=result_data, error=None)

        except Exception as e:
            return StepResult(success=False, data={}, error=str(e))

    # ------------------------------------------------------------------
    # Recipient helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_from_email(raw_text: str) -> str | None:
        """Extract the sender email from a 'From: ...' line in the raw text."""
        import re
        for line in raw_text.splitlines():
            if line.lower().startswith("from:"):
                # Match bare email or angle-bracket form: From: Name <email@x.com>
                m = re.search(r"<([^>]+@[^>]+)>", line) or re.search(r"[\w.+-]+@[\w.+-]+\.\w+", line)
                if m:
                    return m.group(1) if "<" in line else m.group(0)
        return None

    # ------------------------------------------------------------------
    # Body extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _find_body(envelope: dict) -> str:
        steps = envelope.get("execution", {}).get("steps", {})
        

        for step in reversed(steps.values()):
            data = step.get("data", {})

            for key in _BODY_KEYS:
                if key in data:
                    return str(data[key])

        return ""
    # ------------------------------------------------------------------
    # Dry-run path
    # ------------------------------------------------------------------

    @staticmethod
    def _dry_run(
        task_id: str, step_name: str, recipient: str, body: str, attach_path: str | None
    ) -> dict:
        out_dir = Path("output/emails")
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{task_id}_{step_name}.txt"
        out_path = out_dir / filename

        lines = [
            f"To: {recipient}",
            f"Generated-at: {datetime.now(timezone.utc).isoformat()}",
            "",
            body or "(no body found in prior steps)",
        ]
        if attach_path:
            lines.insert(2, f"Attachment: {attach_path}")

        out_path.write_text("\n".join(lines), encoding="utf-8")
        return {"dry_run": True, "recipient": recipient, "output_path": str(out_path)}

    # ------------------------------------------------------------------
    # SMTP send path
    # ------------------------------------------------------------------

    @staticmethod
    def _smtp_send(recipient: str, body: str, attach_path: str | None) -> dict:
        smtp_host     = os.environ.get("SMTP_HOST", "localhost")
        smtp_port     = int(os.environ.get("SMTP_PORT", "587"))
        smtp_user     = os.environ.get("SMTP_USER", "")
        smtp_password = os.environ.get("SMTP_PASSWORD", "")
        smtp_from     = os.environ.get("SMTP_FROM", smtp_user)

        msg = MIMEMultipart()
        msg["From"]    = smtp_from
        msg["To"]      = recipient
        msg["Subject"] = "Office Workflow — automated reply"
        msg.attach(MIMEText(body, "plain"))

        if attach_path and Path(attach_path).exists():
            part = MIMEBase("application", "octet-stream")
            part.set_payload(Path(attach_path).read_bytes())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{Path(attach_path).name}"',
            )
            msg.attach(part)

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, [recipient], msg.as_string())

        return {"reply_sent": True, "recipient": recipient}

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    @staticmethod
    def _write_audit(envelope: dict, recipient: str, result_data: dict) -> str:
        audit_dir = Path("output/audit")
        audit_dir.mkdir(parents=True, exist_ok=True)
        audit_path = audit_dir / "audit_log.jsonl"

        audit_id = str(uuid.uuid4())
        entry = {
            "audit_id":    audit_id,
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "envelope_id": envelope.get("envelope_id", "unknown"),
            "agent_name":  envelope.get("execution", {}).get("agent_name", "unknown"),
            "recipient":   recipient,
            "result":      result_data,
        }
        with audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        return audit_id
