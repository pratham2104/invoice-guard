"""Parse .eml files into a plain dataclass. Pure stdlib."""
import re
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
from pathlib import Path


@dataclass
class ParsedEmail:
    filename: str
    message_id: str
    subject: str
    sender_name: str
    sender_email: str
    sender_domain: str
    reply_to_email: str
    reply_to_domain: str
    date: str
    auth_results: str
    body: str
    attachments: list = field(default_factory=list)

    @property
    def text(self) -> str:
        return f"{self.subject}\n{self.body}"


def _domain(addr: str) -> str:
    return addr.rsplit("@", 1)[-1].lower() if "@" in addr else ""


def parse_eml(path: Path | str) -> ParsedEmail:
    path = Path(path)
    with path.open("rb") as fh:
        msg = BytesParser(policy=policy.default).parse(fh)
    name, email = parseaddr(str(msg.get("From", "")))
    _, reply_to = parseaddr(str(msg.get("Reply-To", "")))
    body_part = msg.get_body(preferencelist=("plain", "html"))
    body = body_part.get_content() if body_part else ""
    if body_part is not None and body_part.get_content_type() == "text/html":
        body = re.sub(r"<[^>]+>", " ", body)
    attachments = [p.get_filename() for p in msg.iter_attachments() if p.get_filename()]
    return ParsedEmail(
        filename=path.name,
        message_id=str(msg.get("Message-ID", path.name)),
        subject=str(msg.get("Subject", "")),
        sender_name=name,
        sender_email=email.lower(),
        sender_domain=_domain(email),
        reply_to_email=reply_to.lower(),
        reply_to_domain=_domain(reply_to),
        date=str(msg.get("Date", "")),
        auth_results=str(msg.get("Authentication-Results", "")),
        body=body,
        attachments=attachments,
    )
