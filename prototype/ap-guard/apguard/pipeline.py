"""End-to-end: .eml -> parse -> extract -> evaluate -> log -> (HOLD) open case."""
import json
from dataclasses import dataclass
from pathlib import Path

from . import cases, rules
from .extractor import extract
from .parser import parse_eml


@dataclass
class Result:
    filename: str
    verdict: object
    case_id: str | None
    extraction: object
    skipped: bool = False


def process_eml(conn, path, use_llm: bool | None = None) -> Result:
    path = Path(path)
    email = parse_eml(path)
    seen = conn.execute("SELECT * FROM messages WHERE message_id=?", (email.message_id,)).fetchone()
    if seen:
        return Result(path.name, None, seen["case_id"], None, skipped=True)

    ex = extract(email, use_llm=use_llm)
    verdict = rules.evaluate(conn, email, ex)

    cur = conn.execute(
        "INSERT INTO messages(message_id,filename,received_at,sender,subject,vendor_id,verdict,score,"
        "extraction_json,findings_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (email.message_id, path.name, email.date, email.sender_email, email.subject, verdict.vendor_id,
         verdict.verdict, verdict.score, json.dumps(ex.redacted(), default=str),
         json.dumps([f.__dict__ for f in verdict.findings], default=str)))
    pk = cur.lastrowid
    case_id = None
    if verdict.verdict == "HOLD":
        case_id = cases.create_case(conn, pk, verdict)
        conn.execute("UPDATE messages SET case_id=? WHERE id=?", (case_id, pk))
    conn.commit()
    return Result(path.name, verdict, case_id, ex)


def process_dir(conn, directory, use_llm=None) -> list[Result]:
    return [process_eml(conn, p, use_llm) for p in sorted(Path(directory).glob("*.eml"))]
