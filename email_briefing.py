"""Email briefing as plain text: mailto or SMTP."""
import logging
import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate
from urllib.parse import quote

from storage.config import Config

logger = logging.getLogger(__name__)


def _briefing_to_plain_text(briefing: dict) -> str:
    """Format briefing as plain-text body."""
    parts = [
        briefing.get("headline", "Briefing"),
        "",
        briefing.get("summary", ""),
        "",
        "KEY DEVELOPMENTS",
        briefing.get("developments", ""),
        "",
    ]
    for key, title in [
        ("context", "CONTEXT"),
        ("actors", "ACTORS"),
        ("outlook", "OUTLOOK"),
    ]:
        val = briefing.get(key, "").strip()
        if val:
            parts.extend([title, val, ""])
    watch = briefing.get("watch_indicators") or []
    if watch:
        parts.append("WHAT TO WATCH")
        parts.extend(f"  • {w}" for w in watch)
        parts.append("")
    return "\n".join(parts).strip()


def get_briefing_subject(briefing: dict) -> str:
    headline = (briefing.get("headline") or "Briefing").strip()
    return f"GeoPulse: {headline[:80]}"


def email_briefing_mailto(briefing: dict, to: str) -> str:
    """Return mailto: URL for opening in default mail client."""
    subject = get_briefing_subject(briefing)
    body = _briefing_to_plain_text(briefing)
    to = (to or "").strip()
    if not to:
        return ""
    return f"mailto:{quote(to)}?subject={quote(subject)}&body={quote(body)}"


def email_briefing_smtp(briefing: dict, to: str) -> None:
    """Send briefing via SMTP. Raises on failure."""
    cfg = Config.email_config()
    smtp_cfg = cfg.get("smtp", {})
    host = smtp_cfg.get("host", "").strip()
    port = int(smtp_cfg.get("port", 587))
    user = smtp_cfg.get("user", "").strip()
    password = smtp_cfg.get("password", "")
    from_addr = (smtp_cfg.get("from_addr") or user or "").strip()
    if not host or not user or not to.strip():
        raise ValueError("SMTP host, user, and recipient are required")
    msg = MIMEText(_briefing_to_plain_text(briefing), "plain", "utf-8")
    msg["Subject"] = get_briefing_subject(briefing)
    msg["From"] = from_addr or user
    msg["To"] = to.strip()
    msg["Date"] = formatdate(localtime=True)
    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        s.login(user, password)
        s.sendmail(from_addr or user, [to.strip()], msg.as_string())
    logger.info("Briefing emailed to %s via SMTP", to)
