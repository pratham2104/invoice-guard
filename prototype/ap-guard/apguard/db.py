"""SQLite schema and helpers."""
import hashlib
import hmac
import re
import sqlite3
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS vendors (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    domains TEXT NOT NULL,              -- comma separated official domains
    status TEXT NOT NULL DEFAULT 'active',
    remit_address TEXT
);
CREATE TABLE IF NOT EXISTS vendor_contacts (
    id INTEGER PRIMARY KEY,
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    name TEXT, email TEXT NOT NULL, phone TEXT,
    trusted INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS vendor_bank_accounts (
    id INTEGER PRIMARY KEY,
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    fingerprint TEXT NOT NULL,          -- HMAC of normalized account, never the raw number
    last4 TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    effective_date TEXT
);
CREATE TABLE IF NOT EXISTS purchase_orders (
    po_number TEXT PRIMARY KEY,
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    amount REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'  -- open | closed
);
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY,
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    invoice_number TEXT NOT NULL,
    amount REAL NOT NULL,
    po_number TEXT,
    status TEXT NOT NULL DEFAULT 'paid', -- paid | open
    invoice_date TEXT,
    UNIQUE(vendor_id, invoice_number)
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    message_id TEXT UNIQUE,
    filename TEXT,
    received_at TEXT,
    sender TEXT, subject TEXT,
    vendor_id INTEGER,
    verdict TEXT, score INTEGER,
    extraction_json TEXT, findings_json TEXT,
    case_id TEXT
);
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    message_pk INTEGER, vendor_id INTEGER,
    state TEXT NOT NULL,
    severity TEXT, risk_score INTEGER, summary TEXT,
    verification_started_by TEXT,
    created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS case_events (
    id INTEGER PRIMARY KEY,
    case_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    detail_json TEXT,
    prev_hash TEXT, hash TEXT
);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or config.DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def normalize_account(raw: str) -> str:
    """Digits-only for US accounts; upper-case alnum for IBANs."""
    s = re.sub(r"[\s\-]", "", raw or "")
    return s.upper() if re.match(r"^[A-Za-z]{2}\d{2}", s) else re.sub(r"\D", "", s)


def fingerprint(raw_account: str) -> str:
    return hmac.new(config.FINGERPRINT_KEY, normalize_account(raw_account).encode(),
                    hashlib.sha256).hexdigest()


def last4(raw_account: str) -> str:
    return normalize_account(raw_account)[-4:]
